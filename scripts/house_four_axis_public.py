"""Replay broad four-axis score/forecast sums and source-predictive draws."""

import argparse
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
import json
from pathlib import Path
import random

from house_four_axis import COHORTS, MODELS, OUTCOMES
from house_pair_public import FRAMES, compositions, csv_bytes, json_bytes, number, rounded

LEVELS = ("history", "demographic")
METRICS = {"logloss": "nll_sum", "Brier": "brier_sum"}


def replay(data):
    if (data.get("contract") != "participation.house_four_axis_sufficient.v1"
            or data.get("source_rows") != 6175 or data.get("source_code_transport_conditional") is not True
            or data.get("population_validation") is not False
            or data.get("current2026_model_or_nonparticipation_parameter_changed") is not False
            or data.get("native_persons_predictions_or_fine_cells_exported") is not False):
        raise ValueError("Unqualified four-axis source experiment")
    expected = {(frame, level, fold, model, cohort) for frame in FRAMES for level in LEVELS
                for fold in range(5) for model in MODELS for cohort in COHORTS}
    rows = {(r["weight_frame"], r["level"], r["fold"], r["model"], r["cohort"]): r for r in data["rows"]}
    if set(rows) != expected or len(data["rows"]) != len(expected):
        raise ValueError("Incomplete or duplicate whole source queries")
    row_fields = {"weight_frame", "level", "fold", "model", "cohort", "available", "n",
                  "reason", "weight_sum", "nll_sum", "brier_sum"}
    for row in rows.values():
        if set(row) != row_fields:
            raise ValueError("Unexpected public fields")
        if row["available"]:
            minimum = 100 if row["cohort"] in COHORTS[:2] else 30
            if (row["n"] < minimum or row["reason"] is not None or number(row["weight_sum"]) <= 0
                    or number(row["nll_sum"]) < 0 or not 0 <= number(row["brier_sum"]) <= 2*number(row["weight_sum"])):
                raise ValueError("Invalid whole-cohort source sums")
        elif any(row[key] is not None for key in ("n", "weight_sum", "nll_sum", "brier_sum")):
            raise ValueError("Held source query must remain wholly withheld")
    for frame in FRAMES:
        for level in LEVELS:
            for fold in range(5):
                for cohort in COHORTS:
                    same = [rows[frame, level, fold, model, cohort] for model in MODELS]
                    if len({(r["available"], r["n"], r["weight_sum"]) for r in same}) != 1:
                        raise ValueError("Models scored on unequal source frames")
                    if cohort == "marginal_house" and same[0]["available"]:
                        for field in ("nll_sum", "brier_sum"):
                            if abs(number(same[0][field])-number(same[2][field])) > Decimal("2e-6"):
                                raise ValueError("Fixed-pair projection changed the accepted House margin")
    diagnostic_keys = {(f, l, k) for f in FRAMES for l in LEVELS for k in range(5)}
    diagnostics = {(r["weight_frame"], r["level"], r["fold"]): r for r in data["diagnostics"]}
    if set(diagnostics) != diagnostic_keys or len(data["diagnostics"]) != 30:
        raise ValueError("Incomplete margin/dual checks")
    for row in diagnostics.values():
        if (not 0 <= number(row["maximum_pair_marginal_error"]) <= Decimal("2.001e-12")
                or not 0 <= number(row["maximum_dual_certificate_error"]) <= Decimal("1e-8")):
            raise ValueError("Pair margin or dual certificate failed")
    references = {r["cohort"]: r for r in data["references"]}
    if set(references) != set(OUTCOMES) or len(data["references"]) != 2:
        raise ValueError("Incomplete primary coarse reference decisions")
    for cohort, reference in references.items():
        if reference["population_validation"] or not reference["source_code_transport_conditional"]:
            raise ValueError("Coarse source response is not population truth")
        if reference["available"]:
            if (set(reference["cells"]) != set(OUTCOMES[cohort])
                    or min(c["n"] for c in reference["cells"].values()) < 30
                    or any(Fraction(c["weight"]) <= 0 for c in reference["cells"].values())):
                raise ValueError("Whole coarse table disclosure hold")
        elif reference["cells"] is not None:
            raise ValueError("Held native reference must not disclose cells")
    forecasts = {(r["level"], r["fold"], r["model"], r["cohort"]): r for r in data["forecasts"]}
    expected_forecasts = {(l, k, m, c) for l in LEVELS for k in range(5) for m in MODELS for c in OUTCOMES
                          if rows[FRAMES[0], l, k, m, c+"_future15"]["available"]}
    if set(forecasts) != expected_forecasts or len(data["forecasts"]) != len(expected_forecasts):
        raise ValueError("Incomplete primary synthetic forecast queries")
    for (level, fold, model, cohort), row in forecasts.items():
        scored = rows[FRAMES[0], level, fold, model, cohort+"_future15"]
        if (row["weight_frame"] != FRAMES[0] or set(row["predictions"]) != set(OUTCOMES[cohort])
                or row["n"] != scored["n"] or row["weight_sum"] != scored["weight_sum"]
                or any(number(value) < 0 for value in row["predictions"].values())
                or abs(sum(map(number, row["predictions"].values()))-number(row["weight_sum"])) > Decimal("1e-8")):
            raise ValueError("Invalid exhaustive synthetic outcome partition")
    scores, stress, flow, simulations = [], [], [], []
    with localcontext() as context:
        context.prec = 70
        for frame in FRAMES:
            for level in LEVELS:
                for model in MODELS:
                    for cohort in COHORTS:
                        selected = [rows[frame, level, k, model, cohort] for k in range(5)]
                        available = all(row["available"] for row in selected)
                        for metric, field in METRICS.items():
                            value = sum(number(r[field]) for r in selected)/sum(number(r["weight_sum"]) for r in selected) if available else None
                            scores.append(dict(weight_frame=frame, level=level, model=model, cohort=cohort, metric=metric,
                                available=available, value=rounded(value) if available else None,
                                reason=None if available else "whole_five_fold_query_support_hold"))
                for cohort in COHORTS:
                    if not all(rows[frame, level, k, MODELS[0], cohort]["available"] for k in range(5)):
                        continue
                    for model in MODELS[1:]:
                        for counts, multiplicity in compositions():
                            for metric, field in METRICS.items():
                                values = {}
                                for name in (MODELS[0], model):
                                    values[name] = sum(number(rows[frame, level, k, name, cohort][field])*n for k, n in enumerate(counts))/sum(
                                        number(rows[frame, level, k, name, cohort]["weight_sum"])*n for k, n in enumerate(counts))
                                stress.append(dict(weight_frame=frame, level=level, model=model, cohort=cohort, metric=metric,
                                    fold_counts="|".join(map(str, counts)), ordered_draw_multiplicity=multiplicity,
                                    model_minus_independent_pairs=rounded(values[model]-values[MODELS[0]]),
                                    interpretation="overlapping_training_fold_composition_stress_NOT_CI"))
        for level in LEVELS:
            for model in MODELS:
                for cohort, outcomes in OUTCOMES.items():
                    if not all((level, k, model, cohort) in forecasts for k in range(5)):
                        continue
                    selected = [forecasts[level, k, model, cohort] for k in range(5)]
                    weight = sum(number(row["weight_sum"]) for row in selected)
                    predictions = {key: sum(number(row["predictions"][key]) for row in selected) for key in outcomes}
                    reference = references[cohort]
                    for outcome, predicted in predictions.items():
                        native = reference["cells"][outcome] if reference["available"] else None
                        actual_weight = Fraction(native["weight"]) if native else None
                        observed = Decimal(actual_weight.numerator)/Decimal(actual_weight.denominator) if native else None
                        if reference["available"]:
                            native_total = sum(Fraction(c["weight"]) for c in reference["cells"].values())
                            observed_percent = 100*observed/(Decimal(native_total.numerator)/Decimal(native_total.denominator))
                        else:
                            observed_percent = None
                        flow.append(dict(level=level, model=model, cohort=cohort, outcome=outcome,
                            synthetic_source_weight=rounded(predicted), predicted_source_percent=rounded(100*predicted/weight),
                            observed_coarse_reference_available=reference["available"],
                            observed_raw_cases=native["n"] if native else None,
                            observed_source_weight=str(actual_weight) if native else None,
                            observed_source_percent=rounded(observed_percent) if native else None,
                            prediction_minus_reference_pp=rounded(100*predicted/weight-observed_percent) if native else None,
                            population_or2026_validation=False))
                    for seed in (11, 29, 47, 83, 101):
                        counts = Counter(random.Random(seed).choices(outcomes, weights=[float(predictions[k]/weight) for k in outcomes], k=10000))
                        for outcome in outcomes:
                            simulations.append(dict(level=level, model=model, cohort=cohort, seed=seed, synthetic_draws=10000,
                                outcome=outcome, simulated_draw_count=counts[outcome], simulated_percent=rounded(Decimal(counts[outcome])/100),
                                analytic_source_percent=rounded(100*predictions[outcome]/weight), design_confidence_interval=False,
                                actual_people_or_2026_forecast=False))
    summary = dict(contract="participation.house_four_axis_public.v1", source_rows=6175, new_conditional_heads=30,
        accepted_paired_heads_reused=60, complete_score_queries=len(rows), pooled_scores=len(scores),
        primary_synthetic_forecast_queries=len(forecasts), complete_coarse_prediction_rows=len(flow),
        source_predictive_simulation_rows=len(simulations), complete_fold_stress_rows=len(stress),
        primary_scores=[r for r in scores if r["weight_frame"] == FRAMES[0]],
        coarse_reference_decisions=[dict(cohort=r["cohort"], available=r["available"], reason=r["reason"]) for r in references.values()],
        full_four_axis_dependence_modeled=True, fixed_pair_marginals_verified=True,
        conditional_head_training_uses_admin_target_factor_but_test_forecasts_enumerate_all_pairs=True,
        forecast_before_any_test_future_labels=True, reported_choices_not_administrative_candidate_truth=True,
        older_native_weight_frames_sensitivity_only=True, known_future_admin_binary_scores_outcome_selected=True,
        native_unknowns_and_conflicts_retained=True, firstever_eligibility_death_migration_identified=False,
        native_persons_predictions_and_fine_cells_exported=False, population_or2026_transport_validated=False,
        original_default_or_live_website_changed=False, design_confidence_intervals=None)
    forecast_flat = []
    for row in data["forecasts"]:
        forecast_flat.extend(dict(**{k: v for k, v in row.items() if k != "predictions"},
                                 outcome=key, predicted_source_weight=value) for key, value in row["predictions"].items())
    return {"fold-scores.csv": csv_bytes(data["rows"]), "scores.csv": csv_bytes(scores),
        "synthetic-forecasts.csv": csv_bytes(forecast_flat), "source-outcomes.csv": csv_bytes(flow),
        "source-predictive-simulations.csv": csv_bytes(simulations), "fold-composition-stress.csv": csv_bytes(stress),
        "pair-margin-diagnostics.csv": csv_bytes(data["diagnostics"]),
        "coarse-reference-decisions.json": json_bytes(data["references"]), "summary.json": json_bytes(summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("sufficient", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete public output")
    outputs = replay(json.loads(args.sufficient.read_bytes()))
    args.output.mkdir(parents=True)
    for name, body in outputs.items():
        (args.output/name).write_bytes(body)
    print(json.dumps(dict(status="complete_four_axis_public_replay", outputs=len(outputs))), flush=True)


if __name__ == "__main__":
    main()
