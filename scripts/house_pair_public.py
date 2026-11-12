"""Standard-library replay of paired-source scores and margin-matched flow tests."""

import argparse
import csv
from decimal import Decimal, localcontext
import io
import itertools
import json
import math
from pathlib import Path


MODELS = ("pooled_history_pairs", "independent_history", "paired_history",
          "independent_demographic", "paired_demographic")
FRAMES = ("commonpostweight_24", "commonpostweight_22", "vvweight_post_22")
PAIRS = ("DD", "DR", "RD", "RR")
SCORES = {
    "admin_logloss": ("admin_nll_sum", "weight_sum"),
    "admin_Brier": ("admin_brier_sum", "weight_sum"),
    "house_logloss": ("house_nll_sum", "weight_sum"),
    "house_Brier": ("house_brier_sum", "weight_sum"),
    "known_admin_logloss": ("known_admin_nll_sum", "known_admin_weight_sum"),
    "known_admin_Brier": ("known_admin_brier_sum", "known_admin_weight_sum"),
    "selected_major_logloss": ("selected_major_nll_sum", "selected_weight_sum"),
    "selected_major_Brier": ("selected_major_brier_sum", "selected_weight_sum")}


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Nonfinite public sufficient sum")
    return result


def rounded(value):
    return format(value, ".12f")


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows, fields=None):
    if fields is None:
        fields = list(rows[0])
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def fit_margins(prior, target):
    total = sum(target.values())
    row = target["DD"] + target["DR"]
    column = target["DD"] + target["RD"]
    lower, upper = max(Decimal(0), row + column - total), min(row, column)
    positive = prior["DD"] * prior["RR"]
    negative = prior["DR"] * prior["RD"]
    if min(prior.values()) <= 0 or min(target.values()) <= 0:
        raise ValueError("The fixed source test requires positive supported four-cell tables")
    for iteration in range(260):
        middle = (lower + upper) / 2
        if middle == lower or middle == upper:
            break
        value = negative * middle * (total - row - column + middle) - positive * (row - middle) * (column - middle)
        if value > 0:
            upper = middle
        else:
            lower = middle
    dd = (lower + upper) / 2
    result = dict(DD=dd, DR=row-dd, RD=column-dd, RR=total-row-column+dd)
    assert min(result.values()) > 0
    return result


def switch_rate(table):
    return 100 * (table["DR"] + table["RD"]) / sum(table.values())


def odds_ratio(table):
    return table["DD"] * table["RR"] / (table["DR"] * table["RD"])


def compositions():
    for first in itertools.product(range(6), repeat=4):
        remaining = 5 - sum(first)
        if remaining >= 0:
            counts = (*first, remaining)
            multiplicity = math.factorial(5)
            for value in counts:
                multiplicity //= math.factorial(value)
            yield counts, multiplicity


def replay(sufficient, reference):
    expected = {(frame, model, fold) for frame in FRAMES for model in MODELS for fold in range(5)}
    by_id, fold_rows = {}, []
    for row in sufficient["rows"]:
        identity = row["weight_frame"], row["model"], row["fold"]
        if identity not in expected or identity in by_id:
            raise ValueError("Missing or repeated source-fold query")
        allowed = {"weight_frame", "model", "fold", "n", "weight_sum", "admin_nll_sum",
                   "admin_brier_sum", "house_nll_sum", "house_brier_sum", "known_admin_n",
                   "known_admin_weight_sum", "known_admin_nll_sum", "known_admin_brier_sum"}
        if identity[0] == FRAMES[0]:
            allowed |= {"selected_source_n", "selected_weight_sum", "selected_major_nll_sum",
                        "selected_major_brier_sum", "selected_major_predictions"}
        if set(row) != allowed:
            raise ValueError("Unexpected fields in coarse source sufficient input")
        if min(row["n"], row["known_admin_n"], row.get("selected_source_n", 100)) < 100:
            raise ValueError("Whole-fold support hold")
        for field in allowed - {"weight_frame", "model", "fold", "selected_major_predictions"}:
            if number(row[field]) < 0:
                raise ValueError("Negative coarse score sufficient input")
        if number(row["weight_sum"]) <= 0 or number(row["known_admin_weight_sum"]) <= 0:
            raise ValueError("Empty weighted source fold")
        if identity[0] == FRAMES[0]:
            if set(row["selected_major_predictions"]) != set(PAIRS):
                raise ValueError("Incomplete primary synthetic forecast")
            if min(number(v) for v in row["selected_major_predictions"].values()) <= 0:
                raise ValueError("Nonpositive synthetic forecast")
        by_id[identity] = row
        flat = {key: value for key, value in row.items() if key != "selected_major_predictions"}
        flat.update({"predicted_" + key: row.get("selected_major_predictions", {}).get(key, "") for key in PAIRS})
        fold_rows.append(flat)
    if set(by_id) != expected:
        raise ValueError("Incomplete75-row public source query set")
    for frame in FRAMES:
        for fold in range(5):
            base = by_id[frame, MODELS[0], fold]
            for model in MODELS:
                candidate = by_id[frame, model, fold]
                for field in ("n", "weight_sum", "known_admin_n", "known_admin_weight_sum"):
                    if candidate[field] != base[field]:
                        raise ValueError("Models compared on unequal held-out source frames")
    if reference["population_validation"] or not reference["source_code_transport_assumption_required"]:
        raise ValueError("Reference must retain source coding and population holds")
    raw_reference = next(row["cells"] for row in reference["decisions"]
                         if row["source"] == "CES_retained_panel" and row["available"])
    if set(raw_reference) != set(PAIRS) or min(v["n"] for v in raw_reference.values()) < 30:
        raise ValueError("Exact predecessor whole-table source-support hold")
    observed = {key: number(value["weight"]) for key, value in raw_reference.items()}
    score_rows, stage_rows, flow_rows, decisions, stress_rows = [], [], [], [], []
    with localcontext() as context:
        context.prec = 70
        primary_scores = {}
        for frame in FRAMES:
            for model in MODELS:
                rows = [by_id[frame, model, fold] for fold in range(5)]
                available_scores = list(SCORES) if frame == FRAMES[0] else list(SCORES)[:6]
                for metric in available_scores:
                    numerator, denominator = SCORES[metric]
                    loss = sum(number(row[numerator]) for row in rows) / sum(number(row[denominator]) for row in rows)
                    score_rows.append(dict(weight_frame=frame, model=model, metric=metric, value=rounded(loss),
                                           source_frame="primary" if frame == FRAMES[0] else "older_weight_sensitivity_only"))
                    if frame == FRAMES[0]:
                        primary_scores.setdefault(model, {})[metric] = rounded(loss)
                decisions.append(dict(weight_frame=frame, model=model, OOF_scores_available=True,
                    primary_four_cell_flow_available=frame == FRAMES[0],
                    flow_hold_reason="" if frame == FRAMES[0] else "no_new_older_weight_raw_reference_release"))
                if frame != FRAMES[0]:
                    continue
                if sum(row["selected_source_n"] for row in rows) != sum(v["n"] for v in raw_reference.values()):
                    raise ValueError("Selected source cohort differs from exact predecessor")
                prior = {key: sum(number(row["selected_major_predictions"][key]) for row in rows) for key in PAIRS}
                scale = sum(observed.values()) / sum(prior.values())
                prior = {key: value * scale for key, value in prior.items()}
                fitted = fit_margins(prior, observed)
                for stage, table in (("unconditioned", prior), ("matched_source_margins", fitted)):
                    residual = max(abs(table["DD"]+table["DR"]-observed["DD"]-observed["DR"]),
                                   abs(table["DD"]+table["RD"]-observed["DD"]-observed["RD"]),
                                   abs(sum(table.values())-sum(observed.values())))
                    ratio_error = abs(odds_ratio(table) / odds_ratio(prior) - 1)
                    if stage == "matched_source_margins" and (residual > Decimal("1e-40") or ratio_error > Decimal("1e-40")):
                        raise ValueError("Source-margin or forecast-odds preservation failed")
                    rate = switch_rate(table)
                    stage_rows.append(dict(model=model, stage=stage, predicted_gross_switch_percent=rounded(rate),
                        reference_gross_switch_percent=rounded(switch_rate(observed)),
                        gross_switch_error_pp=rounded(rate-switch_rate(observed)),
                        absolute_gross_switch_error_pp=rounded(abs(rate-switch_rate(observed))),
                        forecast_odds_ratio=rounded(odds_ratio(table)), max_margin_residual=str(residual),
                        relative_forecast_odds_error=str(ratio_error)))
                    for pair in PAIRS:
                        flow_rows.append(dict(model=model, stage=stage, previous_house=pair[0],
                            current_house=pair[1], synthetic_selected_source_weight=rounded(table[pair]),
                            reference_selected_source_weight=str(observed[pair]),
                            interpretation="conditional_selected_cohort_not_population_or2026flow"))
        combinations = list(compositions())
        assert len(combinations) == 126 and sum(m for c, m in combinations) == 3125
        for frame in FRAMES:
            for level in ("history", "demographic"):
                for counts, multiplicity in combinations:
                    available_scores = list(SCORES) if frame == FRAMES[0] else list(SCORES)[:6]
                    for metric in available_scores:
                        numerator, denominator = SCORES[metric]
                        values = {}
                        for structure in ("paired", "independent"):
                            model = structure + "_" + level
                            rows = [by_id[frame, model, fold] for fold in range(5)]
                            values[structure] = sum(number(row[numerator])*count for row, count in zip(rows, counts)) / sum(
                                number(row[denominator])*count for row, count in zip(rows, counts))
                        stress_rows.append(dict(weight_frame=frame, feature_level=level, metric=metric,
                            fold_counts="|".join(map(str, counts)), ordered_resampling_multiplicity=multiplicity,
                            paired_minus_independent=rounded(values["paired"]-values["independent"]),
                            interpretation="fold_composition_stress_not_CI_or_independent_units"))
        summary = dict(contract="participation.house_pair_oof_comparison.v1", raw_source_cases=6175,
            model_hypotheses=5, native_weight_frames=3, outer_folds=5, source_fold_rows=len(by_id),
            score_rows=len(score_rows), synthetic_flow_rows=len(flow_rows), stage_rows=len(stage_rows),
            exact_fold_compositions=126, ordered_fold_draws=3125, stress_rows=len(stress_rows),
            primary_scores=primary_scores, primary_source_flow_stages=stage_rows,
            source_code_transport_conditional=True, population_validation=False,
            exact_replication_of2026_predictors=False, accepted_models_changed=False,
            design_confidence_intervals=None, source_administrative_and_House_pairs_modeled_separately=True,
            native_persons_or_private_fine_cells_exported=False)
    fold_fields = ["weight_frame","model","fold","n","weight_sum","admin_nll_sum","admin_brier_sum",
                   "house_nll_sum","house_brier_sum","known_admin_n","known_admin_weight_sum",
                   "known_admin_nll_sum","known_admin_brier_sum","selected_source_n","selected_weight_sum",
                   "selected_major_nll_sum","selected_major_brier_sum",*[f"predicted_{key}" for key in PAIRS]]
    for row in fold_rows:
        for key in fold_fields:
            row.setdefault(key, "")
    return {"scores.csv": csv_bytes(score_rows), "fold-scores.csv": csv_bytes(fold_rows, fold_fields),
            "synthetic-flows.csv": csv_bytes(flow_rows), "source-margin-stages.csv": csv_bytes(stage_rows),
            "fold-composition-stress.csv": csv_bytes(stress_rows), "query-decisions.csv": csv_bytes(decisions),
            "summary.json": json_bytes(summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sufficient", "reference", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete public output directory")
    outputs = replay(json.loads(args.sufficient.read_bytes()), json.loads(args.reference.read_bytes()))
    args.output.mkdir(parents=True)
    for name, body in outputs.items():
        (args.output / name).write_bytes(body)
    print(json.dumps(dict(status="all_public_paired_source_queries_replayed", complete_output_files=len(outputs))))


if __name__ == "__main__":
    main()
