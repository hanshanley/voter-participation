import copy
import gzip
import json

import pytest

from scripts import results_granular as granular, results_intake as intake
from scripts import results_native as native, results_pdf_ocr as ocr
from scripts import results_pdf_platte as platte
from scripts.participation_intake.contract import encoded, pin
from test_results_granular import template
from test_results_native import baseline, pdf_reader


def record():
    row = template("MO", "Platte County", "county")
    row["id"] = platte.TARGET
    row["election"] = {
        "date": "2026-11-03", "id": "mo-2026-11-03-general",
        "qualification": "native", "type": "general", "year": 2026}
    row["geography"]["id"] = "native:MO:county:platte-county"
    row["geography"]["join"]["status"] = "unreviewed"
    row["measure"] = copy.deepcopy(platte.MEASURE)
    row["source"].update(
        id="mo-platte-official-20261113", url=platte.URL, input_sha256=platte.REVIEWED_SHA,
        selector={"physical_page": 20, "row": "Total"},
        fields={"selected_physical_table": [{"unit": unit} for unit in platte.UNITS],
                "visual_review_image": {
                    "sha256": "027bc593028516045697a0273f979a9f08dde359a05e0fdc74a808d9b06a5aa0"}})
    row["source_clock"] = {"literal": "11/9/2026 2:38:15 PM", "timezone": "CST"}
    row["view"].update(source_url=platte.URL, maps_approved=False)
    return row


def cells(values, starts=None):
    starts = starts if starts is not None else [index * 100 for index in range(len(values))]
    return [{"text": value, "left": left, "right": left + 40, "confidence": .999}
            for value, left in zip(values, starts)]


def views(date="11/10/2026", zero=False, revised=False):
    date, time = "Date:" + date, "Time:2:38:15PMCST"
    headers = [
        cells(["Statement of Votes Cast"]), cells(["General Election", date]),
        cells(["Platte County, Missouri", time]), cells(["November 3, 2026"]),
        cells(["11032026_1", "Page20/26"]), cells(["Official Results"]),
        cells(["Turnout", "PropI Transportation"]),
        cells(["Reg.", "Ballots", "%", "Reg.", "Total"], [400, 500, 600, 700, 800]),
        cells(["Voters", "Cast", "TurnoutVoters"], [400, 500, 600]),
        cells(["Jurisdiction Wide"]),
    ]
    counts = [0, 0, 0, 0] if zero else [1, 2, 14, 46 if revised else 45]
    stocks = [10, 10, None, 100]
    for label, count, registered in zip(platte.UNITS, counts, stocks):
        if registered is None:
            row = cells([label, str(count), "0", "99999"], [0, 524, 724, 824])
        else:
            fraction = f"{count * 100 / registered:.2f}%"
            row = cells([label, str(registered), str(count), fraction, "99999", "88888"],
                        [0, 424, 524, 624, 724, 824])
        headers.append(row)
    receipt = {"dpi": 180, "page": 21, "rotation_degrees": 0,
               "text_angle_classifier_enabled": False}
    return (
        {"role_cells": headers, "receipt": receipt},
        {"role_cells": [cells([date]), cells([time]), cells(["Page20/26"])],
         "receipt": {**receipt, "normalized_region": list(platte.CLOCK_REGION)}},
    )


def parse(monkeypatch, pair=None, second=None, row=None, prior=None):
    pdf_reader(monkeypatch)
    pair = pair or views()
    second = copy.deepcopy(second or pair)
    for view in second:
        view["receipt"]["dpi"] = 240
    def selected(body, **options):
        assert options["page_index"] == 20
        assert options["strict_role_alignment"] is True
        assert options["text_angle_classifier"] is False
        return [pair[1], second[1]] if options.get("region") else [pair[0], second[0]]
    monkeypatch.setattr(ocr, "page_views", selected)
    return platte.statistics(b"\f" * 26, [row or record()], prior=prior)


@pytest.mark.parametrize("kind", ["current", "zero", "revised"])
def test_selected_page_preserves_four_turnout_rows_not_adjacent_votes_or_a_child_sum(monkeypatch, kind):
    result = parse(monkeypatch, views(zero=kind == "zero", revised=kind == "revised"))
    query = result["complete_native_query"]
    update, = result["updates"]
    assert update["id"] == platte.TARGET
    assert update["value"] == {"current": 45, "zero": 0, "revised": 46}[kind]
    assert update["registered"] == 100 and not update["rate_compatible"]
    assert len(query["statistics"]) == 4
    assert query["statistics"][2]["registered"] is None
    assert query["statistics"][2]["native_fraction_literal"] is None
    assert query["parent"]["pdf_report_timezone_literal"] == "CST"
    assert query["parent"]["page"] == 21 and query["parent"]["native_printed_page"] == 20
    assert query["selected_rows_are_not_a_complete_county_partition"]
    assert query["adjacent_contest_votes_not_selected"]
    assert query["ocr"]["same_engine_resolution_check_not_independent_validation"]


@pytest.mark.parametrize("kind", [
    "column", "missing", "unknown", "negative", "duplicate", "fraction", "low_count",
    "low_clock", "election", "county", "folio", "page", "angle", "crop_disagreement",
])
def test_changed_roles_pages_scope_and_uncertain_counts_fail_closed(monkeypatch, kind):
    pair = views()
    rows = pair[0]["role_cells"]
    if kind == "column":
        rows[-1][2]["left"], rows[-1][2]["right"] = 824, 864
    elif kind == "missing":
        rows[-1].pop(2)
    elif kind in ("unknown", "negative"):
        rows[-1][2]["text"] = "?" if kind == "unknown" else "-1"
    elif kind == "duplicate":
        rows[-1].append(copy.deepcopy(rows[-1][2]))
    elif kind == "fraction":
        rows[-1][3]["text"] = "44.00%"
    elif kind == "low_count":
        rows[-1][2]["confidence"] = .979
    elif kind == "low_clock":
        pair[1]["role_cells"][1][0]["confidence"] = .979
    elif kind == "election":
        rows[3][0]["text"] = "November 3, 2024"
    elif kind == "county":
        rows[2][0]["text"] = "Other County, Missouri"
    elif kind == "folio":
        rows[4][1]["text"] = "Page19/26"
    elif kind == "page":
        pair[0]["receipt"]["page"] = 20
    elif kind == "angle":
        pair[0]["receipt"]["text_angle_classifier_enabled"] = True
    else:
        pair[1]["role_cells"][0][0]["text"] = "Date:11/11/2026"
    with pytest.raises(ValueError):
        parse(monkeypatch, pair)


def test_scales_and_last_good_clock_must_agree_and_remain_query_bound(monkeypatch):
    with pytest.raises(ValueError, match="disagreement"):
        parse(monkeypatch, second=views(revised=True))
    result = parse(monkeypatch, views(date="11/11/2026"))
    prior = {"source": result["complete_native_query"]["source"], "data": result}
    with pytest.raises(ValueError, match="regressed"):
        parse(monkeypatch, prior=prior)
    prior["data"]["updates"][0]["value"] = 99999
    with pytest.raises(ValueError, match="query-bound"):
        parse(monkeypatch, prior=prior)


@pytest.mark.parametrize("field", ["selector", "source", "measure", "denominator"])
def test_profile_requires_the_reviewed_source_frame(monkeypatch, field):
    row = record()
    if field == "selector":
        row["source"]["selector"]["physical_page"] = 21
    elif field == "source":
        row["source"]["input_sha256"] = "0" * 64
    elif field == "measure":
        row["measure"]["literal"] = "Candidate Votes"
    else:
        row["denominator"] = {"qualified": True, "value": 100}
    with pytest.raises(ValueError, match="qualification changed"):
        parse(monkeypatch, row=row)


def test_default_source_plan_and_projection_preserve_identity_and_held_rates(monkeypatch):
    before = baseline(("MO", "TX"))
    row = record()
    before["states/MO.json.gz"] = gzip.compress(encoded({
        "records": [row], "views": {"official": {"counties": [row["id"]]}}}), mtime=0)
    index = json.loads(before["index.json"])
    index["states"]["MO"].update(pin(before["states/MO.json.gz"]))
    before["index.json"] = encoded(index)
    source, = native.source_plan(before)["MO"].values()
    assert source["adapter"] == "reviewed_platte_statistical_grid"
    result = parse(monkeypatch)
    after, changes = granular.project(before, {"MO-platte": {
        "status": "reported", "source": result["complete_native_query"]["source"], "data": result}})
    refreshed, = granular.selected_records(after, "MO")
    assert refreshed["count"]["value"] == 45
    assert refreshed["geography"] == row["geography"] and refreshed["id"] == row["id"]
    assert refreshed["denominator"] is None and refreshed["view"]["reported_pct"] is None
    assert refreshed["view"]["native_printed_pct"] == "45.00%"
    assert refreshed["source_clock"]["timezone"] == "CST"
    assert result["complete_native_query"]["reviewed_selector_preserved_verbatim"] == row[
        "source"]["selector"]
    assert refreshed["source"]["selector"]["native_refresh"] == result["updates"][0]["native"]
    assert after["states/TX.json.gz"] == before["states/TX.json.gz"] and len(changes) == 1


def test_page_ocr_renders_selected_page_and_region_without_changing_first_page_defaults(monkeypatch):
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("rapidocr_onnxruntime")
    document = fitz.open()
    document.new_page(width=100, height=100)
    document.new_page(width=200, height=100)
    body = document.tobytes()
    expected = [pin(document[1].get_pixmap(dpi=dpi, alpha=False).tobytes("png"))
                for dpi in (180, 240)]
    document.close()
    def engine(image, **options):
        return [[[[0, 0], [10, 0], [10, 10], [0, 10]], "0", .999]], None
    monkeypatch.setattr(ocr._local, "engine", engine, raising=False)
    monkeypatch.setattr(ocr._local, "models", {"fixture": pin(b"fixture")}, raising=False)
    selected = ocr.page_views(body, page_index=1)
    assert [view["receipt"]["image"] for view in selected] == expected
    assert all(view["receipt"]["page"] == 2 for view in selected)
    assert ocr.first_page_views(body) == ocr.page_views(body)
    cropped = ocr.page_views(body, page_index=1, region=(.5, 0, 1, .5))
    assert all(view["receipt"]["normalized_region"] == [.5, 0, 1, .5] for view in cropped)
    assert cropped[0]["receipt"]["image"] != selected[0]["receipt"]["image"]
    for options in ({"page_index": -1}, {"page_index": True}, {"region": (-1, 0, 1, 1)}):
        with pytest.raises(ValueError):
            ocr.page_views(body, **options)
