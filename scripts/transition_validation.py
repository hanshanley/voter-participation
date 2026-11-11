"""Source qualifications and unfitted return accounting for synthetic flows."""

import csv
import io
import math
import zipfile


def historical_validation_decisions(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read(
            "complete-state-year-population-pairs.csv").decode())))
    seen, decisions = set(), []
    for row in rows:
        identity = (int(row["year"]), row["reference_state_code"], row["population_frame"])
        if identity in seen:
            raise ValueError("Duplicate historical source frame")
        seen.add(identity)
        if row["reported_voted_pct"] == "":
            disposition = "held_native_reported_voting_unavailable"
        elif row["population_frame"] != "cvap":
            disposition = "held_population_frame_not_citizen_voting_age"
        elif int(row["year"]) < 1996:
            disposition = "held_earlier_citizenship_measurement_definition"
        else:
            disposition = "reported_participation_marginal_not_joint_transition_truth"
        decisions.append(dict(year=identity[0], state_code=identity[1],
            population_frame=identity[2], election_type=row["election_type"],
            reported_voted_pct=float(row["reported_voted_pct"]) if row["reported_voted_pct"] else None,
            disposition=disposition, source_sha256=row["voted_source_sha256"],
            source_url=row["voted_source_url"], joint_transition_target=None,
            individual_retention=None, observed_staying_home=None))
    return dict(status="held_historical_gross_transition_truth_unavailable",
        reason="Published CPS repeated-cross-section marginals do not identify individual transitions; "
            "their population frame also differs from the current conditional source model.",
        complete_historical_source_decisions=decisions,
        historical_joint_holdout_passed=False, population_transport_validated=False,
        marginal_accounting_is_not_transition_validation=True)


def reconcile_return_checks(checks, comparisons, analytic_by_state):
    rows = {row["id"]: row for row in comparisons["rows"]}
    if len(rows) != len(comparisons["rows"]) or set(rows) != {row["id"] for row in checks}:
        raise ValueError("The complete return comparison inventories differ")
    results = []
    for check in checks:
        source = rows[check["id"]]
        if source["state_code"] != check["state_code"] or source["office"] != check["office"] \
                or not math.isclose(source["current_return_margin_pp"],
                    check["reported_current_margin_pp"], abs_tol=1e-9):
            raise ValueError("Changed return identity or source snapshot")
        analytic = analytic_by_state[check["state_code"]]
        reported = source["reported_comparison"]
        row = dict(check, reported_comparison=reported,
            synthetic_source_frame_change_pp=analytic["source_frame_change_pp"],
            synthetic_components_pp=analytic["components_pp"],
            reported_same_office_change_pp=None, prior_baseline_alignment_pp=None,
            total_unallocated_alignment_pp=None, reconciliation_residual_pp=None)
        if reported["status"] != "unavailable":
            previous = reported["previous"]
            previous_margin = 100 * (previous["D"] - previous["R"]) / (previous["D"] + previous["R"])
            actual_change = check["reported_current_margin_pp"] - previous_margin
            if not math.isclose(actual_change, reported["reported_change_pp"], abs_tol=1e-9):
                raise ValueError("Qualified native same-office return arithmetic differs")
            baseline = analytic["prior_recalled_margin_pp"] - previous_margin
            total_alignment = actual_change - analytic["source_frame_change_pp"]
            residual = actual_change - math.fsum([
                *analytic["components_pp"].values(), check["unallocated_return_minus_model_pp"], baseline])
            if abs(residual) > 1e-8:
                raise AssertionError("Reported swing does not reconcile with both frame differences")
            row.update(reported_same_office_change_pp=actual_change,
                prior_baseline_alignment_pp=baseline, total_unallocated_alignment_pp=total_alignment,
                reconciliation_residual_pp=residual)
        results.append(row)
    return results
