"""Keep D.C. registration, voting-mode reports, and absent survey models separate."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .extract_dc_native_reports import ORIGINALS, comparable, normalized
from .washington_register_control import csv_bytes, encoded


BASELINE_SHA = "5fe02b9da970fb3d1a5abc01a9751f3b8e9885a4e1b2d2d048284bc1da9a65cf"
NATIVE_SHA = "a022ecbd8a5949d92784c643adde53b192cc8389efe289283115a3f628a4bad5"
PARTIES = ("DEM", "REP", "STG", "N-P", "OTH", "TOTALS")


def count(value):
    value = normalized(value)
    if value is None:
        return None
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", value):
        raise ValueError("Invalid native count; no zero imputation or coercion")
    return int(value.replace(",", ""))


def native_tables(primary, independent, scope):
    if comparable(primary) != comparable(independent):
        raise ValueError("Independent complete factual PDF readers disagree")
    if ([report["id"] for report in primary["reports"]] != list(ORIGINALS)
            or any(report["source_sha256"] != ORIGINALS[report["id"]] for report in primary["reports"])):
        raise ValueError("Changed original native source inventory")
    if (scope["source_registration_snapshot_date"] != "2026-09-30"
            or scope["dc_has_no_civic_sample_no_pooled_state_projection"] is not True
            or scope["different_modes_and_cutoffs_not_added_into_allmode_cast_or_unique_people"] is not True
            or scope["mail_received_is_accepted_or_cast_ballot_qualified"] is not False
            or scope["vote_center_ward_is_voter_residence_qualified"] is not False):
        raise ValueError("Changed date, model absence, receipt, or location-versus-residence qualification")
    reports = {report["id"]: report for report in primary["reports"]}
    grids, registrations, modes, equations = [], [], [], []
    for report in primary["reports"]:
        for page in report["pages"]:
            for table_number, table in enumerate(page["tables"], 1):
                for row_number, row in enumerate(table["rows"], 1):
                    for column, value in enumerate(row, 1):
                        grids.append(dict(report_id=report["id"], page=page["page"], table=table_number,
                            source_row=row_number, source_column=column, raw_native_cell=value,
                            normalized_native_cell=normalized(value),
                            cell_has_native_text=normalized(value) is not None, missing_imputed_zero=False))

    def equation(report, identity, parent, terms):
        missing = sum(value is None for value in terms)
        observed = sum(value for value in terms if value is not None)
        full = parent is not None and missing == 0
        equations.append(dict(report_id=report, identity=identity, native_parent=parent,
            observed_component_sum=observed, missing_components=missing, complete=full,
            difference=observed - parent if full else None, missing_imputed_zero=False))

    reg = reports["DC-september-registration"]
    if len(reg["pages"]) != 9:
        raise ValueError("Incomplete citywide and all-eight-ward registration grids")
    if ([page["external"]["native_registration_scope"] for page in reg["pages"]].count("citywide") != 1
            or {page["external"]["native_registration_ward"] for page in reg["pages"]
                if page["external"]["native_registration_scope"] == "ward"} != set("12345678")):
        raise ValueError("Missing or repeated explicit native registration ward headers")
    for page in reg["pages"]:
        if len(page["tables"]) != 1:
            raise ValueError("Changed native registration table inventory")
        rows = page["tables"][0]["rows"]
        citywide_page = page["external"]["native_registration_scope"] == "citywide"
        native_ward = page["external"]["native_registration_ward"]
        expected_header = ["WARD" if citywide_page else "PRECINCT", *PARTIES]
        if [normalized(value) for value in rows[1] if normalized(value)] != expected_header:
            raise ValueError("Changed native registration columns")
        for index, row in enumerate(rows[2:], 3):
            if len(row) != 21 or any(normalized(value) is not None
                                      for column, value in enumerate(row) if column % 3):
                raise ValueError("Changed merged-cell layout; do not shift native counts")
            label = normalized(row[0])
            if label == "Percentage by Party":
                continue
            if label is None:
                raise ValueError("Missing native registration geography")
            values = [count(row[column]) for column in range(3, 21, 3)]
            registration = dict(report_id=reg["id"], page=page["page"], source_row=index,
                native_geography_label=label,
                native_ward_label=label if citywide_page and label != "TOTALS" else (
                    native_ward if not citywide_page else None),
                geographic_level=("citywide" if label == "TOTALS" and citywide_page else
                                  "ward" if citywide_page or label == "TOTALS" else "precinct"),
                native_scope=page["external"]["native_registration_scope"],
                source_snapshot_date="2026-09-30", active_inactive_status_qualified=False,
                registration_affiliation_is_vote_choice=False, geographic_codes_inferred=False)
            registration.update(zip(PARTIES, values))
            registrations.append(registration)
            equation(reg["id"], f"page{page['page']}-row{index}-party-accounting", values[-1], values[:-1])
    city = next(row for row in registrations if row["geographic_level"] == "citywide")
    precincts = [row for row in registrations if row["geographic_level"] == "precinct"]
    if (city["TOTALS"] is None or city["TOTALS"] <= 0 or len(precincts) != 144
            or len({row["native_geography_label"] for row in precincts}) != 144):
        raise ValueError("Missing explicit citywide parent or complete unique source precincts")
    for ward in range(1, 9):
        first = next(row for row in registrations if row["native_scope"] == "citywide" and row["native_ward_label"] == str(ward))
        second = next(row for row in registrations if row["native_scope"] == "ward"
                      and row["native_ward_label"] == str(ward) and row["native_geography_label"] == "TOTALS")
        leaves = [row for row in precincts if row["native_ward_label"] == str(ward)]
        for field in PARTIES:
            equation(reg["id"], f"ward{ward}-{field}-all-native-precincts", second[field], [row[field] for row in leaves])
            equation(reg["id"], f"ward{ward}-{field}-repeated-parent", first[field], [second[field]])
    for field in PARTIES:
        equation(reg["id"], "citywide-" + field, city[field],
                 [row[field] for row in registrations if row["native_scope"] == "citywide"
                  and row["geographic_level"] == "ward"])

    def mode(report, row, column, label, value, period=None, ward=None, level=None, measure=None):
        result = dict(report_id=report, source_row=row, source_column=column,
            native_geography_label=label, native_location_ward=ward, geographic_level=level,
            native_period_label=period, raw_native_count=value, native_count=count(value),
            native_measure=measure, geography_is_voter_residence_qualified=False,
            accepted_or_generic_cast_ballots_qualified=False,
            allmode_or_unique_people_count_qualified=False, missing_imputed_zero=False)
        modes.append(result)
        return result["native_count"]

    early = reports["DC-early"]["pages"][0]
    rows = early["tables"][0]["rows"]
    headers = [normalized(value) for value in rows[0]]
    if headers != [None, "26-Oct", "27-Oct", "28-Oct", "29-Oct", "30-Oct", "31-Oct", "1-Nov", "TOTAL"]:
        raise ValueError("Changed native early-voting day columns")
    wards = early["external"]["native_location_ward_labels"]
    if len(rows) != 29 or len(wards) != 27 or normalized(rows[-1][0]) != "TOTAL":
        raise ValueError("Incomplete native early-vote-center grid")
    early_values = []
    for index, row in enumerate(rows[1:], 2):
        if len(row) != 9:
            raise ValueError("Changed early-voting columns")
        values = [mode("DC-early", index, column + 1, row[0], row[column], headers[column],
            wards[index - 2] if index < len(rows) else None,
            "vote_center" if index < len(rows) else "source_report_total",
            "native_early_vote_center_report_count") for column in range(1, 9)]
        early_values.append(values)
        if index < len(rows):
            equation("DC-early", f"center-row{index}", values[-1], values[:-1])
    for column in range(8):
        equation("DC-early", "source-column" + str(column + 2), early_values[-1][column],
                 [row[column] for row in early_values[:-1]])
    equation("DC-early", "explicit-grand-vs-daily-parents", early_values[-1][-1], early_values[-1][:-1])
    early_parent = early_values[-1][-1]

    day = reports["DC-election-day"]["pages"][0]
    if len(day["tables"]) != 8:
        raise ValueError("Incomplete native Election Day location-ward tables")
    day_parents, day_leaves = [], []
    for table_number, table in enumerate(day["tables"], 1):
        rows = table["rows"]
        header = re.fullmatch(r"WARD ([1-8]) (\d+)", normalized(rows[0][0]) or "")
        if not header or int(header.group(1)) != table_number:
            raise ValueError("Changed native vote-center ward parent")
        ward = header.group(1)
        parent = mode("DC-election-day", f"table{table_number}-header", 1, "WARD " + ward,
            header.group(2), ward=ward, level="source_location_ward_parent",
            measure="native_election_day_in_person_report_count")
        leaves = []
        for number, row in enumerate(rows[1:], 2):
            if all(normalized(value) is None for value in row):
                continue
            if len(row) != 2 or normalized(row[0]) is None:
                raise ValueError("Unlabelled native Election Day count")
            leaves.append(mode("DC-election-day", f"table{table_number}-row{number}", 2, row[0], row[1],
                ward=ward, level="vote_center", measure="native_election_day_in_person_report_count"))
        equation("DC-election-day", "location-ward" + ward, parent, leaves)
        day_parents.append(parent)
        day_leaves.extend(leaves)
    day_parent = day["external"].get("native_election_day_parent")
    if type(day_parent) is not int or day_parent <= 0:
        raise ValueError("Missing explicit native Election Day parent; no ward-sum replacement")
    mode("DC-election-day", "outside-grid-native-parent", None, "ELECTION DAY IN-PERSON",
         str(day_parent), level="source_report_total", measure="native_election_day_in_person_report_count")
    equation("DC-election-day", "explicit-citywide-vs-location-wards", day_parent, day_parents)
    equation("DC-election-day", "explicit-citywide-vs-all-centers", day_parent, day_leaves)

    drop = reports["DC-dropbox"]["pages"][0]["tables"][0]["rows"]
    if [normalized(value) for value in drop[0]] != [None, *["WARD " + str(number) for number in range(1, 9)], "TOTAL"]:
        raise ValueError("Changed native drop-box location-ward columns")
    drop_values = []
    for index, row in enumerate(drop[1:], 2):
        if len(row) != 10:
            raise ValueError("Changed native drop-box grid")
        values = [mode("DC-dropbox", index, column + 1,
            "WARD " + str(column) if column < 9 else "source_total", row[column],
            normalized(row[0]), str(column) if column < 9 else None,
            "source_location_ward" if column < 9 else "source_report_total",
            "native_drop_box_mail_ballots_received") for column in range(1, 10)]
        drop_values.append(values)
        equation("DC-dropbox", "source-row" + str(index), values[-1], values[:-1])
    if normalized(drop[-1][0]) != "TOTAL":
        raise ValueError("Missing explicit native drop-box parent")
    for column in range(9):
        equation("DC-dropbox", "source-column" + str(column + 2), drop_values[-1][column],
                 [row[column] for row in drop_values[:-1]])
    drop_parent = drop_values[-1][-1]

    usps = reports["DC-usps"]["pages"][0]["tables"][0]["rows"]
    usps_values = []
    for index, row in enumerate(usps, 1):
        if len(row) != 2 or normalized(row[0]) is None:
            raise ValueError("Changed native USPS daily grid")
        usps_values.append(mode("DC-usps", index, 2, "District of Columbia", row[1],
            normalized(row[0]), level="source_report_total", measure="native_usps_mail_ballots_received"))
    if normalized(usps[-1][0]) != "TOTAL" or usps_values[-1] is None:
        raise ValueError("Missing explicit native USPS parent")
    equation("DC-usps", "explicit-parent-vs-all-native-dates", usps_values[-1], usps_values[:-1])
    parents = {reg["id"]: city["TOTALS"], "DC-early": early_parent,
               "DC-election-day": day_parent, "DC-dropbox": drop_parent, "DC-usps": usps_values[-1]}
    if any(type(value) is not int or value <= 0 for value in parents.values()):
        raise ValueError("Missing explicit native source parent")
    return grids, registrations, modes, equations, parents


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-dc-native-factual-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete version24 baseline or sufficient native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        checksums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(checksums) | {"checksums.json"}:
            raise ValueError("Changed complete factual input inventory")
        for name, metadata in checksums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        scope = json.loads(archive.read("source-scope.json"))
        grids, registrations, modes, equations, parents = native_tables(
            json.loads(archive.read("primary-grids.json")),
            json.loads(archive.read("independent-grids.json")), scope)
        receipts = json.loads(archive.read("source-receipts.json"))
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 43, 31):
        raise ValueError("Changed complete version24 coverage")
    dc = next(row for row in states if row["state_code"] == "DC")
    if (dc["civic_source_n"] or dc["civic_modeled_voter_pct"] or dc["civic_modeled_nonvoter_pct"]
            or dc["conditional_registered_frame_scenario_available"] != "False"
            or dc["control_id"] != "dc-2026-held-citywide-ballots"
            or dc["reported_cast_ballots"] != "185086" or dc["control_registered_denominator"] != "457371"):
        raise ValueError("Preserve absent D.C. source model and existing separate citywide reference")
    summaries = []
    for report_id, parent in parents.items():
        registered = report_id == "DC-september-registration"
        receipt = next(row for row in receipts if row["sha256"] == ORIGINALS[report_id])
        measure = ("native_dated_registration_stock" if registered else
                   next(row["native_measure"] for row in modes if row["report_id"] == report_id))
        control_id = "dc-2026-source-" + report_id.removeprefix("DC-").lower()
        if any(row["id"] == control_id for row in controls):
            raise ValueError("Do not duplicate a prior native source")
        label = ("September30,2026 registered stock; exact clock/timezone and active/inactive status unknown"
                 if registered else "Native daily/location report labels only; count cutoff/clock/timezone unqualified; filenames not timestamps")
        control = dict(controls[0])
        control.update(id=control_id, state_code="DC", year=2026, geographic_level="district",
            geography="District of Columbia separate " + report_id, source_family=receipt["requested_url"],
            measure=measure, native_measure=measure, numerator=None if registered else parent,
            denominator=parent if registered else None,
            denominator_basis="native_September30_monthly_registration_TOTALS" if registered else None,
            denominator_label="Dated registration stock, not linked to election counts" if registered else None,
            source_time_label=label, source_url=receipt["requested_url"],
            native_status="Published native source report; no completion or certification qualification",
            source_kind="reviewed_official_complete_factual_pdf_grids",
            scope_notes="D.C.has no Civic sample; no projected model or allocation. Separate mode/cutoff reports are not added into all-mode cast ballots/unique people. Received mail is not accepted/cast. Location wards are not voter residence. Prior185086ballot/457371registration reference unchanged; source blanks stay unknown.",
            selected_state_reference=False,
            disposition="separate_dated_registration_no_survey_projection" if registered else
                        "separate_native_mode_report_not_generic_allmode_cast_reference")
        controls.append(control)
        summaries.append(dict(report_id=report_id, native_measure=measure, native_count=parent,
            source_registration_date="2026-09-30" if registered else None,
            source_url=receipt["requested_url"], exact_count_cutoff=None, exact_clock=None, timezone=None,
            allmode_cast_ballots_qualified=False, unique_people_qualified=False,
            voter_residence_geography_qualified=False, conditional_model_available=False,
            design_confidence_interval=None, matched_native_registration_denominator=None,
            observed_staying_home=None, rate_approved=False, map_approved=False))
    availability = dict(state_code="DC", civic_source_n=None, civic_sample_available=False,
        source_registration_count_context=parents["DC-september-registration"],
        new_dated_register_repairs_missing_survey_sample=False, pooled_state_propensity_projected=False,
        model_probability=None, conditional_modeled_participant_units=None,
        conditional_modeled_nonparticipant_units=None, native_minus_model=None,
        original_coalition_population_count=None, death_component=None, migration_component=None,
        eligibility_component=None, design_confidence_interval=None, local_or_group_allocation=False)
    complete = [row for row in equations if row["complete"]]
    qualification = dict(source_registration_snapshot_date="2026-09-30",
        active_inactive_status_qualified=False, native_clock=None, native_timezone=None,
        dc_has_no_civic_sample_no_projection=True, prior_dc_185086_ballots_and457371_denominator_unchanged=True,
        all51_prior_state_rows_43_controls_31_scenarios_byte_preserved=True,
        modes_and_cutoffs_not_added_into_generic_cast_or_unique_people=True,
        mail_received_not_qualified_accepted_or_cast=True, location_ward_not_qualified_voter_residence=True,
        dated_registration_not_linked_to_mode_report_denominator=True,
        filename_not_count_cutoff_or_publication_clock=True, blanks_not_zero_or_future_cutoff=True,
        observed_zero_literals_retained_not_population_or_completion_certification=True,
        registration_affiliation_not_vote_choice=True, missing_imputed_zero=False,
        registration_ward_identity_from_printed_headers_not_page_ordinals=True,
        native_accounting_equations=len(equations), complete_equations=len(complete),
        incomplete_equations=len(equations) - len(complete),
        discrepancies=[row for row in complete if row["difference"]],
        new_conditional_model_or_population_validation=False, group_or_local_survey_allocation=False,
        native_allmode_ballots_from_new_reports=None, modeled_staying_home=None,
        native_minus_model=None, design_confidence_interval=None,
        rates_approved=False, maps_approved=False, new_website_view=False,
        mi_and_tn_new_403_routes_stopped_no_cached_numbers_used=True,
        full_contact_prose_web_bodies_compiled_app_code_and_denied_bodies_locally_held_only=True)
    count_values = [row[field] for row in registrations for field in PARTIES] + [row["native_count"] for row in modes]
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-dc-native-grid-cells.csv": csv_bytes(grids),
        "complete-dc-native-registration.csv": csv_bytes(registrations),
        "complete-dc-native-mode-counts.csv": csv_bytes(modes),
        "complete-dc-native-accounting.csv": csv_bytes(equations),
        "complete-dc-source-summaries.csv": csv_bytes(summaries),
        "complete-dc-model-availability.csv": csv_bytes([availability]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=48, conditional_scenarios=31,
            native_pages=13, native_tables=20, native_grid_slots=len(grids),
            native_registration_records=len(registrations), native_unique_precincts=144,
            native_mode_count_slots=len(modes), native_count_slots=len(count_values),
            native_unknown_count_slots=sum(value is None for value in count_values),
            native_observed_zero_literals=sum(value == 0 for value in count_values),
            complete_equations=len(complete), incomplete_equations=len(equations) - len(complete),
            native_accounting_discrepancies=len(qualification["discrepancies"]),
            all51_prior_state_rows_43_controls_31_scenarios_preserved=True,
            no_dc_survey_projection_no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-dc-native-factual-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("dc_native_reports.py", "extract_dc_native_reports.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_dc_native_reports.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "D.C. separate dated registration and native voting-mode reports, not a new all-mode turnout count.\n"
        "September30,2026 registrations453471; old185086ballots/457371denominator reference stays unchanged.\n"
        "EVC27118 andElectionDayInPerson72903 are native report counts; receivedDropBox53736/USPS45376\n"
        "are NOT qualified accepted/cast ballots. Do NOT add across modes/cutoffs or infer unique people.\n"
        "Vote-center/drop-box location wards are not independently qualified voter residence; no ward rates.\n"
        "All complete factual grids, native blanks/zero literals/merged cells/date columns retained.\n"
        "USPSfuture/unknown blanks and dropNov3ward blanks despite printedtotal0 are NOT imputed zero.\n"
        "D.C.has NO Civic survey sample. Dated registration does NOT repair it; no state-pooled projection.\n"
        "No new conditional model, linked registration denominator, residual, staying-home claim or fakeCI.\n"
        "Complete factual primary/independentviews/receipts/qualified baseline24/code/tests/queries/checksums.\n"
        "Full original contact prose, compiledappcode, deniedbodies and personal records stay outside downloads.\n"
        "python3 -m unittest discover -s tests -p test_dc_native_reports.py\n"
        "python3 -m scripts.dc_native_reports --inputs inputs --output reproduced\n").encode()
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
