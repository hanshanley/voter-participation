import copy
import csv
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path

import pytest

from scripts.nationwide import STATES
from scripts.participation_intake.contract import encoded, pin
from scripts.results_granular import project
from scripts.results_intake import Collector
from scripts import results_native
from scripts import results_native_dc as adapter


HERE = Path(__file__).resolve().parent
FIXTURE = json.loads((HERE / "fixtures/dc-native-accepted.json").read_bytes())


def report_rows(body=None):
    source = FIXTURE["participation_report_csv"].encode() if body is None else body
    return list(csv.DictReader(io.StringIO(source.decode("utf-8-sig"), newline="")))


def report_body(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=adapter.CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def source_bodies(election=None, voters=None, report=None):
    election = FIXTURE["election"] if election is None else election
    voters = FIXTURE["voters"] if voters is None else voters
    return {
        adapter.ELECTION_URL: encoded(election),
        adapter.VOTERS_URL: encoded(voters),
        election["CsvLink"]: (
            FIXTURE["participation_report_csv"].encode()
            if report is None else report
        ),
    }


def full_baseline(template=None):
    template = copy.deepcopy(FIXTURE["template"] if template is None else template)
    files, states = {}, {}
    for state in STATES:
        selected = [template["id"]] if state == "DC" else []
        shard = {
            "contract": "portable.complete.state.v1",
            "state_code": state,
            "year": 2026,
            "records": [template] if state == "DC" else [],
            "views": {
                "available": {
                    "counties": selected, "precincts": [], "nongeographic": []},
                "official": {
                    "counties": selected, "precincts": [], "nongeographic": []},
                "in_person_early": {
                    "counties": [], "precincts": [], "nongeographic": []},
                "mail_returned": {
                    "counties": [], "precincts": [], "nongeographic": []},
            },
        }
        name = "states/" + state + ".json.gz"
        files[name] = gzip.compress(encoded(shard), mtime=0)
        states[state] = {"file": name}
    files["index.json"] = encoded({"states": states})
    return files


def parse(templates=None, bodies=None):
    templates = [copy.deepcopy(FIXTURE["template"])] if templates is None else templates
    bodies = source_bodies() if bodies is None else bodies

    def acquire(url, **_):
        body = bodies[url]
        return body, {"origin": "portable_fixture", **pin(body)}

    return adapter.statistics(
        bodies[adapter.ELECTION_URL], templates, adapter.ELECTION_URL, acquire=acquire)


def collect_with_actual_capture(tmp_path, baseline, bodies, prior=None):
    collector = Collector(
        tmp_path, prior or {}, {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 15, tzinfo=timezone.utc))

    def acquire(url, **_):
        body = bodies[url]
        return body, {"origin": "retained_original", **pin(body)}

    collector.acquire = acquire
    return results_native.collect_sources(collector, baseline), collector


def test_complete_safe_facts_project_all_slots_repeat_and_preserve_other_states(tmp_path):
    baseline = full_baseline()
    plan = results_native.source_plan(baseline)
    assert set(plan) == set(STATES)
    dc_sources = list(plan["DC"].values())
    assert len(dc_sources) == 1
    assert dc_sources[0]["adapter"] == adapter.ADAPTER
    assert dc_sources[0]["url"] == adapter.ELECTION_URL
    feeds, collector = collect_with_actual_capture(
        tmp_path / "first", baseline, source_bodies())
    assert len(feeds) == 1
    entry = next(iter(feeds.values()))
    assert entry["status"] == "reported"
    assert entry["adapter"] == adapter.ADAPTER
    query = entry["data"]["complete_native_query"][0]
    assert len(query["native_unit_rows"]) == 144
    assert len(query["source_participation_rows"]) == 288
    assert query["reconciliation"]["registered_voters"] == 457371
    assert query["reconciliation"]["ballots_cast"] == 185086
    assert not query["reconciliation"]["candidate_votes_used_as_ballots"]
    assert not query["reconciliation"]["early_or_mail_reports_added"]
    assert collector.attempts[0]["status"] == "retained_original"

    before_other = {key: value for key, value in baseline.items()
                    if key not in {"index.json", "states/DC.json.gz"}}
    after, changes = project(baseline, feeds)
    assert len(changes) == 1
    assert changes[0]["previous"] == changes[0]["current"] == 185086
    assert before_other == {key: after[key] for key in before_other}
    row = json.loads(gzip.decompress(after["states/DC.json.gz"]))["records"][0]
    assert row["count"]["value"] == 185086
    assert row["denominator"]["value"] == 457371
    assert row["denominator"]["qualified"] is True
    assert row["view"]["reported_pct"] == pytest.approx(100 * 185086 / 457371)
    assert row["view"]["maps_approved"] is False
    assert row["source_clock"]["literal"] == "2026-11-04T04:36:21.283Z"
    assert row["source_clock"]["timezone"] == "UTC"
    assert row["reporting_status"]["complete"] is None

    repeated_feeds, _ = collect_with_actual_capture(
        tmp_path / "repeat", after, source_bodies(), prior=feeds)
    repeated, repeated_changes = project(after, repeated_feeds)
    assert repeated == after
    assert repeated_changes == []


def test_revised_count_and_true_zero_project_without_new_identity_rate_or_geography():
    first = parse()
    baseline = full_baseline()
    first_entry = {
        "status": "reported",
        "source": {"url": adapter.ELECTION_URL, **pin(source_bodies()[adapter.ELECTION_URL])},
        "data": first,
    }
    after, _ = project(baseline, {"DC-native": first_entry})
    template = json.loads(gzip.decompress(after["states/DC.json.gz"]))["records"][0]

    election = copy.deepcopy(FIXTURE["election"])
    election["LastUpdated"] = "2026-11-15T10:00:00.1234567Z"
    voters = copy.deepcopy(FIXTURE["voters"])
    rows = report_rows()
    ballot = next(row for row in rows
                  if row["ContestNumber"] == "-1" and row["PrecinctNumber"] == "143")
    removed = int(ballot["Votes"])
    ballot["Votes"] = "0"
    voters["TotalBallotsCast"] -= removed
    voters["ElectionDayVoters"] -= removed
    bodies = source_bodies(election, voters, report_body(rows))
    data = parse([template], bodies)
    assert data["updates"][0]["value"] == 185086 - removed
    assert next(row for row in data["complete_native_query"][0]["native_unit_rows"]
                if row["precinct_number"] == 143)["ballots_cast"] == 0
    entry = {
        "status": "reported",
        "source": {"url": adapter.ELECTION_URL, **pin(bodies[adapter.ELECTION_URL])},
        "data": data,
    }
    projected, changes = project(after, {"DC-native": entry})
    assert len(changes) == 1
    current = json.loads(gzip.decompress(projected["states/DC.json.gz"]))["records"][0]
    for field in ("id", "election", "geography", "measure"):
        assert current[field] == template[field]
    assert current["count"]["value"] == 185086 - removed
    assert current["denominator"]["value"] == 457371
    assert current["denominator"]["qualified"] is True
    assert current["view"]["maps_approved"] is False


def test_candidate_votes_are_never_ballots_and_unknown_count_is_rejected():
    rows = report_rows()
    rows.append({
        "ElectionDate": "11/3/2026 12:00:00 AM",
        "ElectionName": "General Election",
        "ContestNumber": "999",
        "ContestName": "UNRELATED CANDIDATE CONTEST",
        "PrecinctNumber": "1",
        "WardNumber": "6",
        "Candidate": "Candidate",
        "Party": "NPN",
        "Votes": "999999",
    })
    data = parse(bodies=source_bodies(report=report_body(rows)))
    assert data["updates"][0]["value"] == 185086
    assert not data["complete_native_query"][0]["reconciliation"][
        "candidate_votes_used_as_ballots"]

    rows[0]["Votes"] = ""
    with pytest.raises(ValueError, match="not zero"):
        parse(bodies=source_bodies(report=report_body(rows)))


def test_changed_election_authority_identity_and_clock_rollback_fail_closed():
    election = copy.deepcopy(FIXTURE["election"])
    election["CsvLink"] = "https://example.test/report.csv"
    with pytest.raises(ValueError, match="authority"):
        parse(bodies=source_bodies(election=election))

    template = copy.deepcopy(FIXTURE["template"])
    template["geography"]["id"] = "DC|forged|"
    with pytest.raises(ValueError, match="identity"):
        parse([template])

    first = parse()
    entry = {
        "status": "reported",
        "source": {"url": adapter.ELECTION_URL, **pin(source_bodies()[adapter.ELECTION_URL])},
        "data": first,
    }
    after, _ = project(full_baseline(), {"DC-native": entry})
    projected = json.loads(gzip.decompress(after["states/DC.json.gz"]))["records"]
    election = copy.deepcopy(FIXTURE["election"])
    election["LastUpdated"] = "2026-11-04T04:36:21.282Z"
    with pytest.raises(ValueError, match="regressed"):
        parse(projected, source_bodies(election=election))
