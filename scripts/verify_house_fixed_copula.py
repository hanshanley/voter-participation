"""Verify nested isolation, accepted outer fits, fixed margins and proper scores."""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path


def main():
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    import house_pair_oof as parent
    import house_fixed_copula as copula
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("private", "parent-private", "policy", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    digest = lambda body: hashlib.sha256(body).hexdigest()
    policy = json.loads(args.policy.read_bytes())
    prepared_bytes = (args.parent_private/"prepared.json.gz").read_bytes()
    assert digest(prepared_bytes) == policy["marginal_fit"]["prepared_sha256"]
    prepared = json.loads(gzip.decompress(prepared_bytes))
    data = json.loads((args.private/"public-sufficient-candidate.json").read_bytes())
    assert data["policy_sha256"] == digest(args.policy.read_bytes())
    y = np.asarray(prepared["target"], dtype=int)
    splits = np.asarray(prepared["folds"])
    labels = y[:, 2]*5+y[:, 3]
    curves = {(r["weight_frame"], r["level"], r["outer_fold"], r["theta"]): r for r in data["curves"]}
    decisions = {(r["weight_frame"], r["level"], r["outer_fold"]): r for r in data["decisions"]}
    scores = {(r["weight_frame"], r["level"], r["outer_fold"], r["kind"]): r for r in data["rows"]}
    checks, components, baseline_heads = 0, 0, 0
    binding = digest(json.dumps(policy["marginal_fit"], sort_keys=True).encode())

    def equal(left, right):
        nonlocal checks
        assert left == right, "Nested source isolation or accepted cache differs"
        checks += 1

    def close(left, right, tolerance=2e-9):
        nonlocal checks
        assert math.isfinite(float(left)) and math.isfinite(float(right))
        assert math.isclose(float(left), float(right), rel_tol=5e-12, abs_tol=tolerance), "Independent copula score differs"
        checks += 1

    def proper(p, target, weights):
        nll = math.fsum(float(w)*(-math.log(float(row[int(label)]))) for row, label, w in zip(p, target, weights))
        brier = math.fsum(float(w)*(math.fsum(float(v)*float(v) for v in row)-2*float(row[int(label)])+1)
                          for row, label, w in zip(p, target, weights))
        return nll, brier

    def certificate(joint, before, after, theta):
        kernel = np.ones(joint.shape[1:])
        kernel[0, 0] = kernel[1, 1] = theta
        logarithm = np.log(joint)-np.log(before)[:, :, None]-np.log(after)[:, None, :]-np.log(kernel)
        residual = logarithm-logarithm[:, :, -1][:, :, None]-logarithm[:, -1, :][:, None, :]+logarithm[:, -1, -1][:, None, None]
        equal(bool(np.max(abs(residual)) < 1e-8), True)
        equal(bool(np.max(abs(joint.sum(axis=2)-before)) <= 2.001e-12), True)
        equal(bool(np.max(abs(joint.sum(axis=1)-after)) <= 2.001e-12), True)

    for column, frame in enumerate(parent.native.WEIGHTS):
        weights = np.asarray([float(parent.native.weight(row[column]) or 0) for row in prepared["weights"]])
        with np.load(args.private/f"outer-{frame}.npz", allow_pickle=False) as archive:
            outer_data = {key: archive[key].copy() for key in archive.files}
        equal(bool(np.array_equal(outer_data["target"], y)), True)
        equal(bool(np.array_equal(outer_data["folds"], splits)), True)
        equal(bool(np.array_equal(outer_data["weights"], weights)), True)
        with np.load(args.parent_private/f"predictions-{frame}.npz", allow_pickle=False) as archive:
            accepted = {level: archive[f"independent_{level}_house"].copy() for level in ("history", "demographic")}
        for level in ("history", "demographic"):
            equal(bool(np.array_equal(outer_data[level+"_baseline"], accepted[level], equal_nan=True)), True)
            for outer in range(5):
                outer_test_raw = np.flatnonzero(splits == outer)
                outer_training_raw = np.flatnonzero(splits != outer)
                expected_inner = parent.folds([prepared["history_features"][i]["p20"] for i in outer_training_raw],
                                             policy["inner_split_seed"]+outer, 3)
                inner_full = np.full(len(y), -1, dtype=int)
                inner_full[outer_training_raw] = expected_inner
                chosen_indices = np.flatnonzero((splits != outer) & (weights > 0))
                with np.load(args.private/f"inner-{frame}-{outer}-{level}.npz", allow_pickle=False) as archive:
                    inner = {key: archive[key].copy() for key in archive.files}
                equal(bool(np.array_equal(inner["indices"], chosen_indices)), True)
                equal(bool(np.array_equal(inner["target"], y[chosen_indices])), True)
                equal(bool(np.array_equal(inner["weights"], weights[chosen_indices])), True)
                equal(bool(np.array_equal(inner["inner_folds"], inner_full[chosen_indices])), True)
                position = {int(index): i for i, index in enumerate(chosen_indices)}
                for fold in range(3):
                    train = np.flatnonzero((inner_full >= 0) & (inner_full != fold) & (weights > 0))
                    calibration = np.flatnonzero((inner_full == fold) & (weights > 0))
                    equal(np.intersect1d(train, outer_test_raw).size, 0)
                    equal(np.intersect1d(calibration, outer_test_raw).size, 0)
                    vocabulary = DictVectorizer(sparse=True)
                    vocabulary.fit(prepared[level+"_features"][i] for i in train)
                    vocabulary_hash = digest("\n".join(vocabulary.get_feature_names_out()).encode())
                    for head, classes in (("h22", 6), ("h24", 5)):
                        path = args.private/"heads"/f"{frame}-{outer}-{fold}-{level}-{head}.npz"
                        with np.load(path, allow_pickle=False) as archive:
                            metadata = json.loads(str(archive["metadata"]))
                            probabilities = archive["probabilities"].copy()
                        equal(metadata["marginal_fit_binding"], binding)
                        equal(metadata["weight_frame"], frame)
                        equal(metadata["train_indices_sha256"], digest(train.tobytes()))
                        equal(metadata["calibration_indices_sha256"], digest(calibration.tobytes()))
                        equal(metadata["excluded_outer_indices_sha256"], digest(outer_test_raw.tobytes()))
                        equal(metadata["vocabulary_sha256"], vocabulary_hash)
                        equal(metadata["native_weights_sha256"], digest(weights[train].tobytes()))
                        equal(probabilities.shape, (len(calibration), classes))
                        equal(bool(np.array_equal(probabilities, inner[head][[position[int(i)] for i in calibration]])), True)
                        components += 1
                independently_scored = {}
                for theta in copula.THETAS:
                    joint, iterations = copula.couple(inner["h22"], inner["h24"], theta)
                    certificate(joint, inner["h22"], inner["h24"], theta)
                    nll, brier = proper(joint.reshape(-1, 30), labels[chosen_indices], weights[chosen_indices])
                    record = curves[frame, level, outer, theta]
                    equal(record["calibration_n"], len(chosen_indices))
                    close(record["weight_sum"], math.fsum(map(float, weights[chosen_indices])))
                    close(record["nll_sum"], nll)
                    close(record["brier_sum"], brier)
                    independently_scored[theta] = nll/math.fsum(map(float, weights[chosen_indices]))
                chosen = copula.select_theta(independently_scored)
                equal(chosen, decisions[frame, level, outer]["selected_theta"])
                test = np.flatnonzero((splits == outer) & (weights > 0))
                margins = {}
                for head in ("h22", "h24"):
                    with np.load(args.parent_private/"heads"/f"{frame}-{outer}-{level}-{head}.npz", allow_pickle=False) as archive:
                        metadata = json.loads(str(archive["metadata"]))
                        margins[head] = archive["probabilities"].copy()
                    equal(metadata["policy_sha256"], policy["parent_policy_sha256"])
                    equal(metadata["test_indices_sha256"], digest(test.tobytes()))
                    baseline_heads += 1
                for kind, theta in (("baseline", 1.), ("calibrated", chosen)):
                    record = scores[frame, level, outer, kind]
                    joint = outer_data[level+"_"+kind][test].reshape(-1, 6, 5)
                    certificate(joint, margins["h22"], margins["h24"], theta)
                    nll, brier = proper(joint.reshape(-1, 30), labels[test], weights[test])
                    equal(record["n"], len(test))
                    close(record["weight_sum"], math.fsum(map(float, weights[test])))
                    close(record["nll_sum"], nll)
                    close(record["brier_sum"], brier)
                    for year, axis, labels_year in (("h22", 2, y[test, 2]), ("h24", 1, y[test, 3])):
                        projected = joint.sum(axis=axis)
                        a, b = proper(projected, labels_year, weights[test])
                        c, d = proper(margins[year], labels_year, weights[test])
                        close(a, c, 2e-6)
                        close(b, d, 2e-8)
                    if column == 0:
                        mask = (y[test, 0] == 0) & (y[test, 1] == 0) & (y[test, 2] < 2) & (y[test, 3] < 2)
                        selected_test = test[mask]
                        probability = joint.reshape(-1, 30)[mask][:, [0, 1, 5, 6]]
                        probability = np.asarray([row/math.fsum(map(float, row)) for row in probability])
                        nll, brier = proper(probability, y[selected_test, 2]*2+y[selected_test, 3], weights[selected_test])
                        equal(record["selected_n"], len(selected_test))
                        close(record["selected_weight_sum"], math.fsum(map(float, weights[selected_test])))
                        close(record["selected_nll_sum"], nll)
                        close(record["selected_brier_sum"], brier)
                        for j, pair in enumerate(("DD", "DR", "RD", "RR")):
                            close(record["selected_predictions"][pair],
                                  math.fsum(float(w)*float(p) for w, p in zip(weights[selected_test], probability[:, j])))
                print(json.dumps(dict(frame=frame, level=level, outer_fold=outer, status="independent_nested_checks_passed")), flush=True)
    equal(components, 180)
    equal(baseline_heads, 60)
    result = dict(status="pass", checks=checks, source_cases=6175, new_inner_fits_verified=180,
        accepted_outer_heads_verified_without_refit=60, calibration_curves_verified=270,
        outer_scores_verified=60, all_training_and_calibration_cases_exclude_outer_holdout=True,
        every_case_year_margin_and_dual_certificate_verified=True, original_outer_probabilities_byte_identical=True,
        independent_score_backend="math.fsum_and_math.log", native_cases_predictions_or_fine_cells_exported=False,
        independent_population_or2026_validation=False, successful_source_fits_repeated=False,
        policy_sha256=digest(args.policy.read_bytes()),
        sufficient_sha256=digest((args.private/"public-sufficient-candidate.json").read_bytes()),
        verifier_sha256=digest(Path(__file__).read_bytes()))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
