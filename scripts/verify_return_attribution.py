#!/usr/bin/env python3
"""Independent Fraction accounting for every modeled office/state and sensitivity case."""

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--inputs", type=Path, required=True)
parser.add_argument("--results", type=Path, required=True)
parser.add_argument("--proof", type=Path, required=True)
args = parser.parse_args()
if args.proof.exists():
    raise ValueError("Refuse to replace an independent verification")
inputs = json.loads(args.inputs.read_bytes())
results = json.loads(args.results.read_bytes())
assert results["input_sha256"] == hashlib.sha256(args.inputs.read_bytes()).hexdigest()
controls = {row["id"]: row for row in inputs["return_controls"]}
assert len(controls) == len(inputs["return_controls"]) == len(results["models"]) == 113
assert not results["unmatched_controls"]
checks = 0


def eq(actual, expected):
    global checks
    assert abs(Fraction(str(actual)) - expected) < Fraction(1, 10**48)
    checks += 1


for model in results["models"]:
    control = controls[model["id"]]
    key = control["state_code"] + "|2024"
    native = inputs["state_moments"][key]
    population = inputs["state_participation"][control["state_code"]]
    assert int(population["n"]) >= 100
    assert native["dimension"] == "overall" and native["scope"] == control["state_code"]
    assert control["geography_level"] == "state" and model["eligibility_death_migration"] is None
    assert model["independent_return_validation"] is False
    assert model["calibrated_to_historical_partisan_composition"] is False
    m0, native_m1, t0, t1 = (Fraction(native[key]) for key in ("m24", "m26", "t24", "t26"))
    fields = ("switching", "modeled_nonparticipation", "no_prior_contest_vote_entry", "other_choice", "unresolved")
    raw = {name: Fraction(native[name]) for name in fields}
    assert sum(raw.values()) == native_m1-m0
    d, r = (Fraction(control["current"][key]) for key in ("D", "R"))
    target_margin = 100*(d-r)/(d+r)
    target_m1 = target_margin*t1/100
    poll = inputs["office_poll_switching"].get(control["id"])
    if poll:
        masses = poll["arithmetic_from_rounded_percentages_per_100_current_group_voters"]
        raw["switching"] = 2*Fraction(population["modeled_voter_weight"])*(
            Fraction(str(masses["reported_trump_to_dem"]))-Fraction(str(masses["reported_harris_to_rep"])))/100
    assert len(model["sensitivity_scenarios"]) == 9
    values = {name: [] for name in [*fields, "return_frame_gap", "denominator"]}
    for case in model["sensitivity_scenarios"]:
        weights = dict(raw)
        weights["switching"] *= Fraction(case["switching_multiplier"])
        weights["modeled_nonparticipation"] *= Fraction(case["nonparticipation_multiplier"])
        weights["return_frame_gap"] = target_m1-m0-sum(weights.values())
        expected = {name: value*50*(t0+t1)/(t0*t1) for name, value in weights.items()}
        expected["denominator"] = 50*(m0+target_m1)*(t0-t1)/(t0*t1)
        for name, value in expected.items():
            eq(case["contributions_pp"][name], value)
            values[name].append(value)
        eq(case["source_frame_change_pp"], target_margin-100*m0/t0)
        assert sum(expected.values()) == target_margin-100*m0/t0
    for name in values:
        eq(model["assumption_ranges_pp"][name]["minimum"], min(values[name]))
        eq(model["assumption_ranges_pp"][name]["maximum"], max(values[name]))
    eq(model["reference"]["current_return_known_major_party_margin_pp"], target_margin)
    eq(model["reference"]["source_recalled_prior_margin_pp"], 100*m0/t0)
    if control["previous"] is not None:
        previous = control["previous"]
        margin = 100*Fraction(previous["D"]-previous["R"], previous["D"]+previous["R"])
        eq(model["prior_office_and_source_frame_gap_pp"], 100*m0/t0-margin)
        eq(model["observed_same_office_change_pp"], target_margin-margin)
    checks += 5

proof = dict(status="PASS_independent_Fraction_all113_office_state_models_and1017_scenarios",
    checks=checks, models=len(results["models"]), office_counts=dict(Counter(
        row["office"] for row in results["models"])), scenarios=1017,
    office_specific_switching=len(inputs["office_poll_switching"]),
    state_frames=len(inputs["state_moments"]), state_sources_not_allocated_locally=True,
    eligibility_death_migration_remain_unknown=True, original_survey_reduction_rerun=False,
    causal_or_population_certification=False)
with args.proof.open("x") as stream:
    json.dump(proof, stream, indent=2)
    stream.write("\n")
print(json.dumps(proof))
