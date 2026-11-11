"""Use Connecticut's dated active register without repairing partial election results."""

import argparse
import csv
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .washington_register_control import civic_source, csv_bytes, encoded


BASELINE_SHA = "b4b940c75cf0879ac2959fa2654202f8afa0d1981ddaf8de23a74933beffcce6"
NATIVE_SHA = "98295d009ea820da6b48551926ebd9c36ae55d62ee35da69fb3724226ac28b4e"
PDF_SHA = "2e4d8e75fac512763044e2229efbf10024a9d0ccff9f8ba1e6ccd820dd17746c"
CONTROL = "ct-2026-native-20261019-active-registration-parent"
MEASURE = "native_dated_active_registration_snapshot_not_election_time_denominator"
BASIS = "native_2026_10_19_Totals_Active_parent_not_reported_results_RV"
URL = ("https://portal.ct.gov/-/media/sots/electionservices/registration-and_enrollment_statistics/2026/"
       "registration-enrollment-statistics-11032026-general-election.pdf?"
       "hash=B63BA7D920D0CDC5EEEBCDE76D6661B4&rev=fef46a197a054c8c8b96fba43c563ffc")
GROUPS = ("republican", "democratic", "minor_parties", "unaffiliated", "totals")
FIELDS = tuple(group + "_" + status for group in GROUPS for status in ("active", "inactive", "total"))
COUNTIES = r"Fairfield|Hartford|Litchfield|Middlesex|New Haven|New London|Tolland|Windham"
TOWN = re.compile(r"^(.+?)\s+(" + COUNTIES + r")\s+([1-5](?:\s*,\s*[1-5])*)\s+(.+)$")


def parse_pages(pages):
    if len(pages) != 9 or any("as of October 19, 2026" not in page or "(10/19/2026)" not in page for page in pages):
        raise ValueError("Changed native date or physical page coverage")
    rows = []
    for number, page in enumerate(pages, 1):
        normalized = " ".join(page.split())
        header = "Republican Party Democratic Party Minor Parties Unaffiliated Totals"
        if header not in normalized:
            raise ValueError("Changed native registration column order")
        for line in page.splitlines():
            line = line.strip()
            match = TOWN.fullmatch(line)
            if match:
                town, county, district, body = match.groups()
            elif re.match(r"^Totals\s+\d", line):
                town, county, district, body = "Totals", "", "", line.split(maxsplit=1)[1]
            else:
                continue
            tokens = re.findall(r"\b\d[\d,]*\b", body)
            if len(tokens) != 15:
                raise ValueError("Incomplete native 15-column registration row")
            notes = " ".join(re.sub(r"\b\d[\d,]*\b", "", body).split())
            if notes and not re.fullmatch(r"[A-Z ]+", notes):
                raise ValueError("Unreviewed registration cell or minor-party note")
            row = dict(town_literal=" ".join(town.split()), source_county_literal=county,
                       congressional_district_literal=re.sub(r"\s+", "", district),
                       minor_party_notes_literal=notes, source_page=number)
            row.update(zip(FIELDS, (int(token.replace(",", "")) for token in tokens)))
            rows.append(row)
    if pages[-1].count("Minor Party Key") != 1:
        raise ValueError("Missing or repeated native minor-party legend")
    legend = []
    for line in pages[-1].split("Minor Party Key", 1)[1].splitlines():
        match = re.fullmatch(r"\s*(.+?)\s+([A-Z]+)\s*", line)
        if match:
            legend.append(dict(party_name_literal=" ".join(match[1].split()), party_key_literal=match[2]))
    if len(legend) != 11 or len({row["party_key_literal"] for row in legend}) != 11:
        raise ValueError("Incomplete native minor-party legend")
    return rows, legend


def active_frame(first, second, town_catalog):
    rows, legend = parse_pages(first)
    if (rows, legend) != parse_pages(second):
        raise ValueError("Independent native PDF extractions disagree")
    parents = [row for row in rows if row["town_literal"] == "Totals"]
    towns = [row for row in rows if row["town_literal"] != "Totals"]
    if len(parents) != 1:
        raise ValueError("Missing or duplicate native Totals parent; no marginal fallback")
    if (len(towns) != 169 or len({row["town_literal"] for row in towns}) != 169
            or {row["town_literal"] for row in towns} != set(town_catalog.values())):
        raise ValueError("Incomplete or duplicate native 169-town coverage")
    parent = parents[0]
    if parent["totals_active"] <= 0:
        raise ValueError("Missing positive native active-registration parent")
    discrepancies = []
    for row in rows:
        for group in GROUPS:
            difference = row[group + "_active"] + row[group + "_inactive"] - row[group + "_total"]
            if difference:
                discrepancies.append(dict(scope=row["town_literal"], check=group + "_active_plus_inactive_minus_total", difference=difference))
        for status in ("active", "inactive", "total"):
            difference = sum(row[group + "_" + status] for group in GROUPS[:-1]) - row["totals_" + status]
            if difference:
                discrepancies.append(dict(scope=row["town_literal"], check="affiliation_sum_minus_totals_" + status, difference=difference))
    for field in FIELDS:
        difference = sum(row[field] for row in towns) - parent[field]
        if difference:
            discrepancies.append(dict(scope="all_169_towns", check=field + "_sum_minus_native_state_parent", difference=difference))
    return parent, rows, legend, discrepancies


def results_hold(lookup, headers, turnouts):
    if lookup["election"]["ID"] != "108" or lookup["election"]["DT"] != "11/03/2026":
        raise ValueError("Changed separate results election identity")
    if headers[0] != headers[1] or turnouts[0] != turnouts[1]:
        raise ValueError("Changed previously held results versions")
    header, turnout = headers[0], turnouts[0]
    towns = lookup["townIds"]
    if len(towns) != 169 or set(turnout) != set(towns) | {"170"} or turnout["170"]["NM"] != "Total":
        raise ValueError("Changed held results town coverage")
    if any(turnout[key]["NM"] != town for key, town in towns.items()):
        raise ValueError("Changed held results town identity")
    native_count = lambda value: int(value.replace(",", ""))
    for field, parent_field in (("EV", "RV"), ("VV", "BC")):
        if (sum(native_count(turnout[key][field]) for key in towns)
                != native_count(turnout["170"][field]) or
                native_count(turnout["170"][field]) != native_count(header[parent_field])):
            raise ValueError("Held results accounting changed")
    zero_ev = [dict(town_id=key, town_literal=towns[key]) for key in towns if native_count(turnout[key]["EV"]) == 0]
    zero_vv = [dict(town_id=key, town_literal=towns[key]) for key in towns if native_count(turnout[key]["VV"]) == 0]
    return dict(native_results_header=header, native_total_row=turnout["170"],
                zero_reported_registration_towns=zero_ev, zero_reported_voted_towns=zero_vv,
                native_zero_is_zero_population=False, complete_statewide_registration_qualified=False,
                native_statewide_ballot_reference_qualified=False, registry_mode_semantics_qualified=False,
                native_update_time=None, registration_snapshot_not_substituted=True)


def native_inputs(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Incomplete native input inventory")
        for name, metadata in sums.items():
            raw = archive.read(name)
            if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed native input bytes")
        if hashlib.sha256(archive.read("registration-report.pdf")).hexdigest() != PDF_SHA:
            raise ValueError("Changed pinned public registration PDF")
        receipt = json.loads(archive.read("extraction-receipt.json"))
        for name, digest in receipt["extractions"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError("Changed independent PDF extraction")
        read = lambda name: json.loads(archive.read(name))
        lookup = json.loads(gzip.decompress(archive.read("results/Lookupdata.json.gz")))
        parent, rows, legend, discrepancies = active_frame(read("pymupdf-pages.json"), read("pypdf-pages.json"), lookup["townIds"])
        headers, turnouts = [], []
        for version in ("52337", "52338"):
            headers.append(json.loads(gzip.decompress(archive.read("results/" + version + "/election_Electiondata.json.gz"))))
            turnouts.append(json.loads(gzip.decompress(archive.read("results/" + version + "/voterTurnout_Electiondata.json.gz"))))
        hold = results_hold(lookup, headers, turnouts)
        return parent, rows, legend, discrepancies, hold


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "connecticut-complete-native-inputs.zip").read_bytes()
    if (hashlib.sha256(baseline).hexdigest() != BASELINE_SHA
            or hashlib.sha256(native).hexdigest() != NATIVE_SHA):
        raise ValueError("Changed accepted complete version13 baseline or pinned native inputs")
    parent, rows, legend, discrepancies, hold = native_inputs(native)
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 29, 18):
        raise ValueError("Changed complete version13 coverage")
    target = next(row for row in states if row["state_code"] == "CT")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Connecticut frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "CT" and row["dimension"] == "overall")
    active = parent["totals_active"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = active * (voter / weight), active * (nonvoter / weight)
        if abs(modeled + nonmodeled - active) > Decimal("1e-60"):
            raise ValueError("Conditional dated-active partition failed")
    time = "Native registration date 10/19/2026; timezone/time-of-day absent; not an election-time denominator"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=active, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="CT", year=2026, geographic_level="state", geography="Connecticut dated active-registration snapshot",
                   source_family=URL, measure=MEASURE, native_measure="Native Totals Active dated 10/19/2026; not results RV or election-time population",
                   numerator=None, denominator=active, denominator_basis=BASIS,
                   denominator_label="Native dated Totals Active parent, excluding inactive; not reported results RV or town/party fallback",
                   source_time_label=time, source_url=URL, native_status="Dated registration snapshot; not election counting/certification",
                   source_kind="reviewed_public_dated_active_registration_snapshot",
                   scope_notes="All 169 towns/15 count columns preserved. Party affiliation is registration accounting, not votes. Separate results zeros, registry/mode semantics and geography holds unchanged.",
                   selected_state_reference=False, disposition="dated_active_register_frame_no_election_time_population_or_native_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="CT", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=active,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="native 10/19/2026 active-registration snapshot is exchangeable with source-weighted statewide survey propensity; not an election-time population",
                    scenario_units="dated_2026_10_19_native_active_registration_units_not_election_time_population")
    scenarios.append(scenario)
    qualification = dict(
        year=2026, registration_source_date="10/19/2026", registration_source_timezone=None,
        native_active_registered_parent=active, native_inactive_parent=parent["totals_inactive"],
        native_combined_total_parent=parent["totals_total"], native_parent_not_derived_from_town_or_party_sums=True,
        complete_independent_pdf_extractions_match=True, source_pdf_sha256=PDF_SHA,
        native_town_rows=169, native_state_parent_rows=1, native_count_columns=15,
        native_arithmetic_discrepancies=discrepancies, native_totals_not_repaired=True,
        registered_status_literal="Active", election_time_denominator_qualified=False,
        separate_results_hold=hold, source_affiliation_is_registration_accounting_not_party_votes=True,
        county_labels_are_source_literals_not_current_census_planning_regions=True,
        legislative_districts_are_source_literals_not_boundary_joins=True,
        source_spelling_including_Independance_preserved=True,
        selected_native_statewide_ballot_reference=None, native_minus_model=None,
        survey_population_transport_validated=False, derived_state_frame_rate_approved=False,
        maps_approved=False, counting_completion_approved=False, certification_approved=False,
        generic_cast_ballot_measure_approved=False, town_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        native_pdf_extraction_refresh_optional_requires_pymupdf_and_pypdf=True,
        numerical_analysis_uses_complete_frozen_extractions_and_standard_library=True,
        compiled_publisher_app_code_raw_personal_records_and_private_survey_rows_excluded=True)
    frame = dict(state_code="CT", year=2026, native_source_date="10/19/2026",
                 native_active_registered_parent=active, native_inactive_parent=parent["totals_inactive"],
                 native_combined_total_parent=parent["totals_total"], election_time_denominator_qualified=False,
                 conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
                 selected_native_statewide_ballots=None, native_minus_model=None, rate_approved=False,
                 map_approved=False, observed_staying_home=None)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-connecticut-native-registration-accounting.csv": csv_bytes(rows),
        "complete-connecticut-native-minor-party-legend.csv": csv_bytes(legend),
        "complete-connecticut-dated-active-frame.csv": csv_bytes([frame]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=30, conditional_scenarios=19,
                                    dated_active_registration_frame_added=1, native_statewide_ballot_controls_added=0,
                                    native_town_rows=169, native_state_parent_rows=1, native_count_cells=2550,
                                    native_dated_active_parent=active, native_arithmetic_discrepancies=len(discrepancies),
                                    partial_results_zero_registered_towns=len(hold["zero_reported_registration_towns"]),
                                    partial_results_zero_voted_towns=len(hold["zero_reported_voted_towns"]),
                                    election_time_denominator_qualified=False,
                                    all_fifty_unaffected_states_eighteen_frames_and_twenty_nine_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "connecticut-complete-native-inputs.zip"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("connecticut_dated_register.py", "extract_connecticut_registration.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_connecticut_dated_register.py"] = Path(__file__).parents[1].joinpath("tests/test_connecticut_dated_register.py").read_bytes()
    files["README.txt"] = (
        "Connecticut native Totals ACTIVE2255397 dated10/19/2026; NOT an election-time denominator.\n"
        "Inactive234553/combined2489950 are separate statuses, never substitutes for the active parent.\n"
        "All169towns+state/15countcolumns/11legend entries preserved; affiliation is NOT party voting.\n"
        "Native county/district literals are not geographic crosswalks. No town/group survey allocation.\n"
        "Separate results RV2102250 includes13zero-EV/14zero-VV towns; versions52337/52338 unchanged.\n"
        "Native zeros are not zero populations. Dated registrations never repair incomplete results.\n"
        "Native statewide ballots/residual remain NULL. No rate/map/completion/population approval.\n"
        "Conditional dated-active units assume unvalidated Civic transport, not observed staying home.\n"
        "Complete native PDF/two frozen independent extractions/results originals and version13baseline included.\n"
        "Analysis/tests are standard-library offline; compiled app code and private respondents excluded.\n"
        "python3 -m unittest discover -s tests -p test_connecticut_dated_register.py\n"
        "python3 -m scripts.connecticut_dated_register --inputs inputs --output reproduced\n"
        "Optional native PDF refresh (PyMuPDF+pypdf): unzip inputs/connecticut-complete-native-inputs.zip -d native\n"
        "python3 scripts/extract_connecticut_registration.py --pdf native/registration-report.pdf --output fresh-extractions\n"
        "PDF extraction refresh is distinct from the exactly reproduced frozen-input numerical analysis.\n").encode()
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
