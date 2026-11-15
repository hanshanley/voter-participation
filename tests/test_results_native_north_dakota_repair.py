import copy
import gzip
import json
from pathlib import Path
import sys

import pytest

from scripts import automatic_native_refresh, results_granular
from scripts.participation_intake.contract import pin
from scripts import results_native_north_dakota as nd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nd_native_fixture_support as fixture_support


FIXTURES = Path(__file__).with_name("fixtures") / "nd-native-automatic"


def compressed(value):
    body = bytearray(gzip.compress(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        compresslevel=6, mtime=0))
    body[9] = 3
    return bytes(body)


def source_rows():
    templates = fixture_support.load_gzip(
        FIXTURES / "accepted-templates.json.gz")["records"]
    facts = fixture_support.load_gzip(FIXTURES / "nd-complete-facts.json.gz")
    documents = fixture_support.source_documents(facts)
    parsed = nd.statistics(
        documents[nd.FULL_RESULTS_URL], templates, nd.FULL_RESULTS_URL,
        acquire=lambda url: (documents[url], pin(documents[url])),
    )
    shard = {
        "contract": "participation.count_snapshot.v1", "state_code": "ND",
        "year": 2026, "records": templates, "views": {},
    }
    body = compressed(shard)
    baseline = {
        "index.json": json.dumps({
            "contract": "participation.count_index.v1", "year": 2026,
            "states": {"ND": {"file": "states/ND.json.gz", **pin(body)}},
            "coverage": {},
        }, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        "states/ND.json.gz": body,
    }
    entry = {
        "ND-registered-fixture": {
            "status": "reported", "data": parsed,
            "source": {"url": nd.FULL_RESULTS_URL,
                       **pin(documents[nd.FULL_RESULTS_URL])},
            "error": None,
        }
    }
    successor, changes = results_granular.project(baseline, entry)
    assert len(changes) == 411
    after = json.loads(gzip.decompress(successor["states/ND.json.gz"]))["records"]
    before_by_id = {row["id"]: row for row in templates}
    after_by_id = {row["id"]: row for row in after}
    selected_id = next(
        row["id"] for row in templates
        if row["source"]["id"] == nd.UNIT_SOURCE_ID
        and row["view"]["native_record"]["county"] == "38003"
        and row["view"]["native_record"]["precinct"] == "2401"
    )
    return before_by_id[selected_id], after_by_id[selected_id]


def matched_native(previous):
    facts = previous["view"]["native_record"]
    county_id, precinct_id = facts["county"], facts["precinct"]
    key = f"ND|{county_id}|{precinct_id}"
    view = {
        "ballots": previous["count"]["value"],
        "county": facts["county_name"], "county_id": county_id,
        "denominator": None,
        "denominator_basis": "previously_reviewed_native_denominator",
        "key": key,
        "participation": copy.deepcopy(facts),
        "precinct": facts["precinct_name"], "precinct_code": precinct_id,
        "reported_pct": None,
        "source_update_label": None,
        "source_url": automatic_native_refresh.ND_RESULTS_URL,
        "state_code": "ND", "unit": facts["precinct_name"],
        "unit_key": key, "year": 2026,
    }
    return {
        "contract": "participation.observation.v1",
        "id": "portable-matched-native",
        "count": copy.deepcopy(previous["count"]),
        "denominator": None,
        "election": copy.deepcopy(previous["election"]),
        "geography": {
            "id": f"ND|{county_id}|{key}", "name": facts["precinct_name"],
            "state_code": "ND", "level": "reporting_unit",
            "parent_id": "ND|" + county_id,
            "join": {
                "evidence": "Existing source-specific qualification retained from accepted c4ccdf4; no new geographic approval.",
                "feature_key": key,
                "reference_id": automatic_native_refresh.ND_GEOMETRY_SHA,
                "status": "approved",
            },
        },
        "measure": copy.deepcopy(previous["measure"]),
        "source_clock": {
            "literal": None,
            "qualification": "previously_reviewed_export_label_not_new_native_clock",
            "timezone": None,
        },
        "reporting_status": copy.deepcopy(previous["reporting_status"]),
        "source": {
            "id": automatic_native_refresh.ND_MATCHED_SOURCE_ID,
            "url": automatic_native_refresh.ND_GEOMETRY_URL,
            "input_sha256": automatic_native_refresh.ND_GEOMETRY_SHA,
            "selector": {
                "input": "data/precinct-results/20261105-north-dakota-02/2026/ND.geojson.gz",
                "ordinal": 1, "partition": "matched/ND",
            },
            "classification": "public_aggregate",
            "fields": copy.deepcopy(view),
        },
        "quality": {
            "conflicts": [],
            "native_conflict_status": "retained_in_source_fields_not_newly_classified",
            "notes": [
                facts["quality"],
                "One-time migration of accepted public aggregate export; not a new source parse, conflict adjudication, election/boundary certification or independent validation.",
                "All native fields, conflicts, holds and existing rate decisions remain unchanged in source.fields and view. Export partitions are separate appearances, never additive populations.",
            ],
        },
        "view": view,
    }


def coherent_view_change(row, change):
    change(row["view"])
    row["source"]["fields"] = copy.deepcopy(row["view"])


def test_legacy_and_saved_vector_normalizations_are_explicit_and_reusable():
    previous, current = source_rows()
    native = matched_native(previous)
    refreshed = automatic_native_refresh.project_compatible_observation(
        native, previous, current)
    mirror = refreshed["view"][automatic_native_refresh.ND_VECTOR_KEY]
    assert mirror == {
        "contract": automatic_native_refresh.ND_VECTOR_CONTRACT,
        "source_family": "north_dakota_reviewed_native_turnout",
        "canonical_observation_id": current["id"],
        "canonical_vector": pin(automatic_native_refresh.encoded(current)),
    }
    future = copy.deepcopy(current)
    future["count"] = {"value": current["count"]["value"] + 1,
                       "literal": current["count"]["value"] + 1,
                       "status": "reported"}
    future["view"]["ballots"] = future["count"]["value"]
    record = future["view"]["native_record"]["record"]
    record["TotalBallotsCast"] = future["count"]["value"]
    record["TotalBallotsReceived"] = future["count"]["value"]
    record["BallotsCast"] = [{
        "BallotsCast": future["count"]["value"],
        "BallotsReceived": future["count"]["value"],
        "VotePercent": 100, "VoteTypeID": "1",
    }]
    future["source"]["input_sha256"] = "2" * 64
    future["view"]["source_sha256"] = "2" * 64
    future["source"]["fields"] = copy.deepcopy(future["view"])
    future["source"]["selector"] = {
        "native_refresh": future["view"]["native_record"]}
    repeated = automatic_native_refresh.project_compatible_observation(
        refreshed, current, future)
    assert repeated["count"]["value"] == future["count"]["value"]
    assert repeated["view"]["participation"]["ballots"] == future["count"]["value"]


def test_equal_identity_and_count_cannot_hide_previous_vector_mutations():
    previous, current = source_rows()
    native = matched_native(previous)
    mutations = []
    changed = copy.deepcopy(previous)
    changed["source"]["input_sha256"] = "0" * 64
    mutations.append(changed)
    changed = copy.deepcopy(previous)
    changed["source"]["url"] = "https://resultsnd.sos.nd.gov/changed"
    mutations.append(changed)
    changed = copy.deepcopy(previous)
    changed["reporting_status"]["reported_units"] = 1
    mutations.append(changed)
    changed = copy.deepcopy(previous)
    changed["source_clock"]["literal"] = "changed"
    mutations.append(changed)
    changed = copy.deepcopy(previous)
    changed["measure"]["literal"] = "Changed but identity tuple retained"
    mutations.append(changed)
    changed = copy.deepcopy(previous)
    coherent_view_change(
        changed, lambda view: view["native_record"].update(
            candidate_votes_exceed_ballots=True))
    mutations.append(changed)
    for changed in mutations:
        assert changed["id"] == previous["id"]
        assert changed["count"] == previous["count"]
        with pytest.raises(ValueError, match="North Dakota"):
            automatic_native_refresh.project_compatible_observation(
                native, changed, current)


def test_equal_identity_and_count_cannot_hide_native_vector_mutations():
    previous, current = source_rows()
    native = matched_native(previous)
    mutations = []
    changed = copy.deepcopy(native)
    changed["source"]["input_sha256"] = "0" * 64
    mutations.append(changed)
    changed = copy.deepcopy(native)
    changed["source"]["url"] = "https://example.invalid/geometry"
    mutations.append(changed)
    changed = copy.deepcopy(native)
    coherent_view_change(
        changed, lambda view: view.update(
            source_url="https://example.invalid/results"))
    mutations.append(changed)
    changed = copy.deepcopy(native)
    changed["reporting_status"]["reported_units"] = 1
    mutations.append(changed)
    changed = copy.deepcopy(native)
    changed["source_clock"]["literal"] = "changed"
    mutations.append(changed)
    changed = copy.deepcopy(native)
    changed["measure"]["literal"] = "Changed but compatibility identity retained"
    mutations.append(changed)
    changed = copy.deepcopy(native)
    coherent_view_change(
        changed, lambda view: view["participation"].update(denominator=1))
    mutations.append(changed)
    for changed in mutations:
        assert changed["count"] == native["count"]
        with pytest.raises(ValueError, match="North Dakota"):
            automatic_native_refresh.project_compatible_observation(
                changed, previous, current)


def test_saved_vector_hash_rejects_coherent_previous_source_rewrite():
    previous, current = source_rows()
    refreshed = automatic_native_refresh.project_compatible_observation(
        matched_native(previous), previous, current)
    changed = copy.deepcopy(current)
    changed["source"]["input_sha256"] = "1" * 64
    changed["view"]["source_sha256"] = "1" * 64
    changed["source"]["fields"] = copy.deepcopy(changed["view"])
    with pytest.raises(ValueError, match="saved canonical source vector"):
        automatic_native_refresh.project_compatible_observation(
            refreshed, changed, current)
