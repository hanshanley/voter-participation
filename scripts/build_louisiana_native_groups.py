#!/usr/bin/env python3
"""Build the private Louisiana native early-group dataset from accepted facts."""

import argparse
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path


DATASET_ID = "source-native-la-early-group-data"
CONTRACT = "participation.louisiana_native_early_groups.v1"
OBSERVATION_CONTRACT = "participation.observation.v1"
SOURCE_ID = "la-sos-statewide-early-voting-statistical-report-2026-11-03"
SOURCE_URL = (
    "https://electionstatistics.sos.la.gov/Data/Early_Voting_Statistics/"
    "statewide/2026_1103_StatewideStats.pdf"
)
SOURCE_PDF_SHA256 = "03662b5a09ee09ca57b6806e7ba97e52561317f540dbc6ddafeb56d33f164390"
REFERENCE_SHA256 = "7eeec4d3ebb2ca1fd2897e5f914e925a3b1fb88748bc25c51bd7977bfd930eac"
EXPECTED = {
    "source-result.json": (910047, "4d74f813dfad9cb4fe29518a918ce967b0bd5b91d9efaa2062dbd48290eb3e71"),
    "source-native-facts.json": (37300, "205f430273d6e20747e6be96003e3c2755f07c66a28bab965b2c89fa9eb93dcb"),
    "source-independent-native.json": (29863, "b094ac0086656f60713b932f88edaf0f567027417ca0410e0fef37b496efa8e0"),
    "policy.json": (409, "633aa3677fb3e5b24b64cd011f51ec62fde6e8f1cd01a6219b50a5e5c0cd78f7"),
    "provenance.json": (1273, "ea87440e563c23a50716e3abc417aa56d7b21a60a72f5373fb2059875eebcf62"),
    "LA-reference.geojson.gz": (1288586, REFERENCE_SHA256),
}
FIELDS = (
    "VOTES", "WHITE", "BLACK", "OTHER", "MALE", "FEMALE", "DEM", "REP",
    "NO PARTY", "OTH", "INPER", "ABS", "UOCAVA IN", "UOCAVA OUT", "ASST D", "ASST I",
)
GROUPS = (
    ("WHITE", "race"), ("BLACK", "race"), ("OTHER", "race"),
    ("MALE", "sex"), ("FEMALE", "sex"),
    ("INPER", "native_method"), ("ABS", "native_method"),
)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode()


def pin_bytes(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def pin_file(path):
    return pin_bytes(path.read_bytes())


def gzip_bytes(body):
    return gzip.compress(body, compresslevel=9, mtime=0)


def load_json(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_inputs(root):
    for name, (size, sha256) in EXPECTED.items():
        require(pin_file(root / name) == {"bytes": size, "sha256": sha256},
            f"Changed accepted input: {name}")
    source = load_json(root / "source-result.json")
    spatial = load_json(root.parent / "source-results/complete-result.json")
    require(source["contract"] == "participation.louisiana_early_group_compositions.v1",
        "Changed source contract")
    require(len(source["native_count_cells"]) == 1040
        and len(source["source_profiles"]) == 65
        and len(source["group_compositions"]) == 455
        and len(source["state_coverage"]) == 51, "Incomplete accepted source facts")
    require(len(spatial["bindings"]) == 64
        and len(spatial["spatial_group_compositions"]) == 448
        and len(spatial["provider_comparisons"]) == 128
        and len(spatial["source_state_coverage"]) == 51, "Incomplete accepted spatial review")
    return source, spatial


def observation_id(source, election, geography, measure, mode):
    return hashlib.sha256(encoded([source, election, geography, measure, mode])).hexdigest()[:32]


def measure(field):
    if field == "INPER":
        return {"id": "native-inper", "literal": field, "kind": "early_activity",
            "mode": "in_person_early", "unit": "source-reported VOTES"}
    return {"id": "native-" + field.lower().replace(" ", "-"), "literal": field,
        "kind": "early_activity" if field == "VOTES" else "source_activity",
        "mode": "source_defined", "unit": "source-reported VOTES"}


def observation(profile, field, binding):
    parish = profile["scope_kind"] == "parish"
    geography_id = "LA:" + (profile["native_code"] if parish else "STATE")
    geographic = {
        "id": geography_id,
        "name": binding["reference_name"] if parish else "Louisiana",
        "state_code": "LA",
        "level": "county_equivalent" if parish else "state",
        "parent_id": "LA:STATE" if parish else None,
        "join": {
            "status": "approved" if parish else "nongeographic",
            "reference_id": REFERENCE_SHA256 if parish else None,
            "feature_key": binding["reference_key"] if parish else None,
            "evidence": "reviewed explicit native-name/context identity binding" if parish else None,
        },
    }
    native_measure = measure(field)
    value = profile["raw_counts"][field]
    return {
        "contract": OBSERVATION_CONTRACT,
        "id": observation_id(SOURCE_ID, "LA-2026-11-03-general",
            geography_id, native_measure["id"], native_measure["mode"]),
        "election": {"id": "LA-2026-11-03-general", "year": 2026,
            "date": "2026-11-03", "type": "general",
            "qualification": "native"},
        "geography": geographic,
        "measure": native_measure,
        "count": {"value": value, "status": "reported", "literal": value},
        "denominator": None,
        "source_clock": {"literal": profile["source_print_clock"], "timezone": None},
        "reporting_status": {
            "literal": "64 parish rows plus separate state parent; all 16 printed parent controls reconcile",
            "reported_units": 64, "total_units": 64, "complete": True,
        },
        "source": {
            "id": SOURCE_ID, "url": SOURCE_URL, "input_sha256": SOURCE_PDF_SHA256,
            "selector": {"page": profile["page"], "native_label": profile["native_label"],
                "native_code": profile["native_code"], "field": field},
            "classification": "public_aggregate",
            "fields": {"native_field": field, "native_value": value,
                "filter_begin": profile["report_filter_begin"],
                "filter_end": profile["report_filter_end"]},
        },
        "quality": {"conflicts": [], "notes": [
            "Native early/absentee-report count, not full-election ballots or independently unique people.",
            "Native ABS is not qualified or relabelled as mail returned.",
            "Party fields are accounting categories, not vote choice.",
            "Source parish codes 01-64 are not FIPS.",
        ]},
    }


def validate_observations(rows):
    require(len(rows) == 1040 and len({row["id"] for row in rows}) == 1040,
        "Observation inventory or identity differs")
    for row in rows:
        require(row["contract"] == OBSERVATION_CONTRACT
            and row["denominator"] is None
            and row["count"]["status"] == "reported"
            and isinstance(row["count"]["value"], int)
            and row["count"]["value"] >= 0, "Invalid typed count observation")
        require(row["measure"]["literal"] != "ABS"
            or row["measure"]["mode"] == "source_defined", "ABS promoted to mail returned")
        require(row["source_clock"]["timezone"] is None
            and row["source"]["classification"] == "public_aggregate", "Invented source provenance")


def build(inputs, source_results, output):
    source, spatial = verify_inputs(inputs)
    require(pin_file(source_results / "complete-result.json") == {
        "bytes": 840017,
        "sha256": "db8dd5ee2f174241c7745405f77df7886b356e9dc82b8b083a14e7bdfc06a616",
    }, "Changed complete spatial result")
    output.mkdir(parents=True, exist_ok=False)
    (output / "states").mkdir()
    (output / "references").mkdir()
    bindings = {row["source_key"]: row for row in spatial["bindings"]}
    compositions = {}
    accounts = {}
    for row in source["group_compositions"]:
        compositions.setdefault(row["source_key"], []).append(row)
    for row in source["margin_accounting"]:
        accounts.setdefault(row["source_key"], []).append(row)
    profiles = []
    observations = []
    for profile in source["source_profiles"]:
        binding = bindings.get(profile["source_key"])
        if profile["scope_kind"] == "parish":
            require(binding and binding["disposition"] == "qualified_contextual_name_binding",
                "Missing explicit parish/context binding")
        own_groups = compositions[profile["source_key"]]
        require(len(own_groups) == 7, "Changed seven-group profile")
        own_accounts = accounts[profile["source_key"]]
        require(len(own_accounts) == 4, "Changed margin accounting")
        residuals = {row["dimension"]: row["signed_arithmetic_residual"] for row in own_accounts}
        profiles.append({
            "scope_kind": profile["scope_kind"],
            "source_key": profile["source_key"],
            "native_label": profile["native_label"],
            "native_code": profile["native_code"],
            "page": profile["page"],
            "reference": None if not binding else {
                "feature_key": binding["reference_key"],
                "name": binding["reference_name"],
                "reference_sha256": binding["reference_sha256"],
                "native_code_is_fips": False,
                "context_not_2026_voting_precinct": True,
            },
            "votes": profile["source_votes"],
            "native_fields": profile["raw_counts"],
            "groups": [{
                "native_group": row["native_group"], "dimension": row["dimension"],
                "count": row["native_count"], "share_of_own_native_votes": row["source_composition_pct"],
                "denominator": row["denominator"], "turnout_rate": None,
            } for row in own_groups],
            "margin_residuals": residuals,
            "source_clock": {"literal": profile["source_print_clock"], "timezone": None},
            "query_filter": {"begin": profile["report_filter_begin"],
                "end": profile["report_filter_end"],
                "observed_voting_period": False, "finality_claim": False},
        })
        for field in FIELDS:
            observations.append(observation(profile, field, binding or {}))
    validate_observations(observations)
    parent = next(row for row in profiles if row["scope_kind"] == "state_parent")
    parishes = [row for row in profiles if row["scope_kind"] == "parish"]
    require(parent["votes"] == 536190 and len(parishes) == 64
        and parent["native_fields"]["INPER"] + parent["native_fields"]["ABS"] == parent["votes"]
        and parent["margin_residuals"]["sex"] == 278
        and sum(row["margin_residuals"]["sex"] != 0 for row in parishes) == 37, "Changed controls")
    zero_cells = sum(value == 0 for row in profiles for value in row["native_fields"].values())
    require(zero_cells == 21, "Changed real zero inventory")
    state = {
        "contract": CONTRACT, "state_code": "LA", "year": 2026,
        "source": {
            "title": "Statewide Early Voting Statistical Report",
            "url": SOURCE_URL, "original_pdf_sha256": SOURCE_PDF_SHA256,
            "original_template_redistributed": False,
            "replay_basis": "complete permitted reviewed aggregate facts",
        },
        "state_parent": parent, "parishes": parishes,
        "coverage": source["state_coverage"],
        "provider_comparisons": spatial["provider_comparisons"],
        "source_scope_decisions": spatial["source_state_coverage"],
        "semantics": {
            "full_election_ballots": False, "independently_unique_people": False,
            "eligible_population_turnout": False, "group_turnout": False,
            "native_abs_is_mail_returned": False, "party_is_vote_choice": False,
            "marginals_are_joint_groups": False, "source_codes_are_fips": False,
            "geometry_is_2026_voting_precincts": False,
            "composition_denominator": "same native VOTES for each scope",
        },
        "counts": {"native_rows": 65, "native_parishes": 64, "native_count_cells": 1040,
            "group_bindings": 448, "provider_comparisons": 128,
            "source_scope_decisions": 51, "zero_cells": 21,
            "parish_sex_residuals": 37, "state_sex_residual": 278},
    }
    files = {
        "states/LA.json.gz": gzip_bytes(encoded(state)),
        "observations.json.gz": gzip_bytes(encoded({
            "contract": OBSERVATION_CONTRACT, "records": observations,
        })),
        "references/LA-context.json.gz": (inputs / "LA-reference.geojson.gz").read_bytes(),
    }
    index = {
        "contract": CONTRACT, "year": 2026, "states": ["LA"],
        "groups": [{"native_group": group, "dimension": dimension} for group, dimension in GROUPS],
        "state": {"file": "states/LA.json.gz", "profiles": 65, "parishes": 64,
            "group_bindings": 448, "state_parent_separate": True},
        "observations": {"file": "observations.json.gz", "records": 1040,
            "contract": OBSERVATION_CONTRACT},
        "reference": {"file": "references/LA-context.json.gz", "features": 64,
            "bytes": EXPECTED["LA-reference.geojson.gz"][0], "sha256": REFERENCE_SHA256,
            "scope": "reviewed 2026 parish context shapes, not 2026 voting precincts"},
        "complete_download": {"status": "planned", "published": False,
            "verified_anonymously": False},
        "unknowns_are_zero": False, "zeros_preserved": 21,
        "source_parent_and_children_additive": False,
        "source_parent_and_children_independent": False,
    }
    files["index.json"] = encoded(index)
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    pins = {name: pin_bytes(body) for name, body in sorted(files.items())}
    version = hashlib.sha256(encoded({
        "files": pins, "contract": CONTRACT,
    })).hexdigest()
    descriptor = {
        "contract": "participation.dataset.v1", "id": DATASET_ID,
        "version": version, "record_contract": CONTRACT,
        "files": pins, "index": {"file": "index.json", **pins["index.json"]},
        "complete_download": {
            "status": "planned_parent_publication_required",
            "published": False, "verified_anonymously": False, "immutable": False,
            "url": None, "sha256": None,
        },
        "status": "prepared_private_not_activated",
    }
    (output / "dataset.json").write_bytes(encoded(descriptor))
    receipt = {
        "status": "passed_private_dataset_candidate",
        "id": DATASET_ID, "version": version, "files": pins,
        "profiles": 65, "parishes": 64, "observations": 1040,
        "group_bindings": 448, "provider_comparisons": 128,
        "source_scope_decisions": 51, "zero_cells": 21,
        "state_sex_residual": 278, "parish_sex_residuals": 37,
        "complete_download": "PLANNED_FALSE_UNTIL_PARENT_PUBLISHES_NEW_SDK",
        "catalog_or_frontend_activation": False,
    }
    (output / "build-receipt.json").write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--source-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.inputs, args.source_results, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
