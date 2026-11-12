"""Independent endpoint, rational accounting, demographic and simulation checks."""

import argparse
from fractions import Fraction as F
import json
import math
from pathlib import Path


def verify(result, priors):
    count = 0

    def check(value):
        nonlocal count
        count += 1
        if not value:
            raise ValueError("Independent NORC model check failed: "+str(count))

    def independent(q, global_rows=None, global_columns=None):
        q = [[F(str(v)) for v in row] for row in q]
        rr = global_rows or [sum(row) for row in q]
        cc = global_columns or [sum(q[i][j] for i in range(5)) for j in range(5)]
        v0, v1, a0, a1 = sum(rr[:2]), sum(cc[:2]), rr[0]-rr[1], cc[0]-cc[1]
        parts = dict.fromkeys(("switching", "exit", "entry", "other_choice", "unresolved"), F(0))
        for i, a in enumerate("DRONU"):
            for j, b in enumerate("DRONU"):
                label = ("unresolved" if 4 in (i, j) else "switching" if {i, j} == {0, 1}
                    else "exit" if i < 2 and j == 3 else "entry" if i == 3 and j < 2 else "other_choice")
                delta_numerator = int(j == 0)-int(j == 1)-int(i == 0)+int(i == 1)
                delta_denominator = int(j < 2)-int(i < 2)
                numerator_part = F(50)*delta_numerator*(1/v0+1/v1)
                denominator_part = -F(50)*(a0+a1)*delta_denominator/(v0*v1)
                parts[label] += q[i][j]*(numerator_part+denominator_part)
        return parts, float(100*(a1/v1-a0/v0))

    check(result["contract"] == "participation.norc_house_demographic_model.v1")
    check(len(result["rows"]) == len(priors["states"]) == 50)
    check(len({r["state_code"] for r in result["rows"]}) == 50)
    check(result["confidence_intervals"] is None and result["local_allocation"] is False)
    check(result["demographic_dimensions_are_additive_together"] is False)
    check(result["current_party_totals_used_in_source_model_training"] is False)
    check(result["return_constraints_used_only_in_separate_conditional_reconstruction"] is True)
    for row in result["rows"]:
        q = row["joint"]
        check(len(q) == 5 and all(len(r) == 5 for r in q))
        for values in q:
            for value in values:
                check(math.isfinite(value) and value >= 0)
        check(abs(sum(map(sum, q))-1) < 1e-10)
        expected, delta = independent(q)
        check(abs(delta-row["point"]["total_change_pp"]) < 1e-8)
        for key, value in expected.items():
            check(abs(float(value)-row["point"]["contributions_pp"][key]) < 1e-8)
        check(abs(sum(row["point"]["contributions_pp"].values())-delta) < 1e-8)
        check(row["measured_staying_home"] is row["actual_first_ever_voting"] is row["eligibility_deaths_migration"] is None)
        check(row["unknown_source_response_is_not_nonvote"] is True)
        if row["source_comparison_available"]:
            frame = row["assumed_accounting_frame_units"]
            comparison = row["reported_comparison"]
            for party, index in zip("DRO", range(3)):
                check(abs(frame*sum(q[index])-comparison["previous"][party]) < .0001)
                check(abs(frame*sum(q[i][index] for i in range(5))-comparison["current"][party]) < .0001)
            check(abs(comparison["reported_change_pp"]-delta) < 1e-8)
            check(row["before_current_party_conditioning"]["current_party_totals_used"] is False)
        else:
            check(row["assumed_accounting_frame_units"] is None)
            check(row["reported_comparison"]["status"] == "unavailable")
        previous = [sum(F(str(v)) for v in values) for values in q]
        current = [sum(F(str(q[i][j])) for i in range(5)) for j in range(5)]
        source = priors["states"][row["state_code"]]
        original_groups = {(g["dimension"], g["group"]): g for g in source["groups"]}
        for group in row["groups"]:
            raw = original_groups[(group["dimension"], group["group"])]
            check(group["available"] == raw["available"])
            if not group["available"]:
                check(group["contributions_pp"] is group["net_participation_pp"] is group["total_contribution_pp"] is None)
                continue
            matrix = group["joint"]
            for i in range(5):
                for j in range(5):
                    source_probability = source["prior_joint"][i][j]
                    check(abs(matrix[i][j]-raw["prior_joint"][i][j]*q[i][j]/source_probability) < 1e-10)
            values, _ = independent(matrix, previous, current)
            for key, value in values.items():
                check(abs(float(value)-group["contributions_pp"][key]) < 1e-8)
                bounds = group["sensitivity_ranges_pp"][key]
                check(bounds["minimum"]-1e-8 <= float(value) <= bounds["maximum"]+1e-8)
            check(abs(sum(group["contributions_pp"].values())-group["total_contribution_pp"]) < 1e-8)
        for dimension in {g["dimension"] for g in row["groups"]}:
            selected = [g for g in row["groups"] if g["dimension"] == dimension and g["available"]]
            for key in expected:
                check(abs(sum(g["contributions_pp"][key] for g in selected)-float(expected[key])) < 1e-7)
    for scenario in result["complete_assumption_cases"]:
        parts, change = independent(scenario["joint"])
        check(abs(change-scenario["total_change_pp"]) < 1e-8)
        for key, value in parts.items():
            check(abs(float(value)-scenario["contributions_pp"][key]) < 1e-8)
    for seed in result["complete_demographic_seed_cases"]:
        check(seed["synthetic_agents"] == 10000 and seed["separate_nonadditive_demographic_partition"] is True)
        for key in seed["contributions_pp"]:
            check(abs(sum(g["contributions_pp"][key] for g in seed["groups"])-seed["contributions_pp"][key]) < 1e-7)
        check(abs(sum(g["allocated_change_pp"] for g in seed["groups"])-seed["total_change_pp"]) < 1e-7)
    return dict(status="passed_independent_NORC_endpoints_rational_accounting_and_demographic_simulations",
        checks=count, states=50, return_anchored_states=sum(r["source_comparison_available"] for r in result["rows"]),
        complete_demographic_decisions=sum(len(r["groups"]) for r in result["rows"]),
        assumption_cases=len(result["complete_assumption_cases"]),
        demographic_partition_seed_cases=len(result["complete_demographic_seed_cases"]),
        source_individual_histories_identified=False, population_validation_claimed=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "priors", "proof"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    proof = verify(json.loads((args.results / "complete-result.json").read_bytes()),
        json.loads(args.priors.read_bytes()))
    if args.proof.exists():
        raise ValueError("Use a fresh proof")
    args.proof.write_text(json.dumps(proof, indent=2, sort_keys=True)+"\n")
    print(json.dumps(proof))
