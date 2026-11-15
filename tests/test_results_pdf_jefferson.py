"""Portable behavior tests for the Jefferson County, Kentucky PDF adapter."""

import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import results_pdf_jefferson as jefferson


FIXTURE = Path(__file__).with_name("fixtures") / "results_pdf_jefferson" / "complete-pages.json.gz"


def fixture():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def profile(monkeypatch, data):
    value = copy.deepcopy(jefferson.PROFILES[jefferson.URL])
    value["expected_pages"] = len(data["pages"])
    value["expected_units"] = len(data["units"])
    monkeypatch.setitem(jefferson.PROFILES, jefferson.URL, value)
    return value


def template(unit, clock="11/06/2026     9:52 AM"):
    return {
        "id": "accepted-" + unit,
        "count": {"status": "reported", "value": 1, "literal": 1},
        "denominator": None,
        "election": {"date": "2026-11-03", "year": 2026, "type": "general"},
        "geography": {
            "state_code": "KY",
            "level": "reporting_unit",
            "name": unit,
        },
        "measure": copy.deepcopy(jefferson.MEASURE),
        "source": {
            "url": jefferson.URL,
            "selector": {
                "native_column": "TOTAL",
                "native_measure": "Ballots Cast - Total",
                "native_unit": unit,
            },
        },
        "source_clock": {
            "literal": clock,
            "timezone": None,
            "qualification": "native_printed_clock_timezone_not_supplied",
        },
        "view": {
            "source_url": jefferson.URL,
            "unit": unit,
            "native_record": {"profile": {"native_unit": unit}},
        },
    }


def query(monkeypatch, data):
    selected = profile(monkeypatch, data)
    return jefferson.factual_query_from_pages(
        data["pages"], data["source_pin"], selected,
    )


def test_complete_fixture_preserves_suffix_modes_zeros_and_page_groups(monkeypatch):
    data = fixture()
    result = query(monkeypatch, data)
    assert [row["native_unit"] for row in result["units"]] == data["units"]
    assert result["page_count"] == 4
    assert [row["source_pages"] for row in result["units"]] == [2, 2]
    suffix = result["units"][1]
    assert suffix["native_unit"] == "V120 MID"
    assert suffix["measures"]["Ballots Cast - Total"]["TOTAL"]["value"] == 0
    assert suffix["measures"]["Ballots Cast - Total"]["TOTAL"]["literal"] == "0"
    assert suffix["measures"]["Ballots Cast - Blank"]["TOTAL"]["value"] == 0
    assert result["candidate_totals_not_selected"] is True
    assert result["county_parent_present_in_this_product"] is False


def test_coherent_changed_native_vector_refreshes_without_old_count_guard(monkeypatch):
    data = fixture()
    data["pages"][0] = data["pages"][0].replace(
        "Ballots Cast - Total 10 7 1 0 2 0",
        "Ballots Cast - Total 12 8 1 0 3 0",
    )
    parsed = query(monkeypatch, data)
    monkeypatch.setattr(jefferson, "factual_query", lambda body, url=jefferson.URL: parsed)
    result = jefferson.statistics(
        b"portable-fixture",
        [template(unit) for unit in data["units"]],
    )
    assert [update["value"] for update in result["updates"]] == [12, 0]
    assert all(update["registered"] is None and not update["rate_compatible"]
               for update in result["updates"])
    assert result["county_parent_updated"] is False


@pytest.mark.parametrize("mutation", ["election", "status", "page", "clock"])
def test_wrong_scope_or_broken_source_continuity_is_rejected(monkeypatch, mutation):
    data = fixture()
    if mutation == "election":
        data["pages"][0] = data["pages"][0].replace(
            "2026 General Election", "2026 Primary Election",
        )
    elif mutation == "status":
        data["pages"][0] = data["pages"][0].replace(
            "UNOFFICIAL RESULTS", "OFFICIAL RESULTS",
        )
    elif mutation == "page":
        data["pages"][1] = data["pages"][1].replace("2 of 4", "3 of 4")
    else:
        data["pages"][1] = data["pages"][1].replace("9:52 AM", "9:53 AM")
    with pytest.raises(ValueError):
        query(monkeypatch, data)


def test_changed_duplicate_statistical_vector_is_rejected(monkeypatch):
    data = fixture()
    block = (
        "Statistics TOTAL Election\nDay\nMail Walk-in\nExcuse\nWalk-in\nEarly\n"
        "Provision\nal\nBallots Cast - Total 11 8 1 0 2 0\n"
        "Ballots Cast - Blank 0 0 0 0 0 0\n"
    )
    data["pages"][1] = data["pages"][1].replace("CONTEST B\n", block + "CONTEST B\n")
    with pytest.raises(ValueError, match="duplicate statistical vector"):
        query(monkeypatch, data)


@pytest.mark.parametrize("mutation", ["identity", "measure", "denominator", "source"])
def test_template_semantic_or_literal_identity_changes_are_rejected(monkeypatch, mutation):
    data = fixture()
    parsed = query(monkeypatch, data)
    templates = [template(unit) for unit in data["units"]]
    if mutation == "identity":
        templates[1]["view"]["unit"] = "V120"
    elif mutation == "measure":
        templates[0]["measure"]["literal"] = "Total Votes Cast"
    elif mutation == "denominator":
        templates[0]["denominator"] = {"value": 10, "qualified": True}
    else:
        templates[0]["source"]["url"] = "https://example.test/unreviewed.pdf"
        templates[0]["view"]["source_url"] = "https://example.test/unreviewed.pdf"
    monkeypatch.setattr(jefferson, "factual_query", lambda body, url=jefferson.URL: parsed)
    with pytest.raises(ValueError):
        jefferson.statistics(b"portable-fixture", templates)


def test_missing_or_extra_source_unit_is_not_joined(monkeypatch):
    data = fixture()
    parsed = query(monkeypatch, data)
    monkeypatch.setattr(jefferson, "factual_query", lambda body, url=jefferson.URL: parsed)
    with pytest.raises(ValueError, match="template inventory"):
        jefferson.statistics(b"portable-fixture", [template(data["units"][0])])


def test_printed_clock_rollback_is_rejected(monkeypatch):
    data = fixture()
    parsed = query(monkeypatch, data)
    monkeypatch.setattr(jefferson, "factual_query", lambda body, url=jefferson.URL: parsed)
    templates = [template(unit, "11/07/2026 9:52 AM") for unit in data["units"]]
    with pytest.raises(ValueError, match="clock regressed"):
        jefferson.statistics(b"portable-fixture", templates)


def test_runtime_module_import_does_not_require_pdf_or_ocr_packages():
    command = (
        "import os, pathlib, scripts, sys; "
        "root = pathlib.Path(os.environ['JEFFERSON_MODULE_ROOT']); "
        "scripts.__path__ = [str(root / 'scripts'), *scripts.__path__]; "
        "sys.modules['pypdf']=None; sys.modules['fitz']=None; "
        "sys.modules['rapidocr_onnxruntime']=None; "
        "import scripts.results_pdf_jefferson"
    )
    environment = dict(os.environ, JEFFERSON_MODULE_ROOT=str(Path(__file__).parents[1]))
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
