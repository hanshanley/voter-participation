"""Verify cached OOF predictions independently with native controls and math.fsum."""

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path


def main():
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    import house_pair_oof as fitting
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "private", "original-private", "native-control", "results", "policy", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    policy = json.loads(args.policy.read_bytes())
    assert digest(args.source) == policy["source_sha256"]
    prepared = json.loads(gzip.decompress((args.private / "prepared.json.gz").read_bytes()))
    assert prepared["policy_sha256"] == digest(args.policy)
    candidate = json.loads((args.private / "public-sufficient-candidate.json").read_bytes())
    actual = {(r["weight_frame"], r["model"], r["fold"]): r for r in candidate["rows"]}
    y = np.asarray(prepared["target"], dtype=int)
    split = np.asarray(prepared["folds"])
    checks = 0

    def equal(left, right):
        nonlocal checks
        assert left == right, "Independent OOF control mismatch"
        checks += 1

    def close(left, right):
        nonlocal checks
        assert math.isfinite(float(left)) and math.isfinite(float(right))
        assert math.isclose(float(left), float(right), rel_tol=5e-13, abs_tol=1e-10), "Independent reduction mismatch"
        checks += 1

    with args.source.open(encoding="utf-8-sig", newline="") as stream:
        for i, row in enumerate(csv.DictReader(stream)):
            p20 = {"1": "D", "2": "R", "4": "O", "5": "CONTEST_NONVOTE",
                   "6": "REPORTED_NONVOTE"}.get(row["CC20_410"], "UNKNOWN")
            born = row["birthyr_20"]
            age = None if born in fitting.native.MISSING else 2020-int(born)
            age_group = ("UNKNOWN" if age is None or not 18 <= age <= 110 else
                         "18_29" if age <= 29 else "30_44" if age <= 44 else "45_64" if age <= 64 else "65_PLUS")
            values = dict(p20=p20, age20=age_group,
                educ20="UNKNOWN" if row["educ_20"] in fitting.native.MISSING else row["educ_20"],
                state20="UNKNOWN" if row["inputstate_20"] in fitting.native.MISSING else row["inputstate_20"],
                p20_age20=p20+"|"+age_group,
                p20_educ20=p20+"|"+("UNKNOWN" if row["educ_20"] in fitting.native.MISSING else row["educ_20"]))
            equal(prepared["history_features"][i], {"p20": p20})
            equal(prepared["demographic_features"][i], values)
            equal(prepared["weights"][i], [row[name] for name in fitting.native.WEIGHTS])
            equal(prepared["target"][i], [
                fitting.ADMIN.index(fitting.native.history(row["TS_g2022"])),
                fitting.ADMIN.index(fitting.native.history(row["TS_g2024"])),
                fitting.H22.index(fitting.native.house(row, 22)),
                fitting.H24.index(fitting.native.house(row, 24))])
    equal(i+1, 6175)
    raw = Counter()
    grouped = {name: defaultdict(lambda: [0, Fraction(0), Fraction(0)]) for name in fitting.native.WEIGHTS}
    for target, row_weights in zip(y, prepared["weights"]):
        a0, a1, h0, h1 = map(int, target)
        key = "|".join((fitting.ADMIN[a0], fitting.H22[h0], fitting.ADMIN[a1], fitting.H24[h1]))
        raw[key] += 1
        for name, value in zip(fitting.native.WEIGHTS, row_weights):
            if value in fitting.native.MISSING or not Fraction(value):
                continue
            weight = Fraction(value)
            bucket = grouped[name][key]
            bucket[0] += 1
            bucket[1] += weight
            bucket[2] += weight*weight
    previous = json.loads(args.native_control.read_bytes())["scopes"]["ALL_SOURCE"]
    equal(dict(raw), previous["raw_full_joint"])
    for name in fitting.native.WEIGHTS:
        equal(set(grouped[name]), set(previous["frames"][name]["full_joint"]))
        for key, values in grouped[name].items():
            old = previous["frames"][name]["full_joint"][key]
            equal(values, [old["n"], Fraction(old["weight"]), Fraction(old["squared_weight"])])
    cached_components = 0

    def independent_scores(probabilities, labels, weights):
        losses, briers = [], []
        for p, label in zip(probabilities, labels):
            chosen = float(p[int(label)])
            losses.append(-math.log(chosen))
            briers.append(math.fsum(float(v)*float(v) for v in p)-2*chosen+1)
        return (math.fsum(float(w)*value for w, value in zip(weights, losses)),
                math.fsum(float(w)*value for w, value in zip(weights, briers)))

    for name in fitting.native.WEIGHTS:
        with np.load(args.private / f"predictions-{name}.npz", allow_pickle=False) as archive:
            data = {key: archive[key].copy() for key in archive.files}
        equal(bool(np.array_equal(data["target"], y)), True)
        equal(bool(np.array_equal(data["folds"], split)), True)
        weights = data["weights"]
        for fold in range(5):
            train = np.flatnonzero((split != fold) & (weights > 0))
            test = np.flatnonzero((split == fold) & (weights > 0))
            for level in ("history", "demographic"):
                features = prepared[level + "_features"]
                vectorizer = DictVectorizer(sparse=True)
                vectorizer.fit(features[i] for i in train)
                vocabulary = hashlib.sha256("\n".join(vectorizer.get_feature_names_out()).encode()).hexdigest()
                heads = {}
                for head, classes in fitting.HEADS.items():
                    path = args.private / "heads" / f"{name}-{fold}-{level}-{head}.npz"
                    with np.load(path, allow_pickle=False) as cache:
                        metadata = json.loads(str(cache["metadata"]))
                        probabilities = cache["probabilities"].copy()
                    equal(metadata["policy_sha256"], digest(args.policy))
                    equal(metadata["vocabulary_sha256"], vocabulary)
                    equal(metadata["train_indices_sha256"], hashlib.sha256(train.tobytes()).hexdigest())
                    equal(metadata["test_indices_sha256"], hashlib.sha256(test.tobytes()).hexdigest())
                    equal(probabilities.shape, (len(test), classes))
                    equal(bool(np.isfinite(probabilities).all() and (probabilities > 0).all()), True)
                    equal(bool(np.max(abs(probabilities.sum(axis=1)-1)) < 1e-12), True)
                    heads[head] = probabilities
                    cached_components += 1
                products = {
                    "admin": (heads["a22"][:, :, None]*heads["a24"][:, None, :]).reshape(-1, 9),
                    "house": (heads["h22"][:, :, None]*heads["h24"][:, None, :]).reshape(-1, 30)}
                for kind in ("admin", "house"):
                    equal(bool(np.array_equal(products[kind], data[f"independent_{level}_{kind}"][test])), True)
                    equal(bool(np.array_equal(heads[kind], data[f"paired_{level}_{kind}"][test])), True)
            for model in fitting.MODELS:
                row = actual[name, model, fold]
                equal(row["n"], len(test))
                close(row["weight_sum"], math.fsum(map(float, weights[test])))
                for kind, labels in (("admin", y[:, 0]*3+y[:, 1]), ("house", y[:, 2]*5+y[:, 3])):
                    probabilities = data[model+"_"+kind][test]
                    nll, brier = independent_scores(probabilities, labels[test], weights[test])
                    close(nll, row[kind+"_nll_sum"])
                    close(brier, row[kind+"_brier_sum"])
                known = test[(y[test, 0] < 2) & (y[test, 1] < 2)]
                probabilities = data[model+"_admin"][known][:, [0, 1, 3, 4]]
                probabilities = np.asarray([p/math.fsum(map(float, p)) for p in probabilities])
                nll, brier = independent_scores(probabilities, y[known, 0]*2+y[known, 1], weights[known])
                equal(row["known_admin_n"], len(known))
                close(row["known_admin_weight_sum"], math.fsum(map(float, weights[known])))
                close(nll, row["known_admin_nll_sum"])
                close(brier, row["known_admin_brier_sum"])
                if name == fitting.native.WEIGHTS[0]:
                    selected = test[(y[test, 0] == 0) & (y[test, 1] == 0) & (y[test, 2] < 2) & (y[test, 3] < 2)]
                    probabilities = data[model+"_house"][selected][:, [0, 1, 5, 6]]
                    probabilities = np.asarray([p/math.fsum(map(float, p)) for p in probabilities])
                    nll, brier = independent_scores(probabilities, y[selected, 2]*2+y[selected, 3], weights[selected])
                    equal(row["selected_source_n"], len(selected))
                    close(row["selected_weight_sum"], math.fsum(map(float, weights[selected])))
                    close(nll, row["selected_major_nll_sum"])
                    close(brier, row["selected_major_brier_sum"])
                    for column, pair in enumerate(("DD", "DR", "RD", "RR")):
                        close(row["selected_major_predictions"][pair],
                              math.fsum(float(w)*float(p) for w, p in zip(weights[selected], probabilities[:, column])))
        if name == fitting.native.WEIGHTS[0]:
            with np.load(args.original_private / f"predictions-{name}.npz", allow_pickle=False) as old:
                equal(set(old.files), set(data))
                for key in old.files:
                    equal(bool(np.array_equal(old[key], data[key], equal_nan=True)), True)
    equal(cached_components, 180)
    with (args.results / "synthetic-flows.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for model in fitting.MODELS:
        original = np.asarray([float(next(row["synthetic_selected_source_weight"] for row in rows
            if row["model"] == model and row["stage"] == "unconditioned" and
            row["previous_house"]+row["current_house"] == pair)) for pair in ("DD", "DR", "RD", "RR")]).reshape(2, 2)
        reference = np.asarray([float(next(row["reference_selected_source_weight"] for row in rows
            if row["model"] == model and row["previous_house"]+row["current_house"] == pair))
            for pair in ("DD", "DR", "RD", "RR")]).reshape(2, 2)
        fitted = original.copy()
        for iteration in range(20000):
            fitted *= (reference.sum(axis=1)/fitted.sum(axis=1))[:, None]
            fitted *= (reference.sum(axis=0)/fitted.sum(axis=0))[None, :]
            if max(np.max(abs(fitted.sum(axis=1)-reference.sum(axis=1))),
                   np.max(abs(fitted.sum(axis=0)-reference.sum(axis=0)))) < 1e-10:
                break
        else:
            raise AssertionError("Independent IPF did not converge")
        for column, pair in enumerate(("DD", "DR", "RD", "RR")):
            actual_value = next(row["synthetic_selected_source_weight"] for row in rows
                if row["model"] == model and row["stage"] == "matched_source_margins" and
                row["previous_house"]+row["current_house"] == pair)
            close(actual_value, fitted.ravel()[column])
    receipt = json.loads((args.private / "fitting-receipt.json").read_bytes())
    equal(receipt["successful_component_fits_new"], 108)
    equal(receipt["successful_component_fits_reused"], 72)
    report = dict(status="pass", checks=checks, source_cases=6175, cached_component_fits_verified=180,
        all_75_model_fold_frame_rows_independently_scored=True,
        all_native_targets_and_weight_frames_match_accepted_private_controls=True,
        all_predictors_match_contemporaneous2020_source_fields=True,
        all_primary_pre_correction_predictions_identical=True,
        score_backend="independent_math_fsum_and_math_log", source_margin_check="independent_iterative_IPF",
        policy_sha256=digest(args.policy), sufficient_sha256=digest(args.private/"public-sufficient-candidate.json"),
        verifier_sha256=digest(Path(__file__)), successful_fits_repeated=0,
        native_people_predictions_or_fine_cells_exported=False, population_validation=False)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
