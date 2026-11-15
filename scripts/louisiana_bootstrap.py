"""Authority-gated Louisiana count onboarding for default collection and replay."""

import copy
import gzip
import json
import re

from scripts.participation_count_additions import append_reviewed
from scripts.participation_intake.contract import encoded, pin


AUTHORITY_CONTRACT = "participation.louisiana_route_authority.v1"
ADDITION_CONTRACT = "participation.louisiana_reviewed_addition.v1"
IDENTITY = "LA-native-post-election-bootstrap"


EXPECTED_AUTHORITY = {
    "contract": AUTHORITY_CONTRACT,
    "status": "verified",
    "state_navigation_url": (
        "https://www.sos.la.gov/elections-voting/"
        "statewide-post-election-statistics"),
    "state_navigation_pin": {
        "bytes": 78111,
        "sha256": "bbac646fabb26a648a40f055664a3e7c2b6537cc8a430094f6f4a2c7716ec7b7",
    },
    "parish_navigation_url": (
        "https://www.sos.la.gov/elections-voting/"
        "post-election-statistics-by-parish"),
    "parish_navigation_pin": {
        "bytes": 78149,
        "sha256": "ed1430b6f3043037ed3d64d6d84d4bd282bc968889f40c4c61cd86d3db0a54ba",
    },
    "publisher_script_url": "https://www.sos.la.gov/scripts/sosscript.js",
    "publisher_script_pin": {
        "bytes": 5288,
        "sha256": "ed8f01cef8363a1889213250df9dc1e7bceedbfa9606ee782106f6051b19bb46",
    },
    "authority_receipt_pin": {
        "bytes": 2244,
        "sha256": "5cb5abb0c9971a6fba5e7fed75eddead1002c9d7272d7f4121443b7d45a7c3b5",
    },
    "state_index_url": (
        "https://electionstatistics.sos.la.gov/default.aspx?"
        "Stats=Post_Election_Statistics&Type=Statewide"),
    "parish_index_url": (
        "https://electionstatistics.sos.la.gov/default.aspx?"
        "Stats=Post_Election_Statistics&Type=Parish"),
    "state_workbook_url": (
        "https://electionstatistics.sos.la.gov/Data/Post_Election_Statistics/"
        "statewide/2026_1103_sta.xlsx"),
    "parish_workbook_url": (
        "https://electionstatistics.sos.la.gov/Data/Post_Election_Statistics/"
        "parish/2026_1103_par.xlsx"),
}


def authority_decision(authority):
    if not isinstance(authority, dict):
        return {
            "status": "held",
            "code": "missing_exact_official_production_navigation",
            "message": (
                "Accepted production-host context exists, but no exact retained official "
                "navigation binds the current post-election index routes."
            ),
        }
    if authority.get("contract") != AUTHORITY_CONTRACT:
        raise ValueError("Unknown Louisiana route-authority contract")
    if authority.get("status") != "verified":
        return {
            "status": "held",
            "code": authority.get(
                "code", "missing_exact_official_production_navigation"
            ),
            "message": authority.get("message"),
        }
    if authority != EXPECTED_AUTHORITY:
        raise ValueError("Louisiana verified route authority differs from review")
    return {"status": "verified", "authority": copy.deepcopy(authority)}

def _compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=6, mtime=0))
    body[9] = 3
    return bytes(body)


def addition_payload(files, bodies):
    from scripts import louisiana_onboarding
    from scripts import results_native_louisiana_runtime as runtime

    index = json.loads(files["index.json"])
    declaration = index["states"]["LA"]
    state = json.loads(gzip.decompress(files[declaration["file"]]))
    rows = runtime.canonical_rows(bodies)
    binding = louisiana_onboarding._binding(
        state, rows, pin(files[declaration["file"]])
    )
    return {
        "contract": ADDITION_CONTRACT,
        "rows": rows,
        "binding": binding,
        "source_workbooks": {
            "statewide": {
                "url": runtime.source.STATE_XLSX_URL,
                **pin(bodies[runtime.source.STATE_XLSX_URL]),
            },
            "parish": {
                "url": runtime.source.PARISH_XLSX_URL,
                **pin(bodies[runtime.source.PARISH_XLSX_URL]),
            },
        },
    }


def apply_addition(files, payload):
    if (
        not isinstance(payload, dict)
        or payload.get("contract") != ADDITION_CONTRACT
        or not isinstance(payload.get("rows"), list)
        or not isinstance(payload.get("binding"), dict)
        or set(payload.get("source_workbooks", {})) != {"statewide", "parish"}
    ):
        raise ValueError("Malformed Louisiana reviewed addition payload")
    result = dict(files)
    index = json.loads(files["index.json"])
    declaration = index["states"]["LA"]
    path = declaration["file"]
    state = json.loads(gzip.decompress(files[path]))
    old = copy.deepcopy(state)
    existing = [
        row for row in state["records"]
        if row.get("source", {}).get("id")
            == "la-sos-post-election-statistics-2026-11-03"
    ]
    if existing:
        if (
            len(existing) != 3783
            or {row["id"] for row in existing}
                != {row["id"] for row in payload["rows"]}
        ):
            raise ValueError("Existing Louisiana reviewed addition identity differs")
        return files
    source = {
        "rows": payload["rows"],
        "baseline_source_ids": [],
        "addition": payload["binding"],
    }
    state, additions = append_reviewed(state, source, pin(files[path]))
    if additions != 3783 or state["records"][: len(old["records"])] != old["records"]:
        raise ValueError("Louisiana addition changed an accepted record")
    for mode, old_frame in old["views"].items():
        frame = state["views"][mode]
        for partition in ("counties", "precincts", "nongeographic"):
            if frame[partition][: len(old_frame[partition])] != old_frame[partition]:
                raise ValueError("Louisiana addition changed accepted mode membership")
            if mode != "official" and frame[partition] != old_frame[partition]:
                raise ValueError("Louisiana # VOTING entered a non-official mode")
    body = _compressed(state)
    result[path] = body
    declaration.update(pin(body), records=len(state["records"]))
    by_id = {row["id"]: row for row in state["records"]}
    for mode, frame in state["views"].items():
        description = declaration["views"][mode]
        for partition in ("counties", "precincts", "nongeographic"):
            selected = [by_id[identity] for identity in frame[partition]]
            description[partition] = len(selected)
            description["dispositions"][partition] = {
                "reported": sum(
                    row["count"]["status"] == "reported" for row in selected
                ),
                "unknown": sum(
                    row["count"]["status"] == "unknown" for row in selected
                ),
                "withheld": sum(
                    row["count"]["status"] == "withheld" for row in selected
                ),
                "qualified_fractions": 0,
                "geography_levels": sorted(
                    {row["geography"]["level"] for row in selected}
                ),
            }
    index["coverage"]["LA"] = {
        "records": len(state["records"]),
        "reported": sum(
            row["count"]["status"] == "reported" for row in state["records"]
        ),
        "unknown": sum(
            row["count"]["status"] == "unknown" for row in state["records"]
        ),
        "withheld": sum(
            row["count"]["status"] == "withheld" for row in state["records"]
        ),
        "zeros": sum(row["count"]["value"] == 0 for row in state["records"]),
        "qualified_fractions": 0,
    }
    index.setdefault("extensions", []).append(
        {
            "id": "louisiana-post-election-voters-participating-20261115-01",
            "state_code": "LA",
            "new_observations": 3783,
            "state_parents_unselected": 1,
            "parish_parents": 64,
            "native_precincts": 3718,
            "qualified_new_geometry": False,
            "qualified_new_rates": False,
            "frontend_activation_approved": False,
            "source_workbooks": copy.deepcopy(payload["source_workbooks"]),
        }
    )
    result["index.json"] = encoded(index)
    return result


def collect_bootstrap(collector, baseline, authority):
    from scripts import results_native_louisiana as source
    from scripts import results_native_louisiana_runtime as runtime

    decision = authority_decision(authority)
    if decision["status"] != "verified":
        return {
            "status": "authority_hold",
            "data": None,
            "source": None,
            "error": decision["code"],
            "first_observed_at": None,
            "authority": decision,
        }

    def parse(state_body):
        bodies = {source.STATE_XLSX_URL: state_body}
        for url in (
            source.ELECTION_DATES_URL,
            source.STATE_INDEX_URL,
            source.PARISH_INDEX_URL,
            source.PARISH_XLSX_URL,
        ):
            bodies[url], _ = collector.acquire(url)
        rows = runtime.canonical_rows(bodies)

        def acquire(url):
            return bodies[url], {"url": url, **pin(bodies[url])}

        data = runtime.statistics(
            state_body,
            rows,
            source.STATE_XLSX_URL,
            acquire=acquire,
        )
        data["reviewed_count_addition"] = addition_payload(baseline, bodies)
        data["route_authority"] = decision["authority"]
        return data

    return collector.capture(IDENTITY, source.STATE_XLSX_URL, parse)


__all__ = [
    "ADDITION_CONTRACT",
    "AUTHORITY_CONTRACT",
    "IDENTITY",
    "addition_payload",
    "apply_addition",
    "authority_decision",
    "collect_bootstrap",
]
