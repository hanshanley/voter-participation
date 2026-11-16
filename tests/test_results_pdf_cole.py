import copy
from decimal import Decimal, ROUND_HALF_UP
import gzip
import json

import pytest

from scripts import results_granular as granular, results_native as native
from scripts import results_pdf_cole as cole, results_pdf_ocr as ocr
from scripts import results_intake as intake
from scripts.participation_intake.contract import encoded, observation_id, pin
from test_results_granular import template
from test_results_native import baseline, pdf_reader


def record():
    row = template("MO", "Cole County", "county")
    row["id"] = cole.TARGET
    row["election"] = {
        "date": "2026-11-03", "id": "missouri-2026-11-03-general",
        "qualification": "native", "type": "general", "year": 2026}
    row["geography"]["id"] = "native:MO:cole"
    row["geography"]["join"]["status"] = "unreviewed"
    row["measure"] = copy.deepcopy(cole.MEASURE)
    row["count"] = {"literal": 29108, "status": "reported", "value": 29108}
    row["source"].update(
        id="cole-native-turnout-20261113", url=cole.URL, input_sha256=cole.REVIEWED_SHA,
        selector={"native_unit": "Total", "physical_page": 1, "row": 30,
                  "table_id": "cole-complete-native-turnout-statistics"},
        fields={"native_unit": "Total", "ballots": 29108, "registered": 55406,
                "native_fraction": "52.54%"})
    row["source_clock"] = {"literal": "11/9/2026 10:05:40 AM", "timezone": None}
    row["view"].update(source_url=cole.URL, maps_approved=False, ballots=29108,
                       county_id="native:MO:cole")
    return row


def cells(values):
    return [{"text": value, "left": left, "right": left + width, "confidence": .999}
            for value, left, width in zip(values, (0, 900, 1100, 1300), (300, 140, 140, 140))]


def records(parent=None):
    rows = []
    for number, label in enumerate(cole.UNITS, 1):
        row = copy.deepcopy(parent or record())
        if number != 30:
            row["geography"].update(
                id=f"native:MO:cole:statistical-row-{number}", level="reporting_unit",
                name=label, parent_id="native:MO:cole")
            row["id"] = observation_id(
                row["source"]["id"], row["election"]["id"], row["geography"]["id"],
                row["measure"]["id"], row["measure"]["mode"])
            row["source"]["selector"].update(row=number, native_unit=label)
            row["source"]["fields"]["native_unit"] = label
        rows.append(row)
    return rows


def view(zero=False, revised=False, date="11/10/2026"):
    rows = [
        cells(["VoterTurnout"]), cells(["GENERAL ELECTION", "Date:" + date]),
        cells(["COLE COUNTY, MISSOURI"]),
        cells(["TUESDAY, NOVEMBER 3, 2026", "Time:10:05:40AM"]),
        cells(["ELECTION RESULTS"]), cells(["Page1/1"]),
        cells(["VOTER TURNOUT BY PRECINCT"]), cells(["OFFICIAL RESULTS"]),
        cells(["Precincts", "Ballots Cast", "Registered Voters", "% Turnout"]),
    ]
    counts = [0 if zero else 1 + (revised and index == 0) for index in range(28)]
    counts += [0 if zero else 2]
    counts += [sum(counts)]
    for label, count in zip(cole.UNITS, counts):
        registered = 10 if label in cole.LOCALITIES else 280
        percent = (Decimal(count) * 100 / registered).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP)
        rows.append(cells([label, str(count), str(registered), f"{percent:.2f}%"]))
    return {"role_cells": rows, "receipt": {
        "dpi": 180, "rotation_degrees": 0, "text_angle_classifier_enabled": False}}


def parse(monkeypatch, first=None, second=None, row=None, prior=None):
    pdf_reader(monkeypatch)
    first = first or view()
    second = copy.deepcopy(second or first)
    second["receipt"]["dpi"] = 240
    def views(body, **options):
        assert options == {"strict_role_alignment": True, "text_angle_classifier": False}
        return [first, second]
    monkeypatch.setattr(ocr, "first_page_views", views)
    return cole.statistics(b"\f" * 23, records(row), prior=prior)


@pytest.mark.parametrize("kind", ["current", "revised", "zero"])
def test_grid_retains_complete_rows_and_refreshes_only_the_reviewed_parent(monkeypatch, kind):
    result = parse(monkeypatch, view(zero=kind == "zero", revised=kind == "revised"))
    assert len(result["updates"]) == 30
    update = next(value for value in result["updates"] if value["id"] == cole.TARGET)
    assert update["id"] == cole.TARGET
    assert update["value"] == {"current": 30, "revised": 31, "zero": 0}[kind]
    assert update["registered"] == 280 and update["rate_compatible"] is False
    query = result["complete_native_query"]
    assert len(query["statistics"]) == 30
    assert query["statistics"][-2]["native_unit_kind"] == "nongeographic_absentee"
    assert sum(row["registered"] for row in query["statistics"][:-1]) == 560
    assert query["parent"]["registered"] == 280
    assert query["parent"]["native_report_status_literal"] == "OFFICIAL RESULTS"
    assert query["source_clock_timezone"] is None
    assert not result["geographic_joins_changed"] and not result["analytical_rates_promoted"]


@pytest.mark.parametrize("change", [
    "column", "unit", "parent", "fraction", "missing", "low_count", "absentee_stock",
    "election", "status", "clock", "duplicate", "angle", "negative", "unknown",
])
def test_grid_rejects_changed_roles_scope_ocr_and_unreconciled_facts(monkeypatch, change):
    candidate = view()
    rows = candidate["role_cells"]
    if change == "column":
        rows[-1][1]["left"], rows[-1][1]["right"] = 1200, 1250
    elif change == "unit":
        rows[9][0]["text"] = "An unreviewed precinct"
    elif change == "parent":
        rows[-1][1]["text"] = "31"
    elif change == "fraction":
        rows[9][3]["text"] = "20.00%"
    elif change == "missing":
        rows[9].pop(1)
    elif change == "low_count":
        rows[9][1]["confidence"] = .979
    elif change == "absentee_stock":
        rows[-2][2]["text"] = "281"
    elif change == "election":
        rows[3][0]["text"] = "TUESDAY NOVEMBER 3, 2024"
    elif change == "status":
        rows[7][0]["text"] = "UNOFFICIAL RESULTS"
    elif change == "clock":
        rows[1][1]["text"] = "Date:11/8/2026"
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[-1]))
    elif change == "angle":
        candidate["receipt"]["text_angle_classifier_enabled"] = True
    else:
        rows[9][1]["text"] = "-1" if change == "negative" else "?"
    with pytest.raises(ValueError):
        parse(monkeypatch, candidate)


def test_grid_rejects_disagreement_and_last_good_clock_rollback(monkeypatch):
    first = view()
    with pytest.raises(ValueError, match="disagreement"):
        parse(monkeypatch, first, view(revised=True))
    accepted = parse(monkeypatch, first)
    prior = {"source": accepted["complete_native_query"]["source"], "data": accepted}
    with pytest.raises(ValueError, match="regressed"):
        parse(monkeypatch, view(date="11/9/2026"), prior=prior)
    broken = copy.deepcopy(prior)
    broken["data"]["updates"][0]["value"] = 9999
    with pytest.raises(ValueError, match="last-good"):
        parse(monkeypatch, first, prior=broken)


def test_zero_registers_preserve_literal_undefined_fractions_without_promoting_rates(monkeypatch):
    candidate = view(zero=True)
    for row in candidate["role_cells"][9:]:
        row[2]["text"] = "0"
    result = parse(monkeypatch, candidate)
    assert all(row["fraction_reconciliation"] == "undefined_zero_register"
               for row in result["complete_native_query"]["statistics"])
    assert all(update["value"] == update["registered"] == 0
               and not update["rate_compatible"] for update in result["updates"])


def test_low_confidence_report_clock_is_not_borrowed_from_retrieval(monkeypatch):
    candidate = view()
    candidate["role_cells"][3][1]["confidence"] = .979
    with pytest.raises(ValueError, match="report-clock confidence"):
        parse(monkeypatch, candidate)


@pytest.mark.parametrize("field", ["denominator", "selector", "source", "measure"])
def test_grid_requires_the_original_qualified_source_frame(monkeypatch, field):
    row = record()
    if field == "denominator":
        row["denominator"] = {"qualified": True, "value": 55406}
    elif field == "selector":
        row["source"]["selector"]["row"] = 29
    elif field == "source":
        row["source"]["input_sha256"] = "0" * 64
    else:
        row["measure"]["literal"] = "Candidate total"
    with pytest.raises(ValueError, match="qualification changed"):
        parse(monkeypatch, row=row)


def test_default_source_plan_and_projection_keep_identity_and_withheld_rate(monkeypatch):
    row = record()
    before = baseline(intake.STATES)
    before["states/MO.json.gz"] = gzip.compress(encoded({
        "records": records(), "views": {"official": {"counties": [cole.TARGET],
            "precincts": [item["id"] for item in records()[:-1]]}}}), mtime=0)
    index = json.loads(before["index.json"])
    index["states"]["MO"] = {"file": "states/MO.json.gz", **pin(before["states/MO.json.gz"])}
    before["index.json"] = encoded(index)
    source, = native.source_plan(before)["MO"].values()
    assert source["adapter"] == "reviewed_cole_statistical_grid"
    result = parse(monkeypatch, view(revised=True))
    inputs = {"MO-cole": {"status": "reported", "source": result["complete_native_query"]["source"],
                       "data": result}}
    after, changes = granular.project(before, inputs)
    refreshed = next(item for item in granular.selected_records(after, "MO")
                     if item["id"] == cole.TARGET)
    assert refreshed["id"] == cole.TARGET and refreshed["count"]["value"] == 31
    assert refreshed["denominator"] is None and refreshed["view"]["reported_pct"] is None
    assert refreshed["geography"] == row["geography"]
    assert len(changes) == 30
