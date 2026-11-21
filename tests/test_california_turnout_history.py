from datetime import datetime, timezone
from types import SimpleNamespace

import pypdf
import pytest

from scripts import bulk_participation_archives as bulk, california_turnout_history as history, results_intake


URL = "https://elections.cdn.sos.ca.gov/sov/2025-special/sov/04-historical-voter-reg-general.pdf"
NOW = datetime(2026, 11, 21, tzinfo=timezone.utc)


def original(last="2025", *, registered="120", voted=80, wrong_roles=False):
    general = []
    for year in range(1910, 2025, 2):
        day = history.federal_general(year).day
        marker = " P" if year % 4 == 0 else ""
        reg = "* * * *" if year == 1910 else "* * * 120" if year < 1922 else "40 40 40 120"
        rate = "*" if year == 1910 else "66.67%"
        general.append(f"Nov. {day}, {year}{marker} 200 {reg} 80 {rate} 40.00%")
    special = f"Nov. 4, {last} S 200 40 40 40 {registered} {voted} 66.67% {voted/2:.2f}%"
    headings = list(history.HEADER)
    if wrong_roles:
        headings[-1] = headings[-1].replace("Voters Registered Eligible", "Voters Eligible Registered")
    return ("\n".join([headings[0], history.TITLE + last, *headings[1:], *general, special, "Notes",
                       "* Indicates information not available.", "P indicates a presidential election year.",
                       "S indicates a statewide special election.", "4"]) + "\n").encode()


@pytest.fixture
def native_pdf(monkeypatch):
    monkeypatch.setattr(pypdf, "PdfReader", lambda buf: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda **_: buf.getvalue()[9:].decode())]))
    return lambda **kwargs: b"%PDF-1.6\n" + original(**kwargs)


def test_bulk_replay_preserves_reported_counts_and_different_rate_holds(native_pdf, tmp_path):
    body = native_pdf(registered="121", voted=79)
    facts = history.parse(body, url=URL)
    rows = history.query(facts["native_lines"], url=URL)
    assert len(rows) == 59
    assert rows[0]["reported_registered_voters"] is None
    assert rows[-1]["election_type"] == "statewide_special"
    assert rows[-1]["reported_total_voters"] == 79
    assert rows[-1]["registration_component_difference"] == -1
    assert rows[-1]["qualified_registered_pct"] is None
    assert rows[-1]["qualified_eligible_pct"] == 39.5
    with pytest.raises(ValueError, match="coverage differs"):
        history.query(facts["native_lines"][:5] + facts["native_lines"][6:], url=URL)
    with pytest.raises(ValueError, match="column roles"):
        history.parse(native_pdf(wrong_roles=True), url=URL)

    data = {"report": {"url": URL, **history.pin(body)}, **facts}
    entries = {history.FEED: {"status": "reported", "data": data}}
    manifest = bulk.original_inventory(entries)
    (tmp_path / manifest[history.FEED]["filename"]).write_bytes(body)
    assert bulk.verify_original_reports(entries, tmp_path) == 1
    assert dict(bulk.exports(entries))[history.CSV][-1]["reported_total_voters"] == 79


def test_automatic_capture_accepts_upward_and_downward_revisions_and_retains_on_failure(
        native_pdf, tmp_path, monkeypatch):
    source = {
        history.INDEX: (f'<a href="{URL}">Historical Voter Registration and Participation in Statewide '
                        'General and Special Elections 1910-2025 (PDF)</a>').encode(),
        URL: native_pdf(),
    }
    monkeypatch.setattr(results_intake.Collector, "acquire", lambda _, url: (source[url], {"origin": "fixture"}))
    c = results_intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []}, NOW)

    def run(old=None):
        c.prior = {history.FEED: old} if old else {}
        return bulk.collectors()[history.FEED](c)

    first = run()
    assert first["status"] == "reported"
    assert run(first)["data"] == first["data"]
    source[URL] = native_pdf(voted=81)
    up = run(first)
    assert up["status"] == "reported"
    source[URL] = native_pdf(voted=79)
    down = run(up)
    assert history.exports({history.FEED: down})[-1]["reported_total_voters"] == 79
    source[URL] = native_pdf(wrong_roles=True)
    failed = run(down)
    assert failed["data"] == down["data"]
    assert failed["status"] == "retained_after_failure"
