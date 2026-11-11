#!/usr/bin/env python3
"""Connect NORC whole-frame moments to returns without calling unexplained change persuasion."""

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path


TERMS = ("switching", "modeled_nonparticipation", "no_prior_contest_vote_entry",
         "other_choice", "unresolved")
ZERO = Decimal(0)
HUNDRED = Decimal(100)


def number(value):
    if isinstance(value, bool):
        raise ValueError("A boolean is not a model moment or source count")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Nonfinite model input")
    return result


def count(value):
    result = number(value)
    if result < 0 or result != result.to_integral_value():
        raise ValueError("Return controls must retain exact nonnegative candidate counts")
    return result


def margin(returns):
    d, r = (count(returns[key]) for key in ("D", "R"))
    if d + r <= 0:
        raise ValueError("No reported known-major-party denominator")
    return HUNDRED * (d-r) / (d+r)


def scenario(moments, current_margin, switching_multiplier=1, nonparticipation_multiplier=1,
             switching_override=None):
    """Keep the exact symmetric normalized-margin denominator term."""
    m0, t0, t1 = (number(moments[key]) for key in ("m24", "t24", "t26"))
    if min(t0, t1) <= 0 or abs(m0) > t0:
        raise ValueError("Invalid source-frame known-choice denominators")
    modeled_m1 = number(current_margin) * t1 / HUNDRED
    scale = HUNDRED * (1/t0 + 1/t1) / 2
    raw = {key: number(moments[key]) for key in TERMS}
    if switching_override is not None:
        raw["switching"] = number(switching_override)
    raw["switching"] *= number(switching_multiplier)
    raw["modeled_nonparticipation"] *= number(nonparticipation_multiplier)
    # This includes office transport, selection and model error, not more switchers.
    raw["return_frame_gap"] = modeled_m1 - m0 - sum(raw.values(), ZERO)
    components = {key: value * scale for key, value in raw.items()}
    components["denominator"] = HUNDRED * (m0+modeled_m1) / 2 * (1/t1-1/t0)
    delta = current_margin - HUNDRED*m0/t0
    if abs(sum(components.values(), ZERO) - delta) > Decimal("1e-50"):
        raise AssertionError("Full source-frame contributions do not reconcile")
    return dict(contributions_pp=components, source_frame_change_pp=delta,
        source_recalled_prior_margin_pp=HUNDRED*m0/t0,
        current_return_known_major_party_margin_pp=current_margin)


def estimate(moments, control, participation, poll=None):
    with localcontext() as context:
        context.prec = 80
        if moments["scope"] != control["state_code"] or moments.get("dimension") != "overall":
            raise ValueError("Use the state's own whole-frame moments; no local survey allocation")
        if control.get("geography_level", "state") != "state":
            raise ValueError("State source moments cannot be allocated to local races")
        if control["office"] not in ("house", "senate", "governor"):
            raise ValueError("Unsupported office")
        if control["year"] != 2026 or moments["prior_election"] not in ("2024", "2022"):
            raise ValueError("Unreviewed comparison period")
        if control["office"] != "house" and moments["prior_election"] != "2024":
            raise ValueError("Cross-office transport must identify its presidential baseline")
        current_margin = margin(control["current"])
        baseline = margin(control["previous"]) if control.get("previous") is not None else None
        override = None
        switching_source = "NORC state whole-frame House model"
        if poll is not None:
            if (poll["state_code"] != control["state_code"] or poll["office"] != control["office"]
                    or poll["status"] != "published_joint_question_reviewed"
                    or moments["prior_election"] != "2024"):
                raise ValueError("Poll switching table does not match the state, office and baseline")
            masses = poll["arithmetic_from_rounded_percentages_per_100_current_group_voters"]
            override = 2 * number(participation["modeled_voter_weight"]) * (
                number(masses["reported_trump_to_dem"]) - number(masses["reported_harris_to_rep"])) / HUNDRED
            switching_source = "SSRS office-specific rounded switching masses transported to NORC modeled voters"
        reference = scenario(moments, current_margin, switching_override=override)
        cases = []
        for switching in ("0.5", "1", "1.5"):
            for nonparticipation in ("0.5", "1", "1.5"):
                cases.append(dict(switching_multiplier=switching, nonparticipation_multiplier=nonparticipation,
                    **scenario(moments, current_margin, switching, nonparticipation, override)))
        terms = reference["contributions_pp"]
        ranges = {key: dict(minimum=min(case["contributions_pp"][key] for case in cases),
            maximum=max(case["contributions_pp"][key] for case in cases)) for key in terms}
        prior_frame_gap = (reference["source_recalled_prior_margin_pp"] - baseline
                           if baseline is not None else None)
        observed_change = current_margin - baseline if baseline is not None else None
        if observed_change is not None and abs(
                sum(terms.values(), ZERO) + prior_frame_gap - observed_change) > Decimal("1e-50"):
            raise AssertionError("Previous-office/source-frame gap does not close observed change")
        total = reference["source_frame_change_pp"]
        return dict(id=control["id"], state_code=control["state_code"], office=control["office"],
            year=2026, status="conditional_source_weighted_model_not_individual_or_causal_attribution",
            baseline=dict(source_year=moments["prior_election"], source_office=moments["prior_office"],
                observed_previous_year=control.get("previous_year"), observed_previous_office=control["office"]),
            reference=reference, assumption_ranges_pp=ranges, sensitivity_scenarios=cases,
            observed_same_office_change_pp=observed_change, prior_office_and_source_frame_gap_pp=prior_frame_gap,
            switching_vs_nonparticipation_balance=(
                (abs(terms["switching"])-abs(terms["modeled_nonparticipation"]))
                / (abs(terms["switching"])+abs(terms["modeled_nonparticipation"]))
                if abs(terms["switching"])+abs(terms["modeled_nonparticipation"]) else None),
            dominant_modeled_term=max(TERMS, key=lambda key: abs(terms[key])),
            signed_share_of_source_frame_change_pct={
                key: value/total*HUNDRED if total else None for key, value in terms.items()},
            source_support=dict(raw_whole_state_n=int(participation["n"]),
                source_effective_n=participation["source_effective_n"]),
            evidence=dict(switching=switching_source,
                nonparticipation="NORC model-classified nonparticipation, not administratively observed staying home",
                candidate_returns=control, model_current_office=moments["current_office"],
                cross_office_transport=control["office"] != "house"),
            uncertainty_type="declared_effect-strength_sensitivity_not_confidence_or_identification_interval",
            sensitivity_assumptions=dict(switching_strength=["0.5", "1", "1.5"],
                nonparticipation_strength=["0.5", "1", "1.5"],
                gaps_recomputed_to_retain_return_constraints=True),
            eligibility_death_migration=None, unique_people=None,
            calibrated_to_historical_partisan_composition=False, independent_return_validation=False,
            limitations=[
                "The source frame is current respondents recalling past choice, not all original historical voters.",
                "The source weight target and field period remain unqualified; weights are not numbers of people.",
                "Senate/governor estimates explicitly transport source participation/House information unless office-specific switching is available.",
                "The return/frame gap is unallocated model, selection, timing and office mismatch, not additional persuasion or staying home.",
                "Prior contest nonvote does not establish no ballot, first-ever voting or newly eligible status.",
                "Source component endpoints are different scenarios and cannot be summed as a joint interval.",
                "No state survey estimate is allocated to counties, precincts or congressional districts."])


def serial(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    body = args.inputs.read_bytes()
    inputs = json.loads(body)
    modeled, unmatched = [], []
    for control in inputs["return_controls"]:
        key = control["state_code"] + "|" + str(control.get("model_prior_year", "2024"))
        moment = inputs["state_moments"].get(key)
        participation = inputs["state_participation"].get(control["state_code"])
        if moment is None or participation is None:
            unmatched.append(dict(id=control["id"], status="no_matching_NORC_state_frame_not_zero"))
            continue
        poll = inputs.get("office_poll_switching", {}).get(control["id"])
        modeled.append(estimate(moment, control, participation, poll))
    result = dict(status="computed_conditional_NORC_and_returns_models", models=modeled,
        unmatched_controls=unmatched, input_sha256=hashlib.sha256(body).hexdigest(),
        no_raw_survey_records=True, state_source_not_allocated_locally=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, default=serial, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(dict(modeled=len(modeled), unmatched=len(unmatched))))


if __name__ == "__main__":
    main()
