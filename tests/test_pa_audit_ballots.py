import csv
from datetime import datetime, timezone
import io

import pytest

from scripts import pa_audit_ballots as audit
from scripts.bulk_participation_archives import original_inventory, verify_original_reports
from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_intake import Collector
from scripts.results_granular import project


URL = (
    "https://www.pa.gov/content/dam/copapwp-pagov/en/vote/elections/risk-limiting-audit-reports/"
    "2026-general-election/audit-report-november-3-2026-general-election-2026-11-19t1653z.csv"
)


def fixture(total=100, sampled=20, pending=5):
    out = io.StringIO(newline="")
    csv.writer(out).writerows([
        ["######## ELECTION INFO ########"],
        ["Organization", "Election Name", "State"], ["Pennsylvania", "2026 General Election", "PA"],
        ["######## CONTESTS ########"],
        ["Contest Name", "Targeted?", "Number of Winners", "Votes Allowed", "Total Ballots Cast",
         "Vote Totals", "Vote Totals from Batches", "Pending Ballots"],
        ["Governor", "Targeted", 1, 1, total, "ignore", "ignore", pending],
        ["######## AUDIT SETTINGS ########"],
        ["Audit Name", "Audit Type", "Audit Math Type"],
        ["November 3, 2026 General Election", "BATCH_COMPARISON", "MACRO"],
        ["######## ROUNDS ########"],
        ["Round Number", "Contest Name", "Targeted?", "Sample Size", "Risk Limit Met?", "P-Value",
         "Start Time", "End Time", "Audited Votes", "Batches Sampled", "Ballots Sampled"],
        [1, "Governor", "Targeted", 1, "Yes", "0.05", "2026-11-13T17:56:35+00:00",
         "2026-11-19T16:51:52+00:00", "ignore", 1, 20],
        ["######## SAMPLED BATCHES ########"],
        ["Jurisdiction Name", "Batch Name", "Ballots in Batch", "Ticket Numbers: Governor", "Audited?",
         "Last Edited By"],
        ["Somerset", "Batch 1", sampled, "ignore", "Yes", "person@example.test"],
        ["Totals", "", 20, "", "", ""],
    ])
    return out.getvalue().encode()


def test_audit_archive_revises_and_replays_without_promoting_sample_or_pending_ballots(tmp_path):
    sources = {
        audit.INDEX: f'<a href="{URL}">View detailed results of the 2026 General Election risk-limiting audit.</a>'.encode(),
        URL: fixture(),
    }

    def run(previous=None):
        collector = Collector(tmp_path, previous or {}, {"urls": [], "prefixes": [], "hosts": []},
                              datetime(2026, 11, 21, tzinfo=timezone.utc))

        def acquire(url):
            if url not in sources:
                raise IntakeError("transport", "Temporary outage")
            return sources[url], {"origin": "fixture", **pin(sources[url])}

        collector.acquire = acquire
        return {audit.FEED: audit.collect(collector, audit.FEED)}

    first = run()
    baseline = {"index.json": b'{"states": {}}'}
    assert project(baseline, first) == (baseline, [])
    assert run(first) == first
    universe, batch = audit.exports(first)
    assert (universe["audit_report_total_ballots_cast"], universe["audit_report_pending_ballots"]) == (100, 5)
    assert batch["sample_batch_ballots"] == 20
    assert all(not row["final_turnout_qualified"] and not row["geographic_turnout_qualified"]
               for row in (universe, batch))
    assert "person@example.test" not in repr(first)
    for revised in (104, 96):
        sources[URL] = fixture(total=revised)
        first = run(first)
        assert audit.exports(first)[0]["audit_report_total_ballots_cast"] == revised
    inventory = original_inventory(first)[audit.FEED]
    (tmp_path / inventory["filename"]).write_bytes(sources.pop(URL))
    assert verify_original_reports(first, tmp_path) == 1
    kept = run(first)
    assert audit.exports(kept)[0]["source_status"] == "retained_after_failure"
    assert audit.exports(kept)[0]["audit_report_total_ballots_cast"] == 96


@pytest.mark.parametrize("body", [fixture(sampled=19), fixture(pending=101),
                                fixture().replace(b"2026 General Election,PA", b"2026 Primary Election,PA")])
def test_wrong_election_or_failed_arithmetic_stays_out(body):
    with pytest.raises(ValueError):
        audit.parse(body, url=URL)
