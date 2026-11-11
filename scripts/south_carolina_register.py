"""Use the native statewide register once; preserve demographic stocks and blanks."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "c615e4533315fe9814d3c89eb6d50507552c8828fad261c86297a0f20a79ebb7"
WORKBOOK_SHA = "04067e0bacdbc0b9e04d41e4f088d6a1371ceeb821fb2d3cc4a1e1b9f5271b7b"
NATIVE_SHA = "79c003b5ff142705047db5a8065a8d3d33a294f9f822ded179c37dbc44dc9353"
URL = "https://scvotes.gov/wp-content/uploads/2026/11/VR-Totals-Race-County-Gender-Age-2026-11-2.xlsx"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RACES = ["All", "Black/AA", "White", "Asian", "Hispanic", "Native American", "Multiple", "Other", "Unknown"]
AGES = ["18 - 24", "25 - 44", "45 - 64", "65 - Up"]
SLOTS = [("H", "All", "All")]
for gender, columns in (("Female", ["J", "K", "L", "M", "N"]),
                        ("Male", ["P", "Q", "R", "S", "T"]),
                        ("Unknown", ["W", "X", "Y", "Z", "AA"])):
    SLOTS.extend(zip(columns, [gender] * 5, ["All", *AGES]))
CONTROL = "sc-2026-native-RP0040-registration-report-labelled-20261102"
BASIS = "native_RP0040_Race_All_TOTAL_All_Total_report_label_not_cutoff"
MEASURE = "native_report_labelled_registration_total_cutoff_not_stated"


def column_name(value):
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def decode_workbook(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = list(workbook.find("{" + NS + "}sheets"))
        if [row.get("name") for row in sheets] != ["Sheet" + str(value) for value in range(1, 10)]:
            raise ValueError("Changed complete nine-worksheet inventory")
        relations = {row.get("Id"): row.get("Target") for row in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        cells = []
        for index, sheet in enumerate(sheets, 1):
            name, last_row = sheet.get("name"), 59 if index == 1 else 58
            target = relations[sheet.get("{" + REL + "}id")]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            root = ET.fromstring(archive.read(path))
            if max(int(row.get("r")) for row in root.iter("{" + NS + "}row")) != last_row:
                raise ValueError("Changed native row extent")
            physical = {cell.get("r"): cell for cell in root.iter("{" + NS + "}c")}
            expected = {column_name(column) + str(row) for row in range(1, last_row + 1) for column in range(1, 28)}
            if set(physical) - expected:
                raise ValueError("Unreviewed native cells outside complete rectangle")
            for row in range(1, last_row + 1):
                for column in range(1, 28):
                    address = column_name(column) + str(row)
                    node = physical.get(address)
                    kind, value, raw = "blank", None, None
                    stored_type = node.get("t", "n") if node is not None else None
                    style = node.get("s") if node is not None else None
                    if node is not None:
                        if node.find("{" + NS + "}f") is not None:
                            raise ValueError("Unreviewed native formula; no execution or replacement")
                        cached = node.find("{" + NS + "}v")
                        raw = cached.text if cached is not None else None
                        if stored_type == "inlineStr":
                            kind, value = "text", "".join(part.text or "" for part in node.iter("{" + NS + "}t"))
                        elif stored_type == "str" and raw is not None:
                            kind, value = "text", raw
                        elif stored_type == "n" and raw is not None:
                            kind, value = "number", format(Decimal(raw).normalize(), "f")
                        elif stored_type not in ("str", "n"):
                            raise ValueError("Unreviewed native cell type")
                    cells.append(dict(sheet=name, cell=address, kind=kind, value=value,
                                      physical=node is not None, stored_type=stored_type, style_id=style, raw_value=raw))
        return cells


def native_count(cell, required=False):
    if cell["kind"] == "number" and re.fullmatch(r"\d+", cell["value"] or ""):
        return int(cell["value"])
    if required or not (cell["kind"] == "blank" or cell["kind"] == "text" and cell["value"] == ""):
        raise ValueError("Missing explicit numeric native total; no component fallback")
    return None


def registration_frame(cells, independent):
    if [{key: cell[key] for key in ("sheet", "cell", "kind", "value")} for cell in cells] != independent:
        raise ValueError("Independent full workbook readers disagree")
    indexed = {(cell["sheet"], cell["cell"]): cell for cell in cells}
    margins, diagnostics, groups = [], [], {}
    def equation(scope, parent, children):
        unknown = [key for key, value in children if value is None]
        known = sum(value for _, value in children if value is not None)
        diagnostics.append(dict(scope=scope, native_parent=parent, observed_child_subtotal=known,
                                unknown_child_cells=unknown, complete_equation_qualified=parent is not None and not unknown,
                                observed_subtotal_minus_parent=known - parent if parent is not None else None,
                                unknowns_not_recovered_by_complement=True))
    for number, race in enumerate(RACES, 1):
        sheet = "Sheet" + str(number)
        get = lambda address: indexed[(sheet, address)]
        header, start, parent_row = (10, 11, 58) if number == 1 else (9, 10, 57)
        if get("C1")["value"] != "RP0040" or get("B3")["value"] != "VR Totals by County / Race / Gender / Age":
            raise ValueError("Changed native registration report identity")
        if get("C" + str(7 if number == 1 else 6))["value"] != "Race: " + race:
            raise ValueError("Changed native race category; no demographic crosswalk")
        expected_headers = {"D": "Code", "F": "County Name", "H": "All Total"}
        expected_headers.update({column: "Total" if age == "All" else age for column, gender, age in SLOTS[1:]})
        if any(get(column + str(header))["value"] != label for column, label in expected_headers.items()):
            raise ValueError("Changed native count/age column semantics")
        if any(get(column + str(header - 1))["value"] != label for column, label in (("I", "Female"), ("O", "Male"), ("U", "Unknown"))):
            raise ValueError("Changed native administrative gender labels")
        if get("D" + str(parent_row))["value"] != "TOTAL":
            raise ValueError("Missing native statewide TOTAL; no county sum fallback")
        for row in [*range(start, start + 46), parent_row]:
            code, county = get("D" + str(row))["value"], get("F" + str(row))["value"]
            if row != parent_row and code != f"{row - start + 1:02}":
                raise ValueError("Changed native 46-county code inventory; not FIPS")
            if row != parent_row and (not isinstance(county, str) or not county):
                raise ValueError("Missing literal native county name")
            if number > 1 and row != parent_row and county != groups[("All", code)]["county"]:
                raise ValueError("Native county labels disagree across race views")
            counts = {column: native_count(get(column + str(row)), required=column == "H") for column, _, _ in SLOTS}
            groups[(race, code)] = dict(county=county, counts=counts, source_row=row)
            for column, gender, age in SLOTS:
                cell = get(column + str(row))
                margins.append(dict(sheet=sheet, source_row=row, race_label_native=race,
                                    county_code_literal=code, county_name_literal=county,
                                    gender_label_native=gender, age_label_native=age, cell=column + str(row),
                                    native_cell_kind=cell["kind"], native_value=cell["value"],
                                    native_registered_count=counts[column], missing_is_zero=False,
                                    registration_not_participation=True))
            equation(sheet + ":" + code + ":gender", counts["H"], [(column, counts[column]) for column in ("J", "P", "W")])
            for total_column, age_columns in (("J", ["K", "L", "M", "N"]), ("P", ["Q", "R", "S", "T"]), ("W", ["X", "Y", "Z", "AA"])):
                equation(sheet + ":" + code + ":" + total_column, counts[total_column], [(column, counts[column]) for column in age_columns])
        for column, _, _ in SLOTS:
            equation(sheet + ":county_sum:" + column, groups[(race, "TOTAL")]["counts"][column],
                     [(code, groups[(race, code)]["counts"][column]) for code in (f"{value:02}" for value in range(1, 47))])
    for code in [*(f"{value:02}" for value in range(1, 47)), "TOTAL"]:
        for column, _, _ in SLOTS:
            equation("race_sum:" + code + ":" + column, groups[("All", code)]["counts"][column],
                     [(race, groups[(race, code)]["counts"][column]) for race in RACES[1:]])
    total = groups[("All", "TOTAL")]["counts"]["H"]
    if total <= 0:
        raise ValueError("Missing positive native overall state parent")
    return total, margins, diagnostics


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-south-carolina-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete version18 baseline or pinned native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient native input")
        workbook = archive.read("registration.xlsx")
        if hashlib.sha256(workbook).hexdigest() != WORKBOOK_SHA:
            raise ValueError("Changed pinned original workbook")
        cells = decode_workbook(workbook)
        total, margins, diagnostics = registration_frame(cells, json.loads(archive.read("openpyxl-cells.json")))
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 35, 24):
        raise ValueError("Changed complete version18 coverage")
    target = next(row for row in states if row["state_code"] == "SC")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing South Carolina frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "SC" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
    time = "Declared report label November2,2026; embedded registration cutoff/report clock/timezone not stated"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=total, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="SC", year=2026, geographic_level="state", geography="South Carolina source-registration report",
                   source_family=URL, measure=MEASURE, native_measure="Explicit Race:All statewide TOTAL/All Total; registration stock, not participating voters",
                   numerator=None, denominator=total, denominator_basis=BASIS,
                   denominator_label="Native overall registration parent, not a sum of overlapping race/sex/age margins",
                   source_time_label=time, source_url=URL, native_status="Report-labelled registration stock; not election counting/certification",
                   source_kind="reviewed_public_registration_demographic_margins_workbook",
                   scope_notes="All9views/46counties plusnativeparents preserved. Blanksnotzero; sourcecountycode notFIPS. Administrativegender/race/Hispanic/age categories not automaticallyCPS/Civic-equivalent; no group/local probability allocation.",
                   selected_state_reference=False, disposition="registration_frame_no_independent_population_or_native_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="SC", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=total,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="native overall registration parent is exchangeable with source-weighted statewide survey propensity; report label is not qualified registration cutoff or demographic category match",
                    scenario_units="source_overall_registration_units_report_labelled_2026_11_02_cutoff_unknown_not_observed_people")
    scenarios.append(scenario)
    complete = [row for row in diagnostics if row["complete_equation_qualified"]]
    discrepancies = [row for row in complete if row["observed_subtotal_minus_parent"] != 0]
    missing = sum(row["native_registered_count"] is None for row in margins)
    qualification = dict(
        declared_report_label="2026-11-02", embedded_registration_cutoff_date=None, embedded_report_time=None, source_timezone=None,
        declared_file_label_not_promoted_to_registration_cutoff=True, native_registered_total_parent=total,
        native_active_registered_parent=None, native_inactive_parent=None, active_inactive_status_qualified=False,
        native_overall_parent_not_derived_from_gender_race_age_or_county_sums=True,
        nine_views_not_nine_populations=True, original_workbook_decoded_by_standard_library=True,
        complete_14121_cell_comparison_with_frozen_independent_openpyxl=True,
        native_race_labels=RACES, native_gender_labels=["Female", "Male", "Unknown"], native_age_labels=AGES,
        native_blank_or_empty_count_cells=missing, unknowns_not_inferred_zero_or_recovered_by_complement=True,
        source_county_codes_not_inferred_fips=True, native_cps_civic_race_ethnicity_gender_age_equivalence_qualified=False,
        native_group_registration_margins_are_not_group_participation=True,
        source_count_equations=len(diagnostics), complete_equations=len(complete),
        complete_equation_discrepancies=discrepancies, incomplete_equations_not_completed_as_zero=len(diagnostics)-len(complete),
        selected_native_statewide_ballot_reference=None, native_minus_model=None,
        source_population_transport_validated=False, election_time_population_independently_qualified=False,
        derived_state_frame_rate_approved=False, maps_approved=False, counting_completion_approved=False,
        certification_approved=False, generic_cast_ballot_measure_approved=False, county_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        source_workbook_sha256=WORKBOOK_SHA, no_raw_personal_records_private_survey_cells_or_compiled_app_code=True)
    frame = dict(state_code="SC", year=2026, declared_report_label="2026-11-02",
                 native_registration_cutoff=None, native_report_clock=None, native_registered_total_parent=total,
                 repeated_source_views_not_added=True, blanks_not_zero=True, population_transport_qualified=False,
                 conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
                 selected_native_statewide_ballots=None, native_minus_model=None, rate_approved=False, map_approved=False,
                 observed_staying_home=None, native_group_participation_inferred=False)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-workbook-cells.csv": csv_bytes(cells),
        "complete-native-registration-marginals.csv": csv_bytes(margins),
        "complete-south-carolina-registration-frame.csv": csv_bytes([frame]),
        "native-accounting-diagnostics.json": encoded(diagnostics),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=36, conditional_scenarios=25,
            conditional_registration_frame_added=1, native_statewide_ballot_controls_added=0,
            native_workbook_cells=len(cells), native_accounting_slots=len(margins), native_missing_count_cells=missing,
            native_counties_per_view=46, native_views=9, native_registered_total_parent=total,
            complete_equation_discrepancies=len(discrepancies),
            all_fifty_unaffected_states_twenty_four_prior_frames_and_thirty_five_controls_preserved=True,
            no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-south-carolina-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("south_carolina_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_south_carolina_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "SC nativeRP0040Race:All TOTAL/AllTotal3470220 registrationstock, NOT participatingvoters.\n"
        "DeclaredNovember2reportlabel is NOTembeddedregistrationcutoff/clock/timezone; active/inactivestatusunknown.\n"
        "All9raceviews/46counties+TOTAL/gender+age margins preserved; Allview and8raceviews are NOT9populations.\n"
        "NativeFemale/Male/Unknown and18-24/25-44/45-64/65-Up categories are NOT automaticallyCPS/Civic-equivalent.\n"
        "Blanksnotzero/complementrecoveries; numericzerosremainobservedzeros. County01..46are NOT inferredFIPS.\n"
        "Nativegroupregistrationmargins are NOTgroupturnout; nogroup/local allocation of source survey probabilities.\n"
        "Conditionaloverallregisteredunits assumeunvalidatedCivictransport; no observedstayinghome/ballots/residual/rate/mapapproval.\n"
        "Default numerical reproduction decodesoriginalOOXMLstdlib and comparesallcells tofrozenindependentopenpyxl snapshot.\n"
        "Complete originalworkbook/independent snapshot+receipt/version18baseline/maintainedcode/tests/allqueries/checksums.\n"
        "python3 -m unittest discover -s tests -p test_south_carolina_register.py\n"
        "python3 -m scripts.south_carolina_register --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) for name, body in sorted(files.items())})
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
