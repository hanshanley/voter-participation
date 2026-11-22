"""Versioned provider-to-science handoff; review once, verify stable IDs thereafter."""

import argparse
import copy
import gzip
import json
import re
import shutil
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from scripts.participation_intake.contract import encoded, pin
from scripts.results_congress import check_revision, house_state_comparisons, normalize
from scripts.congressional_geography import DATA_PATHS as GEOGRAPHY_PATHS
from scripts.congressional_candidate_identity import VERSION as IDENTITY_VERSION, DATA_PATHS as IDENTITY_PATHS
from scripts.congressional_candidate_identity import DECLARATION_VERSION, DECLARATION_PATHS
from scripts.congressional_candidate_identity import OFFICIAL_DECLARATION_VERSION, OFFICIAL_DECLARATION_PATHS
from scripts.congressional_category_reconciliation import VERSION as CATEGORY_VERSION
from scripts.congressional_category_reconciliation import DATA_PATHS as CATEGORY_PATHS
from scripts.congressional_filing_identity import VERSION as FILING_VERSION, DATA_PATHS as FILING_PATHS
from scripts.congressional_complete_categories import VERSION as COMPLETE_CATEGORY_VERSION
from scripts.congressional_complete_categories import DATA_PATHS as COMPLETE_CATEGORY_PATHS


CONTRACT = "participation.congressional_analytical_review.v1"
VERSION = "20261116-01"
REVIEW_PATH = "data/results-intake/analytical-handoff/review.json.gz"
ORIGINAL_PATHS = ("fec-2020.xlsx", "fec-2022.xlsx", "nebraska-2024.pdf")
DATA_PATHS = (REVIEW_PATH,) + tuple(
    "data/results-intake/analytical-handoff/" + name for name in ORIGINAL_PATHS) + GEOGRAPHY_PATHS


def data_paths(review):
    result = tuple(name for name in DATA_PATHS
                 if name not in GEOGRAPHY_PATHS or review.get("house_boundaries") is not None)
    if review.get("explicit_reference_names") is not None:
        from scripts.congressional_reference_identity import DATA_PATHS as REFERENCE_PATHS
        result += REFERENCE_PATHS
    if (review.get("house_boundaries") or {}).get("split_geometry_review") is not None:
        from scripts.congressional_split_blocks import DATA_PATHS as SPLIT_PATHS
        result += SPLIT_PATHS
    if "water_only_review" in (review.get("house_boundaries") or {}):
        from scripts.congressional_geography import WATER_PATHS
        result += WATER_PATHS
    if review.get("official_house_precedence") is not None:
        from scripts.official_house_precedence import DATA_PATHS as PRECEDENCE_PATHS
        result += PRECEDENCE_PATHS
    if review.get("native_official_house") is not None:
        from scripts.native_official_house import DATA_PATHS as NATIVE_PATHS
        result += NATIVE_PATHS
    if review.get("version") in (OFFICIAL_DECLARATION_VERSION, FILING_VERSION, COMPLETE_CATEGORY_VERSION):
        if review["version"] == COMPLETE_CATEGORY_VERSION:
            result += COMPLETE_CATEGORY_PATHS
        if review["version"] in (FILING_VERSION, COMPLETE_CATEGORY_VERSION):
            result += FILING_PATHS
        return result + IDENTITY_PATHS + DECLARATION_PATHS + CATEGORY_PATHS + OFFICIAL_DECLARATION_PATHS
    if review.get("version") == CATEGORY_VERSION:
        return result + IDENTITY_PATHS + DECLARATION_PATHS + CATEGORY_PATHS
    if review.get("version") == DECLARATION_VERSION:
        return result + IDENTITY_PATHS + DECLARATION_PATHS
    return result + (IDENTITY_PATHS if review.get("version") == IDENTITY_VERSION else ())

FRAME_FIELDS = (
    "id", "provider_race_id", "chamber", "state_code", "seat", "seat_label",
    "election_date", "election_kind", "stage", "ranked_choice", "round",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compressed(value):
    body = gzip.compress(encoded(value), mtime=0)
    return body[:9] + bytes([3]) + body[10:]


def load_review(root, *, include_split_geometry=True, include_water_only=False):
    root = Path(root)
    review = json.loads(gzip.decompress((root / REVIEW_PATH).read_bytes()))
    require(review.get("contract") == CONTRACT
            and review.get("version") in (VERSION, IDENTITY_VERSION, DECLARATION_VERSION, CATEGORY_VERSION,
                                         OFFICIAL_DECLARATION_VERSION, FILING_VERSION, COMPLETE_CATEGORY_VERSION),
            "Unreviewed congressional analytical successor")
    if review["version"] == COMPLETE_CATEGORY_VERSION:
        from scripts.congressional_complete_categories import load_successor
        load_successor(root, review)
    elif review["version"] == FILING_VERSION:
        from scripts.congressional_filing_identity import load_successor
        load_successor(root, review)
    elif review["version"] == OFFICIAL_DECLARATION_VERSION:
        from scripts.congressional_candidate_identity import load_official_declaration_successor
        load_official_declaration_successor(root, review)
    elif review["version"] == CATEGORY_VERSION:
        from scripts.congressional_category_reconciliation import load_successor
        load_successor(root, review)
    elif review["version"] == IDENTITY_VERSION:
        from scripts.congressional_candidate_identity import load_successor
        load_successor(root, review)
    elif review["version"] == DECLARATION_VERSION:
        from scripts.congressional_candidate_identity import load_declaration_successor
        load_declaration_successor(root, review)
    for dataset in review["historical_senate"]["datasets"]:
        original = dataset["original"]
        body = (root / "data/results-intake/analytical-handoff" / original["path"]).read_bytes()
        require(pin(body) == {key: original[key] for key in ("bytes", "sha256")},
                "Changed complete official congressional baseline")
    from scripts.congressional_reference_identity import load_optional as load_reference_names
    review = load_reference_names(root, review)
    from scripts.congressional_geography import load_review as load_geography
    geography = load_geography(root, include_split_geometry=include_split_geometry,
                               include_water_only=include_water_only)
    if geography is not None:
        review["house_boundaries"] = geography
    from scripts.official_house_precedence import REVIEW_PATH as PRECEDENCE_PATH, load_review as load_precedence
    if (root / PRECEDENCE_PATH).exists():
        review["official_house_precedence"] = load_precedence(root, review)
    from scripts.native_official_house import REVIEW_PATH as NATIVE_PATH, load_review as load_native
    if (root / NATIVE_PATH).exists():
        review["native_official_house"] = load_native(root, review)
    return review


def identity(row):
    return {key: row.get(key) for key in FRAME_FIELDS}


def catalog_identity(rows):
    return [{"state_code": row["state_code"], "district": row["district"],
             "name": row["name"], "party": row["party"], "year": row["year"]}
            for row in rows]


def name_tokens(value):
    return re.findall(r"[a-z0-9]+", value.casefold())


def review_names(old, new):
    before, after = name_tokens(old), name_tokens(new)
    if before == after:
        return "literal_name_case_punctuation_only"
    if len(before) >= 2 and len(after) >= 2 and before[0] == after[0] and before[-1] == after[-1]:
        if [word for word in before[1:-1] if len(word) > 1] == [
                word for word in after[1:-1] if len(word) > 1]:
            return "same_first_surname_optional_middle_initial_only"
    return None


def prepare_review(congress, seed, scientific_review, baselines):
    from scripts.automatic_estimates import _party_group

    require(congress.get("election_date") == "2026-11-03", "Wrong reviewed election")
    legacy = seed["accepted_candidates"]
    by_district = defaultdict(list)
    for index, row in enumerate(legacy):
        by_district[row["district"]].append((index, row))
    race_reviews, crosswalk = {}, []
    for key, entry in sorted(congress["races"].items()):
        data = entry.get("data")
        if data is None:
            continue
        mapped, unmatched, reasons = {}, [], []
        if data["chamber"] == "house" and data["voting_house_seat"]:
            suffix = "-AL" if len([district for district in by_district
                                  if district.startswith(data["state_code"] + "-")]) == 1 else (
                                      "-" + data["seat"].zfill(2))
            district = data["state_code"] + suffix
            old_rows = by_district.get(district, [])
            require(bool(old_rows), "Missing legacy district for " + key)
            for index, old in old_rows:
                options = []
                group = _party_group(old["party"])
                for candidate in data["candidates"]:
                    rule = review_names(old["name"], candidate["name"])
                    if (candidate["role"] == "named_candidate"
                            and candidate["party_group"] == group and rule):
                        options.append((candidate, rule))
                if len(options) == 1 and options[0][0]["candidate_id"] not in mapped:
                    candidate, rule = options[0]
                    mapped[candidate["candidate_id"]] = index
                    status = "reviewed_named_identity"
                else:
                    candidate, rule = None, None
                    unmatched.append(index)
                    status = "retained_legacy_identity_unresolved"
                    if group in "DR":
                        reasons.append("unmatched_or_ambiguous_named_major_candidate:" + old["name"])
                crosswalk.append({
                    "race_id": key, "provider_race_id": data["provider_race_id"],
                    "state_code": data["state_code"], "district": district,
                    "legacy_index": index, "legacy": copy.deepcopy(old),
                    "provider_candidate_id": candidate["candidate_id"] if candidate else None,
                    "provider_literal_name": candidate["name"] if candidate else None,
                    "provider_literal_party": candidate["literal_party"] if candidate else None,
                    "rule": rule, "decision": status, "individual_count_allocated_from_Other": False,
                })
            aggregates = [candidate for candidate in data["candidates"]
                          if candidate["role"] == "provider_aggregate_other"]
            unlisted = [candidate for candidate in data["candidates"]
                        if candidate["candidate_id"] not in mapped and candidate not in aggregates]
            if unlisted:
                reasons.append("unmatched_new_named_candidate")
            unmatched_other = [index for index in unmatched if _party_group(legacy[index]["party"]) == "O"]
            mass = sum(int(legacy[index]["votes"]) for index in unmatched_other)
            if unmatched_other and (len(aggregates) != 1 or aggregates[0]["votes"] != mass):
                reasons.append("aggregate_other_not_reconciled_to_retained_minor_candidate_mass")
            if len(aggregates) > 1 or any(candidate["party_group"] != "O" for candidate in aggregates):
                reasons.append("ambiguous_aggregate_other_role")
        else:
            district = None
        race_reviews[key] = {
            "identity": identity(data), "accepted_native": copy.deepcopy(data),
            "source_url": (entry.get("source") or {}).get("url"),
            "district": district, "named_crosswalk": mapped, "unmatched_legacy_indices": unmatched,
            "initial_holds": sorted(set(reasons)),
            "subsequent_updates_require_stable_provider_and_candidate_IDs": True,
            "initial_provider_selection": (
                "Explicit reviewed cross-provider substitution, not a claim that NPR/AP clocks "
                "postdate Civic clocks; subsequent NPR/AP revisions require monotone native versions."),
            "Other_policy": (
                "Preserve every legacy identity and original count; a reconciled provider Other "
                "bucket updates only category O, never an omitted individual's votes."),
        }
    recorded = {row["state_code"]: row for row in house_state_comparisons(congress, scientific_review)}
    frozen = {row["state_code"]: row for row in seed["scenarios"][
        "original/accepted_ridge_multinomial"]["accepted_result"]["rows"]}
    states = {}
    for state, row in sorted(frozen.items()):
        reasons = []
        current = recorded.get(state)
        if not row["source_comparison_available"]:
            reasons.append("frozen_scientific_hold:" + row["reported_comparison"]["reason"])
        if not current or not current["qualified_comparison"]:
            reasons.extend((current or {}).get("comparison_holds", ["current_recorded_comparison_missing"]))
        if state in ("HI", "WY"):
            reasons.append("protected_official_source_frame_not_replaceable_by_NPR_AP")
        expected = [key for key, race in race_reviews.items()
                    if race["identity"]["chamber"] == "house"
                    and race["identity"]["state_code"] == state]
        for key in expected:
            reasons.extend(key + ":" + reason for reason in race_reviews[key]["initial_holds"])
        prior = row["reported_comparison"].get("previous") or row["contest_comparability"]["previous_counts"]
        if current and {party: current["previous"].get(party) for party in "DRO"} != prior:
            reasons.append("historical_statewide_source_frame_differs")
        states[state] = {"expected_race_ids": sorted(expected),
                         "reviewed_previous_counts": copy.deepcopy(prior),
                         "reviewed_comparability": copy.deepcopy(row.get("contest_comparability")),
                         "frozen_scientific_comparison_qualified": row["source_comparison_available"],
                         "initial_recorded_comparison_qualified": bool(current and current["qualified_comparison"]),
                         "automatic_update_reviewed": not reasons, "holds": sorted(set(reasons))}
    return {
        "contract": CONTRACT, "version": VERSION, "election_date": "2026-11-03",
        "frozen_qualification": copy.deepcopy(seed["qualification"]),
        "legacy_candidate_identity_sha256": pin(encoded(catalog_identity(legacy)))["sha256"],
        "legacy_candidates_preserved": copy.deepcopy(legacy),
        "races": race_reviews, "candidate_crosswalk": crosswalk, "states": states,
        "historical_senate": baselines,
        "no_new_scientific_eligibility_or_respondent_fit": True,
        "all_House_district_comparisons_remain_boundary_held": True,
        "Senate_models": {
            "decision": "frozen_separate_scientific_versions",
            "reason": "No reviewed same-seat/stage/provider endpoint-to-prior bridge for existing Senate "
                      "model inputs; recorded Senate references do not grant conditional-model eligibility.",
        },
    }


def evaluate(snapshot, seed):
    review = seed["congressional_analytical_review"]
    require(review.get("contract") == CONTRACT
            and review.get("version") in (VERSION, IDENTITY_VERSION, DECLARATION_VERSION, CATEGORY_VERSION,
                                         OFFICIAL_DECLARATION_VERSION, FILING_VERSION, COMPLETE_CATEGORY_VERSION),
            "Unreviewed congressional analytical successor")
    require(pin(encoded(catalog_identity(seed["accepted_candidates"])))["sha256"]
            == review["legacy_candidate_identity_sha256"], "Legacy scientific identity changed")
    require(seed["qualification"] == review["frozen_qualification"], "Frozen qualification changed")
    congress = snapshot.get("congress", {})
    races, checkpoints = {}, {}
    previous = seed.get("congressional_analytical_last_good", {})
    for key, reviewed in review["races"].items():
        entry = congress.get("races", {}).get(key, {})
        data, reasons = entry.get("data"), list(reviewed["initial_holds"])
        if entry.get("status") != "reported" or entry.get("advertised", True) is not True:
            reasons.append("current_source_not_fresh_or_not_advertised")
        if data is None or identity(data) != reviewed["identity"]:
            reasons.append("office_election_geography_seat_stage_or_round_changed")
        else:
            try:
                require((entry.get("source") or {}).get("url") == reviewed["source_url"],
                        "reviewed_provider_source_URL_changed")
                require(normalize(data["native_facts"], data["chamber"]) == data,
                        "normalized_result_differs_from_native_candidate_source")
                check_revision(previous.get(key, reviewed["accepted_native"]), data)
                require(all(type(row["votes"]) is int and 0 <= row["votes"] <= 9007199254740991
                            and row["party_group"] in "DRO" for row in data["candidates"]),
                        "missing_count_or_unknown_party")
                from scripts.congressional_complete_categories import current_hold
                category_hold = current_hold(congress, key, reviewed, data)
                if category_hold:
                    reasons.append(category_hold)
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                reasons.append(str(error))
        races[key] = {"race_id": key, "state_code": reviewed["identity"]["state_code"],
                      "chamber": reviewed["identity"]["chamber"], "holds": sorted(set(reasons)),
                      "compatible": not reasons, "source_updated_at": (data or {}).get("source_updated_at")}
        if not reasons:
            checkpoints[key] = copy.deepcopy(data)
    for key in sorted(set(congress.get("races", {})) - set(review["races"])):
        entry = congress["races"][key]
        data = entry.get("data") or {}
        races[key] = {"race_id": key, "state_code": data.get("state_code"),
                      "chamber": data.get("chamber"), "compatible": False,
                      "holds": ["new_provider_identity_requires_reviewed_scientific_successor"]}
    models = {row["state_code"]: row for row in seed["scenarios"][
        "original/accepted_ridge_multinomial"]["accepted_result"]["rows"]}
    states = {}
    for state, reviewed in review["states"].items():
        reasons = list(reviewed["holds"])
        expected = reviewed["expected_race_ids"]
        actual = {key for key, entry in congress.get("races", {}).items()
                  if (entry.get("data") or {}).get("chamber") == "house"
                  and (entry.get("data") or {}).get("state_code") == state}
        if set(expected) != actual:
            reasons.append("current_state_district_inventory_changed")
        for key in expected:
            reasons.extend(key + ":" + reason for reason in races[key]["holds"])
        counts = None
        if not reasons:
            counts = {party: sum(candidate["votes"] for key in expected
                                for candidate in checkpoints[key]["candidates"]
                                if candidate["party_group"] == party) for party in "DRO"}
            if counts["D"] <= 0 or counts["R"] <= 0:
                reasons.append("nonpositive_major_party_endpoint")
        old = models[state]["reported_comparison"].get("current")
        previous_counts = models[state]["reported_comparison"].get("previous")
        if (reviewed["frozen_scientific_comparison_qualified"]
                and previous_counts != reviewed["reviewed_previous_counts"]):
            reasons.append("reviewed_historical_model_endpoint_changed")
        active = not reasons
        states[state] = {
            "state_code": state, "automatic_update_eligible": active,
            "decision": "fresh_compatible_conditioning" if active else "frozen_dated_result",
            "holds": sorted(set(reasons)), "counts": counts if active else None,
            "changed": bool(active and counts != old),
            "last_good_model_counts": copy.deepcopy(old),
            "current_district_counts": {
                review["races"][key]["district"]: {
                    party: sum(candidate["votes"] for candidate in checkpoints[key]["candidates"]
                               if candidate["party_group"] == party) for party in "DRO"}
                for key in expected
            } if active else None,
            "current_stages": sorted({checkpoints[key]["stage"] for key in expected}) if active else [],
            "current_rounds": sorted({checkpoints[key]["round"] for key in expected}) if active else [],
            "source_update_labels": sorted({races[key]["source_updated_at"] for key in expected
                                            if races[key].get("source_updated_at")}),
            "source_urls": sorted({congress["races"][key]["source"]["url"] for key in expected
                                   if isinstance(congress.get("races", {}).get(key, {}).get("source"), dict)
                                   and congress["races"][key]["source"].get("url")}),
            "frozen_scientific_comparison_qualified": reviewed["frozen_scientific_comparison_qualified"],
            "reviewed_comparability": copy.deepcopy(reviewed["reviewed_comparability"]),
            "recorded_results_available_separately": True,
        }
    return {"contract": "participation.congressional_analytical_handoff.v1",
            "review_version": review["version"], "states": states, "races": races,
            "last_good": {**copy.deepcopy(previous), **checkpoints},
            "candidate_crosswalk": review["candidate_crosswalk"],
            "historical_senate": review["historical_senate"],
            "Senate_models": review["Senate_models"]}


def apply_decisions(decisions, endpoints, recorded, handoff):
    from scripts.automatic_estimates import _recorded

    for index, row in enumerate(decisions):
        state = row["state_code"]
        bridge = handoff["states"][state]
        active = bridge["automatic_update_eligible"]
        action = ("changed_recompute_behavioral" if bridge["changed"] else "retained_fresh_unchanged"
                  ) if active else "held_retain_last_good"
        provider_bridge = not bridge.get("official_direct_source", False)
        row.update(decision=action, provider_bridge=provider_bridge, reason="; ".join(bridge["holds"]) or None,
                   recorded_counts_changed=bridge["changed"],
                   congressional_analytical_status=copy.deepcopy(bridge))
        endpoints[state].update(
            fresh_complete=active, changed=bridge["changed"], provider_bridge=provider_bridge,
            source_urls=bridge["source_urls"], source_update_labels=bridge["source_update_labels"])
        if active:
            endpoints[state]["counts"] = copy.deepcopy(bridge["counts"])
            recorded[index] = _recorded(state, recorded[index]["previous"], bridge["counts"],
                                        action, bridge["source_update_labels"], True)
        elif bridge["last_good_model_counts"] is not None:
            endpoints[state]["counts"] = copy.deepcopy(bridge["last_good_model_counts"])
            recorded[index] = _recorded(
                state, recorded[index]["previous"], bridge["last_good_model_counts"],
                action, [], False)


def snapshot_label(value):
    return re.sub(r"\b[0-9a-f]{64}\b", lambda match: match.group()[:12] + " (short ID)", str(value))


def hold_reason(hold):
    require(isinstance(hold, str) and bool(hold), "Nonliteral analytical hold")
    if hold.startswith("npr:"):
        fields = hold.split(":", 7)
        require(len(fields) == 8 and fields[1] in ("house", "senate") and bool(fields[7]),
                "Malformed race-scoped analytical hold")
        return fields[7].casefold()
    return hold.casefold()


def state_guard_matrix(handoff):
    requirements = {
        "candidate_identity": "Explicit primary-source identity declarations or a complete compatible candidate crosswalk.",
        "other_write_in": "Complete named-minor/write-in inventory and explicit source-category equivalence; retain omitted mass.",
        "source_universe": "Compatible complete source inventory without replacing protected official frames.",
        "party_coverage": "Comparable candidate-party coverage; unchanged district numbers or equal major-party totals are insufficient.",
        "election_stage": "Compatible office, seat, election-stage and round evidence.",
        "denominator": "Compatible source-defined denominator evidence.",
        "geography": "Comparable electorate and boundary evidence for the actual election-year pair.",
        "source_freshness": "A successful compatible source observation; retained values keep their original clocks.",
        "scientific_eligibility": "Resolve retained scientific comparison restrictions; fresh returns alone are insufficient.",
        "unclassified": "Inspect the exact unresolved guard; no reviewed automatic remedy is established.",
    }
    terms = {
        "candidate_identity": ("unmatched", "ambiguous_named", "candidate_identity", "identity_changed"),
        "other_write_in": ("aggregate_other", "write-in", "write_in", "aggregate_other_role",
                           "official_category_other_mass"),
        "source_universe": ("protected_official", "inventory", "source_frame", "source_url",
                            "counts missing", "missing_count", "unknown_party",
                            "normalized_result_differs", "native_candidate_source"),
        "party_coverage": ("party", "nominee", "nonpartisan", "unopposed", "no-ballot"),
        "election_stage": ("stage", "ranked", "runoff", "round"),
        "denominator": ("denominator",),
        "geography": ("boundary", "geography", "electorate"),
        "source_freshness": ("fresh", "source_unavailable", "source_missing", "not_advertised",
                             "revision", "rollback", "clock", "version"),
    }
    rows = []
    for state, decision in sorted(handoff.get("states", {}).items()):
        holds = copy.deepcopy(decision["holds"])
        reasons = [hold_reason(hold) for hold in holds]
        families = {family: any(any(term in reason for term in words) for reason in reasons)
                    for family, words in terms.items()}
        families["scientific_eligibility"] = not decision["frozen_scientific_comparison_qualified"]
        families["unclassified"] = any(
            not reason.startswith("frozen_scientific_hold:")
            and not any(term in reason for words in terms.values() for term in words)
            for reason in reasons)
        rows.append({
            "state_code": state, "decision": decision["decision"],
            "automatic_update_eligible": decision["automatic_update_eligible"],
            "frozen_scientific_comparison_qualified": decision["frozen_scientific_comparison_qualified"],
            "overlapping_guard_families": families, "exact_holds": holds,
            "missing_evidence": [text for family, text in requirements.items() if families[family]],
            "last_good_model_counts": copy.deepcopy(decision["last_good_model_counts"]),
            "current_compatible_counts": copy.deepcopy(decision["counts"]),
            "source_update_labels": copy.deepcopy(decision["source_update_labels"]),
            "source_urls": copy.deepcopy(decision["source_urls"]),
        })
    return {
        "contract": "participation.house_state_guard_matrix.v2",
        "review_version": handoff.get("review_version"),
        "states": rows,
        "automatic_states": [row["state_code"] for row in rows if row["automatic_update_eligible"]],
        "previously_qualified_frozen_states": [
            row["state_code"] for row in rows if row["frozen_scientific_comparison_qualified"]
            and not row["automatic_update_eligible"]],
        "overlapping_guard_counts": {
            family: sum(row["overlapping_guard_families"][family] for row in rows)
            for family in requirements},
        "classification_changes_eligibility": False,
        "snapshot_classification_not_claim_of_source_absence": True,
    }


def current_comparability(audit, comparison, decision):
    audit = copy.deepcopy(audit)
    audit.update(previous_counts=copy.deepcopy(comparison["previous"]),
                 current_counts=copy.deepcopy(comparison["current"]),
                 raw_reported_aggregate_margin_change_pp=comparison["reported_change_pp"])
    districts = audit.get("common_reported_DR_district_ids")
    if districts is not None:
        require(len(districts) == len(set(districts))
                and set(districts) <= set(decision["current_district_counts"]),
                "Reviewed common-district diagnostic inventory changed")
        current = {party: sum(decision["current_district_counts"][district][party]
                              for district in districts) for party in "DRO"}
        previous = audit["common_source_id_previous_counts"]
        def margin(counts):
            total = counts["D"] + counts["R"]
            return float(Fraction(100 * (counts["D"] - counts["R"]), total)) if total else None
        before, after = margin(previous), margin(current)
        change = after - before if before is not None and after is not None else None
        audit.update(common_source_id_current_counts=current, common_source_id_margin_change_pp=change,
                     aggregate_minus_common_source_id_change_pp=(
                         comparison["reported_change_pp"] - change if change is not None else None))
    return audit


def annotate_result(result, handoff):
    version = handoff["review_version"]
    for row in result["rows"]:
        decision = handoff["states"][row["state_code"]]
        comparison = row["reported_comparison"]
        if not row["source_comparison_available"]:
            continue
        if decision["automatic_update_eligible"]:
            direct = decision.get("official_direct_source", False)
            fingerprint = pin(encoded({"counts": decision["counts"],
                                       "source_update_labels": decision["source_update_labels"],
                                       "source_urls": decision["source_urls"]}))["sha256"]
            snapshot = ("reviewed direct official endpoint " if direct else "reviewed NPR/AP endpoint ") + fingerprint
            comparison.update(
                current_snapshot=snapshot_label(snapshot),
                current_snapshot_identity=snapshot,
                current_native_clock=(decision["source_update_labels"] or None) if direct
                                     else decision["source_update_labels"],
                current_stage=decision["current_stages"][0] if len(decision["current_stages"]) == 1 else None,
                current_round=decision["current_rounds"][0] if len(decision["current_rounds"]) == 1 else None,
                current_native_control_scope_qualification=(
                    "Direct original official candidate inventory under reviewed source policy "
                    + decision.get("direct_official_review_version",
                                   handoff.get("protected_official_review_version", version))
                    + ". All supplied named minor candidates and source-unassigned write-ins retained; no provider substitution, "
                    "respondent refit, new scientific eligibility or inferred count clock."
                    if direct else
                    "Fresh NPR/AP category D/R/O endpoints under reviewed stable-ID bridge "
                    + version + ". O may be an aggregate bucket; omitted legacy candidates and "
                    "their dated individual counts remain in the full crosswalk. No individual "
                    "Other allocation, respondent refit or new scientific eligibility."),
                current_source_scope=(
                    "Complete reviewed same-office original official candidate-choice frame, "
                    "including separately identified unassigned write-ins where supplied; "
                    "candidate counts are not ballots or turnout" if direct else
                    "Reviewed same-office statewide provider D/R/O category frame; "
                    "individual omitted candidate counts are not allocated"),
            )
            audit = copy.deepcopy(decision["reviewed_comparability"])
            if audit is not None:
                audit = current_comparability(audit, comparison, decision)
                audit["congressional_analytical_review"] = version
                row["contest_comparability"] = audit
                comparison["contest_comparability"] = copy.deepcopy(audit)
        else:
            old = row.get("congressional_analytical_status", {})
            snapshot = old.get("last_good_snapshot", comparison.get("current_snapshot"))
            comparison["current_snapshot"] = "FROZEN ANALYTICAL RESULT: " + snapshot_label(snapshot)
            comparison["current_snapshot_identity"] = snapshot
            comparison["current_native_control_scope_qualification"] = (
                "Not conditioned on fresh congressional returns. "
                + "; ".join(reason.replace(":", " / ").replace("_", " ")
                            for reason in decision["holds"])
                + ". Fresh recorded results remain available separately.")
        row["congressional_analytical_status"] = {
            "review_version": version, "decision": decision["decision"],
            "holds": decision["holds"], "conditioned_on_fresh_returns": decision["automatic_update_eligible"],
            "last_good_snapshot": snapshot,
        }
        if "source_aggregate_comparison" in row:
            if decision["automatic_update_eligible"]:
                row["source_aggregate_comparison"] = copy.deepcopy(comparison)
            else:
                row["source_aggregate_comparison"]["current_snapshot"] = comparison["current_snapshot"]
                row["source_aggregate_comparison"]["current_snapshot_identity"] = snapshot
    return result


def main(argv=None):
    from scripts.congressional_baselines import compile_baselines

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "seed", "scientific-review", "fec2020", "fec2022", "nebraska2024", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Review needs a new, explicit output directory")
    def read(path):
        body = path.read_bytes()
        return json.loads(gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body)
    review = prepare_review(read(args.snapshot)["congress"], read(args.seed),
                            read(args.scientific_review),
                            compile_baselines(args.fec2020, args.fec2022, args.nebraska2024))
    args.output.mkdir(parents=True)
    (args.output / "review.json.gz").write_bytes(compressed(review))
    for original, name in zip((args.fec2020, args.fec2022, args.nebraska2024), ORIGINAL_PATHS):
        shutil.copyfile(original, args.output / name)
    print(json.dumps({"review": pin(encoded(review)), "states": review["states"]}, sort_keys=True))


if __name__ == "__main__":
    main()
