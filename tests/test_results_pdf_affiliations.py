import copy
import gzip
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import results_pdf_affiliations as affiliation
from scripts.participation_intake.contract import encoded


PROFILE = {
    **affiliation.PROFILES[affiliation.URL],
    "county_codes": ["01", "02"],
}


def page(number, code, name, cells, total, clock="10/31/2026 8:34 PM"):
    return "\n".join([
        PROFILE["title"] + " " + clock,
        "Election Date: 11/03/2026", f"County: {code} {name}",
        "Absentee", "Affiliation In-person",
        *(f"{name} {value}" for name, value in cells), str(total),
        f"ap2541 Page {number} of 3",
    ])


def pages():
    return [
        page(1, "01", "ONE", [("Republican", 4), ("Democrat", 2)], 6),
        page(2, "02", "TWO", [("Republican", 0), ("Democrat", 0)], 0),
        page(3, "99", "STATE", [("Republican", 4), ("Democrat", 2)], 6),
    ]


def templates():
    return [{
        "id": "observation-" + code,
        "geography": {"state_code": "OK", "level": "county", "name": name + " County"},
        "election": {"year": 2026, "type": "general"},
        "measure": copy.deepcopy(PROFILE["measure"]),
        "count": {"status": "reported", "value": value}, "denominator": None,
        "source": {"url": affiliation.URL},
        "view": {"source_url": affiliation.URL, "native_record": {
            "source_county_code": code, "source_county_literal": name,
            "report_clock_literal": "10/30/2026 8:34 PM",
        }},
    } for code, name, value in (("01", "ONE", 6), ("02", "TWO", 0))]


def collect(texts=None, records=None):
    texts = pages() if texts is None else texts
    pdf = SimpleNamespace(is_encrypted=False, pages=[
        SimpleNamespace(extract_text=lambda text=text, **kwargs: text) for text in texts
    ])
    with patch.dict(affiliation.PROFILES, {affiliation.URL: PROFILE}), patch(
            "pypdf.PdfReader", return_value=pdf):
        return affiliation.statistics(b"retained original", templates() if records is None else records,
                                      affiliation.URL)


def test_complete_counts_real_zero_and_missing_affiliations_are_distinct():
    rows, query, clock = affiliation.parse_pages(pages(), PROFILE)
    assert rows["02"]["categories"]["Republican"]["value"] == 0
    assert rows["01"]["categories"]["Libertarian"] is None
    assert query["separate_printed_parent"]["count"] == 6
    assert clock == "10/31/2026 8:34 PM"
    result = collect()
    assert [row["value"] for row in result["updates"]] == [6, 0]
    assert all(not row["rate_compatible"] for row in result["updates"])
    assert [row["id"] for row in result["updates"]] == ["observation-01", "observation-02"]


def test_later_changed_counts_refresh_without_a_frozen_count_or_clock():
    texts = pages()
    texts[0] = texts[0].replace("Republican 4", "Republican 7").replace("\n6\n", "\n9\n")
    texts[2] = texts[2].replace("Republican 4", "Republican 7").replace("\n6\n", "\n9\n")
    texts = [text.replace("10/31/2026 8:34 PM", "11/01/2026 9:15 PM") for text in texts]
    result = collect(texts)
    assert result["updates"][0]["value"] == 9
    assert result["updates"][0]["clock"] == "11/01/2026 9:15 PM"


@pytest.mark.parametrize("old,new", [
    ("Election Date: 11/03/2026", "Election Date: 05/05/2026"),
    ("Affiliation In-person", "Affiliation Mail"),
    ("County: 02 TWO", "County: 01 TWO"),
    ("County: 99 STATE", "County: 99 OTHER"),
    ("Republican 4", "Republican 1,00"),
    ("Republican 4", "Republican -4"),
    ("Republican 4", "Unknown 4"),
    ("Democrat 2", "Democrat"),
    ("Democrat 2", "Democrat 2\nDemocrat 0"),
    ("Page 1 of 3", "Page 1 of 4"),
])
def test_changed_layout_or_incomplete_count_cells_fail_closed(old, new):
    texts = [text.replace(old, new) for text in pages()]
    with pytest.raises(ValueError):
        collect(texts)


def test_parent_discrepancy_and_mixed_page_clocks_fail_closed():
    texts = pages()
    texts[-1] = page(3, "99", "STATE", [("Republican", 8)], 8)
    with pytest.raises(ValueError, match="statewide parent"):
        collect(texts)
    texts = pages()
    texts[-1] = texts[-1].replace("8:34 PM", "9:34 PM")
    with pytest.raises(ValueError, match="clocks"):
        collect(texts)


def test_rollback_identity_mode_and_missing_county_templates_are_rejected():
    records = templates()
    records[0]["view"]["native_record"]["report_clock_literal"] = "11/01/2026 8:34 PM"
    with pytest.raises(ValueError, match="regressed"):
        collect(records=records)
    for field, value in (("source_county_code", "03"), ("source_county_literal", "OTHER")):
        records = templates()
        records[0]["view"]["native_record"][field] = value
        with pytest.raises(ValueError, match="identity"):
            collect(records=records)
    records = templates()
    records[0]["measure"]["mode"] = "all_methods"
    with pytest.raises(ValueError, match="identity"):
        collect(records=records)
    with pytest.raises(ValueError, match="inventory"):
        collect(records=templates()[:1])


def test_common_source_plan_and_collector_keep_every_county_template():
    from scripts import results_native

    records = templates()
    baseline = {
        "index.json": encoded({"states": {"OK": {"file": "states/OK.json.gz"}}}),
        "states/OK.json.gz": gzip.compress(encoded({
            "records": records, "views": {"in_person_early": {
                "counties": [row["id"] for row in records],
            }},
        })),
    }
    with patch.dict(affiliation.PROFILES, {affiliation.URL: PROFILE}), patch.object(
            results_native, "affiliation_pdf_statistics",
            side_effect=lambda body, templates, url: collect(records=templates)):
        plan = results_native.source_plan(baseline)["OK"]
        source, = plan.values()
        assert source["adapter"] == "reviewed_county_affiliation_pdf"
        assert len(source["templates"]) == 2
        collector = SimpleNamespace(capture=lambda identity, url, parse: {
            "status": "reported", "data": parse(b"retained original"),
        })
        result, = results_native.collect_sources(collector, baseline).values()
    assert result["reviewed_record_count"] == 2
    assert [row["value"] for row in result["data"]["updates"]] == [6, 0]
