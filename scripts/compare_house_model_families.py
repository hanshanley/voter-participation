"""Compare fixed NORC model families on identical held endpoints and simulation grids."""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from scripts import norc_house_model as simulation


BASELINE = "accepted_ridge_multinomial"
FAMILIES = (BASELINE, "histogram_gradient_boosting", "extra_randomized_trees")
LABELS = {BASELINE: "Multinomial ridge · accepted baseline",
          FAMILIES[1]: "Histogram gradient boosting",
          FAMILIES[2]: "Extra-randomized trees"}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def normalized_metrics(priors, historical=None):
    validation = priors["validation"]
    if historical is None:
        transfer = validation["historical_transfer"]
    else:
        transfer = dict(historical["with_demographics"],
            source_weighted_multiclass_brier=historical["with_demographics"]["source_weighted_brier"])
    return {"house24_bridge": validation["house_2024_bridge"],
            "house26_response": validation["current_2026_response"], "historical_transfer": transfer}


def select_family(metrics):
    reference = metrics[BASELINE]
    choices, decisions = [BASELINE], []
    for family in FAMILIES[1:]:
        value = metrics[family]
        flags = {
            "historical_log_loss_not_worse": value["historical_transfer"]["source_weighted_log_loss"] <=
                reference["historical_transfer"]["source_weighted_log_loss"],
            "historical_Brier_not_worse": value["historical_transfer"]["source_weighted_multiclass_brier"] <=
                reference["historical_transfer"]["source_weighted_multiclass_brier"],
            "current_response_Brier_not_worse": value["house26_response"]["source_weighted_multiclass_brier"] <=
                reference["house26_response"]["source_weighted_multiclass_brier"],
        }
        admissible = all(flags.values())
        if admissible:
            choices.append(family)
        decisions.append(dict(family=family, admissible=admissible, **flags,
                              current_partisan_returns_used=False))
    preferred = min(choices, key=lambda family: (
        metrics[family]["historical_transfer"]["source_weighted_log_loss"], FAMILIES.index(family)))
    return dict(preferred_family=preferred, decisions=decisions,
        selection_uses_source_validation_not_current_return_errors=True,
        historical_test_used_for_family_selection_not_independent_postselection_test=True,
        current_partisan_returns_used=False)


def check_public_priors(priors, baseline):
    if (priors["contract"] != "participation.norc_house_demographic_priors.v1"
            or priors["raw_records_or_private_fine_cells_exported"] is not False
            or priors["old_synthetic_state_couplings_used"] is not False
            or priors["source_input_sha256"] != baseline["source_input_sha256"]
            or priors["source_cases"] != baseline["source_cases"]
            or set(priors["states"]) != set(baseline["states"])):
        raise ValueError("Changed source/privacy contract")
    for code, state in priors["states"].items():
        old = baseline["states"][code]
        fields = ("dimension", "group", "label", "available")
        if sorted(tuple(g[k] for k in fields) for g in state["groups"]) != sorted(
                tuple(g[k] for k in fields) for g in old["groups"]):
            raise ValueError("Changed public demographic disclosure mask")
        matrix = state["prior_joint"]
        if len(matrix) != 5 or any(len(row) != 5 or any(not math.isfinite(v) or v < 0 for v in row) for row in matrix):
            raise ValueError("Invalid public synthetic prior")
        if not math.isclose(sum(map(sum, matrix)), 1, abs_tol=1e-10):
            raise ValueError("Synthetic prior is not normalized")


def state_comparisons(results):
    rows = []
    for family in FAMILIES:
        for state in results[family]["rows"]:
            point, prediction = state["point"], state["before_current_party_conditioning"]
            observed = state["reported_comparison"] if state["source_comparison_available"] else None
            row = dict(family=family, state_code=state["state_code"],
                observed_comparison_available=observed is not None,
                observed_previous_margin_pp=observed["previous_margin_pp"] if observed else None,
                observed_current_margin_pp=observed["current_margin_pp"] if observed else None,
                observed_margin_change_pp=observed["reported_change_pp"] if observed else None,
                observed_Democratic_two_party_share_previous_pct=50 + observed["previous_margin_pp"] / 2 if observed else None,
                observed_Democratic_two_party_share_current_pct=50 + observed["current_margin_pp"] / 2 if observed else None,
                observed_Democratic_two_party_share_change_pp=observed["reported_change_pp"] / 2 if observed else None,
                predicted_current_margin_before_party_conditioning_pp=prediction["current_margin_pp"] if prediction else None,
                observed_minus_predicted_margin_pp=prediction["prediction_error_observed_minus_predicted_pp"] if prediction else None,
                observed_minus_predicted_Democratic_two_party_share_pp=
                    prediction["prediction_error_observed_minus_predicted_pp"] / 2 if prediction else None,
                gross_retained_share_pct=state["gross_outcomes"]["retaining"] * 100,
                gross_switched_share_pct=state["gross_outcomes"]["switching"] * 100,
                gross_modeled_exit_share_pct=state["gross_outcomes"]["exit"] * 100,
                model_family_not_independent_behavioral_truth=True)
            for key, value in point["contributions_pp"].items():
                row[key + "_margin_pp"] = value
                row[key + "_Democratic_two_party_share_pp"] = value / 2
            row["net_participation_margin_pp"] = point["net_participation_pp"]
            row["net_participation_Democratic_two_party_share_pp"] = point["net_participation_pp"] / 2
            rows.append(row)
    return rows


def dispersion(results):
    values = {}
    for family, result in results.items():
        values[family] = {row["state_code"]: row for row in result["rows"]}
    rows = []
    for code in sorted(values[BASELINE]):
        available = values[BASELINE][code]["source_comparison_available"]
        for key in (*simulation.MECHANISMS, "net_participation"):
            estimates = [(values[family][code]["point"]["net_participation_pp"] if key == "net_participation"
                else values[family][code]["point"]["contributions_pp"][key]) for family in FAMILIES]
            rows.append(dict(state_code=code, mechanism=key, families=len(FAMILIES),
                observed_comparison_available=available, minimum_margin_pp=min(estimates),
                maximum_margin_pp=max(estimates), family_spread_margin_pp=max(estimates) - min(estimates),
                minimum_Democratic_two_party_share_pp=min(estimates) / 2,
                maximum_Democratic_two_party_share_pp=max(estimates) / 2,
                confidence_interval=False, identified_behavioral_effect=False))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-results", "baseline-priors", "baseline-historical", "hist-priors",
                 "extra-priors", "policy", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh comparison output")
    priors = {BASELINE: json.loads(args.baseline_priors.read_bytes()),
              FAMILIES[1]: json.loads(args.hist_priors.read_bytes()),
              FAMILIES[2]: json.loads(args.extra_priors.read_bytes())}
    for family in FAMILIES:
        check_public_priors(priors[family], priors[BASELINE])
    historical = json.loads(args.baseline_historical.read_bytes())
    metrics = {family: normalized_metrics(priors[family], historical if family == BASELINE else None)
               for family in FAMILIES}
    for role, name in (("house24_bridge", "house_2024_bridge"), ("house26_response", "current_2026_response")):
        expected = priors[BASELINE]["validation"][name]
        for family in FAMILIES[1:]:
            actual = metrics[family][role]
            if (actual["train_cases"], actual["test_cases"]) != (expected["train_cases"], expected["test_cases"]):
                raise ValueError("Changed respondent holdout size")
        if metrics[FAMILIES[1]][role]["test_indices_sha256"] != metrics[FAMILIES[2]][role]["test_indices_sha256"]:
            raise ValueError("Models used different held-out respondents")
    selection = select_family(metrics)
    args.output.mkdir(parents=True)
    (args.output / "selection-before-return-evaluation.json").write_bytes(encoded(selection))
    baseline = json.loads((args.baseline_results / "complete-result.json").read_bytes())
    accepted = dict(rows=[dict(office="house", state_code=row["state_code"],
                               reported_comparison=row["reported_comparison"]) for row in baseline["rows"]])
    results = {BASELINE: baseline}
    for family in FAMILIES:
        directory = args.output / family
        directory.mkdir()
        if family != BASELINE:
            print("Calculating only new family simulations:", family, flush=True)
            results[family] = simulation.build(priors[family], accepted)
        for name, body in simulation.result_files(results[family]).items():
            if family == BASELINE and body != (args.baseline_results / name).read_bytes():
                raise ValueError("Accepted baseline output bytes changed")
            (directory / name).write_bytes(body)
    state_rows, spread = state_comparisons(results), dispersion(results)
    metric_rows = [dict(family=family, role=role, label=LABELS[family],
        source_weighted_log_loss=value["source_weighted_log_loss"],
        source_weighted_multiclass_brier=value["source_weighted_multiclass_brier"],
        current_returns_used_for_fit_or_selection=False)
        for family, roles in metrics.items() for role, value in roles.items()]
    summary = dict(families=list(FAMILIES), states_per_family=50, qualified_comparisons_per_family=48,
        preferred_family=selection["preferred_family"],
        margin_MAE_pp={f: r["preconditioning_margin_MAE_pp"] for f, r in results.items()},
        Democratic_two_party_share_MAE_pp={f: r["preconditioning_margin_MAE_pp"] / 2 for f, r in results.items()},
        state_decisions=len(state_rows), family_dispersion_decisions=len(spread),
        baseline_fits_or_simulations_repeated=False, raw_respondents_exported=False)
    viewer = dict(contract="participation.house_model_families.v1", preferred_family=selection["preferred_family"],
        family_labels=LABELS, families={f: {k: v for k, v in r.items() if not k.startswith("complete_")}
                                    for f, r in results.items()},
        source_validation=metric_rows, state_comparisons=state_rows, family_dispersion=spread, summary=summary,
        no_independent_behavioral_identification=True, family_spread_is_not_confidence_interval=True)
    for name, body in {"viewer-data.json": simulation.encoded(viewer), "summary.json": encoded(summary),
        "complete-source-validation.csv": csv_bytes(metric_rows),
        "complete-state-family-comparisons.csv": csv_bytes(state_rows),
        "complete-family-dispersion.csv": csv_bytes(spread),
        "preregistered-policy.json": args.policy.read_bytes()}.items():
        (args.output / name).write_bytes(body)
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
