"""Add source-specific Oklahoma/Pennsylvania register frames, not turnout."""

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


BASELINE_SHA = "182f8b721da13b98207de1b0f408104a77ee70f16c594ccd53aa4506c22eb132"
NATIVE_SHA = "970a2183bd67e5f9b7ff1cd6f3c4c2fada13967198b554c4c8e96a1281284121"
REPORTS = {
    "OK": dict(
        name="Oklahoma", pdf_sha256="2fb7a4c9ca06aaf0455f48a2647f4d3d1347be9a42d841996a56e844d3c03f6f",
        pages=3, counties=77, parent="Grand Total",
        labels=["(1) Republican", "(2) Democrat", "(3) Libertarian", "(4) Independent", "Total"],
        header="County (1) Republican (2) Democrat (3) Libertarian (4) Independent Total",
        title="MESA - Current Registration Statistics by County",
        report_clock_literal="11/1/2026 3:05 AM", declared_as_of_date="2026-11-01",
        election_label=None, registration_cutoff_date="2026-11-01",
        measure="native_dated_total_registration_snapshot_no_independent_population_transport",
        basis="native_2026_11_01_Grand_Total_parent_status_unspecified",
        units="dated_2026_11_01_native_total_registration_units_not_administratively_observed_people",
        time="Declared as of November1,2026; native printed clock11/1/2026 3:05AM; timezone absent; not an election-time denominator",
        url="https://oklahoma.gov/content/dam/ok/en/elections/voter-registration-statistics/2026-vr-statistics/2026-11-01-vrstats-county.pdf"),
    "PA": dict(
        name="Pennsylvania", pdf_sha256="7f4e19415a6a1f013e674158e6df9d79fecb3dfedc3c3edc54d81f77a7e1b921",
        pages=2, counties=67, parent="Total",
        labels=["Democratic", "Republican", "Libertarian", "Other Parties", "All Parties"],
        header="County Democratic Republican Libertarian Other Parties All Parties",
        title="2026 Voter Registration Statistics", report_clock_literal=None, declared_as_of_date=None,
        election_label="November 3, 2026 General Election", registration_cutoff_date=None,
        measure="native_election_labelled_registration_total_cutoff_not_stated",
        basis="native_2026_general_All_Parties_Total_parent_cutoff_and_status_unspecified",
        units="election_labelled_2026_general_native_registration_units_cutoff_unknown_not_observed_people",
        time="Election label November3,2026 General Election; registration cutoff, report time and timezone not stated",
        url="https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/voting-and-election-statistics/voter-registration-statistics/certified%20voter%20registration%20stats%20general%20election%202026%20-%20final.pdf"),
}


def compact(value):
    return re.sub(r"\s+", "", value)


def parse_pages(state, pages):
    config = REPORTS[state]
    text = " ".join(" ".join(page.split()) for page in pages)
    if len(pages) != config["pages"] or compact(config["title"]) not in compact(text):
        raise ValueError("Changed native title or page coverage")
    if config["report_clock_literal"] and any(compact(config["report_clock_literal"]) not in compact(page) for page in pages):
        raise ValueError("Changed native report clock")
    if config["election_label"] and compact(config["election_label"]) not in compact(text):
        raise ValueError("Changed native election label, not a registration cutoff")
    rows = []
    for number, page in enumerate(pages, 1):
        if compact(config["header"]) not in compact(page):
            raise ValueError("Changed native registration column order")
        for line in page.splitlines():
            match = None
            code = ""
            if state == "OK":
                match = re.fullmatch(r"\s*(\d{2})\s*([A-Z][A-Z\s]+?)(\d[\d,\s]*)", line)
                if match:
                    code, label, body = match.groups()
            if not match:
                match = re.fullmatch(r"\s*([A-Za-z][A-Za-z\s]+?)(\d[\d,\s]*)", line)
                if not match:
                    continue
                label, body = match.groups()
                if state == "OK" and compact(label) != compact(config["parent"]):
                    continue
            tokens = body.split()
            if len(tokens) != 5 or any(not re.fullmatch(r"[0-9][0-9,]*", token) for token in tokens):
                raise ValueError("Incomplete native five-column registration row")
            rows.append(dict(county_code_literal=code, county_literal=" ".join(label.split()),
                             source_page=number, counts=[int(token.replace(",", "")) for token in tokens]))
    return rows


def registration_frame(state, first, second):
    config = REPORTS[state]
    rows, other = parse_pages(state, first), parse_pages(state, second)
    signature = lambda row: (row["county_code_literal"], compact(row["county_literal"]), row["source_page"], row["counts"])
    if [signature(row) for row in rows] != [signature(row) for row in other]:
        raise ValueError("Independent native PDF extractions disagree")
    parents = [row for row in rows if compact(row["county_literal"]) == compact(config["parent"])]
    counties = [row for row in rows if compact(row["county_literal"]) != compact(config["parent"])]
    if len(parents) != 1:
        raise ValueError("Missing or duplicate native state parent; no county or party fallback")
    if len(counties) != config["counties"] or len({compact(row["county_literal"]) for row in counties}) != config["counties"]:
        raise ValueError("Incomplete or duplicate native county coverage")
    if state == "OK" and {row["county_code_literal"] for row in counties} != {f"{value:02}" for value in range(1, 78)}:
        raise ValueError("Incomplete or duplicate native county code inventory")
    parent = parents[0]
    if parent["counts"][-1] <= 0:
        raise ValueError("Missing positive native registration parent")
    discrepancies = []
    for row in rows:
        difference = sum(row["counts"][:-1]) - row["counts"][-1]
        if difference:
            discrepancies.append(dict(scope=row["county_literal"], check="party_sum_minus_native_total", difference=difference))
    for position, label in enumerate(config["labels"]):
        difference = sum(row["counts"][position] for row in counties) - parent["counts"][position]
        if difference:
            discrepancies.append(dict(scope="all_native_counties", check=label + "_sum_minus_native_state_parent", difference=difference))
    return parent, rows, discrepancies


def native_inputs(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Incomplete native input inventory")
        for name, metadata in sums.items():
            raw = archive.read(name)
            if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed native input bytes")
        reports = {}
        for state, config in REPORTS.items():
            if hashlib.sha256(archive.read(state + "/report.pdf")).hexdigest() != config["pdf_sha256"]:
                raise ValueError("Changed pinned public registration PDF")
            receipt = json.loads(archive.read(state + "/extraction-receipt.json"))
            for name, digest in receipt["extractions"].items():
                if hashlib.sha256(archive.read(state + "/" + name)).hexdigest() != digest:
                    raise ValueError("Changed independent PDF extraction")
            reports[state] = registration_frame(state, *[
                json.loads(archive.read(state + "/" + name)) for name in ("pymupdf-pages.json", "pypdf-pages.json")])
        return reports


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "complete-native-registration-inputs.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete version15 baseline or frozen native inputs")
    reports = native_inputs(native)
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 31, 20):
        raise ValueError("Changed complete version15 coverage")
    public_civic = civic_source(baseline)["participation"]
    accounting, frames, qualifications = [], [], {}
    for state, config in REPORTS.items():
        parent, rows, discrepancies = reports[state]
        total = parent["counts"][-1]
        target = next(row for row in states if row["state_code"] == state)
        if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
            raise ValueError("Do not duplicate an existing state frame")
        source = next(row for row in public_civic if row["scope"] == state and row["dimension"] == "overall")
        with localcontext() as context:
            context.prec = 80
            weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
            if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
                raise ValueError("Changed full public Civic state denominator")
            modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
            if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
                raise ValueError("Conditional source-register partition failed")
        control_id = state.lower() + "-2026-native-source-registration-parent"
        target.update(control_id=control_id, control_measure=config["measure"], control_native_numerator=None,
                      control_registered_denominator=total, control_denominator_basis=config["basis"],
                      control_native_time=config["time"], control_source_url=config["url"],
                      conditional_registered_frame_scenario_available="True")
        control = dict(controls[0])
        control.update(id=control_id, state_code=state, year=2026, geographic_level="state",
                       geography=config["name"] + " source-defined registration report",
                       source_family=config["url"], measure=config["measure"],
                       native_measure="Explicit native statewide registration total; source party accounting, not votes",
                       numerator=None, denominator=total, denominator_basis=config["basis"],
                       denominator_label="Native statewide parent, not a county/party sum or independently validated population",
                       source_time_label=config["time"], source_url=config["url"],
                       native_status="Registration report; not election counting/certification",
                       source_kind="reviewed_public_source_defined_registration_report",
                       scope_notes="Native county inventory and party counts preserved. Active/inactive status unspecified. Election labels and printed report clocks are distinct from population/cohort validation.",
                       selected_state_reference=False,
                       disposition="source_registration_frame_no_independent_population_or_native_ballot_reference")
        controls.append(control)
        scenario = dict(scenarios[0])
        scenario.update(year=2026, state_code=state, control_id=control_id, control_measure=config["measure"],
                        control_native_status=control["native_status"], native_registered_denominator=total,
                        native_denominator_basis=config["basis"], source_time_label=config["time"], source_url=config["url"],
                        civic_source_n=source["n"], civic_weight=source["weight"],
                        civic_modeled_voter_weight=source["modeled_voter_weight"],
                        civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                        conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                        reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                        assumption="native source-defined registration parent is exchangeable with source-weighted statewide survey propensity; " + config["time"],
                        scenario_units=config["units"])
        scenarios.append(scenario)
        for row in rows:
            for position, (label, value) in enumerate(zip(config["labels"], row["counts"]), 1):
                accounting.append(dict(state_code=state, county_code_literal=row["county_code_literal"],
                                       county_literal=row["county_literal"], source_page=row["source_page"],
                                       native_column_position=position, native_column_label=label, native_count=value))
        qualifications[state] = dict(
            native_registered_total_parent=total, native_active_registered_parent=None, native_inactive_parent=None,
            registered_status_literal=None, active_inactive_status_qualified=False,
            declared_as_of_date=config["declared_as_of_date"], registration_cutoff_date=config["registration_cutoff_date"],
            native_report_clock_literal=config["report_clock_literal"], report_clock_timezone=None,
            native_printed_report_clock_not_live_update_or_survey_cutoff=True,
            election_label=config["election_label"], election_label_is_not_registration_cutoff=True,
            source_pdf_sha256=config["pdf_sha256"], source_county_rows=config["counties"],
            native_count_columns=config["labels"], native_arithmetic_discrepancies=discrepancies,
            complete_independent_pdf_extractions_match=True, native_parent_not_derived_from_county_or_party_sums=True,
            source_county_codes_are_not_inferred_fips=True, no_fuzzy_label_aliases_or_count_repair=True,
            source_party_affiliation_is_registration_accounting_not_votes=True,
            survey_population_transport_validated=False, election_time_population_independently_qualified=False,
            selected_native_statewide_ballot_reference=None, native_minus_model=None,
            derived_state_frame_rate_approved=False, maps_approved=False,
            counting_completion_approved=False, certification_approved=False,
            generic_cast_ballot_measure_approved=False, county_or_demographic_survey_allocation=False,
            observed_staying_home=None, demographic_population=None, design_confidence_interval=None)
        frames.append(dict(state_code=state, year=2026, native_registered_total_parent=total,
                           declared_as_of_date=config["declared_as_of_date"], registration_cutoff_date=config["registration_cutoff_date"],
                           native_report_clock_literal=config["report_clock_literal"], election_label=config["election_label"],
                           active_inactive_status_qualified=False, population_transport_qualified=False,
                           conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
                           selected_native_statewide_ballots=None, native_minus_model=None, rate_approved=False,
                           map_approved=False, observed_staying_home=None))
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-native-registration-accounting.csv": csv_bytes(accounting),
        "complete-source-registration-frames.csv": csv_bytes(frames),
        "source-qualification.json": encoded(dict(reports=qualifications,
            numerical_analysis_uses_complete_frozen_extractions_and_standard_library=True,
            optional_pdf_refresh_requires_pymupdf_and_pypdf=True,
            compiled_publisher_code_raw_personal_records_and_private_survey_rows_excluded=True)),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=33, conditional_scenarios=22,
            source_registration_frames_added=2, native_statewide_ballot_controls_added=0,
            native_county_rows=144, native_state_parent_rows=2, native_count_cells=730,
            all_forty_nine_unaffected_states_twenty_prior_frames_and_thirty_one_controls_preserved=True,
            no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "complete-native-registration-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("state_registration_reports.py", "extract_state_registration_reports.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_state_registration_reports.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Oklahoma native GrandTotal2455735, declaredasof11/1/2026; printedclock11/1/2026 3:05AM timezoneabsent.\n"
        "Pennsylvania native Total/AllParties9052695, electionlabelNovember3,2026General; REGISTRATION CUTOFF UNKNOWN.\n"
        "Election labels and printed report clocks are not independent population/cohort/survey validation.\n"
        "All77OK+67PAcounties/stateparents/730cells preserved. Nativepartylabels are registration accounting NOT votes.\n"
        "Active/inactive status unspecified; source county codes are not inferredFIPS. No local/group model allocation.\n"
        "Conditional register units assume unvalidated Civicexchangeability, not observed stayinghome or ballot counts.\n"
        "No state ballot reference/residual/new rate/map approval. All prior source and access holds remain intact.\n"
        "Complete native PDFs/two frozen extractions per source/receipts and entireversion15baseline included.\n"
        "python3 -m unittest discover -s tests -p test_state_registration_reports.py\n"
        "python3 -m scripts.state_registration_reports --inputs inputs --output reproduced\n"
        "Optional native refresh requires PyMuPDF+pypdf: unzip inputs/complete-native-registration-inputs.zip -d native\n"
        "python3 -m scripts.extract_state_registration_reports --state OK --pdf native/OK/report.pdf --output refreshed-OK\n"
        "Use --state PA/--pdf native/PA/report.pdf for Pennsylvania. Refresh is distinct from frozen-input numerical reproduction.\n").encode()
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
