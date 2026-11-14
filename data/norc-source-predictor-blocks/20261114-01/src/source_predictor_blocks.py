"""Shared source-only predictor-block helpers.

The fitted target is the five-class survey response D/R/Other/modeled-N/unknown.
No current election returns, respondent identifiers, or final-return calibration
targets are accepted as predictors.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter


CHOICES = "DRONU"
FORBIDDEN_PREDICTORS = {
    "HOUSEVOTE",
    "LIKELYVOTER",
    "LVB",
    "SU_ID",
    "CASEID",
    "respondent_ID",
    "current_return_party_counts",
    "QVOTE2020S",
    "QVOTE2022S",
}

HISTORICAL_BLOCKS = {
    "training_weighted_marginal": (),
    "prior_only": ("prior_2020_president",),
    "prior_state": ("prior_2020_president", "state"),
    "prior_age_education": ("prior_2020_president", "age", "education"),
    "prior_state_age_education": ("prior_2020_president", "state", "age", "education"),
}

CURRENT_BLOCKS = {
    "training_weighted_marginal": (),
    "prior_only": ("p24", "h22"),
    "prior_state": ("p24", "h22", "state"),
    "prior_age_education": ("p24", "h22", "AGE6", "EDUC"),
    "prior_state_age_education": ("p24", "h22", "state", "AGE6", "EDUC"),
    "prior_state_age_education_race_income": (
        "p24", "h22", "state", "AGE6", "EDUC", "RACETH5", "INCOME"
    ),
    "prior_state_age_education_race_income_sex_rucc": (
        "p24", "h22", "state", "AGE6", "EDUC", "RACETH5", "INCOME", "SEX", "RUCC"
    ),
}


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def native(value) -> int:
    match = re.match(r"\(?(\d+)", str(value).strip())
    return int(match.group(1)) if match else 999


def choice(value, reversed_parties=False) -> str:
    code = native(value)
    major = {1: "R", 2: "D"} if reversed_parties else {1: "D", 2: "R"}
    return major.get(code, {3: "O", 4: "N"}.get(code, "U"))


def native_category(value, valid_codes) -> str:
    text = str(value).strip()
    if not text:
        return "missing"
    code = native(text)
    if code in valid_codes:
        return str(code)
    if code == 77:
        return "dont_know_77"
    if code == 88:
        return "disclosure_removed_88"
    if code == 98:
        return "web_skipped_98"
    if code == 99:
        return "unknown_refused_99"
    return "other_native_" + str(code)


def route_weight(value):
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return "invalid", None
    if not math.isfinite(weight):
        return "invalid", None
    if weight < 0:
        return "negative", weight
    if weight == 0:
        return "zero", weight
    return "positive", weight


def modeled_target(likely_voter, house_vote) -> int:
    label = choice(house_vote) if native(likely_voter) == 1 else "N"
    return CHOICES.index(label)


def historical_prior(row) -> str:
    if native(row["QPVVOTE20"]) in (1, 2, 3):
        return "N"
    return choice(row["QVOTE2020"], reversed_parties=True)


def ap_record(row):
    state_match = re.match(r"\(([A-Z]{2})\)", str(row["P_STATE"]).strip())
    if not state_match:
        raise ValueError("Unexpected native AP state coding")
    return {
        "state": state_match.group(1),
        "prior_2020_president": historical_prior(row),
        "age": native_category(row["AGE65"], range(1, 7)),
        "education": native_category(row["EDUC"], range(1, 5)),
    }


def chep_record(row):
    state = str(row["P_STATE"]).strip()
    if not re.fullmatch(r"[A-Z]{2}", state):
        raise ValueError("Unexpected native CHEP state coding")
    return {
        "state": state,
        "p24": choice(row["VOTE24_CHOICE"]),
        "h22": choice(row["VOTE22_CHOICE"]),
        "AGE6": native_category(row["AGE6"], range(1, 7)),
        "EDUC": native_category(row["EDUC"], range(1, 5)),
        "RACETH5": native_category(row["RACETH5"], range(1, 6)),
        "INCOME": native_category(row["INCOME"], range(1, 6)),
        "SEX": native_category(row["SEX"], range(1, 3)),
        "RUCC": native_category(row["RUCC"], range(1, 4)),
    }


def predictor_features(row, block, study):
    blocks = HISTORICAL_BLOCKS if study == "historical_ap_transfer" else CURRENT_BLOCKS
    if block not in blocks:
        raise ValueError("Unknown frozen predictor block")
    fields = blocks[block]
    if FORBIDDEN_PREDICTORS & set(fields):
        raise ValueError("Outcome or identifier entered the predictor contract")
    if not fields:
        return {}
    result = {field: str(row[field]) for field in fields}
    if block in ("prior_age_education", "prior_state_age_education"):
        if study == "historical_ap_transfer":
            priors, demographics = ("prior_2020_president",), ("age", "education")
        else:
            priors, demographics = ("p24", "h22"), ("AGE6", "EDUC")
        for prior in priors:
            for field in demographics:
                result[prior + "_x_" + field] = str(row[prior]) + "|" + str(row[field])
    elif study == "current_chep_holdout" and block.startswith("prior_state_age_education"):
        for prior in ("p24", "h22"):
            for field in ("AGE6", "EDUC"):
                result[prior + "_x_" + field] = str(row[prior]) + "|" + str(row[field])
    if FORBIDDEN_PREDICTORS & set(result):
        raise ValueError("Outcome leakage")
    return result


def state_stratified_split(records, seed):
    import numpy as np

    rng = np.random.default_rng(seed)
    train, test = [], []
    states = sorted({row["state"] for row in records})
    for state in states:
        indices = np.asarray([i for i, row in enumerate(records) if row["state"] == state], dtype=np.int64)
        if len(indices) < 2:
            raise ValueError("State cannot support a holdout")
        rng.shuffle(indices)
        size = max(1, len(indices) // 5)
        test.extend(indices[:size])
        train.extend(indices[size:])
    return np.asarray(train, dtype=np.int64), np.asarray(test, dtype=np.int64)


def normalized_training_weights(weights, train_indices):
    import numpy as np

    selected = np.asarray(weights, dtype=float)[train_indices]
    if not np.isfinite(selected).all() or np.any(selected <= 0):
        raise ValueError("Training weights must be finite and positive")
    mean = float(selected.mean())
    result = selected / mean
    return result, mean


def weighted_marginal(labels, weights):
    import numpy as np

    labels = np.asarray(labels, dtype=int)
    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("Marginal weights must be finite and positive")
    totals = np.bincount(labels, weights=weights, minlength=len(CHOICES)).astype(float)
    if len(totals) != len(CHOICES) or np.any(totals <= 0):
        raise ValueError("Every response class must have positive training support")
    return totals / totals.sum()


def probabilities_for_marginal(marginal, rows):
    import numpy as np

    values = np.asarray(marginal, dtype=float)
    return np.repeat(values[None, :], rows, axis=0)


def weighted_metrics(labels, probabilities, weights):
    import numpy as np
    from sklearn.metrics import log_loss

    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if probabilities.shape != (len(labels), len(CHOICES)):
        raise ValueError("Changed probability shape")
    if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
        raise ValueError("Nonfinite or negative probabilities")
    if not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-10):
        raise ValueError("Probabilities do not sum to one")
    onehot = np.eye(len(CHOICES))[labels]
    known_major = np.isin(labels, (0, 1))
    return {
        "source_weighted_log_loss": float(log_loss(
            labels, probabilities, labels=list(range(len(CHOICES))), sample_weight=weights
        )),
        "source_weighted_multiclass_brier": float(np.average(
            np.sum((probabilities - onehot) ** 2, axis=1), weights=weights
        )),
        "known_major_party_source_log_loss": float(log_loss(
            labels[known_major],
            probabilities[known_major],
            labels=list(range(len(CHOICES))),
            sample_weight=weights[known_major],
        )),
    }


def calibration_rows(labels, probabilities, weights, minimum=30):
    import numpy as np

    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    weights = np.asarray(weights, dtype=float)
    counts = np.bincount(labels, minlength=len(CHOICES))
    if np.any(counts < minimum):
        return None
    total_weight = float(weights.sum())
    rows = []
    for index, category in enumerate(CHOICES):
        rows.append({
            "category": category,
            "raw_outcome_cases": int(counts[index]),
            "weighted_observed_share": float(weights[labels == index].sum() / total_weight),
            "weighted_mean_predicted_probability": float(np.average(probabilities[:, index], weights=weights)),
        })
    return rows


def outcome_inventory(labels):
    counts = Counter(CHOICES[int(value)] for value in labels)
    return {category: int(counts.get(category, 0)) for category in CHOICES}


def split_digest(indices) -> str:
    import numpy as np

    return sha256_bytes(np.asarray(indices, dtype="<i8").tobytes())
