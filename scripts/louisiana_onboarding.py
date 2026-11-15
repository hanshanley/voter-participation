"""One-time exact-preimage Louisiana canonical count addition."""

import copy
import gzip
import json

from scripts.participation_count_additions import append_reviewed
from scripts.participation_intake.contract import encoded, pin
from scripts import results_native_louisiana_runtime as louisiana


EXTENSION_ID = "louisiana-post-election-voters-participating-20261115-01"


def _compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=6, mtime=0))
    body[9] = 3
    return bytes(body)


def _disposition(rows):
    return {
        "reported": sum(row["count"]["status"] == "reported" for row in rows),
        "unknown": sum(row["count"]["status"] == "unknown" for row in rows),
        "withheld": sum(row["count"]["status"] == "withheld" for row in rows),
        "qualified_fractions": sum(
            bool(row["denominator"] and row["denominator"]["qualified"]) for row in rows
        ),
        "geography_levels": sorted({row["geography"]["level"] for row in rows}),
    }


def _binding(state, rows, baseline_pin):
    state_ids = [row["id"] for row in rows if row["geography"]["level"] == "state"]
    parishes = [
        row["id"] for row in rows if row["geography"]["level"] == "county_equivalent"
    ]
    precincts = [row["id"] for row in rows if row["geography"]["level"] == "precinct"]
    if len(state_ids) != 1 or len(parishes) != 64 or len(precincts) != 3718:
        raise ValueError("Louisiana reviewed addition scope changed")
    views = {}
    for mode, frame in state["views"].items():
        views[mode] = {}
        for partition in ("counties", "precincts", "nongeographic"):
            append = []
            if mode == "official" and partition == "counties":
                append = parishes
            elif mode == "official" and partition == "precincts":
                append = precincts
            views[mode][partition] = {
                "before": list(frame[partition]),
                "append": append,
            }
    return {
        "contract": "participation.reviewed_count_addition.v1",
        "baseline_shard": baseline_pin,
        "source_scope_review_evidence": (
            "Official retained Louisiana post-election workbooks: native # VOTING, "
            "one printed state parent, 64 printed parish parents and 3718 native precincts. "
            "No new geometry, rates, denominator, model or frontend approval."
        ),
        "records": {row["id"]: pin(encoded(row)) for row in rows},
        "views": views,
        "unselected": state_ids,
    }


def onboard(files, bodies):
    result = dict(files)
    index = json.loads(files["index.json"])
    if (
        index.get("contract") != "participation.count_index.v1"
        or index.get("year") != 2026
        or len(index.get("states", {})) != 51
    ):
        raise ValueError("Wrong or incomplete canonical count baseline")
    declaration = index["states"]["LA"]
    path = declaration["file"]
    state = json.loads(gzip.decompress(files[path]))
    old_state = copy.deepcopy(state)
    rows = louisiana.canonical_rows(bodies)
    source = {
        "rows": rows,
        "baseline_source_ids": [],
        "addition": _binding(state, rows, pin(files[path])),
    }
    state, additions = append_reviewed(state, source, pin(files[path]))
    if additions != 3783 or state["records"][: len(old_state["records"])] != old_state["records"]:
        raise ValueError("Louisiana reviewed addition changed an accepted record")
    for mode, old_frame in old_state["views"].items():
        current = state["views"][mode]
        for partition in ("counties", "precincts", "nongeographic"):
            if current[partition][: len(old_frame[partition])] != old_frame[partition]:
                raise ValueError("Louisiana reviewed addition changed an accepted mode membership")
            if mode != "official" and current[partition] != old_frame[partition]:
                raise ValueError("Louisiana native # VOTING entered a non-official mode")
    state_body = _compressed(state)
    result[path] = state_body
    declaration.update(pin(state_body), records=len(state["records"]))
    by_id = {row["id"]: row for row in state["records"]}
    for mode, frame in state["views"].items():
        description = declaration["views"][mode]
        for partition in ("counties", "precincts", "nongeographic"):
            selected = [by_id[identity] for identity in frame[partition]]
            description[partition] = len(selected)
            description["dispositions"][partition] = _disposition(selected)
        description["holds"] = len(frame["holds"])
        description["qualified"] = frame["qualified"]
    index["coverage"]["LA"] = {
        "records": len(state["records"]),
        "reported": sum(row["count"]["status"] == "reported" for row in state["records"]),
        "unknown": sum(row["count"]["status"] == "unknown" for row in state["records"]),
        "withheld": sum(row["count"]["status"] == "withheld" for row in state["records"]),
        "zeros": sum(row["count"]["value"] == 0 for row in state["records"]),
        "qualified_fractions": sum(
            bool(row["denominator"] and row["denominator"]["qualified"])
            for row in state["records"]
        ),
    }
    extension = {
        "id": EXTENSION_ID,
        "state_code": "LA",
        "new_observations": 3783,
        "state_parents_unselected": 1,
        "parish_parents": 64,
        "native_precincts": 3718,
        "qualified_new_geometry": False,
        "qualified_new_rates": False,
        "frontend_activation_approved": False,
        "source_workbooks": {
            "statewide": pin(bodies[louisiana.source.STATE_XLSX_URL]),
            "parish": pin(bodies[louisiana.source.PARISH_XLSX_URL]),
        },
    }
    if any(item.get("id") == EXTENSION_ID for item in index.get("extensions", [])):
        raise ValueError("Louisiana reviewed addition is already present")
    index.setdefault("extensions", []).append(extension)
    result["index.json"] = encoded(index)
    return result, {
        "added": additions,
        "state_parent": 1,
        "parish_parents": 64,
        "precincts": 3718,
        "old_records_retained": len(old_state["records"]),
        "source_id": louisiana.SOURCE_ID,
        "identity_pin": louisiana.CANONICAL_IDENTITY_PIN,
    }


__all__ = ["EXTENSION_ID", "onboard"]
