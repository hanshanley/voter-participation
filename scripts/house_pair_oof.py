"""Private forward-source tests of independent versus cross-election paired heads."""

import argparse
import csv
from fractions import Fraction
import gzip
import hashlib
import json
import os
from pathlib import Path

import house_panel_validation as native


MODELS = ("pooled_history_pairs", "independent_history", "paired_history",
          "independent_demographic", "paired_demographic")
H22 = ("D", "R", "O", "CONTEST_NONVOTE", "REPORTED_NONVOTE", "UNKNOWN")
H24 = ("D", "R", "O", "CONTEST_NONVOTE", "UNKNOWN")
ADMIN = ("POSITIVE", "EXPLICIT_NONVOTE", "UNKNOWN")
FIPS = set("1 2 4 5 6 8 9 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split())
HEADS = {"a22": 3, "a24": 3, "h22": 6, "h24": 5, "admin": 9, "house": 30}


def pin(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prior(value):
    if value in native.MISSING or value in ("7", "98", "99"):
        return "UNKNOWN"
    if value not in ("1", "2", "4", "5", "6"):
        raise ValueError("Unqualified contemporaneous 2020 presidential code")
    return {"1": "D", "2": "R", "4": "O", "5": "CONTEST_NONVOTE",
            "6": "REPORTED_NONVOTE"}[value]


def features(row, demographic):
    p20 = prior(row["CC20_410"])
    result = {"p20": p20}
    if demographic:
        birth = row["birthyr_20"]
        age = None if birth in native.MISSING else 2020 - int(birth)
        age_bin = ("UNKNOWN" if age is None or not 18 <= age <= 110 else
                   "18_29" if age < 30 else "30_44" if age < 45 else
                   "45_64" if age < 65 else "65_PLUS")
        education = row["educ_20"]
        state = row["inputstate_20"]
        if education not in native.MISSING | set("123456"):
            raise ValueError("Unqualified native education code")
        if state not in native.MISSING | FIPS:
            raise ValueError("Unqualified baseline survey-state code")
        result.update(age20=age_bin, educ20="UNKNOWN" if education in native.MISSING else education,
                      state20="UNKNOWN" if state in native.MISSING else state)
        result.update(p20_age20=p20 + "|" + result["age20"], p20_educ20=p20 + "|" + result["educ20"])
    return result


def folds(strata, seed, count):
    import numpy as np
    result = np.full(len(strata), -1, dtype=int)
    rng = np.random.default_rng(seed)
    for label in sorted(set(strata)):
        indices = np.flatnonzero(np.asarray(strata) == label)
        rng.shuffle(indices)
        offset = int(rng.integers(count))
        result[indices] = (np.arange(len(indices)) + offset) % count
    assert set(result) == set(range(count))
    return result


def smoothed(raw, target, weights, classes):
    import numpy as np
    normalized = weights / weights.mean()
    q = np.bincount(target, weights=normalized, minlength=classes) + .5
    q /= q.sum()
    amount = 1 / (len(target) + 1)
    return (1 - amount) * raw + amount * q


def pooled(train_groups, test_groups, target, weights, classes):
    import numpy as np
    normalized = weights / weights.mean()
    global_prior = np.bincount(target, weights=normalized, minlength=classes) + .5
    global_prior /= global_prior.sum()
    lookup = {}
    for group in set(test_groups):
        selected = np.asarray(train_groups) == group
        values = np.bincount(target[selected], weights=normalized[selected], minlength=classes)
        values = values + 20 * global_prior
        lookup[group] = values / values.sum()
    return np.asarray([lookup[group] for group in test_groups])


def metrics(probabilities, target, weights):
    import numpy as np
    chosen = probabilities[np.arange(len(target)), target]
    logloss = -np.log(chosen)
    brier = (probabilities * probabilities).sum(axis=1) - 2 * chosen + 1
    return {"nll_sum": float(np.sum(weights * logloss, dtype=np.float64)),
            "brier_sum": float(np.sum(weights * brier, dtype=np.float64))}


def secure_npz(path, **values):
    import numpy as np
    temporary = path.with_suffix(".temporary.npz")
    np.savez_compressed(temporary, **values)
    temporary.replace(path)


def prepare(args, policy):
    import numpy as np
    path = args.private / "prepared.json.gz"
    if path.exists():
        value = json.loads(gzip.decompress(path.read_bytes()))
        if value["policy_sha256"] != pin(args.policy):
            raise ValueError("Private prepared cache belongs to another frozen design")
        return value
    full, history, target, weights = [], [], [], []
    reference = {key: {"n": 0, "weight": Fraction(0), "squared_weight": Fraction(0)}
                 for key in ("DD", "DR", "RD", "RR")}
    with args.panel.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            full.append(features(row, True))
            history.append(features(row, False))
            a0, a1 = ADMIN.index(native.history(row["TS_g2022"])), ADMIN.index(native.history(row["TS_g2024"]))
            h0, h1 = H22.index(native.house(row, 22)), H24.index(native.house(row, 24))
            target.append([a0, a1, h0, h1])
            weights.append([row[name] for name in native.WEIGHTS])
            w = native.weight(row[native.WEIGHTS[0]])
            if w is not None and a0 == a1 == 0 and h0 < 2 and h1 < 2:
                w = Fraction(w)
                item = reference[H22[h0] + H24[h1]]
                item["n"] += 1
                item["weight"] += w
                item["squared_weight"] += w * w
    if len(full) != 6175:
        raise ValueError("Changed retained-panel source size")
    old = json.loads(args.reference.read_bytes())
    if not old["source_code_transport_assumption_required"] or old["population_validation"]:
        raise ValueError("Reference must retain conditional coding and population-validation holds")
    old = next(row["cells"] for row in old["decisions"] if row["source"] == "CES_retained_panel" and row["available"])
    for key, values in reference.items():
        assert values["n"] == old[key]["n"]
        assert values["weight"] == Fraction(old[key]["weight"])
        assert values["squared_weight"] == Fraction(old[key]["squared_weight"])
    assigned = folds([row["p20"] for row in history], policy["split_seed"], policy["folds"]).tolist()
    value = dict(policy_sha256=pin(args.policy), demographic_features=full, history_features=history,
                 target=target, weights=weights, folds=assigned,
                 all_source_rows=6175, accepted_pooled_reference_reused_byte_bound=True)
    path.write_bytes(gzip.compress(json.dumps(value, sort_keys=True).encode(), mtime=0))
    return value


def cached_head(path, matrix_train, matrix_test, target, weights, classes, metadata):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    if path.exists():
        with np.load(path, allow_pickle=False) as cache:
            if str(cache["metadata"]) != metadata:
                raise ValueError("Successful fitted cache binding differs; do not silently refit")
            probabilities = cache["probabilities"]
            if (probabilities.shape != (matrix_test.shape[0], classes) or
                    not np.isfinite(probabilities).all() or not (probabilities > 0).all() or
                    np.max(abs(probabilities.sum(axis=1) - 1)) >= 1e-12):
                raise ValueError("Invalid successful prediction cache; do not silently refit")
            return probabilities, True
    model = LogisticRegression(C=.15, solver="lbfgs", max_iter=1000, tol=1e-6)
    normalized = weights / weights.mean()
    model.fit(matrix_train, target, sample_weight=normalized)
    raw = np.zeros((matrix_test.shape[0], classes))
    raw[:, model.classes_] = model.predict_proba(matrix_test)
    probabilities = smoothed(raw, target, weights, classes)
    assert np.isfinite(probabilities).all() and (probabilities > 0).all()
    assert np.max(abs(probabilities.sum(axis=1) - 1)) < 1e-12
    secure_npz(path, probabilities=probabilities, metadata=np.asarray(metadata))
    return probabilities, False


def run(args, policy, prepared):
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    target = np.asarray(prepared["target"], dtype=int)
    labels = dict(a22=target[:, 0], a24=target[:, 1], h22=target[:, 2], h24=target[:, 3],
                  admin=target[:, 0] * 3 + target[:, 1], house=target[:, 2] * 5 + target[:, 3])
    split = np.asarray(prepared["folds"])
    numeric = lambda v: float(native.weight(v) or 0)
    all_weights = np.asarray([[numeric(v) for v in row] for row in prepared["weights"]])
    rows, fits, reused = [], 0, 0
    for column, weight_name in enumerate(native.WEIGHTS):
        weights = all_weights[:, column]
        predictions = {model: {"admin": np.full((len(target), 9), np.nan),
                               "house": np.full((len(target), 30), np.nan)} for model in MODELS}
        for fold in range(policy["folds"]):
            train = np.flatnonzero((split != fold) & (weights > 0))
            test = np.flatnonzero((split == fold) & (weights > 0))
            if min(len(train), len(test)) < 100:
                raise ValueError("Whole source-fold support hold")
            groups = [row["p20"] for row in prepared["history_features"]]
            grouped = {kind: pooled([groups[i] for i in train], [groups[i] for i in test],
                                    labels[kind][train], weights[train], HEADS[kind])
                       for kind in ("admin", "house")}
            for kind in grouped:
                predictions[MODELS[0]][kind][test] = grouped[kind]
            for level in ("history", "demographic"):
                features_source = prepared[level + "_features"]
                vectorizer = DictVectorizer(sparse=True)
                matrix_train = vectorizer.fit_transform(features_source[i] for i in train)
                matrix_test = vectorizer.transform(features_source[i] for i in test)
                vocabulary_hash = hashlib.sha256("\n".join(vectorizer.get_feature_names_out()).encode()).hexdigest()
                outputs = {}
                for head, classes in HEADS.items():
                    metadata = json.dumps(dict(policy_sha256=pin(args.policy), weight_frame=weight_name,
                        fold=fold, feature_level=level, head=head, vocabulary_sha256=vocabulary_hash,
                        train_indices_sha256=hashlib.sha256(train.tobytes()).hexdigest(),
                        test_indices_sha256=hashlib.sha256(test.tobytes()).hexdigest()), sort_keys=True)
                    cache = args.private / "heads" / f"{weight_name}-{fold}-{level}-{head}.npz"
                    outputs[head], hit = cached_head(cache, matrix_train, matrix_test, labels[head][train],
                                                     weights[train], classes, metadata)
                    reused += int(hit)
                    fits += int(not hit)
                independent_admin = (outputs["a22"][:, :, None] * outputs["a24"][:, None, :]).reshape(-1, 9)
                independent_house = (outputs["h22"][:, :, None] * outputs["h24"][:, None, :]).reshape(-1, 30)
                for name, result in ((f"independent_{level}", {"admin": independent_admin, "house": independent_house}),
                                     (f"paired_{level}", {"admin": outputs["admin"], "house": outputs["house"]})):
                    for kind, values in result.items():
                        predictions[name][kind][test] = values
            for model in MODELS:
                row = dict(weight_frame=weight_name, model=model, fold=fold, n=len(test),
                           weight_sum=format(float(weights[test].sum()), ".17g"))
                for kind in ("admin", "house"):
                    values = metrics(predictions[model][kind][test], labels[kind][test], weights[test])
                    row.update({kind + "_" + key: format(value, ".17g") for key, value in values.items()})
                known = test[(target[test, 0] < 2) & (target[test, 1] < 2)]
                if len(known) < 100:
                    raise ValueError("Whole known-history source-fold support hold")
                conditional = predictions[model]["admin"][known][:, [0, 1, 3, 4]]
                conditional /= conditional.sum(axis=1)[:, None]
                values = metrics(conditional, target[known, 0] * 2 + target[known, 1], weights[known])
                row.update(known_admin_n=len(known),
                           known_admin_weight_sum=format(float(weights[known].sum()), ".17g"),
                           **{"known_admin_" + key: format(value, ".17g") for key, value in values.items()})
                if column == 0:
                    selected = test[(target[test, 0] == 0) & (target[test, 1] == 0) &
                                    (target[test, 2] < 2) & (target[test, 3] < 2)]
                    if len(selected) < 100:
                        raise ValueError("Whole primary selected-fold support hold")
                    probabilities = predictions[model]["house"][selected][:, [0, 1, 5, 6]]
                    probabilities /= probabilities.sum(axis=1)[:, None]
                    expected = np.sum(weights[selected, None] * probabilities, axis=0, dtype=np.float64)
                    row["selected_source_n"] = len(selected)
                    row["selected_weight_sum"] = format(float(weights[selected].sum()), ".17g")
                    values = metrics(probabilities, target[selected, 2] * 2 + target[selected, 3], weights[selected])
                    row.update({"selected_major_" + key: format(value, ".17g") for key, value in values.items()})
                    row["selected_major_predictions"] = {
                        key: format(value, ".17g") for key, value in zip(("DD", "DR", "RD", "RR"), expected)}
                rows.append(row)
            print(json.dumps(dict(weight_frame=weight_name, fold=fold, status="all_five_OOF_hypotheses_scored")), flush=True)
        secure_npz(args.private / f"predictions-{weight_name}.npz", target=target, folds=split, weights=weights,
                   **{name + "_" + kind: values for name, outcomes in predictions.items() for kind, values in outcomes.items()})
    result = dict(contract="participation.house_pair_oof_sufficient.v1", source_rows=6175,
                  policy_sha256=pin(args.policy), rows=rows, models=list(MODELS), fold_count=policy["folds"],
                  source_code_transport_conditional=True, native_respondents_and_fine_cells_exported=False)
    (args.private / "public-sufficient-candidate.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (args.private / "fitting-receipt.json").write_text(json.dumps(dict(
        successful_component_fits_new=fits, successful_component_fits_reused=reused,
        policy_sha256=pin(args.policy), source_rows=6175, source_weights=list(native.WEIGHTS),
        OOF_model_fold_frame_rows=len(rows), final_candidate_sha256=pin(args.private / "public-sufficient-candidate.json")
    ), indent=2, sort_keys=True) + "\n")
    print(json.dumps(dict(status="new_paired_source_OOF_fits_complete", new_fits=fits, reused_fits=reused, public_coarse_rows=len(rows))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("panel", "policy", "reference", "private"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    policy = json.loads(args.policy.read_bytes())
    if (pin(args.panel) != native.SOURCE_SHA or pin(Path(__file__)) != policy["fitter_sha256"] or
            pin(Path(native.__file__)) != policy["native_classifier_sha256"] or
            pin(Path(__file__).resolve().parents[1] / "tests/test_house_pair_oof.py") != policy["tests_sha256"] or
            pin(args.reference) != policy["reference_sha256"]):
        raise ValueError("Frozen source/code/reference binding differs")
    if (args.private / "fitting-receipt.json").exists():
        raise ValueError("Fits already complete; use existing results, do not repeat")
    if Path(__file__).resolve().parents[1] in args.private.resolve().parents:
        raise ValueError("Private fits must remain outside the repository")
    args.private.mkdir(parents=True, exist_ok=True, mode=0o700)
    (args.private / "heads").mkdir(exist_ok=True, mode=0o700)
    prepared = prepare(args, policy)
    run(args, policy, prepared)


if __name__ == "__main__":
    main()
