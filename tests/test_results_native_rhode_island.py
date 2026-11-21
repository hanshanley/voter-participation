import copy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from uuid import UUID

import pytest

from scripts.nationwide import STATES
from scripts.participation_intake.contract import encoded, pin
from scripts.results_granular import project
from scripts.results_intake import Collector
from scripts import results_native
from scripts import results_native_rhode_island as adapter


HERE = Path(__file__).resolve().parent
FIXTURE = json.loads(gzip.decompress(
    (HERE / "fixtures/rhode-island-native-accepted.json.gz").read_bytes()))


def source_document():
    return copy.deepcopy(FIXTURE["source_document"])


def source_body(document=None):
    return encoded(source_document() if document is None else document)


def full_baseline(templates=None):
    templates = copy.deepcopy(FIXTURE["templates"] if templates is None else templates)
    files, states = {}, {}
    for state in STATES:
        selected = [row["id"] for row in templates] if state == "RI" else []
        shard = {
            "contract": "portable.complete.state.v1",
            "state_code": state,
            "year": 2026,
            "records": templates if state == "RI" else [],
            "views": {
                "available": {
                    "counties": [row["id"] for row in templates
                                 if row["geography"]["level"] == "municipality"],
                    "precincts": [],
                    "nongeographic": [row["id"] for row in templates
                                      if row["geography"]["level"] == "nongeographic"],
                },
                "official": {
                    "counties": [row["id"] for row in templates
                                 if row["geography"]["level"] == "municipality"],
                    "precincts": [],
                    "nongeographic": [row["id"] for row in templates
                                      if row["geography"]["level"] == "nongeographic"],
                },
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


def collect(work_root, baseline, body=None, prior=None, name="capture"):
    work = work_root / name
    collector = Collector(
        work,
        prior or {},
        {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 15, tzinfo=timezone.utc),
    )
    retained = source_body() if body is None else body

    def acquire(url, **_):
        assert url == adapter.API_URL
        return retained, {"origin": "retained_original", **pin(retained)}

    collector.acquire = acquire
    return results_native.collect_sources(collector, baseline), collector


def test_complete_safe_facts_capture_project_all_slots_repeat_and_preserve_other_states(
        tmp_path):
    baseline = full_baseline()
    plan = results_native.source_plan(baseline)
    assert set(plan) == set(STATES)
    sources = list(plan["RI"].values())
    assert len(sources) == 1
    assert sources[0]["adapter"] == adapter.ADAPTER
    assert sources[0]["url"] == adapter.API_URL
    assert len(sources[0]["templates"]) == len(FIXTURE["templates"])

    feeds, collector = collect(tmp_path, baseline)
    assert len(feeds) == 1
    entry = next(iter(feeds.values()))
    assert entry["status"] == "reported"
    assert entry["adapter"] == adapter.ADAPTER
    assert collector.attempts[0]["status"] == "retained_original"
    query = entry["data"]["complete_native_query"][0]
    source_rows = FIXTURE["source_document"]["localityElections"]
    children = {
        str(UUID(row["id"])): row["name"][0]["text"]
        for row in FIXTURE["source_document"]["jurisdiction"]["childLocalities"]
    }
    assert len(query["source_locality_rows"]) == len(source_rows)
    assert query["separate_source_parent"]["ballots_qualified_for_projection"] is False
    assert query["reconciliation"]["federal_ballots_unallocated"] == next(
        row["ballotsCast"] for row in source_rows
        if children[str(UUID(row["jurisdictionId"]))] == "Federal")
    assert not query["reconciliation"]["candidate_votes_used_as_ballots"]
    assert not query["reconciliation"]["state_parent_derived_from_locality_sum"]

    before_other = {
        key: value for key, value in baseline.items()
        if key not in {"index.json", "states/RI.json.gz"}
    }
    after, changes = project(baseline, feeds)
    assert len(changes) == len(FIXTURE["templates"])
    assert before_other == {key: after[key] for key in before_other}
    rows = json.loads(gzip.decompress(after["states/RI.json.gz"]))["records"]
    assert len(rows) == len(FIXTURE["templates"])
    for before, current in zip(FIXTURE["templates"], rows):
        for field in ("id", "election", "geography", "measure"):
            assert current[field] == before[field]
        assert current["denominator"]["qualified"] is False
        assert current["view"]["reported_pct"] is None
        assert current["view"]["maps_approved"] is False
        assert current["geography"]["join"] == before["geography"]["join"]
        assert current["reporting_status"]["complete"] is None
        assert current["source_clock"]["timezone"] == "UTC"
        assert current["view"]["native_record"]["source_clock_timezone_literal"] == "UTC"
        assert current["view"]["native_record"]["query"][
            "source_clock_timezone_literal"] == "UTC"

    repeated_feeds, _ = collect(
        tmp_path, after, prior=feeds, name="repeat")
    repeated, repeated_changes = project(after, repeated_feeds)
    assert repeated == after
    assert repeated_changes == []


def test_complete_native_export_preserves_withheld_parent_and_unallocated_federal(tmp_path):
    baseline = full_baseline()
    feeds, _ = collect(tmp_path, baseline)
    entry = feeds[adapter.IDENTITY]
    query = entry["data"]["complete_native_query"][0]
    rows = adapter.turnout_rows(feeds)
    assert len(rows) == 41
    assert rows[0]["ballots"] == query["separate_source_parent"]["ballots"]
    assert rows[0]["count_disposition"] == "native_parent_withheld"
    assert all(not row["rate_qualified"] for row in rows)
    municipal = [row for row in rows if row["geography_level"] == "municipality"]
    assert len(municipal) == 39
    assert sum(row["ballots"] for row in municipal) == query["reconciliation"]["municipal_ballots_literal_sum"]
    federal, = (row for row in rows if row["geography_level"] == "nongeographic")
    assert federal["count_disposition"] == "unallocated_federal"
    assert federal["ballots"] == query["reconciliation"]["federal_ballots_unallocated"]
    entry["status"] = "retained_after_failure"
    assert all(row["source_status"] == "retained_after_failure" for row in adapter.turnout_rows(feeds))
    query["source_locality_rows"].pop()
    with pytest.raises(ValueError, match="turnout export evidence"):
        adapter.turnout_rows(feeds)


def test_revised_count_and_true_zero_preserve_literal_roles_and_separate_federal_scope(
        tmp_path):
    first_feeds, _ = collect(tmp_path, full_baseline(), name="first")
    after, _ = project(full_baseline(), first_feeds)
    document = source_document()
    children = {
        str(UUID(row["id"])): row["name"][0]["text"]
        for row in document["jurisdiction"]["childLocalities"]
    }
    municipal = next(
        row for row in document["localityElections"]
        if children[str(UUID(row["jurisdictionId"]))] != "Federal"
        and row["ballotsCast"] < row["totalVoters"]
    )
    municipal["ballotsCast"] = 0
    municipal["asOf"] = "2026-11-15T12:00:00.0000000Z"
    federal = next(
        row for row in document["localityElections"]
        if children[str(UUID(row["jurisdictionId"]))] == "Federal"
    )
    federal["ballotsCast"] += 1
    federal["asOf"] = "2026-11-15T12:00:00.0000000Z"
    document["election"]["asOf"] = "2026-11-15T12:00:00.0000000Z"

    feeds, _ = collect(
        tmp_path, after, source_body(document),
        prior=first_feeds, name="revision")
    entry = next(iter(feeds.values()))
    updates = {
        row["native"]["locality"]: row for row in entry["data"]["updates"]
    }
    assert updates[children[str(UUID(municipal["jurisdictionId"]))]]["value"] == 0
    assert updates["Federal"]["value"] == federal["ballotsCast"]
    assert updates["Federal"]["registered"] == federal["totalVoters"]
    assert updates["Federal"]["native"]["federal_reporting_unit_unallocated"] is True
    projected, changes = project(after, feeds)
    assert len(changes) == len(FIXTURE["templates"])
    assert sum(row["previous"] != row["current"] for row in changes) == 2
    rows = json.loads(gzip.decompress(projected["states/RI.json.gz"]))["records"]
    assert all(row["denominator"]["qualified"] is False for row in rows)
    assert all(row["view"]["reported_pct"] is None for row in rows)


def test_reconciled_positive_parent_does_not_interrupt_locality_refresh(tmp_path):
    baseline = full_baseline()
    initial, _ = collect(tmp_path, baseline, name="placeholder")
    current, _ = project(baseline, initial)
    document = source_document()
    parent = document["election"]
    parent["ballotsCast"] = sum(row["ballotsCast"] for row in document["localityElections"])
    assert parent["ballotsCast"] > 0
    with pytest.raises(ValueError, match="without a newer count clock"):
        adapter.statistics(source_body(document), FIXTURE["templates"], adapter.API_URL,
                           prior=next(iter(initial.values())))
    parent["asOf"] = "2026-11-15T12:00:00Z"
    feeds, _ = collect(tmp_path, current, source_body(document), prior=initial, name="positive")
    entry = next(iter(feeds.values()))
    assert entry["status"] == "reported"
    query = entry["data"]["complete_native_query"][0]
    assert query["separate_source_parent"]["ballots"] == parent["ballotsCast"]
    assert query["separate_source_parent"]["ballots_qualified_for_projection"] is False
    assert query["reconciliation"]["federal_ballots_unallocated"] > 0
    updated, _ = project(current, feeds)
    assert len(json.loads(gzip.decompress(updated["states/RI.json.gz"]))["records"]) == 40
    repeated, _ = collect(tmp_path, updated, source_body(document), prior=feeds, name="repeat-positive")
    assert project(updated, repeated) == (updated, [])

    before = parent["ballotsCast"]
    for hour, delta in ((13, -2), (14, 3)):
        clock = f"2026-11-15T{hour}:00:00Z"
        document["localityElections"][0]["ballotsCast"] += delta
        document["localityElections"][0]["asOf"] = parent["asOf"] = clock
        held, _ = collect(tmp_path, updated, source_body(document), prior=feeds, name=f"mismatch-{hour}")
        assert next(iter(held.values()))["status"] == "retained_after_failure"
        assert project(updated, held) == (updated, [])

        parent["ballotsCast"] += delta
        feeds, _ = collect(tmp_path, updated, source_body(document), prior=held, name=f"corrected-{hour}")
        entry = next(iter(feeds.values()))
        assert entry["status"] == "reported"
        assert entry["data"]["complete_native_query"][0]["separate_source_parent"]["ballots"] == before + delta
        updated, changes = project(updated, feeds)
        assert sum(row["current"] - row["previous"] for row in changes) == delta
        before += delta


def test_parent_and_locality_inventory_identity_registration_and_clock_fail_closed():
    cases = []
    missing_parent = source_document()
    missing_parent.pop("election")
    cases.append((missing_parent, "declaration"))
    parent = source_document()
    parent["election"]["ballotsCast"] = 1
    cases.append((parent, "parent ballots"))
    missing = source_document()
    child_names = {
        str(UUID(row["id"])): row["name"][0]["text"]
        for row in missing["jurisdiction"]["childLocalities"]
    }
    missing["localityElections"] = [
        row for row in missing["localityElections"]
        if child_names[str(UUID(row["jurisdictionId"]))] != "Federal"
    ]
    cases.append((missing, "inventory"))
    registration = source_document()
    registration["election"]["totalVoters"] += 1
    cases.append((registration, "registrations"))
    identity = source_document()
    identity["jurisdiction"]["childLocalities"][0]["name"][0]["text"] = "Changed"
    cases.append((identity, "identity/name"))
    rollback = source_document()
    rollback["localityElections"][0]["asOf"] = "2026-11-04T00:00:00Z"
    cases.append((rollback, "regressed"))
    missing_count = source_document()
    missing_count["localityElections"][0]["ballotsCast"] = None
    cases.append((missing_count, "not zero"))
    for document, message in cases:
        with pytest.raises(ValueError, match=message):
            adapter.statistics(
                source_body(document), copy.deepcopy(FIXTURE["templates"]), adapter.API_URL)


def test_frozen_registration_prior_vector_rejects_each_clock_rollback_and_keeps_prior(
        tmp_path):
    baseline = full_baseline()
    revised = source_document()
    target = revised["localityElections"][0]
    original_ballots = target["ballotsCast"]
    target["ballotsCast"] -= 1
    target["asOf"] = "2026-11-15T12:00:00Z"
    revised["election"]["asOf"] = "2026-11-15T12:00:00Z"
    first, _ = collect(
        tmp_path, baseline, source_body(revised), name="frozen-revised")
    first_entry = next(iter(first.values()))
    assert first_entry["status"] == "reported"
    first_update = next(
        row for row in first_entry["data"]["updates"]
        if row["native"]["source_locality_id"]
            == str(UUID(target["jurisdictionId"])))
    assert first_update["value"] == original_ballots - 1
    assert first_update["clock"] == "2026-11-15T12:00:00Z"

    rollback = source_document()
    rollback["localityElections"][0]["asOf"] = "2026-11-14T12:00:00Z"
    rollback["election"]["asOf"] = "2026-11-14T12:00:00Z"
    failed, collector = collect(
        tmp_path, baseline, source_body(rollback),
        prior=first, name="frozen-rollback")
    failed_entry = next(iter(failed.values()))
    assert failed_entry["status"] == "retained_after_failure"
    assert failed_entry["error"] == "schema_or_source_semantics_changed"
    assert failed_entry["data"] == first_entry["data"]
    assert failed_entry["source"] == first_entry["source"]
    assert failed_entry["first_observed_at"] == first_entry["first_observed_at"]
    assert collector.attempts[0]["status"] == "schema_or_source_semantics_changed"
    retained_update = next(
        row for row in failed_entry["data"]["updates"]
        if row["native"]["source_locality_id"]
            == str(UUID(target["jurisdictionId"])))
    assert retained_update["value"] == original_ballots - 1
    assert retained_update["clock"] == "2026-11-15T12:00:00Z"

    repeated, _ = collect(
        tmp_path, baseline, source_body(revised),
        prior=first, name="frozen-repeat")
    repeated_entry = next(iter(repeated.values()))
    assert repeated_entry["status"] == "reported"
    assert repeated_entry["error"] is None
    assert repeated_entry["data"] == first_entry["data"]
    assert repeated_entry["source"] == first_entry["source"]

    partial = copy.deepcopy(revised)
    partial["localityElections"][0]["asOf"] = "2026-11-14T12:00:00Z"
    partial["localityElections"][1]["asOf"] = "2026-11-16T12:00:00Z"
    partial["election"]["asOf"] = "2026-11-16T12:00:00Z"
    partial_failed, _ = collect(
        tmp_path, baseline, source_body(partial),
        prior=first, name="frozen-partial-rollback")
    assert next(iter(partial_failed.values()))["status"] == "retained_after_failure"

    parent_future = source_document()
    parent_future["election"]["asOf"] = "2026-11-15T12:00:00Z"
    parent_first, _ = collect(
        tmp_path, baseline, source_body(parent_future),
        name="frozen-parent-first")
    parent_rollback = source_document()
    parent_rollback["election"]["asOf"] = "2026-11-14T12:00:00Z"
    parent_failed, _ = collect(
        tmp_path, baseline, source_body(parent_rollback),
        prior=parent_first, name="frozen-parent-rollback")
    assert next(iter(parent_failed.values()))["status"] == "retained_after_failure"

    zero = copy.deepcopy(revised)
    zero["localityElections"][0]["ballotsCast"] = 0
    zero["localityElections"][0]["asOf"] = "2026-11-16T12:00:00Z"
    zero["election"]["asOf"] = "2026-11-16T12:00:00Z"
    zero_feeds, _ = collect(
        tmp_path, baseline, source_body(zero),
        prior=first, name="frozen-true-zero")
    zero_entry = next(iter(zero_feeds.values()))
    assert zero_entry["status"] == "reported"
    assert next(
        row["value"] for row in zero_entry["data"]["updates"]
        if row["native"]["source_locality_id"]
            == str(UUID(target["jurisdictionId"]))) == 0

    for ordinal, mutation in enumerate(("missing", "unknown")):
        bad = copy.deepcopy(zero)
        if mutation == "missing":
            bad["localityElections"][0].pop("ballotsCast")
        else:
            bad["localityElections"][0]["ballotsCast"] = None
        bad["localityElections"][0]["asOf"] = "2026-11-17T12:00:00Z"
        bad["election"]["asOf"] = "2026-11-17T12:00:00Z"
        retained, _ = collect(
            tmp_path, baseline, source_body(bad),
            prior=zero_feeds, name=f"frozen-{mutation}-{ordinal}")
        retained_entry = next(iter(retained.values()))
        assert retained_entry["status"] == "retained_after_failure"
        assert retained_entry["data"] == zero_entry["data"]
        assert retained_entry["source"] == zero_entry["source"]


def test_corrupt_projected_source_pin_fails_closed(tmp_path):
    feeds, _ = collect(tmp_path, full_baseline(), name="pin-first")
    after, _ = project(full_baseline(), feeds)
    rows = json.loads(gzip.decompress(after["states/RI.json.gz"]))["records"]
    rows[0]["view"]["native_record"]["private_original_pin"]["sha256"] = "0" * 64
    rows[0]["source"]["fields"] = copy.deepcopy(rows[0]["view"])
    with pytest.raises(ValueError, match="source vector"):
        adapter.validate_templates(rows)


def test_corrupt_prior_pin_query_or_update_vector_fails_closed(tmp_path):
    baseline = full_baseline()
    first, _ = collect(tmp_path, baseline, name="prior-vector-first")
    entry = next(iter(first.values()))
    cases = []
    bad_pin = copy.deepcopy(entry)
    bad_pin["source"]["sha256"] = "0" * 64
    cases.append(bad_pin)
    bad_query = copy.deepcopy(entry)
    bad_query["data"]["complete_native_query"][0][
        "source_locality_rows"][0]["ballots"] += 1
    cases.append(bad_query)
    bad_update = copy.deepcopy(entry)
    bad_update["data"]["updates"][0]["clock"] = "2026-11-15T12:00:00Z"
    cases.append(bad_update)
    for prior in cases:
        with pytest.raises(ValueError, match="Prior Rhode Island"):
            adapter.statistics(
                source_body(), copy.deepcopy(FIXTURE["templates"]),
                adapter.API_URL, prior=prior)


def test_capture_failure_retains_complete_prior_frame_without_projection(tmp_path):
    baseline = full_baseline()
    first, _ = collect(tmp_path, baseline, name="retained-first")
    after, _ = project(baseline, first)
    broken = source_document()
    broken["localityElections"][0]["ballotsCast"] = None
    failed, collector = collect(
        tmp_path, after, source_body(broken),
        prior=first, name="retained-failure")
    entry = next(iter(failed.values()))
    assert entry["status"] == "retained_after_failure"
    assert entry["error"] == "schema_or_source_semantics_changed"
    assert collector.attempts[0]["status"] == "schema_or_source_semantics_changed"
    projected, changes = project(after, failed)
    assert projected == after
    assert changes == []
