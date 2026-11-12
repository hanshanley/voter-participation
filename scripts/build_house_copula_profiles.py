"""Build disclosed 2026 association stresses without refitting source marginals."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import compare_house_model_families as families
from scripts import norc_house_model as simulation
from scripts.transport_house_copula import stress_priors


FILES = ("accepted_ridge_multinomial-priors.json", "histogram_gradient_boosting-priors.json",
         "extra_randomized_trees-priors.json")


def pin(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def combine(baseline, changed, codes):
    result = copy.deepcopy(baseline)
    if not codes:
        return result
    for field in ("rows", "complete_assumption_cases", "complete_seed_cases", "complete_demographic_seed_cases"):
        old = [row for row in baseline[field] if row["state_code"] not in codes]
        result[field] = sorted(old+changed[field], key=lambda row: row["state_code"])
    denominator = sum(row["source_comparison_available"] for row in result["rows"])
    result["preconditioning_margin_MAE_pp"] = math.fsum(
        abs(row["before_current_party_conditioning"]["prediction_error_observed_minus_predicted_pp"])
        for row in result["rows"] if row["source_comparison_available"])/denominator if denominator else None
    result["summary"] = dict(baseline["summary"])
    return result


def check_prepared_projection(original, prepared, decisions, theta, profile):
    flags = prepared.get("structural_association_stress", {})
    if (flags.get("profile") != profile or flags.get("requested_theta") != theta
            or flags.get("current_return_targets_used") is not False
            or set(original["states"]) != set(prepared["states"]) or set(decisions) != set(original["states"])):
        raise ValueError("Prepared projection changed its source-only binding")

    def margins(table):
        return [math.fsum(row) for row in table]+[math.fsum(row[j] for row in table) for j in range(5)]

    for code, old in original["states"].items():
        new, decision = prepared["states"][code], decisions[code]
        if (decision["requested_theta"] != theta or decision["feasibility_exponent"] not in (0, .125, .25, .5, 1)
                or not math.isclose(decision["effective_theta"], theta**decision["feasibility_exponent"], abs_tol=1e-12)
                or new["direct_2022_house_prior_joint"] != old["direct_2022_house_prior_joint"]
                or len(new["groups"]) != len(old["groups"])):
            raise ValueError("Prepared strength or direct scenario differs")
        log_ratio = [[math.log(new["prior_joint"][i][j]/old["prior_joint"][i][j])
                      -(math.log(decision["effective_theta"]) if i == j and i < 2 else 0)
                      for j in range(5)] for i in range(5)]
        if any(abs(log_ratio[i][j]-log_ratio[i][-1]-log_ratio[-1][j]+log_ratio[-1][-1]) > 1e-8
               for i in range(5) for j in range(5)):
            raise ValueError("Prepared state joint violates its association dual certificate")
        for before, after in [(old, new), *zip(old["groups"], new["groups"])]:
            if before is not old and any(before[key] != after[key] for key in ("dimension", "group", "label", "available")):
                raise ValueError("Prepared projection changed its disclosure mask")
            if before.get("available", True):
                if (any(not math.isfinite(value) or value < 0 for row in after["prior_joint"] for value in row)
                        or any(abs(a-b) > 1e-10 for a, b in zip(margins(before["prior_joint"]), margins(after["prior_joint"])))):
                    raise ValueError("Prepared projection changed a source year margin")
            elif before["prior_joint"] != after["prior_joint"]:
                raise ValueError("Prepared projection filled a held source group")
        for dimension in {group["dimension"] for group in new["groups"]}:
            tables = [group["prior_joint"] for group in new["groups"] if group["dimension"] == dimension and group["available"]]
            if any(abs(math.fsum(table[i][j] for table in tables)-new["prior_joint"][i][j]) > 1e-10
                   for i in range(5) for j in range(5)):
                raise ValueError("Prepared demographic partition does not reproduce its state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-summary", "priors", "baseline-results", "baseline-viewer", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--prepared-projections", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete association-profile directory")
    source = json.loads(args.source_summary.read_bytes())
    if not source["conditional_transport_gate_passed"]:
        raise ValueError("The prespecified historical-source gate did not pass; do not promote a positive stress")
    if source["population_or2026_parameter_validation"] or source["default_accepted_model_changed"]:
        raise ValueError("Historical association is not a validated2026parameter/default replacement")
    original_viewer = json.loads(args.baseline_viewer.read_bytes())
    manifest = json.loads((args.priors/"manifest.json").read_bytes())
    original_priors, transformed, projection_decisions = {}, {}, {}
    args.output.mkdir(parents=True)
    for family, filename in zip(families.FAMILIES, FILES):
        path = args.priors/filename
        if pin(path) != manifest[filename]["sha256"]:
            raise ValueError("Accepted public synthetic source prior changed")
        original_priors[family] = json.loads(path.read_bytes())
    # Freeze all source-only projections before reading any current return comparison.
    for profile, theta in source["historical_profile_requested_thetas"].items():
        transformed[profile], projection_decisions[profile] = {}, {}
        for family in families.FAMILIES:
            print(json.dumps(dict(profile=profile, family=family, stage="source_margin_constrained_projection")), flush=True)
            if args.prepared_projections:
                prepared_directory = args.prepared_projections/profile/family
                prior = json.loads((prepared_directory/"synthetic-priors.json").read_bytes())
                decisions = json.loads((prepared_directory/"source-projection-decisions.json").read_bytes())
                check_prepared_projection(original_priors[family], prior, decisions, theta, profile)
            else:
                prior, decisions = stress_priors(original_priors[family], theta, profile)
            directory = args.output/profile/family
            directory.mkdir(parents=True)
            (directory/"synthetic-priors.json").write_bytes(simulation.encoded(prior))
            (directory/"source-projection-decisions.json").write_bytes(families.encoded(decisions))
            transformed[profile][family] = prior
            projection_decisions[profile][family] = decisions
    results = {}
    comparison_rows = []
    baseline = {family: json.loads((args.baseline_results/family/"complete-result.json").read_bytes())
                for family in families.FAMILIES}
    for row in families.state_comparisons(baseline):
        comparison_rows.append(dict(profile="original", requested_theta=1., effective_theta=1.,
                                    source_feasibility_exponent=1., **row))
    accepted = dict(rows=[dict(office="house", state_code=row["state_code"], reported_comparison=row["reported_comparison"])
                         for row in baseline[families.BASELINE]["rows"]])
    for profile, priors in transformed.items():
        results[profile] = {}
        for family, prior in priors.items():
            decisions = projection_decisions[profile][family]
            changed_codes = {code for code, decision in decisions.items() if decision["changed"]}
            print(json.dumps(dict(profile=profile, family=family, changed_states=len(changed_codes),
                                  unchanged_states_reused=50-len(changed_codes), stage="new_stress_simulation")), flush=True)
            changed = simulation.build(prior, accepted, state_codes=changed_codes) if changed_codes else None
            result = combine(baseline[family], changed, changed_codes)
            result["historical_association_stress"] = dict(profile=profile,
                requested_theta=source["historical_profile_requested_thetas"][profile],
                state_parameters={code: {key: value for key, value in decision.items() if key != "attempts"}
                                  for code, decision in decisions.items()},
                source_summary_sha256=pin(args.source_summary),
                unvalidated_source_cycle_predictor_and_aggregation_transport=True,
                fitted_source_state_and_group_year_marginals_preserved=True,
                current_return_targets_used_to_select_association=False, default_accepted_model_changed=False)
            directory = args.output/profile/family
            for name, body in simulation.result_files(result).items():
                (directory/name).write_bytes(body)
            results[profile][family] = result
        for row in families.state_comparisons(results[profile]):
            decision = projection_decisions[profile][row["family"]][row["state_code"]]
            comparison_rows.append(dict(profile=profile, requested_theta=decision["requested_theta"],
                effective_theta=decision["effective_theta"], source_feasibility_exponent=decision["feasibility_exponent"], **row))
        viewer = copy.deepcopy(original_viewer)
        viewer["families"] = {family: {key: value for key, value in result.items() if not key.startswith("complete_")}
                              for family, result in results[profile].items()}
        viewer["state_comparisons"] = families.state_comparisons(results[profile])
        viewer["family_dispersion"] = families.dispersion(results[profile])
        viewer["summary"].update(
            margin_MAE_pp={family: result["preconditioning_margin_MAE_pp"] for family, result in results[profile].items()},
            Democratic_two_party_share_MAE_pp={family: result["preconditioning_margin_MAE_pp"]/2
                                               for family, result in results[profile].items()})
        viewer["association_profile"] = dict(profile=profile,
            requested_theta=source["historical_profile_requested_thetas"][profile],
            source_primary_history_theta_median=source["source_primary_history_theta_median"],
            historical_parameter_not_validated_for2026=True, applied_postaggregation_not_per_case=True,
            demographic_partition_year_margins_preserved=True, source_only_feasibility_backoff=True,
            default_accepted_model_changed=False)
        (args.output/f"viewer-{profile}.json").write_bytes(simulation.encoded(viewer))
    (args.output/"complete-profile-family-state-comparisons.csv").write_bytes(families.csv_bytes(comparison_rows))
    summary = dict(contract="participation.house_copula_profiles.v1", profiles=["original", *transformed],
        families=list(families.FAMILIES), states_per_family=50, qualified_comparisons_per_family=48,
        complete_profile_family_state_decisions=len(comparison_rows), accepted_marginal_fits_repeated=False,
        source_row_group_year_margins_preserved=True, profile_family_scenarios=6,
        all_original_outputs_and_default_unchanged=True, current_return_errors_used_for_selection=False,
        actual_staying_home_firstever_eligibility_death_migration=None,
        unvalidated_transport=True, independent_population_validation=False,
        native_respondents_and_private_fine_cells_exported=False,
        projection_decisions={profile: {family: dict(
            changed_states=sum(value["changed"] for value in decisions.values()),
            zero_effective_states=sum(not value["changed"] for value in decisions.values()),
            backed_off_states=sum(value["feasibility_exponent"] < 1 for value in decisions.values()))
            for family, decisions in values.items()} for profile, values in projection_decisions.items()})
    (args.output/"profile-summary.json").write_bytes(families.encoded(summary))
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
