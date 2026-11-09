"""A dated Idaho register scenario, not a repair of election-report registrations."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "f721fb06dc9e4f28e9d392065a4858ccfc316c0696419d1faa93393d09d7a9e6"
NATIVE_SHA = "ada9fa61b1bba0b4d6b0a331f233e3553c309a0c63c54b0419f2af9d43061a34"
SOURCE_SHA = {
    "County": "4cce58411fd267af49b613ed651f6b4abec58dbe1a848cb91acdae3c108e72df",
    "Legislative": "662170eff3e5fb5016972c8dc87824088ef44c3faec24c41290772fcc9a29e57",
    "Congressional": "c32c9cc692b3148e6c5524082dea677d764872b2e0375d70bbc349cdbf6a0edd",
}
CONTROL = "id-2026-native-monthly-registration-202611"
MEASURE = "native_month_labelled_registration_total_cutoff_not_qualified"
BASIS = "native_202611_CountyTotals_Total_corroborated_by_two_district_views_status_unspecified"
URL = "https://archive.voteidaho.gov/data/voter-registrations/202611_CountyTotals.csv"
PARTIES = ["CON", "DEM", "LIB", "REP", "UNA", "Total"]
COUNTIES = "ADA|ADAMS|BANNOCK|BEAR LAKE|BENEWAH|BINGHAM|BLAINE|BOISE|BONNER|BONNEVILLE|BOUNDARY|BUTTE|CAMAS|CANYON|CARIBOU|CASSIA|CLARK|CLEARWATER|CUSTER|ELMORE|FRANKLIN|FREMONT|GEM|GOODING|IDAHO|JEFFERSON|JEROME|KOOTENAI|LATAH|LEMHI|LEWIS|LINCOLN|MADISON|MINIDOKA|NEZ PERCE|ONEIDA|OWYHEE|PAYETTE|POWER|SHOSHONE|TETON|TWIN FALLS|VALLEY|WASHINGTON".split("|")


def native_count(raw):
    value = raw.strip()
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", value):
        raise ValueError("Missing or invalid native count; no zero or component fallback")
    return int(value.replace(",", ""))


def registration_frame(bodies, independent, declarations):
    if (declarations["selected_year"] != "2026" or declarations["selected_month"] != "11"
            or declarations["groups"] != ["County", "Legislative", "Congressional"]
            or declarations["index_label_last_updated"] != "November 2, 2026"
            or declarations["native_registration_cutoff"] is not None
            or declarations["active_inactive_status_qualified"] is not False):
        raise ValueError("Changed native archive selection or cutoff/status qualification")
    tables, accounting, diagnostics = {}, [], []
    for view in SOURCE_SHA:
        rows = list(csv.reader(io.StringIO(bodies[view].decode("utf-8-sig"), newline="")))
        if rows != independent[view]:
            raise ValueError("Independent complete CSV readers disagree")
        geo = view if view == "County" else view + "District"
        if rows[0] != [geo, *PARTIES] or any(len(row) != 7 for row in rows):
            raise ValueError("Changed native geography/party/Total columns")
        expected = set(COUNTIES) if view == "County" else {str(value) for value in range(1, 36 if view == "Legislative" else 3)}
        labels = [row[0] for row in rows[1:]]
        if len(set(labels)) != len(labels) or set(labels) != expected | {"Total"}:
            raise ValueError("Incomplete or duplicate native geography inventory or explicit Total")
        tables[view] = {row[0]: [native_count(value) for value in row[1:]] for row in rows[1:]}
        for ordinal, row in enumerate(rows[1:], 2):
            values = tables[view][row[0]]
            diagnostics.append(dict(scope=view + ":" + row[0], native_parent=values[-1],
                                    observed_child_sum=sum(values[:-1]), difference=sum(values[:-1]) - values[-1]))
            for column, literal, count in zip(PARTIES, row[1:], values):
                accounting.append(dict(view=view, source_row=ordinal, geography_literal=row[0],
                    native_column=column, raw_native_cell=literal, native_registered_count=count,
                    missing_imputed_zero=False, source_geography_not_inferred_fips=True,
                    registration_affiliation_not_vote_choice=True))
        for column, party in enumerate(PARTIES):
            parent = tables[view]["Total"][column]
            subtotal = sum(values[column] for label, values in tables[view].items() if label != "Total")
            diagnostics.append(dict(scope=view + ":component:" + party, native_parent=parent,
                                    observed_child_sum=subtotal, difference=subtotal - parent))
    parent = tables["County"]["Total"]
    if parent[-1] <= 0 or any(tables[view]["Total"] != parent for view in tables):
        raise ValueError("Missing positive native state parent or repeated parents disagree")
    return parent[-1], accounting, diagnostics


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-idaho-monthly-native-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted version21 baseline or complete native inputs")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed complete native input inventory")
        for name, metadata in sums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient native input")
        bodies = {view: archive.read(view + ".csv") for view in SOURCE_SHA}
        if any(hashlib.sha256(body).hexdigest() != SOURCE_SHA[view] for view, body in bodies.items()):
            raise ValueError("Changed original CSV bytes")
        declarations = json.loads(archive.read("source-declarations.json"))
        total, accounting, diagnostics = registration_frame(
            bodies, json.loads(archive.read("pandas-tables.json")), declarations)
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 39, 27):
        raise ValueError("Changed complete version21 coverage")
    target = next(row for row in states if row["state_code"] == "ID")
    if (target["control_id"] != "id-2026-held-separate-ballot-report"
            or target["reported_cast_ballots"] != "731980"
            or target["control_registered_denominator"] or target["conditional_registered_frame_scenario_available"] != "False"):
        raise ValueError("Do not link a monthly register to or repair the primary ballot report")
    target["conditional_registered_frame_scenario_available"] = "True"
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "ID" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state weights")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional dated-register partition failed")
    time = "Native archive month2026-11; index lastupdatedNovember2,2026 is not registry cutoff/clock; status/TZ unspecified"
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="ID", year=2026, geographic_level="state", geography="Idaho monthly registration",
        source_family=URL, measure=MEASURE, native_measure="Explicit 202611 CountyTotals Total, corroborated by legislative and congressional views",
        numerator=None, denominator=total, denominator_basis=BASIS,
        denominator_label="Separate monthly registration stock; not primary ballot-report registration",
        source_time_label=time, source_url=URL, native_status="Monthly administrative register, not election counting/certification",
        source_kind="reviewed_public_official_monthly_aggregate_csv",
        scope_notes="All44counties35legislative2congressional+3parents preserved; repeatedviewsonepopulation. Rawcellspaces preserved, blanksnotzero. SourcecodesnotFIPS; affiliationnotvotechoice. No group/local survey allocation or election-time population validation.",
        selected_state_reference=False, disposition="additional_dated_registration_scenario_primary_ballot_denominator_not_linked")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="ID", control_id=CONTROL, control_measure=MEASURE,
        control_native_status=control["native_status"], native_registered_denominator=total,
        native_denominator_basis=BASIS, source_time_label=time, source_url=URL,
        civic_source_n=source["n"], civic_weight=source["weight"],
        civic_modeled_voter_weight=source["modeled_voter_weight"], civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
        assumption="month-labelled source registration stock exchangeable with statewide Civic propensity; unvalidated and not linked to primary ballot-report denominator",
        scenario_units="native_month_labelled_registry_units_not_administratively_observed_people")
    scenarios.append(scenario)
    qualification = dict(native_month_label="2026-11", native_registration_parent=total,
        native_index_update_date="2026-11-02", native_registry_cutoff=None, native_timezone=None,
        active_inactive_status_qualified=False, index_update_not_registry_cutoff_or_live_clock=True,
        published_selector_values_and_explicit_url_template_not_guessed=True,
        all_609_raw_cells_including_headers_spaces_and_labels_independently_preserved=True,
        all_504_count_slots_preserved=True, missing_imputed_zero=False,
        repeated_geographic_margins_counted_once=True, source_geography_not_inferred_fips=True,
        affiliation_not_vote_choice=True, native_accounting_checks=diagnostics,
        native_accounting_discrepancies=[row for row in diagnostics if row["difference"]],
        primary_ballot_report_731980_and_native_registration_conflict_preserved=True,
        primary_ballot_registered_denominator_still_null=True, mixed_source_primary_turnout_rate_approved=False,
        only_idaho_scenario_availability_flag_changed_in_state_query=True,
        native_ballots_linked_to_dated_register=None, native_minus_model=None, observed_staying_home=None,
        group_or_local_survey_allocation=False, source_population_transport_validated=False,
        design_confidence_interval=None, rates_approved=False, maps_approved=False,
        counting_completion_approved=False, certification_approved=False)
    frame = dict(state_code="ID", native_month_label="2026-11", native_registration_parent=total,
        native_index_update_date="2026-11-02", native_registry_cutoff=None,
        conditional_model_participant_units=str(modeled), conditional_model_nonparticipant_units=str(nonmodeled),
        primary_ballots_kept_separate=731980, primary_ballot_registration_denominator=None,
        primary_registration_disagreement_not_repaired=True, matched_ballot_numerator=None,
        native_minus_model=None, observed_staying_home=None, rate_approved=False, map_approved=False)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-registration-accounting.csv": csv_bytes(accounting),
        "complete-idaho-dated-register-frame.csv": csv_bytes([frame]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=40, conditional_scenarios=28,
            month_labelled_registration_parent=total, native_views=3, native_raw_cells=609,
            native_count_slots=504, native_accounting_equations=len(diagnostics),
            native_accounting_discrepancies=len(qualification["native_accounting_discrepancies"]),
            prior_50_other_states_39_controls_27_scenarios_preserved=True,
            primary_idaho_source_fields_and_denominator_hold_preserved=True, no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-idaho-monthly-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("idaho_monthly_register.py", "extract_idaho_monthly_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_idaho_monthly_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Idaho's separately dated 2026-11 registration Total is 1,056,803, not an election-time population.\n"
        "Official selector values and URL template declare the three archived aggregate CSVs; no guessed URLs.\n"
        "Index update November 2 is not a qualified registry cutoff or live clock; status/timezone unknown.\n"
        "All44county/35legislative/2congressional rows plus repeated parents, 609 raw cells/504 count slots,\n"
        "headers and native cell spaces preserved. Repeated margins count once; blanks never imputed zero.\n"
        "Party affiliation is registration accounting, not vote choice. No local or party model allocation.\n"
        "Conditional monthly-register units assume unvalidated overall Civic transport, not observed people.\n"
        "Primary ballot report 731980 and its registration disagreement remain untouched, denominator NULL.\n"
        "No mixed-source primary rate/residual, observed staying home, population validation or fake intervals.\n"
        "Complete original CSVs, independent view, factual declaration/receipts, baseline, code/tests/allqueries.\n"
        "Full index app code/contact details, respondent records and personal voter data are excluded.\n"
        "python3 -m unittest discover -s tests -p test_idaho_monthly_register.py\n"
        "python3 -m scripts.idaho_monthly_register --inputs inputs --output reproduced\n").encode()
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
