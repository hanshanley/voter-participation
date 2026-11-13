"""Recondition changed reviewed official endpoints; never refit source models."""

import copy
import math

from scripts import house_official_sources as official
from scripts import norc_house_model as simulation


def controls(previous, candidates, queries_body):
    review = official.validate_current(candidates, queries_body)
    policies = {row["state_code"]: row for row in review["policies"]}
    result = copy.deepcopy(previous)
    for row in result["return_controls"]:
        code = row["state_code"]
        if row["office"] != "house" or code not in policies:
            continue
        policy = policies[code]
        selected = [candidate for candidate in review["candidates"] if candidate["state_code"] == code]
        totals = dict(D=0, R=0, O=0)
        for candidate in selected:
            group = "D" if candidate["party"] == "Democratic" else (
                "R" if candidate["party"] == "Republican" else "O")
            totals[group] += int(candidate["votes"])
        row.update(current=totals, missing_candidate_control_indices=[],
            full_candidate_control_rows=[dict(state_code=code, district=candidate["district"],
                candidate=candidate["name"], literal_party=candidate["party"],
                reported_district_votes=candidate["votes"], located_county_rows=None,
                located_county_votes=None, located_minus_reported=None,
                independent_validation=False, status="reviewed_pinned_official_candidate_source")
                for candidate in selected],
            source_native_clock=None, source_snapshot="native-query:" + policy["query_pin"]["sha256"],
            source_scope=policy["count_scope"], source_election_scope=policy["stage"],
            source_round=None, official_source_revision=copy.deepcopy(policy))
    return result


def build(priors, previous, audit):
    policy = {row["state_code"]: row for row in audit["states"]}
    sources = {row["state_code"]: row for row in audit["reviewed_official_source_revisions"]}
    if set(policy) != {row["state_code"] for row in previous["rows"]}:
        raise ValueError("The complete prior state inventory must remain")
    accepted, changed = [], []
    for old in previous["rows"]:
        code = old["state_code"]
        comparison = copy.deepcopy(old["reported_comparison"])
        decision = policy[code]
        if code in sources:
            if not old["source_comparison_available"] or not decision["like_for_like_statewide_source_comparison"]:
                raise ValueError("This successor cannot lift or bypass an existing endpoint hold")
            if comparison["previous"] != decision["previous_counts"]:
                raise ValueError("The previous native endpoint cannot change")
            before = simulation_margin(decision["previous_counts"])
            after = simulation_margin(decision["current_counts"])
            source = sources[code]
            comparison.update(current=copy.deepcopy(decision["current_counts"]),
                previous_margin_pp=before, current_margin_pp=after,
                reported_change_pp=decision["raw_reported_aggregate_margin_change_pp"],
                current_native_clock=None, current_snapshot="native-query:" + source["query_pin"]["sha256"],
                current_source_scope=source["count_scope"], current_stage=source["stage"],
                current_round=None, current_official_source_revision=copy.deepcopy(source),
                contest_comparability=copy.deepcopy(decision))
            if old["reported_comparison"]["current"] != comparison["current"]:
                changed.append(code)
        accepted.append(dict(office="house", state_code=code, reported_comparison=comparison))
    calculated = simulation.build(priors, dict(rows=accepted), state_codes=changed) if changed else None
    result = copy.deepcopy(previous)
    expected = {row["state_code"]: row["reported_comparison"] for row in accepted}
    for field in ("rows", "complete_assumption_cases", "complete_seed_cases",
                  "complete_demographic_seed_cases"):
        retained = [row for row in previous[field] if row["state_code"] not in changed]
        replacements = calculated[field] if calculated else []
        result[field] = sorted(copy.deepcopy(retained) + replacements,
            key=lambda row: (row["state_code"], row.get("frame_scale", 0), row.get("affinity", 0),
                row.get("seed", 0), row.get("dimension", "")))
    for row in result["rows"]:
        code = row["state_code"]
        if code in sources:
            row["reported_comparison"] = expected[code]
            row["source_aggregate_comparison"] = copy.deepcopy(expected[code])
            row["contest_comparability"] = copy.deepcopy(policy[code])
    old_mask = {row["state_code"] for row in previous["rows"] if row["source_comparison_available"]}
    new_mask = {row["state_code"] for row in result["rows"] if row["source_comparison_available"]}
    if new_mask != old_mask:
        raise ValueError("This source revision must preserve every existing model hold")
    for field in ("complete_assumption_cases", "complete_seed_cases", "complete_demographic_seed_cases"):
        if len(result[field]) != len(previous[field]):
            raise ValueError("A complete assumption/seed query inventory changed")
    anchored = [row for row in result["rows"] if row["source_comparison_available"]]
    result["preconditioning_margin_MAE_pp"] = math.fsum(abs(
        row["before_current_party_conditioning"]["prediction_error_observed_minus_predicted_pp"])
        for row in anchored) / len(anchored)
    result["summary"] = copy.deepcopy(previous["summary"])
    result["comparison_policy"].update(
        changed_state_scenarios_recomputed=sorted(changed), other_state_numerics_reused=True,
        source_model_refitted=False, native_source_counts_changed=False,
        native_source_counts_changed_definition="No repairs within the supplied native source counts.",
        input_source_counts_revised_from_previous_release=bool(changed))
    result["endpoint_update"] = dict(
        source="Reviewed complete official native queries; previous endpoints and learned priors unchanged",
        source_model_refitted=False, changed_states=sorted(changed),
        native_source_counts_revised_from_previous_release=bool(changed),
        source_count_repairs=0, unchanged_state_numerics_and_seeds_reused=True,
        current_native_clocks={code: source["native_updated_at"] for code, source in sources.items()},
        official_source_revisions=list(sources.values()),
        survey_weights_changed=False, independent_behavioral_validation=False,
        return_error_change_is_not_independent_model_fit_improvement=True)
    return result


def simulation_margin(counts):
    from fractions import Fraction
    return float(Fraction(100 * (counts["D"] - counts["R"]), counts["D"] + counts["R"]))
