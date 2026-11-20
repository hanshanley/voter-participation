import copy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts import results_intake, results_native_congress as source, results_official_congress


def facts():
    return json.loads((Path(__file__).parent / "fixtures/virginia-federal-candidates.json").read_bytes())


def parent(value):
    root = copy.deepcopy(value["root"])
    root["jurisdiction"]["childLocalities"] = [
        {"mapFeatureId": row["code"], "shortName": row["short_name"], "id": row["id"],
         "name": [{"languageId": "en", "text": row["name"]}]} for row in value["declarations"]]
    return {
        "status": "reported", "error": None, "adapter": "reviewed_virginia_native_localities",
        "source": copy.deepcopy(value["numerical_input_manifest"]["root"]),
        "first_observed_at": "2026-11-18T23:00:00+00:00",
        "data": {"updates": [], "complete_native_query": [{
            "root_document": root, "locality_documents": copy.deepcopy(value["localities"]),
            "numerical_input_manifest": copy.deepcopy(value["numerical_input_manifest"]),
            "numerical_input_manifest_pin": copy.deepcopy(value["numerical_input_manifest_pin"]),
        }]},
    }


def revise(value, delta=None, zero=False):
    value = copy.deepcopy(value)
    race = value["root"]["ballotItems"][0]
    identity = race["summaryResults"]["ballotOptions"][-1 if zero else 0]["nativeId"]
    root_candidate = next(c for c in race["summaryResults"]["ballotOptions"] if c["nativeId"] == identity)
    root_delta = 0
    for document in value["localities"].values():
        for piece in document["ballotItems"]:
            if piece["parentId"] != race["id"]:
                continue
            row = next(c for c in piece["summaryResults"]["ballotOptions"] if c["nativeId"] == identity)
            if zero:
                root_delta -= row["voteCount"]
                piece["voteTotal"] -= row["voteCount"]
                row["voteCount"] = 0
                for mode in row["groupResults"]:
                    mode["voteCount"] = 0
            elif root_delta == 0:
                row["voteCount"] += delta
                row["groupResults"][0]["voteCount"] += delta
                piece["voteTotal"] += delta
                root_delta = delta
                root_candidate["groupResults"][0]["voteCount"] += delta
    root_candidate["voteCount"] += root_delta
    race["voteTotal"] += root_delta
    if zero:
        for mode in root_candidate["groupResults"]:
            mode["voteCount"] = 0
    return value


@pytest.mark.parametrize("delta,zero", [(0, False), (7, False), (-13, False), (None, True)])
def test_complete_native_inventory_methods_revisions_and_true_zero(delta, zero):
    original = facts()
    value = revise(original, delta, zero)
    result = source.normalized(value)
    assert len(result["races"]) == 11
    assert sum(len(row["candidates"]) for row in result["races"]) == 47
    assert sum(len(row["locality_contests"]) for row in result["races"]) == 145
    assert len({p["locality_code"] for r in result["races"] for p in r["locality_contests"]}) == 133
    assert sum(c["role"] == "generic_write_in" for r in result["races"] for c in r["candidates"]) == 11
    assert source.normalized(result["native_facts"]) == result
    entry = source.derive({source.PARENT_ID: parent(value)})[source.IDENTITY]
    assert entry["status"] == "reported" and entry["data"] == result
    assert not result["conditional_model_eligible"] and not result["provider_other_equivalence_qualified"]
    assert not result["participation_observation_qualified"]
    original_total = sum(r["voteTotal"] for r in original["root"]["ballotItems"])
    assert sum(r["contest_total"] for r in result["races"]) == original_total + (
        -original["root"]["ballotItems"][0]["summaryResults"]["ballotOptions"][-1]["voteCount"]
        if zero else delta)
    if zero:
        assert result["races"][0]["candidates"][-1]["votes"] == 0


@pytest.mark.parametrize("change", [
    "locality", "duplicate_district", "candidate", "mode", "party", "write_in",
    "total", "boolean", "negative", "primary", "production", "vote_for", "parent",
    "clock", "lineage", "language",
])
def test_changed_identity_universe_election_arithmetic_or_lineage_refuses(change):
    value = facts()
    race = value["root"]["ballotItems"][0]
    candidate = race["summaryResults"]["ballotOptions"][0]
    piece = next(p for d in value["localities"].values() for p in d["ballotItems"]
                 if p["parentId"] == race["id"])
    if change == "locality":
        value["localities"].pop(next(iter(value["localities"])))
    elif change == "duplicate_district":
        value["root"]["ballotItems"][-1] = copy.deepcopy(race)
    elif change == "candidate":
        piece["summaryResults"]["ballotOptions"][0]["name"][0]["text"] = "Different Person"
    elif change == "mode":
        candidate["groupResults"][0]["voteCount"] += 1
    elif change == "party":
        candidate["party"]["abbreviation"] = "unreviewed"
    elif change == "write_in":
        race["summaryResults"]["ballotOptions"][-1]["isWriteIn"] = False
    elif change in ("total", "boolean", "negative"):
        candidate["voteCount"] = {"total": 1, "boolean": True, "negative": -1}[change]
    elif change == "primary":
        value["root"]["election"]["isPrimary"] = True
    elif change == "production":
        value["root"]["election"]["isProduction"] = False
    elif change == "vote_for":
        race["voteFor"][0]["text"] = "Vote for two"
    elif change == "parent":
        piece["parentId"] = value["root"]["ballotItems"][1]["id"]
    elif change == "clock":
        race["reportingStatus"]["asOf"] = "not a clock"
    elif change == "lineage":
        value["numerical_input_manifest"]["localities"].pop()
    else:
        candidate["name"].append({"languageId": "en", "text": "Ambiguous"})
    with pytest.raises(ValueError):
        source.normalized(value)


def test_unchanged_failure_rollback_future_and_recovery_keep_own_last_good():
    value = facts()
    initial = {source.PARENT_ID: parent(value)}
    before = copy.deepcopy(initial)
    first = source.derive(initial)
    assert initial == before
    assert source.derive(first) == first
    for change in ("outage", "root_rollback", "local_rollback", "future", "missing_query",
                   "local_election_identity", "method_identity", "consistent_rename"):
        feeds = copy.deepcopy(first)
        p = feeds[source.PARENT_ID]
        query = p["data"]["complete_native_query"][0]
        if change == "outage":
            p.update(status="retained_after_failure", error="source_unavailable")
        elif change == "missing_query":
            p["data"]["complete_native_query"] = []
        elif change == "root_rollback":
            query["root_document"]["election"]["asOf"] = "2026-11-03T00:00:00Z"
        elif change == "local_election_identity":
            document = next(iter(query["locality_documents"].values()))
            document["election"]["id"] = "01000000-0000-0000-0000-000000000001"
            for summary in query["root_document"]["localityElections"]:
                if summary["jurisdictionId"] == document["jurisdiction"]["id"]:
                    summary["id"] = document["election"]["id"]
        elif change == "method_identity":
            query["root_document"]["ballotItems"][0]["summaryResults"]["ballotOptions"][0][
                "groupResults"][0]["groupId"] = "01000000-0000-0000-0000-000000000001"
        elif change == "consistent_rename":
            race = query["root_document"]["ballotItems"][0]
            row = race["summaryResults"]["ballotOptions"][0]
            row["name"][0]["text"] = "Consistent But Different Candidate"
            for document in query["locality_documents"].values():
                for piece in document["ballotItems"]:
                    if piece["parentId"] == race["id"]:
                        next(c for c in piece["summaryResults"]["ballotOptions"]
                             if c["nativeId"] == row["nativeId"])["name"][0]["text"] = row["name"][0]["text"]
        else:
            piece = next(x for doc in query["locality_documents"].values() for x in doc["ballotItems"])
            piece["reportingStatus"]["asOf"] = (
                "2026-11-19T00:00:00Z" if change == "future" else "2026-11-03T00:00:00Z")
        held = source.derive(feeds)[source.IDENTITY]
        assert held["status"] == "retained_after_failure", change
        assert held["data"] == first[source.IDENTITY]["data"], change
        assert held["source"] == first[source.IDENTITY]["source"], change
        assert held["first_observed_at"] == first[source.IDENTITY]["first_observed_at"]
        recovered = source.derive({source.PARENT_ID: parent(value), source.IDENTITY: held})
        assert recovered[source.IDENTITY] == first[source.IDENTITY]


def test_existing_default_collection_exports_and_literal_portable_replay(tmp_path, monkeypatch):
    from test_results_intake import fixture, unavailable
    from scripts import results_congress, results_granular

    registry = fixture(tmp_path)
    config = results_intake.read(registry)
    config["congressional"] = {"test_scope": "stub national inventory only"}
    results_intake.write(registry, config)
    results_intake.write(registry.with_name("official-congress.json"),
                         results_official_congress.ASPX_CONFIG)
    entry = parent(facts())
    calls = []

    def granular(*args, **kwargs):
        calls.append("existing_native_acquisition")
        return {source.PARENT_ID: copy.deepcopy(entry)}

    monkeypatch.setattr(results_granular, "collect", granular)
    monkeypatch.setattr(results_congress, "collect", lambda *args: {"races": {}})
    monkeypatch.setattr(results_intake.Collector, "acquire", unavailable)
    work = tmp_path / "captured"
    first = results_intake.collect(registry, work, now=datetime(2026, 11, 19, tzinfo=timezone.utc))
    state = results_intake.read(work / "state.json")
    assert calls == ["existing_native_acquisition"]
    assert state["feeds"][source.IDENTITY]["status"] == "reported"
    second = results_intake.collect(
        registry, tmp_path / "same", state, now=datetime(2026, 11, 19, tzinfo=timezone.utc))
    assert first["version"] == second["version"]
    with zipfile.ZipFile(work / "complete-results.zip") as packet:
        for name in ("scripts/results_native_congress.py", "tests/test_results_native_congress.py",
                     "tests/fixtures/virginia-federal-candidates.json"):
            assert packet.read("code/" + name) == (results_intake.ROOT / name).read_bytes()
        rows = csv.DictReader(packet.read("queries/congress-official-candidates.csv").decode().splitlines())
        assert sum(row["evidence_id"] == source.IDENTITY for row in rows) == 47
        packet.extractall(tmp_path / "extracted")
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".", "--output", "reproduced"],
        cwd=tmp_path / "extracted", capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["network_requests"] == 0


def test_selected_parent_refreshes_dependent_federal_evidence_only(tmp_path, monkeypatch):
    from scripts import results_native
    from test_results_intake import fixture, unavailable

    registry = fixture(tmp_path)
    config = results_intake.registry_config(registry)
    old = source.derive({source.PARENT_ID: parent(facts())})
    unrelated_id = "NC-registered-0000000000000000"
    old[unrelated_id] = {"status": "reported", "source": {"url": "https://example.test/other"},
                         "data": {"own_clock": "retained literal source clock"}}
    previous = {"feeds": old, "granular": {source.PARENT_ID: old[source.PARENT_ID]},
                "districts": [f"stub-{number}" for number in range(435)],
                "directories": {}, "source_stops": config["source_stops"]}
    previous["house"] = {key: {} for key in previous["districts"]}
    before = copy.deepcopy(previous)
    monkeypatch.setattr(results_native, "source_plan", lambda baseline: {"VA": {
        source.PARENT_ID: {"adapter": "reviewed_virginia_native_localities"},
        unrelated_id: {"adapter": "reviewed_north_carolina_native"}}})
    calls = []

    def collect(collector, baseline, source_ids):
        calls.append(set(source_ids))
        return {key: parent(revise(facts(), 7)) if key == source.PARENT_ID else copy.deepcopy(old[key])
                for key in source_ids}

    monkeypatch.setattr(results_native, "collect_sources", collect)
    monkeypatch.setattr(results_intake.Collector, "acquire", unavailable)
    monkeypatch.setattr(results_intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)
    selected = results_intake.refresh_selected(registry, tmp_path / "selected", previous, [source.PARENT_ID])
    assert calls == [{source.PARENT_ID}]
    assert selected["feeds"][source.IDENTITY]["data"] == source.normalized(revise(facts(), 7))
    assert selected["feeds"][unrelated_id] == old[unrelated_id]
    other = results_intake.refresh_selected(registry, tmp_path / "other", previous, [unrelated_id])
    assert calls == [{source.PARENT_ID}, {unrelated_id}]
    assert other["feeds"][source.IDENTITY] == old[source.IDENTITY]
    assert other["feeds"][source.PARENT_ID] == old[source.PARENT_ID]
    assert previous == before
