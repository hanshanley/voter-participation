"""Independently verify conditional-head isolation, all270 probabilities and source scores."""

import argparse
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path


def main():
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    import house_pair_oof as accepted
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("private", "parent-private", "policy", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    digest = lambda body: hashlib.sha256(body).hexdigest()
    policy = json.loads(args.policy.read_bytes())
    prepared_bytes = (args.parent_private/"prepared.json.gz").read_bytes()
    assert digest(prepared_bytes) == policy["prepared_sha256"]
    prepared = json.loads(gzip.decompress(prepared_bytes))
    sufficient = json.loads((args.private/"public-sufficient-candidate.json").read_bytes())
    assert sufficient["policy_sha256"] == digest(args.policy.read_bytes())
    target = np.asarray(prepared["target"], dtype=int)
    folds = np.asarray(prepared["folds"])
    rows = {(r["weight_frame"], r["level"], r["fold"], r["model"], r["cohort"]): r for r in sufficient["rows"]}
    forecasts = {(r["level"], r["fold"], r["model"], r["cohort"]): r for r in sufficient["forecasts"]}
    models = ("independent_pairs", "conditional_house_given_admin", "fixed_pair_marginals")
    keys = ("positive_same_major", "positive_changed_major", "positive_other_or_contest_nonvote",
            "positive_unknown_house", "explicit_nonvote_any_house", "unknown_history_any_house")
    checks, new_heads, old_heads = 0, 0, 0

    def equal(a, b):
        nonlocal checks
        assert a == b, "Four-axis source/cache binding differs"
        checks += 1

    def close(a, b, tolerance=2e-8):
        nonlocal checks
        a, b = float(a), float(b)
        assert math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=5e-12, abs_tol=tolerance), "Independent source arithmetic differs"
        checks += 1

    def proper(probability, labels, weights):
        nll = math.fsum(-float(w)*math.log(float(row[int(label)])) for row, label, w in zip(probability, labels, weights))
        brier = math.fsum(float(w)*(math.fsum(float(v)*float(v) for v in row)-2*float(row[int(label)])+1)
                          for row, label, w in zip(probability, labels, weights))
        return nll, brier

    def extra(source, pair):
        result = dict(source)
        result["admin_pair"] = str(pair)
        result["president_by_admin"] = source["p20"]+"|"+str(pair)
        return result

    for column, frame in enumerate(accepted.native.WEIGHTS):
        weights = np.asarray([float(accepted.native.weight(r[column]) or 0) for r in prepared["weights"]])
        with np.load(args.private/f"forecasts-{frame}.npz", allow_pickle=False) as archive:
            data = {key: archive[key].copy() for key in archive.files}
        equal(bool(np.array_equal(data["target"], target)), True)
        equal(bool(np.array_equal(data["folds"], folds)), True)
        equal(bool(np.array_equal(data["weights"], weights)), True)
        for level in ("history", "demographic"):
            source = prepared[level+"_features"]
            for fold in range(5):
                train = np.flatnonzero((folds != fold) & (weights > 0))
                test = np.flatnonzero((folds == fold) & (weights > 0))
                equal(np.intersect1d(train, test).size, 0)
                vocabulary = DictVectorizer(sparse=True)
                vocabulary.fit(extra(source[i], int(target[i, 0]*3+target[i, 1])) for i in train)
                hypothetical = [extra(source[i], pair) for i in test for pair in range(9)]
                equal(len(hypothetical), len(test)*9)
                equal([int(row["admin_pair"]) for row in hypothetical], list(range(9))*len(test))
                with np.load(args.private/"heads"/f"{frame}-{fold}-{level}.npz", allow_pickle=False) as archive:
                    metadata = json.loads(str(archive["metadata"]))
                    conditional = archive["probabilities"].copy().reshape(len(test), 9, 30)
                equal(metadata["policy_sha256"], digest(args.policy.read_bytes()))
                equal(metadata["train_indices_sha256"], digest(train.tobytes()))
                equal(metadata["test_indices_sha256"], digest(test.tobytes()))
                equal(metadata["hypothetical_case_indices_sha256"], digest(np.repeat(test, 9).tobytes()))
                equal(metadata["hypothetical_admin_pairs_sha256"], digest(np.tile(np.arange(9), len(test)).tobytes()))
                equal(metadata["vocabulary_sha256"], digest("\n".join(vocabulary.get_feature_names_out()).encode()))
                equal(metadata["native_training_weights_sha256"], digest(weights[train].tobytes()))
                equal(bool(np.max(abs(conditional.sum(axis=2)-1)) < 1e-12), True)
                new_heads += 1
                margins = {}
                for head in ("admin", "house"):
                    with np.load(args.parent_private/"heads"/f"{frame}-{fold}-{level}-{head}.npz", allow_pickle=False) as archive:
                        binding = json.loads(str(archive["metadata"]))
                        margins[head] = archive["probabilities"].copy()
                    equal(binding["policy_sha256"], policy["parent_policy_sha256"])
                    equal(binding["train_indices_sha256"], digest(train.tobytes()))
                    equal(binding["test_indices_sha256"], digest(test.tobytes()))
                    old_heads += 1
                equal(bool(np.array_equal(data[level+"_"+models[0]][test], margins["admin"][:, :, None]*margins["house"][:, None, :])), True)
                equal(bool(np.array_equal(data[level+"_"+models[1]][test], margins["admin"][:, :, None]*conditional)), True)
                fixed = data[level+"_"+models[2]][test]
                equal(bool(np.isfinite(fixed).all() and (fixed > 0).all()), True)
                equal(bool(max(np.max(abs(fixed.sum(axis=2)-margins["admin"])),
                               np.max(abs(fixed.sum(axis=1)-margins["house"]))) <= 2.001e-12), True)
                logarithm = np.log(fixed)-np.log(margins["admin"][:, :, None]*conditional)
                residual = logarithm-logarithm[:, :, -1][:, :, None]-logarithm[:, -1, :][:, None, :]+logarithm[:, -1, -1][:, None, None]
                equal(bool(np.max(abs(residual)) <= 1e-8), True)
                y, w = target[test], weights[test]
                masks = {"previous_voter_major": (y[:, 0] == 0) & (y[:, 2] < 2), "previous_nonvoter": y[:, 0] == 1}
                for model in models:
                    joint = data[level+"_"+model][test]
                    future = []
                    for i, row in enumerate(y):
                        value = [float(joint[i, row[0]*3+a, row[2]*5+h]) for a in range(3) for h in range(5)]
                        total = math.fsum(value)
                        future.append([v/total for v in value])
                    future = np.asarray(future)
                    queries = [("full_four_axis", np.ones(len(test), dtype=bool), joint.reshape(-1, 270),
                                (y[:, 0]*3+y[:, 1])*30+y[:, 2]*5+y[:, 3]),
                               ("marginal_house", np.ones(len(test), dtype=bool), joint.sum(axis=1), y[:, 2]*5+y[:, 3])]
                    for cohort, mask in masks.items():
                        queries.append((cohort+"_future15", mask, future, y[:, 1]*5+y[:, 3]))
                        admin = np.asarray([[math.fsum(row[:5]), math.fsum(row[5:10])] for row in future])
                        admin /= admin.sum(axis=1)[:, None]
                        queries.append((cohort+"_known_future_admin", mask & (y[:, 1] < 2), admin, y[:, 1]))
                    for cohort, mask, probabilities, labels in queries:
                        record = rows[frame, level, fold, model, cohort]
                        count = int(mask.sum())
                        required = 100 if cohort in ("full_four_axis", "marginal_house") else 30
                        equal(record["available"], count >= required)
                        if record["available"]:
                            equal(record["n"], count)
                            close(record["weight_sum"], math.fsum(map(float, w[mask])))
                            nll, brier = proper(probabilities[mask], labels[mask], w[mask])
                            close(record["nll_sum"], nll)
                            close(record["brier_sum"], brier)
                        else:
                            equal((record["n"], record["nll_sum"], record["brier_sum"]), (None, None, None))
                    if column == 0:
                        for cohort, mask in masks.items():
                            if int(mask.sum()) < 30:
                                continue
                            record = forecasts[level, fold, model, cohort]
                            selected = np.flatnonzero(mask)
                            probabilities = []
                            for i in selected:
                                value = future[i]
                                if cohort == "previous_nonvoter":
                                    probabilities.append([math.fsum(value[j:j+5]) for j in (0, 5, 10)])
                                else:
                                    previous = int(y[i, 2])
                                    probabilities.append([value[previous], value[1-previous], value[2]+value[3], value[4],
                                                          math.fsum(value[5:10]), math.fsum(value[10:15])])
                            names = ("positive_any_house", "explicit_nonvote_any_house", "unknown_history_any_house") if cohort == "previous_nonvoter" else keys
                            for j, name in enumerate(names):
                                close(record["predictions"][name], math.fsum(float(w[i])*float(p[j]) for i, p in zip(selected, probabilities)))
                print(json.dumps(dict(frame=frame, level=level, fold=fold, status="independent_four_axis_checks_passed")), flush=True)
    for reference in sufficient["references"]:
        names = ("positive_any_house", "explicit_nonvote_any_house", "unknown_history_any_house") if reference["cohort"] == "previous_nonvoter" else keys
        cells = {key: dict(n=0, weight=Fraction(0)) for key in names}
        for y, raw in zip(prepared["target"], prepared["weights"]):
            weight = accepted.native.weight(raw[0])
            selected = y[0] == 1 if reference["cohort"] == "previous_nonvoter" else y[0] == 0 and y[2] < 2
            if weight is None or not selected:
                continue
            if reference["cohort"] == "previous_nonvoter":
                index = y[1]
            elif y[1] > 0:
                index = 4 if y[1] == 1 else 5
            else:
                index = 0 if y[3] == y[2] else 1 if y[3] < 2 else 2 if y[3] < 4 else 3
            cell = cells[names[index]]
            cell["n"] += 1
            cell["weight"] += Fraction(weight)
        available = all(cell["n"] >= 30 for cell in cells.values())
        equal(reference["available"], available)
        if available:
            for name, value in cells.items():
                equal(reference["cells"][name]["n"], value["n"])
                equal(Fraction(reference["cells"][name]["weight"]), value["weight"])
        else:
            equal(reference["cells"], None)
    equal(new_heads, 30)
    equal(old_heads, 60)
    report = dict(status="pass", checks=checks, new_conditional_heads_verified=30,
        accepted_paired_heads_verified_without_refit=60, complete_score_queries_verified=540,
        all_test_predictions_enumerate_nine_hypothetical_pairs_without_future_targets=True,
        original_paired_admin_and_house_margins_and_dual_certificate_verified=True,
        independent_score_backend="math.fsum_and_math.log", all_prior_cohorts_and_disclosure_holds_verified=True,
        private_persons_predictions_or_fine_cells_exported=False, current2026_transport_validated=False,
        source_fits_repeated=False, policy_sha256=digest(args.policy.read_bytes()),
        sufficient_sha256=digest((args.private/"public-sufficient-candidate.json").read_bytes()),
        verifier_sha256=digest(Path(__file__).read_bytes()))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
