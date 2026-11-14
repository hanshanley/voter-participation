"""Apply final-02 metadata errata without changing any fitted numeric value."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def repaired_jurisdictions(original_rows):
    output = []
    for row in original_rows:
        study, state = row["study"], row["jurisdiction"]
        source_presence = state != "DC"
        if study == "historical_ap2022_to_ap2024":
            common = state not in ("DE", "WV", "DC")
            state_inference = (
                "qualified_by_ap2022_codebook_for_common_48_source_transfer"
                if common else
                "national_only_not_state_qualified" if state in ("DE", "WV") else
                "unsupported_not_in_source"
            )
            decision = (
                "included_in_common_48_train_and_score_frame"
                if common else
                "excluded_from_train_and_score_national_only" if state in ("DE", "WV") else
                "unsupported_not_in_source"
            )
            pooled = False
        else:
            common = False
            pooled = source_presence
            state_inference = (
                "not_established_by_held_codebook_evidence"
                if source_presence else "unsupported_not_in_source"
            )
            decision = (
                "observed_in_pooled_source_holdout_only"
                if source_presence else "unsupported_not_in_source"
            )
        output.append({
            "study": study,
            "jurisdiction": state,
            "source_presence": source_presence,
            "observed_in_pooled_source_holdout": pooled,
            "qualified_for_pooled_source_response_analysis": pooled,
            "qualified_for_common_48_transfer_score": common,
            "state_inference_qualification": state_inference,
            "decision": decision,
            "state_score_published": False,
        })
    return output


def repaired_promotion(original):
    candidates = []
    for row in original["candidates"]:
        candidates.append({
            "block": row["block"],
            "checks": copy.deepcopy(row["checks"]),
            "meets_exploratory_arithmetic_gate":
                row["eligible_source_only_scientific_candidate"],
            "scientific_promotion_eligible": False,
        })
    arithmetic = [
        row["block"] for row in candidates if row["meets_exploratory_arithmetic_gate"]
    ]
    return {
        "original_rule_claim_withdrawn": True,
        "rule_frozen_before_native_fits": False,
        "external_preregistration": False,
        "classification": "exploratory_post_hoc_comparison_on_seen_source_outcomes",
        "arithmetic_rule": original["rule"],
        "candidates": candidates,
        "blocks_meeting_exploratory_arithmetic_gate": arithmetic,
        "automatic_default_promotion": False,
        "scientific_promotion": False,
        "generalization_claim": False,
        "uncertainty_analysis": False,
        "new_independent_historical_episode": False,
        "ap_chep_specs_identical": False,
        "ap_chep_spec_note": (
            "AP uses one prior; CHEP uses two priors. Age/education blocks are thematic "
            "comparisons, not identical specifications or a shared identified mechanism."
        ),
        "comparison_is_against_accepted_full_rich_model": False,
        "current_only_race_income_and_sex_rucc_cross_source_eligible": False,
        "changed_state_estimates_generated": False,
        "synthetic_coarse_priors_generated": False,
        "disposition": "exploratory_small_difference_no_promotion_no_generalization_claim",
    }


def repair(original, erratum):
    value = copy.deepcopy(original)
    value["contract"] = "participation.source_predictor_blocks.repaired.v2"
    value["forensic_original_contract"] = original["contract"]
    value["erratum"] = {
        "contract": erratum["contract"],
        "original_protocol_sha256": erratum["originals_preserved"]["protocol_sha256"],
        "original_sdk_sha256": erratum["originals_preserved"]["sdk_sha256"],
        "original_handoff_sha256": erratum["originals_preserved"]["handoff_sha256"],
        "chronology_classification": erratum["chronology_correction"]["replacement_classification"],
    }
    value["protocol_status"] = {
        "sha256": original["protocol_sha256"],
        "preserved_forensic_original": True,
        "declared_frozen_at_valid": False,
        "rule_frozen_before_native_fits": False,
        "classification": "exploratory_not_independently_time_certified",
    }
    for study, blocks in value["results"].items():
        for block, result in blocks.items():
            baseline = block == "training_weighted_marginal"
            result["evaluation_type"] = (
                "training_weighted_marginal_calculation"
                if baseline else "multinomial_logistic_estimator_fit"
            )
            result["logistic_estimator_fit_performed"] = not baseline
    inventories = value["frame_inventory"]
    for key in ("ap2022", "ap2024"):
        inventories[key]["common_48_transfer_score_cases"] = inventories[key].pop(
            "qualified_score_cases"
        )
        inventories[key]["common_48_transfer_score_states"] = inventories[key].pop(
            "qualified_score_states"
        )
        inventories[key]["historical_validation_scope"] = (
            "common_48_state_source_transfer_not_all_state_validation"
        )
    inventories["chep2026"]["pooled_source_holdout_cases"] = inventories["chep2026"].pop(
        "qualified_score_cases"
    )
    inventories["chep2026"]["pooled_source_holdout_states"] = inventories["chep2026"].pop(
        "qualified_score_states"
    )
    inventories["chep2026"]["state_inference_qualification"] = (
        "not_established_by_held_codebook_evidence"
    )
    value["jurisdiction_decisions"] = repaired_jurisdictions(
        original["jurisdiction_decisions"]
    )
    value["promotion_decision"] = repaired_promotion(original["promotion_decision"])
    value["execution_accounting"] = {
        "evaluations": 12,
        "multinomial_logistic_estimator_fits": 10,
        "training_weighted_marginal_calculations": 2,
        "repair_refits": 0,
    }
    value["query_definitions"] = {
        "metric_rows": (
            "Twelve source evaluations: ten multinomial logistic estimator fits and two "
            "training-weighted marginal calculations. Numeric scores are unchanged."
        ),
        "calibration_rows": original["query_definitions"]["calibration_rows"],
        "jurisdiction_rows": (
            "All 50 states plus DC. AP decisions identify the common 48-state transfer "
            "frame. CHEP decisions identify source presence and pooled holdout eligibility "
            "only; state-inference qualification is not claimed."
        ),
        "population_validation": False,
        "respondent_predictions_exported": False,
        "current_2026_returns_consumed": False,
        "state_inference_scores_published": False,
    }
    value["limitations"] = list(original["limitations"]) + [
        "The original frozen_at timestamp and prefit-freeze claim are withdrawn.",
        "The age/education difference is exploratory, small, and lacks uncertainty analysis or a new independent historical episode.",
        "AP and CHEP age/education blocks are thematic rather than identical specifications.",
        "The arithmetic gate compares with prior_only, not the accepted full rich model, and does not justify promotion.",
        "CHEP jurisdiction rows establish pooled source presence only, not state-inference qualification.",
    ]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-facts", type=Path, required=True)
    parser.add_argument("--erratum", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh repaired-facts path")
    original = json.loads(args.original_facts.read_bytes())
    erratum = json.loads(args.erratum.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded(repair(original, erratum)))
    print(json.dumps({"status": "repaired_metadata_only", "refits": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
