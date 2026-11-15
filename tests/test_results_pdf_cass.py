"""Portable behavioral tests for the Cass County, Indiana PDF adapter."""

import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import results_pdf_cass as cass


def page(number, count=18, reference=41, count_pct="43.90%",
         reported=2, total=3, reported_pct="66.67%", clock="8:11 PM"):
    return "\n".join((
        "Cumulative Results Report",
        "OFFICIAL 2026 GENERAL",
        "Run Time",
        "Run Date",
        clock,
        "11/03/2026",
        "CASS COUNTY",
        "2026 General",
        "11/3/2026",
        f"Page {number}",
        "Unofficial Results",
        "Registered Voters",
        f"{count} of {reference} = {count_pct}",
        "Precincts Reporting",
        f"{reported} of {total} = {reported_pct}",
        f"CONTEST {number}",
        "Choice",
        "Party",
        "Absentee Voting",
        "Early Voting",
        "Election Day Voting",
        "Total",
        "Candidate",
        "0",
    ))


def query(pages=None):
    return cass.factual_query_from_pages(
        pages or [page(1), page(2)],
        {"bytes": 123, "sha256": "a" * 64},
    )


def template(clock="11/03/2026 7:59 PM"):
    return {
        "id": cass.TARGET_ID,
        "count": {"status": "reported", "value": 7, "literal": 7},
        "denominator": None,
        "election": {"year": 2026, "type": "general"},
        "geography": {
            "id": "IN|additional:IN:18017|",
            "state_code": "IN",
            "level": "county",
            "name": "Cass County",
        },
        "measure": copy.deepcopy(cass.MEASURE),
        "source": {"url": cass.URL, "fields": {"source_url": cass.URL}},
        "source_clock": {"literal": clock, "timezone": None},
        "view": {
            "source_url": cass.URL,
            "county": "Cass County",
            "county_id": "additional:IN:18017",
            "selected_source_kind": "native_turnout_numerator",
            "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False,
            "native_record": {"county": "Cass", "measure_literal": "Registered Voters"},
        },
    }


def test_changed_numeric_body_refreshes_without_old_count_or_hash_lookup(monkeypatch):
    parsed = query()
    monkeypatch.setattr(cass, "factual_query", lambda body, url=cass.URL: parsed)
    result = cass.statistics(b"changed-source-body", [template()])
    update = result["updates"][0]
    assert update["value"] == 18
    assert update["registered"] is None
    assert update["reported_units"] == 2
    assert update["total_units"] == 3
    assert update["rate_compatible"] is False
    assert update["native"]["native_display_reference"] == 41
    assert result["complete_native_query"]["source"]["sha256"] == "a" * 64


def test_true_zero_is_preserved_without_inventing_a_denominator(monkeypatch):
    parsed = query([page(1, count=0, count_pct="0.00%")])
    monkeypatch.setattr(cass, "factual_query", lambda body, url=cass.URL: parsed)
    update = cass.statistics(b"zero-source-body", [template()])["updates"][0]
    assert update["value"] == 0
    assert update["registered"] is None
    assert update["native"]["native_count"] == 0
    assert update["native"]["native_display_reference"] == 41


@pytest.mark.parametrize("mutation", [
    lambda text: text.replace("2026 General", "2026 Primary", 1),
    lambda text: text.replace("CASS COUNTY", "OTHER COUNTY", 1),
    lambda text: text.replace("Registered Voters", "Ballots Cast", 1),
    lambda text: text.replace("Absentee Voting", "Mail Voting", 1),
    lambda text: text.replace("Page 1", "Page 2", 1),
    lambda text: text.replace("18 of 41 = 43.90%", "18 of 41 = 43.91%", 1),
    lambda text: text.replace("2 of 3 = 66.67%", "2 of 3 = 66.66%", 1),
    lambda text: text.replace("18 of 41 = 43.90%", "UNKNOWN", 1),
])
def test_wrong_election_scope_columns_sequence_percent_or_unknown_is_rejected(mutation):
    with pytest.raises(ValueError):
        query([mutation(page(1))])


def test_pages_must_share_count_scope_status_and_clock():
    with pytest.raises(ValueError, match="one cumulative report edition"):
        query([page(1), page(2, count=19, count_pct="46.34%")])
    with pytest.raises(ValueError, match="one cumulative report edition"):
        query([page(1), page(2, clock="8:12 PM")])
    with pytest.raises(ValueError):
        query([page(1), page(2).replace("Unofficial Results", "Official Results")])


@pytest.mark.parametrize("mutation", ["target", "parent", "measure", "denominator", "source", "kind"])
def test_wrong_target_parent_measure_or_source_semantics_are_rejected(monkeypatch, mutation):
    parsed = query()
    monkeypatch.setattr(cass, "factual_query", lambda body, url=cass.URL: parsed)
    selected = template()
    if mutation == "target":
        selected["id"] = "other"
    elif mutation == "parent":
        selected["geography"]["level"] = "reporting_unit"
    elif mutation == "measure":
        selected["measure"]["literal"] = "Ballots Cast"
    elif mutation == "denominator":
        selected["denominator"] = {"value": 41, "qualified": True}
    elif mutation == "source":
        selected["source"]["url"] = "https://example.test/other.pdf"
        selected["source"]["fields"]["source_url"] = "https://example.test/other.pdf"
        selected["view"]["source_url"] = "https://example.test/other.pdf"
    else:
        selected["view"]["selected_source_kind"] = "cast_ballots"
    with pytest.raises(ValueError):
        cass.statistics(b"fixture", [selected])


def test_clock_rollback_and_multiple_templates_are_rejected(monkeypatch):
    parsed = query()
    monkeypatch.setattr(cass, "factual_query", lambda body, url=cass.URL: parsed)
    with pytest.raises(ValueError, match="clock regressed"):
        cass.statistics(b"fixture", [template("11/03/2026 8:12 PM")])
    with pytest.raises(ValueError, match="inventory"):
        cass.statistics(b"fixture", [template(), template()])


def test_runtime_module_import_does_not_require_pdf_or_ocr_packages():
    command = (
        "import os, pathlib, sys; "
        "root = pathlib.Path(os.environ['CASS_MODULE_ROOT']); "
        "sys.path.insert(0, str(root)); import scripts; "
        "scripts.__path__ = [str(root / 'scripts'), *list(scripts.__path__)]; "
        "sys.modules['pypdf']=None; sys.modules['fitz']=None; "
        "sys.modules['rapidocr_onnxruntime']=None; "
        "import scripts.results_pdf_cass"
    )
    environment = dict(os.environ, CASS_MODULE_ROOT=str(Path(__file__).parents[1]))
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
