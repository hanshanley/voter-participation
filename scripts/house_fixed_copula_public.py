"""Replay broad nested-calibration sufficient sums without native records or fits."""

import argparse
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import statistics

from house_fixed_copula import THETAS, select_theta
from house_pair_public import PAIRS, compositions, csv_bytes, fit_margins, json_bytes, number, odds_ratio, rounded, switch_rate


FRAMES = ("commonpostweight_24", "commonpostweight_22", "vvweight_post_22")
LEVELS = ("history", "demographic")
KINDS = ("baseline", "calibrated")
SCORES = {"House_logloss": ("nll_sum", "weight_sum"), "House_Brier": ("brier_sum", "weight_sum"),
          "selected_major_logloss": ("selected_nll_sum", "selected_weight_sum"),
          "selected_major_Brier": ("selected_brier_sum", "selected_weight_sum")}


def replay(sufficient, reference):
    if (sufficient.get("contract") != "participation.house_fixed_copula_sufficient.v1"
            or sufficient.get("source_rows") != 6175
            or sufficient.get("population_validation") is not False
            or sufficient.get("source_code_transport_conditional") is not True):
        raise ValueError("Unqualified retained-source calibration")
    curves = {(r["weight_frame"], r["level"], r["outer_fold"], float(r["theta"])): r
              for r in sufficient["curves"]}
    decisions = {(r["weight_frame"], r["level"], r["outer_fold"]): r for r in sufficient["decisions"]}
    rows = {(r["weight_frame"], r["level"], r["outer_fold"], r["kind"]): r for r in sufficient["rows"]}
    expected = {(f, l, k) for f in FRAMES for l in LEVELS for k in range(5)}
    if (set(decisions) != expected or len(sufficient["decisions"]) != 30 or
            set(curves) != {(*identity, t) for identity in expected for t in THETAS} or
            len(sufficient["curves"]) != 270 or
            set(rows) != {(*identity, kind) for identity in expected for kind in KINDS} or
            len(sufficient["rows"]) != 60):
        raise ValueError("Incomplete or duplicated prespecified nested source queries")
    curve_fields = {"weight_frame", "level", "outer_fold", "theta", "calibration_n", "weight_sum",
                    "nll_sum", "brier_sum", "maximum_case_marginal_error",
                    "maximum_dual_certificate_error", "projection_iterations"}
    row_fields = (curve_fields - {"calibration_n"}) | {"kind", "n"}
    for row in sufficient["curves"]:
        if set(row) != curve_fields or row["calibration_n"] < 100:
            raise ValueError("Unexpected calibration fields or whole-fold support hold")
    for row in sufficient["rows"]:
        fields = set(row_fields)
        if row["weight_frame"] == FRAMES[0]:
            fields |= {"selected_n", "selected_weight_sum", "selected_nll_sum",
                       "selected_brier_sum", "selected_predictions"}
            if row["selected_n"] < 100 or set(row["selected_predictions"]) != set(PAIRS):
                raise ValueError("Whole selected-source support hold")
        if set(row) != fields or row["n"] < 100:
            raise ValueError("Unexpected scored fields or whole-fold support hold")
    for row in [*sufficient["rows"], *sufficient["curves"]]:
        if (number(row["weight_sum"]) <= 0 or number(row["nll_sum"]) < 0 or
                not 0 <= number(row["brier_sum"]) <= 2*number(row["weight_sum"]) or
                not 0 <= number(row["maximum_case_marginal_error"]) <= Decimal("2.001e-12") or
                not 0 <= number(row["maximum_dual_certificate_error"]) <= Decimal("1e-8")):
            raise ValueError("Invalid source sum or fixed-margin/dual certificate")
    decision_rows = []
    for identity in sorted(expected):
        if len({(curves[identity+(theta,)]["calibration_n"],
                 curves[identity+(theta,)]["weight_sum"]) for theta in THETAS}) != 1:
            raise ValueError("Calibration strengths used unequal inner source frames")
        curve = {theta: float(curves[identity+(theta,)]["nll_sum"])/float(curves[identity+(theta,)]["weight_sum"])
                 for theta in THETAS}
        chosen = select_theta(curve)
        if decisions[identity]["selected_theta"] != chosen or rows[identity+("calibrated",)]["theta"] != chosen:
            raise ValueError("Held-out parameter is not the inner-only selected theta")
        if (abs(decisions[identity]["calibration_logloss"]-curve[chosen]) > 1e-12 or
                abs(decisions[identity]["baseline_calibration_logloss"]-curve[1.]) > 1e-12):
            raise ValueError("Calibration decision differs from its inner-only curve")
        if rows[identity+("baseline",)]["theta"] != 1:
            raise ValueError("The accepted independence baseline must not change")
        for field in ("n", "weight_sum"):
            if rows[identity+("baseline",)][field] != rows[identity+("calibrated",)][field]:
                raise ValueError("Models scored on unequal held-out source frames")
        decision_rows.append(dict(weight_frame=identity[0], level=identity[1], outer_fold=identity[2],
            selected_theta=chosen, calibration_logloss=rounded(number(curve[chosen])),
            baseline_calibration_logloss=rounded(number(curve[1.]))))
    if reference["population_validation"] or not reference["source_code_transport_assumption_required"]:
        raise ValueError("Native coding and population holds must remain")
    ref = next(row["cells"] for row in reference["decisions"]
               if row["source"] == "CES_retained_panel" and row["available"])
    if min(value["n"] for value in ref.values()) < 30:
        raise ValueError("Exact predecessor reference support hold")
    observed = {key: number(value["weight"]) for key, value in ref.items()}
    score_rows, flow_rows, stages, stress_rows = [], [], [], []
    means = {}
    with localcontext() as context:
        context.prec = 70
        for frame in FRAMES:
            for level in LEVELS:
                for kind in KINDS:
                    selected = [rows[frame, level, fold, kind] for fold in range(5)]
                    metrics = list(SCORES) if frame == FRAMES[0] else list(SCORES)[:2]
                    for metric in metrics:
                        numerator, denominator = SCORES[metric]
                        value = sum(number(r[numerator]) for r in selected)/sum(number(r[denominator]) for r in selected)
                        means[frame, level, kind, metric] = value
                        score_rows.append(dict(weight_frame=frame, level=level, kind=kind, metric=metric,
                            value=rounded(value), frame_role="primary" if frame == FRAMES[0] else "older_weight_sensitivity_only"))
                    if frame != FRAMES[0]:
                        continue
                    if sum(r["selected_n"] for r in selected) != sum(value["n"] for value in ref.values()):
                        raise ValueError("Reference cohort changed")
                    prior = {key: sum(number(r["selected_predictions"][key]) for r in selected) for key in PAIRS}
                    scale = sum(observed.values())/sum(prior.values())
                    prior = {key: value*scale for key, value in prior.items()}
                    matched = fit_margins(prior, observed)
                    for stage, table in (("unconditioned", prior), ("matched_source_margins", matched)):
                        residual = max(abs(table["DD"]+table["DR"]-observed["DD"]-observed["DR"]),
                                       abs(table["DD"]+table["RD"]-observed["DD"]-observed["RD"]),
                                       abs(sum(table.values())-sum(observed.values())))
                        stages.append(dict(level=level, kind=kind, stage=stage,
                            gross_switch_percent=rounded(switch_rate(table)),
                            reference_gross_switch_percent=rounded(switch_rate(observed)),
                            switch_error_pp=rounded(switch_rate(table)-switch_rate(observed)),
                            forecast_odds_ratio=rounded(odds_ratio(table)), maximum_margin_residual=str(residual)))
                        for pair in PAIRS:
                            flow_rows.append(dict(level=level, kind=kind, stage=stage, previous_house=pair[0],
                                current_house=pair[1], synthetic_selected_source_weight=rounded(table[pair]),
                                reference_source_weight=str(observed[pair]), observed_individual_gold=False))
        for frame in FRAMES:
            for level in LEVELS:
                for counts, multiplicity in compositions():
                    metrics = list(SCORES) if frame == FRAMES[0] else list(SCORES)[:2]
                    for metric in metrics:
                        numerator, denominator = SCORES[metric]
                        values = {}
                        for kind in KINDS:
                            selected = [rows[frame, level, fold, kind] for fold in range(5)]
                            values[kind] = sum(number(row[numerator])*count for row, count in zip(selected, counts))/sum(
                                number(row[denominator])*count for row, count in zip(selected, counts))
                        stress_rows.append(dict(weight_frame=frame, level=level, metric=metric,
                            fold_counts="|".join(map(str, counts)), ordered_draw_multiplicity=multiplicity,
                            calibrated_minus_independent=rounded(values["calibrated"]-values["baseline"]),
                            interpretation="fold_composition_stress_not_CI"))
        base = lambda metric: means[FRAMES[0], "history", "baseline", metric]
        calibrated = lambda metric: means[FRAMES[0], "history", "calibrated", metric]
        median = statistics.median(decisions[FRAMES[0], "history", fold]["selected_theta"] for fold in range(5))
        gates = dict(full_logloss_improves=calibrated("House_logloss") < base("House_logloss"),
            full_Brier_not_worse=calibrated("House_Brier") <= base("House_Brier")+Decimal("1e-10"),
            selected_major_Brier_not_worse=calibrated("selected_major_Brier") <= base("selected_major_Brier")+Decimal("1e-10"),
            positive_source_median=median > 1, all_case_margins_and_dual_certificates_pass=True)
        summary = dict(contract="participation.house_fixed_copula_public.v1", source_rows=6175,
            calibration_curve_rows=270, calibration_decisions=30, outer_score_rows=60,
            pooled_score_rows=len(score_rows), synthetic_flow_rows=len(flow_rows), matching_stages=len(stages),
            fold_composition_rows=len(stress_rows), source_primary_history_theta_median=median,
            conditional_transport_gate=gates, conditional_transport_gate_passed=all(gates.values()),
            historical_profile_requested_thetas={"attenuated": math.sqrt(median), "full": median},
            primary_scores=[r for r in score_rows if r["weight_frame"] == FRAMES[0]],
            primary_flow_stages=stages, fixed_marginals_not_changed=True, native_persons_or_predictions_exported=False,
            code_transport_conditional=True, population_or2026_parameter_validation=False,
            source_feature_set_and_election_direction_differ_from2026=True,
            default_accepted_model_changed=False, design_confidence_intervals=None)
    outer_flat = []
    for row in sufficient["rows"]:
        flat = {key: value for key, value in row.items() if key != "selected_predictions"}
        flat.update({"predicted_"+key: row.get("selected_predictions", {}).get(key, "") for key in PAIRS})
        outer_flat.append(flat)
    fields = sorted({key for row in outer_flat for key in row})
    for row in outer_flat:
        for key in fields:
            row.setdefault(key, "")
    return {"calibration-curves.csv": csv_bytes(sufficient["curves"]),
        "selection-decisions.csv": csv_bytes(decision_rows), "outer-scores.csv": csv_bytes(outer_flat, fields),
        "scores.csv": csv_bytes(score_rows), "synthetic-flows.csv": csv_bytes(flow_rows),
        "source-margin-stages.csv": csv_bytes(stages), "fold-composition-stress.csv": csv_bytes(stress_rows),
        "summary.json": json_bytes(summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("sufficient", "reference", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete public output")
    outputs = replay(json.loads(args.sufficient.read_bytes()), json.loads(args.reference.read_bytes()))
    args.output.mkdir(parents=True)
    for name, body in outputs.items():
        (args.output/name).write_bytes(body)
    print(json.dumps(dict(status="all_nested_source_queries_replayed", complete_outputs=len(outputs))))


if __name__ == "__main__":
    main()
