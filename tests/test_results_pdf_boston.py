"""Portable behavioral tests for the bounded Boston statement adapter."""

import copy
import hashlib
from unittest.mock import patch

import pytest

from scripts import results_pdf_boston as boston
from scripts import native_pdf
from scripts.participation_intake.contract import encoded, pin


CONTEXT_ONE = "SENATOR IN CONGRESS (Vote for 1)"
CONTEXT_TWO = "QUESTION 9 (Vote for 1)"


def add_horizontal(page, text, x, y, width=4):
    for character in text:
        identity = [page["page"], 0, 0, len(page["glyphs"])]
        page["glyphs"].append({
            "id": identity, "text": character,
            "reading_bbox": [x, y, x + width, y + 8],
            "font_size": 8,
        })
        x += width


def add_vertical(page, text, x=170, y=135):
    for character in text:
        identity = [page["page"], 1, 0, len(page["glyphs"])]
        page["glyphs"].append({
            "id": identity, "text": character,
            "reading_bbox": [x, y, x + 7, y + 3],
            "font_size": 8,
        })
        y -= 4


def page(number):
    value = {
        "page": number, "reading_rect": [0, 0, 792, 612], "glyphs": [],
        "native_text_absent_requires_separate_review": False,
    }
    add_horizontal(value, f"Page: {number} of 3", 20, 20)
    add_horizontal(value, "11/4/2026 11:39:02 AM", 650, 20)
    return value


def add_row(page_value, y, values, columns):
    for value, (left, right) in zip(values, columns):
        add_horizontal(page_value, value, left + 2, y)


def synthetic_facts():
    summary, first, second = page(1), page(2), page(3)
    add_horizontal(summary, "Unofficial Election Results - City of Boston", 250, 45)
    add_horizontal(summary, "State Election - November 3, 2026", 280, 60)
    summary_columns = ((15, 130), (130, 190), (190, 245), (245, 300))
    for y, values in (
        (110, ("BOSTON", "", "", "")),
        (130, ("WARD 1, PRECINCT 1", "0", "7", "N/A")),
        (150, ("BOSTON - Total", "0", "7", "N/A")),
        (170, ("Cumulative", "", "", "")),
        (190, ("Cumulative", "0", "0", "N/A")),
        (210, ("Cumulative - Total", "0", "0", "N/A")),
        (230, ("BOSTON - Total", "0", "7", "N/A")),
    ):
        add_row(summary, y, values, summary_columns)
    context_columns = ((15, 130), (130, 195), (195, 255), (255, 320))
    for page_value, heading, count in (
            (first, CONTEXT_ONE, 5), (second, CONTEXT_TWO, 6)):
        add_horizontal(page_value, heading, 20, 45)
        add_vertical(page_value, "Times Cast")
        for y, values in (
            (150, ("BOSTON", "", "", "")),
            (170, ("WARD 1, PRECINCT 1", str(count), "0", "1")),
            (190, ("BOSTON - Total", str(count), "0", "1")),
            (210, ("Cumulative", "", "", "")),
            (230, ("Cumulative", "0", "0", "0")),
            (250, ("Cumulative - Total", "0", "0", "0")),
            (270, ("BOSTON - Total", str(count), "0", "1")),
        ):
            add_row(page_value, y, values, context_columns)
    return {"pages": [summary, first, second]}


def configure(monkeypatch):
    digest = hashlib.sha256(b"1:1").hexdigest()
    contexts = {
        CONTEXT_ONE: (2, 1, digest),
        CONTEXT_TWO: (3, 1, digest),
    }
    pages = hashlib.sha256(b"2,3").hexdigest()
    monkeypatch.setattr(boston, "PAGE_COUNT", 3)
    monkeypatch.setattr(boston, "SUMMARY_PAGE_COUNT", 1)
    monkeypatch.setattr(boston, "TEMPLATE_COUNT", 2)
    monkeypatch.setattr(boston, "UNIT_COUNT", 1)
    monkeypatch.setattr(boston, "CONTEXTS", contexts)
    monkeypatch.setattr(boston, "STATISTICS_PAGE_DIGEST", pages)


def templates():
    common = {
        "election": {"date": "2026-11-03", "year": 2026, "type": "general"},
        "count": {"status": "reported", "value": 1},
        "denominator": None,
        "source": {"url": boston.URL},
        "source_clock": {"literal": "11/4/2026 11:39:02 AM"},
    }
    parent = {
        **copy.deepcopy(common), "id": "parent",
        "geography": {"state_code": "MA", "level": "municipality", "name": "Boston"},
        "measure": copy.deepcopy(boston.SUMMARY_MEASURE),
        "view": {"source_url": boston.URL, "native_record": {
            "selected_context": CONTEXT_ONE,
            "native_count_field": "Ballots Cast / Times Cast",
        }},
    }
    unit = {
        **copy.deepcopy(common), "id": "unit",
        "geography": {"state_code": "MA", "level": "reporting_unit",
                      "name": "Ward 1, Precinct 1"},
        "measure": copy.deepcopy(boston.UNIT_MEASURE),
        "view": {"source_url": boston.URL, "native_record": {
            "ward": "1", "precinct": "1", "native_context": CONTEXT_ONE,
        }},
    }
    return [parent, unit]


def parse(monkeypatch, facts):
    configure(monkeypatch)
    with patch.object(native_pdf, "read", return_value=facts):
        return boston.factual_query(b"portable-fixture")


def test_portable_fixture_preserves_summary_contexts_and_selected_measure(monkeypatch):
    facts = synthetic_facts()
    query = parse(monkeypatch, facts)
    assert query["summary"]["derived_voters_cast_sum"] == 7
    assert [item["derived_times_cast_sum"] for item in query["contexts"]] == [5, 6]
    monkeypatch.setattr(boston, "factual_query", lambda body: query)
    result = boston.statistics(b"portable-fixture", templates())
    assert [update["value"] for update in result["updates"]] == [5, 5]
    assert all(update["registered"] is None and not update["rate_compatible"]
               for update in result["updates"])
    assert result["updates"][0]["native"]["query"]["native_summary_voters_cast"] == 7
    assert result["updates"][0]["native"]["native_reporting_complete_qualified"] is False
    assert pin(encoded(query)) == {
        "bytes": 21287,
        "sha256": "4c6f0743b98782668368fc7e945bfeab02ac0c15e9ae8713626460cba22e4918",
    }


def replace_summary_count(facts, y, old, new):
    candidates = native_pdf.select(facts["pages"][0], [190, y - 2, 245, y + 10])
    glyph, = [item for item in candidates if item["text"] == old]
    glyph["text"] = new


def test_coherent_summary_refresh_is_accepted_without_replacing_selected_times_cast(monkeypatch):
    facts = synthetic_facts()
    for y in (130, 150, 230):
        replace_summary_count(facts, y, "7", "8")
    query = parse(monkeypatch, facts)
    assert query["summary"]["derived_voters_cast_sum"] == 8
    assert [item["derived_times_cast_sum"] for item in query["contexts"]] == [5, 6]
    monkeypatch.setattr(boston, "factual_query", lambda body: query)
    result = boston.statistics(b"portable-fixture", templates())
    parent, unit = result["updates"]
    assert parent["value"] == unit["value"] == 5
    assert parent["native"]["query"]["native_summary_voters_cast"] == 8
    assert parent["native"]["query"]["count"] == 5


@pytest.mark.parametrize("changed_rows", [(130,), (150, 230), (150,)])
def test_mismatched_summary_units_or_parent_copies_are_rejected(monkeypatch, changed_rows):
    facts = synthetic_facts()
    for y in changed_rows:
        replace_summary_count(facts, y, "7", "8")
    configure(monkeypatch)
    with patch.object(native_pdf, "read", return_value=facts):
        with pytest.raises(ValueError, match="summary controls"):
            boston.factual_query(b"portable-fixture")


@pytest.mark.parametrize("mutation", ["title", "clock", "header", "count"])
def test_portable_physical_mutations_are_rejected(monkeypatch, mutation):
    facts = synthetic_facts()
    configure(monkeypatch)
    if mutation == "title":
        candidates = native_pdf.select(facts["pages"][0], [200, 35, 600, 70])
        glyph = next(item for item in candidates if item["text"] == "U")
    elif mutation == "clock":
        candidates = native_pdf.select(facts["pages"][1], [650, 15, 780, 35])
        glyph = next(item for item in candidates if item["text"] == "1")
    elif mutation == "header":
        candidates = native_pdf.select(facts["pages"][1], [165, 55, 182, 145])
        glyph = next(item for item in candidates if item["text"] == "T")
    else:
        candidates = native_pdf.select(facts["pages"][1], [130, 165, 195, 183])
        glyph = next(item for item in candidates if item["text"] == "5")
    glyph["text"] = "X"
    with patch.object(native_pdf, "read", return_value=facts):
        with pytest.raises(ValueError):
            boston.factual_query(b"portable-fixture")


@pytest.mark.parametrize("mutation", ["source", "measure", "context", "denominator"])
def test_portable_template_mutations_are_rejected(monkeypatch, mutation):
    query = parse(monkeypatch, synthetic_facts())
    rows = templates()
    target = rows[1]
    if mutation == "source":
        target["view"]["source_url"] = "https://example.test/unreviewed.pdf"
    elif mutation == "measure":
        target["measure"]["literal"] = "Candidate votes"
    elif mutation == "context":
        target["view"]["native_record"]["native_context"] = CONTEXT_TWO
    else:
        target["denominator"] = {"value": 1, "qualified": True}
    monkeypatch.setattr(boston, "factual_query", lambda body: query)
    with pytest.raises(ValueError):
        boston.statistics(b"portable-fixture", rows)
