"""Fit two additional NORC model families locally; never export private cases."""

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import log_loss
from sklearn.preprocessing import OrdinalEncoder
from threadpoolctl import threadpool_limits

from scripts import fit_norc_house_model as original
from scripts import validate_norc_historical_transfer as historical


FAMILIES = ("histogram_gradient_boosting", "extra_randomized_trees")
ROLES = ("house24_bridge", "house26_response", "historical_transfer")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def digest(body):
    return hashlib.sha256(body).hexdigest()


def private_write(path, body):
    if path.exists():
        raise ValueError("Do not overwrite a completed private stage")
    path.write_bytes(body)
    os.chmod(path, 0o600)


def checked_predictors(records, fields):
    forbidden = {"HOUSEVOTE", "LIKELYVOTER", "LVB", "respondent_ID", "current_return_party_counts", "QVOTE2022S"}
    if forbidden & set(fields) or any(set(row) != set(fields) for row in records):
        raise ValueError("Predictor leakage or changed native predictor contract")
    return [[str(row[field]) for field in fields] for row in records]


def design(records, fields, family, role, fit_records=None):
    reference = records if fit_records is None else fit_records
    checked_predictors(reference, fields)
    checked_predictors(records, fields)
    if family == FAMILIES[0]:
        encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, dtype=np.float64)
        encoder.fit([[str(row[field]) for field in fields] for row in reference])
        if any(len(values) > 255 for values in encoder.categories_):
            raise ValueError("A native category exceeds declared histogram support")
        return encoder, encoder.transform([[str(row[field]) for field in fields] for row in records])
    if family != FAMILIES[1]:
        raise ValueError("Unknown preregistered family")

    def features(row):
        if role != "historical_transfer":
            return original.features(row, tuple(field for field in fields if field not in ("state", "p24", "h22")))
        result = dict(row)
        for field in ("age", "education"):
            result["prior_" + field] = row["prior_2020_president"] + "|" + row[field]
        return result

    vectorizer = DictVectorizer()
    vectorizer.fit(features(row) for row in reference)
    return vectorizer, vectorizer.transform(features(row) for row in records)


def transform(encoder, records, fields, family, role):
    if any({"HOUSEVOTE", "LIKELYVOTER", "LVB", "respondent_ID", "current_return_party_counts", "QVOTE2022S"} & set(row)
           for row in records):
        raise ValueError("Outcome or identifier present in predictor records")
    records = [{field: row[field] for field in fields} for row in records]
    checked_predictors(records, fields)
    if family == FAMILIES[0]:
        return encoder.transform([[str(row[field]) for field in fields] for row in records])
    if role == "historical_transfer":
        def features(row):
            result = dict(row)
            for field in ("age", "education"):
                result["prior_" + field] = row["prior_2020_president"] + "|" + row[field]
            return result
    else:
        def features(row):
            return original.features(row, tuple(field for field in fields if field not in ("state", "p24", "h22")))
    return encoder.transform(features(row) for row in records)


def estimator(family, parameters, width):
    if family == FAMILIES[0]:
        return HistGradientBoostingClassifier(categorical_features=np.ones(width, dtype=bool), **parameters)
    return ExtraTreesClassifier(**parameters)


def metrics(labels, probabilities, weights):
    if probabilities.shape != (len(labels), 5) or not np.isfinite(probabilities).all():
        raise ValueError("Missing or nonfinite DRONU response probabilities")
    if np.min(probabilities) < 0 or not np.allclose(probabilities.sum(axis=1), 1, atol=1e-10):
        raise ValueError("Invalid response probability partition")
    known = np.isin(labels, (0, 1))
    return dict(source_weighted_log_loss=float(log_loss(labels, probabilities,
                    labels=list(range(5)), sample_weight=weights)),
        source_weighted_multiclass_brier=float(np.average(
            np.sum((probabilities - np.eye(5)[labels]) ** 2, axis=1), weights=weights)),
        known_major_party_source_log_loss=float(log_loss(labels[known], probabilities[known],
                    labels=list(range(5)), sample_weight=weights[known])))


def support_probabilities(probabilities, floor):
    if not 0 < floor < 1e-5:
        raise ValueError("Unqualified synthetic support floor")
    values = np.maximum(probabilities, floor)
    return values / values.sum(axis=1, keepdims=True)


def save_dataset(root, name, data):
    records, labels, weights = data
    private_write(root / (name + ".json.gz"), gzip.compress(encoded(records), mtime=0))
    path = root / (name + ".npz")
    if path.exists():
        raise ValueError("Existing native cache")
    np.savez_compressed(path, labels=labels, weights=weights)
    os.chmod(path, 0o600)


def load_dataset(root, name):
    records = json.loads(gzip.decompress((root / (name + ".json.gz")).read_bytes()))
    with np.load(root / (name + ".npz"), allow_pickle=False) as arrays:
        return records, arrays["labels"].copy(), arrays["weights"].copy()


def prepare(args, root, policy):
    for key, path in (("chep2026", args.chep), ("ap2024", args.ap2024), ("ap2022", args.ap2022)):
        if original.pin(path) != policy["source_input_sha256"][key]:
            raise ValueError("Changed original native source")
    names = ("bridge", "current", "historical_before", "historical_after")
    receipt = root / "prepared-private-inputs.json"
    if receipt.exists():
        if json.loads(receipt.read_bytes())["policy_sha256"] != digest(args.policy.read_bytes()):
            raise ValueError("Changed frozen experiment")
        return {name: load_dataset(root, name) for name in names}
    print("Preparing native source-weight frames once for this new experiment", flush=True)
    bridge, current = original.source_rows(args.chep, args.ap2024)
    before = historical.load(args.ap2022, "AP_VOTECAST_2022_midterm.csv")
    after = historical.load(args.ap2024, "AP_VOTECAST_2024_GENERAL.csv")
    datasets = dict(zip(names, (bridge, current, before, after)))
    for name, value in datasets.items():
        if not np.isfinite(value[2]).all() or np.min(value[2]) < 0 or value[2].sum() <= 0:
            raise ValueError("Changed native weight frame")
        save_dataset(root, name, value)
    private_write(receipt, encoded(dict(policy_sha256=digest(args.policy.read_bytes()),
        source_hashes=policy["source_input_sha256"], source_cases={k: len(v[1]) for k, v in datasets.items()},
        raw_cases_or_fine_cells_public=False)))
    return datasets


def fit_role(family, role, data, current, policy, output):
    receipt, predictions_path = output / (role + "-metrics.json"), output / (role + "-predictions.npz")
    if receipt.exists():
        metadata = json.loads(receipt.read_bytes())
        with np.load(predictions_path, allow_pickle=False) as arrays:
            probabilities = arrays["probabilities"].copy()
        if digest(predictions_path.read_bytes()) != metadata["private_prediction_sha256"]:
            raise ValueError("Changed completed private predictions")
        return metadata, probabilities
    records, labels, weights = data
    fields = policy["predictors"][role]
    parameters = policy["model_families"][family]
    print(f"Fitting {family}: {role}; cases={len(labels)}", flush=True)
    if role == "historical_transfer":
        before, after = data, current
        encoder, matrix = design(before[0], fields, family, role)
        model = estimator(family, parameters, matrix.shape[1])
        model.fit(matrix, before[1], sample_weight=before[2] / before[2].mean())
        if list(model.classes_) != list(range(5)):
            raise ValueError("A response class disappeared")
        probabilities = model.predict_proba(transform(encoder, after[0], fields, family, role))
        result = dict(metrics(after[1], probabilities, after[2]),
            train_cases=len(before[1]), test_cases=len(after[1]), training_year=2022, test_year=2024,
            weights="Native poll-close state weights; not final-vote weights",
            historical_test_not_a_matched_panel=True, current_return_targets_used=False)
    else:
        seed = policy["bridge_holdout_seed"] if role == "house24_bridge" else policy["current_holdout_seed"]
        train, test = original.split(records, seed)
        encoder, matrix = design(records, fields, family, role)
        model = estimator(family, parameters, matrix.shape[1])
        model.fit(matrix[train], labels[train], sample_weight=(weights / weights.mean())[train])
        if list(model.classes_) != list(range(5)):
            raise ValueError("A response class disappeared")
        result = dict(metrics(labels[test], model.predict_proba(matrix[test]), weights[test]),
            train_cases=len(train), test_cases=len(test), split_seed=seed,
            train_indices_sha256=digest(np.asarray(train, dtype="<i8").tobytes()),
            test_indices_sha256=digest(np.asarray(test, dtype="<i8").tobytes()),
            state_stratified_respondent_holdout=True, current_return_targets_used=False)
        model.fit(matrix, labels, sample_weight=weights / weights.mean())
        probabilities = model.predict_proba(transform(encoder, current[0], fields, family, role))
    np.savez_compressed(predictions_path, probabilities=probabilities)
    os.chmod(predictions_path, 0o600)
    result["private_prediction_sha256"] = digest(predictions_path.read_bytes())
    private_write(receipt, encoded(result))
    print(json.dumps(dict(family=family, role=role, **{k: v for k, v in result.items()
        if not k.startswith("private_")})), flush=True)
    return result, probabilities


def synthetic_priors(baseline, records, weights, earlier, later, family, validation, floor):
    result = copy.deepcopy(baseline)
    result["model_family"] = family
    result["synthetic_probability_support_floor"] = floor
    result["validation"] = validation
    result["assumptions"] = [
        "Native weights are globally rescaled by their mean for the preregistered "
        + family + " fit, never fitted to election returns in training"
        if text.startswith("Native weights are globally rescaled") else text
        for text in result["assumptions"]]
    earlier, later = support_probabilities(earlier, floor), support_probabilities(later, floor)
    for state, previous in baseline["states"].items():
        selected = np.asarray([i for i, row in enumerate(records) if row["state"] == state])
        w = weights[selected] / weights[selected].sum()
        matrices = earlier[selected, :, None] * later[selected, None, :] * w[:, None, None]
        joint = matrices.sum(axis=0)
        direct = np.zeros((5, 5))
        for k, i in enumerate(selected):
            direct[original.CHOICES.index(records[i]["h22"])] += w[k] * later[i]
        groups = []
        for dimension in original.DEMOGRAPHICS:
            displayed = np.zeros((5, 5))
            for template in previous["groups"]:
                if template["dimension"] != dimension or template["group"] == "unshown":
                    continue
                item = copy.deepcopy(template)
                item["prior_joint"] = None
                if item["available"]:
                    chosen = np.asarray([original.group_for(records[i], dimension) == item["group"] for i in selected])
                    aggregate = matrices[chosen].sum(axis=0)
                    displayed += aggregate
                    item["prior_joint"] = aggregate.tolist()
                groups.append(item)
            remainder = joint - displayed
            if remainder.min() < -1e-10:
                raise ValueError("Overlapping native disclosure partition")
            groups.append(dict(dimension=dimension, group="unshown",
                label="Other / undisclosed source categories", available=True,
                opaque_model_residual_not_a_new_native_group=True, prior_joint=np.maximum(remainder, 0).tolist()))
        result["states"][state] = dict(state_code=state, prior_joint=joint.tolist(),
            direct_2022_house_prior_joint=direct.tolist(), groups=groups,
            actual_joint_demographic_records_used=True, source_joint_cells_reconstructed_or_exported=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("chep", "ap2022", "ap2024", "baseline-priors", "policy", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if any((p / ".git").exists() for p in (root, *root.parents)):
        raise ValueError("All cases and prediction caches must stay private outside Git")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    policy = json.loads(args.policy.read_bytes())
    if policy["current_partisan_returns_used_for_training_or_model_selection"] is not False:
        raise ValueError("No current partisan-return fitting is permitted")
    baseline = json.loads(args.baseline_priors.read_bytes())
    datasets = prepare(args, root, policy)
    with threadpool_limits(limits=1):
        for family in FAMILIES:
            output = root / family
            output.mkdir(mode=0o700, exist_ok=True)
            validation = {}
            bridge_metrics, earlier = fit_role(family, "house24_bridge", datasets["bridge"],
                                               datasets["current"], policy, output)
            current_metrics, later = fit_role(family, "house26_response", datasets["current"],
                                              datasets["current"], policy, output)
            transfer_metrics, _ = fit_role(family, "historical_transfer", datasets["historical_before"],
                                           datasets["historical_after"], policy, output)
            for key, value in (("house_2024_bridge", bridge_metrics), ("current_2026_response", current_metrics),
                               ("historical_transfer", transfer_metrics)):
                validation[key] = {k: v for k, v in value.items() if not k.startswith("private_")}
            target = output / "public-safe-synthetic-priors.json"
            if not target.exists():
                priors = synthetic_priors(baseline, datasets["current"][0], datasets["current"][2],
                    earlier, later, family, validation, policy["probability_floor_for_synthetic_prior_support"])
                private_write(target, encoded(priors))
            print(f"Completed synthetic priors: {family}; 50 states; no private cases exported", flush=True)
    print("All newly declared families fitted; endpoint comparisons have not been used for selection", flush=True)


if __name__ == "__main__":
    main()
