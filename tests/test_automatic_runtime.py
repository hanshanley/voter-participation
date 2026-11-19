import copy
import gzip
import io
import json
import subprocess
import sys
import zipfile

import pytest

from scripts import automatic_runtime as runtime
from scripts.participation_intake.contract import encoded, pin


def test_current_only_updates_matching_fresh_native_measure_and_preserves_every_other_frame():
    rows = [
        {"state_code": "OR", "ballots": 10, "denominator": 20,
         "denominator_basis": "active_registered_voters",
         "source_url": "https://official.test/native", "source_update_label": "old",
         "source_date": "2026-11-04", "source_retrieved_at": "old-retrieval",
         "source_sha256": "a" * 64},
        {"state_code": "NC", "ballots": 7, "source_update_label": "retained"},
    ]
    current = {"snapshot": {"reporting": rows, "demographics": [{"count": 4}], "early_voting": [5]},
               "reviewed_states": [{"untouched": True}]}
    body = gzip.compress(encoded(current), mtime=0)
    files = {"current.json.gz": body, "index.json": encoded({
        "current_snapshot": {"file": "current.json.gz", **pin(body)}})}
    original = copy.deepcopy(files)
    source = {"ballots": 11, "denominator": 20, "denominator_basis": "active_registered_voters",
              "source_update_label": "new native clock"}
    snapshot = {"jurisdictions": [
        {"state_code": "OR", "statewide_administrative_status": "reported",
         "statewide_administrative_observation": source},
        {"state_code": "NC", "statewide_administrative_status": "retained_after_failure",
         "statewide_administrative_observation": {"ballots": 999}}],
        "source_status": [{"source": "OR-official", "source_url": "https://official.test/native"}],
        "participation_observations": [{
            "channel": "OR-official", "status": "reported", "observation": source,
            "source": {"url": "https://official.test/native", "sha256": "b" * 64}}]}
    result = runtime.refresh_current(files, snapshot)
    updated = json.loads(gzip.decompress(result["current.json.gz"]))
    assert files == original
    assert updated["snapshot"]["reporting"][0]["ballots"] == 11
    assert updated["snapshot"]["reporting"][0]["source_update_label"] == "new native clock"
    assert updated["snapshot"]["reporting"][0]["source_sha256"] == "b" * 64
    assert updated["snapshot"]["reporting"][0]["source_retrieved_at"] is None
    assert updated["snapshot"]["reporting"][0]["source_date"] is None
    assert updated["snapshot"]["reporting"][0]["accepted_source_provenance"][
        "source_retrieved_at"] == "old-retrieval"
    assert updated["snapshot"]["reporting"][1] == rows[1]
    assert updated["snapshot"]["early_voting"] == current["snapshot"]["early_voting"]
    assert updated["snapshot"]["demographics"] == current["snapshot"]["demographics"]
    assert updated["reviewed_states"] == current["reviewed_states"]
    assert runtime.refresh_current(result, snapshot) == result
    snapshot["jurisdictions"][0]["statewide_administrative_observation"]["denominator_basis"] = "different_stock"
    assert runtime.refresh_current(files, snapshot) == files


@pytest.mark.parametrize("ballots", [11, 0])
def test_reviewed_state_mirror_follows_exact_canonical_successor(ballots):
    row = {
        "state_code": "DE", "year": 2026, "mode": "official", "ballots": 10,
        "denominator": 20, "validated_pct": 50,
        "maps_approved": False, "source_update_label": "Native clock not supplied",
        "source_url": "https://official.test/turnout.json",
        "native_record": {"query": {"ballots_cast": 10}},
    }
    record = {
        "id": "reviewed-state", "geography": {"level": "state", "state_code": "DE"},
        "election": {"year": 2026}, "measure": {"literal": "Ballots Cast"},
        "view": row,
    }
    current = {"reviewed_states": [row, {"state_code": "GA", "ballots": 7}],
               "snapshot": {"reporting": [], "early_voting": [{"ballots": 2}]}}
    old_body = gzip.compress(encoded({"records": [record], "views": {}}), mtime=0)
    body = gzip.compress(encoded(current), mtime=0)
    files = {"current.json.gz": body, "states/DE.json.gz": old_body, "index.json": encoded({
        "current_snapshot": {"file": "current.json.gz", **pin(body)},
        "states": {"DE": {"file": "states/DE.json.gz", **pin(old_body)}}})}
    successor = copy.deepcopy(record)
    successor["view"].update(ballots=ballots, validated_pct=100 * ballots / 20,
                             automatic_source_refresh=True, source_sha256="b" * 64)
    successor["view"]["native_record"]["query"]["ballots_cast"] = ballots
    after = dict(files)
    after["states/DE.json.gz"] = gzip.compress(
        encoded({"records": [successor], "views": {}}), mtime=0)
    unchanged = copy.deepcopy(files)
    snapshot = {"jurisdictions": [], "source_status": []}

    result = runtime.refresh_current(after, snapshot, previous_files=files)
    visible = json.loads(gzip.decompress(result["current.json.gz"]))
    assert visible["reviewed_states"][0] == successor["view"]
    assert visible["reviewed_states"][1] == current["reviewed_states"][1]
    assert visible["snapshot"] == current["snapshot"]
    assert visible["reviewed_states"][0]["maps_approved"] is False
    assert visible["reviewed_states"][0]["source_update_label"] == "Native clock not supplied"
    assert files == unchanged
    assert runtime.refresh_current(result, snapshot, previous_files=result) == result
    assert runtime.refresh_current(files, snapshot, previous_files=files) == files

    stale = copy.deepcopy(current)
    stale["reviewed_states"][0]["ballots"] = 9
    mismatch = dict(after, **{"current.json.gz": gzip.compress(encoded(stale), mtime=0)})
    assert runtime.refresh_current(mismatch, snapshot, previous_files=files) == mismatch
    corrupt = copy.deepcopy(successor)
    corrupt["geography"]["level"] = "county"
    invalid = dict(after)
    invalid["states/DE.json.gz"] = gzip.compress(
        encoded({"records": [corrupt], "views": {}}), mtime=0)
    with pytest.raises(ValueError, match="reviewed statewide mirror"):
        runtime.refresh_current(invalid, snapshot, previous_files=files)


def test_full_archive_is_deterministic_and_never_just_a_pointer():
    members = {"inputs/native-query.csv": b"county,count\nA,0\n",
               "queries/result.json": b'{"value":0}\n', "code/reproduce.py": b"print(0)\n"}
    body = runtime.archive_bytes(members)
    assert body == runtime.archive_bytes(dict(reversed(list(members.items()))))
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("checksums.json"))
        assert manifest == {name: pin(value) for name, value in members.items()}
        assert all(archive.read(name) == value for name, value in members.items())
    with pytest.raises(ValueError, match="Unsafe"):
        runtime.archive_bytes({"../outside": b"not allowed"})


def test_state_only_statistics_refresh_does_not_leave_old_numeric_query_or_invent_clock():
    from scripts import results_state_statistics as state

    text = ("<h1>" + state.TITLE + "</h1><p>" + state.HEADING + "</p>"
            "<p>Early Voting Turnout: 0 (0.0%)</p><p>Absentee Voting: 2 (40.0%)</p>"
            "<p>Election Day Turnout: 3 (60.0%)</p><p>Total Voter Turnout: 5</p>"
            "<p>Turnout of Active Registered Voters: 59.8%</p>")
    data = state.statistics(text.encode(), "SC")
    old = {
        "state_code": "SC", "county_id": "native:SC:statewide", "geography_level": "statewide",
        "mode": "official", "source_url": state.URL, "ballots": 4,
        "participation_measure_kind": "source_defined_participation_count",
        "cast_ballot_count_qualified": False, "unique_voter_count_qualified": False,
        "maps_approved": False, "denominator": None, "denominator_basis": state.BASIS,
        "native_statistics": {"retained_original": 4}}
    current = {"snapshot": {"reporting": [old, {"state_code": "ND", "ballots": 7}],
                            "early_voting": [{"state_code": "SC", "ballots": 2}]}}
    body = gzip.compress(encoded(current), mtime=0)
    files = {"current.json.gz": body, "index.json": encoded({
        "current_snapshot": {"file": "current.json.gz", **pin(body)}})}
    original = copy.deepcopy(files)
    snapshot = {
        "jurisdictions": [{"state_code": "SC", "statewide_administrative_status": "reported",
                          "statewide_administrative_observation": data}],
        "source_status": [{"source": "SC-official", "source_url": state.URL}],
        "participation_observations": [{"channel": "SC-official", "status": "reported",
            "observation": data, "source": {"url": state.URL, "sha256": "b" * 64}}]}
    result = runtime.refresh_current(files, snapshot)
    changed = json.loads(gzip.decompress(result["current.json.gz"]))
    row = changed["snapshot"]["reporting"][0]
    assert row["ballots"] == row["native_statistics"]["fields"]["total"]["value"] == 5
    assert row["native_statistics"]["fields"]["early"]["value"] == 0
    assert row["accepted_source_provenance"]["native_statistics"] == {"retained_original": 4}
    assert row["denominator"] is row["reported_pct"] is row["source_update_label"] is None
    assert row["maps_approved"] is row["unique_voter_count_qualified"] is False
    assert changed["snapshot"]["reporting"][1] == current["snapshot"]["reporting"][1]
    assert changed["snapshot"]["early_voting"] == current["snapshot"]["early_voting"]
    assert files == original
    assert runtime.refresh_current(result, snapshot) == result
    snapshot["jurisdictions"][0]["statewide_administrative_status"] = "retained_after_failure"
    assert runtime.refresh_current(files, snapshot) == files


def granular_reference_fixture():
    update = {"id": "synthetic-observation", "value": 0}
    full_entry = {
        "status": "reported",
        "adapter": "reviewed_test",
        "source": {"url": "https://official.test/native", "bytes": 7, "sha256": "a" * 64},
        "data": {
            "updates": [update],
            "geographic_joins_changed": False,
            "numerical_data_qualified": False,
        },
    }
    full = {"AZ-native": full_entry}
    body = gzip.compress(encoded(full), mtime=0)
    reference = {
        "file": "granular-source-queries.json.gz", **pin(body),
        "key": "AZ-native",
        "qualification": "Exact full native query and replay updates retained externally.",
    }
    compact = {
        key: copy.deepcopy(value) for key, value in full_entry.items() if key != "data"
    }
    compact["data"] = {
        "summary": {
            "geographic_joins_changed": False,
            "numerical_data_qualified": False,
            "projected_updates": {
                "records": 1, "reported": 1, "unknown": 0,
                "observation_ids_pin": runtime.digest(encoded(["synthetic-observation"])),
            },
        },
        "full_data": reference,
    }
    snapshot = {"granular_sources": {"AZ-native": compact}}
    packet = runtime.archive_bytes({"queries/granular-source-queries.json.gz": body})
    return snapshot, packet, full


def test_checksum_bound_granular_hydration_restores_exact_full_updates():
    snapshot, packet, full = granular_reference_fixture()
    hydrated = runtime.hydrate_granular_sources(snapshot, packet)
    assert hydrated is not snapshot
    assert hydrated["granular_sources"] == full
    assert snapshot["granular_sources"]["AZ-native"]["data"].get("updates") is None
    assert runtime.hydrate_granular_sources(hydrated, None) is hydrated


@pytest.mark.parametrize("change", [None, "reference", "summary", "source", "missing_granular"])
def test_externalized_observation_restores_full_query_and_rejects_mismatched_mirrors(change):
    snapshot, packet, full = granular_reference_fixture()
    compact = snapshot["granular_sources"]["AZ-native"]["data"]
    snapshot["participation_observations"] = [{
        "state_code": "AZ", "channel": "AZ-native",
        "status": full["AZ-native"]["status"],
        "source": copy.deepcopy(full["AZ-native"]["source"]),
        "observation": {
            "contract": "participation.externalized_native_query.v1",
            "summary": copy.deepcopy(compact["summary"]),
            "full_data": {
                **compact["full_data"],
                "qualification": (
                    "Lossless exact native data externalized from the bounded snapshot."),
            },
        },
    }]
    observation = snapshot["participation_observations"][0]
    if change == "reference":
        observation["observation"]["full_data"]["sha256"] = "b" * 64
    elif change == "summary":
        observation["observation"]["summary"]["projected_updates"]["records"] = 2
    elif change == "source":
        observation["source"]["sha256"] = "b" * 64
    elif change == "missing_granular":
        snapshot["granular_sources"] = {}
    if change:
        with pytest.raises(ValueError, match="Externalized"):
            runtime.hydrate_granular_sources(snapshot, packet)
    else:
        before = copy.deepcopy(snapshot)
        hydrated = runtime.hydrate_granular_sources(snapshot, packet)
        assert hydrated["participation_observations"][0]["observation"] == full["AZ-native"]["data"]
        assert snapshot == before
        assert runtime.hydrate_granular_sources(hydrated, None) is hydrated


@pytest.mark.parametrize("change", ["missing_packet", "wrong_hash", "wrong_key", "wrong_summary"])
def test_granular_hydration_refuses_missing_or_changed_replay_data(change):
    snapshot, packet, _ = granular_reference_fixture()
    if change == "missing_packet":
        packet = runtime.archive_bytes({"queries/other.json.gz": gzip.compress(b"{}\n")})
    elif change == "wrong_hash":
        snapshot["granular_sources"]["AZ-native"]["data"]["full_data"]["sha256"] = "b" * 64
    elif change == "wrong_key":
        snapshot["granular_sources"]["AZ-native"]["data"]["full_data"]["key"] = "other"
    else:
        snapshot["granular_sources"]["AZ-native"]["data"]["summary"][
            "projected_updates"]["records"] = 2
    with pytest.raises(ValueError, match="granular|Granular|source packet"):
        runtime.hydrate_granular_sources(snapshot, packet)


@pytest.mark.parametrize("runtime_declaration", ["legacy", "matching", "different"])
def test_literal_extracted_runtime_replay_hydrates_before_actual_producer_call(
        monkeypatch, tmp_path, runtime_declaration):
    from scripts import automatic_estimates

    snapshot, source_packet, full = granular_reference_fixture()
    package = tmp_path / "packet"
    output = tmp_path / "output"
    seed = gzip.compress(b"{}\n", mtime=0)
    members = {
        "inputs/snapshot.json": encoded(snapshot),
        "inputs/complete-source-results.zip": source_packet,
        "inputs/before-counts/index.json": b"before-counts",
        "inputs/before-native/index.json": b"before-native",
        "inputs/model-seed/rolling-seed.json.gz": seed,
        "inputs/model-seed/rolling-seed-descriptor.json": encoded({"synthetic": True}),
        "queries/after-counts/index.json": b"after-counts",
        "queries/after-native/index.json": b"after-native",
        "queries/model-queries/result.json": b"model-result",
    }
    if runtime_declaration != "legacy":
        declaration = runtime.numerical_runtime()
        if runtime_declaration == "different":
            declaration["python_major_minor"] = [0, 0]
        members["inputs/numerical-runtime.json"] = encoded(declaration)
    for name, body in members.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    (package / "checksums.json").write_bytes(encoded(
        {name: pin(body) for name, body in members.items()}))
    monkeypatch.setattr(automatic_estimates, "load_rolling_seed_bytes",
                        lambda body, declaration: {"seed": True})
    observed = {}

    def compile_runtime(snapshot, counts, native, seed, packet):
        observed.update(snapshot=snapshot, counts=counts, native=native, seed=seed, packet=packet)
        return {
            "counts": {"index.json": b"after-counts"},
            "native": {"index.json": b"after-native"},
            "model_files": {"result.json": b"model-result"},
            "local_changes": [{"id": "synthetic-observation"}],
        }

    monkeypatch.setattr(runtime, "compile_runtime", compile_runtime)
    if runtime_declaration == "different":
        with pytest.raises(ValueError, match="producer's Python"):
            runtime.replay(package, output)
        assert not observed and not output.exists()
        return
    result = runtime.replay(package, output)
    assert result == {
        "passed": True, "complete_outputs": 3,
        "network_requests": 0, "external_operations_blocked": True,
    }
    assert observed["snapshot"]["granular_sources"] == full
    assert observed["packet"] == source_packet
    assert observed["seed"] == {"seed": True}
    assert (output / "queries/after-counts/index.json").read_bytes() == b"after-counts"


def native_refresh_fixture(family=False, maps_approved=False):
    from scripts import automatic_native_refresh as native_refresh

    source_id = (native_refresh.REVIEWED_FAMILY_SOURCE_IDS["WY"]
                 if family else "ordinary-approved-native-source")

    def row(ballots, url, sha, vector):
        status = "unknown" if ballots is None else "reported"
        view = {
            "state_code": "WY", "key": "WY|unit", "unit": "UNIT",
            "maps_approved": maps_approved, "ballots": ballots,
            "denominator": 10, "registered": 10, "reported_pct": None,
            "source_url": url, "native_record": {
                "native_original_pin": {"bytes": 7, "sha256": sha},
                "vector": {"other": vector},
            },
        }
        return {
            "id": "observation",
            "count": {"value": ballots, "literal": ballots, "status": status},
            "denominator": {"value": 10, "literal": "registered",
                            "basis": "registered", "qualified": False},
            "election": {"id": "general-2026", "year": 2026,
                         "date": "2026-11-03", "type": "general",
                         "qualification": "native"},
            "geography": {
                "id": "WY-unit", "name": "UNIT", "state_code": "WY",
                "level": "reporting_unit", "parent_id": "WY-parent",
                "join": {"status": "unreviewed", "reference_id": None,
                         "feature_key": None, "evidence": "synthetic"}},
            "measure": {"id": "native-count", "literal": "Native count",
                        "kind": "participation_reported", "mode": "source_defined",
                        "unit": "source_count"},
            "reporting_status": {"literal": None, "reported_units": None,
                                 "total_units": None, "complete": None},
            "source_clock": {"literal": None, "timezone": None,
                             "qualification": "native_clock_not_supplied"},
            "quality": {"notes": ["held"], "conflicts": []},
            "source": {"id": source_id, "input_sha256": sha, "url": url,
                       "classification": "public_aggregate",
                       "selector": {"frame": vector}, "fields": copy.deepcopy(view)},
            "view": view,
        }

    before_row = row(None, "https://official.test/prior", "a" * 64, 1)
    after_row = row(0, "https://official.test/current", "b" * 64, 2)

    def files(value):
        body = gzip.compress(encoded({
            "contract": "participation.count_snapshot.v1",
            "state_code": "WY", "records": [value]}), mtime=0)
        return {"index.json": encoded({
            "contract": "participation.count_index.v1", "year": 2026,
            "states": {"WY": {"file": "states/WY.json.gz", **pin(body)}}}),
            "states/WY.json.gz": body}

    native_observation = copy.deepcopy(before_row)
    native_observation["source"]["fields"] = copy.deepcopy(native_observation["view"])
    source_value = [{
        "state_code": "WY", "key": "WY|unit", "unit": "UNIT",
        "maps_approved": maps_approved, "ballots": None, "registered": 10,
        "reported_pct": None, "source_url": "https://official.test/prior",
        "native_record": copy.deepcopy(before_row["view"]["native_record"]),
    }]
    table_value = {"contract": "participation.reporting_units.v1", "state_code": "WY",
                   "records": [{"observation": native_observation,
                                "properties": copy.deepcopy(source_value[0])}]}
    table = gzip.compress(encoded(table_value), mtime=0)
    source = gzip.compress(encoded(source_value), mtime=0)
    native = {
        "index.json": encoded({
            "contract": "participation.native_index.v1", "year": 2026,
            "reporting_tables": {"WY": {
                "file": "tables/WY.json.gz", "rows": 1, **pin(table)}},
            "reporting_sources": {"WY": {"rows": 1, "sha256": pin(source)["sha256"]}},
        }),
        "tables/WY.json.gz": table,
        "source-reporting/WY.json.gz": source,
    }
    return files(before_row), files(after_row), native


def repin_native(native, table_value=None, source_value=None):
    result = copy.deepcopy(native)
    index = json.loads(result["index.json"])
    if table_value is not None:
        body = gzip.compress(encoded(table_value), mtime=0)
        result["tables/WY.json.gz"] = body
        index["reporting_tables"]["WY"].update(pin(body))
    if source_value is not None:
        body = gzip.compress(encoded(source_value), mtime=0)
        result["source-reporting/WY.json.gz"] = body
        index["reporting_sources"]["WY"]["rows"] = len(source_value)
        index["reporting_sources"]["WY"]["sha256"] = pin(body)["sha256"]
    result["index.json"] = encoded(index)
    return result


def state_row(files):
    return json.loads(gzip.decompress(files["states/WY.json.gz"]))["records"][0]


def native_rows(files):
    table = json.loads(gzip.decompress(files["tables/WY.json.gz"]))
    source = json.loads(gzip.decompress(files["source-reporting/WY.json.gz"]))
    return table["records"][0]["observation"], source[0]


def test_original_ordinary_approved_native_refresh_remains_unchanged():
    from scripts import automatic_native_refresh as native_refresh

    before, after, native = native_refresh_fixture(maps_approved=True)
    result = native_refresh.refresh(before, after, native)
    observation, source = native_rows(result)
    assert observation == state_row(after)
    assert source["ballots"] == 0
    assert source["registered"] == 10
    assert source["maps_approved"] is True
    assert native_refresh.refresh(after, after, result) == result


def test_reviewed_family_bridge_synchronizes_true_zero_repeat_and_second_successor():
    from scripts import automatic_native_refresh as native_refresh

    before, after, native = native_refresh_fixture(family=True)
    result = native_refresh.refresh(before, after, native)
    observation, source = native_rows(result)
    successor = state_row(after)
    assert observation["count"] == successor["count"]
    assert observation["source"]["input_sha256"] == "b" * 64
    assert observation["source"]["url"] == "https://official.test/current"
    assert observation["view"]["native_record"] == successor["view"]["native_record"]
    assert source["ballots"] == 0
    assert source["registered"] == 10
    assert source["native_record"] == successor["view"]["native_record"]
    assert native_refresh.refresh(after, after, result) == result

    second_row = copy.deepcopy(successor)
    second_row["count"] = {"value": 3, "literal": 3, "status": "reported"}
    second_row["view"].update(ballots=3, source_url="https://official.test/second")
    second_row["view"]["native_record"] = {
        "native_original_pin": {"bytes": 7, "sha256": "c" * 64},
        "vector": {"other": 3},
    }
    second_row["source"].update(input_sha256="c" * 64,
                                url="https://official.test/second",
                                selector={"frame": 3})
    second_row["source"]["fields"] = copy.deepcopy(second_row["view"])
    second = copy.deepcopy(after)
    body = gzip.compress(encoded({"contract": "participation.count_snapshot.v1",
                                  "state_code": "WY", "records": [second_row]}), mtime=0)
    second["states/WY.json.gz"] = body
    index = json.loads(second["index.json"])
    index["states"]["WY"].update(pin(body))
    second["index.json"] = encoded(index)
    advanced = native_refresh.refresh(after, second, result)
    advanced_observation, advanced_source = native_rows(advanced)
    assert advanced_observation["count"]["value"] == 3
    assert advanced_observation["source"]["input_sha256"] == "c" * 64
    assert advanced_source["ballots"] == 3
    assert advanced_source["registered"] == 10
    assert native_refresh.refresh(second, second, advanced) == advanced


def test_family_source_rows_may_omit_the_observations_display_unit():
    from scripts import automatic_native_refresh as native_refresh

    before, after, native = native_refresh_fixture(family=True)
    table = json.loads(gzip.decompress(native["tables/WY.json.gz"]))
    source = json.loads(gzip.decompress(native["source-reporting/WY.json.gz"]))
    table["records"][0]["properties"].pop("unit")
    source[0].pop("unit")
    native = repin_native(native, table_value=table, source_value=source)
    result = native_refresh.refresh(before, after, native)
    observation, source = native_rows(result)
    assert observation["view"]["unit"] == "UNIT"
    assert observation["count"]["value"] == source["ballots"] == 0
    assert "unit" not in source


@pytest.mark.parametrize("state", ["AR", "AZ"])
def test_family_tables_with_external_legacy_sources_need_no_separate_source_file(state):
    from scripts import automatic_native_refresh as native_refresh

    before, after, native = native_refresh_fixture(family=True)

    def restate(observation):
        observation["geography"]["state_code"] = state
        observation["view"].update(state_code=state, key=state + "|unit")
        observation["source"]["id"] = native_refresh.REVIEWED_FAMILY_SOURCE_IDS[state]
        observation["source"]["fields"] = copy.deepcopy(observation["view"])
        return observation

    def canonical(files):
        observation = restate(state_row(files))
        name = "states/" + state + ".json.gz"
        body = gzip.compress(encoded({
            "contract": "participation.count_snapshot.v1",
            "state_code": state, "records": [observation],
        }), mtime=0)
        return {name: body, "index.json": encoded({
            "contract": "participation.count_index.v1", "year": 2026,
            "states": {state: {"file": name, **pin(body)}},
        })}

    table = json.loads(gzip.decompress(native["tables/WY.json.gz"]))
    table["state_code"] = state
    table["records"][0]["observation"] = restate(table["records"][0]["observation"])
    table["records"][0]["properties"].update(state_code=state, key=state + "|unit")
    name = "tables/" + state + ".json.gz"
    body = gzip.compress(encoded(table), mtime=0)
    native = {name: body, "index.json": encoded({
        "contract": "participation.native_index.v1", "year": 2026,
        "reporting_tables": {state: {"file": name, "rows": 1, **pin(body)}},
        "reporting_sources": {state: {
            "rows": 1, "data_url": "/retained/" + state + ".json.gz",
            "sha256": "a" * 64,
        }},
    })}
    result = native_refresh.refresh(canonical(before), canonical(after), native)
    observation = json.loads(gzip.decompress(result[name]))["records"][0]["observation"]
    assert observation["count"]["value"] == 0
    assert observation["source"]["input_sha256"] == "b" * 64
    assert "source-reporting/" + state + ".json.gz" not in result


@pytest.mark.parametrize("change", [
    "maps", "unit", "duplicate_key", "missing_key", "missing_file",
    "vector", "source_pin", "selector",
])
def test_reviewed_family_bridge_fails_closed_for_corruption(change):
    from scripts import automatic_native_refresh as native_refresh

    before, after, native = native_refresh_fixture(family=True)
    if change == "missing_file":
        native.pop("source-reporting/WY.json.gz")
    elif change in ("maps", "unit", "source_pin", "selector"):
        source_rows = None
        table = json.loads(gzip.decompress(native["tables/WY.json.gz"]))
        observation = table["records"][0]["observation"]
        if change == "maps":
            observation["view"]["maps_approved"] = True
            observation["source"]["fields"] = copy.deepcopy(observation["view"])
            table["records"][0]["properties"]["maps_approved"] = True
        elif change == "unit":
            observation["view"]["unit"] = "CHANGED"
            observation["source"]["fields"] = copy.deepcopy(observation["view"])
            table["records"][0]["properties"]["unit"] = "CHANGED"
            source_rows = json.loads(gzip.decompress(native["source-reporting/WY.json.gz"]))
            source_rows[0]["unit"] = "CHANGED"
        else:
            if change == "source_pin":
                observation["source"]["input_sha256"] = "d" * 64
            else:
                observation["source"]["selector"] = {"changed": True}
        native = repin_native(native, table_value=table, source_value=source_rows)
    else:
        values = json.loads(gzip.decompress(native["source-reporting/WY.json.gz"]))
        if change == "duplicate_key":
            values.append(copy.deepcopy(values[0]))
        elif change == "missing_key":
            values = []
        else:
            values[0]["native_record"]["vector"]["other"] = 999
        native = repin_native(native, source_value=values)
    with pytest.raises(ValueError):
        native_refresh.refresh(before, after, native)


def test_successor_descriptor_does_not_inherit_the_previous_publication_origin():
    before = {"contract": "participation.dataset.v1", "record_contract": "count-contract",
              "id": "test", "version": "old", "base_url": "https://old.test/",
              "staged_commit": "old", "status": "loaded"}
    descriptor = runtime.descriptor(before, {"index.json": b"{}\n"})
    assert all(key not in descriptor for key in ("base_url", "staged_commit", "status"))
    assert descriptor["version"] != "old"
    assert before["staged_commit"] == "old"


def test_untrusted_or_changed_public_body_is_refused_before_any_source_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted transport was opened")
    monkeypatch.setattr(runtime.urllib.request, "urlopen", forbidden)
    for url in ("http://raw.githubusercontent.com/hanshanley/voter-participation/a",
                "https://official.test/data", "https://raw.githubusercontent.com/other/repo/a"):
        with pytest.raises(ValueError, match="two public"):
            runtime.fetch(url)
    with pytest.raises(ValueError, match="declaration"):
        runtime.fetch(runtime.RESULTS_POINTER, {"bytes": True, "sha256": "a" * 64})


def test_result_pointer_cannot_redirect_pinned_queries_to_another_commit(monkeypatch):
    pointer = {"contract": "participation.automatic_results_latest.v1", "version": "a" * 64,
               "results_commit": "b" * 40,
               "base_url": "https://raw.githubusercontent.com/hanshanley/voter-participation/main/"}
    monkeypatch.setattr(runtime, "fetch", lambda *args, **kwargs: encoded(pointer))
    with pytest.raises(ValueError, match="exact immutable"):
        runtime.results(runtime.RESULTS_POINTER)


def test_safe_seed_inventory_never_packages_unlisted_local_files(tmp_path):
    source = runtime.ROOT / "data/results-intake/model-seed"
    for name, body in runtime.seed_files(source).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    (tmp_path / "private-unlisted.json").write_text('{"do_not_publish":true}')
    members = runtime.seed_files(tmp_path)
    assert len(members) == 25
    assert "private-unlisted.json" not in members
    manifest = json.loads(members["manifest.json"])
    manifest["accepted_candidates"]["path"] = "../outside.json"
    (tmp_path / "manifest.json").write_bytes(encoded(manifest))
    with pytest.raises(ValueError, match="Unsafe"):
        runtime.seed_files(tmp_path)


def test_missing_or_unpinned_rolling_seed_never_falls_back_to_original(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A previous publication must never reset to bootstrap")
    monkeypatch.setattr(runtime, "seed_files", forbidden)
    monkeypatch.setattr(runtime, "fetch", forbidden)
    for previous in (
        {}, {"contract": runtime.CONTRACT},
        {"contract": runtime.CONTRACT, "version": "a" * 64, "house_sources": {"next_seed": {
            "path": "rolling/next-seed.json.gz", "url": runtime.RESULTS_POINTER}}},
    ):
        with pytest.raises(ValueError):
            runtime.select_seed(previous, "not-used")


def test_verified_rolling_seed_is_the_exact_input_retained_for_replay(monkeypatch):
    from scripts import automatic_estimates
    body = gzip.compress(b'{"newest_accepted":true}\n', mtime=0)
    version = "a" * 64
    item = {"path": "rolling/next-seed.json.gz", **pin(body),
            "url": ("https://raw.githubusercontent.com/" + runtime.WEBSITE_REPOSITORY
                    + "/" + "b" * 40 + "/automatic/versions/" + version
                    + "/rolling/next-seed.json.gz")}
    previous = {"contract": runtime.CONTRACT, "version": version,
                "house_sources": {"next_seed": item}}
    monkeypatch.setattr(runtime, "fetch", lambda *args, **kwargs: body)
    marker = {"last_good_not_original": True}
    monkeypatch.setattr(automatic_estimates, "load_rolling_seed_bytes",
                        lambda value, declaration: marker if value == body and declaration == item else None)
    selected, members = runtime.select_seed(previous, "not-used")
    assert selected is marker
    assert members == {"rolling-seed.json.gz": body, "rolling-seed-descriptor.json": encoded(item)}
    monkeypatch.setattr(runtime, "fetch", lambda *args, **kwargs: body + b"changed")
    with pytest.raises(ValueError, match="Changed rolling"):
        runtime.select_seed(previous, "not-used")


def test_unchanged_dataset_keeps_its_values_but_shares_the_atomic_publication_origin():
    identities = ("participation-counts-2026", "participation-native-bindings-2026")
    catalog = {"datasets": {identity: {
        "id": identity, "version": "a" * 64, "files": {"index.json": pin(b"{}\n")},
        "base_url": "old-origin", "complete_download": {"old_complete": True},
    } for identity in identities}, "unrelated": {"preserved": True}}
    original = copy.deepcopy(catalog)
    changed = {**catalog["datasets"][identities[0]], "version": "c" * 64}
    result, checks = runtime.bind_datasets(catalog, {identities[0]: changed},
                                         "b" * 40, runtime.WEBSITE_REPOSITORY)
    assert catalog == original
    assert result["unrelated"] == original["unrelated"]
    for identity in identities:
        row = result["datasets"][identity]
        assert "/" + "b" * 40 + "/" in row["base_url"]
        assert row["staged_commit"] == "b" * 40
        assert row["complete_download"] == {"old_complete": True}
        assert "datasets/" + identity + "/" + row["version"] + "/index.json" in checks
    assert result["datasets"][identities[1]]["version"] == "a" * 64


def test_complete_packet_includes_accepted_numerical_engine_and_only_selected_seed_bytes(tmp_path):
    seed = {"rolling-seed.json.gz": b"full-public-aggregate-seed"}
    compiled = {"counts": {"index.json": b"count-query"}, "native": {"index.json": b"native-query"},
                "model_files": {"all-nine-results.json.gz": b"complete-model-queries"}}
    packet = runtime.scientific_package({}, b"full-source-packet", {}, {}, seed, compiled)
    with zipfile.ZipFile(io.BytesIO(packet)) as archive:
        runtime.packet_manifest(archive)
        assert archive.read("code/scripts/norc_house_model.py") == (
            runtime.ROOT / "scripts/norc_house_model.py").read_bytes()
        assert archive.read("code/scripts/results_json_congress.py") == (
            runtime.ROOT / "scripts/results_json_congress.py").read_bytes()
        assert {name for name in archive.namelist() if name.startswith("inputs/model-seed/")} == {
            "inputs/model-seed/rolling-seed.json.gz"}
        assert archive.read("queries/model-queries/all-nine-results.json.gz") == b"complete-model-queries"
        assert json.loads(archive.read("inputs/numerical-runtime.json")) == runtime.numerical_runtime()
        assert b"code/reproduce.py --replay-package . --output reproduced" in archive.read("REPRODUCE.txt")
        archive.extractall(tmp_path)
    subprocess.run([sys.executable, "-E", "-c",
                    "import sys; sys.path.insert(0, 'code'); "
                    "from scripts import statewide_ballot_totals, supported_analytical_release"],
                   cwd=tmp_path, check=True)


@pytest.fixture
def publication(monkeypatch, tmp_path):
    class Publisher:
        def __init__(self):
            self.head = "a" * 40
            self.objects = {self.head: {"catalog.json": encoded({"datasets": {
                name: {"id": name, "version": "b" * 64, "record_contract": name,
                       "files": {"index.json": pin(b"{}\n")}, "complete_download": {"old": True}}
                for name in ("participation-counts-2026", "participation-native-bindings-2026")
            }})}}
            self.objects[self.head].update({
                f"datasets/{name}/{'b' * 64}/index.json": b"{}\n"
                for name in ("participation-counts-2026", "participation-native-bindings-2026")
            })
            self.promotions = 0
            self.compilations = 0
            self.releases = 0
            self.interrupt = None
            self.parents = {}

        def remote_head(self):
            return self.head

        def fetch_parent(self, parent):
            assert parent in self.objects

        def catalog(self, parent):
            return json.loads(self.objects[parent]["catalog.json"])

        def git(self, operation, target, check=False):
            assert operation == "show"
            commit, path = target.split(":", 1)
            return self.objects[commit].get(path, b"").decode()

        def tree(self, parent, bodies):
            return {**self.objects[parent], **bodies}

        def commit(self, tree, parent, message):
            identity = runtime.digest(encoded({
                "parent": parent, "files": {name: pin(body) for name, body in tree.items()}}))[:40]
            self.objects[identity] = tree
            self.parents[identity] = parent
            return identity

        def parent_of(self, commit):
            return self.parents[commit]

        def promote(self, commit, expected):
            if self.head != expected:
                raise ValueError("Concurrent publication")
            self.head = commit
            self.promotions += 1

        def verify_files(self, commit, files):
            for name, expected in files.items():
                assert pin(self.objects[commit][name]) == expected
            phase = "activation" if "automatic/latest.json" in files else "staging"
            if self.interrupt == phase:
                self.interrupt = None
                raise OSError("Interrupted " + phase + " verification")

    publisher = Publisher()
    monkeypatch.setattr(runtime, "GitPublisher", lambda *args, **kwargs: publisher)
    pointer = {"version": "f" * 64, "checked_at": "2026-11-14T16:00:00+00:00"}
    monkeypatch.setattr(runtime, "results_pointer", lambda _: pointer)
    monkeypatch.setattr(runtime, "result_bodies", lambda _: (
        {}, {"complete-results.zip": b"full-source-packet"}))
    monkeypatch.setattr(runtime, "dataset_files", lambda _: {"index.json": b"{}\n"})
    monkeypatch.setattr(runtime, "seed_files", lambda _: {"manifest.json": b"safe"})
    monkeypatch.setattr(runtime, "select_seed", lambda *args: ({}, {}))

    def compile_snapshot(*args):
        publisher.compilations += 1
        return {"counts": {"index.json": b'{"changed":true}\n'},
                "native": {"index.json": b"{}\n"}, "estimates": {"house_sources": {}},
                "model_files": {"all-results.json.gz": b"complete-public-queries"},
                "local_changes": []}
    monkeypatch.setattr(runtime, "compile_runtime", compile_snapshot)
    proof = {"passed": True, "network_requests": 0, "external_operations_blocked": True,
             "complete_outputs": 3}

    def package(*args):
        return runtime.archive_bytes({"code/reproduce.py": (
            "import json\nprint(json.dumps(" + repr(proof) + "))\n").encode()})
    monkeypatch.setattr(runtime, "scientific_package", package)

    def release(repository, version, path, journal, checkpoint):
        if not journal.get("release_id"):
            publisher.releases += 1
            journal["release_id"] = publisher.releases
            checkpoint()
        return {"url": "https://github.com/" + repository + "/releases/download/unit/complete-analysis.zip",
                **pin(path.read_bytes()), "immutable": True, "verified_anonymously": True}
    monkeypatch.setattr(runtime, "complete_release", release)
    from scripts import automatic_estimates
    monkeypatch.setattr(automatic_estimates, "bind_publication",
                        lambda result, base, download: {"house_sources": {"base_url": base}})
    return publisher, tmp_path / "work", proof


@pytest.mark.parametrize("interrupt", [None, "staging", "activation"])
def test_publication_resume_and_unchanged_input_do_not_reset_or_duplicate_activation(
        publication, interrupt, monkeypatch):
    publisher, work, _ = publication
    original_catalog = publisher.catalog(publisher.head)
    publisher.interrupt = interrupt
    if interrupt:
        with pytest.raises(OSError, match="Interrupted"):
            runtime.run("not-used", work)
        if interrupt == "staging":
            assert publisher.catalog(publisher.head) == original_catalog
            assert "automatic/latest.json" not in publisher.objects[publisher.head]
        # A fresh Actions runner has no checkout-local work directory or journal.
        work = work.with_name("fresh-runner")
        monkeypatch.setattr(runtime, "result_bodies", lambda _: pytest.fail("Recovery fetched bulk data"))
    result = runtime.run("not-used", work)
    assert result["status"] in ("published", "unchanged")
    current = json.loads(publisher.objects[publisher.head]["automatic/latest.json"])
    catalog = publisher.catalog(publisher.head)
    assert current["counts"] == catalog["datasets"]["participation-counts-2026"]
    assert current["native"] == catalog["datasets"]["participation-native-bindings-2026"]
    assert current["native"]["version"] == "b" * 64
    assert current["counts"]["staged_commit"] == current["native"]["staged_commit"]
    assert publisher.releases == 1 and publisher.promotions == 2 and publisher.compilations == 1
    compilations, head = publisher.compilations, publisher.head
    monkeypatch.setattr(runtime, "result_bodies", lambda _: pytest.fail("No-op fetched bulk source data"))
    assert runtime.run("not-used", work)["status"] == "unchanged"
    assert publisher.compilations == compilations and publisher.head == head
    assert publisher.promotions == 2


@pytest.mark.parametrize(("changes", "message"), [
    ({"version": "e" * 64, "checked_at": "2026-11-14T15:59:59+00:00"}, "refusing rollback"),
    ({"checked_at": "2026-11-14T16:00:01+00:00"}, "changed its immutable pointer"),
])
def test_runtime_rejects_stale_or_rebound_source_before_downloading(publication, monkeypatch, changes, message):
    publisher, work, _ = publication
    runtime.run("not-used", work)
    old_pointer = runtime.results_pointer(runtime.RESULTS_POINTER)
    monkeypatch.setattr(runtime, "results_pointer", lambda _: {**old_pointer, **changes})
    monkeypatch.setattr(runtime, "result_bodies", lambda _: pytest.fail("Unsafe source requested"))
    head = publisher.head
    with pytest.raises(ValueError, match=message):
        runtime.run("not-used", work)
    assert publisher.head == head


@pytest.mark.parametrize("changed", ["catalog", "body", "parent"])
def test_staged_successor_refuses_changed_predecessor_or_payload(publication, monkeypatch, changed):
    publisher, work, _ = publication
    runtime.run("not-used", work)
    old_head = publisher.head
    pointer = {"version": "e" * 64, "checked_at": "2026-11-14T17:00:00+00:00"}
    monkeypatch.setattr(runtime, "results_pointer", lambda _: pointer)
    publisher.interrupt = "staging"
    with pytest.raises(OSError, match="Interrupted staging"):
        runtime.run("not-used", work)
    staged = publisher.head
    assert publisher.objects[staged]["automatic/latest.json"] == publisher.objects[old_head]["automatic/latest.json"]
    if changed == "catalog":
        catalog = publisher.catalog(staged)
        catalog["extra"] = "unrelated newer catalog edit"
        publisher.objects[staged]["catalog.json"] = encoded(catalog)
    elif changed == "body":
        files = json.loads(publisher.objects[staged][runtime.PENDING_RUNTIME])["files"]
        publisher.objects[staged][next(iter(files))] = b"changed"
    else:
        publisher.parents[staged] = "d" * 40
    monkeypatch.setattr(runtime, "result_bodies", lambda _: pytest.fail("Unsafe source requested"))
    with pytest.raises((ValueError, AssertionError)):
        runtime.run("not-used", work.with_name("fresh-runner"))
    assert publisher.head == staged
    assert publisher.objects[staged]["automatic/latest.json"] == publisher.objects[old_head]["automatic/latest.json"]


def test_concurrent_catalog_change_is_not_overwritten_after_archive_verification(publication, monkeypatch):
    publisher, work, _ = publication
    release = runtime.complete_release
    concurrent = "c" * 40

    def advance(*args, **kwargs):
        result = release(*args, **kwargs)
        publisher.objects[concurrent] = {
            **publisher.objects[publisher.head], "independent-data.json": b"preserved"}
        publisher.head = concurrent
        return result
    monkeypatch.setattr(runtime, "complete_release", advance)
    with pytest.raises(ValueError, match="Data branch advanced"):
        runtime.run("not-used", work)
    assert publisher.head == concurrent and publisher.promotions == 0
    assert publisher.objects[publisher.head]["independent-data.json"] == b"preserved"


@pytest.mark.parametrize("changed", [
    {"passed": False}, {"network_requests": 1}, {"complete_outputs": 0},
    {"external_operations_blocked": False},
])
def test_unqualified_extracted_replay_never_creates_a_release_or_promotes_data(publication, changed):
    publisher, work, proof = publication
    proof.update(changed)
    with pytest.raises(ValueError, match="extracted replay"):
        runtime.run("not-used", work)
    assert publisher.releases == publisher.promotions == 0
