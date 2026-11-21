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
