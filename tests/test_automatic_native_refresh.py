import copy

import pytest

from scripts.automatic_native_refresh import compressed, encoded, pin, read_json, refresh


IDENTITY, GEOMETRY = "a" * 32, "b" * 64


def observation(ballots=928):
    view = {
        "ballots": ballots, "denominator": None, "reported_pct": None,
        "year": 2026, "state_code": "MN", "county": "Aitkin",
        "county_id": "additional:MN:followup:01", "county_fips": "27001",
        "geography_level": "reporting_unit", "unit": "AITKIN",
        "unit_key": "MN|01|0005", "unit_kind": "geographic_precinct",
        "denominator_basis": "previously_reviewed_native_denominator",
        "participation_measure_label": "Native Total Number Voted",
        "maps_approved": True, "source_update_label": None,
        "source_url": "https://electionresultsfiles.sos.mn.gov/20261103/pctstats.txt",
        "native_record": {"state": "MN", "county_id": "01", "precinct_id": "0005",
                          "precinct_name": "AITKIN", "total_number_voted": ballots},
    }
    return {
        "contract": "participation.observation.v1", "id": IDENTITY,
        "election": {"id": "us-2026-general", "year": 2026, "type": "general",
                     "qualification": "previously_reviewed", "date": "2026-11-03"},
        "geography": {"state_code": "MN", "level": "reporting_unit",
                      "id": "MN|additional:MN:followup:01|MN|01|0005",
                      "name": "AITKIN", "parent_id": "MN|additional:MN:followup:01",
                      "join": {"status": "approved", "reference_id": GEOMETRY,
                               "feature_key": "MN|01|0005", "evidence": "Accepted"}},
        "measure": {"id": "accepted", "literal": "Native Total Number Voted",
                    "unit": "source_reported_count", "kind": "participation_reported",
                    "mode": "source_defined"},
        "count": {"status": "reported", "value": ballots, "literal": ballots},
        "denominator": None,
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": None, "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": "accepted", "url": "https://example.test/MN.txt",
                   "input_sha256": "c" * 64, "classification": "public_aggregate",
                   "selector": {}, "fields": copy.deepcopy(view)},
        "quality": {"notes": [], "conflicts": []}, "view": view,
    }


def fixtures():
    old = observation()
    state_name = "states/MN.json.gz"
    state_body = compressed({"contract": "participation.count_snapshot.v1", "year": 2026,
                             "state_code": "MN", "records": [old], "views": {}})
    before = {
        "index.json": encoded({"contract": "participation.count_index.v1", "year": 2026,
                               "states": {"MN": {"file": state_name, **pin(state_body)}}}),
        state_name: state_body,
    }
    properties = {
        "key": "MN|01|0005", "year": 2026, "state_code": "MN",
        "county": "Aitkin", "county_id": "additional:MN:followup:01",
        "county_fips": "27001", "unit": "AITKIN", "unit_key": "0005",
        "unit_kind": "geographic_precinct", "maps_approved": True,
        "ballots": 928, "denominator": None, "reported_pct": None,
        "native_record": {"total_number_voted": 928},
        "reference_geometry": {"sha256": GEOMETRY},
    }
    native_name = "counts/precinct-MN.json.gz"
    native_observation = copy.deepcopy(old)
    native_observation["id"] = "f" * 32
    native_observation["geography"] = {
        "state_code": "MN", "level": "reporting_unit",
        "id": "MN|additional:MN:followup:01|MN|01|0005", "name": "AITKIN",
        "parent_id": "MN|additional:MN:followup:01",
        "join": {"status": "approved", "reference_id": GEOMETRY,
                 "feature_key": "MN|01|0005", "evidence": "Accepted native geometry"},
    }
    native_observation["measure"]["literal"] = "Native Total Number Voted"
    native_observation["measure"]["mode"] = "source_defined"
    native_body = compressed({
        "contract": "participation.native_bindings.v1", "id": "precinct/MN",
        "state_code": "MN", "geometry": {"sha256": GEOMETRY}, "rows": [{
            "key": "MN|01|0005", "geometry_type": "Polygon", "properties": properties,
            "paths": {"count": ["ballots"], "denominator": ["denominator"],
                      "rate": ["reported_pct"]},
            "observation": native_observation,
        }],
    })
    native = {
        "index.json": encoded({
            "contract": "participation.native_index.v1", "year": 2026,
            "config": {"preserve": True},
            "county_bindings": {"MN": {"available": {"preserve": True}}},
            "municipal_bindings": {},
            "layers": {"precinct/MN": {
                "file": native_name, **pin(native_body), "features": 1,
                "geometry_sha256": GEOMETRY,
                "coverage": {"source_rows": 1, "reported": 1, "unknown": 0,
                             "withheld": 0, "fractions": 0},
            }},
            "reporting_tables": {}, "reporting_sources": {},
        }),
        native_name: native_body,
    }
    return before, native, state_name, native_name


def changed(before, state_name):
    after = dict(before)
    state = read_json(state_name, after[state_name])
    row = state["records"][0]
    row["count"].update(value=929, literal=929)
    row["view"]["ballots"] = 929
    row["view"]["native_record"]["total_number_voted"] = 929
    row["view"]["automatic_source_refresh"] = True
    row["source"]["fields"] = copy.deepcopy(row["view"])
    row["source"]["input_sha256"] = "d" * 64
    after[state_name] = compressed(state)
    index = read_json("index.json", after["index.json"])
    index["states"]["MN"].update(pin(after[state_name]))
    after["index.json"] = encoded(index)
    return after


def test_gzip_is_deterministic_and_normalizes_unix_os_byte():
    first, second = compressed({"value": "same"}), compressed({"value": "same"})
    assert first == second
    assert first[:3] == b"\x1f\x8b\x08"
    assert first[9] == 3


def test_refreshes_only_existing_projection_and_preserves_static_metadata():
    before, native, state_name, native_name = fixtures()
    result = refresh(before, changed(before, state_name), native)
    old, new = read_json(native_name, native[native_name]), read_json(native_name, result[native_name])
    assert new["rows"][0]["properties"]["ballots"] == 929
    assert new["rows"][0]["properties"]["native_record"]["total_number_voted"] == 929
    assert new["rows"][0]["properties"]["automatic_source_refresh"] is True
    assert new["rows"][0]["observation"]["id"] == "f" * 32
    assert new["rows"][0]["observation"]["geography"] == \
        old["rows"][0]["observation"]["geography"]
    assert new["rows"][0]["properties"]["unit_key"] == "0005"
    assert new["rows"][0]["properties"]["reference_geometry"] == \
        old["rows"][0]["properties"]["reference_geometry"]
    old_index, new_index = read_json("index.json", native["index.json"]), \
        read_json("index.json", result["index.json"])
    assert new_index["config"] == old_index["config"]
    assert new_index["county_bindings"] == old_index["county_bindings"]
    assert new_index["layers"]["precinct/MN"]["geometry_sha256"] == GEOMETRY
    assert new_index["layers"]["precinct/MN"]["sha256"] != \
        old_index["layers"]["precinct/MN"]["sha256"]


def test_rejects_changed_identity_label_and_native_preimage():
    before, native, state_name, native_name = fixtures()
    after = changed(before, state_name)
    for mutate in (
        lambda row: row.__setitem__("id", "e" * 32),
        lambda row: row["view"].__setitem__("unit", "Changed unit"),
    ):
        broken = dict(after)
        state = read_json(state_name, broken[state_name])
        mutate(state["records"][0])
        broken[state_name] = compressed(state)
        index = read_json("index.json", broken["index.json"])
        index["states"]["MN"].update(pin(broken[state_name]))
        broken["index.json"] = encoded(index)
        with pytest.raises(ValueError, match="existing count IDs|identity|label"):
            refresh(before, broken, native)
    bad_native = dict(native)
    data = read_json(native_name, bad_native[native_name])
    data["rows"][0]["observation"]["view"]["native_record"]["total_number_voted"] += 1
    bad_native[native_name] = compressed(data)
    with pytest.raises(ValueError, match="vector preimage"):
        refresh(before, after, bad_native)


def test_noop_and_changed_count_without_native_dependency_preserve_every_native_byte():
    before, native, state_name, _ = fixtures()
    assert refresh(before, before, native) == native
    empty_native = {
        "index.json": encoded({
            "contract": "participation.native_index.v1", "year": 2026,
            "config": {"preserve": True}, "county_bindings": {},
            "municipal_bindings": {}, "layers": {},
            "reporting_tables": {}, "reporting_sources": {},
        }),
    }
    assert refresh(before, changed(before, state_name), empty_native) == empty_native


def test_ambiguous_compatible_canonical_preimages_fail_closed():
    before, native, state_name, _ = fixtures()
    state = read_json(state_name, before[state_name])
    duplicate = copy.deepcopy(state["records"][0])
    duplicate["id"] = "1" * 32
    state["records"].append(duplicate)
    before[state_name] = compressed(state)
    index = read_json("index.json", before["index.json"])
    index["states"]["MN"].update(pin(before[state_name]))
    before["index.json"] = encoded(index)
    after = changed(before, state_name)
    state = read_json(state_name, after[state_name])
    second = state["records"][1]
    second["count"].update(value=930, literal=930)
    second["view"]["ballots"] = 930
    second["view"]["native_record"]["total_number_voted"] = 930
    second["view"]["automatic_source_refresh"] = True
    second["source"]["fields"] = copy.deepcopy(second["view"])
    after[state_name] = compressed(state)
    index = read_json("index.json", after["index.json"])
    index["states"]["MN"].update(pin(after[state_name]))
    after["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="Ambiguous canonical native source identity"):
        refresh(before, after, native)


def test_list_shaped_source_reporting_rows_refresh_by_exact_existing_key():
    before, _, state_name, _ = fixtures()
    state = read_json(state_name, before[state_name])
    state["records"][0]["view"]["key"] = "MN|raw-source-1"
    state["records"][0]["source"]["fields"] = copy.deepcopy(state["records"][0]["view"])
    before[state_name] = compressed(state)
    index = read_json("index.json", before["index.json"])
    index["states"]["MN"].update(pin(before[state_name]))
    before["index.json"] = encoded(index)
    after = changed(before, state_name)
    source_name = "source-reporting/MN.json.gz"
    source_body = compressed([{
        "state_code": "MN", "key": "MN|raw-source-1", "ballots": 928,
        "unit": "AITKIN", "quality": ["preserve"],
    }])
    native = {
        "index.json": encoded({
            "contract": "participation.native_index.v1", "year": 2026,
            "config": {}, "county_bindings": {}, "municipal_bindings": {},
            "layers": {}, "reporting_tables": {},
            "reporting_sources": {"MN": {"rows": 1, **pin(source_body)}},
        }),
        source_name: source_body,
    }
    result = refresh(before, after, native)
    rows = read_json(source_name, result[source_name])
    assert rows[0]["ballots"] == 929
    assert rows[0]["automatic_source_refresh"] is True
    source = read_json("index.json", result["index.json"])["reporting_sources"]["MN"]
    assert source["rows"] == 1
    assert source["sha256"] == pin(result[source_name])["sha256"]
