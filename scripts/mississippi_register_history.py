"""Dated registration stocks and explicitly conditional, differently measured participation signals."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .extract_mississippi_register_history import read_pdf
from .washington_register_control import csv_bytes, encoded


YEARS = (2022, 2024, 2026)
NATIVE_SHA = "b5025d7ac4313948987a09008d9822c336aec2fce86662dfcb912ebd92648bda"
CPS_SHA = "bda083bac82cd4ac43a7f50e99a02a1c0d15113da9cb0341e9e5a1908a77152e"


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def csv_rows(body):
    return list(csv.DictReader(io.StringIO(body.decode())))


def native_frame(year, rows, peer, scope):
    if (year not in YEARS or scope["report_month"] != f"{year}-10"
            or scope["registration_status"] != "ACTIVE" or scope["exact_cutoff_date"] is not None
            or scope["printed_statewide_total"] is not None
            or scope["model_frame_transport_validated"] is not False):
        raise ValueError("Keep native month/status, unknown cutoff, derived stock and unvalidated transport")
    if rows != peer:
        raise ValueError("Independent complete historical native rows disagree")
    if len(rows) != 82 or [row["native_county_label"][:2] for row in rows] != [f"{i:02}" for i in range(1, 83)]:
        raise ValueError("Missing or repeated native county coverage")
    contexts, diagnostics = [], []
    for row in rows:
        values = {}
        for field in ("native_active_voters", "native_cvap_estimate"):
            raw = row[field]
            if raw is not None and (not isinstance(raw, str) or not re.fullmatch(r"\d+", raw)):
                raise ValueError("Invalid native count; no coercion or zero fill")
            values[field] = int(raw) if raw is not None else None
        active, cvap = values["native_active_voters"], values["native_cvap_estimate"]
        raw = row["native_percentage"]
        if raw is not None and not re.fullmatch(r"\d+\.\d{3}%", raw):
            raise ValueError("Changed native percentage format")
        display = Fraction(raw[:-1]) if raw is not None else None
        exact = Fraction(100 * active, cvap) if active is not None and cvap is not None and cvap > 0 else None
        difference = display - exact if display is not None and exact is not None else None
        contexts.append(dict(year=year, **row, report_month=f"{year}-10",
            native_county_code_not_fips=row["native_county_label"][:2],
            source_cvap_header=scope["source_cvap_header"], cvap_used_as_model_denominator=False,
            actual_cutoff_date=None, source_url=scope["source_url"], missing_imputed_zero=False,
            geographic_codes_inferred=False, group_or_county_model_allocation=False))
        diagnostics.append(dict(year=year, native_county_label=row["native_county_label"],
            source_percentage=raw, exact_active_per_source_cvap_pct=number(exact) if exact is not None else None,
            source_display_minus_exact_pp=number(difference) if difference is not None else None,
            three_decimal_rounding_compatible=abs(difference) <= Fraction(1, 2000) if difference is not None else None,
            over100_preserved=display > 100 if display is not None else None,
            percentage_is_turnout=False, clipped_or_repaired=False))
    missing = sum(row["native_active_voters"] is None for row in rows)
    total = sum(int(row["native_active_voters"]) for row in rows) if not missing else None
    state = dict(year=year, state_code="MS", report_month=f"{year}-10",
        election_type="presidential" if year == 2024 else "midterm",
        registration_status="ACTIVE", native_county_rows=82,
        derived_active_register=total, missing_active_cells=missing,
        printed_statewide_total=None, aggregate_is_derived_not_printed=True,
        actual_cutoff_date=None, exact_clock=None, timezone=None, source_url=scope["source_url"],
        independent_legal_eligibility_certification=False, administratively_observed_voting=False,
        all82_county_sum_not_an_independent_state_benchmark=True, local_model_allocation=False)
    return state, contexts, diagnostics


def stock_comparisons(states):
    pairs = ((2022, 2024), (2024, 2026), (2022, 2026))
    index = {row["year"]: row for row in states}
    out = []
    for a, b in pairs:
        before, after = index[a]["derived_active_register"], index[b]["derived_active_register"]
        difference = after - before if before is not None and after is not None else None
        out.append(dict(from_year=a, to_year=b, state_code="MS",
            source_status="ACTIVE", report_months="October labels; exact cutoffs unknown",
            from_derived_register=before, to_derived_register=after, registration_stock_difference=difference,
            registration_stock_change_pct=number(Fraction(100 * difference, before)) if difference is not None and before > 0 else None,
            same_election_type=index[a]["election_type"] == index[b]["election_type"],
            matched_person_panel=False, registration_definitions_and_processing_harmonized=False,
            change_is_turnout_or_participation_change=False, inferred_new_voters=None,
            retained_voters=None, deaths=None, migration=None, eligibility=None))
    return out


def participation(states, references, civic, existing_2026):
    register = {row["year"]: row["derived_active_register"] for row in states}
    cps = {(int(row["year"]), row["population_frame"]): row for row in references
           if row["reference_state_code"] == "MS" and int(row["year"]) in (2022, 2024)}
    if len(cps) != len([row for row in references if row["reference_state_code"] == "MS"
                       and int(row["year"]) in (2022, 2024)]):
        raise ValueError("Duplicate selected CPS native state/frame rows")
    source = next(row for row in civic["participation"] if row["scope"] == "MS" and row["dimension"] == "overall")
    decisions, scenarios = [], []
    for year in YEARS:
        for view in ("CPS_cvap_marginal_ratio", "CPS_vap_marginal_ratio", "Civic_native_model"):
            reason, selected, ratio, native = "source_year_absent_from_selected_input_not_global_absence", False, None, None
            if view.startswith("CPS") and (year, view.split("_")[1]) in cps:
                native = cps[year, view.split("_")[1]]
                if view == "CPS_vap_marginal_ratio":
                    reason = "alternative_native_population_frame_preserved_not_selected_not_pooled"
                else:
                    yes, registered = native["reported_voted_pct"], native["reported_registered_pct"]
                    if yes and registered and 0 <= Fraction(yes) <= Fraction(registered) and Fraction(registered) > 0:
                        ratio = Fraction(yes) / Fraction(registered)
                        selected, reason = True, "conditional_rounded_marginal_ratio_transport_UNVALIDATED_not_individual_joint"
                    else:
                        reason = "native_percentages_missing_or_incompatible_no_repair"
            elif view == "Civic_native_model" and year == 2026:
                weight, voter, nonvoter = (Fraction(source[field]) for field in
                    ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
                if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight:
                    raise ValueError("Changed full public Civic source weights")
                ratio = voter / weight
                selected, reason = True, "existing_unvalidated_2026_native_source_model_frame_reused"
            if selected and register[year] is None:
                selected, reason = False, "incomplete_native_active_stock_no_partial_count_projection"
            decisions.append(dict(year=year, state_code="MS", source_view=view, selected=selected,
                disposition=reason, native_registered_stock=register[year],
                source_voted_pct=native["reported_voted_pct"] if native else None,
                source_registered_pct=native["reported_registered_pct"] if native else None,
                unknown_response_mass_identified=False if view.startswith("CPS") else None,
                no_missing_population_or_response_repair=True))
            if not selected:
                continue
            signal = number(register[year] * ratio)
            complement = number(register[year] * (1 - ratio))
            if year == 2026:
                signal, complement = (existing_2026[field] for field in
                    ("conditional_model_participant_units", "conditional_model_nonparticipant_units"))
                if (abs(Fraction(signal) - register[year] * ratio) >= Fraction(1, 10**60)
                        or abs(Fraction(complement) - register[year] * (1 - ratio)) >= Fraction(1, 10**60)):
                    raise ValueError("Changed accepted 2026 source model scenario")
            scenarios.append(dict(year=year, state_code="MS", source_view=view,
                native_active_register=register[year], source_signal_fraction=number(ratio),
                source_voted_pct=native["reported_voted_pct"] if native else None,
                source_registered_pct=native["reported_registered_pct"] if native else None,
                source_sample_n=source["n"] if year == 2026 else None,
                conditional_voting_signal_units=signal, conditional_complement_units=complement,
                complement_interpretation="source_model_nonparticipant_class_not_observed_people" if year == 2026
                    else "remainder_of_rounded_marginal_ratio_not_identified_reported_nonvoters_or_unknown",
                reported_unknown_response_units=None, source_measurements_harmonized_across_years=False,
                source_ratio_is_individual_registered_joint=False,
                registry_date_status_population_transport_validated=False,
                administratively_observed_turnout=False, observed_staying_home=False,
                actual_cutoff_date=None, design_confidence_interval=None,
                source_rounding_or_decimal_arithmetic_not_precision_claim=True,
                group_or_local_allocation=False))
    comparisons = [dict(from_year=row["from_year"], to_year=row["to_year"],
        disposition="held_different_election_types_and_unvalidated_measurement_transport"
            if not row["same_election_type"] else "held_CPS_selfreport_vs_Civic_model_not_harmonized",
        conditional_participation_unit_difference=None, observed_turnout_change=None,
        person_switching_or_retention=None, no_cross_source_trend_claim=True)
        for row in stock_comparisons(states)]
    return decisions, scenarios, comparisons


def build(inputs):
    native = (inputs / "complete-register-history-inputs.zip").read_bytes()
    cps = (inputs / "complete-cps-state-inputs.zip").read_bytes()
    if hashlib.sha256(native).hexdigest() != NATIVE_SHA or hashlib.sha256(cps).hexdigest() != CPS_SHA:
        raise ValueError("Changed complete sufficient public inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        manifest = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(manifest) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in manifest.items():
            value = archive.read(name)
            if len(value) != metadata["bytes"] or hashlib.sha256(value).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed frozen factual input")
        scopes = json.loads(archive.read("report-scopes.json"))
        states, counties, percentages = [], [], []
        for year in YEARS:
            if year in (2022, 2024):
                rows = read_pdf(archive.read(f"MS-October-{year}.pdf"), year)
                peer = json.loads(archive.read(f"independent-{year}-rows.json"))["rows"]
            else:
                rows = [{field: int(row[field]) if field == "page" else row[field]
                         for field in ("page", "native_county_label", "native_cvap_estimate",
                                       "native_active_voters", "native_percentage")}
                        for row in csv_rows(archive.read("existing-2026-county-query.csv"))]
                with zipfile.ZipFile(io.BytesIO(archive.read("existing-2026-native-inputs.zip"))) as previous:
                    peer = json.loads(previous.read("independent-pdf-rows.json"))["rows"]
            state, context, diagnostics = native_frame(year, rows, peer, scopes[str(year)])
            states.append(state)
            counties.extend(context)
            percentages.extend(diagnostics)
        civic = json.loads(archive.read("civic-selected-aggregates.json"))
        existing_2026 = csv_rows(archive.read("existing-2026-frame.csv"))[0]
    with zipfile.ZipFile(io.BytesIO(cps)) as archive:
        references = csv_rows(archive.read("complete-state-year-population-pairs.csv"))
    decisions, scenarios, comparisons = participation(states, references, civic, existing_2026)
    qualification = dict(state_code="MS", years=list(YEARS), source_month="October index labels",
        exact_cutoff_dates_clocks_timezones_unknown=True, native_status="ACTIVE",
        state_totals_derived_from_all82_counties_not_printed_or_independently_benchmarked=True,
        native_cvap_headers_and_2026_asterisks_retained_not_population_crosswalked=True,
        cvap_not_model_denominator_or_turnout=True,
        CPS_scenarios_use_rounded_native_CVAP_voted_over_registered_marginal_percentages=True,
        CPS_ratio_not_individual_joint_or_known_response_only_estimate=True,
        CPS_complement_not_identified_reported_nonvoting_or_unknown=True,
        Civic_2026_scenario_reused_unchanged_not_newly_estimated=True,
        date_status_registry_population_transport_validated=False,
        across_source_measurement_equivalence_validated=False,
        source_registration_stock_changes_not_turnout_new_returning_voters_retention_or_demographic_change=True,
        exact_decimal_arithmetic_not_sampling_precision_or_interval=True,
        observed_staying_home=None, person_switching=None, deaths=None, migration=None, eligibility=None,
        local_or_group_allocation=False, rates_or_maps_approved=False, new_website_view=False,
        current_native27_all51_state_decisions_51_controls_33_scenarios_unchanged=True,
        prior_source403_holds_downloads_and_models_unchanged=True)
    return {
        "complete-native-county-query.csv": csv_bytes(counties),
        "complete-state-registration-frames.csv": csv_bytes(states),
        "complete-registration-stock-comparisons.csv": csv_bytes(stock_comparisons(states)),
        "complete-native-percent-diagnostics.csv": csv_bytes(percentages),
        "complete-participation-scenario-decisions.csv": csv_bytes(decisions),
        "complete-conditional-participation-scenarios.csv": csv_bytes(scenarios),
        "complete-scenario-comparison-decisions.csv": csv_bytes(comparisons),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_code="MS", years=list(YEARS), native_pages=9, native_county_rows=246,
            native_factual_cells=984, native_count_cells=492, native_percentage_cells=246,
            registration_stock_comparisons=3, complete_source_year_scenario_decisions=len(decisions),
            new_CPS_conditional_scenarios=sum(row["year"] != 2026 for row in scenarios),
            reused_Civic_2026_scenarios=sum(row["year"] == 2026 for row in scenarios),
            held_model_comparisons=len(comparisons),
            native_percent_rounding_disagreements=sum(row["three_decimal_rounding_compatible"] is False for row in percentages),
            native_percentages_over100_preserved=sum(row["over100_preserved"] is True for row in percentages),
            native_current27_and_website_unchanged=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("complete-register-history-inputs.zip", "complete-cps-state-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("mississippi_register_history.py", "extract_mississippi_register_history.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_mississippi_register_history.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Mississippi October ACTIVE register stocks for2022/2024/2026, not election-time populations or ballots.\n"
        "Each state total is our derived all82county sum; no printedstateparent or independentbenchmark.\n"
        "Complete native rows/percentages/headers/asterisks and unknown actual cutoffs are retained.\n"
        "New CPS2022/2024 scenarios: native rounded CVAP voted% /registered% xOctober ACTIVE stock.\n"
        "This is UNVALIDATED date/status/registry/population transport, NOTan individual registered-voter joint.\n"
        "CPS complement is NOTidentified reportednonvoters or unknowns; no response repair or known-only rate.\n"
        "2026 Civic model and all native inputs/queries reused unchanged; different measurement, NOTa cross-year trend.\n"
        "Registration-stock changes are NOTturnout, retention, newvoters, migration, deaths, eligibility or demographics.\n"
        "No state survey allocation to counties/groups, fabricatedCI, legalcertification, new rate/map/website view.\n"
        "Includes all3native originals, independent factual cells, complete original CPS package/public aggregates,\n"
        "everynew query/decision/result, portable code/tests/checksums. Prior unrelated nested baselines not required.\n"
        "Requires existing pypdf. No network/private files required for reproduction.\n"
        "python3 -m unittest discover -s tests -p test_mississippi_register_history.py\n"
        "python3 -m scripts.mississippi_register_history --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                                     for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
