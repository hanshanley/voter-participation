"""Whole official analytical frames; national-provider discrepancies remain separate."""

import copy
import gzip
import json
from pathlib import Path

from scripts import congressional_complete_categories as categories
from scripts.participation_intake.contract import encoded, pin


CONTRACT = "participation.official_house_precedence_review.v1"
VERSION = "20261118-01"
REVIEW_PATH = "data/results-intake/official-house-precedence/review.json"
DATA_PATHS = (REVIEW_PATH,)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(data):
    return sorted([
        [race["state_code"], race["district"], race["seat"], race["native_contest_id"],
         race["election_date"], race["election_kind"], race["stage"], race["total_units"],
         categories.signature(race)]
        for race in data["races"]
    ])


def prepare_review(analytical, evidence):
    require(analytical.get("version") == categories.VERSION,
            "Official precedence requires the reviewed complete-category successor")
    query = evidence["official_house_query"]
    decisions = categories.reconcile(analytical, query)
    states = {analytical["races"][key]["identity"]["state_code"] for key in decisions}
    require(states == {"RI"}, "Unreviewed official precedence state inventory")
    state = analytical["states"]["RI"]
    require(state["frozen_scientific_comparison_qualified"]
            and state["initial_recorded_comparison_qualified"] and not state["holds"]
            and set(state["expected_race_ids"]) == set(decisions),
            "Official precedence cannot waive scientific or historical restrictions")
    require(all(analytical["races"][key]["complete_official_categories"] == decision
                and not analytical["races"][key]["initial_holds"]
                for key, decision in decisions.items()),
            "Official precedence needs complete reviewed candidate/category equivalence")
    return {
        "contract": CONTRACT, "version": VERSION,
        "policy": "prefer_complete_reviewed_official_frame_without_provider_count_mixing",
        "states": {"RI": {
            "source_id": categories.IDENTITY, "source_url": categories.URL,
            "expected_provider_race_ids": sorted(decisions),
            "reviewed_previous_counts": copy.deepcopy(state["reviewed_previous_counts"]),
            "official_inventory": inventory(query), "accepted_native": copy.deepcopy(query),
            "category_evidence_sha256": pin(encoded(evidence))["sha256"],
        }},
        "provider_discrepancies_preserved": True,
        "individual_count_allocation_from_Other_allowed": False,
        "new_scientific_eligibility_allowed": False,
        "respondent_refitting_allowed": False,
    }


def load_review(root, analytical):
    root = Path(root)
    value = json.loads((root / REVIEW_PATH).read_bytes())
    evidence = json.loads(gzip.decompress((root / categories.DATA_PATHS[1]).read_bytes()))
    require(value == prepare_review(analytical, evidence),
            "Official House precedence review does not reproduce from complete evidence")
    return value


def current(entry, policy, previous):
    require(entry.get("status") == "reported" and entry.get("advertised", True) is True,
            "official_precedence_source_not_fresh")
    require((entry.get("source") or {}).get("url") == policy["source_url"],
            "official_precedence_source_URL_changed")
    data = entry["data"]
    require(categories.parse(encoded(data["native_facts"])) == data,
            "official_precedence_normalized_result_differs_from_native_candidate_source")
    require(inventory(data) == policy["official_inventory"],
            "official_precedence_candidate_inventory_changed")
    before = previous or policy["accepted_native"]
    require(categories.parse(encoded(before["native_facts"])) == before
            and inventory(before) == policy["official_inventory"],
            "official_precedence_last_good_inventory_changed")
    timestamp = categories.clock(data["source_updated_at"])
    require(timestamp >= categories.clock(before["source_updated_at"]),
            "official_precedence_source_clock_regressed")
    require(timestamp <= categories.clock(entry["first_observed_at"].replace("+00:00", "Z")),
            "official_precedence_source_clock_in_future")
    return data


def evaluate(snapshot, seed, handoff):
    policy = seed["congressional_analytical_review"].get("official_house_precedence")
    if policy is None:
        return handoff
    require(policy.get("contract") == CONTRACT and policy.get("version") == VERSION,
            "Unreviewed official House precedence")
    require(set(policy.get("states", {})) == {"RI"},
            "Unreviewed official precedence state inventory")
    result = copy.deepcopy(handoff)
    previous = seed.get("official_house_precedence_last_good", {})
    checkpoints = copy.deepcopy(previous)
    models = {row["state_code"]: row for row in seed["scenarios"][
        "original/accepted_ridge_multinomial"]["accepted_result"]["rows"]}
    congress = snapshot.get("congress", {})
    for state, reviewed in policy["states"].items():
        decision = result["states"][state]
        original = seed["congressional_analytical_review"]["states"][state]
        require(decision["frozen_scientific_comparison_qualified"]
                and not original["holds"]
                and original["reviewed_previous_counts"] == reviewed["reviewed_previous_counts"]
                == models[state]["reported_comparison"]["previous"]
                and sorted(original["expected_race_ids"]) == reviewed["expected_provider_race_ids"],
                "Official precedence scientific or historical endpoint changed")
        entry = congress.get("official_candidate_evidence", {}).get(reviewed["source_id"], {})
        data, reasons, counts = None, [], None
        try:
            data = current(entry, reviewed, previous.get(state))
            counts = {party: sum(row["votes"] for race in data["races"]
                                 for row in race["candidates"] if row["party_group"] == party)
                      for party in "DRO"}
            require(counts["D"] > 0 and counts["R"] > 0,
                    "official_precedence_nonpositive_major_endpoint")
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            reasons.append(str(error))
        active = not reasons
        old = models[state]["reported_comparison"]["current"]
        provider = {}
        for key in reviewed["expected_provider_race_ids"]:
            raw = congress.get("races", {}).get(key, {})
            native = raw.get("data") or {}
            candidates = native.get("candidates", [])
            known = bool(candidates) and all(type(row.get("votes")) is int for row in candidates)
            provider[key] = {
                "status": raw.get("status"), "source_updated_at": native.get("source_updated_at"),
                "counts": {party: sum(row["votes"] for row in candidates
                                       if row["party_group"] == party) for party in "DRO"} if known else None,
                "compatibility_holds": copy.deepcopy(result["races"][key]["holds"]),
            }
        decision.update(
            automatic_update_eligible=active,
            decision="fresh_compatible_conditioning" if active else "frozen_dated_result",
            holds=reasons, counts=counts if active else None,
            changed=bool(active and counts != old), last_good_model_counts=copy.deepcopy(old),
            current_district_counts={
                race["district"]: {party: sum(row["votes"] for row in race["candidates"]
                                             if row["party_group"] == party) for party in "DRO"}
                for race in data["races"]} if active else None,
            current_stages=["general"] if active else [],
            current_rounds=["not_ranked"] if active else [],
            source_update_labels=[data["source_updated_at"]] if active else [],
            source_urls=[reviewed["source_url"]], official_direct_source=True,
            official_source_clock_supplied=True, direct_official_review_version=VERSION,
            source_revision_policy=policy["policy"], national_provider_frames=provider,
            provider_fallback_on_official_failure_allowed=False,
            provider_counts_added_to_official_counts=False,
        )
        if active:
            checkpoints[state] = copy.deepcopy(data)
    result["official_house_precedence_last_good"] = checkpoints
    result["official_house_precedence_review_version"] = VERSION
    return result
