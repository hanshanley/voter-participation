"""Use New Jersey's native dated total register without inferring party voting."""

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


BASELINE_SHA = "96c223b86f535d11c73d2134e3788a3451d820aef1003bef1e918af8c3f9e4f7"
NATIVE_SHA = "d50f7858b6b98c692ddd1905b99d16e10ad91df64071daca840d7c9381e1960a"
PDF_SHA = "a14234d4c27984fa01e9547f1a3a796c14fbb7397c5fc891cc607d7f6f9ef1db"
CONTROL = "nj-2026-native-20261103-total-registration-parent"
MEASURE = "native_dated_total_registration_snapshot_no_independent_population_transport"
BASIS = "native_2026_11_03_total_parent_active_inactive_status_unspecified"
URL = "https://www.nj.gov/state/elections/assets/pdf/svrs-reports/2026/2026-1103-voter-registration-by-county.pdf"
FIELDS = ("UNA", "DEM", "REP", "CNV", "CON", "GRE", "LIB", "NAT", "RFP", "SSP", "total")
COUNTIES = ("Atlantic", "Bergen", "Burlington", "Camden", "Cape May", "Cumberland", "Essex",
            "Gloucester", "Hudson", "Hunterdon", "Mercer", "Middlesex", "Monmouth", "Morris",
            "Ocean", "Passaic", "Salem", "Somerset", "Sussex", "Union", "Warren")


def parse_pages(pages):
    if len(pages) != 1 or "11/3/26" not in pages[0] or "Statewide Voter Registration Summary" not in " ".join(pages[0].split()):
        raise ValueError("Changed native date, title or page coverage")
    if "COUNTY" + "".join(FIELDS) not in re.sub(r"\s+", "", pages[0]):
        raise ValueError("Changed native registration column order")
    labels = {label.replace(" ", ""): label for label in (*COUNTIES, "total")}
    rows = []
    for line in pages[0].splitlines():
        match = re.fullmatch(r"\s*([A-Za-z\s]+)([0-9].*)", line)
        if not match:
            continue
        label = labels.get(re.sub(r"\s+", "", match[1]))
        if label is None:
            continue
        tokens = match[2].split()
        if len(tokens) != 11 or any(not re.fullmatch(r"[0-9][0-9,]*", token) for token in tokens):
            raise ValueError("Incomplete native 11-column registration row")
        row = dict(county_literal=label, source_page=1)
        row.update(zip(FIELDS, (int(token.replace(",", "")) for token in tokens)))
        rows.append(row)
    return rows


def registration_frame(first, second):
    rows = parse_pages(first)
    if rows != parse_pages(second):
        raise ValueError("Independent native PDF extractions disagree")
    parents = [row for row in rows if row["county_literal"] == "total"]
    counties = [row for row in rows if row["county_literal"] != "total"]
    if len(parents) != 1:
        raise ValueError("Missing or duplicate native total parent; no county or party fallback")
    if len(counties) != 21 or {row["county_literal"] for row in counties} != set(COUNTIES):
        raise ValueError("Incomplete or duplicate native 21-county coverage")
    parent = parents[0]
    if parent["total"] <= 0:
        raise ValueError("Missing positive native registration parent")
    discrepancies = []
    for row in rows:
        difference = sum(row[field] for field in FIELDS[:-1]) - row["total"]
        if difference:
            discrepancies.append(dict(scope=row["county_literal"], check="party_sum_minus_native_total", difference=difference))
    for field in FIELDS:
        difference = sum(row[field] for row in counties) - parent[field]
        if difference:
            discrepancies.append(dict(scope="all_21_counties", check=field + "_sum_minus_native_state_parent", difference=difference))
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
        if hashlib.sha256(archive.read("new-jersey-registration.pdf")).hexdigest() != PDF_SHA:
            raise ValueError("Changed pinned public registration PDF")
        receipt = json.loads(archive.read("extraction-receipt.json"))
        for name, digest in receipt["extractions"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError("Changed independent PDF extraction")
        return registration_frame(json.loads(archive.read("pymupdf-pages.json")), json.loads(archive.read("pypdf-pages.json")))


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "new-jersey-complete-native-inputs.zip").read_bytes()
    pins = json.loads((inputs / "native-source-reference.json").read_bytes())
    if (hashlib.sha256(baseline).hexdigest() != BASELINE_SHA
            or hashlib.sha256(native).hexdigest() != NATIVE_SHA
            or pins["native_inputs_sha256"] != NATIVE_SHA):
        raise ValueError("Changed accepted complete version14 baseline or frozen native inputs")
    if pins["source_pdf_sha256"] != PDF_SHA:
        raise ValueError("Changed native source identity")
    parent, rows, discrepancies = native_inputs(native)
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 30, 19):
        raise ValueError("Changed complete version14 coverage")
    target = next(row for row in states if row["state_code"] == "NJ")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing New Jersey frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "NJ" and row["dimension"] == "overall")
    total = parent["total"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = total * (voter / weight), total * (nonvoter / weight)
        if abs(modeled + nonmodeled - total) > Decimal("1e-60"):
            raise ValueError("Conditional dated-register partition failed")
    time = "Native report date 11/3/26; time-of-day/timezone and active/inactive status unspecified"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=total, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="NJ", year=2026, geographic_level="state", geography="New Jersey dated total-registration snapshot",
                   source_family=URL, measure=MEASURE, native_measure="Native total dated 11/3/26; active/inactive status unspecified",
                   numerator=None, denominator=total, denominator_basis=BASIS,
                   denominator_label="Native dated total parent, not a party/county sum or qualified active/eligible population",
                   source_time_label=time, source_url=URL, native_status="General Election Day registration report; not election counting/certification",
                   source_kind="reviewed_public_dated_total_registration_snapshot",
                   scope_notes="All21counties/10native party-code columns/total preserved. Affiliation is registration accounting, not votes. Election-day date alone does not establish cohort/survey transport.",
                   selected_state_reference=False, disposition="dated_total_register_frame_no_independent_population_or_native_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="NJ", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=total,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="native 11/3/26 total-registration snapshot is exchangeable with source-weighted statewide survey propensity; active/inactive status and cohort transport unqualified",
                    scenario_units="dated_2026_11_03_native_total_registration_units_not_administratively_observed_people")
    scenarios.append(scenario)
    qualification = dict(
        year=2026, registration_source_date_literal="11/3/26", registration_source_date="2026-11-03",
        source_date_is_election_day=True, registration_source_timezone=None, registration_source_time_of_day=None,
        native_registered_total_parent=total, native_active_registered_parent=None, native_inactive_parent=None,
        registered_status_literal=None, active_inactive_status_independently_qualified=False,
        native_parent_not_derived_from_county_or_party_sums=True,
        complete_independent_pdf_extractions_match=True, source_pdf_sha256=PDF_SHA,
        native_county_rows=21, native_state_parent_rows=1, native_count_columns=11,
        native_party_code_order=list(FIELDS[:-1]), native_arithmetic_discrepancies=discrepancies,
        native_totals_not_repaired=True, election_time_population_independently_qualified=False,
        layout_only_label_whitespace_normalized_no_fuzzy_aliases=True,
        source_affiliation_is_registration_accounting_not_party_votes=True,
        source_date_alone_does_not_validate_survey_or_cohort_transport=True,
        selected_native_statewide_ballot_reference=None, native_minus_model=None,
        survey_population_transport_validated=False, derived_state_frame_rate_approved=False,
        maps_approved=False, counting_completion_approved=False, certification_approved=False,
        generic_cast_ballot_measure_approved=False, county_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        numerical_analysis_uses_complete_frozen_extractions_and_standard_library=True,
        optional_pdf_refresh_requires_pymupdf_and_pypdf=True,
        new_york_and_maryland_denied_routes_stopped_no_snippet_counts=True,
        compiled_publisher_app_code_raw_personal_records_and_private_survey_rows_excluded=True)
    frame = dict(state_code="NJ", year=2026, native_source_date="11/3/26", native_registered_total_parent=total,
                 native_active_registered_parent=None, native_inactive_parent=None,
                 active_inactive_status_qualified=False, election_time_population_independently_qualified=False,
                 conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
                 selected_native_statewide_ballots=None, native_minus_model=None,
                 rate_approved=False, map_approved=False, observed_staying_home=None)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-new-jersey-native-registration-accounting.csv": csv_bytes(rows),
        "complete-new-jersey-dated-registration-frame.csv": csv_bytes([frame]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=31, conditional_scenarios=20,
                                    dated_total_registration_frame_added=1, native_statewide_ballot_controls_added=0,
                                    native_county_rows=21, native_state_parent_rows=1, native_count_cells=242,
                                    native_registered_total_parent=total, native_arithmetic_discrepancies=len(discrepancies),
                                    source_date_is_election_day=True, active_inactive_status_qualified=False,
                                    all_fifty_unaffected_states_nineteen_frames_and_thirty_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "new-jersey-complete-native-inputs.zip", "native-source-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("new_jersey_register.py", "extract_new_jersey_registration.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_new_jersey_register.py"] = Path(__file__).parents[1].joinpath("tests/test_new_jersey_register.py").read_bytes()
    files["README.txt"] = (
        "New Jersey native total6747375 dated11/3/26, General Election Day registration report.\n"
        "Active/inactive status and time-of-day/timezone unspecified; no independently qualified population/cohort transport.\n"
        "All21counties+state/10nativepartycode columns+total preserved. Registration affiliation is NOT party voting.\n"
        "Dated register total is not an observed ballot count, local/group population or observed staying-home count.\n"
        "No state ballot reference/residual/new rate/map approval. State survey propensity never allocated locally.\n"
        "NY/MD declared originals returned403; routes stopped, no alternateclient/cache/mirror or snippet counts.\n"
        "Complete native PDF/independent frozen extractions/receipts and entireversion14baseline included.\n"
        "python3 -m unittest discover -s tests -p test_new_jersey_register.py\n"
        "python3 -m scripts.new_jersey_register --inputs inputs --output reproduced\n"
        "Optional native refresh requires existing PyMuPDF+pypdf: unzip inputs/new-jersey-complete-native-inputs.zip -d native\n"
        "python3 scripts/extract_new_jersey_registration.py --pdf native/new-jersey-registration.pdf --output fresh-extractions\n"
        "PDF refresh is separate from exactly reproduced standard-library frozen-input numerical analysis.\n").encode()
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
