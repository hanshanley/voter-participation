from datetime import datetime, timezone
from types import SimpleNamespace

import pypdf
import pytest

from scripts import hawaii_precinct_turnout as hi, results_intake


@pytest.fixture
def reports(monkeypatch):
    monkeypatch.setattr(hi, "ROSTER", hi.digest(b"01-01\n01-02\nOS I\n"))
    monkeypatch.setattr(pypdf, "PdfReader", lambda buf, **_: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda txt=page: txt)
                                   for page in buf.getvalue().decode()[9:-6].split("\f")]))
    monkeypatch.setattr(hi, "statewide_control", lambda body, **_: {
        "report_clock": "2026-11-10T20:00:08-10:00",
        "native_values": dict(zip(("TOTAL REGISTRATION", "TOTAL TURNOUT", "Mail TURNOUT", "In-Person TURNOUT"),
                                  (100, 40 + int(body), 40, int(body)))),
    })

    def report(count=10, *, duplicate=False, missing=False):
        rows = [("01-01", "Mail", 100, 40), ("01-01", "In-Person", 100, count),
                ("01-02", "Mail", 0, 0), ("01-02", "In-Person", 0, 1),
                ("OS I", "Mail", 0, 0), ("OS I", "In-Person", 0, 0)]
        if duplicate:
            rows.insert(1, rows[0])
        blocks = []
        for i, (unit, mode, reg, votes) in enumerate(rows, 1):
            block = ["Printed on: 11/10/2026 at 08:00:58 pm",
                     "GENERAL ELECTION 2026 - State of Hawaii - Statewide Precinct",
                     f"{mode} {unit}", "November 3, 2026", "FINAL"]
            if not missing or i != 2:
                frac = f"{votes/reg*100:.1f}%" if reg else "0.0%"
                block += [hi.FOOTER, "*" * 40, "GENERAL", "*" * 40, "PRECINCT REGISTRATION",
                          str(reg), f"{mode} TURNOUT", str(votes), frac]
            blocks.append("\n".join([*block, f"PAGE {i}"]))
        return ("%PDF-1.6\n" + "\f".join(blocks) + "\n%%EOF").encode()
    return report


def test_native_counts_preserve_rate_holds_and_reject_incomplete_blocks(reports):
    detail = hi.parse_detail(reports())
    with pytest.raises(ValueError, match="repeats"):
        hi.parse_detail(reports(duplicate=True))
    with pytest.raises(ValueError, match="missing"):
        hi.parse_detail(reports(missing=True))
    data = {"detail": detail, "control": hi.statewide_control(b"9"),
            "report": {"url": hi.URL, **hi.pin(reports())},
            "supporting_report": {"url": hi.HI_URL, **hi.pin(b"9")}}
    rows = hi.exports({hi.FEED: {"status": "reported", "data": data}})
    assert [r["reported_mode_sum"] for r in rows] == [50, 1, 0]
    assert rows[0]["precinct_sum_minus_state_reported_mode_sum"] == 2
    assert [r["rate_hold_reason"] for r in rows] == [
        "precinct_and_state_ballot_counts_disagree", "reported_ballots_exceed_registration",
        "nongeographic_reporting_unit"]
    data["control"] = hi.statewide_control(b"11")
    rows = hi.exports({hi.FEED: {"status": "reported", "data": data}})
    assert rows[0]["qualified_registration_fraction_pct"] == 50
    assert rows[1]["qualified_registration_fraction_pct"] is None


def test_automatic_capture_accepts_revisions_and_retains_last_good(reports, tmp_path, monkeypatch):
    bodies = {hi.URL: reports(), hi.HI_URL: b"9"}
    monkeypatch.setattr(results_intake.Collector, "acquire", lambda _, url: (bodies[url], {"origin": "fixture"}))
    c = results_intake.Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                                 datetime(2026, 11, 21, tzinfo=timezone.utc))
    first = hi.collect(c, hi.FEED)
    assert first["status"] == "reported"
    c.prior = {hi.FEED: first}
    assert hi.collect(c, hi.FEED)["data"] == first["data"]
    for count in (12, 8):
        bodies[hi.URL] = reports(count)
        revised = hi.collect(c, hi.FEED)
        assert hi.exports({hi.FEED: revised})[0]["reported_in_person"] == count
        c.prior = {hi.FEED: revised}
    bodies[hi.URL] = reports(duplicate=True)
    failed = hi.collect(c, hi.FEED)
    assert failed["status"] == "retained_after_failure"
    assert failed["data"] == revised["data"]


def test_historical_detail_requires_its_own_date_and_profile(reports, monkeypatch):
    monkeypatch.setattr(hi, "HISTORICAL_ROSTER", hi.ROSTER)
    historical = (reports().replace(b"11/10/2026", b"11/13/2024")
                  .replace(b"GENERAL ELECTION 2026 - State of Hawaii - Statewide Precinct",
                           b"GENERAL ELECTION 2024 - State of Hawaii - Statewide Precinct Report")
                  .replace(b"November 3, 2026", b"November 5, 2024")
                  .replace(b"Mail ", b"MAIL ").replace(b"In-Person ", b"IN-PERSON ")
                  .replace(b"FINAL", b"Final"))
    assert hi.parse_detail(historical, year=2024)["mode_blocks"][0][:2] == ["01-01", "Mail"]
    with pytest.raises(ValueError, match="election"):
        hi.parse_detail(historical, year=2026)
