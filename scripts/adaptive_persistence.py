"""Nested source-frame tests of demographic persistence, reusing cached couplings."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def mean(values):
    values = list(values)
    if not values:
        raise ValueError("An empty source population is not zero")
    return math.fsum(values) / len(values)


def solve(matrix, target):
    rows = [list(row) + [value] for row, value in zip(matrix, target)]
    for column in range(len(rows)):
        pivot = max(range(column, len(rows)), key=lambda row: abs(rows[row][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        if not math.isfinite(divisor) or abs(divisor) < 1e-14:
            raise ValueError("Singular adaptive-persistence system")
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(len(rows)):
            if row != column:
                ratio = rows[row][column]
                rows[row] = [a - ratio * b for a, b in zip(rows[row], rows[column])]
    result = [row[-1] for row in rows]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Nonfinite adaptive-persistence coefficients")
    return result


def inputs_from_simulation(simulation, spec):
    calibration = simulation["persistence_calibration"]
    factors = sorted(calibration["candidate_factors"])
    targets = {}
    for row in calibration["complete_poll_decisions"]:
        if row["target_fraction"] is not None:
            targets.setdefault(row["state_code"], []).append(row)
    curves, summaries = {}, {}
    for code in sorted(targets):
        kernels = [calibration["grid_kernels"][code + "|" + str(factor)] for factor in factors]
        curves[code] = [row["analytic"]["synthetic_gross_switching_share_of_modeled_current_voters"]
            for row in kernels]
        summaries[code] = [row["analytic"] for row in kernels]
    decisions = {(row["state_code"], row["dimension"], row["group"]): row
        for row in simulation["complete_demographic_decisions"]}
    if len(decisions) != len(simulation["complete_demographic_decisions"]):
        raise ValueError("Duplicate demographic source decisions")
    if any(not math.isfinite(value) or not 0 <= value <= 1
            for values in curves.values() for value in values):
        raise ValueError("Invalid cached gross switching fraction")
    features, availability = {}, []
    for code in sorted(targets):
        features[code] = {"nonvoter": summaries[code][0]["modeled_nonvoter_share"]}
        for name, key in (("age_gap", "age_contrast"), ("rurality_gap", "rurality_contrast")):
            dimension, left, right = spec[key]
            rows = [decisions.get((code, dimension, group)) for group in (left, right)]
            supported = all(row and row["disposition"] == spec["group_disposition"] for row in rows)
            value = None
            if supported:
                value = rows[0]["conditional_simulation"][0]["analytic"]["modeled_nonvoter_share"] \
                    - rows[1]["conditional_simulation"][0]["analytic"]["modeled_nonvoter_share"]
                features[code][name] = value
            availability.append(dict(state_code=code, feature=name, value=value,
                source_groups=[dict(dimension=dimension, group=group,
                    disposition=row["disposition"] if row else "missing_source_decision")
                    for group, row in zip((left, right), rows)],
                status="released_source_contrast" if supported else "held_missing_or_suppressed_group"))
    regions = {code: name for name, codes in spec["regions"].items() for code in codes}
    if len(regions) != sum(len(codes) for codes in spec["regions"].values()) \
            or any(code not in regions for code in targets):
        raise ValueError("Missing or repeated source-state region")
    losses = {code: [mean((value - row["target_fraction"]) ** 2 for row in targets[code])
        for value in curves[code]] for code in targets}
    optima = {code: min(range(len(factors)), key=lambda index: (losses[code][index], factors[index]))
        for code in targets}
    return dict(factors=factors, targets=targets, curves=curves, summaries=summaries,
        features=features, availability=availability, regions=regions,
        original_global_predictions=calibration["heldout_predictions"],
        losses=losses, state_optimum_indices=optima, _global_cache={})


def state_loss(data, code, index):
    if "losses" in data:
        return data["losses"][code][index]
    prediction = data["curves"][code][index]
    return mean((prediction - row["target_fraction"]) ** 2 for row in data["targets"][code])


def global_index(data, training):
    if not training:
        raise ValueError("No training states")
    key = tuple(sorted(training))
    cache = data.setdefault("_global_cache", {})
    if key in cache:
        return cache[key]
    result = min(range(len(data["factors"])), key=lambda index: (
        mean(state_loss(data, code, index) for code in training), data["factors"][index]))
    cache[key] = result
    return result


def fit(data, training, names, penalty, minimum):
    baseline = global_index(data, training)
    eligible = [code for code in training if all(name in data["features"][code] for name in names)]
    result = dict(training_states=sorted(training), eligible_training_states=sorted(eligible),
        feature_names=names, penalty=penalty, global_index=baseline,
        global_factor=data["factors"][baseline], coefficients=[], centers=[], scales=[])
    if not names or len(eligible) < minimum:
        result["status"] = "global" if not names else "held_insufficient_feature_training_states"
        return result
    centers = [mean(data["features"][code][name] for code in eligible) for name in names]
    scales = [math.sqrt(mean((data["features"][code][name] - center) ** 2 for code in eligible))
        for name, center in zip(names, centers)]
    scales = [value if value > 1e-12 else 1.0 for value in scales]
    x = [[(data["features"][code][name] - center) / scale
        for name, center, scale in zip(names, centers, scales)] for code in eligible]
    optima = data["state_optimum_indices"]
    y = [math.log2(data["factors"][optima[code]])
        - math.log2(data["factors"][baseline]) for code in eligible]
    matrix = [[mean(row[i] * row[j] for row in x) + (penalty if i == j else 0)
        for j in range(len(names))] for i in range(len(names))]
    target = [mean(row[i] * value for row, value in zip(x, y)) for i in range(len(names))]
    result.update(status="regularized_training_only", coefficients=solve(matrix, target),
        centers=centers, scales=scales)
    return result


def predict_index(data, model, code):
    if code in model["training_states"]:
        raise ValueError("A held-out prediction cannot be a training state")
    if model["status"] != "regularized_training_only":
        return model["global_index"], model["status"]
    if not all(name in data["features"][code] for name in model["feature_names"]):
        return model["global_index"], "held_missing_or_suppressed_feature_global_fallback"
    value = math.log2(model["global_factor"]) + math.fsum(
        coefficient * (data["features"][code][name] - center) / scale
        for coefficient, name, center, scale in zip(model["coefficients"], model["feature_names"],
            model["centers"], model["scales"]))
    index = min(range(len(data["factors"])), key=lambda i: (
        abs(math.log2(data["factors"][i]) - value), data["factors"][i]))
    return index, "adaptive_grid_prediction"


def choose_penalty(data, training, names, spec):
    if not names:
        return None, []
    scores = []
    for penalty in spec["penalties"]:
        inner = []
        for code in training:
            model = fit(data, [state for state in training if state != code],
                names, penalty, spec["minimum_training_states"])
            index, disposition = predict_index(data, model, code)
            inner.append(dict(heldout_state=code, factor=data["factors"][index],
                loss=state_loss(data, code, index), disposition=disposition,
                training_states=model["training_states"],
                eligible_training_states=model["eligible_training_states"], fit=model))
        scores.append(dict(penalty=penalty, state_balanced_mse=mean(row["loss"] for row in inner),
            complete_inner_predictions=inner))
    selected = min(scores, key=lambda row: (row["state_balanced_mse"], row["penalty"]))
    return selected["penalty"], scores


def metrics(rows):
    states = sorted({row["state_code"] for row in rows})
    return dict(tables=len(rows), states=len(states),
        table_mae_pp=mean(abs(row["error_pp"]) for row in rows),
        state_balanced_mae_pp=mean(mean(abs(row["error_pp"]) for row in rows
            if row["state_code"] == code) for code in states),
        state_balanced_mse_pp2=mean(mean(row["error_pp"] ** 2 for row in rows
            if row["state_code"] == code) for code in states),
        maximum_absolute_error_pp=max(abs(row["error_pp"]) for row in rows))


def run(simulation, spec):
    data = inputs_from_simulation(simulation, spec)
    states = sorted(data["targets"])
    blocks = [("state", code, [code]) for code in states]
    blocks += [("census_region", region, [code for code in states if data["regions"][code] == region])
        for region in sorted(set(data["regions"][code] for code in states))]
    predictions, folds = [], []
    for kind, block, heldout in blocks:
        training = [code for code in states if code not in heldout]
        for name, names in spec["models"].items():
            penalty, candidates = choose_penalty(data, training, names, spec)
            model = fit(data, training, names, penalty, spec["minimum_training_states"])
            fold = dict(block_type=kind, block=block, heldout_states=heldout,
                model=name, fit=model, inner_candidates=candidates)
            folds.append(fold)
            for code in heldout:
                index, disposition = predict_index(data, model, code)
                prediction = data["curves"][code][index]
                for target in data["targets"][code]:
                    predictions.append(dict(block_type=kind, block=block, model=name,
                        state_code=code, office=target["office"], id=target["id"],
                        factor=data["factors"][index], predicted_fraction=prediction,
                        reported_fraction=target["target_fraction"],
                        error_pp=100 * (prediction - target["target_fraction"]),
                        disposition=disposition,
                        exact_cached_coupling_key=code + "|" + str(data["factors"][index]),
                        analytic=data["summaries"][code][index]))
    summaries = {kind: {name: metrics([row for row in predictions
        if row["block_type"] == kind and row["model"] == name]) for name in spec["models"]}
        for kind in ("state", "census_region")}
    source_states = set(simulation.get("allocations", {})) or {
        row["state_code"] for row in simulation["complete_demographic_decisions"]
        if row.get("conditional_simulation")}
    benchmark_decisions = [dict(state_code=code, census_region=region,
        disposition="qualified_current_voter_benchmark" if code in data["targets"] else
            "held_no_reviewed_current_voter_table" if code in source_states else "held_no_source_sample")
        for code, region in sorted(data["regions"].items())]
    coverage = {kind: {name: dict(
        adaptive_state_predictions=len({row["state_code"] for row in predictions
            if row["block_type"] == kind and row["model"] == name and row["disposition"] == "adaptive_grid_prediction"}),
        changed_factor_state_predictions=len({row["state_code"] for row in predictions
            if row["block_type"] == kind and row["model"] == name and row["factor"] != next(
                base["factor"] for base in predictions if base["block_type"] == kind
                and base["model"] == "global" and base["id"] == row["id"])}),
        dispositions={disposition: len({row["state_code"] for row in predictions
            if row["block_type"] == kind and row["model"] == name and row["disposition"] == disposition})
            for disposition in sorted({row["disposition"] for row in predictions
                if row["block_type"] == kind and row["model"] == name})})
        for name in spec["models"]} for kind in ("state", "census_region")}
    original = {row["id"]: row for row in data["original_global_predictions"]}
    for row in predictions:
        if row["block_type"] == "state" and row["model"] == "global":
            before = original[row["id"]]
            if row["factor"] != before["selected_factor"] or row["predicted_fraction"] != before["predicted_fraction"]:
                raise ValueError("Cached accepted global holdout differs")
    return dict(status="conditional_source_frame_adaptive_persistence_transport_experiment",
        specification=spec, complete_feature_availability=data["availability"],
        complete_benchmark_decisions=benchmark_decisions, feature_and_factor_coverage=coverage,
        complete_outer_folds=folds, complete_heldout_predictions=predictions, metrics=summaries,
        qualified_source_states=states, current_voter_tables=sum(map(len, data["targets"].values())),
        automatic_ui_promotion=False, partisan_direction_or_return_fitting=False,
        original_model_or_source_counts_changed=False, entropy_or_seed_reductions_repeated=False,
        private_joint_cells_reconstructed=False, missing_group_values_imputed=False,
        population_transport_validated=False, demographic_party_association_identified=False,
        precinct_or_county_transition_estimates=False, observed_staying_home=None,
        uncertainty="Cross-source blocked prediction errors, not design confidence intervals or causal effects.")


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("simulation", "spec", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh adaptive-persistence result")
    simulation_body, spec_body = args.simulation.read_bytes(), args.spec.read_bytes()
    result = run(json.loads(simulation_body), json.loads(spec_body))
    result["input_sha256"] = dict(simulation=hashlib.sha256(simulation_body).hexdigest(),
        specification=hashlib.sha256(spec_body).hexdigest())
    args.output.write_bytes(encoded(result))
    print(json.dumps(dict(status=result["status"],metrics=result["metrics"],
        folds=len(result["complete_outer_folds"]), predictions=len(result["complete_heldout_predictions"])),
        sort_keys=True))


if __name__ == "__main__":
    main()
