"""Untouched AP2024 source-response test of an AP2022 model, not joint-history truth."""

import argparse
import csv
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from threadpoolctl import threadpool_limits

from scripts.fit_norc_house_model import native, choice


def load(path, member):
    features, labels, weights = [], [], []
    fields = ("P_STATE", "POLLCLOSE_STATE_WEIGHT", "LIKELYVOTER", "HOUSEVOTE",
        "QPVVOTE20", "QVOTE2020", "AGE65", "EDUC")
    with zipfile.ZipFile(path) as archive, io.TextIOWrapper(archive.open(member),
            encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        indices = [header.index(field) for field in fields]
        for raw in reader:
            row = dict(zip(fields, (raw[i] for i in indices)))
            weight = float(row["POLLCLOSE_STATE_WEIGHT"] or 0)
            if weight <= 0:
                continue
            state = re.match(r"\(([A-Z]{2})\)", row["P_STATE"])
            if not state:
                raise ValueError("Unexpected native state")
            prior = "N" if native(row["QPVVOTE20"]) in (1, 2, 3) else choice(
                row["QVOTE2020"], reversed_parties=True)
            age, education = native(row["AGE65"]), native(row["EDUC"])
            source = dict(state=state[1], prior_2020_president=prior,
                age=str(age) if age in range(1, 7) else "unknown",
                education=str(education) if education in range(1, 5) else "unknown")
            features.append(source)
            labels.append("DRONU".index(choice(row["HOUSEVOTE"]) if native(row["LIKELYVOTER"]) == 1 else "N"))
            weights.append(weight)
    return features, np.asarray(labels), np.asarray(weights)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("ap2022", "ap2024", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    before = load(args.ap2022, "AP_VOTECAST_2022_midterm.csv")
    after = load(args.ap2024, "AP_VOTECAST_2024_GENERAL.csv")
    result = {}
    with threadpool_limits(limits=1):
        for demographic in (False, True):
            def rows(source):
                for row in source:
                    value = {k: v for k, v in row.items() if demographic or k not in ("age", "education")}
                    if demographic:
                        for k in ("age", "education"):
                            value["prior_"+k] = row["prior_2020_president"]+"|"+row[k]
                    yield value
            vectorizer = DictVectorizer()
            x = vectorizer.fit_transform(rows(before[0]))
            test = vectorizer.transform(rows(after[0]))
            model = LogisticRegression(C=.15, max_iter=1000, tol=1e-6)
            model.fit(x, before[1], sample_weight=before[2]/before[2].mean())
            p = model.predict_proba(test)
            result["with_demographics" if demographic else "without_demographics"] = dict(
                source_weighted_log_loss=float(log_loss(after[1], p, labels=list(range(5)), sample_weight=after[2])),
                source_weighted_brier=float(np.average(np.sum((p-np.eye(5)[after[1]])**2, axis=1), weights=after[2])))
    result.update(training_year=2022, untouched_test_year=2024, training_cases=len(before[1]),
        test_cases=len(after[1]), weights="Native poll-close state weights; final-vote weights not used",
        target="AP source modeled participation/current House-response class, not validated individual histories",
        held_target_election_results_used_in_training=False, matched_panel=False,
        race_and_gender_harmonization_attempted=False,
        changing_election_type_and_residence_and_age_composition_remain=True)
    if args.output.exists():
        raise ValueError("Use a fresh historical receipt")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps(result))
