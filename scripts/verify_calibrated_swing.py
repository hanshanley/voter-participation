"""Verify all endpoint constraints and Shapley effects via all 24 orderings."""

import argparse
import itertools
import json
import math
from pathlib import Path


TERMS = ("switching", "nonparticipation", "entry", "other_choice")


def verify(result, original):
    checks = 0

    def check(value):
        nonlocal checks
        checks += 1
        if not value:
            raise ValueError(f"Independent calibrated-swing check failed: {checks}")

    def margin(d, r):
        check(d >= 0 and r >= 0 and d+r > 0)
        return 100 * (d-r) / (d+r)

    originals = {row["id"]: row for row in original["rows"]}
    check(len(result["rows"]) == len(originals) == 113)
    identities = set()
    fits = 0
    for row in result["rows"]:
        check(row["id"] not in identities)
        identities.add(row["id"])
        old = originals[row["id"]]
        comparison = old["reported_comparison"]
        check(row["reported_comparison"] == comparison)
        check(row["state_code"] == old["state_code"] and row["office"] == old["office"])
        if comparison["status"] == "unavailable":
            check(row["point"] is None and row["ranges_pp"] is None and row["status"] == "unavailable")
            continue
        check(row["calibration_is_not_independent_validation"] is True)
        check(row["population_size_measured"] is False and row["measured_staying_home"] is None)
        check(len(row["complete_scenarios"]) == 9)
        check(row["point"] in row["complete_scenarios"])
        for case in row["complete_scenarios"]:
            fits += 1
            q, frame = case["synthetic_joint"], case["assumed_common_frame_units"]
            check(len(q) == 4 and all(len(values) == 4 for values in q))
            check(all(type(value) is float and math.isfinite(value) and value >= 0 for values in q for value in values))
            rows, columns = [sum(v) for v in q], [sum(q[i][j] for i in range(4)) for j in range(4)]
            check(abs(sum(rows)-1) < 1e-11)
            for counts, totals, targets in ((comparison["previous"], rows, case["target_rows"]),
                    (comparison["current"], columns, case["target_columns"])):
                for i, party in enumerate("DRO"):
                    check(abs(totals[i]-targets[i]) < 1e-11)
                    if party in counts:
                        check(abs(totals[i]*frame-counts[party]) < .0001)
                check(abs(totals[3]-targets[3]) < 1e-11)
            check(abs(margin(*rows[:2])-comparison["previous_margin_pp"]) < 1e-8)
            check(abs(margin(*columns[:2])-comparison["current_margin_pp"]) < 1e-8)
            changes = {key: [0.0, 0.0] for key in TERMS}
            for i, before in enumerate("DRON"):
                for j, after in enumerate("DRON"):
                    if i == j:
                        continue
                    kind = "switching" if i < 2 and j < 2 else (
                        "nonparticipation" if j == 3 else "entry" if i == 3 else "other_choice")
                    for k, party in enumerate("DR"):
                        changes[kind][k] += q[i][j]*((after == party)-(before == party))
            independent = {key: 0.0 for key in TERMS}
            for order in itertools.permutations(TERMS):
                d, r = rows[:2]
                before = margin(d, r)
                for key in order:
                    d += changes[key][0]
                    r += changes[key][1]
                    after = margin(d, r)
                    independent[key] += (after-before)/24
                    before = after
            for key in TERMS:
                check(abs(independent[key]-case["components_pp"][key]) < 1e-8)
            check(abs(sum(independent.values())-comparison["reported_change_pp"]) < 1e-8)
            gross = case["gross_shares_of_modeled_previous_major_party"]
            check(abs(sum(gross.values())-1) < 1e-10)
            check(abs(gross["retaining"]-(q[0][0]+q[1][1])/(rows[0]+rows[1])) < 1e-10)
        for key in TERMS:
            check(row["ranges_pp"][key]["minimum"] == min(c["components_pp"][key] for c in row["complete_scenarios"]))
            check(row["ranges_pp"][key]["maximum"] == max(c["components_pp"][key] for c in row["complete_scenarios"]))
    check(fits == 801 and len(identities) == 113)
    check(sum(row["point"] is None for row in result["rows"]) == 24)
    return dict(status="passed_independent_all_state_return_constraints", complete_decisions=113,
        complete_fits=fits, calibrated_comparisons=89, unavailable=24, checks=checks,
        all_native_counts_and_both_margins_preserved=True,
        all_24_permutation_Shapley_decompositions_checked=True,
        no_residual_effect_inserted=True, calibration_not_independent_behavioral_validation=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--returns", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = verify(json.loads(args.results.read_bytes()), json.loads(args.returns.read_bytes()))
    with args.output.open("x") as stream:
        json.dump(proof, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(proof))
