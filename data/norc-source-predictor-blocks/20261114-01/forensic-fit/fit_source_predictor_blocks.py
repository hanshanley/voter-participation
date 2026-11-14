"""Fit the frozen AP-transfer and CHEP holdout predictor-block ablation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import warnings
import zipfile

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

from source_predictor_blocks import (
    CHOICES,
    CURRENT_BLOCKS,
    HISTORICAL_BLOCKS,
    ap_record,
    calibration_rows,
    chep_record,
    encoded,
    modeled_target,
    normalized_training_weights,
    outcome_inventory,
    predictor_features,
    probabilities_for_marginal,
    route_weight,
    sha256_bytes,
    split_digest,
    state_stratified_split,
    weighted_marginal,
    weighted_metrics,
)


AP_FIELDS = (
    "P_STATE",
    "POLLCLOSE_STATE_WEIGHT",
    "LIKELYVOTER",
    "HOUSEVOTE",
    "QPVVOTE20",
    "QVOTE2020",
    "AGE65",
    "EDUC",
)
CHEP_FIELDS = (
    "P_STATE",
    "CHEP_WEIGHT",
    "VOTE24_CHOICE",
    "VOTE22_CHOICE",
    "LIKELYVOTER",
    "HOUSEVOTE",
    "AGE6",
    "EDUC",
    "RACETH5",
    "INCOME",
    "SEX",
    "RUCC",
)
STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
)


def file_sha256(path):
    with path.open("rb") as stream:
        if hasattr(hashlib, "file_digest"):
            return hashlib.file_digest(stream, "sha256").hexdigest()
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def write_new(path, body, mode=0o644):
    if path.exists():
        raise ValueError("Refusing to overwrite completed output: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    os.chmod(path, mode)


def read_member_rows(path, member, fields):
    with zipfile.ZipFile(path) as archive, io.TextIOWrapper(
        archive.open(member), encoding="utf-8-sig", newline=""
    ) as stream:
        reader = csv.reader(stream)
        header = next(reader)
        indices = [header.index(field) for field in fields]
        for raw in reader:
            yield dict(zip(fields, (raw[index] for index in indices)))


def load_ap(path, member, excluded_states):
    records, labels, weights = [], [], []
    inventory = {
        "raw_retained_cases": 0,
        "positive_pollclose_state_weight_cases": 0,
        "zero_pollclose_state_weight_cases": 0,
        "negative_pollclose_state_weight_cases": 0,
        "invalid_pollclose_state_weight_cases": 0,
        "positive_weight_cases_excluded_by_state_qualification": 0,
        "qualified_score_cases": 0,
        "raw_states_present": [],
        "qualified_score_states": [],
        "weight": "POLLCLOSE_STATE_WEIGHT",
        "final_vote_weights_consumed": False,
    }
    raw_states, score_states = set(), set()
    for row in read_member_rows(path, member, AP_FIELDS):
        inventory["raw_retained_cases"] += 1
        record = ap_record(row)
        raw_states.add(record["state"])
        status, weight = route_weight(row["POLLCLOSE_STATE_WEIGHT"])
        inventory[status + "_pollclose_state_weight_cases"] += 1
        if status != "positive":
            continue
        if record["state"] in excluded_states:
            inventory["positive_weight_cases_excluded_by_state_qualification"] += 1
            continue
        records.append(record)
        labels.append(modeled_target(row["LIKELYVOTER"], row["HOUSEVOTE"]))
        weights.append(weight)
        score_states.add(record["state"])
    inventory["qualified_score_cases"] = len(records)
    inventory["raw_states_present"] = sorted(raw_states)
    inventory["qualified_score_states"] = sorted(score_states)
    return records, np.asarray(labels, dtype=np.int64), np.asarray(weights, dtype=float), inventory


def load_chep(path):
    records, labels, weights = [], [], []
    inventory = {
        "raw_retained_cases": 0,
        "positive_weight_cases": 0,
        "zero_weight_cases": 0,
        "negative_weight_cases": 0,
        "invalid_weight_cases": 0,
        "qualified_score_cases": 0,
        "raw_states_present": [],
        "qualified_score_states": [],
        "weight": "CHEP_WEIGHT",
        "final_return_weight_dependency": "Source documentation does not establish independence from final returns",
    }
    states = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = set(CHEP_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError("Missing CHEP fields: " + ",".join(sorted(missing)))
        for row in reader:
            inventory["raw_retained_cases"] += 1
            status, weight = route_weight(row["CHEP_WEIGHT"])
            inventory[status + "_weight_cases"] += 1
            if status != "positive":
                continue
            record = chep_record(row)
            states.add(record["state"])
            records.append(record)
            labels.append(modeled_target(row["LIKELYVOTER"], row["HOUSEVOTE"]))
            weights.append(weight)
    inventory["qualified_score_cases"] = len(records)
    inventory["raw_states_present"] = sorted(states)
    inventory["qualified_score_states"] = sorted(states)
    return records, np.asarray(labels, dtype=np.int64), np.asarray(weights, dtype=float), inventory


def model_cache_key(protocol_sha, code_hashes, source_hashes, study, block, split):
    return sha256_bytes(encoded({
        "protocol_sha256": protocol_sha,
        "code_sha256": code_hashes,
        "source_sha256": source_hashes,
        "study": study,
        "block": block,
        "split": split,
    }))


def fit_and_score(train_records, train_labels, train_weights, test_records, test_labels,
                  test_weights, block, study, parameters):
    if block == "training_weighted_marginal":
        marginal = weighted_marginal(train_labels, train_weights)
        probabilities = probabilities_for_marginal(marginal, len(test_labels))
        vocabulary = []
        train_weight_mean = float(np.mean(train_weights))
    else:
        train_features = [predictor_features(row, block, study) for row in train_records]
        test_features = [predictor_features(row, block, study) for row in test_records]
        vectorizer = DictVectorizer()
        matrix = vectorizer.fit_transform(train_features)
        test_matrix = vectorizer.transform(test_features)
        normalized, train_weight_mean = normalized_training_weights(
            train_weights, np.arange(len(train_weights), dtype=np.int64)
        )
        model = LogisticRegression(
            C=parameters["C"],
            solver=parameters["solver"],
            max_iter=parameters["max_iter"],
            tol=parameters["tol"],
            random_state=parameters["random_state"],
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(matrix, train_labels, sample_weight=normalized)
        if list(model.classes_) != list(range(len(CHOICES))):
            raise ValueError("A source-response class disappeared")
        probabilities = model.predict_proba(test_matrix)
        vocabulary = vectorizer.get_feature_names_out().tolist()
    metrics = weighted_metrics(test_labels, probabilities, test_weights)
    calibration = calibration_rows(test_labels, probabilities, test_weights)
    return {
        **metrics,
        "train_cases": len(train_labels),
        "test_cases": len(test_labels),
        "train_weight_mean_before_normalization": train_weight_mean,
        "training_weight_normalization": "divide positive training weights by positive training mean only",
        "vocabulary_fit_rows": "training_only",
        "vocabulary_size": len(vocabulary),
        "vocabulary_sha256": sha256_bytes(encoded(vocabulary)),
        "test_outcome_cases": outcome_inventory(test_labels),
        "test_weighted_class_shares": {
            category: float(test_weights[test_labels == index].sum() / test_weights.sum())
            for index, category in enumerate(CHOICES)
        },
        "test_weighted_mean_predictions": {
            category: float(np.average(probabilities[:, index], weights=test_weights))
            for index, category in enumerate(CHOICES)
        },
        "class_calibration": calibration,
        "calibration_disposition": (
            "published_complete_five_class_table_minimum_30_each"
            if calibration is not None else "held_whole_one_or_more_classes_below_30"
        ),
        "private_predictions_persisted": False,
        "trained_estimator_persisted": False,
    }


def cached_fit(cache_dir, cache_key, fit_function):
    target = cache_dir / (cache_key + ".json")
    if target.exists():
        value = json.loads(target.read_bytes())
        if value["cache_key"] != cache_key:
            raise ValueError("Changed cache identity")
        return value, True
    result = fit_function()
    result["cache_key"] = cache_key
    write_new(target, encoded(result), mode=0o600)
    return result, False


def jurisdiction_decisions():
    rows = []
    for state in STATES + ("DC",):
        if state == "DC":
            historical = ("unsupported_not_in_ap_source", False)
            current = ("unsupported_not_in_chep_source", False)
        elif state in ("DE", "WV"):
            historical = ("national_only_not_state_qualified", False)
            current = ("qualified_source_holdout_state_present", True)
        else:
            historical = ("qualified_common_48_state_transfer_frame", True)
            current = ("qualified_source_holdout_state_present", True)
        for study, decision in (
            ("historical_ap2022_to_ap2024", historical),
            ("current_chep2026_holdout", current),
        ):
            rows.append({
                "study": study,
                "jurisdiction": state,
                "qualified": decision[1],
                "decision": decision[0],
                "state_score_published": False,
            })
    return rows


def promotion_decision(results):
    historical = results["historical_ap2022_to_ap2024"]
    current = results["current_chep2026_holdout"]
    candidates = []
    for block in ("prior_state", "prior_age_education", "prior_state_age_education"):
        checks = {}
        passed = True
        for study, values in (("historical", historical), ("current", current)):
            checks[study] = {
                "log_loss_improves_vs_prior_only":
                    values[block]["source_weighted_log_loss"]
                    < values["prior_only"]["source_weighted_log_loss"],
                "brier_improves_vs_prior_only":
                    values[block]["source_weighted_multiclass_brier"]
                    < values["prior_only"]["source_weighted_multiclass_brier"],
            }
            passed = passed and all(checks[study].values())
        candidates.append({
            "block": block,
            "checks": checks,
            "eligible_source_only_scientific_candidate": passed,
        })
    eligible = [row["block"] for row in candidates if row["eligible_source_only_scientific_candidate"]]
    return {
        "rule_frozen_before_native_fits": True,
        "rule": (
            "A common AP/CHEP block is a scientific follow-up candidate only if both "
            "weighted multiclass log loss and Brier improve strictly versus prior_only "
            "on both the AP2022-to-AP2024 transfer and the CHEP2026 respondent holdout."
        ),
        "candidates": candidates,
        "eligible_blocks": eligible,
        "current_only_race_income_and_sex_rucc_blocks_eligible_for_cross_source_promotion": False,
        "automatic_default_promotion": False,
        "changed_state_estimates_generated": False,
        "synthetic_coarse_priors_generated": False,
        "disposition": (
            "source_only_candidate_exists_but_requires_independent_review_and_no_default_change"
            if eligible else "negative_source_model_finding_no_common_richer_block_passed"
        ),
    }


def write_csv(path, rows, fields):
    if path.exists():
        raise ValueError("Refusing overwrite: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def flatten_metrics(results):
    rows, calibration = [], []
    for study, blocks in results.items():
        for block, result in blocks.items():
            rows.append({
                "study": study,
                "block": block,
                "train_cases": result["train_cases"],
                "test_cases": result["test_cases"],
                "source_weighted_log_loss": result["source_weighted_log_loss"],
                "source_weighted_multiclass_brier": result["source_weighted_multiclass_brier"],
                "known_major_party_source_log_loss": result["known_major_party_source_log_loss"],
                "vocabulary_size": result["vocabulary_size"],
                "train_weight_mean_before_normalization": result[
                    "train_weight_mean_before_normalization"
                ],
                "calibration_disposition": result["calibration_disposition"],
            })
            if result["class_calibration"] is not None:
                for item in result["class_calibration"]:
                    calibration.append({"study": study, "block": block, **item})
    return rows, calibration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ap2022", type=Path, required=True)
    parser.add_argument("--ap2024", type=Path, required=True)
    parser.add_argument("--chep2026", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(args.protocol.read_bytes())
    protocol_sha = file_sha256(args.protocol)
    script_dir = Path(__file__).resolve().parent
    code_hashes = {
        "source_predictor_blocks.py": file_sha256(script_dir / "source_predictor_blocks.py"),
        "fit_source_predictor_blocks.py": file_sha256(Path(__file__).resolve()),
    }
    if code_hashes != protocol["code_sha256"]:
        raise ValueError("Code changed after protocol freeze")
    source_paths = {
        "ap2022": args.ap2022,
        "ap2024": args.ap2024,
        "chep2026": args.chep2026,
    }
    source_hashes = {name: file_sha256(path) for name, path in source_paths.items()}
    if source_hashes != protocol["source_input_sha256"]:
        raise ValueError("Changed native source pin")

    ap2022 = load_ap(args.ap2022, protocol["source_members"]["ap2022"], {"DE", "WV"})
    ap2024 = load_ap(args.ap2024, protocol["source_members"]["ap2024"], {"DE", "WV"})
    chep = load_chep(args.chep2026)
    if set(ap2022[3]["qualified_score_states"]) != set(STATES) - {"DE", "WV"}:
        raise ValueError("Changed AP2022 qualification frame")
    if ap2022[3]["qualified_score_states"] != ap2024[3]["qualified_score_states"]:
        raise ValueError("Historical train/test states differ")
    if set(chep[3]["qualified_score_states"]) != set(STATES):
        raise ValueError("Changed CHEP state frame")

    cache_dir = root / "private" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(root / "private", 0o700)
    os.chmod(cache_dir, 0o700)
    parameters = protocol["learner"]
    results = {
        "historical_ap2022_to_ap2024": {},
        "current_chep2026_holdout": {},
    }
    cache_events = []
    with threadpool_limits(limits=1):
        for block in protocol["blocks"]["historical_ap_transfer"]:
            key = model_cache_key(
                protocol_sha, code_hashes, source_hashes,
                "historical_ap2022_to_ap2024", block, {"seed": None, "states": 48},
            )
            result, reused = cached_fit(
                cache_dir,
                key,
                lambda block=block: fit_and_score(
                    ap2022[0], ap2022[1], ap2022[2],
                    ap2024[0], ap2024[1], ap2024[2],
                    block, "historical_ap_transfer", parameters,
                ),
            )
            results["historical_ap2022_to_ap2024"][block] = result
            cache_events.append({"study": "historical_ap2022_to_ap2024", "block": block, "reused": reused})

        train, test = state_stratified_split(chep[0], protocol["current_holdout_seed"])
        split = {
            "seed": protocol["current_holdout_seed"],
            "train_indices_sha256": split_digest(train),
            "test_indices_sha256": split_digest(test),
        }
        train_records = [chep[0][index] for index in train]
        test_records = [chep[0][index] for index in test]
        for block in protocol["blocks"]["current_chep_holdout"]:
            key = model_cache_key(
                protocol_sha, code_hashes, source_hashes,
                "current_chep2026_holdout", block, split,
            )
            result, reused = cached_fit(
                cache_dir,
                key,
                lambda block=block: fit_and_score(
                    train_records, chep[1][train], chep[2][train],
                    test_records, chep[1][test], chep[2][test],
                    block, "current_chep_holdout", parameters,
                ),
            )
            result.update(split)
            results["current_chep2026_holdout"][block] = result
            cache_events.append({"study": "current_chep2026_holdout", "block": block, "reused": reused})

    promotion = promotion_decision(results)
    decisions = jurisdiction_decisions()
    inventories = {
        "ap2022": {**ap2022[3], "outcome_cases_qualified_score_frame": outcome_inventory(ap2022[1])},
        "ap2024": {**ap2024[3], "outcome_cases_qualified_score_frame": outcome_inventory(ap2024[1])},
        "chep2026": {**chep[3], "outcome_cases_qualified_score_frame": outcome_inventory(chep[1])},
    }
    query_definitions = {
        "metric_rows": (
            "One row per frozen study/block on its common score frame; weighted multiclass "
            "log loss and five-class Brier use native source weights."
        ),
        "calibration_rows": (
            "For each complete model table, one row per D/R/O/N/U category with raw outcome "
            "support, weighted observed share and weighted mean prediction. Entire table held "
            "if any class has fewer than 30 raw outcomes."
        ),
        "jurisdiction_rows": (
            "All 50 states plus DC, separately for AP transfer and CHEP holdout. No state score "
            "or complement is published."
        ),
        "population_validation": False,
        "respondent_predictions_exported": False,
        "current_2026_returns_consumed": False,
    }
    facts = {
        "contract": "participation.source_predictor_blocks.v1",
        "protocol_sha256": protocol_sha,
        "source_input_sha256": source_hashes,
        "code_sha256": code_hashes,
        "results": results,
        "frame_inventory": inventories,
        "jurisdiction_decisions": decisions,
        "promotion_decision": promotion,
        "query_definitions": query_definitions,
        "limitations": [
            "CHEP LIKELYVOTER nonvote is modeled, not observed completed abstention.",
            "AP historical transfer is cross-sectional source transfer, not a matched panel.",
            "AP poll-close weights are used for historical scoring; final-vote weights are not consumed.",
            "AP2024 bridge weights used by older accepted work can depend on final returns; this ablation does not claim independent population validation.",
            "CHEP source weights may depend on final returns; source holdout supports conditional testing only.",
            "No product of marginal tables is treated as an observed transition.",
            "Race and sex are not harmonized across AP studies.",
            "No respondent vectors, estimators, source rows, state score tables, or private fine cells are exported.",
        ],
    }
    facts_dir = root / "facts"
    write_new(facts_dir / "coarse-facts.json", encoded(facts))
    metric_rows, calibration = flatten_metrics(results)
    write_csv(
        facts_dir / "model-metrics.csv",
        metric_rows,
        [
            "study", "block", "train_cases", "test_cases", "source_weighted_log_loss",
            "source_weighted_multiclass_brier", "known_major_party_source_log_loss",
            "vocabulary_size", "train_weight_mean_before_normalization",
            "calibration_disposition",
        ],
    )
    write_csv(
        facts_dir / "class-calibration.csv",
        calibration,
        [
            "study", "block", "category", "raw_outcome_cases",
            "weighted_observed_share", "weighted_mean_predicted_probability",
        ],
    )
    write_csv(
        facts_dir / "jurisdiction-decisions.csv",
        decisions,
        ["study", "jurisdiction", "qualified", "decision", "state_score_published"],
    )
    write_new(facts_dir / "frame-inventory.json", encoded(inventories))
    write_new(facts_dir / "promotion-decision.json", encoded(promotion))
    write_new(facts_dir / "query-definitions.json", encoded(query_definitions))
    receipt = {
        "status": "complete_bounded_source_only_predictor_block_ablation",
        "protocol_sha256": protocol_sha,
        "source_input_sha256": source_hashes,
        "code_sha256": code_hashes,
        "models_completed": len(metric_rows),
        "cache_events": cache_events,
        "private_predictions_persisted": False,
        "trained_estimators_persisted": False,
        "current_return_files_read": False,
        "changed_state_estimates_generated": False,
        "public_fact_sha256": file_sha256(facts_dir / "coarse-facts.json"),
    }
    write_new(root / "private" / "run-receipt.json", encoded(receipt), mode=0o600)
    print(json.dumps({
        "models_completed": len(metric_rows),
        "historical_test_cases": len(ap2024[1]),
        "current_test_cases": len(test),
        "promotion_disposition": promotion["disposition"],
        "cache_reused": sum(item["reused"] for item in cache_events),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
