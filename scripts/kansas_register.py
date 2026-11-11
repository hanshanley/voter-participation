"""Use Kansas's dated workbook parent; preserve blank cells and repeated margins."""

import argparse
import csv
from datetime import datetime, timedelta
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


BASELINE_SHA = "d4d0d4ca4baf0c326ef84e0c98ffd7f122d83870eabf037ea5271e0642e17cc7"
WORKBOOK_SHA = "8c048f8d236b679d1e8e49be8cdc3c7f2ddc8d32e13a23daee72501efd700e52"
NATIVE_SHA = "f31f0a5df6f3898d80c4f912912695bfcd24eb656a8fd94ea3feb9e803238ce2"
URL = "https://sos.ks.gov/elections/vr-statistics/2026/10-2026-Voter-Registration-Numbers-by-County.xlsx"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SHEETS = {"By County": (107, 10), "By Congressional District": (6, 9),
          "By KS House": (127, 9), "By KS Senate": (42, 9)}
PARTIES = ["Democratic", "Libertarian", "No Labels Kansas", "Republican",
           "United Kansas", "Unaffiliated", "Total"]
CONTROL = "ks-2026-native-20261001-Grand-Total-registration-parent"
BASIS = "native_2026_10_01_Grand_Total_parent_blank_party_cells_preserved"
MEASURE = "native_dated_total_registration_snapshot_no_independent_population_transport"


def decode_workbook(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        properties = workbook.find("{" + NS + "}workbookPr")
        if properties is not None and properties.get("date1904", "0") not in ("0", "false"):
            raise ValueError("Changed native Excel date epoch")
        relations = {row.get("Id"): row.get("Target") for row in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        strings = ["".join(part.text or "" for part in item.iter("{" + NS + "}t"))
                   for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        styles = list(ET.fromstring(archive.read("xl/styles.xml")).find("{" + NS + "}cellXfs"))
        native_sheets = list(workbook.find("{" + NS + "}sheets"))
        if [row.get("name") for row in native_sheets] != list(SHEETS):
            raise ValueError("Changed complete native worksheet inventory")
        cells = []
        for sheet in native_sheets:
            name = sheet.get("name")
            target = relations[sheet.get("{" + REL + "}id")]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            root = ET.fromstring(archive.read(path))
            row_count, columns = SHEETS[name]
            dimension = root.find("{" + NS + "}dimension").get("ref")
            if dimension != "A1:" + chr(64 + columns) + str(row_count):
                raise ValueError("Changed native rectangular worksheet coverage")
            physical = {cell.get("r"): cell for cell in root.iter("{" + NS + "}c")}
            for row in range(1, row_count + 1):
                for column in range(1, columns + 1):
                    address = chr(64 + column) + str(row)
                    node = physical.get(address)
                    value_node = node.find("{" + NS + "}v") if node is not None else None
                    formula = node.find("{" + NS + "}f") if node is not None else None
                    raw = value_node.text if value_node is not None else None
                    stored_type = node.get("t", "n") if node is not None else None
                    style = node.get("s") if node is not None else None
                    kind, value = "blank", None
                    if node is not None and stored_type == "s":
                        kind, value = "text", strings[int(raw)]
                    elif node is not None and stored_type == "str":
                        kind, value = "text", raw or ""
                    elif node is not None and stored_type == "inlineStr":
                        kind, value = "text", "".join(part.text or "" for part in node.iter("{" + NS + "}t"))
                    elif raw is not None and stored_type == "n":
                        number = Decimal(raw)
                        if column == 1 and row > 1:
                            if style is None or styles[int(style)].get("numFmtId") != "14" or number != int(number):
                                raise ValueError("Unreviewed native date style or time-of-day")
                            kind, value = "date", (datetime(1899, 12, 30) + timedelta(days=int(number))).date().isoformat()
                        else:
                            kind, value = "number", format(number.normalize(), "f")
                    elif raw is not None:
                        raise ValueError("Unreviewed native cell type")
                    cells.append(dict(sheet=name, cell=address, kind=kind, value=value,
                                      physical=node is not None, stored_type=stored_type, style_id=style,
                                      raw_value=raw, formula_present=formula is not None,
                                      formula_text=(formula.text or "") if formula is not None else None,
                                      formula_attributes=dict(formula.attrib) if formula is not None else {}))
        return cells


def count(cell):
    if cell["kind"] != "number" or not re.fullmatch(r"\d+", cell["value"] or ""):
        raise ValueError("Missing explicit numeric native total; no party/county fallback")
    return int(cell["value"])


def registration_frame(cells, independent):
    canonical = [{key: cell[key] for key in ("sheet", "cell", "kind", "value")} for cell in cells]
    if canonical != independent:
        raise ValueError("Independent full workbook cell readers disagree")
    by_address = {(cell["sheet"], cell["cell"]): cell for cell in cells}
    parents, accounting, diagnostics = {}, [], []
    for sheet, (row_count, columns) in SHEETS.items():
        get = lambda address: by_address[(sheet, address)]
        header = [get(chr(65 + column) + "1")["value"] for column in range(columns)]
        expected = ["Date", "County", "Column1", *PARTIES] if sheet == "By County" else [
            "Date", {"By Congressional District": "U.S. Congressional District",
                     "By KS House": "Kansas State House of Representatives",
                     "By KS Senate": "Kansas Senate District"}[sheet], *PARTIES]
        if header != expected:
            raise ValueError("Changed native column semantics")
        labels, parent_rows = [], []
        for row in range(2, row_count + 1):
            date, label = get("A" + str(row)), get("B" + str(row))["value"]
            if date["kind"] != "date" or date["value"] != "2026-10-01":
                raise ValueError("Changed native snapshot date; midnight is not a report clock")
            if not isinstance(label, str) or not label:
                raise ValueError("Missing native geography label")
            labels.append(label)
            if label == "Grand Total":
                parent_rows.append(row)
            values, missing = [], []
            for offset, party in enumerate(PARTIES):
                address = chr(64 + columns - 6 + offset) + str(row)
                cell = get(address)
                observed = None
                if cell["kind"] == "number":
                    observed = count(cell)
                elif not (cell["kind"] == "blank" or cell["kind"] == "text" and cell["value"] == ""):
                    raise ValueError("Unreviewed native party count type")
                if observed is None:
                    missing.append(party)
                values.append(observed)
                accounting.append(dict(sheet=sheet, source_row=row, native_date=date["value"],
                                       geography_literal=label, native_column_label=party, cell=address,
                                       native_cell_kind=cell["kind"], native_value=cell["value"],
                                       native_count=observed, missing_is_zero=False,
                                       repeated_geographic_margins_not_additive=True))
            total = count(get(chr(64 + columns) + str(row)))
            known_sum = sum(value for value in values[:-1] if value is not None)
            diagnostics.append(dict(sheet=sheet, source_row=row, geography_literal=label,
                                    native_total=total, observed_party_subtotal=known_sum,
                                    observed_subtotal_minus_native_total=known_sum - total,
                                    unknown_party_cells=missing,
                                    exhaustive_party_partition_qualified=not missing,
                                    blanks_not_repaired=True))
        if len(parent_rows) != 1:
            raise ValueError("Missing or duplicate native Grand Total; no marginal fallback")
        if len(set(labels)) != row_count - 1:
            raise ValueError("Duplicate native geography labels")
        prefix = {"By Congressional District": "U.S. Representative ", "By KS House": "Kansas Representative ",
                  "By KS Senate": "Kansas Senate "}.get(sheet)
        if prefix and set(labels) - {"Grand Total"} != {prefix + str(value) for value in range(1, row_count - 1)}:
            raise ValueError("Incomplete native district inventory")
        parent_row = parent_rows[0]
        parents[sheet] = count(get(chr(64 + columns) + str(parent_row)))
        county_sum = sum(count(get(chr(64 + columns) + str(row))) for row in range(2, row_count + 1) if row != parent_row)
        if county_sum != parents[sheet]:
            raise ValueError("Native geographic totals disagree; no parent repair")
    if min(parents.values()) <= 0 or len(set(parents.values())) != 1:
        raise ValueError("Repeated native state parents disagree; do not add margins")
    return parents["By County"], accounting, diagnostics, parents


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-kansas-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed complete version16 baseline or frozen native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed native input coverage")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient native input")
        workbook = archive.read("registration.xlsx")
        if hashlib.sha256(workbook).hexdigest() != WORKBOOK_SHA:
            raise ValueError("Changed pinned original workbook")
        cells = decode_workbook(workbook)
        total, accounting, diagnostics, parents = registration_frame(cells, json.loads(archive.read("openpyxl-cells.json")))
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 33, 22):
        raise ValueError("Changed complete version16 coverage")
    target = next(row for row in states if row["state_code"] == "KS")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Kansas frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "KS" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
    time = "Native Date column October1,2026; date-only Excel style, not an observed midnight clock; timezone absent"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=total, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="KS", year=2026, geographic_level="state", geography="Kansas dated total-registration snapshot",
                   source_family=URL, measure=MEASURE, native_measure="Explicit By County Grand Total; repeated district margins not additive",
                   numerator=None, denominator=total, denominator_basis=BASIS,
                   denominator_label="Native dated Grand Total; blank party cells not inferred zero; active/inactive status unspecified",
                   source_time_label=time, source_url=URL, native_status="Dated registration report; not election counting/certification",
                   source_kind="reviewed_public_dated_total_registration_workbook",
                   scope_notes="All4sheets/105counties/4USHouse/125KSHouse/40KSSenate+four repeated state parents preserved. Party accounting is not voting; no missing-party complements or local model allocation.",
                   selected_state_reference=False, disposition="dated_register_frame_no_independent_population_or_native_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="KS", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=total,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="native 10/1/2026 total-registration parent is exchangeable with source-weighted statewide survey propensity; blank party cells and active/inactive status remain unqualified",
                    scenario_units="dated_2026_10_01_native_total_registration_units_not_administratively_observed_people")
    scenarios.append(scenario)
    qualification = dict(
        native_source_date="2026-10-01", native_time_of_day=None, native_timezone=None,
        excel_date_only_style_not_observed_midnight=True, native_registered_total_parent=total,
        native_active_registered_parent=None, native_inactive_parent=None, active_inactive_status_qualified=False,
        repeated_native_grand_totals=parents, repeated_margins_counted_once=True,
        complete_four_worksheet_inventory_preserved=True, complete_workbook_cell_reader_comparison=True,
        workbook_cells=len(cells), native_accounting_cells=len(accounting),
        native_blank_or_empty_party_cells=sum(row["native_count"] is None for row in accounting),
        no_labels_kansas_blanks_not_inferred_zero=True, native_empty_strings_distinct_from_absent_cells=True,
        party_partition_exhaustiveness_qualified=False, missing_party_cells_not_recovered_by_complement=True,
        original_shared_formula_text_attributes_and_cached_values_preserved_without_execution=True,
        source_party_affiliation_is_registration_accounting_not_votes=True,
        district_rows_not_independent_populations_or_geometry_approval=True,
        november_december_index_entries_unlinked_not_guessed=True,
        selected_native_statewide_ballot_reference=None, native_minus_model=None,
        survey_population_transport_validated=False, election_time_population_independently_qualified=False,
        derived_state_frame_rate_approved=False, maps_approved=False, counting_completion_approved=False,
        certification_approved=False, generic_cast_ballot_measure_approved=False, county_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        source_workbook_sha256=WORKBOOK_SHA, native_parent_not_derived_from_party_or_county_sums=True,
        numerical_analysis_decodes_original_workbook_with_standard_library=True,
        optional_independent_snapshot_refresh_requires_openpyxl=True)
    cell_rows = [{**cell, "formula_attributes": json.dumps(cell["formula_attributes"], sort_keys=True)} for cell in cells]
    frame = dict(state_code="KS", year=2026, native_source_date="2026-10-01", native_registered_total_parent=total,
                 repeated_source_parents_counted_once=True, blank_party_cells_not_zero=True,
                 active_inactive_status_qualified=False, population_transport_qualified=False,
                 conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
                 selected_native_statewide_ballots=None, native_minus_model=None, rate_approved=False,
                 map_approved=False, observed_staying_home=None)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-workbook-cells.csv": csv_bytes(cell_rows),
        "complete-native-registration-accounting.csv": csv_bytes(accounting),
        "complete-kansas-registration-frame.csv": csv_bytes([frame]),
        "native-accounting-diagnostics.json": encoded(diagnostics),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=34, conditional_scenarios=23,
            dated_registration_frame_added=1, native_statewide_ballot_controls_added=0,
            native_county_rows=105, native_district_rows=169, repeated_native_state_parents=4,
            native_workbook_cells=len(cells), native_accounting_cells=len(accounting),
            native_blank_or_empty_party_cells=qualification["native_blank_or_empty_party_cells"],
            native_registered_total_parent=total,
            all_fifty_unaffected_states_twenty_two_prior_frames_and_thirty_three_controls_preserved=True,
            no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-kansas-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("kansas_register.py", "extract_kansas_registration.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_kansas_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Kansas native ByCountyGrandTotal2027520 dated10/1/2026, date-only Excel cells NOT observed midnight/TZ.\n"
        "All4sheets/105counties/4USHouse/125KSHouse/40KSSenate +4repeated state parents preserved; count populationONCE.\n"
        "AllNoLabelsKansas blank cells and nativeUnitedKansas emptystrings remain unknown, NOTzero/complement recoveries.\n"
        "NativeGrandTotal is direct, not a sum of parties/counties/fourgeographicmargins. Affiliation is NOT voting behavior.\n"
        "Original XLSX/raw cell types/styles/shared formula text+attrs/cached labels preserved; no formula execution.\n"
        "Numerical analysis decodes original OOXML with stdlib and compares allcells to frozen independentopenpyxl snapshot.\n"
        "No state ballot reference/residual/new rate/map/population approval/local model allocation/observed stayinghome.\n"
        "Complete native inputs, entireversion16baseline, maintained code/tests/allqueries/checksums included.\n"
        "python3 -m unittest discover -s tests -p test_kansas_register.py\n"
        "python3 -m scripts.kansas_register --inputs inputs --output reproduced\n"
        "Optional independent snapshot refresh requiresopenpyxl: unzip inputs/complete-kansas-native-inputs.zip -d native\n"
        "python3 -m scripts.extract_kansas_registration --workbook native/registration.xlsx --output refreshed-independent\n"
        "November/December index entries were unlinked; no file/clock/activepopulation invented.\n").encode()
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
