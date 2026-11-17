"""Reproduce complete official category bridges without allocating Other to people."""

import copy
import csv
from decimal import Decimal
import gzip
import io
import json
from pathlib import Path
import re

from scripts.congressional_candidate_identity import DECLARATION_VERSION, load_declaration_successor
from scripts.participation_intake.contract import encoded, pin


VERSION = "20261117-categories-01"
CONTRACT = "participation.congressional_official_categories.v1"
DATA_ROOT = "data/results-intake/analytical-handoff/official-categories/"
DATA_PATHS = tuple(DATA_ROOT + name for name in (
    "predecessor-review.json.gz", "evidence.json.gz", "MN-ushouse.txt",
    "independent-native-verification.json"))
MASS_HOLD = "aggregate_other_not_reconciled_to_retained_minor_candidate_mass"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+", value),
            "Missing or noninteger official candidate count")
    result = int(value)
    require(result <= 9007199254740991, "Unsafe official candidate count")
    return result


def minnesota_house(body):
    result = {}
    parties = {"DFL": "D", "R": "R", "IND": "O", "WI": "O"}
    for fields in csv.reader(io.StringIO(body.decode("utf-8")), delimiter=";"):
        require(len(fields) == 16 and fields[0] == "MN"
                and fields[1:3] == ["", ""] and fields[8:10] == ["", ""],
                "Not a complete statewide Minnesota candidate-return row")
        seat = integer(fields[5])
        require(1 <= seat <= 8 and fields[3] == str(103 + seat).zfill(4)
                and fields[4] == "U.S. Representative District " + str(seat),
                "Official congressional office or district changed")
        require(fields[10] in parties and re.fullmatch(r"[0-9]{4}", fields[6]),
                "Unreviewed official candidate party or identifier")
        write_in = fields[7] == "WRITE-IN"
        require(write_in == (fields[10] == "WI") == (fields[6] == "9901"),
                "Ambiguous official write-in category")
        require(bool(fields[7].strip()), "Missing official candidate name")
        count, total = integer(fields[13]), integer(fields[15])
        reporting, units = integer(fields[11]), integer(fields[12])
        require(units > 0 and reporting == units,
                "Incomplete official district reporting inventory")
        fraction = Decimal(fields[14])
        require(fraction.is_finite() and 0 <= fraction <= 100,
                "Invalid native percentage context")
        rows = result.setdefault(str(seat), [])
        require(fields[6] not in {row["candidate_id"] for row in rows},
                "Duplicate official district candidate")
        rows.append({
            "candidate_id": fields[6], "name": fields[7], "literal_party": fields[10],
            "party_group": parties[fields[10]], "votes": count,
            "role": "generic_write_in" if write_in else "named_candidate",
            "native_fields": fields, "contest_total": total,
        })
    require(set(result) == {str(seat) for seat in range(1, 9)},
            "Official statewide district inventory incomplete")
    for rows in result.values():
        require(len({(row["native_fields"][11], row["native_fields"][12],
                      row["contest_total"]) for row in rows}) == 1
                and sum(row["votes"] for row in rows) == rows[0]["contest_total"]
                and sum(row["role"] == "generic_write_in" for row in rows) == 1
                and sum(row["party_group"] == "D" for row in rows) == 1
                and sum(row["party_group"] == "R" for row in rows) == 1,
                "Official candidate inventory does not reconcile to its contest control")
    return result


def reconcile(previous, source, body):
    from scripts.congressional_analytical_bridge import review_names, name_tokens

    require(set(source) == {"family", "url", "original_path", "original_pin",
                            "election_date", "stage", "captured_at"},
            "Unexpected official category source fields")
    require(source["family"] == "mn_house_statewide_semicolon_v1"
            and source["url"] == "https://electionresultsfiles.sos.mn.gov/20261103/ushouse.txt"
            and source["original_path"] == DATA_PATHS[2]
            and source["election_date"] == "2026-11-03" and source["stage"] == "general"
            and source["captured_at"] is None,
            "Unreviewed official statewide category source")
    require(pin(body) == source["original_pin"], "Official candidate original changed")
    official = minnesota_house(body)
    expected = previous["states"]["MN"]["expected_race_ids"]
    require(len(expected) == 8 and {previous["races"][key]["identity"]["seat"]
                                 for key in expected} == set(official),
            "Official and reviewed provider district inventories differ")
    decisions = {}
    for key in expected:
        race = previous["races"][key]
        frame = race["identity"]
        require(frame["state_code"] == "MN" and frame["chamber"] == "house"
                and frame["election_date"] == source["election_date"]
                and frame["stage"] == source["stage"] and frame["election_kind"] == "regular"
                and frame["ranked_choice"] is False and frame["round"] == "not_ranked",
                "Official/provider election, office, seat, stage or round differs")
        provider = race["accepted_native"]["candidates"]
        aggregates = [row for row in provider if row["role"] == "provider_aggregate_other"]
        named = [row for row in provider if row["role"] == "named_candidate"]
        require(len(aggregates) == 1 and aggregates[0]["party_group"] == "O"
                and len(named) + 1 == len(provider), "Ambiguous provider category inventory")
        mapped, matches = set(), []
        rows = official[frame["seat"]]
        for row in rows:
            if row["role"] == "generic_write_in":
                continue
            options = [candidate for candidate in named
                       if candidate["party_group"] == row["party_group"]
                       and review_names(row["name"], candidate["name"])]
            require(len(options) == 1 and options[0]["candidate_id"] not in mapped,
                    "Official named candidate unmatched or ambiguous")
            candidate = options[0]
            require(candidate["candidate_id"] in race["named_crosswalk"],
                    "Official category evidence cannot replace unresolved named identity")
            mapped.add(candidate["candidate_id"])
            matches.append({
                "official": copy.deepcopy(row), "provider": copy.deepcopy(candidate),
                "provider_minus_official_votes": candidate["votes"] - row["votes"],
                "individual_count_allocated_from_Other": False,
            })
        require(mapped == {row["candidate_id"] for row in named},
                "Provider named candidate absent from complete official inventory")
        unmatched = race["unmatched_legacy_indices"]
        require(len(unmatched) == 1 and name_tokens(previous["legacy_candidates_preserved"][
            unmatched[0]]["name"]) == ["write", "in"],
            "Unmatched legacy mass is not one generic write-in category")
        write_in = next(row for row in rows if row["role"] == "generic_write_in")
        require(write_in["votes"] == aggregates[0]["votes"],
                "Provider Other differs from the complete official write-in category")
        decisions[key] = {
            "method": "complete_official_named_inventory_and_separate_write_in_category",
            "source_url": source["url"], "source_pin": source["original_pin"],
            "named_candidates": matches, "official_write_in": copy.deepcopy(write_in),
            "provider_aggregate_other": copy.deepcopy(aggregates[0]),
            "retained_legacy_write_in": copy.deepcopy(
                previous["legacy_candidates_preserved"][unmatched[0]]),
            "cross_provider_named_count_differences_retained_not_added": True,
            "native_count_clock": None, "captured_at": None,
            "certification_or_synchronized_snapshot_claimed": False,
            "subsequent_updates_require_stable_provider_and_candidate_IDs": True,
            "individual_count_allocated_from_Other": False,
        }
    return decisions


def successor(previous, value, originals, files):
    require(previous.get("version") == DECLARATION_VERSION,
            "Category successor needs its complete reviewed predecessor")
    require(set(value) == {"contract", "sources"} and value["contract"] == CONTRACT
            and isinstance(value["sources"], list) and len(value["sources"]) == 1
            and set(originals) == {DATA_PATHS[2]},
            "Incomplete official category evidence")
    decisions = reconcile(previous, value["sources"][0], originals[DATA_PATHS[2]])
    review = copy.deepcopy(previous)
    resolved = []
    for key, decision in decisions.items():
        race = review["races"][key]
        if MASS_HOLD in race["initial_holds"]:
            race["initial_holds"].remove(MASS_HOLD)
            resolved.append(key)
        race["official_category_reconciliation"] = decision
    require(bool(resolved), "Official category evidence resolves no existing guard")
    for state, decision in review["states"].items():
        removed = {key + ":" + MASS_HOLD for key in resolved
                   if key in decision["expected_race_ids"]}
        decision["holds"] = sorted(set(decision["holds"]) - removed)
        decision["automatic_update_reviewed"] = not decision["holds"]
        if decision["automatic_update_reviewed"]:
            require(decision["frozen_scientific_comparison_qualified"]
                    and decision["initial_recorded_comparison_qualified"] and state not in ("HI", "WY"),
                    "Category evidence cannot grant new scientific eligibility")
    review["version"] = VERSION
    review["official_category_successor"] = {
        "contract": CONTRACT, "version": VERSION, "files": copy.deepcopy(files),
        "predecessor_review_sha256": pin(encoded(previous))["sha256"],
        "evidence_sha256": pin(encoded(value))["sha256"],
        "reviewed_races": sorted(decisions), "resolved_races": sorted(resolved),
        "all_legacy_candidates_and_individual_counts_preserved": True,
        "named_minor_candidates_not_merged_with_write_ins": True,
        "provider_counts_not_added_to_official_counts": True,
    }
    return review


def load_successor(root, review):
    require(review.get("version") == VERSION, "Unreviewed official category successor")
    files = (review.get("official_category_successor") or {}).get("files") or {}
    require(set(files) == set(DATA_PATHS), "Incomplete official category evidence package")
    bodies = {}
    for name in DATA_PATHS:
        body = (Path(root) / name).read_bytes()
        require(pin(body) == files[name], "Changed complete official category evidence")
        bodies[name] = body
    previous = json.loads(gzip.decompress(bodies[DATA_PATHS[0]]))
    load_declaration_successor(root, previous)
    evidence = json.loads(gzip.decompress(bodies[DATA_PATHS[1]]))
    require(successor(previous, evidence, {DATA_PATHS[2]: bodies[DATA_PATHS[2]]}, files) == review,
            "Official category decisions do not reproduce from complete pinned evidence")
    return review
