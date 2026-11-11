"""Independent scalar checks; deliberately imports neither NumPy nor the fitter."""

import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import zipfile


CELLS = [(a, b) for a in "DRONU" for b in "DRONU"]
TERMS = ("switching", "modeled_nonparticipation", "no_prior_contest_vote_entry",
    "other_choice", "unresolved")
FEATURES = ("m24", "t24", "m26", "t26", "modeled_nonvoter_weight", *TERMS)


class Verifier:
    def __init__(self):
        self.checks = 0

    def require(self, condition, message):
        self.checks += 1
        if not condition:
            raise ValueError(message)

    def close(self, left, right, message, tolerance=1e-8):
        self.require(math.isfinite(left) and math.isfinite(right)
            and abs(left - right) <= tolerance, message)

    def distribution(self, probability):
        self.require(len(probability) == 25, "Incomplete synthetic support")
        for value in probability:
            self.require(math.isfinite(value) and value >= 0, "Invalid synthetic probability")
        self.close(math.fsum(probability), 1, "Probability mass differs", 1e-10)
        contributions = {name: [] for name in FEATURES}
        for (prior, current), value in zip(CELLS, probability):
            old, new = int(prior == "D") - int(prior == "R"), int(current == "D") - int(current == "R")
            for name, coefficient in zip(FEATURES[:5],
                    (old, int(prior in "DR"), new, int(current in "DR"), int(current == "N"))):
                contributions[name].append(value * coefficient)
            term = ("switching" if prior + current in ("DR", "RD") else
                "modeled_nonparticipation" if prior in "DR" and current == "N" else
                "no_prior_contest_vote_entry" if prior == "N" and current in "DR" else
                "unresolved" if "U" in (prior, current) else "other_choice")
            contributions[term].append(value * (new - old))
        return {name: math.fsum(values) for name, values in contributions.items()}

    def entropy_stationarity(self, probability, targets, factor):
        columns = [self.distribution([float(i == j) for j in range(25)]) for i in range(25)]
        allowed = set(range(25))
        for name in FEATURES:
            low, high = min(c[name] for c in columns), max(c[name] for c in columns)
            if abs(targets[name] - low) < 2e-10 or abs(targets[name] - high) < 2e-10:
                allowed &= {i for i, c in enumerate(columns) if abs(c[name] - targets[name]) < 2e-10}
        self.require(all((p > 0) == (i in allowed) for i, p in enumerate(probability)),
            "Synthetic support differs from declared structural boundaries")
        indices = sorted(allowed)
        basis = []
        for vector in [[1.] * len(indices)] + [[columns[i][name] for i in indices] for name in FEATURES]:
            residual = vector[:]
            for _ in range(2):
                for q in basis:
                    projection = math.fsum(a * b for a, b in zip(residual, q))
                    residual = [a - projection * b for a, b in zip(residual, q)]
            norm = math.sqrt(math.fsum(a * a for a in residual))
            if norm > 1e-10:
                basis.append([a / norm for a in residual])
        gradient = [math.log(probability[i]) - (math.log(factor)
            if CELLS[i][0] == CELLS[i][1] and CELLS[i][0] in "DR" else 0) for i in indices]
        for q in basis:
            projection = math.fsum(a * b for a, b in zip(gradient, q))
            gradient = [a - projection * b for a, b in zip(gradient, q)]
        self.require(max(abs(value) for value in gradient) <= 1e-7,
            "Feasible moments do not establish the declared relative-entropy optimum")

    def summary(self, probability, reported):
        m = self.distribution(probability)
        if min(m["t24"], m["t26"]) <= 0:
            self.require(reported["status"] == "no_simulated_major_party_denominator",
                "Absent denominator was not held")
            return
        shares = {}
        classifications = {
            "retaining": lambda a, b: a == b and a in "DR",
            "switching": lambda a, b: a + b in ("DR", "RD"),
            "nonparticipation": lambda a, b: a in "DR" and b == "N",
            "other_choice": lambda a, b: a in "DR" and b == "O",
            "unresolved": lambda a, b: a in "DR" and b == "U"}
        for name, predicate in classifications.items():
            shares[name] = math.fsum(p for (a, b), p in zip(CELLS, probability) if predicate(a, b)) / m["t24"]
            self.close(reported["synthetic_" + name + "_share_of_recalled_major_party"],
                shares[name], "Gross recalled-major-party flow differs")
        self.close(math.fsum(shares.values()), 1, "Gross flows do not partition prior major-party mass")
        entry = math.fsum(p for (a, b), p in zip(CELLS, probability) if a == "N" and b in "DR")
        self.close(reported["synthetic_no_prior_contest_vote_entry_share_of_current_major_party"],
            entry / m["t26"], "Prior-contest nonvote entry differs")
        gross = shares["switching"] * m["t24"] / (1 - m["modeled_nonvoter_weight"])
        self.close(reported["synthetic_gross_switching_share_of_modeled_current_voters"],
            gross, "Current-voter gross switching differs")
        old, new = 100 * m["m24"] / m["t24"], 100 * m["m26"] / m["t26"]
        self.close(reported["prior_recalled_margin_pp"], old, "Recalled margin differs")
        self.close(reported["modeled_current_margin_pp"], new, "Current model margin differs")
        self.close(reported["source_frame_change_pp"], new - old, "Source model change differs")
        self.close(reported["modeled_nonvoter_share"], m["modeled_nonvoter_weight"], "Model class differs")
        scale = (100 / m["t24"] + 100 / m["t26"]) / 2
        parts = {term: scale * m[term] for term in TERMS}
        parts["denominator"] = (m["m24"] + m["m26"]) * (100 / m["t26"] - 100 / m["t24"]) / 2
        for term, value in parts.items():
            self.close(reported["components_pp"][term], value, "Independent signed accounting differs")
        self.close(math.fsum(parts.values()), new - old, "Full source model accounting differs")
        self.require(reported["identified_individual_histories"] is False
            and reported["measured_staying_home"] is None, "Synthetic flows were relabeled as observed histories")

    def monte_carlo(self, cases, reported):
        valid = all(row["status"] == "conditional_synthetic_source_frame_not_people" for row in cases)
        if not valid:
            self.require(reported["status"] == "held_missing_seed_or_major_party_denominator",
                "Missing seed denominator was not held")
            return
        self.require(reported["seeds"] == len(cases), "Incomplete Monte Carlo seed summary")
        for name, row in reported["metrics"].items():
            values = [case[name] for case in cases]
            for key, value in (("mean", statistics.fmean(values)), ("minimum", min(values)),
                    ("maximum", max(values)), ("standard_deviation", statistics.stdev(values))):
                self.close(row[key], value, "Monte Carlo diagnostic differs")


def verify(result, bridge, groups, comparisons, historical_archive):
    v = Verifier()
    v.require(result["cells"] == [list(pair) for pair in CELLS], "Changed synthetic choice labels")
    weights, source_targets = {}, {}
    for row in bridge["state_moments"].values():
        code = row["scope"]
        participation = bridge["state_participation"][code]
        weights[code] = float(participation["modeled_voter_weight"]) + float(participation["modeled_nonvoter_weight"])
        source_targets[code] = {name: float(participation[name] if name == "modeled_nonvoter_weight"
            else row[name]) / weights[code] for name in FEATURES}
    spec, allocations = result["agent_spec"], result["allocations"]
    v.require(set(allocations) == set(source_targets), "Incomplete state experiment")
    v.require(sum(allocations.values()) == spec["agent_budget"], "State agent budget was not conserved")
    for count in allocations.values():
        v.require(isinstance(count, int) and count >= spec["minimum_agents_per_state"], "State floor lost")
    calibration = result["persistence_calibration"]
    kernels = {**calibration["grid_kernels"], **result["coupling_assumptions"]}
    gross = {}
    for identity, kernel in kernels.items():
        code = identity.split("|")[0]
        moment = v.distribution(kernel["probabilities"])
        for name, target in source_targets[code].items():
            v.close(moment[name], target, "Released native moment not reproduced", 2e-10 + 1e-14)
        v.entropy_stationarity(kernel["probabilities"], source_targets[code],
            kernel["fit"]["persistence_factor"])
        v.summary(kernel["probabilities"], kernel["analytic"])
        v.require(kernel["fit"]["source_joint_cells_reconstructed"] is False, "Unidentified source cells claimed")
        gross[identity] = kernel["analytic"]["synthetic_gross_switching_share_of_modeled_current_voters"]
    runs = defaultdict(list)
    budget = defaultdict(int)
    for row in result["seed_results"]:
        identity = row["state_code"] + "|" + str(row["persistence_factor"])
        v.require(row["seed"] in spec["seeds"] and row["agents"] == allocations[row["state_code"]],
            "Unknown state seed or allocation")
        counts = row["simulated_cells"]
        v.require(all(isinstance(n, int) and n >= 0 for n in counts)
            and sum(counts) == row["agents"], "State synthetic draws were not conserved")
        v.summary([n / row["agents"] for n in counts], row)
        runs[identity].append(row)
        budget[row["persistence_factor"], row["seed"]] += sum(counts)
    v.require(len(budget) == len(result["effective_persistence_factors"]) * len(spec["seeds"]),
        "Incomplete factor/seed experiment")
    for count in budget.values():
        v.require(count == spec["agent_budget"], "National diagnostic agent budget differs")
    for identity, kernel in result["coupling_assumptions"].items():
        v.require(len(runs[identity]) == len(spec["seeds"])
            and {r["seed"] for r in runs[identity]} == set(spec["seeds"]), "Incomplete or duplicate seeds")
        v.monte_carlo(runs[identity], kernel["monte_carlo"])
    decisions = {(r["state_code"], r["dimension"], r["group"]): r
        for r in result["complete_demographic_decisions"]}
    v.require(len(decisions) == len(groups["groups"]), "Incomplete demographic query set")
    for source in groups["groups"]:
        row = decisions[source["state_code"], source["dimension"], source["group"]]
        v.require(row["disposition"] == source["disposition"], "Disclosure decision changed")
        if source["disposition"] != "selected_broad_source_model":
            v.require(row["conditional_simulation"] is None, "Protected or unavailable group inferred")
            continue
        q = float(source["modeled_nonvoter_weight"]) / float(source["weight"])
        v.require(row["demographic_party_association_identified"] is False
            and row["conditional_group_draws_are_nonadditive_diagnostics"] is True, "Demographic scope lost")
        v.require({c["persistence_factor"] for c in row["conditional_simulation"]}
            == set(result["effective_persistence_factors"]), "Incomplete demographic assumptions")
        for case in row["conditional_simulation"]:
            code = source["state_code"]
            base = result["coupling_assumptions"][code + "|" + str(case["persistence_factor"])]["probabilities"]
            n = math.fsum(p for (a, b), p in zip(CELLS, base) if b == "N")
            conditional = [p * (q / n if b == "N" else (1 - q) / (1 - n))
                for (a, b), p in zip(CELLS, base)]
            v.summary(conditional, case["analytic"])
            v.close(case["analytic"]["modeled_nonvoter_share"], q, "Disclosed demographic model class differs")
            v.require(len(case["seed_results"]) == len(spec["seeds"])
                and {r["seed"] for r in case["seed_results"]} == set(spec["seeds"]),
                "Incomplete demographic seed experiment")
            for seed in case["seed_results"]:
                counts, count = seed["synthetic_cells"], seed["diagnostic_draws"]
                v.require(count == allocations[code] and all(isinstance(n, int) and n >= 0 for n in counts)
                    and sum(counts) == count, "Conditional demographic diagnostic draws differ")
                v.summary([n / count for n in counts], seed)
            v.monte_carlo(case["seed_results"], case["monte_carlo"])
    selected = [r for r in calibration["complete_poll_decisions"] if r["target_fraction"] is not None]
    v.require({r["id"] for r in calibration["complete_poll_decisions"]}
        == set(bridge["office_poll_switching"]), "Incomplete public poll decisions")
    for row in selected:
        source = bridge["office_poll_switching"][row["id"]]["joint_question_rows"]
        target = math.fsum(source[a]["prior_choice_share_pct"]
            * source[a]["current_choice_pct_within_prior_choice"][b] / 10000 for a, b in (("D", "R"), ("R", "D")))
        v.close(row["target_fraction"], target, "Published gross-switching arithmetic differs", 1e-12)
        v.require(row["nonvoter_estimate"] is None, "Current-voter poll used to infer missing nonvoters")
    states = sorted({r["state_code"] for r in selected})
    losses = {code: {factor: statistics.fmean(
        (gross[code + "|" + str(factor)] - row["target_fraction"]) ** 2
        for row in selected if row["state_code"] == code)
        for factor in calibration["candidate_factors"]} for code in states}

    def best(training):
        return min(calibration["candidate_factors"], key=lambda factor: (
            statistics.fmean(losses[code][factor] for code in training), factor))

    v.require(calibration["selected_factor"] == best(states), "Gross-only calibration optimum differs")
    folds = {r["heldout_state"]: r for r in calibration["folds"]}
    v.require(set(folds) == set(states), "Incomplete held-out states")
    for code, fold in folds.items():
        training = sorted(set(states) - {code})
        v.require(fold["training_states"] == training
            and fold["selected_factor"] == best(training), "Same-state leakage or changed fold objective")
    v.require(len(calibration["heldout_predictions"]) == len(selected), "Incomplete held-out office targets")
    for row in calibration["heldout_predictions"]:
        prediction = gross[row["state_code"] + "|" + str(folds[row["state_code"]]["selected_factor"])]
        v.close(row["predicted_fraction"], prediction, "Held-out prediction differs")
        v.close(row["predicted_minus_reported_pp"], 100 * (prediction - row["reported_fraction"]),
            "Held-out residual differs")
    v.close(calibration["heldout_mean_absolute_error_pp"], statistics.fmean(
        abs(r["predicted_minus_reported_pp"]) for r in calibration["heldout_predictions"]), "Held-out MAE differs")
    source_comparisons = {row["id"]: row for row in comparisons["rows"]}
    checks = result["unfitted_return_checks"]
    v.require({r["id"] for r in checks} == set(source_comparisons)
        == {r["id"] for r in bridge["return_controls"]}, "Incomplete unfitted return inventory")
    supported = 0
    for row in checks:
        v.require(row["fitted_to_reported_partisan_counts"] is False, "Return fitting claimed")
        source = source_comparisons[row["id"]]["reported_comparison"]
        if source["status"] == "unavailable":
            v.require(row["reported_same_office_change_pp"] is None, "Unsupported historical baseline filled")
            continue
        supported += 1
        v.close(row["reported_same_office_change_pp"], source["reported_change_pp"], "Reported swing changed")
        v.close(row["reported_same_office_change_pp"], math.fsum([
            *row["synthetic_components_pp"].values(), row["prior_baseline_alignment_pp"],
            row["unallocated_return_minus_model_pp"]]), "Both frame differences do not reconcile reported swing")
    historical = result["historical_holdout_validation"]
    with zipfile.ZipFile(historical_archive) as archive:
        native = list(csv.DictReader(io.StringIO(archive.read("complete-state-year-population-pairs.csv").decode())))
    actual = {(r["year"], r["state_code"], r["population_frame"]): r
        for r in historical["complete_historical_source_decisions"]}
    v.require(len(actual) == len(native), "Incomplete historical qualification inventory")
    for source in native:
        row = actual[int(source["year"]), source["reference_state_code"], source["population_frame"]]
        v.require(row["joint_transition_target"] is None and row["observed_staying_home"] is None,
            "Historical marginals were relabeled as joint observations")
        if source["reported_voted_pct"]:
            v.close(row["reported_voted_pct"], float(source["reported_voted_pct"]), "Historical source marginal changed")
        else:
            v.require(row["reported_voted_pct"] is None, "Unknown historical source value replaced by zero")
    v.require(historical["historical_joint_holdout_passed"] is False
        and result["private_joint_cells_reconstructed"] is False
        and result["source_units_are_people"] is False and result["local_allocation"] is False,
        "Qualification changed")
    return dict(status="passed_independent_scalar_verification", checks=v.checks,
        source_states=len(source_targets), final_kernels=len(result["coupling_assumptions"]),
        calibration_grid_kernels=len(calibration["grid_kernels"]), state_seed_cases=len(result["seed_results"]),
        complete_demographic_decisions=len(decisions), state_blocked_poll_targets=len(selected),
        same_office_comparisons=supported, complete_historical_decisions=len(native),
        imports_producer_or_numpy=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("result", "bridge-archive", "demographics", "same-office-comparisons",
            "historical-cps-archive", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.bridge_archive) as archive:
        bridge = json.loads(archive.read("inputs/model-inputs.json"))
    result = json.loads(args.result.read_bytes())
    paths = dict(bridge_archive=args.bridge_archive, disclosed_demographics=args.demographics,
        same_office_comparisons=args.same_office_comparisons, historical_cps_archive=args.historical_cps_archive)
    for name, path in paths.items():
        if result["input_sha256"][name] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("Pinned input hash differs")
    proof = verify(result, bridge, json.loads(args.demographics.read_bytes()),
        json.loads(args.same_office_comparisons.read_bytes()), args.historical_cps_archive)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
