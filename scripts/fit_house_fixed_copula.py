"""Nested source-only calibration with cached outer margins and isolated inner fits."""

import argparse
import ast
import gzip
import hashlib
import json
import os
from pathlib import Path

import house_fixed_copula as copula
import house_pair_oof as parent


def digest(body):
    return hashlib.sha256(body).hexdigest()


def ast_binding():
    tree = ast.parse(Path(__file__).read_bytes())
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "inner_predictions")
    return digest(ast.dump(node).encode())


def inner_predictions(prepared, weights, outer, level, target, args, policy):
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    split = np.asarray(prepared["folds"])
    outer_training_raw = np.flatnonzero(split != outer)
    outer_test_raw = np.flatnonzero(split == outer)
    strata = [prepared["history_features"][i]["p20"] for i in outer_training_raw]
    inner_local = parent.folds(strata, policy["inner_split_seed"]+outer, policy["inner_folds"])
    inner = np.full(len(split), -1, dtype=int)
    inner[outer_training_raw] = inner_local
    selected = np.flatnonzero((split != outer) & (weights > 0))
    features = prepared[level+"_features"]
    predictions = {"h22": np.full((len(split), 6), np.nan), "h24": np.full((len(split), 5), np.nan)}
    new, reused = 0, 0
    binding = digest(json.dumps(policy["marginal_fit"], sort_keys=True).encode())
    for inner_fold in range(policy["inner_folds"]):
        train = np.flatnonzero((inner != inner_fold) & (inner >= 0) & (weights > 0))
        calibration = np.flatnonzero((inner == inner_fold) & (weights > 0))
        if min(len(train), len(calibration)) < 100:
            raise ValueError("Insufficient whole inner-fold source support")
        if np.intersect1d(train, outer_test_raw).size or np.intersect1d(calibration, outer_test_raw).size:
            raise ValueError("Outer held-out cases leaked into calibration")
        vectorizer = DictVectorizer(sparse=True)
        matrix_train = vectorizer.fit_transform(features[i] for i in train)
        matrix_calibration = vectorizer.transform(features[i] for i in calibration)
        for head, classes, column in (("h22", 6, 2), ("h24", 5, 3)):
            metadata = json.dumps(dict(marginal_fit_binding=binding, weight_frame=args.frame_name, outer_fold=outer,
                inner_fold=inner_fold, level=level, head=head,
                train_indices_sha256=digest(train.tobytes()), calibration_indices_sha256=digest(calibration.tobytes()),
                excluded_outer_indices_sha256=digest(outer_test_raw.tobytes()),
                vocabulary_sha256=digest("\n".join(vectorizer.get_feature_names_out()).encode()),
                native_weights_sha256=digest(weights[train].tobytes())), sort_keys=True)
            path = args.private/"heads"/f"{args.frame_name}-{outer}-{inner_fold}-{level}-{head}.npz"
            values, hit = parent.cached_head(path, matrix_train, matrix_calibration,
                target[train, column], weights[train], classes, metadata)
            predictions[head][calibration] = values
            new += int(not hit)
            reused += int(hit)
    if any(not np.isfinite(predictions[head][selected]).all() for head in predictions):
        raise ValueError("Calibration predictions did not cover the isolated outer training set")
    parent.secure_npz(args.private/f"inner-{args.frame_name}-{outer}-{level}.npz",
        h22=predictions["h22"][selected], h24=predictions["h24"][selected],
        indices=selected, inner_folds=inner[selected], weights=weights[selected], target=target[selected])
    return selected, predictions, new, reused


def read_outer(args, frame, outer, level, test, policy):
    import numpy as np
    probabilities = {}
    for head, classes in (("h22", 6), ("h24", 5)):
        path = args.parent_private/"heads"/f"{frame}-{outer}-{level}-{head}.npz"
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"]))
            value = archive["probabilities"].copy()
        if (metadata["policy_sha256"] != policy["parent_policy_sha256"] or
                metadata["test_indices_sha256"] != digest(test.tobytes()) or value.shape != (len(test), classes)):
            raise ValueError("Accepted outer-marginal cache binding differs")
        probabilities[head] = value
    return probabilities


def run(args, policy, prepared):
    import numpy as np
    target = np.asarray(prepared["target"], dtype=int)
    splits = np.asarray(prepared["folds"])
    full_target = target[:, 2]*5+target[:, 3]
    curves, decisions, rows = [], [], []
    new_fits, reused_fits = 0, 0
    parent_rows = json.loads(args.parent_sufficient.read_bytes())["rows"]
    parent_rows = {(row["weight_frame"], row["model"], row["fold"]): row for row in parent_rows}
    for column, frame in enumerate(parent.native.WEIGHTS):
        args.frame_name = frame
        weights = np.asarray([float(parent.native.weight(row[column]) or 0) for row in prepared["weights"]])
        outer_prediction = {}
        for level in ("history", "demographic"):
            outer_prediction[level+"_baseline"] = np.full((len(target), 30), np.nan)
            outer_prediction[level+"_calibrated"] = np.full((len(target), 30), np.nan)
            for outer in range(policy["outer_folds"]):
                selected, predictions, new, reused = inner_predictions(
                    prepared, weights, outer, level, target, args, policy)
                new_fits += new
                reused_fits += reused
                curve = {}
                for theta in copula.THETAS:
                    joint, iterations = copula.couple(predictions["h22"][selected], predictions["h24"][selected], theta)
                    scores = copula.metric(joint.reshape(-1, 30), full_target[selected], weights[selected])
                    curve[theta] = scores["nll_sum"]/float(weights[selected].sum())
                    curves.append(dict(weight_frame=frame, level=level, outer_fold=outer, theta=theta,
                        calibration_n=len(selected), weight_sum=format(float(weights[selected].sum()), ".17g"),
                        **{key: format(value, ".17g") for key, value in scores.items()},
                        **copula.prediction_diagnostics(joint, predictions["h22"][selected], predictions["h24"][selected], theta),
                        projection_iterations=iterations))
                chosen = copula.select_theta(curve)
                decisions.append(dict(weight_frame=frame, level=level, outer_fold=outer,
                                      selected_theta=chosen, calibration_logloss=curve[chosen],
                                      baseline_calibration_logloss=curve[1.]))
                test = np.flatnonzero((splits == outer) & (weights > 0))
                outer_margins = read_outer(args, frame, outer, level, test, policy)
                for kind, theta in (("baseline", 1.), ("calibrated", chosen)):
                    joint, iterations = copula.couple(outer_margins["h22"], outer_margins["h24"], theta)
                    values = joint.reshape(-1, 30)
                    outer_prediction[level+"_"+kind][test] = values
                    scores = copula.metric(values, full_target[test], weights[test])
                    row = dict(weight_frame=frame, level=level, outer_fold=outer, kind=kind, theta=theta,
                        n=len(test), weight_sum=format(float(weights[test].sum()), ".17g"),
                        **{key: format(value, ".17g") for key, value in scores.items()},
                        **copula.prediction_diagnostics(joint, outer_margins["h22"], outer_margins["h24"], theta),
                        projection_iterations=iterations)
                    if kind == "baseline":
                        previous = parent_rows[frame, "independent_"+level, outer]
                        if not np.allclose([float(previous["house_nll_sum"]), float(previous["house_brier_sum"])],
                                [scores["nll_sum"], scores["brier_sum"]], atol=1e-10, rtol=5e-13):
                            raise ValueError("Accepted baseline scores changed")
                    if column == 0:
                        mask = (target[test, 0] == 0) & (target[test, 1] == 0) & (target[test, 2] < 2) & (target[test, 3] < 2)
                        selected_test = test[mask]
                        if len(selected_test) < 100:
                            raise ValueError("Whole selected-cohort support hold")
                        probabilities = values[mask][:, [0, 1, 5, 6]]
                        probabilities /= probabilities.sum(axis=1)[:, None]
                        scores = copula.metric(probabilities, target[selected_test, 2]*2+target[selected_test, 3],
                                               weights[selected_test])
                        row.update(selected_n=len(selected_test),
                            selected_weight_sum=format(float(weights[selected_test].sum()), ".17g"),
                            selected_nll_sum=format(scores["nll_sum"], ".17g"),
                            selected_brier_sum=format(scores["brier_sum"], ".17g"),
                            selected_predictions={key: format(float(np.sum(weights[selected_test]*probabilities[:, j])), ".17g")
                                                  for j, key in enumerate(("DD", "DR", "RD", "RR"))})
                    rows.append(row)
                print(json.dumps(dict(frame=frame, level=level, outer_fold=outer,
                                      selected_theta=chosen, status="nested_calibration_and_heldout_score_complete")), flush=True)
        parent.secure_npz(args.private/f"outer-{frame}.npz", target=target, weights=weights,
                         folds=splits, **outer_prediction)
    result = dict(contract="participation.house_fixed_copula_sufficient.v1", source_rows=6175,
        policy_sha256=digest(args.policy.read_bytes()), curves=curves, decisions=decisions, rows=rows,
        source_code_transport_conditional=True, population_validation=False)
    (args.private/"public-sufficient-candidate.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    receipt = dict(status="complete_new_nested_fixed_marginal_calibration",
        new_inner_component_fits=new_fits, previously_new_inner_fits_reused=reused_fits,
        accepted_outer_marginal_fits_reused=60, accepted_outer_fits_repeated=0,
        inner_calibration_rows=len(curves), decisions=len(decisions), outer_score_rows=len(rows),
        policy_sha256=digest(args.policy.read_bytes()),
        sufficient_sha256=digest((args.private/"public-sufficient-candidate.json").read_bytes()))
    (args.private/"fitting-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent-private", "parent-sufficient", "policy", "private"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    policy = json.loads(args.policy.read_bytes())
    if (digest(Path(__file__).read_bytes()) != policy["driver_sha256"] or
            digest(Path(copula.__file__).read_bytes()) != policy["copula_sha256"] or
            digest(Path(parent.__file__).read_bytes()) != policy["parent_fitter_sha256"] or
            ast_binding() != policy["marginal_fit"]["inner_function_ast_sha256"] or
            digest((args.parent_private/"prepared.json.gz").read_bytes()) != policy["marginal_fit"]["prepared_sha256"] or
            digest(args.parent_sufficient.read_bytes()) != policy["parent_sufficient_sha256"]):
        raise ValueError("Frozen source/code/split binding differs")
    if (args.private/"fitting-receipt.json").exists():
        raise ValueError("Completed fits must be reused, not repeated")
    if Path(__file__).resolve().parents[1] in args.private.resolve().parents:
        raise ValueError("Native fits and predictions must stay outside the repository")
    prepared = json.loads(gzip.decompress((args.parent_private/"prepared.json.gz").read_bytes()))
    if prepared["policy_sha256"] != policy["parent_policy_sha256"]:
        raise ValueError("Accepted prepared-case binding differs")
    args.private.mkdir(parents=True, exist_ok=True, mode=0o700)
    (args.private/"heads").mkdir(exist_ok=True, mode=0o700)
    run(args, policy, prepared)


if __name__ == "__main__":
    main()
