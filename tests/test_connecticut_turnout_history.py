import hashlib
from datetime import datetime, timezone

import pytest

from scripts import connecticut_turnout_history as ct, results_intake


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


def test_2018_scan_accepts_matched_counts_without_guessing_a_mode_cell(monkeypatch):
    monkeypatch.setitem(ct.STATEMENTS, 2018, (*ct.STATEMENTS[2018][:3], 1))
    monkeypatch.setattr(ct, "ROSTER", hashlib.sha256(b"Andover\nEast Granby\nTorrington").hexdigest())
    header = ["Election: 11/06/2018 - November 2018 State Election",
              "Election Day Registration, Turnout and Absentee Ballot Statistics",
              "Checklist Percentage EDR Received EDR Rejected EDR Voted Town"]
    pages = [[{"receipt": {"page": 171, "dpi": dpi, "rotation_degrees": 90}, "header": header,
               "rows": [[name, "20", "12", "60.00%", "2", rejected, "2", "1", "0", "1"]
                        for name in ("Andover", "StatewideTotal")]}
              for dpi, rejected in ((180, "0"), (240, "o"))]]
    rows, deltas = ct.scanned_statement_rows(pages)
    assert deltas == [0, 0] and rows[0][2] == [20, 12, 2, None, 2, 1, 0, 1]
    pages[0][1]["rows"][0][2] = "13"
    with pytest.raises(ValueError, match="counts or printed rate disagree"):
        ct.scanned_statement_rows(pages)


def test_2018_scan_does_not_repeat_an_unchanged_rejection(tmp_path, monkeypatch):
    feed = "CT-2018-general-town-turnout-archive"
    url = "https://portal.ct.gov/-/media/sots/electionservices/statementofvote_pdfs/2018-sov.pdf"
    index = f'<a href="{url}">2018 PDF</a>'.encode()
    calls = []

    def parse(body, year):
        assert year == 2018
        calls.append(body)
        if body == b"bad edition":
            ct.scan.fail("Town counts disagree")
        if body == b"transient":
            raise RuntimeError("OCR worker failed")
        return {"complete_native_query": [body.decode()]}

    monkeypatch.setattr(ct, "parse", parse)
    monkeypatch.setattr(ct.scan, "scan_policy", lambda *args: "v1")
    prior = {}

    def refresh(body):
        collector = results_intake.Collector(tmp_path, prior, {"urls": [], "prefixes": [], "hosts": []},
                                             datetime(2026, 11, 21, tzinfo=timezone.utc))
        monkeypatch.setattr(collector, "acquire", lambda target: (
            index if target == ct.STATEMENT_INDEX else body, {"origin": "test"}))
        prior[feed] = ct.collect(collector, feed)
        return prior[feed]

    accepted = refresh(b"original")
    assert refresh(b"original") == accepted
    held = refresh(b"bad edition")
    assert held["status"] == "retained_after_failure"
    assert held["error"] == "scan_reconciliation_failed" and held["error_detail"] == "Town counts disagree"
    assert held["data"] == accepted["data"] and refresh(b"bad edition") == held
    assert calls == [b"original", b"bad edition"]

    monkeypatch.setattr(ct.scan, "scan_policy", lambda *args: "v2")
    assert refresh(b"bad edition")["error"] == "scan_reconciliation_failed"
    assert calls.count(b"bad edition") == 2
    assert refresh(b"transient")["status"] == refresh(b"transient")["status"] == "retained_after_failure"
    assert calls.count(b"transient") == 2
    restored = refresh(b"revised")
    assert restored["status"] == "reported" and "rejected_scan" not in restored
    assert restored["data"]["complete_native_query"] == ["revised"]


def test_2018_checkpoint_repairs_only_exact_source_edition(tmp_path, monkeypatch):
    feed = "CT-2018-general-town-turnout-archive"
    url = "https://portal.ct.gov/-/media/sots/electionservices/statementofvote_pdfs/2018-sov.pdf"
    checksum = "f3c4f52f92c14b3403778a2b6cd5a1541c47def83a248da151a7dd53deea7de8"
    pin = {"url": url, "bytes": 18_795_348, "sha256": checksum}
    facts = ct.reviewed_scan_checkpoint(pin)
    rows, deltas = ct.scanned_statement_rows(facts["complete_native_query"])
    assert len(rows) == 168 and deltas == [0, 0]
    assert ct.reviewed_scan_checkpoint({**pin, "sha256": "a" * 64}) is None
    assert ct.reviewed_scan_checkpoint({**pin, "url": "https://example.test/2018-sov.pdf"}) is None

    original = b"official file pinned by this fixture"
    digest = ct.pin
    monkeypatch.setattr(ct, "pin", lambda body: {"bytes": pin["bytes"], "sha256": checksum}
                        if body == original else digest(body))
    monkeypatch.setattr(ct, "parse", lambda *_: pytest.fail("A pinned edition must not invoke OCR"))
    prior = {feed: {"status": "scan_reconciliation_failed", "data": None,
                    "rejected_scan": {"key": {"report": pin, "policy": "old"}, "detail": "runner disagreement"}}}
    collector = results_intake.Collector(tmp_path, prior, {"urls": [], "prefixes": [], "hosts": []},
                                         datetime(2026, 11, 21, tzinfo=timezone.utc))
    index = f'<a href="{url}">2018 PDF</a>'.encode()
    monkeypatch.setattr(collector, "acquire", lambda target: (
        index if target == ct.STATEMENT_INDEX else original, {"origin": "test"}))
    accepted = ct.collect(collector, feed)
    assert accepted["status"] == "reported" and "rejected_scan" not in accepted
    assert accepted["data"] == {"report": pin, **facts}


def test_2026_collector_accepts_only_the_verified_table_layout(tmp_path, monkeypatch):
    import re

    import pymupdf

    feed = "CT-2026-general-town-turnout-archive"
    path = "/-/media/sots/electionservices/statementofvote_pdfs/"
    prior = f'<a href="{path}2024_statement_of_vote.pdf">2024</a>'.encode()
    link = f'<a href="{path}2026_statement_of_vote.pdf">2026</a>'.encode()
    title = "State of Connecticut Statement of Vote General Election November 3, 2026"
    header = ["Same-Day Registration (SDR), Turnout, Absentee & Early Voting Ballot Statistics",
              "Official Active Checklist", "Town", "Having Voted", "Percentage",
              "Absentee Ballots", "Early Voting and SDR"]
    table = [f"Andover 20 12 60.00% {'0 ' * 8}0", f"20 12 60.00% {'0 ' * 8}0"]
    index = prior
    requested = []
    historical = {}

    class FixturePdf(list):
        needs_pass = False
        permissions = pymupdf.PDF_PERM_COPY

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    class Cover:
        def get_text(self):
            return title

    def open_pdf(**_):
        return FixturePdf([Cover(), header + table])

    def acquire(url):
        requested.append(url)
        return (index if url == ct.STATEMENT_INDEX else repr(table).encode().join((b"%PDF-", b"")),
                {"origin": "synthetic_test"})

    fingerprint = re.sub(r"[^a-z0-9]", "", " ".join(header).lower())
    monkeypatch.setattr(pymupdf, "open", open_pdf)
    monkeypatch.setattr(ct, "physical_text", lambda page, _: page if isinstance(page, list) else [])
    monkeypatch.setattr(ct, "SDR_HEADER_SHA256", hashlib.sha256(fingerprint.encode()).hexdigest())
    monkeypatch.setattr(ct, "ROSTER", hashlib.sha256(b"Andover").hexdigest())

    def refresh():
        collector = results_intake.Collector(tmp_path, historical, {"urls": [], "prefixes": [], "hosts": []},
                                             datetime(2026, 11, 21, tzinfo=timezone.utc))
        monkeypatch.setattr(collector, "acquire", acquire)
        historical[feed] = ct.collect(collector, feed)
        return historical[feed]

    assert refresh()["status"] == "report_not_linked" and requested == [ct.STATEMENT_INDEX]
    index += link
    accepted = refresh()
    assert accepted["status"] == "reported"
    assert all(row["checked_as_voted_fraction"] == "0.60000000" for row in ct.exports(historical))
    table[-1] = f"20 13 65.00% {'0 ' * 8}0"
    assert refresh()["data"] == accepted["data"]
    assert historical[feed]["status"] == "retained_after_failure"
    table[-1] = f"20 12 60.00% {'0 ' * 8}1"
    header[-1] = "Different mode fields"
    assert refresh()["data"] == accepted["data"]
    assert historical[feed]["status"] == "retained_after_failure"
