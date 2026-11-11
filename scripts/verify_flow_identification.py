"""Independently verify primal tables and all bipartite-network cuts."""

import argparse
from decimal import Decimal as D
import hashlib
import itertools
import json
from pathlib import Path
import zipfile


def verify(result, accepted):
    checks = 0

    def require(condition):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError("Independent flow-bound check failed at " + str(checks))

    require(result["contract"] == "participation.gross_flow_identification.v1")
    require(len(result["decisions"]) == len(accepted["rows"]) == 113)
    original = {r["id"]: r for r in accepted["rows"]}
    require(len(original) == 113)
    case_by_id = {r["case_id"]: r for r in result["cases"]}
    require(len(case_by_id) == len(result["cases"]) == 356)
    retained_cases, bounded, held, witnesses, cut_count = set(), 0, 0, 0, 0

    def check_table(matrix, rows, columns):
        n = len(rows)
        require(len(matrix) == n and all(len(row) == n for row in matrix))
        matrix = [[D(v) for v in row] for row in matrix]
        for i in range(n):
            for value in matrix[i]:
                require(value.is_finite() and value >= 0)
            require(sum(matrix[i]) == rows[i])
            require(sum(matrix[j][i] for j in range(n)) == columns[i])
        return matrix

    for decision in result["decisions"]:
        require(decision["id"] in original)
        source = original[decision["id"]]
        for key in ("state_code", "office", "reported_comparison"):
            require(decision[key] == source[key])
        if source["point"] is None:
            require(decision["status"] == "unavailable" and not decision["case_ids"])
            require(decision["reason"] == source["reason"])
            continue
        require(decision["status"] == "conditional_bounds_not_identified_histories")
        require(len(decision["case_ids"]) == 4)
        previous, current = [source["reported_comparison"][key] for key in ("previous", "current")]
        has_other = "O" in previous and "O" in current
        require(("O" in previous) == ("O" in current))
        categories = list("DRON" if has_other else "DRX")
        expected_frames = {f"accepted_frame_{scale}": D(str(next(
            c["assumed_common_frame_units"] for c in source["complete_scenarios"]
            if c["persistence_scale"] == 1 and c["frame_scale"] == scale)))
            for scale in (0.8, 1.0, 1.25)}
        expected_frames["large_frame_counterexample"] = D(sum(previous.values())+sum(current.values()))
        require({case_by_id[key]["frame_name"] for key in decision["case_ids"]} == set(expected_frames))
        for identity in decision["case_ids"]:
            require(identity not in retained_cases)
            retained_cases.add(identity)
            case = case_by_id[identity]
            require(case["id"] == decision["id"] and case["categories"] == categories)
            frame = D(case["frame_units"])
            require(frame == expected_frames[case["frame_name"]])
            require(case["frame_is_measured_population"] is False)
            require(case["unknown_other_is_opaque_X"] == (not has_other))
            targets = []
            for votes in (previous, current):
                counts = [D(votes[key]) for key in categories[:-1]]
                targets.append(counts+[frame-sum(counts)])
            rows, columns = targets
            require(list(map(D, case["target_rows"])) == rows)
            require(list(map(D, case["target_columns"])) == columns)
            require(sum(rows) == sum(columns) == frame)
            definitions = {
                "retention": {(a, a) for a in "DR"},
                "switching": {("D", "R"), ("R", "D")},
                "outside_major_party": {(a, b) for a in "DR" for b in categories if b not in "DR"},
                "entry_to_major_party": {(a, b) for a in categories if a not in "DR" for b in "DR"},
                "no_current_contest_vote": {(a, "N") for a in "DR"},
                "other_choice": {(a, "O") for a in "DR"},
            }
            require(set(case["metrics"]) == set(definitions))
            n = len(categories)
            for metric, definition in definitions.items():
                value = case["metrics"][metric]
                if not has_other and metric in ("no_current_contest_vote", "other_choice"):
                    require(value["status"] == "unavailable_unknown_other_not_no_contest_vote")
                    require(value["lower"] is value["upper"] is value["denominator"] is None)
                    held += 1
                    continue
                bounded += 1
                denominator = sum(columns[:2]) if metric == "entry_to_major_party" else sum(rows[:2])
                require(D(value["denominator"]) == denominator and denominator > 0)
                require(value["status"] == "sharp_conditional_accounting_bounds")
                require(0 <= D(value["lower"]["value"]) <= D(value["upper"]["value"]) <= denominator)
                for end in ("lower", "upper"):
                    record = value[end]
                    matrix = check_table(record["witness"], rows, columns)
                    witnesses += 1
                    objective = sum((matrix[i][j] for i, a in enumerate(categories)
                        for j, b in enumerate(categories) if (a, b) in definition), D(0))
                    require(objective == D(record["value"]))
                    require(D(value[end+"_percent"]) == 100*objective/denominator)
                    edges = {(i, j) for i, a in enumerate(categories) for j, b in enumerate(categories)
                        if ((a, b) in definition) == (end == "upper")}
                    all_cuts = []
                    for row_side in itertools.product((False, True), repeat=n):
                        for col_side in itertools.product((False, True), repeat=n):
                            capacity = sum((rows[i] for i in range(n) if not row_side[i]), D(0))
                            capacity += sum((columns[j] for j in range(n) if col_side[j]), D(0))
                            capacity += frame*sum(row_side[i] and not col_side[j] for i, j in edges)
                            require(capacity >= (objective if end == "upper" else frame-objective))
                            all_cuts.append(capacity)
                            cut_count += 1
                    cut = record["cut"]
                    subset = cut["row_subset"]
                    require(type(subset) is int and 0 <= subset < (1 << n))
                    neighbors = sorted({j for i, j in edges if subset & (1 << i)})
                    require(cut["column_neighbors"] == neighbors)
                    certificate = sum((rows[i] for i in range(n) if not subset & (1 << i)), D(0))
                    certificate += sum((columns[j] for j in neighbors), D(0))
                    require(certificate == D(cut["capacity"]) == min(all_cuts))
                    require(objective == (certificate if end == "upper" else frame-certificate))
            is_counterexample = case["frame_name"] == "large_frame_counterexample"
            require(case["counterexample_not_fitted_estimate"] == is_counterexample)
            if is_counterexample:
                matrix = check_table(case["joint_zero_retention_and_switching_witness"], rows, columns)
                require(all(matrix[i][j] == 0 for i in (0, 1) for j in (0, 1)))
    require(retained_cases == set(case_by_id))
    require(bounded == 1912 and held == 224 and witnesses == 3824)
    for key in ("probability_model_or_partisan_fit_performed", "old_fits_rerun",
            "endpoints_determine_individual_histories", "independently_measured_population",
            "local_allocation", "joint_attainability_of_separate_bounds"):
        require(result[key] is False)
    for key in ("confidence_intervals", "measured_staying_home", "eligibility_deaths_migration"):
        require(result[key] is None)
    return dict(status="passed_independent_exact_primal_and_all_cut_verification", checks=checks,
        all_cut_evaluations=cut_count, complete_decisions=113, frame_cases=len(retained_cases),
        sharp_metric_bounds=bounded, explicit_metric_holds=held, extremal_primal_tables=witnesses,
        simultaneous_zero_retention_switching_counterexamples=89,
        numerical_tolerance_used=False, prior_fits_or_source_reductions_rerun=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--accepted-science", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.results / "complete-result.json").read_bytes())
    with zipfile.ZipFile(args.accepted_science) as archive:
        accepted = json.loads(archive.read("results/complete-result.json"))
    if hashlib.sha256(args.accepted_science.read_bytes()).hexdigest() != result["accepted_science_sha256"]:
        raise ValueError("Changed accepted input archive")
    proof = verify(result, accepted)
    if args.proof.exists():
        raise ValueError("Use a fresh proof path")
    args.proof.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof))
