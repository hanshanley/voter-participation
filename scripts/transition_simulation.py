"""Synthetic source-frame flows, not reconstructed respondents or causal effects."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import statistics
import zipfile

import numpy as np

if __package__:
    from .civic_estimates import component
    from .transition_validation import historical_validation_decisions, reconcile_return_checks
else:
    from civic_estimates import component
    from transition_validation import historical_validation_decisions, reconcile_return_checks


CHOICES = tuple("DRONU")
CELLS = tuple((prior, current) for prior in CHOICES for current in CHOICES)
TERMS = ("switching", "modeled_nonparticipation", "no_prior_contest_vote_entry",
    "other_choice", "unresolved")
FEATURES = ("m24", "t24", "m26", "t26", "modeled_nonvoter_weight", *TERMS)
SOURCE_SHA = "496a5b57fbc435210bdf78e2c1c3717879c0689c74081bee830d121b548c792f"


def score(choice):
    return int(choice == "D") - int(choice == "R")


def features(prior, current):
    kind, change = component(prior, current)
    return [score(prior), int(prior in "DR"), score(current), int(current in "DR"),
        int(current == "N"), *[change if term == kind else 0 for term in TERMS]]


MATRIX = np.asarray([features(*cell) for cell in CELLS], dtype=float).T


def multiply(matrix, value):
    # Direct small contractions keep numerical warnings visible and avoid BLAS products.
    expression = "ij,j->i" if value.ndim == 1 else "ij,jk->ik"
    result = np.einsum(expression, matrix, value, optimize=False)
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite synthetic-model contraction")
    return result


@dataclass(frozen=True)
class SimulationSpec:
    agent_budget: int = 1_000_000
    minimum_agents_per_state: int = 2_000
    seeds: tuple = (202601, 202602, 202603, 202604, 202605)
    persistence_factors: tuple = (1.0, 4.0, 16.0)
    calibration_grid: tuple = tuple(2 ** (step / 4) for step in range(-4, 33))


def allocate_agents(weights, budget, minimum):
    if not weights or budget < len(weights) * minimum or minimum < 1:
        raise ValueError("The fixed agent budget must support every source-state floor")
    if any(not math.isfinite(value) or value <= 0 for value in weights.values()):
        raise ValueError("Source weights must be positive finite units, not missing populations")
    codes = sorted(weights)
    remaining = budget - len(codes) * minimum
    total = sum(weights.values())
    quotas = {code: remaining * weights[code] / total for code in codes}
    allocations = {code: minimum + math.floor(quotas[code]) for code in codes}
    left = budget - sum(allocations.values())
    for code in sorted(codes, key=lambda code: (-(quotas[code] % 1), code))[:left]:
        allocations[code] += 1
    if sum(allocations.values()) != budget:
        raise AssertionError("Agent budget was not conserved")
    return allocations


def source_targets(moment, participation):
    weight = float(participation["modeled_voter_weight"]) + float(participation["modeled_nonvoter_weight"])
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError("Invalid source-frame mass")
    targets = np.asarray([float(participation[name] if name == "modeled_nonvoter_weight"
        else moment[name]) / weight for name in FEATURES])
    if not np.isfinite(targets).all() or min(targets[1], targets[3]) <= 0:
        raise ValueError("Unknown or absent major-party denominator")
    if abs(targets[2] - targets[0] - sum(targets[5:])) > 1e-11:
        raise ValueError("Released source-frame accounting differs")
    return targets, weight


def fit_coupling(targets, persistence_factor=1.0, tolerance=2e-10, max_iterations=250):
    """Choose one relative-entropy coupling; public moments do not identify it."""
    targets = np.asarray(targets, dtype=float)
    if targets.shape != (len(FEATURES),) or not np.isfinite(targets).all():
        raise ValueError("Complete finite public moments are required")
    if not math.isfinite(persistence_factor) or persistence_factor <= 0:
        raise ValueError("Invalid declared persistence assumption")
    support = np.ones(len(CELLS), dtype=bool)
    for row, target in zip(MATRIX, targets):
        if target < row.min() - tolerance or target > row.max() + tolerance:
            raise ValueError("Moment lies outside its feasible synthetic support")
        if abs(target - row.min()) < tolerance:
            support &= np.abs(row - target) < tolerance
        elif abs(target - row.max()) < tolerance:
            support &= np.abs(row - target) < tolerance
    if not support.any():
        raise ValueError("No feasible synthetic support")
    matrix = MATRIX[:, support]
    centered = matrix - matrix[:, :1]
    basis, singular, _ = np.linalg.svd(centered, full_matrices=False)
    rank = int(np.sum(singular > 1e-11))
    basis = basis[:, :rank]
    reduced, target = multiply(basis.T, matrix), multiply(basis.T, targets)
    log_prior = np.asarray([math.log(persistence_factor) if prior == current and prior in "DR"
        else 0.0 for prior, current in CELLS])[support]
    theta = np.zeros(rank)

    def evaluate(parameters):
        logits = log_prior + multiply(reduced.T, parameters)
        maximum = float(logits.max())
        normalizer = maximum + math.log(float(np.exp(logits - maximum).sum()))
        probabilities = np.exp(logits - normalizer)
        objective = normalizer - math.fsum(float(a*b) for a, b in zip(parameters, target))
        return probabilities, objective

    probabilities, objective = evaluate(theta)
    for iteration in range(max_iterations):
        mean = multiply(reduced, probabilities)
        gradient = mean - target
        if np.max(np.abs(multiply(matrix, probabilities) - targets)) <= tolerance:
            result = np.zeros(len(CELLS))
            result[support] = probabilities
            return result, dict(iterations=iteration,
                maximum_moment_residual=float(np.max(np.abs(multiply(MATRIX, result) - targets))),
                persistence_factor=persistence_factor, source_joint_cells_reconstructed=False)
        hessian = multiply(reduced * probabilities, reduced.T) - np.outer(mean, mean)
        eigenvalues, eigenvectors = np.linalg.eigh(hessian)
        active = eigenvalues > max(float(eigenvalues.max()), 1e-30) * 1e-13
        vectors = eigenvectors[:, active]
        direction = multiply(vectors, multiply(vectors.T, gradient) / eigenvalues[active])
        step = 1.0
        descent = math.fsum(float(a*b) for a, b in zip(gradient, direction))
        while step > 1e-12:
            candidate, value = evaluate(theta - step * direction)
            if value <= objective - 1e-4 * step * descent + 1e-14:
                theta -= step * direction
                probabilities, objective = candidate, value
                break
            step *= 0.5
        else:
            break
    raise ValueError("Public moments did not converge to a feasible declared coupling")


def condition_participation(probabilities, nonvoter_fraction):
    if not math.isfinite(nonvoter_fraction) or not 0 <= nonvoter_fraction <= 1:
        raise ValueError("An unavailable demographic probability is not zero")
    mask = np.asarray([current == "N" for _, current in CELLS])
    original = float(probabilities[mask].sum())
    if not 0 < original < 1:
        raise ValueError("Both model classes need source support")
    result = probabilities.copy()
    result[mask] *= nonvoter_fraction / original
    result[~mask] *= (1 - nonvoter_fraction) / (1 - original)
    return result


def summarize(probabilities):
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.shape != (len(CELLS),) or np.any(probabilities < 0) or not math.isclose(
            float(probabilities.sum()), 1, abs_tol=1e-10):
        raise ValueError("A full normalized synthetic distribution is required")
    moment = dict(zip(FEATURES, multiply(MATRIX, probabilities)))
    t0, t1 = moment["t24"], moment["t26"]
    if min(t0, t1) <= 0:
        return dict(status="no_simulated_major_party_denominator", components_pp=None)
    scale = 50 * (1/t0 + 1/t1)
    parts = {term: float(scale * moment[term]) for term in TERMS}
    parts["denominator"] = float(50 * (moment["m24"] + moment["m26"]) * (1/t1 - 1/t0))
    delta = float(100 * (moment["m26"]/t1 - moment["m24"]/t0))
    if not math.isclose(sum(parts.values()), delta, abs_tol=1e-9):
        raise AssertionError("Simulated normalized-margin accounting failed")
    retained = sum(probabilities[i] for i, (prior, current) in enumerate(CELLS)
        if prior == current and prior in "DR")
    switches = sum(probabilities[i] for i, (prior, current) in enumerate(CELLS)
        if {prior, current} == {"D", "R"})
    nonparticipating = sum(probabilities[i] for i, (prior, current) in enumerate(CELLS)
        if prior in "DR" and current == "N")
    other = sum(probabilities[i] for i, (prior, current) in enumerate(CELLS)
        if prior in "DR" and current == "O")
    unresolved = sum(probabilities[i] for i, (prior, current) in enumerate(CELLS)
        if prior in "DR" and current == "U")
    entry = sum(probabilities[i] for i, (prior, current) in enumerate(CELLS)
        if prior == "N" and current in "DR")
    return dict(status="conditional_synthetic_source_frame_not_people",
        prior_recalled_margin_pp=float(100 * moment["m24"]/t0),
        modeled_current_margin_pp=float(100 * moment["m26"]/t1),
        source_frame_change_pp=delta, components_pp=parts,
        synthetic_retaining_share_of_recalled_major_party=float(retained/t0),
        synthetic_switching_share_of_recalled_major_party=float(switches/t0),
        synthetic_nonparticipation_share_of_recalled_major_party=float(nonparticipating/t0),
        synthetic_other_choice_share_of_recalled_major_party=float(other/t0),
        synthetic_unresolved_share_of_recalled_major_party=float(unresolved/t0),
        synthetic_no_prior_contest_vote_entry_share_of_current_major_party=float(entry/t1),
        synthetic_gross_switching_share_of_modeled_current_voters=float(
            switches / (1 - moment["modeled_nonvoter_weight"])),
        modeled_nonvoter_share=float(moment["modeled_nonvoter_weight"]),
        identified_individual_histories=False, measured_staying_home=None)


def poll_switching_targets(polls, source_states):
    decisions = []
    for identity, row in sorted(polls.items()):
        decision = dict(id=identity, state_code=row["state_code"], office=row["office"],
            source_url=row["source_url"], source_sha256=row["source_sha256"],
            source_timestamp=row["source_timestamp"], target_fraction=None,
            rounding_only_bounds=None, nonvoter_estimate=None)
        if row["state_code"] not in source_states:
            decisions.append(dict(decision, disposition="held_source_state_unavailable"))
            continue
        if row["status"] != "published_joint_question_reviewed" or row[
                "composition_quality"] != "within_four_row_rounding_tolerance":
            decisions.append(dict(decision, disposition="held_unqualified_published_table"))
            continue
        values = [(row["joint_question_rows"][prior]["prior_choice_share_pct"],
            row["joint_question_rows"][prior]["current_choice_pct_within_prior_choice"][current])
            for prior, current in (("D", "R"), ("R", "D"))]
        if any(value is None for pair in values for value in pair):
            decisions.append(dict(decision, disposition="held_native_switching_cell_unavailable"))
            continue
        if any(not isinstance(value, (int, float)) or not math.isfinite(value)
                or not 0 <= value <= 100 for pair in values for value in pair):
            raise ValueError("Invalid disclosed current-voter switching percentage")
        gross = math.fsum(prior * current / 10000 for prior, current in values)
        published = row["arithmetic_from_rounded_percentages_per_100_current_group_voters"][
            "gross_reported_major_party_switchers"] / 100
        if not math.isclose(gross, published, abs_tol=1e-12):
            raise ValueError("Native gross switching differs from reviewed source arithmetic")
        bounds = [math.fsum(max(0, prior - .5) * max(0, current - .5) / 10000
            for prior, current in values), math.fsum(min(100, prior + .5)
            * min(100, current + .5) / 10000 for prior, current in values)]
        decisions.append(dict(decision, target_fraction=gross, rounding_only_bounds=bounds,
            disposition="published_gross_switching_current_voters_only",
            population_transport_validated=False, design_confidence_interval=None))
    return decisions


def monte_carlo_summary(cases):
    if not cases or any(row["status"] != "conditional_synthetic_source_frame_not_people" for row in cases):
        return dict(status="held_missing_seed_or_major_party_denominator")
    fields = [name for name, value in cases[0].items() if isinstance(value, (int, float))
        and (name.startswith("synthetic_") or name in ("source_frame_change_pp", "modeled_current_margin_pp"))]
    return dict(status="finite_draw_variation_not_source_sampling_uncertainty",
        seeds=len(cases), metrics={name: dict(
            mean=statistics.fmean(row[name] for row in cases),
            standard_deviation=statistics.stdev(row[name] for row in cases) if len(cases) > 1 else None,
            minimum=min(row[name] for row in cases), maximum=max(row[name] for row in cases))
            for name in fields})


def calibrate_persistence(targets, polls, candidate_factors):
    """Fit only gross switching; block every same-state office table in validation."""
    decisions = poll_switching_targets(polls, targets)
    selected = [row for row in decisions if row["target_fraction"] is not None]
    states = sorted({row["state_code"] for row in selected})
    if len(states) < 3 or not candidate_factors:
        return dict(status="held_insufficient_source_states", complete_poll_decisions=decisions,
            selected_factor=None, grid_kernels={}, heldout_predictions=[])
    factors = sorted(set(candidate_factors))
    grid, losses = {}, {}
    for code in states:
        rows = [row for row in selected if row["state_code"] == code]
        losses[code] = {}
        for factor in factors:
            probability, diagnostic = fit_coupling(targets[code], factor)
            analytic = summarize(probability)
            gross = analytic["synthetic_gross_switching_share_of_modeled_current_voters"]
            grid[code + "|" + str(factor)] = dict(
                probabilities=probability.tolist(), fit=diagnostic, analytic=analytic)
            losses[code][factor] = math.fsum(
                (gross - row["target_fraction"]) ** 2 for row in rows) / len(rows)

    def select(training_states):
        return min(factors, key=lambda factor: (
            math.fsum(losses[code][factor] for code in training_states) / len(training_states), factor))

    heldout, folds = [], []
    for code in states:
        training = [state for state in states if state != code]
        factor = select(training)
        folds.append(dict(heldout_state=code, training_states=training, selected_factor=factor,
            training_state_balanced_mse=math.fsum(losses[state][factor] for state in training) / len(training)))
        prediction = grid[code + "|" + str(factor)]["analytic"][
            "synthetic_gross_switching_share_of_modeled_current_voters"]
        for row in selected:
            if row["state_code"] == code:
                heldout.append(dict(id=row["id"], state_code=code, office=row["office"],
                    selected_factor=factor, predicted_fraction=prediction,
                    reported_fraction=row["target_fraction"],
                    predicted_minus_reported_pp=100 * (prediction - row["target_fraction"]),
                    rounding_only_bounds=row["rounding_only_bounds"]))
    factor = select(states)
    baselines = {str(factor): 100 * math.fsum(abs(grid[row["state_code"] + "|" + str(factor)][
        "analytic"]["synthetic_gross_switching_share_of_modeled_current_voters"] - row["target_fraction"])
        for row in selected) / len(selected) for factor in (1.0, 4.0, 16.0) if factor in factors}
    return dict(status="cross_source_current_voter_benchmark_not_population_validation",
        selected_factor=factor, selected_at_grid_boundary=factor in (factors[0], factors[-1]),
        complete_poll_decisions=decisions, grid_kernels=grid, candidate_factors=factors,
        folds=folds, heldout_predictions=heldout,
        heldout_mean_absolute_error_pp=math.fsum(abs(row["predicted_minus_reported_pp"])
            for row in heldout) / len(heldout),
        fixed_assumption_mean_absolute_error_pp=baselines,
        objective="state_balanced_squared_error_of_gross_switching_fraction",
        partisan_direction_used_for_calibration=False, reported_returns_used_for_calibration=False,
        current_voter_only=True, observed_nonparticipation=None,
        house_model_transported_to_senate_governor=True, house_poll_validation_available=False,
        population_transport_validated=False, survey_sample_independence_certified=False,
        historical_validation=False, design_confidence_intervals=None)


def load_inputs(bridge_archive, groups_file):
    with zipfile.ZipFile(bridge_archive) as source:
        bridge = json.loads(source.read("inputs/model-inputs.json"))
    groups = json.loads(groups_file.read_bytes())
    if bridge["sources"]["norc_native_reduction"]["source_sha256"] != SOURCE_SHA \
            or groups["original_csv_sha256"] != SOURCE_SHA \
            or not groups["qualification"]["no_private_fine_cells_raw_records_or_candidate_choice_tables"]:
        raise ValueError("Do not mix unqualified source frames or select private cells")
    return bridge, groups


def run(bridge, groups, spec, comparisons=None, historical_archive=None):
    weights, targets = {}, {}
    for key, moment in bridge["state_moments"].items():
        code = moment["scope"]
        if key != code + "|2024" or moment["dimension"] != "overall" or code == "DC":
            raise ValueError("Use only the released whole-state frame")
        targets[code], weights[code] = source_targets(moment, bridge["state_participation"][code])
    allocations = allocate_agents(weights, spec.agent_budget, spec.minimum_agents_per_state)
    calibration = calibrate_persistence(targets, bridge["office_poll_switching"], spec.calibration_grid)
    factors = set(spec.persistence_factors)
    if calibration["selected_factor"] is not None:
        factors.update(calibration["selected_factor"] * change for change in (.5, 1, 2))
    factors = sorted(factors)
    estimates, kernels, decisions, checks = [], {}, [], []
    for factor in factors:
        for code in sorted(targets):
            identity = code + "|" + str(factor)
            existing = calibration["grid_kernels"].get(identity)
            if existing is None:
                probability, diagnostic = fit_coupling(targets[code], factor)
            else:
                probability, diagnostic = np.asarray(existing["probabilities"]), existing["fit"]
            kernels[identity] = dict(probabilities=probability.tolist(), fit=diagnostic,
                analytic=summarize(probability), agents=allocations[code])
            seed_cases = []
            for seed in spec.seeds:
                state_seed = np.random.SeedSequence([seed, int.from_bytes(code.encode(), "little"), int(factor * 1000)])
                generator = np.random.default_rng(state_seed)
                counts = generator.multinomial(allocations[code], probability)
                seed_cases.append(dict(state_code=code, persistence_factor=factor, seed=seed,
                    agents=allocations[code], simulated_cells=counts.tolist(),
                    **summarize(counts / allocations[code])))
            estimates.extend(seed_cases)
            kernels[identity]["monte_carlo"] = monte_carlo_summary(seed_cases)
    for row in groups["groups"]:
        decision = {key: row[key] for key in ("state_code", "dimension", "group", "label", "disposition")}
        if row["disposition"] != "selected_broad_source_model":
            decisions.append(dict(decision, conditional_simulation=None))
            continue
        code = row["state_code"]
        if code not in targets:
            raise ValueError("Selected demographic has no source-state frame")
        total, nonvoter = float(row["weight"]), float(row["modeled_nonvoter_weight"])
        if not math.isfinite(total) or total <= 0 or row["n"] < 100:
            raise ValueError("Unreleased or unsupported demographic weight")
        cases = []
        for factor in factors:
            base = np.asarray(kernels[code + "|" + str(factor)]["probabilities"])
            conditioned = condition_participation(base, nonvoter / total)
            group_seed = int.from_bytes(hashlib.sha256(json.dumps(
                [code, row["dimension"], row["group"]], separators=(",", ":")).encode()).digest()[:8], "little")
            seeds = []
            for seed in spec.seeds:
                generator = np.random.default_rng(np.random.SeedSequence(
                    [seed, group_seed, int(factor * 1000)]))
                counts = generator.multinomial(allocations[code], conditioned)
                seeds.append(dict(seed=seed, diagnostic_draws=allocations[code],
                    synthetic_cells=counts.tolist(), **summarize(counts / allocations[code])))
            cases.append(dict(persistence_factor=factor, analytic=summarize(conditioned),
                seed_results=seeds, monte_carlo=monte_carlo_summary(seeds)))
        decisions.append(dict(decision, conditional_simulation=cases,
            demographic_party_association_identified=False, source_weight_units_not_people=True,
            partial_demographic_partitions_not_completed=True,
            conditional_group_draws_are_nonadditive_diagnostics=True,
            synthetic_cells_are_not_released_private_source_cells=True))
    point_factor = calibration["selected_factor"] or spec.persistence_factors[0]
    for control in bridge["return_controls"]:
        code = control["state_code"]
        if code not in targets:
            continue
        d, r = (int(control["current"][party]) for party in ("D", "R"))
        actual = 100 * (d-r)/(d+r)
        expected = kernels[code + "|" + str(point_factor)]["analytic"]["modeled_current_margin_pp"]
        checks.append(dict(id=control["id"], office=control["office"], state_code=code,
            reported_current_margin_pp=actual, simulated_source_expected_margin_pp=expected,
            unallocated_return_minus_model_pp=actual-expected,
            house_model_transported_to_other_office=control["office"] != "house",
            fitted_to_reported_partisan_counts=False,
            independent_population_validation=False, source_scope=control["source_scope"]))
    analytic_by_state = {code: kernels[code + "|" + str(point_factor)]["analytic"] for code in targets}
    if comparisons is not None:
        checks = reconcile_return_checks(checks, comparisons, analytic_by_state)
    historical = (historical_validation_decisions(historical_archive) if historical_archive else
        dict(status="held_historical_source_packet_not_supplied", historical_joint_holdout_passed=False))
    envelopes = {}
    if calibration["selected_factor"] is not None:
        for code in targets:
            scenarios = [kernels[code + "|" + str(point_factor * change)]["analytic"]
                for change in (.5, 1, 2)]
            envelopes[code] = {name: dict(minimum=min(row[name] for row in scenarios),
                maximum=max(row[name] for row in scenarios), point=analytic_by_state[code][name])
                for name in scenarios[0] if name.startswith("synthetic_")}
    return dict(status="conditional_source_frame_scenarios_not_population_validated",
        agent_spec=vars(spec), allocations=allocations, cells=CELLS,
        effective_persistence_factors=factors, persistence_calibration=calibration,
        calibrated_half_double_assumption_envelopes=envelopes,
        coupling_assumptions=kernels, seed_results=estimates, complete_demographic_decisions=decisions,
        unfitted_return_checks=checks, historical_holdout_validation=historical,
        source_units_are_people=False, source_nonvoter_is_administrative_staying_home=False,
        private_joint_cells_reconstructed=False, local_allocation=False,
        uncertainty=dict(monte_carlo="finite draw variation only, not a population confidence interval",
            persistence_envelope="half/double calibrated strength scenarios, not a confidence interval",
            source_sampling_design=None, cross_source_population_transport=None,
            demographic_party_association="assumed conditional structure, not identified"),
        eligibility_death_migration=None, design_confidence_intervals=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-archive", type=Path, required=True)
    parser.add_argument("--demographics", type=Path, required=True)
    parser.add_argument("--same-office-comparisons", type=Path)
    parser.add_argument("--historical-cps-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refuse to replace an immutable numerical version")
    bridge, groups = load_inputs(args.bridge_archive, args.demographics)
    result = run(bridge, groups, SimulationSpec(),
        json.loads(args.same_office_comparisons.read_bytes()) if args.same_office_comparisons else None,
        args.historical_cps_archive)
    inputs = [("bridge_archive", args.bridge_archive), ("disclosed_demographics", args.demographics),
        ("same_office_comparisons", args.same_office_comparisons),
        ("historical_cps_archive", args.historical_cps_archive)]
    result["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in inputs if path is not None}
    result["numerical_library_version"] = np.__version__
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    print(json.dumps(dict(status=result["status"], source_states=len(result["allocations"]),
        kernels=len(result["coupling_assumptions"]), seeds=len(result["seed_results"]),
        demographic_decisions=len(result["complete_demographic_decisions"]),
        unfitted_return_checks=len(result["unfitted_return_checks"]))))


if __name__ == "__main__":
    main()
