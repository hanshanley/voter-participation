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


def observation_identity(row: dict[str, Any]) -> bytes:
    denominator = row.get("denominator")
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
        "view": {key: row.get("view", {}).get(key) for key in IDENTITY_VIEW_KEYS},
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
            raise ValueError(f"Automatic refresh may update only existing count IDs: {code}")
        for identity in old:
            if old[identity] != new[identity]:
                if observation_identity(old[identity]) != observation_identity(new[identity]):
                    raise ValueError(f"Changed count identity, geography, label or qualification: {identity}")
                before[identity], after[identity] = old[identity], new[identity]
        changed_states.add(code)
    return before, after, changed_states


def compatibility_identity(row: dict[str, Any]) -> bytes | None:
    view = row.get("view", {})
    native = view.get("native_record")
    if not isinstance(native, dict):
        return None
    election = row.get("election", {})
    election_date = election.get("date") or view.get("source_election_date")
    if election_date is None and election.get("year") == 2026 \
            and election.get("type") == "general":
        election_date = "2026-11-03"
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
    if native.get("view", {}).get("native_record") != previous.get("view", {}).get("native_record"):
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
    result["view"] = projected(result["view"], current["view"])
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


def refresh(before_count_files: dict[str, bytes], after_count_files: dict[str, bytes],
            native_files: dict[str, bytes]) -> dict[str, bytes]:
    """Return a deterministic native successor with only existing approved count rows refreshed."""
    before, after, changed_states = changed_records(before_count_files, after_count_files)
    output = dict(native_files)
    if not before:
        return output
    index = read_json("index.json", native_files["index.json"])
    if index.get("contract") != "participation.native_index.v1" or index.get("year") != 2026:
        raise ValueError("Wrong native binding index contract or election")
    original_static = copy.deepcopy(index)
    compatible = compatibility_map(before)
    used_compatible = set()
    changed_files, refreshed_ids = set(), set()
    for name in sorted(native_files):
        if not name.startswith(NATIVE_PREFIXES) or not name.endswith(".json.gz"):
            continue
        data = read_json(name, native_files[name])
        data, embedded = refresh_embedded(
            data, before, after, compatible, used_compatible)
        data, source_rows = refresh_source_rows(data, before, after)
        touched = embedded | source_rows
        if touched:
            output[name] = compressed(data)
            changed_files.add(name)
            refreshed_ids.update(touched)
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
