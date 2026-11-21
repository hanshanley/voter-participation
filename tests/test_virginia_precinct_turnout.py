from datetime import datetime, timezone
from urllib.parse import urljoin

import pytest

from scripts import bulk_participation_archives as archives, results_granular, virginia_precinct_turnout as va
from scripts.participation_intake.contract import IntakeError


LOCALITY = "KING & QUEEN COUNTY"
LINK = "Turnout/KING_&_QUEEN_COUNTY.html"
URL = urljoin(va.VA_LOCALITY_URL, LINK)


def sources(clock="12/06/2022 02:16 AM", precinct=9, early=7):
    rows = [("# AB - Absentee By Mail", 2), ("# EV - Early Voting", early),
            ("# PE - Ballots Processed Post Election***", 3), ("## Provisional", 1),
            ("001 -Peters Creek", precinct)]
    control = dict(county=LOCALITY, by_mail=5, early_voting=early, provisional=1,
                   election_day=precinct, ballots_cast=precinct + early + 6)
    detail_rows = "".join(f"<tr><td>{label}</td><td>{count}</td></tr>" for label, count in rows)
    detail = (f'<title>2022 November General</title><h2 class="entry-title">Official Results</h2>'
              f'<h1 class="turnout-stats">Turnout Statistics - KING &amp; QUEEN COUNTY</h1>'
              f'<p class="asOf">Page generated on {clock}</p>'
              f'<table><tr><th>Precinct Name</th><th>Totals</th></tr>{detail_rows}</table>').encode()
    parent = dict(counties=[control], edition=datetime.strptime(clock, "%m/%d/%Y %I:%M %p").isoformat(),
                  native_clock=clock)
    index = b'<a href="Turnout/KING_&amp;_QUEEN_COUNTY.html">KING &amp; QUEEN COUNTY</a>'
    return parent, index, detail


class FixtureCollector:
    offline = False

    def __init__(self, dataset, old=None, day=21):
        _, index, detail = dataset
        self.bodies = {va.VA_LOCALITY_URL: index, URL: detail}
        self.prior = {va.FEED: old} if old else {}
        self.now = datetime(2026, 11, day, tzinfo=timezone.utc)
        self.attempts = []
        self.requests = []

    def observation_time(self):
        return self.now

    def acquire(self, url):
        self.requests.append(url)
        if url not in self.bodies:
            raise IntakeError("source_stopped", "Test access hold")
        return self.bodies[url], {}


def test_link_roster_and_detail_guards(monkeypatch):
    parent, index, detail = sources()
    control = parent["counties"][0]
    monkeypatch.setattr(va, "virginia_locality_report", lambda *_: parent)
    assert va.parse_index(index)["links"] == {LOCALITY: LINK}
    for bad in (index + index, index.replace(b"Turnout/", b"//outside.invalid/")):
        with pytest.raises(ValueError, match="link roster"):
            va.parse_index(bad)
    facts = va.parse_detail(detail, control=control, clock=parent["native_clock"])
    assert va.reconcile(facts, control)[-1]["precinct_code"] == "001"
    for invalid in (
        detail.replace(b"Official Results", b"Unofficial Results"),
        detail.replace(b"02:16", b"02:17"),
        detail.replace(b"QUEEN COUNTY", b"GEORGE COUNTY"),
        detail.replace(b"<td>7</td>", b"<td>8</td>").replace(b"<td>9</td>", b"<td>8</td>"),
        detail.replace(b"</table>", b"<tr><td>001 - Different label</td><td>0</td></tr></table>"),
    ):
        with pytest.raises(ValueError):
            va.parse_detail(invalid, control=control, clock=parent["native_clock"])


def test_weekly_retention_revisions_and_replay(monkeypatch, tmp_path):
    def capture(dataset, old=None, day=21, *, reuse=False, outage=False):
        monkeypatch.setattr(va, "virginia_locality_report", lambda *_: dataset[0])
        collector = FixtureCollector(dataset, old, day)
        if outage:
            del collector.bodies[URL]
        result = archives.collectors(reuse_checked_week=reuse)[va.FEED](collector)
        return result, collector

    initial = sources()
    accepted, original = capture(initial)
    assert accepted["status"] == "reported"
    assert original.requests == [va.VA_LOCALITY_URL, URL]
    entries = {va.FEED: accepted}
    baseline = {"index.json": b'{"states": {}}'}
    assert results_granular.project(baseline, entries) == (baseline, [])
    inventory = archives.original_inventory(entries)
    for report in inventory.values():
        (tmp_path / report["filename"]).write_bytes(original.bodies[report["url"]])
    assert archives.verify_original_reports(entries, tmp_path) == 2
    _, public = next((name, rows) for name, rows in archives.exports(entries) if name == va.CSV)
    public = list(public)
    assert sum(row["ballots"] for row in public) == 22
    assert public[-1]["unit_kind"] == "physical_precinct"
    assert all(row["turnout_rate"] is None and not row["geometry_qualified"] for row in public)

    reused, no_transport = capture(initial, accepted, reuse=True)
    assert reused == accepted and not no_transport.requests
    unchanged, _ = capture(initial, accepted, day=23, reuse=True)
    assert unchanged["first_observed_at"] == accepted["first_observed_at"]
    assert unchanged["archive_check_week_utc"] != accepted["archive_check_week_utc"]
    parent, index, detail = initial
    html_only = parent, index + b"<!-- new wrapper -->", detail + b"<!-- new wrapper -->"
    equivalent, _ = capture(html_only, accepted, day=23, reuse=True)
    assert equivalent == unchanged
    stale, _ = capture(initial, accepted, day=23, outage=True)
    assert stale["status"] == "retained_after_failure" and stale["error_stage"] == "detail_acquisition"
    assert stale["data"] == accepted["data"]
    silent, _ = capture(sources(precinct=11), accepted, day=23)
    assert silent["status"] == "retained_after_failure"
    up, _ = capture(sources(clock="12/07/2022 02:16 AM", precinct=11), accepted, day=23)
    down, _ = capture(sources(clock="12/08/2022 02:16 AM", precinct=8), up, day=24)
    assert [sum(r["ballots"] for r in va.exports({va.FEED: e})) for e in (accepted, up, down)] == [22, 24, 21]
    regressed, _ = capture(initial, down, day=25)
    assert regressed["status"] == "retained_after_failure" and regressed["data"] == down["data"]
