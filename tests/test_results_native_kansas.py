import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import io

import pytest

from scripts import results_granular as granular, results_intake as intake, results_native as native
from scripts.automatic_native_refresh import observation_identity, reviewed_measure_label
from scripts.participation_intake.contract import encoded, observation_id, pin, validate
from scripts.results_native_kansas import PROFILE, REVIEWED_INPUT_SHA
from test_results_granular import template


def reviewed_template():
    row = template("KS", "Greeley County", "county")
    row["source"].update(
        id="ks-greeley-official-general-20261103", url=PROFILE["url"],
        input_sha256=REVIEWED_INPUT_SHA,
        selector={"cells": ["A1", "A2", "A3"],
                  "selected_field": "A3 reported turnout total", "sheet": PROFILE["sheets"][0]})
    row["geography"]["id"] = "ks-greeley-county-official-general-20261103"
    row["measure"] = {
        "id": "native-source-reported-turnout-total", "kind": "voters_reported",
        "literal": "451 voted ... 9 provisionals = 460", "mode": "source_defined",
        "unit": "source_reported_voters_in_turnout_total"}
    row["count"] = {"value": 460, "literal": 460, "status": "reported"}
    row["denominator"] = {
        "value": 853, "literal": "Registered Voters",
        "basis": "native_registered_voters_same_official_county_report", "qualified": True}
    row["source_clock"] = {"literal": None, "timezone": None}
    row["view"].update(
        ballots=460, denominator=853, reported_pct=53.93, source_url=PROFILE["url"],
        source_update_label=None, participation_measure_kind="voters_reported",
        participation_measure_literal=(
            "Source-reported turnout total (451 voted + 9 counted provisionals)"),
        cast_ballot_count_qualified=False, unique_voter_count_qualified=False,
        maps_approved=False)
    row["id"] = observation_id(row["source"]["id"], row["election"]["id"],
                              row["geography"]["id"], row["measure"]["id"], "source_defined")
    return validate(row)


def workbook(total=460):
    openpyxl = pytest.importorskip("openpyxl")
    voted, counted, other = (total - 9, 9, 1) if total else (0, 0, 0)
    msd, gsd, hc = (voted - 162, 143, 19) if total else (0, 0, 0)
    fraction = (Decimal(total) * 100 / 853).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = PROFILE["sheets"][0]
    sheet["A1"] = "2026 General Election  853 Registered Voters "
    sheet["A2"] = (f"{voted} voted {counted + other} provisionals {counted} counted "
                   f"{other} new registrant did not.  {fraction}% turnout")
    sheet["A3"] = f"MSD-{msd}   GSD-{gsd}   HC-{hc}={voted}  {counted} provisionals = {total}"
    sheet["A9"], sheet["B9"] = "Candidate votes", 99999
    book.create_sheet(PROFILE["sheets"][1])["B2"] = 22222
    return book


def body(book):
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def baseline(row):
    shard = {"records": [row], "views": {"official": {"counties": [row["id"]]}}}
    compressed = intake.compressed(encoded(shard))
    return {"states/KS.json.gz": compressed, "index.json": encoded({
        "states": {"KS": {"file": "states/KS.json.gz", **pin(compressed)}}})}


def parse(original, row=None):
    return native.workbook_statistics(
        original, [row or reviewed_template()], native.WORKBOOK_PROFILES[PROFILE["url"]])


@pytest.mark.parametrize("total", [0, 461])
def test_revised_and_zero_turnout_refresh_without_stale_numeric_display_or_new_identity(total):
    row, original = reviewed_template(), body(workbook(total))
    data = parse(original, row)
    entry = {"status": "reported", "source": {"url": PROFILE["url"], **pin(original)}, "data": data}
    before = baseline(row)
    after, changes = granular.project(before, {"KS-workbook": entry})
    current, = granular.selected_records(after, "KS")
    assert current["count"]["value"] == total
    assert current["denominator"] == row["denominator"]
    assert current["view"]["reported_pct"] == pytest.approx(100 * total / 853)
    assert current["view"]["participation_measure_label"] == "Source-reported turnout total"
    assert current["view"]["native_record"]["reported_turnout_total"] == total
    assert current["view"]["participation_measure_literal_qualification"].startswith(
        "Initial accepted source literal")
    assert current["measure"] == row["measure"]
    assert observation_identity(current) == observation_identity(row)
    assert current["source_clock"]["literal"] is None
    assert current["source_clock"]["timezone"] is None
    assert current["reporting_status"]["complete"] is None
    assert current["geography"] == row["geography"]
    assert not current["view"]["cast_ballot_count_qualified"]
    assert not current["view"]["unique_voter_count_qualified"]
    assert not current["view"]["maps_approved"]
    assert len(changes) == 1
    assert data["factual_product"]["native_inventory"] == [
        {"name": name, "rows": None, "columns": None} for name in PROFILE["sheets"]]
    assert data["factual_product"]["tables"][0]["rows"][-1]["cells"][-1]["value"] == 99999
    assert data["coverage"]["other_counties_unknown"] == 104
    assert data["new_denominator_qualification"] is False
    validate(current)


@pytest.mark.parametrize("cell,old,new", [
    ("A1", "2026", "2024"), ("A1", "General", "Primary"),
    ("A1", "853", "0"), ("A2", "451 voted", "- voted"),
    ("A2", "10 provisionals", "11 provisionals"),
    ("A2", "53.93%", "99.99%"), ("A3", "MSD-289", "MSD-290"),
    ("A3", "9 provisionals", "8 provisionals"),
    ("A3", "= 460", "= 461"), ("A3", "MSD-", "Ballots-"),
])
def test_changed_election_unknown_counts_and_inconsistent_equations_fail_closed(cell, old, new):
    book = workbook()
    assert old in book.active[cell].value
    book.active[cell] = book.active[cell].value.replace(old, new)
    with pytest.raises(ValueError):
        parse(body(book))


@pytest.mark.parametrize("change", ["missing", "formula", "sheet", "private"])
def test_missing_formula_wrong_sheet_and_individual_data_are_not_native_statistics(change):
    book = workbook()
    if change == "missing":
        book.active["A3"] = None
    elif change == "formula":
        book.active["A3"] = '="MSD-289 GSD-143 HC-19=451 9 provisionals = 460"'
    elif change == "sheet":
        book.active.title = "Other election"
    else:
        book.active["A10"] = "VoterID"
    with pytest.raises(ValueError):
        parse(body(book))


@pytest.mark.parametrize("field", ["kind", "date", "county", "denominator", "literal", "ballots"])
def test_reviewed_display_alias_does_not_hide_measure_election_geography_or_frame_changes(field):
    row = reviewed_template()
    changed = copy.deepcopy(row)
    if field == "kind":
        changed["measure"]["kind"] = "ballots_cast"
    elif field == "date":
        changed["election"]["date"] = "2026-11-17"
    elif field == "county":
        changed["geography"]["name"] = "Other County"
    elif field == "denominator":
        changed["denominator"]["basis"] = "eligible_population"
    elif field == "literal":
        changed["view"]["participation_measure_literal"] = "Current people"
    else:
        changed["view"]["cast_ballot_count_qualified"] = True
    assert reviewed_measure_label(changed) is None
    assert observation_identity(changed) != observation_identity(row)
    with pytest.raises(ValueError):
        parse(body(workbook()), changed)


def test_current_display_alias_requires_its_query_and_input_pin():
    row, original = reviewed_template(), body(workbook(461))
    data = parse(original, row)
    entry = {"status": "reported", "source": {"url": PROFILE["url"], **pin(original)}, "data": data}
    entry["data"]["updates"][0]["native"]["query"]["source_pin"] = pin(b"other body")
    with pytest.raises(ValueError, match="source/query-bound"):
        granular.project(baseline(row), {"KS-workbook": entry})


def test_actual_default_planning_and_capture_preserve_last_good_query_on_failure_and_stop(tmp_path, monkeypatch):
    row, original = reviewed_template(), body(workbook(461))
    before = baseline(row)
    calls = []
    current = [original]
    def acquire(self, url):
        self.guard(url)
        calls.append(url)
        return current[0], {"origin": "fixture_transport", **pin(current[0])}
    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    stops = {"urls": [], "prefixes": [], "hosts": []}
    plan = native.source_plan(before)
    identity, source = next(iter(plan["KS"].items()))
    assert source["adapter"] == "reviewed_workbook_statistics"
    first = native.collect_sources(intake.Collector(tmp_path / "first", {}, stops, now), before)
    assert first[identity]["status"] == "reported"
    current[0] = b"changed native layout"
    second = native.collect_sources(
        intake.Collector(tmp_path / "second", first, stops, now), before)
    assert second[identity]["status"] == "retained_after_failure"
    for field in ("data", "source", "first_observed_at"):
        assert second[identity][field] == first[identity][field]
    assert granular.project(before, first)[0] == granular.project(before, second)[0]
    calls.clear()
    held = {"urls": [PROFILE["url"]], "prefixes": [], "hosts": []}
    third = native.collect_sources(intake.Collector(tmp_path / "third", second, held, now), before)
    assert third[identity]["error"] == "source_stopped"
    assert not calls and third[identity]["data"] == first[identity]["data"]
