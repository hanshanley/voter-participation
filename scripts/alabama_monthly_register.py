"""Separate Alabama monthly active and combined frames from election reporting."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .extract_alabama_monthly_register import column_name, read_workbook
from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "13a0fecb05d650f1013bf74c79fb630ac83b0dc1554ceed4a9d933aca0662ecd"
WORKBOOK_SHA = "e0942c9ce7d5e390d9163fe16cbb654b5ede4161ac6ae980dae7e464825fc382"
URL = "https://www.sos.alabama.gov/sites/default/files/election-data/2026-11/ALVR-2026.xlsx"


def registration_frames(body, independent, declaration):
    if hashlib.sha256(body).hexdigest() != WORKBOOK_SHA:
        raise ValueError("Changed original native registration workbook")
    sheets = read_workbook(body)
    if (declaration["source_year"] != 2026 or declaration["selected_native_sheet"] != "October"
            or declaration["registration_cutoff_date"] is not None
            or declaration["url_directory_is_not_registration_month"] is not True):
        raise ValueError("Do not substitute the URL month or retrieval date for the native month")
    comparison = [dict(name=sheet["name"], rows=sheet["rows"], columns=sheet["columns"],
                      values={address: cell["value"] for address, cell in sheet["cells"].items()})
                  for sheet in sheets]
    if comparison != independent:
        raise ValueError("Independent XML and complete cached-value workbook readers disagree")
    accounting, equations, parents = [], [], []

    def equation(sheet, label, parent, terms):
        cells = sheet["cells"]
        values = [cells[address]["value"] for address in terms]
        native_parent = cells[parent]["value"]
        missing = sum(value is None for value in values)
        observed = sum(value for value in values if value is not None)
        complete = missing == 0 and native_parent is not None
        equations.append(dict(month_label=sheet["name"], equation=label, parent_cell=parent,
            native_parent=native_parent, observed_component_sum=observed, missing_components=missing,
            complete=complete, difference=observed - native_parent if complete else None,
            missing_imputed_zero=False))

    for sheet in sheets:
        cells = sheet["cells"]
        if (sheet["state"] != "visible" or cells["A3"]["value"] != "TOTAL"
                or cells["C1"]["value"] != "Active" or cells["M1"]["value"] != "Inactive"
                or cells["L2"]["value"] != "Total Active" or cells["V2"]["value"] != "Total Inactive"):
            raise ValueError("Changed native active/inactive parent definitions")
        counties = [cells["A" + str(row)]["value"] for row in range(4, 71)]
        if any(not isinstance(value, str) or not value for value in counties) or len(set(counties)) != 67:
            raise ValueError("Missing or repeated native county; no inferred geographic codes")
        for address, cell in cells.items():
            digits = next(index for index, character in enumerate(address) if character.isdigit())
            column, row = address[:digits], int(address[digits:])
            count_slot = column != "A" and row >= 3
            if count_slot and cell["value"] is not None and (
                    type(cell["value"]) is not int or cell["value"] < 0):
                raise ValueError("Invalid native count; no coercion or formula execution")
            accounting.append(dict(month_label=sheet["name"], cell=address, native_value=cell["value"],
                raw_stored_value=cell["raw_value"], source_type=cell["source_type"],
                source_cell_present=cell["source_cell_present"], count_slot=count_slot,
                native_count=cell["value"] if count_slot else None,
                is_formula=cell["is_formula"], stored_formula_text=cell["stored_formula_text"],
                stored_formula_attributes=json.dumps(cell["stored_formula_attributes"], sort_keys=True),
                missing_imputed_zero=False))
        for row in range(3, 71):
            equation(sheet, "combined_equals_active_plus_inactive", "B" + str(row),
                     ["L" + str(row), "V" + str(row)])
            for parent, first, last in (("L", 3, 11), ("V", 13, 21)):
                equation(sheet, "native_category_components_" + parent, parent + str(row),
                         [column_name(column) + str(row) for column in range(first, last + 1)])
        for column in range(2, 23):
            name = column_name(column)
            equation(sheet, "explicit_parent_vs_all67_counties", name + "3",
                     [name + str(row) for row in range(4, 71)])
        parents.append(dict(year=2026, native_month_label=sheet["name"],
            native_combined_parent=cells["B3"]["value"], native_active_parent=cells["L3"]["value"],
            native_inactive_parent=cells["V3"]["value"], registration_cutoff_date=None,
            exact_clock=None, timezone=None, repeated_snapshots_not_additive_populations=True))
    selected = parents[-1]
    if any(type(selected[field]) is not int or selected[field] <= 0 for field in (
            "native_combined_parent", "native_active_parent", "native_inactive_parent")):
        raise ValueError("Missing explicit cached October parent; do not calculate a replacement")
    return selected, accounting, equations, parents


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA:
        raise ValueError("Changed accepted complete version23 baseline")
    native = (inputs / "complete-alabama-monthly-native-inputs.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Incomplete native sufficient inputs")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        selected, accounting, equations, parents = registration_frames(archive.read("ALVR-2026.xlsx"),
            json.loads(archive.read("independent-cached-values.json")),
            json.loads(archive.read("source-declaration.json")))
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 41, 29):
        raise ValueError("Changed complete version23 coverage")
    source = next(row for row in civic_source(baseline)["participation"]
                  if row["scope"] == "AL" and row["dimension"] == "overall")
    target = next(row for row in states if row["state_code"] == "AL")
    if target["control_id"] != "reporting-AL" or target["conditional_registered_frame_scenario_available"] != "True":
        raise ValueError("Preserve existing Alabama election-reporting reference and scenario")
    frames = []
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in
                                  ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state weights")
        for kind, field, label in (
                ("active", "native_active_parent", "source monthly active registrations"),
                ("combined", "native_combined_parent", "source monthly active plus inactive registrations")):
            total = selected[field]
            control_id = "al-2026-native-monthly-" + kind + "-202610"
            if any(row["id"] == control_id for row in controls):
                raise ValueError("Do not duplicate a prior source frame")
            modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
            if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
                raise ValueError("Conditional source-register partition failed")
            time = "Native worksheet October/year2026; cutoff date/clock/timezone unknown; URL2026-11 is not snapshot month"
            basis = "native_" + kind + "_registration_TOTAL_cached_" + ("L3" if kind == "active" else "B3")
            control = dict(controls[0])
            control.update(id=control_id, state_code="AL", year=2026, geographic_level="state",
                geography="Alabama monthly " + kind + " registration frame", source_family=URL,
                measure="native_monthly_" + kind + "_registrations", native_measure=label,
                numerator=None, denominator=total, denominator_basis=basis, denominator_label=label,
                source_time_label=time, source_url=URL,
                native_status="Administrative monthly registration stock, not election counting/certification",
                source_kind="reviewed_public_official_workbook_cached_parent",
                scope_notes="Native October sheet, not November URLdirectory. Formula caches retained, never executed; blanks unknown. Active and combined overlap, not additive. No inactive eligibility/turnout or group/local allocation claim; prior reporting reference untouched.",
                selected_state_reference=False,
                disposition="separate_monthly_" + kind + "_frame_not_election_time_population_or_ballot_reference")
            controls.append(control)
            scenario = dict(scenarios[0])
            scenario.update(year=2026, state_code="AL", control_id=control_id,
                control_measure=control["measure"], control_native_status=control["native_status"],
                native_registered_denominator=total, native_denominator_basis=basis,
                source_time_label=time, source_url=URL, civic_source_n=source["n"],
                civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                conditional_modeled_voter_count=str(modeled),
                conditional_modeled_nonvoter_count=str(nonmodeled), reported_cast_ballot_measure_control=None,
                reported_cast_minus_conditional_modeled_voter_count=None,
                assumption=label + " exchangeable with statewide Civic propensity; unvalidated, different overlapping frames, not election-time population or legal-eligibility certification",
                scenario_units="native_monthly_" + kind + "_registration_units_not_administratively_observed_people")
            scenarios.append(scenario)
            frames.append(dict(state_code="AL", native_year=2026, native_month_label="October",
                frame=kind, native_registered_parent=total, registration_cutoff_date=None,
                conditional_model_participant_units=str(modeled),
                conditional_model_nonparticipant_units=str(nonmodeled),
                ballots_linked_to_dated_frame=None, native_minus_model=None, observed_staying_home=None,
                rate_approved=False, map_approved=False))
    complete = [row for row in equations if row["complete"]]
    discrepancies = [row for row in complete if row["difference"]]
    qualification = dict(native_year=2026, native_month_label="October", url_directory_month_not_snapshot=True,
        registration_cutoff_date=None, exact_clock=None, timezone=None,
        active_parent=selected["native_active_parent"], inactive_parent_context=selected["native_inactive_parent"],
        combined_parent=selected["native_combined_parent"], active_and_combined_overlap_not_additive=True,
        inactive_is_not_ineligible_or_nonparticipant=True, cached_formula_values_not_recalculated=True,
        native_formula_records_preserved=True, missing_imputed_zero=False,
        native_race_and_federal_registration_categories_not_harmonized_or_used_for_group_models=True,
        independent_legal_eligibility_certification=False, source_population_transport_validated=False,
        native_accounting_equations=len(equations), complete_equations=len(complete),
        incomplete_equations=len(equations) - len(complete), discrepancies=discrepancies,
        prior_all51_state_rows_and41_controls_and29_scenarios_unchanged=True,
        old_alabama_reporting_count_denominator_rate_and_scenario_unchanged=True,
        native_ballots_linked_to_monthly_frame=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_survey_allocation=False, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, counting_completion_approved=False,
        certification_approved=False, new_website_view=False)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-alabama-native-workbook-cells.csv": csv_bytes(accounting),
        "complete-alabama-native-accounting.csv": csv_bytes(equations),
        "complete-alabama-monthly-parents.csv": csv_bytes(parents),
        "complete-alabama-monthly-frames.csv": csv_bytes(frames),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=43, conditional_scenarios=31,
            native_month_sheets=len(parents), native_county_rows=670, native_grid_slots=len(accounting),
            native_count_slots=sum(row["count_slot"] for row in accounting),
            native_unknown_count_slots=sum(row["count_slot"] and row["native_count"] is None for row in accounting),
            native_observed_zeros=sum(row["count_slot"] and row["native_count"] == 0 for row in accounting),
            native_formula_cache_records=sum(row["is_formula"] for row in accounting),
            complete_equations=len(complete), incomplete_equations=len(equations) - len(complete),
            native_accounting_discrepancies=len(discrepancies),
            all51_state_rows_41_controls_29_scenarios_preserved=True, no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-alabama-monthly-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("alabama_monthly_register.py", "extract_alabama_monthly_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_alabama_monthly_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Alabama native October2026 monthly registration, NOTNovember URLdirectory or retrievaldate.\n"
        "Active3,390,357 and combined3,853,181 are separate OVERLAPPING frames, never additive.\n"
        "Inactive462,824 is native context, NOT ineligible or administratively nonparticipating people.\n"
        "All TEN month sheets January-October, native county/cell/formula/cache/unknown records included.\n"
        "Formulas are never executed/recalculated; blank fine cells remain UNKNOWN, not zero.\n"
        "Conditional statewide source-register units assume unvalidated Civic exchangeability.\n"
        "No observedpeople/stayinghome/monthly-linkedballots/residual/group/localallocation/fakeCI/rate/map.\n"
        "All51prior state rows and existing ALreporting count/denominator/rate/scenario stay unchanged.\n"
        "Complete original workbook/independentgrid/declaration/receipts/baseline/code/tests/allqueries/checksums.\n"
        "python3 -m unittest discover -s tests -p test_alabama_monthly_register.py\n"
        "python3 -m scripts.alabama_monthly_register --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                     for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, body)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
