"""Audit every House district before interpreting aggregate party-margin changes."""

from collections import defaultdict
import copy
from fractions import Fraction
import math
import re

from scripts import house_clerk_endpoints as clerk

GENERIC = re.compile(r"^(?:write[- ]?ins?|all others|scattered|scattering|other write[- ]?ins?)$", re.I)
CURRENT_D = {"democratic", "democrat", "dem"}
CURRENT_R = {"republican", "rep"}


def margin(counts):
    denominator = counts["D"]+counts["R"]
    return Fraction(100*(counts["D"]-counts["R"]), denominator) if denominator else None


def district_rows(previous, current):
    groups = defaultdict(lambda: {"previous": [], "current": []})
    for row in previous:
        groups[row["district"]]["previous"].append(dict(
            name=row["candidate"], group=row["counted_as"], votes=row["votes"],
            named=any(line["role"] == "named_candidate" for line in row["source_lines"]),
            literal_parties=row["literal_affiliations"]))
    identities = set()
    urls, district_urls = {}, {}
    for row in current:
        if (row["year"] != "2026" or row["office"] != "U.S. House"
                or not row["district"].startswith(row["state_code"]+"-")
                or not re.fullmatch(r"[0-9]+", row["votes"])
                or not re.fullmatch(r"https://civicapi\.org/api/v2/race/[0-9]+", row["source_url"])):
            raise ValueError("Current candidate has an unqualified year, office, count or source")
        key = row["district"], row["name"], row["party"]
        if key in identities:
            raise ValueError("Repeated native candidate line")
        identities.add(key)
        if (row["source_url"] in urls and urls[row["source_url"]] != row["district"]
                or row["district"] in district_urls and district_urls[row["district"]] != row["source_url"]):
            raise ValueError("One native race cannot supply multiple districts or vice versa")
        urls[row["source_url"]] = row["district"]
        district_urls[row["district"]] = row["source_url"]
        party = row["party"].strip().casefold()
        group = "D" if party in CURRENT_D else "R" if party in CURRENT_R else "O"
        if clerk.NONCANDIDATE.fullmatch(row["name"].strip()):
            raise ValueError("Accounting row is not a candidate vote")
        groups[row["district"]]["current"].append(dict(name=row["name"], group=group,
            votes=int(row["votes"]), named=not bool(GENERIC.fullmatch(row["name"].strip())),
            literal_parties=[row["party"]], source_url=row["source_url"],
            source_updated_at=row["source_updated_at"]))
    result = []
    for district, sources in sorted(groups.items()):
        if not sources["previous"] or not sources["current"]:
            raise ValueError("A district missing at either endpoint cannot be zero-filled")
        phases = {}
        for phase, rows in sources.items():
            totals = {party: sum(row["votes"] for row in rows
                                if row["group"] == party and row["votes"] is not None)
                      for party in "DRO"}
            named = {party: [row["name"] for row in rows if row["group"] == party and row["named"]]
                     for party in "DR"}
            phases[phase] = dict(reported_counts=totals, named_major_party_candidates=named,
                major_party_presence={party: bool(named[party]) for party in "DR"},
                missing_major_party_counts=[row["name"] for row in rows
                    if row["group"] in "DR" and row["votes"] is None],
                multiple_same_party_nominees=any(len(names) > 1 for names in named.values()),
                source_candidate_rows=rows)
        before, after = phases["previous"], phases["current"]
        changed = before["major_party_presence"] != after["major_party_presence"]
        missing = bool(before["missing_major_party_counts"] or after["missing_major_party_counts"])
        common = (all(before["major_party_presence"].values()) and all(after["major_party_presence"].values())
                  and not missing and margin(before["reported_counts"]) is not None
                  and margin(after["reported_counts"]) is not None)
        result.append(dict(state_code=district[:2], district=district, **phases,
            major_party_coverage_changed=changed, missing_major_party_counts=missing,
            common_reported_DR_district_id=common,
            geographic_boundary_stability_independently_qualified=False,
            absent_party_is_not_zero_voter_preference=True))
    return result


def audit(previous_facts, current_candidates, controls):
    if previous_facts["source_pdf_sha256"] != "d4ba800fc17135b616ae556c92861080ab962d95916ace34b546c5aac824aec4":
        raise ValueError("Wrong pinned native House Clerk original")
    previous = clerk.candidate_totals(previous_facts["candidate_party_lines"])
    if previous != previous_facts["candidates"]:
        raise ValueError("Native candidate grouping changed")
    districts = district_rows(previous, current_candidates)
    if len(districts) != 435 or {r["state_code"] for r in districts} != set(clerk.STATES):
        raise ValueError("The complete 435-district/50-state audit is required")
    held = {row["state_code"]: row for row in controls["return_controls"] if row["office"] == "house"}
    if set(held) != set(clerk.STATES):
        raise ValueError("Every accepted current House control must remain explicit")
    states = []
    for code in sorted(clerk.STATES):
        local = [row for row in districts if row["state_code"] == code]
        totals = {phase: {party: sum(row[phase]["reported_counts"][party] for row in local)
                          for party in "DRO"} for phase in ("previous", "current")}
        if totals["current"] != held[code]["current"]:
            raise ValueError("Current source totals differ from accepted controls: "+code)
        changed = [row["district"] for row in local if row["major_party_coverage_changed"]]
        missing = [row["district"] for row in local if row["missing_major_party_counts"]]
        multiple = [row["district"] for row in local
                    if any(row[phase]["multiple_same_party_nominees"] for phase in ("previous", "current"))]
        before, after = margin(totals["previous"]), margin(totals["current"])
        raw = after-before if before is not None and after is not None else None
        common = [row for row in local if row["common_reported_DR_district_id"]]
        common_totals = {phase: {party: sum(row[phase]["reported_counts"][party] for row in common)
                                 for party in "DRO"} for phase in ("previous", "current")}
        common_before, common_after = margin(common_totals["previous"]), margin(common_totals["current"])
        common_change = common_after-common_before if common_before is not None and common_after is not None else None
        reasons = []
        if changed:
            reasons.append("Named D/R candidate coverage changed in "+", ".join(changed)+
                           "; aggregate vote-margin change is not a like-for-like statewide comparison.")
        if missing:
            reasons.append("Native major-party counts are absent/non-numeric in "+", ".join(missing)+
                           "; an unopposed/no-ballot contest is not zero voter support.")
        if multiple:
            reasons.append("Multiple same-party nominees require independently qualified election-stage scope in "+
                           ", ".join(multiple)+".")
        qualified = not reasons and raw is not None
        states.append(dict(state_code=code, districts=len(local), previous_counts=totals["previous"],
            current_counts=totals["current"],
            previous_named_D_districts=sum(row["previous"]["major_party_presence"]["D"] for row in local),
            previous_named_R_districts=sum(row["previous"]["major_party_presence"]["R"] for row in local),
            current_named_D_districts=sum(row["current"]["major_party_presence"]["D"] for row in local),
            current_named_R_districts=sum(row["current"]["major_party_presence"]["R"] for row in local),
            coverage_changed_districts=changed, missing_count_districts=missing,
            multiple_same_party_nominee_districts=multiple,
            like_for_like_statewide_source_comparison=qualified, hold_reasons=reasons,
            raw_reported_aggregate_margin_change_pp=float(raw) if raw is not None else None,
            raw_aggregate_is_not_voter_preference_swing=True,
            common_reported_DR_district_ids=[row["district"] for row in common],
            common_source_id_previous_counts=common_totals["previous"],
            common_source_id_current_counts=common_totals["current"],
            common_source_id_margin_change_pp=float(common_change) if common_change is not None else None,
            common_source_id_is_not_statewide_estimate=True,
            common_source_id_boundary_stability_qualified=False,
            aggregate_minus_common_source_id_change_pp=(
                float(raw-common_change) if raw is not None and common_change is not None else None),
            aggregate_minus_subset_is_descriptive_composition_not_causal_effect=True,
            current_counting_complete_independently_qualified=False))
    return dict(contract="participation.house_comparability.v1", states=states, district_queries=districts,
        complete_states=50, complete_districts=435, source_counts_changed=False,
        new_voter_or_turnout_inferences=False, generic_all_state_audit=True)


def requalify_model(priors, previous, review):
    from scripts import norc_house_model as simulation

    policy = {row["state_code"]: row for row in review["states"]}
    if set(policy) != {row["state_code"] for row in previous["rows"]}:
        raise ValueError("Comparability decisions must cover every model state")
    accepted, raw, changed = [], {}, []
    for row in previous["rows"]:
        code = row["state_code"]
        decision = policy[code]
        comparison = copy.deepcopy(row["reported_comparison"])
        raw[code] = copy.deepcopy(row.get("source_aggregate_comparison", comparison))
        if row["source_comparison_available"] and not decision["like_for_like_statewide_source_comparison"]:
            comparison = dict(status="unavailable", reason=" ".join(decision["hold_reasons"]),
                reported_change_pp=None, baseline_alignment_pp=None, other_and_unallocated_pp=None)
            changed.append(code)
        comparison["contest_comparability"] = copy.deepcopy(decision)
        accepted.append(dict(office="house", state_code=code, reported_comparison=comparison))
    expected = {row["state_code"]: row["reported_comparison"] for row in accepted}
    recalculated = simulation.build(priors, dict(rows=accepted), state_codes=changed) if changed else None
    result = copy.deepcopy(previous)
    if recalculated:
        for field in ("rows", "complete_assumption_cases", "complete_seed_cases", "complete_demographic_seed_cases"):
            result[field] = sorted(
                [row for row in previous[field] if row["state_code"] not in changed]+recalculated[field],
                key=lambda row: (row["state_code"], row.get("frame_scale", 0), row.get("affinity", 0),
                                 row.get("seed", 0), row.get("dimension", "")))
    for row in result["rows"]:
        code = row["state_code"]
        row["reported_comparison"] = expected[code]
        row["source_aggregate_comparison"] = raw[code]
        row["contest_comparability"] = copy.deepcopy(policy[code])
        if row["source_comparison_available"] and not policy[code]["like_for_like_statewide_source_comparison"]:
            raise ValueError("An incompatible endpoint still conditions a behavioral reconstruction")
    anchored = [row for row in result["rows"] if row["source_comparison_available"]]
    result["preconditioning_margin_MAE_pp"] = (math.fsum(
        abs(row["before_current_party_conditioning"]["prediction_error_observed_minus_predicted_pp"])
        for row in anchored)/len(anchored)) if anchored else None
    result["summary"] = dict(previous["summary"], states=len(result["rows"]), return_anchored=len(anchored),
        assumption_cases=len(result["complete_assumption_cases"]), seeds=len(result["complete_seed_cases"]),
        synthetic_agents=len(result["complete_seed_cases"])*10000,
        demographic_partition_seed_cases=len(result["complete_demographic_seed_cases"]),
        demographic_partition_agent_draws=len(result["complete_demographic_seed_cases"])*10000,
        complete_group_decisions=sum(len(row["groups"]) for row in result["rows"]))
    result["comparison_policy"] = dict(contract=review["contract"], all_districts_audited=435,
        all_states_audited=50, unchanged_major_party_coverage_required=True,
        raw_aggregate_is_not_preference_swing=True, changed_state_scenarios_recomputed=sorted(changed),
        other_state_numerics_reused=True, source_model_refitted=False,
        native_source_counts_changed=False, common_source_id_subtotals_are_not_statewide_estimates=True)
    if "endpoint_update" in result:
        result["prior_endpoint_update_provenance"] = result.pop("endpoint_update")
    result["endpoint_update"] = dict(source="All435district named-candidate coverage and count audit",
        changed_states=sorted(changed), source_model_refitted=False,
        frozen_current_snapshot="20261107T125502Z", native_source_counts_changed=False,
        qualified_state_comparisons=len(anchored), unchanged_state_numerics_and_seeds_reused=True)
    return result
