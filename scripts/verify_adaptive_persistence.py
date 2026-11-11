"""Independent scalar checks of adaptive fitting, leakage and cached predictions."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def verify(simulation, result, specification=None):
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(message)

    def average(values):
        values = list(values)
        return math.fsum(values) / len(values)

    def close(a, b, message):
        require(math.isclose(a, b, abs_tol=2e-10, rel_tol=2e-10), message)

    spec, calibration = result["specification"], simulation["persistence_calibration"]
    if specification is not None:
        require(spec == specification, "Declared experiment specification changed")
    factors = sorted(calibration["candidate_factors"])
    targets = {}
    for row in calibration["complete_poll_decisions"]:
        if row["target_fraction"] is not None:
            targets.setdefault(row["state_code"], []).append(row)
    states = sorted(targets)
    regions = {code: name for name, codes in spec["regions"].items() for code in codes}
    curves, losses, feature_values, optima = {}, {}, {}, {}
    decisions = {(row["state_code"], row["dimension"], row["group"]): row
        for row in simulation["complete_demographic_decisions"]}
    feature_decisions = {(row["state_code"], row["feature"]): row
        for row in result["complete_feature_availability"]}
    require(len(feature_decisions) == len(result["complete_feature_availability"]) == 2 * len(states),
        "Feature qualification inventory differs")
    for code in states:
        curves[code] = [calibration["grid_kernels"][code + "|" + str(factor)]["analytic"][
            "synthetic_gross_switching_share_of_modeled_current_voters"] for factor in factors]
        losses[code] = [average((value - row["target_fraction"]) ** 2 for row in targets[code])
            for value in curves[code]]
        optima[code] = min(range(len(factors)), key=lambda index: (losses[code][index], factors[index]))
        feature_values[code] = {"nonvoter": calibration["grid_kernels"][code + "|" + str(factors[0])][
            "analytic"]["modeled_nonvoter_share"]}
        for name, key in (("age_gap", "age_contrast"), ("rurality_gap", "rurality_contrast")):
            dimension, left, right = spec[key]
            source = [decisions.get((code, dimension, group)) for group in (left, right)]
            available = all(row and row["disposition"] == spec["group_disposition"] for row in source)
            actual = feature_decisions[code, name]
            require(actual["source_groups"] == [dict(dimension=dimension, group=group,
                disposition=row["disposition"] if row else "missing_source_decision")
                for group, row in zip((left, right), source)], "Feature source dispositions differ")
            if available:
                value = source[0]["conditional_simulation"][0]["analytic"]["modeled_nonvoter_share"] \
                    - source[1]["conditional_simulation"][0]["analytic"]["modeled_nonvoter_share"]
                close(value, actual["value"], "Released demographic contrast differs")
                require(actual["status"] == "released_source_contrast", "Released feature mislabeled")
                feature_values[code][name] = value
            else:
                require(actual["value"] is None
                    and actual["status"] == "held_missing_or_suppressed_group",
                    "Suppressed source group was imputed")
    global_cache, fit_cache = {}, set()

    def global_choice(training):
        key = tuple(sorted(training))
        if key not in global_cache:
            global_cache[key] = min(range(len(factors)), key=lambda i: (
                average(losses[code][i] for code in key), factors[i]))
        return global_cache[key]

    def check_fit(model, training, names, penalty):
        require(model["training_states"] == sorted(training), "Training/holdout leakage")
        eligible = sorted(code for code in training if all(name in feature_values[code] for name in names))
        require(model["eligible_training_states"] == eligible, "Feature support changed")
        require(model["feature_names"] == names and model["penalty"] == penalty, "Undeclared fitting option")
        baseline = global_choice(training)
        require(model["global_index"] == baseline and model["global_factor"] == factors[baseline],
            "Training global optimum differs")
        key = json.dumps(model, sort_keys=True, separators=(",", ":"))
        if key in fit_cache:
            return
        fit_cache.add(key)
        if not names or len(eligible) < spec["minimum_training_states"]:
            require(model["status"] == ("global" if not names else "held_insufficient_feature_training_states")
                and model["coefficients"] == [], "Unqualified feature fit")
            return
        require(model["status"] == "regularized_training_only", "Changed fitting family")
        require(len(model["centers"]) == len(model["scales"]) == len(model["coefficients"]) == len(names),
            "Fitted feature dimensions differ")
        centers = [average(feature_values[code][name] for code in eligible) for name in names]
        scales = [math.sqrt(average((feature_values[code][name] - center) ** 2 for code in eligible))
            for name, center in zip(names, centers)]
        scales = [value if value > 1e-12 else 1.0 for value in scales]
        for actual, expected in zip(model["centers"], centers):
            close(actual, expected, "Training-only feature center differs")
        for actual, expected in zip(model["scales"], scales):
            close(actual, expected, "Training-only feature scale differs")
        x = [[(feature_values[code][name] - center) / scale
            for name, center, scale in zip(names, centers, scales)] for code in eligible]
        y = [math.log2(factors[optima[code]]) - math.log2(factors[baseline]) for code in eligible]
        beta = model["coefficients"]
        require(len(beta) == len(names), "Coefficient dimension differs")
        for i in range(len(names)):
            gradient = average(row[i] * (math.fsum(a * b for a, b in zip(row, beta)) - target)
                for row, target in zip(x, y)) + penalty * beta[i]
            close(gradient, 0, "Ridge normal-equation residual differs")

    def predict(model, code):
        if model["status"] != "regularized_training_only":
            return model["global_index"], model["status"]
        if not all(name in feature_values[code] for name in model["feature_names"]):
            return model["global_index"], "held_missing_or_suppressed_feature_global_fallback"
        value = math.log2(model["global_factor"]) + math.fsum(
            coefficient * (feature_values[code][name] - center) / scale
            for coefficient, name, center, scale in zip(model["coefficients"],
                model["feature_names"], model["centers"], model["scales"]))
        return min(range(len(factors)), key=lambda i: (
            abs(math.log2(factors[i]) - value), factors[i])), "adaptive_grid_prediction"

    outer = {}
    for fold in result["complete_outer_folds"]:
        kind, block, name = fold["block_type"], fold["block"], fold["model"]
        key = kind, block, name
        require(key not in outer, "Duplicate outer fold")
        outer[key] = fold
        heldout = [block] if kind == "state" else [code for code in states if regions[code] == block]
        require(fold["heldout_states"] == heldout, "Geographic holdout inventory differs")
        training = [code for code in states if code not in heldout]
        names = spec["models"][name]
        for candidate in fold["inner_candidates"]:
            require(candidate["penalty"] in spec["penalties"], "Undeclared tuning value")
            require([row["heldout_state"] for row in candidate["complete_inner_predictions"]] == training,
                "Incomplete inner validation")
            errors = []
            for row in candidate["complete_inner_predictions"]:
                code = row["heldout_state"]
                inner_training = [state for state in training if state != code]
                check_fit(row["fit"], inner_training, names, candidate["penalty"])
                require(row["training_states"] == inner_training
                    and row["eligible_training_states"] == row["fit"]["eligible_training_states"],
                    "Inner training record differs")
                index, disposition = predict(row["fit"], code)
                require(row["factor"] == factors[index] and row["disposition"] == disposition,
                    "Inner grid prediction differs")
                close(row["loss"], losses[code][index], "Inner state-balanced error differs")
                errors.append(row["loss"])
            close(candidate["state_balanced_mse"], average(errors), "Tuning objective differs")
        penalty = None
        if names:
            require([row["penalty"] for row in fold["inner_candidates"]] == spec["penalties"],
                "Tuning candidate inventory differs")
            penalty = min(fold["inner_candidates"],
                key=lambda row: (row["state_balanced_mse"], row["penalty"]))["penalty"]
        check_fit(fold["fit"], training, names, penalty)
    expected_folds = (len(states) + len({regions[code] for code in states})) * len(spec["models"])
    require(len(outer) == expected_folds, "Incomplete outer experiment")
    require(set(outer) == {("state", code, name) for code in states for name in spec["models"]}
        | {("census_region", region, name) for region in {regions[code] for code in states}
            for name in spec["models"]}, "Outer experiment inventory differs")
    seen = set()
    original = {row["id"]: row for row in calibration["heldout_predictions"]}
    for row in result["complete_heldout_predictions"]:
        key = row["block_type"], row["block"], row["model"]
        identity = key, row["id"]
        require(identity not in seen, "Duplicate heldout prediction")
        seen.add(identity)
        fold, code = outer[key], row["state_code"]
        require(code in fold["heldout_states"], "Wrong source-state prediction")
        index, disposition = predict(fold["fit"], code)
        require(row["factor"] == factors[index] and row["disposition"] == disposition,
            "Outer adaptive grid choice differs")
        close(row["predicted_fraction"], curves[code][index], "Cached gross prediction differs")
        target = next(value for value in targets[code] if value["id"] == row["id"])
        require(row["office"] == target["office"], "Heldout office differs")
        require(row["reported_fraction"] == target["target_fraction"], "Reported target changed")
        close(row["error_pp"], 100 * (curves[code][index] - target["target_fraction"]), "Prediction error differs")
        kernel_key = code + "|" + str(factors[index])
        require(row["exact_cached_coupling_key"] == kernel_key
            and row["analytic"] == calibration["grid_kernels"][kernel_key]["analytic"],
            "Original analytic coupling altered")
        if row["block_type"] == "state" and row["model"] == "global":
            require(row["factor"] == original[row["id"]]["selected_factor"]
                and row["predicted_fraction"] == original[row["id"]]["predicted_fraction"],
                "Accepted baseline comparison changed")
    require(len(seen) == 2 * len(spec["models"]) * sum(map(len, targets.values())),
        "Incomplete heldout prediction inventory")
    source_states = set(simulation.get("allocations", {})) or {
        row["state_code"] for row in simulation["complete_demographic_decisions"]
        if row.get("conditional_simulation")}
    expected_benchmarks = [dict(state_code=code, census_region=region,
        disposition="qualified_current_voter_benchmark" if code in targets else
            "held_no_reviewed_current_voter_table" if code in source_states else "held_no_source_sample")
        for code, region in sorted(regions.items())]
    require(result["complete_benchmark_decisions"] == expected_benchmarks,
        "Unbenchmarked states or missing sample were hidden")
    require(result["qualified_source_states"] == states
        and result["current_voter_tables"] == sum(map(len, targets.values())),
        "Benchmark support summary differs")
    require(set(result["metrics"]) == set(result["feature_and_factor_coverage"])
        == {"state", "census_region"}, "Metric block inventory differs")
    for kind, models in result["metrics"].items():
        require(set(models) == set(result["feature_and_factor_coverage"][kind]) == set(spec["models"]),
            "Metric model inventory differs")
        for name, reported in models.items():
            rows = [row for row in result["complete_heldout_predictions"]
                if row["block_type"] == kind and row["model"] == name]
            close(reported["table_mae_pp"], average(abs(row["error_pp"]) for row in rows), "MAE differs")
            close(reported["state_balanced_mae_pp"], average(average(abs(row["error_pp"])
                for row in rows if row["state_code"] == code) for code in states), "State MAE differs")
            close(reported["state_balanced_mse_pp2"], average(average(row["error_pp"] ** 2
                for row in rows if row["state_code"] == code) for code in states), "State MSE differs")
            require(reported["tables"] == len(rows) and reported["states"] == len(states),
                "Metric support differs")
            close(reported["maximum_absolute_error_pp"], max(abs(row["error_pp"]) for row in rows),
                "Maximum error differs")
            coverage = result["feature_and_factor_coverage"][kind][name]
            close(coverage["adaptive_state_predictions"], len({row["state_code"] for row in rows
                if row["disposition"] == "adaptive_grid_prediction"}), "Feature eligibility coverage differs")
            baseline_rows = {row["id"]: row for row in result["complete_heldout_predictions"]
                if row["block_type"] == kind and row["model"] == "global"}
            require(coverage["changed_factor_state_predictions"] == len({row["state_code"] for row in rows
                if row["factor"] != baseline_rows[row["id"]]["factor"]}), "Changed-factor coverage differs")
            require(coverage["dispositions"] == {disposition: len({row["state_code"] for row in rows
                if row["disposition"] == disposition}) for disposition in {row["disposition"] for row in rows}},
                "Fallback disposition coverage differs")
    require(not result["automatic_ui_promotion"] and not result["partisan_direction_or_return_fitting"]
        and not result["missing_group_values_imputed"] and not result["precinct_or_county_transition_estimates"],
        "Unsupported model promotion or population interpretation")
    require(not any(result[name] for name in ("population_transport_validated",
        "demographic_party_association_identified", "private_joint_cells_reconstructed",
        "original_model_or_source_counts_changed", "entropy_or_seed_reductions_repeated"))
        and result["observed_staying_home"] is None, "Unsupported validation or history claim")
    return dict(status="passed_independent_adaptive_persistence_verification", checks=checks,
        unique_fits_checked=len(fit_cache), outer_folds=len(outer), heldout_predictions=len(seen),
        same_state_and_region_leakage_rejected=True, all_cached_analytic_outputs_unchanged=True,
        suppressed_features_not_imputed=True, population_transport_validated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("simulation", "result", "spec", "proof"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.proof.exists():
        raise ValueError("Use a fresh independent verification receipt")
    simulation_body, spec_body = args.simulation.read_bytes(), args.spec.read_bytes()
    saved = json.loads(args.result.read_bytes())
    if saved["input_sha256"] != dict(simulation=hashlib.sha256(simulation_body).hexdigest(),
            specification=hashlib.sha256(spec_body).hexdigest()):
        raise ValueError("Pinned experiment inputs differ")
    result = verify(json.loads(simulation_body), saved, json.loads(spec_body))
    args.proof.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
