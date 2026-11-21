import hashlib

import pytest

from scripts import connecticut_turnout_history as ct


def test_archive_refuses_ambiguous_or_foreign_targets():
    path = "/-/media/sots/electionservices/elecdaystats_pdfs/regturnoutabsentee2006pdf.pdf"
    local = f'<a href="{path}">PDF</a>'
    assert ct.discover(local.encode(), 2006) == f"https://portal.ct.gov{path}"
    with pytest.raises(ValueError, match="ambiguous"):
        ct.discover((local + f'<a href="{path}?rev={"a"*32}&amp;hash={"b"*32}">PDF</a>').encode(), 2006)
    with pytest.raises(ct.IntakeError, match="not linked"):
        ct.discover(f'<a href="https://example.test{path}">PDF</a>'.encode(), 2006)


def test_preserves_bad_cell_and_unreconciled_state_without_fabricating_rates(monkeypatch):
    monkeypatch.setattr(ct, "ROSTER", hashlib.sha256(b"Southbury").hexdigest())
    feed = "CT-1998-general-town-turnout-archive"
    report = "https://portal.ct.gov/-/media/sots/electionservices/elecdaystats_pdfs/regturnoutabsentee1998pdf.pdf"
    entry = {
        "status": "reported", "source": {"url": ct.INDEX},
        "data": {"report": {"url": report, "bytes": 1, "sha256": "a" * 64}, "complete_native_query": [
            "Southbury 12,130 7,l90 59.27% 485 2 483", "Totals 12,130 7,190 59.27% 485 2 483",
        ]},
    }
    town, state = list(ct.exports({feed: entry}))
    assert town["checked_as_voted"] is None and town["rate_hold_reason"] == "malformed_count"
    assert state["checked_as_voted"] == 7190 and state["rate_hold_reason"] == "town_counts_do_not_reconcile"
    with pytest.raises(ValueError, match="roster changed"):
        ct.qualified(["Mystery 10 5 50.00% 1 0 1", "Totals 10 5 50.00% 1 0 1"], 1998)


def test_statement_keeps_split_town_components_and_literal_name(monkeypatch):
    monkeypatch.setattr(ct, "STATEMENT_SPLIT", {"Shelton"})
    monkeypatch.setattr(ct, "ROSTER", hashlib.sha256(b"New Milford\nShelton").hexdigest())
    lines = ["New Millford 50 25 50.00% 2 0 2", "Shelton (3rd CD) 30 18 60.00% 3 0 3",
             "Shelton (4th CD) 20 9 45.00% 1 0 1", "Statewide 100 52 52.00% 6 0 6"]
    rows, deltas = ct.statement_rows(lines, 2014)
    assert deltas == [0, 0]
    assert [(r[0], r[1]) for r in rows] == [
        ("New Milford", False), ("Shelton", True), ("Shelton", True), ("Statewide Totals", False)]
    assert rows[0][-1] == lines[0]
    with pytest.raises(ValueError, match="roster changed"):
        ct.statement_rows(lines[:2] + lines[-1:], 2014)


def test_statement_does_not_promote_state_with_omitted_towns(monkeypatch):
    monkeypatch.setattr(ct, "ROSTER", hashlib.sha256(b"Andover\nNew Canaan\nNorth Branford").hexdigest())
    report = "https://portal.ct.gov/-/media/sots/electionservices/statementofvote_pdfs/2020-sov.pdf"
    entry = {
        "status": "reported", "source": {"url": ct.STATEMENT_INDEX},
        "data": {"report": {"url": report, "bytes": 1, "sha256": "a" * 64}, "complete_native_query": [
            "Andover 20 12 60.00% 2 0 2 1 0 1", "Statewide Total 20 12 60.00% 2 0 2 1 0 1",
        ]},
    }
    town, state = list(ct.exports({"CT-2020-general-town-turnout-archive": entry}))
    assert town["checked_as_voted_fraction"] == "0.60000000" and town["edr_voted"] == 1
    assert state["checked_as_voted"] == 12 and state["town_minus_state_checked_as_voted"] == 0
    assert state["checked_as_voted_fraction"] is None and state["rate_hold_reason"] == "incomplete_town_inventory"
    entry["data"]["complete_native_query"][1:] = [
        "New Canaan 20 12 60.00% 2 0 2 1 0 1", "North Branford 20 12 60.00% 2 0 2 1 0 1",
        "Statewide Total 60 36 60.00% 6 0 6 3 0 3",
    ]
    assert list(ct.exports({"CT-2020-general-town-turnout-archive": entry}))[-1]["checked_as_voted_fraction"] == "0.60000000"


def test_2016_retains_signed_absentee_entry_and_derives_only_the_checklist_fraction(monkeypatch):
    monkeypatch.setattr(ct, "ROSTER", hashlib.sha256(b"Kent").hexdigest())
    report = "https://portal.ct.gov/-/media/sots/releases/2016/turnout11082016novemberpresidentialelectionpdf.pdf"
    entry = {
        "status": "reported", "source": {"url": ct.PRESS_INDEX},
        "data": {"report": {"url": report, "bytes": 1, "sha256": "a" * 64}, "complete_native_query": [
            "Kent 20 12 60.00% 0 2 -2 1 0 1", "Statewide 20 12 2 2 0 1 0 1",
        ]},
    }
    town, state = list(ct.exports({"CT-2016-general-town-turnout-archive": entry}))
    assert town["absentee_voted"] == -2 and town["checked_as_voted_fraction"] == "0.60000000"
    assert state["source_reported_percent"] is None and state["checked_as_voted_fraction"] == "0.60000000"
    entry["data"]["complete_native_query"][0] = "Kent 20 12 60.00% 0 3 -3 1 0 1"
    with pytest.raises(ValueError, match="negative ballot-mode cell"):
        list(ct.exports({"CT-2016-general-town-turnout-archive": entry}))
