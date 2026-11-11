"""Transport only a primary-context register; never substitute primary turnout for November."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .extract_indiana_primary_register import read_workbook
from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "8ee46200c534b07ccc570dd589908b5d011af67f8debb45f3cc36656ddebfb9a"
NATIVE_SHA = "2e08f30607fc3b46af7923fd14f7aea83497dd0d8ac4733111b7a438f0ab0f07"
URL = "https://www.in.gov/dA/21e5da4ae7/2026-Primary-Registration-and-Turnout-Data.xlsx?language_id=1"
REGISTER = "in-2026-native-primary-context-register"
PRIMARY = "in-2026-native-primary-total-voters-context-only"
FIELDS = {"B": "Registered Voters", "C": "Total Voters", "E": "Election Day", "F": "Absentee"}


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def registration_frame(grid, independent, scope):
    if (scope["native_election_context"] != "2026 Primary" or scope["registration_cutoff_date"] is not None
            or scope["primary_total_voters_not_general_ballots"] is not True
            or scope["cross_election_registration_frame_transport_validated"] is not False):
        raise ValueError("Keep primary/general context, unknown cutoff and unvalidated transport separate")
    if ((grid["sheet"], grid["rows"], grid["columns"]) !=
            (independent["sheet"], independent["rows"], independent["columns"])):
        raise ValueError("Independent complete workbook identities disagree")
    if set(grid["cells"]) != set(independent["cells"]) or len(grid["cells"]) != 665:
        raise ValueError("Incomplete native grid")
    cells = grid["cells"]
    for address, cell in cells.items():
        other = independent["cells"][address]
        if cell["value"] is None:
            same = other["value"] is None
        elif cell["source_type"] == "s":
            same = cell["value"] == other["value"]
        elif address[0] in "DG" and int(address[1:]) >= 3 and cell["number_format"] == "0%":
            same = type(other["value"]) in (int, float) and float(cell["raw_value"]) == float(other["value"])
        else:
            same = other["value"] is not None and Decimal(cell["raw_value"]) == Decimal(str(other["value"]))
        if not same or cell["number_format"] != other["number_format"]:
            raise ValueError("Independent full native cells or number formats disagree")
    if cells["A1"]["value"] != "2026 Primary Registration and Turnout Data":
        raise ValueError("Changed native election title; do not treat as general election")
    if [cells[column + "2"]["value"] for column in "ABCDEFG"] != [
            "County", "Registered Voters", "Total Voters", "Turnout", "Election Day", "Absentee", "Absentee %"]:
        raise ValueError("Changed registered/voter/component/percentage column meanings")
    labels = [cells["A" + str(row)]["value"] for row in range(3, 96)]
    if (labels[-1] != "Statewide" or len(set(labels)) != 93
            or any(not isinstance(value, str) or not value for value in labels)):
        raise ValueError("Missing or repeated native county/explicit Statewide parent")
    raw, contexts, equations, percentages = [], [], [], []

    def native_count(address):
        cell = cells[address]
        if cell["value"] is None:
            return None
        if cell["source_type"] != "n":
            raise ValueError("Native count is not numeric; no coercion")
        value = Decimal(cell["raw_value"])
        if not value.is_finite() or value < 0 or value != value.to_integral_value():
            raise ValueError("Invalid native count; no imputation or renormalization")
        return int(value)

    def equation(identity, parent, terms):
        missing = sum(value is None for value in terms)
        observed = sum(value for value in terms if value is not None)
        full = missing == 0 and parent is not None
        equations.append(dict(identity=identity, native_parent=parent, observed_component_sum=observed,
            missing_components=missing, complete=full, difference=observed - parent if full else None,
            missing_imputed_zero=False, scope="2026_Primary_context_not_November_general"))

    for address, cell in cells.items():
        count_slot = address[0] in FIELDS and int(address[1:]) >= 3
        raw.append(dict(cell=address, raw_native_value=cell["raw_value"], decoded_native_value=cell["value"],
            source_type=cell["source_type"], source_cell_present=cell["source_cell_present"],
            source_number_format=cell["number_format"], native_count_slot=count_slot,
            native_count=native_count(address) if count_slot else None,
            missing_imputed_zero=False, formulas_executed=False))
    for row in range(3, 96):
        label = cells["A" + str(row)]["value"]
        values = {column: native_count(column + str(row)) for column in FIELDS}
        context = dict(native_county_label=label, geographic_level="state" if row == 95 else "county",
            native_election_context="2026 Primary", source_row=row,
            registered_voters=values["B"], total_voters=values["C"],
            election_day=values["E"], absentee=values["F"],
            registration_cutoff_date=None, exact_clock=None, timezone=None,
            active_inactive_status_qualified=False, general_election_ballots_qualified=False,
            absentee_is_mail_only_qualified=False, geographic_codes_inferred=False)
        for column, numerator, denominator, field in (
                ("D", values["C"], values["B"], "total_voters_per_registered"),
                ("G", values["F"], values["C"], "absentee_per_total_voters")):
            cell = cells[column + str(row)]
            if cell["source_type"] != "n" or cell["number_format"] != "0%" or cell["raw_value"] is None:
                raise ValueError("Changed native whole-percent source format or missing percentage")
            native_fraction = Fraction(cell["raw_value"])
            if native_fraction < 0 or native_fraction > 1:
                raise ValueError("Invalid native percentage fraction")
            exact = (Fraction(numerator, denominator) * 100
                     if numerator is not None and denominator is not None and denominator > 0 else None)
            preformat = native_fraction * 100
            printed = Fraction((2 * preformat.numerator + preformat.denominator) // (2 * preformat.denominator))
            context["native_" + field + "_display_pct"] = number(printed)
            percentages.append(dict(native_county_label=label, source_cell=column + str(row),
                native_context_measure=field, source_stored_fraction=cell["raw_value"],
                source_number_format="0%", source_preformat_pct=number(preformat),
                source_display_pct=number(printed),
                exact_source_count_ratio_pct=number(exact) if exact is not None else None,
                displayed_minus_exact_percentage_points=number(printed - exact) if exact is not None else None,
                whole_percent_rounding_compatible=abs(printed - exact) <= Fraction(1, 2) if exact is not None else None,
                general_election_rate_approved=False, design_confidence_interval=None))
        contexts.append(context)
        equation("row" + str(row) + "-total-voters-vs-components", values["C"], [values["E"], values["F"]])
    parent = contexts[-1]
    for field in ("registered_voters", "total_voters", "election_day", "absentee"):
        equation("statewide-" + field + "-vs-all92-counties", parent[field], [row[field] for row in contexts[:-1]])
    if type(parent["registered_voters"]) is not int or parent["registered_voters"] <= 0:
        raise ValueError("Missing positive explicit Statewide registered parent; no county-sum replacement")
    return parent, raw, contexts, equations, percentages


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-indiana-primary-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete version25 baseline or sufficient native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        checksums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(checksums) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in checksums.items():
            value = archive.read(name)
            if len(value) != metadata["bytes"] or hashlib.sha256(value).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        parent, raw, contexts, equations, percentages = registration_frame(
            read_workbook(archive.read("IN-2026-primary.xlsx")),
            json.loads(archive.read("independent-workbook.json")),
            json.loads(archive.read("source-scope.json")))
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 48, 31):
        raise ValueError("Changed complete version25 coverage")
    target = next(row for row in states if row["state_code"] == "IN")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate a prior selected Indiana source register")
    source = next(row for row in civic_source(baseline)["participation"]
                  if row["scope"] == "IN" and row["dimension"] == "overall")
    total = parent["registered_voters"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[field]) for field in
                                  ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state weights")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
    time = "Native2026Primary report context; registration cutoff/date/clock/timezone/status unqualified; NOTNovemberGeneral register"
    basis = "native_Registered_Voters_Statewide_primary_context_not_November_election_time_population"
    target.update(control_id=REGISTER, control_measure="native_primary_context_registered_frame_only",
        control_native_numerator=None, control_registered_denominator=total,
        control_denominator_basis=basis, control_native_time=time, control_source_url=URL,
        conditional_registered_frame_scenario_available="True")
    template = dict(controls[0])
    for control_id, measure, numerator, notes in (
        (REGISTER, "native_primary_context_registered_frame_only", None,
         "Primary registered stock ONLY; cross-election source transport unvalidated. No November ballot/model residual."),
        (PRIMARY, "native_primary_Total_Voters_context_not_general_ballots", parent["total_voters"],
         "Native PRIMARY TotalVoters, ElectionDay and Absentee partition; NOTNovember ballots or general-model validation/calibration.")):
        control = dict(template)
        control.update(id=control_id, state_code="IN", year=2026, geographic_level="state",
            geography="Indiana 2026 PRIMARY context", source_family=URL,
            measure=measure, native_measure="Registered Voters" if control_id == REGISTER else "Total Voters (PRIMARY)",
            numerator=numerator, denominator=total, denominator_basis=basis,
            denominator_label="Explicit Statewide Registered Voters in PRIMARY report; not a qualified November stock",
            source_time_label=time, source_url=URL,
            native_status="Published primary-context statistical report; not general-election counting/certification",
            source_kind="reviewed_official_aggregate_primary_context_workbook",
            scope_notes=notes + " Literal count cells and whole-percent source fractions retained; unknown cutoff/status. Absentee is not independently qualified mail-only. No group/local allocation or legal/population certification.",
            selected_state_reference=False,
            disposition="primary_registered_frame_unvalidated_cross_election_transport" if control_id == REGISTER
                        else "primary_context_only_not_general_ballot_reference_or_model_calibration")
        controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="IN", control_id=REGISTER,
        control_measure="native_primary_context_registered_frame_only",
        control_native_status="Published primary-context registration stock, not November population",
        native_registered_denominator=total, native_denominator_basis=basis,
        source_time_label=time, source_url=URL, civic_source_n=source["n"],
        civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
        civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="2026 General Civic source propensity transported to 2026 PRIMARY registered stock; cross-election registry-frame exchangeability UNVALIDATED; cutoff/status unknown, not November population or legal-eligibility certification",
        scenario_units="native_primary_context_registered_units_not_observed_general_election_people")
    scenarios.append(scenario)
    frame = dict(state_code="IN", registration_source_election_context="2026 Primary",
        model_propensity_context="2026 General Civic source model", registration_cutoff_date=None,
        native_registered_parent=total, conditional_model_participant_units=str(modeled),
        conditional_model_nonparticipant_units=str(nonmodeled),
        cross_election_registry_transport_validated=False, primary_total_voters_used_for_general_model=False,
        general_election_ballots=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_allocation=False, design_confidence_interval=None, rate_approved=False, map_approved=False)
    complete = [row for row in equations if row["complete"]]
    qualification = dict(native_election_context="2026 Primary", model_propensity_context="2026 General Civic",
        registration_cutoff_date=None, exact_clock=None, timezone=None, active_inactive_status_qualified=False,
        native_registered_parent=total, native_primary_Total_Voters_context=parent["total_voters"],
        native_primary_Election_Day_context=parent["election_day"], native_primary_Absentee_context=parent["absentee"],
        primary_total_voters_not_general_ballots=True, primary_counts_not_general_model_validation_or_calibration=True,
        cross_election_registry_frame_transport_validated=False,
        native_unique_person_cast_ballot_or_legal_eligibility_certification=False,
        source_title_and_filename_not_registration_cutoff=True,
        absentee_not_independently_qualified_mail_only=True,
        whole_percent_source_rounding_not_a_confidence_interval=True,
        percentage_peer_comparison_uses_binary64_semantics_raw_lexemes_preserved=True,
        native_count_peer_comparison_exact_not_relaxed=True,
        native_accounting_equations=len(equations), complete_equations=len(complete),
        incomplete_equations=len(equations) - len(complete),
        native_accounting_discrepancies=[row for row in complete if row["difference"]],
        whole_percent_rounding_disagreements=[row for row in percentages if row["whole_percent_rounding_compatible"] is False],
        missing_imputed_zero=False, all50_other_states_48_controls_31_scenarios_preserved=True,
        native_general_ballots=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_allocation=False, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, new_website_view=False,
        illinois_http200_discovery_not_numeric_acquisition_not403_or_world_absence=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-indiana-native-workbook-cells.csv": csv_bytes(raw),
        "complete-indiana-primary-context.csv": csv_bytes(contexts),
        "complete-indiana-native-accounting.csv": csv_bytes(equations),
        "complete-indiana-native-percent-diagnostics.csv": csv_bytes(percentages),
        "complete-indiana-primary-register-frame.csv": csv_bytes([frame]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=50, conditional_scenarios=32,
            native_grid_slots=665, native_count_slots=372, native_percentage_slots=186,
            native_county_rows=92, native_unknown_count_slots=sum(row["native_count_slot"] and row["native_count"] is None for row in raw),
            native_observed_zero_count_slots=sum(row["native_count_slot"] and row["native_count"] == 0 for row in raw),
            complete_equations=len(complete), incomplete_equations=len(equations) - len(complete),
            native_accounting_discrepancies=len(qualification["native_accounting_discrepancies"]),
            native_percent_rounding_disagreements=len(qualification["whole_percent_rounding_disagreements"]),
            all50_other_states_48_controls_31_scenarios_preserved=True,
            no_primary_to_general_ballot_substitution_or_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-indiana-primary-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("indiana_primary_register.py", "extract_indiana_primary_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_indiana_primary_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Indiana native2026 PRIMARY RegisteredVoters4713746, NOTNovemberGeneral election-time population.\n"
        "Primary TotalVoters807059/ElectionDay553110/Absentee253949 are CONTEXT ONLY, never general ballots,\n"
        "general-model validation/calibration, matched residual or observed staying home.\n"
        "Source title doesNOTqualify registrationcutoff/day/clock/timezone/active-inactivestatus.\n"
        "One conditional GENERAL Civic propensity xPRIMARY registered-stock scenario is UNVALIDATED cross-election transport.\n"
        "All92counties/Statewide/665gridcells/372counts/186whole-percent source fractions are preserved.\n"
        "No missing-zero/formulaexecution/partychoice/localgroupallocation/eligibilitycertification/fakeCI/rate/map/view.\n"
        "Illinois200 navigation discovery is NOTnumeric acquisition/403/paid-only/global absence; no guessedfiles/purchase.\n"
        "Complete original/independentgrid/scopes/receipts/baseline25/reader/extractor/sharedcode/tests/allqueries/checksums.\n"
        "python3 -m unittest discover -s tests -p test_indiana_primary_register.py\n"
        "python3 -m scripts.indiana_primary_register --inputs inputs --output reproduced\n").encode()
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
