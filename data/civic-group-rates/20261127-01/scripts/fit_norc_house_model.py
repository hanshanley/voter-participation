"""Fit locally to supplied NORC files; export synthetic coarse priors, not cases."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import zipfile

CHOICES = "DRONU"
CHEP_SHA = "496a5b57fbc435210bdf78e2c1c3717879c0689c74081bee830d121b548c792f"
AP_SHA = "7d63dada53d1e6f5f3fac54417e189755d54ce312cf7945f16abe4f91c5bf62f"
DEMOGRAPHICS = ("AGE6", "EDUC", "RACETH5", "INCOME", "SEX", "RUCC")


def pin(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def native(value):
    match = re.match(r"\(?(\d+)", value.strip())
    return int(match[1]) if match else 99


def choice(value, reversed_parties=False):
    return ({1: "R", 2: "D"} if reversed_parties else {1: "D", 2: "R"}).get(
        native(value), {3: "O", 4: "N"}.get(native(value), "U"))


def features(row, demographics):
    fields = ("state", "p24", "h22") + demographics
    result = {field: str(row[field]) for field in fields}
    for prior in ("p24", "h22"):
        for field in demographics:
            result[prior+"_"+field] = str(row[prior])+"|"+str(row[field])
    return result


def source_rows(chep, ap):
    import numpy as np
    records, targets, weights = [], [], []
    with zipfile.ZipFile(ap) as archive, io.TextIOWrapper(
            archive.open("AP_VOTECAST_2024_GENERAL.csv"), encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        fields = ("P_STATE", "FINALVOTE_STATE_WEIGHT", "LIKELYVOTER", "PRESVOTE",
            "HOUSEVOTE", "QPVVOTE22", "QVOTE2022", "AGE65", "EDUC", "RACETH5", "INCOME")
        indices = [header.index(field) for field in fields]
        for raw in reader:
            row = dict(zip(fields, (raw[i] for i in indices)))
            weight = float(row["FINALVOTE_STATE_WEIGHT"] or 0)
            if weight <= 0:
                continue
            state = re.match(r"\(([A-Z]{2})\)", row["P_STATE"])
            if not state:
                raise ValueError("Unreviewed AP state coding")
            voter = native(row["LIKELYVOTER"]) == 1
            previous = "N" if native(row["QPVVOTE22"]) in (1, 2, 3) else choice(
                row["QVOTE2022"], reversed_parties=True)
            record = dict(state=state[1], p24=choice(row["PRESVOTE"]) if voter else "N", h22=previous)
            for field in ("AGE6", "EDUC", "RACETH5", "INCOME"):
                value = native(row["AGE65" if field == "AGE6" else field])
                record[field] = "unknown" if value in (77, 88, 98, 99) else str(value)
            records.append(record)
            targets.append(CHOICES.index(choice(row["HOUSEVOTE"]) if voter else "N"))
            weights.append(weight)
    ap_data = records, np.asarray(targets), np.asarray(weights)
    records, targets, weights = [], [], []
    with chep.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        fields = ("P_STATE", "CHEP_WEIGHT", "VOTE24_CHOICE", "VOTE22_CHOICE",
            "LIKELYVOTER", "HOUSEVOTE", *DEMOGRAPHICS)
        indices = [header.index(field) for field in fields]
        for raw in reader:
            row = dict(zip(fields, (raw[i] for i in indices)))
            record = dict(state=row["P_STATE"], p24=choice(row["VOTE24_CHOICE"]),
                h22=choice(row["VOTE22_CHOICE"]))
            for field in DEMOGRAPHICS:
                value = native(row[field])
                record[field] = "unknown" if value in (77, 88, 98, 99) else str(value)
            records.append(record)
            targets.append(CHOICES.index(choice(row["HOUSEVOTE"]) if native(row["LIKELYVOTER"]) == 1 else "N"))
            weights.append(float(row["CHEP_WEIGHT"]))
    if len(records) != 113020 or len({r["state"] for r in records}) != 50:
        raise ValueError("Changed NORC CHEP source coverage")
    return ap_data, (records, np.asarray(targets), np.asarray(weights))


def split(records, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    train, test = [], []
    for state in sorted({r["state"] for r in records}):
        indices = np.asarray([i for i, row in enumerate(records) if row["state"] == state])
        rng.shuffle(indices)
        test.extend(indices[:max(1, len(indices)//5)])
        train.extend(indices[max(1, len(indices)//5):])
    return np.asarray(train), np.asarray(test)


def learner(records, target, weights, demographics, seed):
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    vectorizer = DictVectorizer()
    matrix = vectorizer.fit_transform(features(row, demographics) for row in records)
    train, test = split(records, seed)
    normalized = weights/weights.mean()
    model = LogisticRegression(C=.15, solver="lbfgs", max_iter=1000, tol=1e-6)
    model.fit(matrix[train], target[train], sample_weight=normalized[train])
    probabilities = model.predict_proba(matrix[test])
    if list(model.classes_) != list(range(5)):
        raise ValueError("A native response class cannot disappear")
    loss = log_loss(target[test], probabilities, labels=list(range(5)), sample_weight=weights[test])
    onehot = np.eye(5)[target[test]]
    brier = float(np.average(np.sum((probabilities-onehot)**2, axis=1), weights=weights[test]))
    major = np.isin(target[test], (0, 1))
    major_loss = log_loss(target[test][major], probabilities[major], labels=list(range(5)),
        sample_weight=weights[test][major])
    diagnostics = dict(test_cases=len(test), train_cases=len(train), source_weighted_log_loss=float(loss),
        source_weighted_multiclass_brier=brier, known_major_party_source_log_loss=float(major_loss),
        state_stratified_respondent_holdout=True, outcome_return_calibration_used_in_test=False,
        predicts_survey_responses_not_independent_population_histories=True)
    model.fit(matrix, target, sample_weight=normalized)
    return vectorizer, model, diagnostics


def group_for(row, dimension):
    value = row.get(dimension, "unknown")
    return {
        "AGE6": {"1": "18_29", "2": "18_29", "3": "30_49", "4": "30_49",
            "5": "50_64", "6": "65_plus"},
        "EDUC": {"1": "high_school_or_less", "2": "some_college",
            "3": "college_postgraduate", "4": "college_postgraduate"},
        "SEX": {"1": "male", "2": "female"},
        "RACETH5": {"1": "white", "2": "black", "3": "hispanic",
            "4": "asian_pacific", "5": "other_unknown"},
        "INCOME": {"1": "under_25000", "2": "25000_49999", "3": "50000_74999",
            "4": "75000_99999", "5": "100000_plus"},
        "RUCC": {"1": "urban_county", "2": "suburban_county", "3": "rural_county"},
    }[dimension].get(value, "other_unknown" if dimension == "RACETH5" else "unknown")


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def fit(chep, ap, disclosure):
    import numpy as np
    from threadpoolctl import threadpool_limits
    if pin(chep) != CHEP_SHA or pin(ap) != AP_SHA:
        raise ValueError("Use the exact supplied, previously qualified NORC inputs")
    ap_data, current = source_rows(chep, ap)
    records, labels, weights = current
    with threadpool_limits(limits=1):
        bridge_vectorizer, bridge, bridge_test = learner(*ap_data, DEMOGRAPHICS[:4], 20261112)
        _, _, bridge_baseline = learner(*ap_data, (), 20261112)
        current_vectorizer, current_model, current_test = learner(*current, DEMOGRAPHICS, 20261113)
        _, _, current_baseline = learner(*current, (), 20261113)
        earlier = bridge.predict_proba(bridge_vectorizer.transform(
            features(row, DEMOGRAPHICS[:4]) for row in records))
        later = current_model.predict_proba(current_vectorizer.transform(
            features(row, DEMOGRAPHICS) for row in records))
    allowed = {(r["state_code"], r["dimension"], r["group"]): r
        for r in disclosure["groups"]}
    summaries = {}
    for state in sorted({r["state"] for r in records}):
        selected = np.asarray([i for i, row in enumerate(records) if row["state"] == state])
        w = weights[selected]/weights[selected].sum()
        matrices = earlier[selected, :, None]*later[selected, None, :]*w[:, None, None]
        joint = matrices.sum(axis=0)
        direct = np.zeros((5, 5))
        for k, i in enumerate(selected):
            direct[CHOICES.index(records[i]["h22"])] += w[k]*later[i]
        groups = []
        for dimension in DEMOGRAPHICS:
            displayed = np.zeros((5, 5))
            for (s, d, g), mask in allowed.items():
                if s != state or d != dimension:
                    continue
                public = mask["disposition"] == "selected_broad_source_model"
                item = dict(dimension=d, group=g, label=mask["label"], available=public, prior_joint=None)
                if public:
                    chosen = np.asarray([group_for(records[i], dimension) == g for i in selected])
                    aggregate = matrices[chosen].sum(axis=0)
                    displayed += aggregate
                    item["prior_joint"] = aggregate.tolist()
                groups.append(item)
            remainder = joint-displayed
            if remainder.min() < -1e-10:
                raise ValueError("A demographic partition was counted twice")
            groups.append(dict(dimension=dimension, group="unshown", label="Other / undisclosed source categories",
                available=True, opaque_model_residual_not_a_new_native_group=True,
                prior_joint=np.maximum(remainder, 0).tolist()))
        summaries[state] = dict(state_code=state, prior_joint=joint.tolist(),
            direct_2022_house_prior_joint=direct.tolist(), groups=groups,
            actual_joint_demographic_records_used=True, source_joint_cells_reconstructed_or_exported=False)
    return dict(contract="participation.norc_house_demographic_priors.v1", states=summaries,
        categories=list(CHOICES), source_input_sha256=dict(chep=CHEP_SHA, ap2024=AP_SHA),
        source_cases=dict(chep=len(records), ap2024=len(ap_data[0])),
        validation=dict(house_2024_bridge=bridge_test, house_2024_bridge_without_demographics=bridge_baseline,
            current_2026_response=current_test, current_2026_response_without_demographics=current_baseline),
        assumptions=["AP2024 observed within-study President/House association bridges CHEP recalled President to latent House24",
            "AP QVOTE2022 actual recalled House choice is used; QVOTE2022S forced choice is never consumed",
            "Current demographic categories and current state transport to the baseline bridge; aging/migration not identified",
            "CHEP likely-voter model defines modeled current nonparticipation; it is not observed completed abstention",
            "Latent prior House and current response are conditionally independent given included predictors before affinity sensitivity",
            "Native weights are globally rescaled only for ridge regularization, never fitted to election returns in training",
            "Public inputs are smoothed synthetic coarse predictions, not private observed joint cells"],
        new_eligibility_deaths_migration=None, measured_staying_home=None, design_confidence_intervals=None,
        raw_records_or_private_fine_cells_exported=False, old_synthetic_state_couplings_used=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("chep", "ap2024", "disclosure", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or any((p / ".git").exists() for p in (args.output, *args.output.resolve().parents)):
        raise ValueError("Use a fresh private destination outside Git")
    result = fit(args.chep, args.ap2024, json.loads(args.disclosure.read_bytes()))
    args.output.mkdir(mode=0o700, parents=True)
    target = args.output / "public-model-priors.json"
    target.write_bytes(encoded(result))
    os.chmod(target, 0o600)
    print(json.dumps(dict(source_cases=result["source_cases"], validation=result["validation"],
        states=len(result["states"]), private_respondents_exported=False)))
