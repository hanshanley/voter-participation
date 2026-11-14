"""Standard-library rendering and validation of final-02 aggregate facts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write_new(path, body):
    if path.exists():
        raise ValueError("Use a fresh replay output")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def write_csv(path, rows, fields):
    if path.exists():
        raise ValueError("Use a fresh replay output")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def flatten(facts):
    metrics, calibration = [], []
    for study, blocks in facts["results"].items():
        for block, result in blocks.items():
            metrics.append({
                "study": study,
                "block": block,
                "evaluation_type": result["evaluation_type"],
                "logistic_estimator_fit_performed":
                    result["logistic_estimator_fit_performed"],
                "train_cases": result["train_cases"],
                "test_cases": result["test_cases"],
                "source_weighted_log_loss": result["source_weighted_log_loss"],
                "source_weighted_multiclass_brier":
                    result["source_weighted_multiclass_brier"],
                "known_major_party_source_log_loss":
                    result["known_major_party_source_log_loss"],
                "vocabulary_size": result["vocabulary_size"],
                "train_weight_mean_before_normalization":
                    result["train_weight_mean_before_normalization"],
                "calibration_disposition": result["calibration_disposition"],
            })
            if result["class_calibration"] is not None:
                for item in result["class_calibration"]:
                    calibration.append({"study": study, "block": block, **item})
    return metrics, calibration


def render(facts, output):
    if facts["contract"] != "participation.source_predictor_blocks.repaired.v2":
        raise ValueError("Unknown repaired facts contract")
    if facts["protocol_status"]["rule_frozen_before_native_fits"]:
        raise ValueError("Withdrawn freeze claim survived")
    if facts["promotion_decision"]["scientific_promotion"]:
        raise ValueError("Unexpected promotion")
    if len(facts["jurisdiction_decisions"]) != 102:
        raise ValueError("Incomplete jurisdiction decisions")
    chep = [
        row for row in facts["jurisdiction_decisions"]
        if row["study"] == "current_chep2026_holdout" and row["source_presence"]
    ]
    if len(chep) != 50 or any(
        row["state_inference_qualification"]
        != "not_established_by_held_codebook_evidence" for row in chep
    ):
        raise ValueError("CHEP state scope is overstated")
    metrics, calibration = flatten(facts)
    if len(metrics) != 12:
        raise ValueError("Incomplete evaluations")
    if sum(row["logistic_estimator_fit_performed"] for row in metrics) != 10:
        raise ValueError("Incorrect estimator-fit accounting")
    if any(row["raw_outcome_cases"] < 30 for row in calibration):
        raise ValueError("Disclosure threshold violation")
    output.mkdir(parents=True, exist_ok=False)
    write_csv(
        output / "model-metrics.csv",
        metrics,
        [
            "study", "block", "evaluation_type", "logistic_estimator_fit_performed",
            "train_cases", "test_cases", "source_weighted_log_loss",
            "source_weighted_multiclass_brier", "known_major_party_source_log_loss",
            "vocabulary_size", "train_weight_mean_before_normalization",
            "calibration_disposition",
        ],
    )
    write_csv(
        output / "class-calibration.csv",
        calibration,
        [
            "study", "block", "category", "raw_outcome_cases",
            "weighted_observed_share", "weighted_mean_predicted_probability",
        ],
    )
    write_csv(
        output / "jurisdiction-decisions.csv",
        facts["jurisdiction_decisions"],
        [
            "study", "jurisdiction", "source_presence",
            "observed_in_pooled_source_holdout",
            "qualified_for_pooled_source_response_analysis",
            "qualified_for_common_48_transfer_score",
            "state_inference_qualification", "decision", "state_score_published",
        ],
    )
    write_new(output / "frame-inventory.json", encoded(facts["frame_inventory"]))
    write_new(output / "promotion-decision.json", encoded(facts["promotion_decision"]))
    write_new(output / "query-definitions.json", encoded(facts["query_definitions"]))
    summary = {
        "contract": facts["contract"],
        "evaluations": len(metrics),
        "multinomial_logistic_estimator_fits": 10,
        "training_weighted_marginal_calculations": 2,
        "calibration_rows": len(calibration),
        "jurisdiction_decisions": len(facts["jurisdiction_decisions"]),
        "source_fits_reproduced": False,
        "aggregate_facts_replayed": True,
        "facts_sha256": hashlib.sha256(encoded(facts)).hexdigest(),
        "classification": facts["promotion_decision"]["classification"],
        "scientific_promotion": False,
    }
    write_new(output / "replay-summary.json", encoded(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = render(json.loads(args.facts.read_bytes()), args.output)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
