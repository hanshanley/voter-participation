"""NORC-informed demographic House transitions, not identified voter histories."""

import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path
import random
import zipfile


CHOICES = "DRONU"
MECHANISMS = ("switching", "exit", "entry", "other_choice", "unresolved")


def mechanism(before, after):
    if "U" in (before, after):
        return "unresolved"
    if {before, after} == {"D", "R"}:
        return "switching"
    if before in "DR" and after == "N":
        return "exit"
    if before == "N" and after in "DR":
        return "entry"
    return "other_choice"


def accounting(joint, endpoint_rows=None, endpoint_columns=None):
    if len(joint) != 5 or any(len(row) != 5 or any(
            not math.isfinite(v) or v < 0 for v in row) for row in joint):
        raise ValueError("A complete nonnegative DRONU table is required")
    rows = endpoint_rows or [math.fsum(row) for row in joint]
    columns = endpoint_columns or [math.fsum(joint[i][j] for i in range(5)) for j in range(5)]
    v0, v1 = sum(rows[:2]), sum(columns[:2])
    a0, a1 = rows[0]-rows[1], columns[0]-columns[1]
    if min(v0, v1) <= 0:
        raise ValueError("A positive known-D/R denominator is required")
    numerator_factor = 50*(1/v0+1/v1)
    denominator_factor = -50*(a0+a1)/(v0*v1)
    parts = dict.fromkeys(MECHANISMS, 0.0)
    for i, before in enumerate(CHOICES):
        for j, after in enumerate(CHOICES):
            da = (int(after == "D")-int(after == "R")
                -int(before == "D")+int(before == "R"))
            dv = int(after in "DR")-int(before in "DR")
            parts[mechanism(before, after)] += joint[i][j]*(
                numerator_factor*da+denominator_factor*dv)
    total = 100*(a1/v1-a0/v0)
    if endpoint_rows is None and not math.isclose(sum(parts.values()), total, abs_tol=1e-8):
        raise ValueError("Modeled transition mechanisms do not reconcile")
    return dict(contributions_pp=parts, total_change_pp=total,
        previous_margin_pp=100*a0/v0, current_margin_pp=100*a1/v1,
        allocated_change_pp=sum(parts.values()),
        net_participation_pp=parts["entry"]+parts["exit"])


def project(prior, rows, columns):
    q = [[value+1e-13*rows[i]*columns[j] for j, value in enumerate(row)]
        for i, row in enumerate(prior)]
    for iteration in range(10000):
        for i in range(5):
            total = sum(q[i])
            q[i] = [value*rows[i]/total if rows[i] else 0 for value in q[i]]
        for j in range(5):
            total = sum(q[i][j] for i in range(5))
            for i in range(5):
                q[i][j] = q[i][j]*columns[j]/total if columns[j] else 0
        if max(abs(sum(q[i])-rows[i]) for i in range(5)) < 2e-13:
            break
    else:
        raise ValueError("NORC endpoint projection did not converge")
    # The same row/column multipliers must apply to every demographic partition.
    factors = [[q[i][j]/prior[i][j] if prior[i][j] else 0 for j in range(5)] for i in range(5)]
    return q, factors


def adjusted(prior, affinity):
    value = [[v*(affinity if i == j and i < 2 else 1)
        for j, v in enumerate(row)] for i, row in enumerate(prior)]
    total = sum(map(sum, value))
    return [[v/total for v in row] for row in value], total


def targets(counts, frame, source):
    if not all(type(counts.get(k)) is int and counts[k] >= 0 for k in "DRO"):
        raise ValueError("House endpoints require native D/R/Other counts")
    remaining = 1-sum(counts.values())/frame
    if remaining < -1e-12:
        raise ValueError("Frame below native candidate totals")
    unknown = source[4]/sum(source[3:]) if sum(source[3:]) else 0
    return [counts[k]/frame for k in "DRO"]+[remaining*(1-unknown), remaining*unknown]


def predict_without_current_party_totals(prior, previous, current_candidate_volume):
    source_rows = [sum(row) for row in prior]
    source_columns = [sum(row[j] for row in prior) for j in range(5)]
    frame = max(sum(previous.values())/sum(source_rows[:3]),
        max(sum(previous.values()), current_candidate_volume)/(1-1e-6))
    rows = targets(previous, frame, source_rows)
    remaining = 1-current_candidate_volume/frame
    columns = [current_candidate_volume/frame,
        *[remaining*source_columns[k]/sum(source_columns[3:]) for k in (3, 4)]]
    q = [row[:] for row in prior]
    for iteration in range(10000):
        for i in range(5):
            total = sum(q[i])
            q[i] = [v*rows[i]/total if rows[i] else 0 for v in q[i]]
        for indices, target in ((range(3), columns[0]), ((3,), columns[1]), ((4,), columns[2])):
            total = sum(q[i][j] for i in range(5) for j in indices)
            for i in range(5):
                for j in indices:
                    q[i][j] = q[i][j]*target/total if target else 0
        if max(abs(sum(q[i])-rows[i]) for i in range(5)) < 2e-13:
            break
    else:
        raise ValueError("Nonpartisan volume-only projection failed")
    return accounting(q)


def fit_state(state, comparison, frame_scale=1, affinity=1):
    prior, normalizer = adjusted(state["prior_joint"], affinity)
    if comparison["status"] != "reported_source_comparison":
        rows = [sum(row) for row in state["prior_joint"]]
        columns = [sum(row[j] for row in state["prior_joint"]) for j in range(5)]
        joint, factors = project(prior, rows, columns)
        return joint, factors, rows, columns, None, normalizer
    initial_rows = [sum(row) for row in prior]
    initial_columns = [sum(row[j] for row in prior) for j in range(5)]
    frame = max(sum(comparison["current"].values())/sum(initial_columns[:3])*frame_scale,
        max(sum(comparison["previous"].values()), sum(comparison["current"].values()))/(1-1e-6))
    rows = targets(comparison["previous"], frame, initial_rows)
    columns = targets(comparison["current"], frame, initial_columns)
    joint, factors = project(prior, rows, columns)
    return joint, factors, rows, columns, frame, normalizer


def coarse_outcomes(joint):
    total = sum(map(sum, joint))
    previous = sum(sum(row) for row in joint[:2])
    return dict(retaining=(joint[0][0]+joint[1][1])/previous,
        switching=(joint[0][1]+joint[1][0])/previous,
        exit=(joint[0][3]+joint[1][3])/previous,
        other=(joint[0][2]+joint[1][2])/previous,
        unresolved=(joint[0][4]+joint[1][4])/previous,
        current_N=sum(row[3] for row in joint)/total)


def build(priors, accepted, state_codes=None):
    if (priors["contract"] != "participation.norc_house_demographic_priors.v1"
            or priors["raw_records_or_private_fine_cells_exported"] is not False
            or priors["old_synthetic_state_couplings_used"] is not False):
        raise ValueError("Only fitted, public-safe NORC synthetic inputs are allowed")
    originals = {row["state_code"]: row for row in accepted["rows"] if row["office"] == "house"}
    if set(originals) != set(priors["states"]) or len(originals) != 50:
        raise ValueError("All 50 source-state decisions must be retained")
    selected_states = set(priors["states"]) if state_codes is None else set(state_codes)
    if not selected_states or not selected_states <= set(priors["states"]):
        raise ValueError("Select known source states for incremental simulations")
    results, sensitivities, simulations, demographic_seeds = [], [], [], []
    for code, state in sorted(priors["states"].items()):
        if code not in selected_states:
            continue
        comparison = originals[code]["reported_comparison"]
        joint, factors, rows, columns, frame, normalizer = fit_state(state, comparison)
        summary = accounting(joint)
        independent_prediction = None
        if comparison["status"] != "unavailable" and not math.isclose(
                summary["total_change_pp"], comparison["reported_change_pp"], abs_tol=1e-8):
            raise ValueError("NORC fitted shift differs from its native return comparison")
        if comparison["status"] != "unavailable":
            independent_prediction = predict_without_current_party_totals(
                state["prior_joint"], comparison["previous"], sum(comparison["current"].values()))
            independent_prediction.update(current_party_totals_used=False,
                previous_House_counts_and_current_contest_volume_used=True,
                prediction_error_observed_minus_predicted_pp=comparison["current_margin_pp"]
                    -independent_prediction["current_margin_pp"])
        groups = []
        for group in state["groups"]:
            value = {key: group[key] for key in ("dimension", "group", "label", "available")}
            value.update(contributions_pp=None, net_participation_pp=None, total_contribution_pp=None)
            if group["available"]:
                g = group["prior_joint"]
                transformed = [[g[i][j]*factors[i][j]/normalizer
                    for j in range(5)] for i in range(5)]
                allocation = accounting(transformed, rows, columns)
                value.update(contributions_pp=allocation["contributions_pp"],
                    net_participation_pp=allocation["net_participation_pp"],
                    total_contribution_pp=allocation["allocated_change_pp"], joint=transformed,
                    gross_outcomes=coarse_outcomes(transformed) if sum(map(sum, transformed[:2])) else None)
            groups.append(value)
        for dimension in {g["dimension"] for g in groups}:
            part = [g for g in groups if g["dimension"] == dimension and g["available"]]
            for key in MECHANISMS:
                if abs(sum(g["contributions_pp"][key] for g in part)-summary["contributions_pp"][key]) > 1e-7:
                    raise ValueError("Demographic partition does not reconcile to state mechanism")
        cases = []
        for scale in ((.8, 1, 1.2) if frame else (1,)):
            for strength in (.5, 1, 2):
                q, _, _, _, units, _ = fit_state(state, comparison, scale, strength)
                case = dict(state_code=code, frame_scale=scale, affinity=strength,
                    assumed_accounting_frame_units=units, joint=q, **accounting(q))
                cases.append(case)
                sensitivities.append(case)
        ranges = {key: dict(minimum=min(c["contributions_pp"][key] for c in cases),
            maximum=max(c["contributions_pp"][key] for c in cases)) for key in MECHANISMS}
        ranges["net_participation"] = dict(minimum=min(c["net_participation_pp"] for c in cases),
            maximum=max(c["net_participation_pp"] for c in cases))
        for group in groups:
            if not group["available"]:
                group["sensitivity_ranges_pp"] = None
                continue
            allocations = []
            for case in cases:
                q = case["joint"]
                transformed = [[group["joint"][i][j]*q[i][j]/joint[i][j] if joint[i][j] else 0
                    for j in range(5)] for i in range(5)]
                rr = [sum(r) for r in q]
                cc = [sum(q[i][j] for i in range(5)) for j in range(5)]
                allocations.append(accounting(transformed, rr, cc))
            group["sensitivity_ranges_pp"] = {key: dict(
                minimum=min(v["contributions_pp"][key] for v in allocations),
                maximum=max(v["contributions_pp"][key] for v in allocations)) for key in MECHANISMS}
            group["sensitivity_ranges_pp"]["net_participation"] = dict(
                minimum=min(v["net_participation_pp"] for v in allocations),
                maximum=max(v["net_participation_pp"] for v in allocations))
        for seed in (20261101, 20261102, 20261103, 20261104, 20261105):
            rng = random.Random(seed+sum(map(ord, code)))
            sampled = Counter(rng.choices(range(25), weights=sum(joint, []), k=10000))
            q = [[sampled[5*i+j]/10000 for j in range(5)] for i in range(5)]
            value = accounting(q)
            simulations.append(dict(state_code=code, seed=seed, synthetic_agents=10000,
                simulation_not_actual_people=True, margin_sampling_error_pp=value["total_change_pp"]-summary["total_change_pp"],
                **value))
            for dimension in sorted({g["dimension"] for g in groups}):
                selected = [g for g in groups if g["dimension"] == dimension and g["available"]]
                probabilities = [v for g in selected for values in g["joint"] for v in values]
                sampled_groups = Counter(rng.choices(range(len(probabilities)), weights=probabilities, k=10000))
                matrices = [[[sampled_groups[25*k+5*i+j]/10000 for j in range(5)]
                    for i in range(5)] for k in range(len(selected))]
                full = [[sum(m[i][j] for m in matrices) for j in range(5)] for i in range(5)]
                rr = [sum(row) for row in full]
                cc = [sum(full[i][j] for i in range(5)) for j in range(5)]
                grouped = [dict(group=g["group"], **accounting(m, rr, cc))
                    for g, m in zip(selected, matrices)]
                demographic_seeds.append(dict(state_code=code, dimension=dimension, seed=seed,
                    synthetic_agents=10000, separate_nonadditive_demographic_partition=True,
                    groups=grouped, **accounting(full)))
        results.append(dict(state_code=code, id=code+"-house", office="house",
            status="return_anchored_NORC_demographic_model" if frame else "NORC_source_scenario_observed_comparison_unavailable",
            reported_comparison=comparison, estimated_house_baseline_year=2024,
            baseline_bridge="AP2024 President and recalled House22 plus demographics to AP2024 House; applied to CHEP2026",
            point=summary, joint=joint, assumed_accounting_frame_units=frame,
            source_comparison_available=frame is not None, groups=groups,
            before_current_party_conditioning=independent_prediction,
            sensitivity_ranges_pp=ranges, gross_outcomes=coarse_outcomes(joint),
            direct_recalled_2022_house_source_scenario=accounting(state["direct_2022_house_prior_joint"]),
            unknown_source_response_is_not_nonvote=True, measured_staying_home=None,
            actual_first_ever_voting=None, eligibility_deaths_migration=None,
            no_demographic_causal_identification=True))
    return dict(contract="participation.norc_house_demographic_model.v1", rows=results,
        complete_assumption_cases=sensitivities, complete_seed_cases=simulations,
        complete_demographic_seed_cases=demographic_seeds,
        mechanisms=list(MECHANISMS), categories=list(CHOICES), source_input_sha256=priors["source_input_sha256"],
        validation=priors["validation"], assumptions=priors["assumptions"],
        current_party_totals_used_in_source_model_training=False,
        return_constraints_used_only_in_separate_conditional_reconstruction=True,
        preconditioning_margin_MAE_pp=sum(abs(r["before_current_party_conditioning"][
            "prediction_error_observed_minus_predicted_pp"]) for r in results
            if r["before_current_party_conditioning"])/sum(r["source_comparison_available"] for r in results)
            if any(r["source_comparison_available"] for r in results) else None,
        exact_accounting="Symmetric numerator/denominator identity, denominator effects assigned within each transition mechanism",
        model_units_are_people=False, source_likelihood_is_completed_voting=False,
        confidence_intervals=None, local_allocation=False, demographic_dimensions_are_additive_together=False,
        summary=dict(states=len(results), return_anchored=sum(r["source_comparison_available"] for r in results),
            assumption_cases=len(sensitivities), seeds=len(simulations), synthetic_agents=len(simulations)*10000,
            demographic_partition_seed_cases=len(demographic_seeds),
            demographic_partition_agent_draws=len(demographic_seeds)*10000,
            complete_group_decisions=sum(len(r["groups"]) for r in results)))


def result_files(result):
    def csv_bytes(rows):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted({k for row in rows for k in row}), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode()
    decisions, groups, flows = [], [], []
    for row in result["rows"]:
        decisions.append(dict(state_code=row["state_code"], status=row["status"],
            reported_comparison_available=row["source_comparison_available"],
            previous_margin_pp=row["point"]["previous_margin_pp"],
            current_margin_pp=row["point"]["current_margin_pp"],
            total_change_pp=row["point"]["total_change_pp"],
            net_participation_pp=row["point"]["net_participation_pp"], **row["point"]["contributions_pp"]))
        for g in row["groups"]:
            groups.append(dict(state_code=row["state_code"], dimension=g["dimension"], group=g["group"],
                label=g["label"], available=g["available"], total_contribution_pp=g["total_contribution_pp"],
                net_participation_pp=g["net_participation_pp"],
                **(g["contributions_pp"] or dict.fromkeys(MECHANISMS))))
        for i, before in enumerate(CHOICES):
            for j, after in enumerate(CHOICES):
                flows.append(dict(state_code=row["state_code"], previous_house_category=before,
                    current_house_category=after, modeled_fraction=row["joint"][i][j],
                    observed_individual_history=False))
    viewer = {k: v for k, v in result.items() if not k.startswith("complete_")}
    return {"complete-result.json": encoded(result), "viewer-data.json": encoded(viewer),
        "complete-state-mechanisms.csv": csv_bytes(decisions), "complete-demographic-contributions.csv": csv_bytes(groups),
        "complete-modeled-flows.csv": csv_bytes(flows),
        "complete-assumption-cases.json": encoded(result["complete_assumption_cases"]),
        "complete-seed-cases.json": encoded(result["complete_seed_cases"]),
        "complete-demographic-seed-cases.json": encoded(result["complete_demographic_seed_cases"])}


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("priors", "accepted-science", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh scientific output")
    with zipfile.ZipFile(args.accepted_science) as archive:
        accepted = json.loads(archive.read("results/complete-result.json"))
    result = build(json.loads(args.priors.read_bytes()), accepted)
    args.output.mkdir(parents=True)
    for name, body in result_files(result).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"]))
