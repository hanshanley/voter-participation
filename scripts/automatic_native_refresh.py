"""Refresh approved native count projections from canonical successor records."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
from typing import Any


IDENTITY_VIEW_KEYS = (
    "key", "year", "state_code", "county", "county_id", "county_fips",
    "geography_level", "reference_municipality_key", "source_administration_id",
    "source_mode", "unit", "unit_key", "unit_kind", "denominator_basis",
    "participation_measure_kind", "participation_measure_literal",
    "participation_measure_label", "cast_ballot_count_qualified",
    "unique_voter_count_qualified", "maps_approved",
)
NATIVE_PREFIXES = ("counts/", "tables/", "source-reporting/")
STATIC_PROJECTION_KEYS = (
    "reference_geometry", "boundary_label", "geometry_withheld_reason",
    "match_status", "reporting_unit_kind", "rate_withheld_reason",
    "source_count_qualified", "quality",
)
REVIEWED_FAMILY_SOURCE_IDS = {
    "AR": "accepted-export:b128dc3cef02ae063e840495611b3747dc9454692d2788a8cb94e3b160f4908a:reporting/AR",
    "AZ": "accepted-export:bc9f1e93785e4a83148b96afa6855701f511be995f7469b8e9e4dfcb7e6cb51f:reporting/AZ",
    "WY": "accepted-export:cea7eba88d5ae521db73653ce33992dbe2d253a2854cd81d27655890e74be161:reporting/WY",
}
ND_CANONICAL_SOURCE_ID = (
    "accepted-export:14ba49ba698b3fa4ebe3ee2e846f964f4f13e7b882f7a3cd66a89eee7df77783:"
    "precincts"
)
ND_MATCHED_SOURCE_ID = (
    "accepted-export:cbc13e678def482cbc9bdc74d690694eab6d148c9ed71365269bb2b21ecce9e1:"
    "matched/ND"
)
ND_GEOMETRY_SHA = "cbc13e678def482cbc9bdc74d690694eab6d148c9ed71365269bb2b21ecce9e1"
ND_EXPORT_SHA = "14ba49ba698b3fa4ebe3ee2e846f964f4f13e7b882f7a3cd66a89eee7df77783"
ND_STORED_SOURCE_URL = "https://www.themarginoferror.com/participation-local/ND.json.gz"
ND_STORED_UNIT_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "2e7b240d3cece70001ef573dd487538d46ebd5cd/data/precinct-results/"
    "20261105-north-dakota-02/participation.json.gz"
)
ND_RESULTS_URL = (
    "https://resultsnd.sos.nd.gov/results/north-dakota/348/FullDataFile.json"
)
ND_GEOMETRY_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "2e7b240d3cece70001ef573dd487538d46ebd5cd/data/precinct-results/"
    "20261105-north-dakota-02/2026/ND.geojson.gz"
)
ND_VECTOR_KEY = "automatic_native_refresh_source_vector"
ND_VECTOR_CONTRACT = "participation.nd_native_refresh_source_vector.v1"


def encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def pin(body: bytes) -> dict[str, Any]:
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def compressed(value: Any) -> bytes:
    body = bytearray(gzip.compress(encoded(value), compresslevel=9, mtime=0))
    body[9] = 3
    return bytes(body)


def read_json(name: str, body: bytes) -> Any:
    raw = gzip.decompress(body) if name.endswith(".gz") else body
    return json.loads(raw)


def reviewed_measure_label(row: dict[str, Any]) -> str | None:
    source, geography = row.get("source", {}), row.get("geography", {})
    election, measure = row.get("election", {}), row.get("measure", {})
    view, denominator = row.get("view", {}), row.get("denominator") or {}
    label = "Source-reported turnout total"
    if (
        source.get("id") == "ks-greeley-official-general-20261103"
        and source.get("url") == (
            "https://greeleycountyks.gov/documents/elections/"
            "official-general-election-results-2026-11-03.xlsx")
        and (geography.get("state_code"), geography.get("level"), geography.get("name"),
             geography.get("id")) == (
                 "KS", "county", "Greeley County", "ks-greeley-county-official-general-20261103")
        and (election.get("year"), election.get("type"), election.get("date")) == (
            2026, "general", "2026-11-03")
        and (measure.get("id"), measure.get("kind"), measure.get("unit"),
             measure.get("literal")) == (
                 "native-source-reported-turnout-total", "voters_reported",
                 "source_reported_voters_in_turnout_total",
                 "451 voted ... 9 provisionals = 460")
        and view.get("participation_measure_literal") == (
            "Source-reported turnout total (451 voted + 9 counted provisionals)")
        and view.get("participation_measure_label") in (None, label)
        and view.get("cast_ballot_count_qualified") is False
        and view.get("unique_voter_count_qualified") is False
        and view.get("maps_approved") is False
        and denominator.get("basis") == "native_registered_voters_same_official_county_report"
        and denominator.get("literal") == "Registered Voters"
        and denominator.get("qualified") is True
    ):
        return label
    return None


def observation_identity(row: dict[str, Any]) -> bytes:
    denominator = row.get("denominator")
    view = {key: row.get("view", {}).get(key) for key in IDENTITY_VIEW_KEYS}
    label = reviewed_measure_label(row)
    if label is not None:
        # This reviewed display alias removes frozen numbers, not a measure or frame.
        view["participation_measure_label"] = label
    return encoded({
        "id": row.get("id"),
        "election": row.get("election"),
        "geography": row.get("geography"),
        "measure": row.get("measure"),
        "denominator": None if denominator is None else {
            "literal": denominator.get("literal"),
            "basis": denominator.get("basis"),
            "qualified": denominator.get("qualified"),
        },
        "view": view,
    })


def projected(properties: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(properties)
    for key in tuple(result):
        if key not in IDENTITY_VIEW_KEYS and key not in STATIC_PROJECTION_KEYS and key in view:
            result[key] = copy.deepcopy(view[key])
    if view.get("automatic_source_refresh") is True:
        result["automatic_source_refresh"] = True
    return result


def value_at(value: dict[str, Any], path: list[str] | None) -> Any:
    for key in path or []:
        value = value[key]
    return value


def put(value: dict[str, Any], path: list[str] | None, replacement: Any) -> None:
    if not path:
        return
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


def coverage(records: list[dict[str, Any]]) -> dict[str, int]:
    observations = [row["observation"] for row in records]
    return {
        "source_rows": sum(row["geography"]["join"]["status"] == "approved" for row in observations),
        "reported": sum(row["count"]["status"] == "reported" for row in observations),
        "unknown": sum(row["count"]["status"] == "unknown" for row in observations),
        "withheld": sum(row["count"]["status"] == "withheld" for row in observations),
        "fractions": sum(bool(row.get("denominator", {}).get("qualified"))
                         for row in observations if row.get("denominator") is not None),
    }


def state_records(files: dict[str, bytes], index: dict[str, Any], code: str) -> dict[str, Any]:
    declaration = index["states"][code]
    data = read_json(declaration["file"], files[declaration["file"]])
    if data.get("contract") != "participation.count_snapshot.v1" or data.get("state_code") != code:
        raise ValueError(f"Wrong canonical count state contract: {code}")
    records = {row["id"]: row for row in data["records"]}
    if len(records) != len(data["records"]):
        raise ValueError(f"Duplicate canonical count IDs: {code}")
    return records


def changed_records(before_files: dict[str, bytes], after_files: dict[str, bytes]) -> tuple[
        dict[str, dict[str, Any]], dict[str, dict[str, Any]], set[str]]:
    before_index = read_json("index.json", before_files["index.json"])
    after_index = read_json("index.json", after_files["index.json"])
    if (before_index.get("contract") != "participation.count_index.v1"
            or after_index.get("contract") != "participation.count_index.v1"
            or before_index.get("year") != 2026 or after_index.get("year") != 2026
            or set(before_index.get("states", {})) != set(after_index.get("states", {}))):
        raise ValueError("Changed count index contract, election or jurisdiction inventory")
    before, after, changed_states = {}, {}, set()
    for code in sorted(before_index["states"]):
        old_decl, new_decl = before_index["states"][code], after_index["states"][code]
        if old_decl["sha256"] == new_decl["sha256"] and old_decl["bytes"] == new_decl["bytes"]:
            continue
        if old_decl["file"] != new_decl["file"]:
            raise ValueError(f"Changed canonical count path: {code}")
        old = state_records(before_files, before_index, code)
        new = state_records(after_files, after_index, code)
        if set(old) != set(new):
            removed = set(old) - set(new)
            added = set(new) - set(old)
            reviewed = (
                code == "LA" and not removed and len(added) == 3783
                and all(
                    new[identity].get("source", {}).get("id")
                        == "la-sos-post-election-statistics-2026-11-03"
                    and new[identity].get("denominator") is None
                    and new[identity].get("view", {}).get("maps_approved") is False
                    and new[identity].get("view", {}).get(
                        "frontend_activation_approved") is False
                    for identity in added
                )
            )
            if not reviewed:
                raise ValueError(
                    f"Automatic refresh may update only existing count IDs unless explicitly reviewed: {code}")
        for identity in old:
            if old[identity] != new[identity]:
                if observation_identity(old[identity]) != observation_identity(new[identity]):
                    raise ValueError(f"Changed count identity, geography, label or qualification: {identity}")
                before[identity], after[identity] = old[identity], new[identity]
        changed_states.add(code)
    return before, after, changed_states


def _north_dakota_identity(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    county_id = value.get("county_id", value.get("county"))
    county_name = value.get("county_name")
    precinct_id = value.get("precinct_id", value.get("precinct"))
    precinct_name = value.get("precinct_name")
    if (
        not isinstance(county_id, str)
        or len(county_id) != 5
        or not county_id.startswith("38")
        or not county_id[2:].isdigit()
        or not all(isinstance(item, str) and item for item in (
            county_name, precinct_id, precinct_name))
    ):
        return None
    return {
        "state_code": "ND", "county_id": county_id, "county_name": county_name,
        "precinct_id": precinct_id, "precinct_name": precinct_name,
    }


def _north_dakota_row_identity(row: dict[str, Any]) -> dict[str, str] | None:
    if (
        row.get("geography", {}).get("state_code") != "ND"
        or row.get("geography", {}).get("level") != "reporting_unit"
    ):
        return None
    view, source = row.get("view", {}), row.get("source", {})
    if source.get("id") == ND_CANONICAL_SOURCE_ID:
        native = view.get("native_record")
        if isinstance(native, dict) and isinstance(native.get("canonical_identity"), dict):
            return _north_dakota_identity(native["canonical_identity"])
        return _north_dakota_identity(native)
    if source.get("id") == ND_MATCHED_SOURCE_ID:
        return _north_dakota_identity(view.get("participation"))
    return None


def _north_dakota_common(row: dict[str, Any]) -> None:
    if (
        row.get("contract") != "participation.observation.v1"
        or row.get("election") != {
            "date": None, "id": "us-2026-general-previously-reviewed",
            "qualification": "previously_reviewed", "type": "general", "year": 2026,
        }
        or row.get("measure") != {
            "id": "previously-reviewed-participation-count",
            "kind": "participation_reported",
            "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
            "mode": "source_defined", "unit": "source_reported_count",
        }
        or row.get("denominator") is not None
        or row.get("source", {}).get("classification") != "public_aggregate"
        or row.get("source", {}).get("fields") != row.get("view")
    ):
        raise ValueError("North Dakota native/canonical qualification vector changed")


def _north_dakota_legacy_canonical(row: dict[str, Any],
                                   identity: dict[str, str]) -> None:
    _north_dakota_common(row)
    source, view = row["source"], row["view"]
    expected_native = {
        "ballots": row["count"]["value"], "candidate_votes_exceed_ballots": False,
        "county": identity["county_id"], "county_name": identity["county_name"],
        "denominator": None,
        "key": f"ND|{identity['county_id']}|{identity['precinct_id']}",
        "measure": "reported_ballots", "precinct": identity["precinct_id"],
        "precinct_name": identity["precinct_name"],
        "quality": "No precinct electorate denominator. Do not reuse county/state voting-age estimates.",
        "reported_pct": None, "state_code": "ND", "year": 2026,
    }
    if (
        source.get("id") != ND_CANONICAL_SOURCE_ID
        or source.get("url") != ND_STORED_SOURCE_URL
        or source.get("input_sha256") != ND_EXPORT_SHA
        or not isinstance(source.get("selector"), dict)
        or source["selector"].get("input") != "additional/ND.json.gz"
        or source["selector"].get("partition") != "precincts"
        or isinstance(source["selector"].get("ordinal"), bool)
        or not isinstance(source["selector"].get("ordinal"), int)
        or source["selector"]["ordinal"] < 0
        or row.get("source_clock") != {
            "literal": "See frozen source snapshot",
            "qualification": "previously_reviewed_export_label_not_new_native_clock",
            "timezone": None,
        }
        or row.get("reporting_status") != {
            "complete": None, "literal": None, "reported_units": None, "total_units": None}
        or view.get("native_record") != expected_native
        or view.get("ballots") != row["count"]["value"]
        or view.get("county") != identity["county_name"]
        or view.get("county_id") != "additional:ND:" + identity["county_id"]
        or view.get("denominator") is not None
        or view.get("denominator_basis") != "electorate_not_supplied"
        or view.get("geography_level") != "county"
        or view.get("maps_approved") is not False
        or view.get("native_printed_pct") is not None
        or view.get("reported_pct") is not None
        or view.get("reported_units") is not None
        or view.get("total_units") is not None
        or view.get("review_id") != "additional:20261105-north-dakota-02"
        or view.get("source_rows") != 0
        or view.get("source_status_literal") is not None
        or view.get("source_update_label") != "See frozen source snapshot"
        or view.get("source_url") != ND_STORED_UNIT_URL
        or view.get("state_code") != "ND"
        or view.get("unit") != identity["precinct_name"]
        or view.get("unit_key")
           != f"ND|{identity['county_id']}|{identity['precinct_id']}"
        or view.get("unit_kind") != "source_reporting_unit"
        or view.get("year") != 2026
        or row.get("geography", {}).get("name") != identity["precinct_name"]
        or row.get("geography", {}).get("parent_id")
           != "ND|additional:ND:" + identity["county_id"]
    ):
        raise ValueError("North Dakota legacy canonical source vector changed")


def _north_dakota_record_count(record: dict[str, Any]) -> int | None:
    value = record.get("TotalBallotsCast")
    buckets = record.get("BallotsCast")
    if value is None:
        if buckets in (None, []):
            return None
        if (
            isinstance(buckets, list)
            and len(buckets) == 1
            and buckets[0] == {
                "BallotsCast": 0, "BallotsReceived": 0,
                "VotePercent": 0, "VoteTypeID": "1",
            }
            and record.get("PrecinctsReporting") == record.get("TotalPrecincts")
        ):
            return 0
        raise ValueError("North Dakota reviewed native count vector changed")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("North Dakota reviewed native count vector changed")
    expected = [{
        "BallotsCast": value, "BallotsReceived": value,
        "VotePercent": 0 if value == 0 else 100, "VoteTypeID": "1",
    }]
    if buckets != expected or record.get("TotalBallotsReceived", value) != value:
        raise ValueError("North Dakota reviewed native count vector changed")
    return value


def _north_dakota_reviewed_canonical(row: dict[str, Any],
                                     identity: dict[str, str]) -> None:
    _north_dakota_common(row)
    source, view = row["source"], row["view"]
    native = view.get("native_record")
    record = native.get("record") if isinstance(native, dict) else None
    if (
        source.get("id") != ND_CANONICAL_SOURCE_ID
        or source.get("url") != ND_RESULTS_URL
        or not isinstance(source.get("input_sha256"), str)
        or len(source["input_sha256"]) != 64
        or source.get("selector") != {"native_refresh": native}
        or view.get("source_url") != ND_RESULTS_URL
        or view.get("source_sha256") != source["input_sha256"]
        or view.get("ballots") != row["count"]["value"]
        or view.get("denominator") is not None
        or view.get("reported_pct") is not None
        or not isinstance(native, dict)
        or native.get("canonical_identity") != identity
        or native.get("analytical_denominator") is not None
        or native.get("analytical_rate") is not None
        or native.get("geographic_join_changed") is not False
        or native.get("native_reporting_complete_qualified") is not False
        or native.get("source_clock_timezone_literal") != "UTC"
        or native.get("query") != {
            "canonical_identity": identity, "source_clock_timezone_literal": "UTC"}
        or not isinstance(record, dict)
        or record.get("LocationID") != identity["precinct_id"]
        or _north_dakota_record_count(record) != row["count"]["value"]
        or record.get("PrecinctsReporting")
           != row.get("reporting_status", {}).get("reported_units")
        or record.get("TotalPrecincts")
           != row.get("reporting_status", {}).get("total_units")
        or native.get("registered_voters_retained_not_analytical_denominator") is not None
        or isinstance(native.get("house_candidate_votes_not_ballots"), bool)
        or not isinstance(native.get("house_candidate_votes_not_ballots"), int)
        or native["house_candidate_votes_not_ballots"] < 0
        or (row["count"]["value"] is not None
            and native["house_candidate_votes_not_ballots"] > row["count"]["value"])
        or not isinstance(native.get("source_version"), str)
        or not native["source_version"].startswith("v")
        or not native["source_version"][1:].isdigit()
        or native.get("source_status_literal") not in (
            "IsOfficial=false", "IsOfficial=true")
        or row.get("source_clock", {}).get("literal") != view.get("source_update_label")
        or row.get("source_clock", {}).get("timezone") != "UTC"
        or row.get("source_clock", {}).get("qualification")
           != "native_clock_or_explicitly_not_supplied"
        or row.get("reporting_status", {}).get("reported_units")
           != view.get("reported_units")
        or row.get("reporting_status", {}).get("total_units") != view.get("total_units")
        or row.get("reporting_status", {}).get("complete") is not None
        or view.get("automatic_source_refresh") is not True
    ):
        raise ValueError("North Dakota reviewed canonical source vector changed")


def _north_dakota_native(row: dict[str, Any],
                         identity: dict[str, str]) -> dict[str, Any]:
    _north_dakota_common(row)
    source, view = row["source"], row["view"]
    participation = view.get("participation")
    key = f"ND|{identity['county_id']}|{identity['precinct_id']}"
    if (
        source.get("id") != ND_MATCHED_SOURCE_ID
        or source.get("url") != ND_GEOMETRY_URL
        or source.get("input_sha256") != ND_GEOMETRY_SHA
        or not isinstance(source.get("selector"), dict)
        or source["selector"].get("input")
           != "data/precinct-results/20261105-north-dakota-02/2026/ND.geojson.gz"
        or source["selector"].get("partition") != "matched/ND"
        or isinstance(source["selector"].get("ordinal"), bool)
        or not isinstance(source["selector"].get("ordinal"), int)
        or source["selector"]["ordinal"] < 0
        or view.get("source_url") != ND_RESULTS_URL
        or view.get("state_code") != "ND"
        or view.get("county_id") != identity["county_id"]
        or view.get("county") != identity["county_name"]
        or view.get("key") != key
        or view.get("unit_key") != key
        or view.get("precinct_code") != identity["precinct_id"]
        or view.get("precinct") != identity["precinct_name"]
        or view.get("unit") != identity["precinct_name"]
        or view.get("year") != 2026
        or view.get("denominator") is not None
        or view.get("reported_pct") is not None
        or view.get("denominator_basis") != "previously_reviewed_native_denominator"
        or not isinstance(participation, dict)
        or _north_dakota_identity(participation) != identity
        or participation.get("key") != key
        or participation.get("ballots") != row["count"]["value"]
        or participation.get("denominator") is not None
        or participation.get("reported_pct") is not None
        or participation.get("measure") != "reported_ballots"
        or participation.get("year") != 2026
        or row.get("geography", {}).get("name") != identity["precinct_name"]
        or row.get("geography", {}).get("parent_id") != "ND|" + identity["county_id"]
        or row.get("geography", {}).get("join") != {
            "evidence": "Existing source-specific qualification retained from accepted c4ccdf4; no new geographic approval.",
            "feature_key": key, "reference_id": ND_GEOMETRY_SHA, "status": "approved",
        }
    ):
        raise ValueError("North Dakota approved native source vector changed")
    return participation


def _north_dakota_preimage(native: dict[str, Any],
                           previous: dict[str, Any]) -> None:
    identity = _north_dakota_row_identity(native)
    if identity is None or identity != _north_dakota_row_identity(previous):
        raise ValueError("North Dakota native/canonical literal identity differs")
    participation = _north_dakota_native(native, identity)
    if (
        native.get("count") != previous.get("count")
        or native.get("denominator") != previous.get("denominator")
        or native.get("election") != previous.get("election")
        or native.get("measure") != previous.get("measure")
    ):
        raise ValueError("North Dakota native/canonical count or qualification differs")
    mirror = native["view"].get(ND_VECTOR_KEY)
    if mirror is None:
        _north_dakota_legacy_canonical(previous, identity)
        if (
            participation != previous["view"]["native_record"]
            or native.get("source_clock") != {
                "literal": None,
                "qualification": "previously_reviewed_export_label_not_new_native_clock",
                "timezone": None,
            }
            or native.get("reporting_status") != previous.get("reporting_status")
            or native.get("quality", {}).get("conflicts")
               != previous.get("quality", {}).get("conflicts")
            or native.get("quality", {}).get("native_conflict_status")
               != previous.get("quality", {}).get("native_conflict_status")
            or native.get("quality", {}).get("notes", [])[-2:]
               != previous.get("quality", {}).get("notes", [])[-2:]
        ):
            raise ValueError("North Dakota legacy saved-format normalization differs")
        return
    _north_dakota_reviewed_canonical(previous, identity)
    expected = {
        "contract": ND_VECTOR_CONTRACT,
        "source_family": "north_dakota_reviewed_native_turnout",
        "canonical_observation_id": previous["id"],
        "canonical_vector": pin(encoded(previous)),
    }
    if (
        mirror != expected
        or native.get("source_clock") != previous.get("source_clock")
        or native.get("reporting_status") != previous.get("reporting_status")
        or native["view"].get("ballots") != previous["count"]["value"]
        or native["view"].get("source_url") != previous["view"].get("source_url")
        or native["view"].get("source_update_label")
           != previous["view"].get("source_update_label")
    ):
        raise ValueError("North Dakota saved canonical source vector preimage differs")


def north_dakota_compatibility_identity(row: dict[str, Any]) -> bytes | None:
    identity = _north_dakota_row_identity(row)
    if identity is None:
        return None
    return encoded({
        "schema": "reviewed_north_dakota_literal_reporting_unit",
        **identity,
        "election_date": "2026-11-03",
        "measure_kind": "participation_reported",
        "measure_unit": "source_reported_count",
        "measure_mode": "source_defined",
    })


def compatibility_identity(row: dict[str, Any]) -> bytes | None:
    north_dakota = north_dakota_compatibility_identity(row)
    if north_dakota is not None:
        return north_dakota
    view = row.get("view", {})
    native = view.get("native_record")
    if not isinstance(native, dict):
        return None
    election = row.get("election", {})
    election_date = election.get("date") or view.get("source_election_date")
    if election_date is None and election.get("year") == 2026 \
            and election.get("type") == "general":
        election_date = "2026-11-03"
    facts = native.get("native_fields", native.get("query", native))
    unit = None
    if isinstance(facts, dict):
        if (type(facts.get("Precinct_ID")) is int
                and isinstance(facts.get("Precinct"), str)
                and "Ballots_Cast" in facts):
            unit = {"schema": "native_arcgis_ballots_cast",
                    "id": facts["Precinct_ID"], "label": facts["Precinct"]}
        elif ("times_cast_literal" in facts
              and all(isinstance(facts.get(key), str) and facts[key]
                      for key in ("city", "native_context", "native_label", "ward", "precinct"))):
            unit = {key: facts[key] for key in (
                "city", "native_context", "native_label", "ward", "precinct")}
            unit["schema"] = "native_statement_times_cast"
    if unit is not None:
        mode = row.get("measure", {}).get("mode")
        if unit["schema"] == "native_statement_times_cast" \
                and mode in ("source_defined", "all_methods"):
            mode = "native_statement_times_cast"
        fields = {
            "state": row.get("geography", {}).get("state_code"),
            "county_id": view.get("county_id"), "native_unit": unit,
            "source_url": view.get("source_url"),
            "measure_kind": row.get("measure", {}).get("kind"),
            "measure_unit": row.get("measure", {}).get("unit"),
            "measure_mode": mode,
            "geography_level": row.get("geography", {}).get("level"),
            "election_year": election.get("year"), "election_date": election_date,
            "election_type": election.get("type"),
        }
        if any(value is None or value == "" for value in fields.values()):
            return None
        return encoded(fields)
    fields = {
        "state": native.get("state"),
        "county_id": native.get("county_id"),
        "precinct_id": native.get("precinct_id"),
        "precinct_name": native.get("precinct_name"),
        "native_count_field": "total_number_voted"
        if "total_number_voted" in native else None,
        "source_url": view.get("source_url"),
        "measure_kind": row.get("measure", {}).get("kind"),
        "measure_unit": row.get("measure", {}).get("unit"),
        "election_year": election.get("year"),
        "election_date": election_date,
        "election_type": election.get("type"),
    }
    if any(value is None or value == "" for value in fields.values()):
        return None
    return encoded(fields)


def project_compatible_observation(native: dict[str, Any],
                                   previous: dict[str, Any],
                                   current: dict[str, Any]) -> dict[str, Any]:
    if not (compatibility_identity(native) == compatibility_identity(previous)
            == compatibility_identity(current)):
        raise ValueError("Compatible native/canonical source identity differs")
    north_dakota = north_dakota_compatibility_identity(native) is not None
    if north_dakota:
        _north_dakota_preimage(native, previous)
        identity = _north_dakota_row_identity(current)
        if identity is None:
            raise ValueError("North Dakota current canonical identity differs")
        _north_dakota_reviewed_canonical(current, identity)
    elif native.get("view", {}).get("native_record") != previous.get("view", {}).get("native_record"):
        raise ValueError("Compatible native vector preimage differs")
    if native.get("count") != previous.get("count"):
        raise ValueError("Compatible native count preimage differs")
    result = copy.deepcopy(native)
    result["count"] = copy.deepcopy(current["count"])
    old_denominator, new_denominator = result.get("denominator"), current.get("denominator")
    if (old_denominator is None) != (new_denominator is None):
        raise ValueError("Compatible native denominator scope differs")
    if old_denominator is not None:
        old_denominator["value"] = new_denominator["value"]
    for key in ("literal", "reported_units", "total_units", "complete"):
        if key in current.get("reporting_status", {}):
            result["reporting_status"][key] = copy.deepcopy(current["reporting_status"][key])
    result["source_clock"]["literal"] = current.get("source_clock", {}).get("literal")
    result["source_clock"]["timezone"] = current.get("source_clock", {}).get("timezone")
    if north_dakota:
        result["source_clock"]["qualification"] = current.get(
            "source_clock", {}).get("qualification")
    result["view"] = projected(result["view"], current["view"])
    if north_dakota:
        participation = copy.deepcopy(result["view"]["participation"])
        participation["ballots"] = current["count"]["value"]
        participation["denominator"] = None
        participation["reported_pct"] = None
        result["view"]["participation"] = participation
        result["view"][ND_VECTOR_KEY] = {
            "contract": ND_VECTOR_CONTRACT,
            "source_family": "north_dakota_reviewed_native_turnout",
            "canonical_observation_id": current["id"],
            "canonical_vector": pin(encoded(current)),
        }
    result["source"]["fields"] = copy.deepcopy(result["view"])
    return result


def compatibility_map(before: dict[str, dict[str, Any]]) -> dict[bytes, str]:
    result = {}
    for identity, row in before.items():
        key = compatibility_identity(row)
        if key is None:
            continue
        if key in result:
            raise ValueError(f"Ambiguous canonical native source identity: {identity}")
        result[key] = identity
    return result


def refresh_embedded(data: Any, before: dict[str, dict[str, Any]],
                     after: dict[str, dict[str, Any]], compatible: dict[bytes, str],
                     used_compatible: set[str]) -> tuple[Any, set[str]]:
    changed = set()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        observation = value.get("observation")
        canonical_identity = observation.get("id") if isinstance(observation, dict) else None
        direct = canonical_identity in after
        if isinstance(observation, dict) and not direct:
            canonical_identity = compatible.get(compatibility_identity(observation))
        if isinstance(observation, dict) and canonical_identity in after:
            if direct:
                if observation != before[canonical_identity]:
                    raise ValueError(f"Native embedded count preimage differs: {canonical_identity}")
                refreshed = copy.deepcopy(after[canonical_identity])
            else:
                if canonical_identity in used_compatible:
                    raise ValueError(f"Ambiguous approved native dependency: {canonical_identity}")
                refreshed = project_compatible_observation(
                    observation, before[canonical_identity], after[canonical_identity])
                used_compatible.add(canonical_identity)
            properties, paths = value.get("properties"), value.get("paths", {})
            if not isinstance(properties, dict):
                raise ValueError(f"Native projected properties missing: {canonical_identity}")
            original_identity = {key: properties.get(key) for key in IDENTITY_VIEW_KEYS}
            updated = projected(properties, refreshed["view"])
            put(updated, paths.get("count"), refreshed["count"]["value"])
            put(updated, paths.get("denominator"),
                (refreshed.get("denominator") or {}).get("value"))
            put(updated, paths.get("rate"), refreshed["view"].get("reported_pct"))
            if {key: updated.get(key) for key in IDENTITY_VIEW_KEYS} != original_identity:
                raise ValueError(f"Native projection metadata changed: {canonical_identity}")
            value["properties"] = updated
            value["observation"] = refreshed
            changed.add(canonical_identity)
        for child in value.values():
            visit(child)

    visit(data)
    return data, changed


def refresh_source_rows(data: Any, before: dict[str, dict[str, Any]],
                        after: dict[str, dict[str, Any]]) -> tuple[Any, set[str]]:
    if not isinstance(data, list):
        return data, set()
    keyed = {}
    for identity, row in after.items():
        view = row.get("view", {})
        key = (view.get("state_code"), view.get("key"))
        if all(key):
            keyed[key] = identity
    changed = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        identity = keyed.get((row.get("state_code"), row.get("key")))
        if not identity:
            continue
        old_view, new_view = before[identity]["view"], after[identity]["view"]
        for key, value in row.items():
            if key not in IDENTITY_VIEW_KEYS and key in old_view and old_view[key] != value:
                raise ValueError(f"Source-reporting preimage differs: {identity}:{key}")
        original_identity = {key: row.get(key) for key in IDENTITY_VIEW_KEYS}
        row.update(projected(row, new_view))
        if {key: row.get(key) for key in IDENTITY_VIEW_KEYS} != original_identity:
            raise ValueError(f"Source-reporting projection metadata changed: {identity}")
        changed.add(identity)
    return data, changed


def family_selector_matches(source: dict[str, Any], canonical: dict[str, Any]) -> bool:
    if source.get("selector") == canonical.get("source", {}).get("selector"):
        return True
    if canonical.get("geography", {}).get("state_code") != "WY":
        return False
    native = canonical.get("view", {}).get("native_record", {})
    ballots = native.get("ballot_count_query", {})
    expected = {
        "native_query": "wy-precinct-ballots",
        "native_selector": {
            "county": ballots.get("county"),
            "precinct": ballots.get("precinct"),
        },
        "source_rows": ballots.get("source_rows"),
    }
    return all(value is not None for value in expected["native_selector"].values()) \
        and expected["source_rows"] is not None and source.get("selector") == expected


def family_frame_matches(native: dict[str, Any], canonical: dict[str, Any],
                         source_id: str) -> bool:
    view, source = native.get("view", {}), native.get("source", {})
    canonical_view, canonical_source = canonical.get("view", {}), canonical.get("source", {})
    if (
        native.get("id") != canonical.get("id")
        or native.get("election") != canonical.get("election")
        or native.get("measure") != canonical.get("measure")
        or native.get("count") != canonical.get("count")
        or native.get("denominator") != canonical.get("denominator")
        or source.get("id") != source_id
        or canonical_source.get("id") != source_id
        or source.get("input_sha256") != canonical_source.get("input_sha256")
        or source.get("url") != canonical_source.get("url")
        or source.get("classification") != canonical_source.get("classification")
        or not family_selector_matches(source, canonical)
        or source.get("fields") != view
        or view.get("native_record") != canonical_view.get("native_record")
        or view.get("ballots") != canonical_view.get("ballots")
        or view.get("denominator") != canonical_view.get("denominator")
        or view.get("registered") != canonical_view.get("registered")
        or view.get("reported_pct") != canonical_view.get("reported_pct")
        or view.get("source_url") != canonical_view.get("source_url")
        or any(view.get(key) != canonical_view.get(key)
               for key in ("state_code", "key", "unit", "year"))
    ):
        return False
    native_pin = (view.get("native_record") or {}).get("native_original_pin")
    if native_pin is not None and native_pin.get("sha256") != source.get("input_sha256"):
        return False
    native_geo, canonical_geo = native.get("geography", {}), canonical.get("geography", {})
    if any(native_geo.get(key) != canonical_geo.get(key)
           for key in ("id", "name", "state_code", "level", "join")):
        return False
    return (
        view.get("maps_approved") is not True
        and view.get("cast_ballot_count_qualified", False) is not True
        and view.get("unique_voter_count_qualified", False) is not True
    )


def project_family_observation(native: dict[str, Any],
                               previous: dict[str, Any],
                               current: dict[str, Any],
                               source_id: str) -> dict[str, Any]:
    previous_match = family_frame_matches(native, previous, source_id)
    current_match = family_frame_matches(native, current, source_id)
    if not previous_match and not current_match:
        raise ValueError(f"Reviewed family native frame differs: {native.get('id')}")
    result = copy.deepcopy(native)
    result["count"] = copy.deepcopy(current["count"])
    result["denominator"] = copy.deepcopy(current.get("denominator"))
    for key in ("literal", "reported_units", "total_units", "complete"):
        if key in current.get("reporting_status", {}):
            result["reporting_status"][key] = copy.deepcopy(current["reporting_status"][key])
    result["source_clock"]["literal"] = current.get("source_clock", {}).get("literal")
    result["source_clock"]["timezone"] = current.get("source_clock", {}).get("timezone")
    result["view"] = projected(result["view"], current["view"])
    for key in ("ballots", "denominator", "registered", "reported_pct",
                "source_url", "native_record"):
        if key in result["view"]:
            result["view"][key] = copy.deepcopy(current["view"].get(key))
    result["source"] = {
        key: copy.deepcopy(value) for key, value in current["source"].items()
        if key != "fields"
    }
    result["source"]["fields"] = copy.deepcopy(result["view"])
    if observation_identity(result) != observation_identity(native):
        raise ValueError(f"Reviewed family native identity changed: {native.get('id')}")
    return result


def family_source_frame_matches(row: dict[str, Any], canonical: dict[str, Any]) -> bool:
    view = canonical.get("view", {})
    return (
        all(row.get(key) == view.get(key) for key in (
            "ballots", "registered", "reported_pct", "source_url", "native_record"))
        and all(row[key] == view.get(key)
                for key in ("state_code", "key", "unit") if key in row)
    )


def reviewed_family_contexts(before_files: dict[str, bytes],
                             after_files: dict[str, bytes],
                             native_files: dict[str, bytes],
                             native_index: dict[str, Any],
                             changed_before: dict[str, dict[str, Any]],
                             changed_after: dict[str, dict[str, Any]],
                             changed_states: set[str]) -> dict[str, dict[str, Any]]:
    before_index = read_json("index.json", before_files["index.json"])
    after_index = read_json("index.json", after_files["index.json"])
    contexts = {}
    for code, source_id in REVIEWED_FAMILY_SOURCE_IDS.items():
        if code not in changed_states:
            continue
        changed = {
            identity for identity, row in changed_after.items()
            if row.get("source", {}).get("id") == source_id
        }
        if not changed:
            continue
        if any(changed_before[identity].get("source", {}).get("id") != source_id
               for identity in changed):
            raise ValueError(f"Reviewed family source identity changed: {code}")
        old_all = state_records(before_files, before_index, code)
        new_all = state_records(after_files, after_index, code)
        old = {identity: row for identity, row in old_all.items()
               if row.get("source", {}).get("id") == source_id}
        new = {identity: row for identity, row in new_all.items()
               if row.get("source", {}).get("id") == source_id}
        if not old or set(old) != set(new):
            raise ValueError(f"Reviewed family canonical membership changed: {code}")
        declaration = native_index.get("reporting_tables", {}).get(code)
        name = declaration.get("file") if isinstance(declaration, dict) else None
        if (
            not isinstance(name, str)
            or name not in native_files
            or pin(native_files[name]) != {
                key: declaration.get(key) for key in ("bytes", "sha256")
            }
        ):
            raise ValueError(f"Reviewed family reporting-table pin changed: {code}")
        table = read_json(name, native_files[name])
        records = table.get("records") if isinstance(table, dict) else None
        if (
            not isinstance(table, dict)
            or
            table.get("contract") != "participation.reporting_units.v1"
            or table.get("state_code") != code
            or not isinstance(records, list)
            or len(records) != declaration.get("rows")
        ):
            raise ValueError(f"Reviewed family reporting-table inventory changed: {code}")
        table_rows = {}
        for record in records:
            observation = record.get("observation") if isinstance(record, dict) else None
            identity = observation.get("id") if isinstance(observation, dict) else None
            properties = record.get("properties") if isinstance(record, dict) else None
            if not identity or identity in table_rows or not isinstance(properties, dict):
                raise ValueError(f"Duplicate reviewed family native identity: {code}")
            for key in IDENTITY_VIEW_KEYS:
                if key in properties and properties.get(key) != observation.get("view", {}).get(key):
                    raise ValueError(f"Reviewed family property identity changed: {identity}")
            if not (
                family_frame_matches(observation, old.get(identity, {}), source_id)
                or family_frame_matches(observation, new.get(identity, {}), source_id)
            ):
                raise ValueError(f"Reviewed family native vector differs: {identity}")
            table_rows[identity] = record
        if set(table_rows) != set(old):
            raise ValueError(f"Reviewed family reporting-table membership changed: {code}")
        context = {
            "code": code, "source_id": source_id, "old": old, "new": new,
            "table_name": name, "table_rows": table_rows,
        }
        source_name = f"source-reporting/{code}.json.gz"
        source_declaration = native_index.get("reporting_sources", {}).get(code)
        if code == "WY" and source_name not in native_files:
            raise ValueError(f"Reviewed family source-reporting file is missing: {code}")
        if source_name in native_files:
            if (
                not isinstance(source_declaration, dict)
                or pin(native_files[source_name])["sha256"]
                    != source_declaration.get("sha256")
            ):
                raise ValueError(f"Reviewed family source-reporting pin changed: {code}")
            source_rows = read_json(source_name, native_files[source_name])
            if not isinstance(source_rows, list) or len(source_rows) != source_declaration.get("rows"):
                raise ValueError(f"Reviewed family source-reporting inventory changed: {code}")
            keyed = {}
            for identity, row in new.items():
                key = row.get("view", {}).get("state_code"), row.get("view", {}).get("key")
                if not all(key) or key in keyed:
                    raise ValueError(f"Duplicate reviewed family canonical key: {code}")
                keyed[key] = identity
            seen = set()
            for row in source_rows:
                if not isinstance(row, dict):
                    raise ValueError(f"Malformed reviewed family source row: {code}")
                identity = keyed.get((row.get("state_code"), row.get("key")))
                if identity is None or identity in seen:
                    raise ValueError(f"Duplicate reviewed family source key: {code}")
                if not (
                    family_source_frame_matches(row, old[identity])
                    or family_source_frame_matches(row, new[identity])
                ):
                    raise ValueError(f"Reviewed family source vector differs: {identity}")
                if row != table_rows[identity]["properties"]:
                    raise ValueError(f"Reviewed family source/table row differs: {identity}")
                seen.add(identity)
            if seen != set(old):
                raise ValueError(f"Reviewed family source-reporting membership changed: {code}")
            context["source_name"] = source_name
            context["source_keys"] = keyed
        contexts[code] = context
    return contexts


def refresh_family_table(data: dict[str, Any], context: dict[str, Any]) -> tuple[
        dict[str, Any], set[str]]:
    changed = set()
    for record in data["records"]:
        identity = record["observation"]["id"]
        original = copy.deepcopy(record["observation"])
        refreshed = project_family_observation(
            original, context["old"][identity], context["new"][identity],
            context["source_id"])
        properties, paths = record["properties"], record.get("paths", {})
        original_identity = {key: properties.get(key) for key in IDENTITY_VIEW_KEYS}
        updated = projected(properties, refreshed["view"])
        put(updated, paths.get("count"), refreshed["count"]["value"])
        put(updated, paths.get("denominator"),
            (refreshed.get("denominator") or {}).get("value"))
        put(updated, paths.get("rate"), refreshed["view"].get("reported_pct"))
        if {key: updated.get(key) for key in IDENTITY_VIEW_KEYS} != original_identity:
            raise ValueError(f"Reviewed family projection metadata changed: {identity}")
        record["observation"], record["properties"] = refreshed, updated
        if record["observation"] != original:
            changed.add(identity)
    return data, changed


def refresh_family_source(data: list[dict[str, Any]], context: dict[str, Any]) -> tuple[
        list[dict[str, Any]], set[str]]:
    changed = set()
    for row in data:
        identity = context["source_keys"][(row.get("state_code"), row.get("key"))]
        original = copy.deepcopy(row)
        original_identity = {key: row.get(key) for key in IDENTITY_VIEW_KEYS}
        row.update(projected(row, context["new"][identity]["view"]))
        row["registered"] = copy.deepcopy(context["new"][identity]["view"].get("registered"))
        if {key: row.get(key) for key in IDENTITY_VIEW_KEYS} != original_identity:
            raise ValueError(f"Reviewed family source identity changed: {identity}")
        if row != original:
            changed.add(identity)
    return data, changed


def refresh_reference(data: dict[str, Any], before_files: dict[str, bytes],
                      after_files: dict[str, bytes]) -> tuple[dict[str, Any], set[str]]:
    """Revalidate complete reference observations before rebinding their source shard."""
    original = copy.deepcopy(data)
    code, origin = data.get("state_code"), data.get("source_counts", {})
    review = data.get("review", {})
    if (data.get("id") != f"precinct/{code}" or not isinstance(origin, dict)
            or type(origin.get("bytes")) is not int or origin["bytes"] <= 0
            or not isinstance(origin.get("sha256"), str) or len(origin["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in origin["sha256"])
            or not isinstance(origin.get("source_id"), str) or not origin["source_id"]
            or type(origin.get("source_rows")) is not int or origin["source_rows"] <= 0
            or review.get("reviewed") is not True
            or review.get("scope") != "public_authoritative_reference_context"
            or review.get("matching") != "exact_literal_only"
            or review.get("source_observations_preserved") is not True
            or review.get("legal_election_boundaries_certified") is not False
            or review.get("rates_approved") is not False):
        raise ValueError("Unqualified separate reference refresh")
    declarations, groups = [], []
    for files in (before_files, after_files):
        index = read_json("index.json", files["index.json"])
        declaration = index["states"].get(code, {})
        name = declaration.get("file")
        if (name != origin.get("file") or name not in files
                or pin(files[name]) != {key: declaration.get(key) for key in ("bytes", "sha256")}):
            raise ValueError("Separate reference canonical source shard differs")
        records = state_records(files, index, code)
        groups.append({identity: row for identity, row in records.items()
                       if row.get("source", {}).get("id") == origin["source_id"]})
        declarations.append(declaration)
    old_records, new_records = groups
    if (len(old_records) != origin["source_rows"] or set(old_records) != set(new_records)
            or len(data.get("rows", [])) + len(data.get("held_rows", [])) != len(old_records)):
        raise ValueError("Separate reference source inventory differs")
    seen, keys = set(), set()
    for row in data["rows"]:
        observation = row.get("observation", {})
        identity = observation.get("id")
        old, new = old_records.get(identity), new_records.get(identity)
        properties = row.get("properties")
        if (old is None or observation != old or identity in seen
                or observation_identity(old) != observation_identity(new)
                or row.get("key") != old["geography"]["name"] or row["key"] in keys
                or row.get("geometry_type") not in ("Polygon", "MultiPolygon")
                or old["denominator"] is not None or new["denominator"] is not None
                or not isinstance(properties, dict)
                or properties.get("key") != row["key"]
                or properties.get("source_count_observation_id") != identity
                or properties.get("maps_approved") is not True
                or properties.get("reference_context_only") is not True
                or properties.get("legal_election_boundaries_certified") is not False):
            raise ValueError("Separate reference observation or qualification preimage differs")
        for key, value in old["view"].items():
            if key != "maps_approved" and key in properties and properties[key] != value:
                raise ValueError(f"Separate reference display preimage differs: {identity}:{key}")
        properties.update({key: copy.deepcopy(value) for key, value in new["view"].items()
                           if key != "maps_approved"})
        row["observation"] = copy.deepcopy(new)
        seen.add(identity)
        keys.add(row["key"])
    for held in data["held_rows"]:
        identity = held.get("observation_id")
        old, new = old_records.get(identity), new_records.get(identity)
        if (old is None or identity in seen or held.get("native_label") != old["geography"]["name"]
                or observation_identity(old) != observation_identity(new)
                or not isinstance(held.get("reason"), str) or not held["reason"]):
            raise ValueError("Separate reference held identity or qualification differs")
        seen.add(identity)
    if seen != set(old_records):
        raise ValueError("Separate reference source disposition missing")
    # Full observation checks also allow repair of a previously stale shard pin.
    origin.update({key: declarations[1][key] for key in ("file", "bytes", "sha256")})
    return data, set(new_records) if data != original else set()


def refresh(before_count_files: dict[str, bytes], after_count_files: dict[str, bytes],
            native_files: dict[str, bytes]) -> dict[str, bytes]:
    """Return a deterministic native successor with only existing approved count rows refreshed."""
    before, after, changed_states = changed_records(before_count_files, after_count_files)
    output = dict(native_files)
    index = read_json("index.json", native_files["index.json"])
    if index.get("contract") != "participation.native_index.v1" or index.get("year") != 2026:
        raise ValueError("Wrong native binding index contract or election")
    original_static = copy.deepcopy(index)
    family_contexts = reviewed_family_contexts(
        before_count_files, after_count_files, native_files, index,
        before, after, changed_states)
    family_files = {
        context[key]: (context, key)
        for context in family_contexts.values()
        for key in ("table_name", "source_name") if key in context
    }
    compatible = compatibility_map(before)
    used_compatible = set()
    changed_files, refreshed_ids = set(), set()
    for name in sorted(native_files):
        if not name.startswith(NATIVE_PREFIXES) or not name.endswith(".json.gz"):
            continue
        data = read_json(name, native_files[name])
        if name in family_files:
            context, role = family_files[name]
            if role == "table_name":
                data, touched = refresh_family_table(data, context)
            else:
                data, touched = refresh_family_source(data, context)
        elif isinstance(data, dict) and data.get("contract") == "participation.reference_bindings.v1":
            data, touched = refresh_reference(data, before_count_files, after_count_files)
        else:
            data, embedded = refresh_embedded(
                data, before, after, compatible, used_compatible)
            data, source_rows = refresh_source_rows(data, before, after)
            touched = embedded | source_rows
        if touched:
            output[name] = compressed(data)
            changed_files.add(name)
            refreshed_ids.update(touched & set(after))
    if not changed_files:
        return output
    for identity in refreshed_ids:
        if identity not in before or identity not in after:
            raise ValueError(f"Native successor introduced a count identity: {identity}")
    for layer in index.get("layers", {}).values():
        name = layer["file"]
        if name in changed_files:
            layer.update(pin(output[name]))
            layer["coverage"] = coverage(read_json(name, output[name])["rows"])
    for table in index.get("reporting_tables", {}).values():
        name = table["file"]
        if name in changed_files:
            table.update(pin(output[name]))
            records = read_json(name, output[name])["records"]
            table["coverage"] = {**coverage(records), "source_rows": len(records)}
            table["rows"] = len(records)
    for code, source in index.get("reporting_sources", {}).items():
        name = f"source-reporting/{code}.json.gz"
        if name in changed_files:
            source.update(pin(output[name]))
            source["rows"] = len(read_json(name, output[name]))
    output["index.json"] = encoded(index)
    if original_static.get("config") != index.get("config") \
            or original_static.get("county_bindings") != index.get("county_bindings") \
            or original_static.get("municipal_bindings") != index.get("municipal_bindings"):
        raise ValueError("Native geometry, holds or county/municipal bindings changed")
    if "dataset.json" in native_files:
        descriptor = read_json("dataset.json", native_files["dataset.json"])
        declarations = {name: pin(body) for name, body in sorted(output.items())
                        if name != "dataset.json"}
        descriptor["files"] = declarations
        descriptor["index"] = {"file": "index.json", **declarations["index.json"]}
        descriptor["version"] = hashlib.sha256(encoded({
            "files": declarations, "contract": descriptor["record_contract"],
        })).hexdigest()
        output["dataset.json"] = encoded(descriptor)
    return output


__all__ = ["refresh"]
