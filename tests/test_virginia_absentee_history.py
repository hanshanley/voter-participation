import csv
from datetime import datetime, timezone
import io

import pytest

from scripts import bulk_participation_archives as archives, results_granular, virginia_absentee_history as va
from scripts.participation_intake.contract import encoded, pin
from scripts.results_intake import Collector


LOCALITY = "YORK COUNTY"
ROWS = [
    (LOCALITY, "01", "18 to 25", "X", "NE - No Excuse", "Application type", "Mail", 3),
    (LOCALITY, "", "18 to 25", "", "NE - No Excuse", "Application type", "", 4),
]
CONTROL = {"edition": "2022-12-05T02:15:00", "applications": {"Application type": 7}, "receipts": {"Mail": 3}}


def report(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows([va.HEADER, *rows])
    return buffer.getvalue().encode()


def test_group_counts_reconcile_and_do_not_project_turnout(monkeypatch, tmp_path):
    monkeypatch.setattr(va, "VA_LOCALITY_ROSTER", pin(encoded([LOCALITY]))["sha256"])
    monkeypatch.setattr(va, "controls", lambda _: CONTROL)
    monkeypatch.setattr(va, "certified", lambda _: 3)
    bodies = {va.RAW: report(ROWS), va.REPORT: b"html", va.VA_URL: b"history"}
    collector = Collector(tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
                          datetime(2026, 11, 21, tzinfo=timezone.utc), offline=True)
    monkeypatch.setattr(collector, "acquire", lambda url: (bodies[url], {"origin": "cached_offline"}))
    entries = {va.FEED: va.collect(collector)}
    assert entries[va.FEED]["status"] == "reported"
    baseline = {"index.json": b'{"states": {}}'}
    assert results_granular.project(baseline, entries) == (baseline, [])
    for r in archives.original_inventory(entries).values():
        (tmp_path / r["filename"]).write_bytes(bodies[r["url"]])
    assert archives.verify_original_reports(entries, tmp_path) == 3
    state = [r for r in va.exports(entries) if r["geography_level"] == "state"]
    assert [(r["measure"], r["reported_count"], r["native_gender"], r["turnout_rate"]) for r in state] == [
        ("application_without_recorded_receipt", 4, None, None),
        ("returned_absentee_ballot", 3, "X", None),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        va.extract(report([*ROWS, ROWS[0]]), control=CONTROL, certified_receipts=3)
    with pytest.raises(ValueError, match="published aggregate controls"):
        va.extract(report(ROWS), control=CONTROL, certified_receipts=4)
