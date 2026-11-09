"""Native New Mexico participation and a separate conditional register scenario."""

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from openpyxl import load_workbook


BASELINE_SHA = "99bad46c6c8142c8a92dd0a60f1863929b9ecaf930b290a0aec9fd3f3d3ae101"
WORKBOOK_SHA = "330db5ae977029696fd8ff19aedc2bd8d4c6d179ecf371fe0c3b7131bf94e0f2"
URL = "https://electionresults.sos.nm.gov/VoterTurnoutDetails.aspx?map=TURN"
CONTROL = "nm-2026-native-general-registered-turnout"
MEASURE = "native_Votes_Cast_general_turnout_signin_definition"
BASIS = "native_export_Registered_Voters_general_turnout_frame"
TIME = "Native results last updated 11/6/2026 9:55 AM MT; download literal timezone not declared"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def read_turnout(content):
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheets = {sheet.title: list(sheet.values) for sheet in workbook}
    finally:
        workbook.close()
    return turnout(sheets)


def turnout(sheets):
    if len(sheets) != 34 or next(iter(sheets)) != "Voter Turnout":
        raise ValueError("Incomplete native statewide and 33-county workbook")
    metadata = sheets["Voter Turnout"][:4]
    if metadata[0][0] != "2026 Unofficial General Election Results" or metadata[1][0] != "State of New Mexico":
        raise ValueError("Changed election or native status")
    report = re.fullmatch(r"Precincts (\d+) of (\d+) Reporting \(Precincts Partially Reported: (\d+)/(\d+)\)",
                          metadata[2][0])
    if not report or report.group(1) != report.group(2) or report.group(3) != "0" or report.group(2) != report.group(4):
        raise ValueError("Changed native reporting coverage")
    counties, precincts, state = [], [], None
    with localcontext() as context:
        context.prec = 80
        for title, source in sheets.items():
            if source[:4] != metadata:
                raise ValueError("Different native election snapshots across sheets")
            expected = ("County" if title == "Voter Turnout" else "Precinct",
                        "Registered Voters", "Votes Cast", "Percent Turnout")
            if tuple(source[6]) != expected:
                raise ValueError("Changed native turnout population or numerator")
            seen = set()
            for native in source[7:]:
                if not any(value is not None and value != "" for value in native):
                    continue
                label, registered, cast, printed = native
                if (not isinstance(label, str) or label in seen
                        or any(type(value) is not int or value < 0 for value in (registered, cast))
                        or cast > registered):
                    raise ValueError("Duplicate, missing or invalid native participation record")
                seen.add(label)
                percentage = 100 * Decimal(cast) / registered if registered else None
                if registered and str(percentage.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)) + "%" != printed:
                    raise ValueError("Native percentage disagrees with source counts")
                if not registered and (cast != 0 or printed != "0.00%"):
                    raise ValueError("Changed source zero-denominator record")
                row = dict(state_code="NM", year=2026, native_county=label if title == "Voter Turnout" else title,
                           native_precinct=None if title == "Voter Turnout" else label,
                           native_registered_voters=registered, native_votes_cast=cast,
                           native_printed_turnout=printed, source_defined_participation_pct=str(percentage) if percentage is not None else None,
                           disposition="source_defined_registered_frame" if registered else "zero_denominator_no_analytic_rate",
                           generic_cast_ballot_measure_approved=False, map_approved=False,
                           candidate_vote_sum_used=False, demographic_or_survey_allocation=False)
                if title == "Voter Turnout":
                    if label == "TOTALS":
                        state = row
                    else:
                        counties.append(row)
                else:
                    precincts.append(row)
    if state is None or len(counties) != 33 or {row["native_county"] for row in counties} != set(sheets) - {"Voter Turnout"}:
        raise ValueError("Missing or different native county identities")
    for row in counties:
        children = [child for child in precincts if child["native_county"] == row["native_county"]]
        if not children or any(sum(child[key] for child in children) != row[key]
                               for key in ("native_registered_voters", "native_votes_cast")):
            raise ValueError("Native precinct sums disagree with separate county counts")
    if any(sum(row[key] for row in counties) != state[key] for key in ("native_registered_voters", "native_votes_cast")):
        raise ValueError("Native county sums disagree with separate statewide counts")
    if len(precincts) != int(report.group(2)):
        raise ValueError("Native precinct records do not match reported coverage")
    return state, counties, precincts, dict(
        election_literal=metadata[0][0], reporting_literal=metadata[2][0],
        downloaded_at_literal=metadata[3][0], downloaded_timezone=None,
        source_update_literal="11/6/2026 9:55 AM MT",
        registered_denominator_explicit_in_native_export=True,
        native_html_numerator_literal="Ballots Cast", native_export_numerator_literal="Votes Cast",
        official_general_turnout_definition_is_voters_signing_in_over_registered_voters=True,
        generic_ballot_measure_not_silently_qualified=True,
        complete_precinct_reporting_not_certification_or_counting_completion=True)


def build(inputs):
    original = (inputs / "official-native-turnout-export.xlsx").read_bytes()
    if hashlib.sha256(original).hexdigest() != WORKBOOK_SHA:
        raise ValueError("Changed qualified original turnout workbook")
    state, counties, precincts, qualification = read_turnout(original)
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA:
        raise ValueError("Changed complete accepted all-state baseline")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        rows = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states = rows("complete-state-control-query.csv")
        controls = rows("complete-native-control-dispositions.csv")
        scenarios = rows("complete-conditional-registered-scenarios.csv")
        civic = json.loads(archive.read("inputs/civic-selected-aggregates.json"))
    if len(states) != 51 or len(controls) != 20 or len(scenarios) != 9:
        raise ValueError("Changed baseline state/control/scenario coverage")
    target = next(row for row in states if row["state_code"] == "NM")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate or overwrite an existing New Mexico state control")
    source = next(row for row in civic["participation"] if row["scope"] == "NM" and row["dimension"] == "overall")
    registered, native_count = state["native_registered_voters"], state["native_votes_cast"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full native Civic group denominator")
        voters, nonvoters = registered * (voter / weight), registered * (nonvoter / weight)
        if abs(voters + nonvoters - registered) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition failed")
        comparison = dict(state_code="NM", year=2026, native_registered=registered, native_reported_participants=native_count,
                          native_source_participation_pct=state["source_defined_participation_pct"],
                          native_numerator_literal="Votes Cast", native_general_turnout_definition="voters signing in",
                          conditional_modeled_participant_units=str(voters), conditional_modeled_nonparticipant_units=str(nonvoters),
                          native_minus_conditional_participant_units=str(Decimal(native_count) - voters),
                          same_source_population_and_cutoff_proved=False, observed_staying_home=None,
                          population_transport_validation=False, design_confidence_interval=None,
                          group_population=None, local_allocation=False)
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=native_count,
                  control_registered_denominator=registered, control_denominator_basis=BASIS, control_native_time=TIME,
                  control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="NM", year=2026, geographic_level="state", geography="New Mexico",
                   source_family=URL, measure=MEASURE, native_measure="Native Votes Cast; general turnout sign-in definition",
                   numerator=native_count, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Registered Voters in native statewide and all-county turnout export",
                   source_time_label=TIME, source_url=URL, native_status="Unofficial; 2204/2204 precincts reporting; not certified",
                   source_kind="reviewed_public_observation", scope_notes="Native Ballots Cast/Votes Cast labels retained; no generic cast-ballot relabeling or demographic allocation.",
                   selected_state_reference=True, disposition="selected_state_reference_not_independent_validation")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="NM", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=TIME, source_url=URL,
                    civic_source_n=source["n"], civic_weight=source["weight"],
                    civic_modeled_voter_weight=source["modeled_voter_weight"], civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(voters), conditional_modeled_nonvoter_count=str(nonvoters),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None)
    scenarios.append(scenario)
    dated_raw = (inputs / "complete-dated-registration-reference.csv").read_bytes()
    dated = list(csv.DictReader(io.StringIO(dated_raw.decode())))
    if len(dated) != 34 or {row["native_county"] for row in dated} != {row["native_county"] for row in counties} | {"TOTAL"}:
        raise ValueError("Changed independently dated registration county scope")
    total = next(row for row in dated if row["native_county"] == "TOTAL")
    for key in ("native_democratic_registered", "native_republican_registered", "native_no_party_declined_registered", "native_other_registered", "native_registered"):
        if sum(int(row[key]) for row in dated if row["native_county"] != "TOTAL") != int(total[key]):
            raise ValueError("Dated registration county totals disagree")
    dated_query = []
    for row in counties:
        prior = next(value for value in dated if value["native_county"] == row["native_county"])
        dated_query.append(dict(native_county=row["native_county"], election_export_registered=row["native_registered_voters"],
                                separate_reference_date=prior["source_date"], separate_reference_registered=int(prior["native_registered"]),
                                native_count_difference=row["native_registered_voters"] - int(prior["native_registered"]),
                                source_frames_or_population_movement_proved=False, cohort_entry_or_exit=None))
    qualification.update(source_url=URL, survey_population_transport_validated=False,
                         separate_registration_reference_date="2026-10-30",
                         separate_registration_reference_total=int(total["native_registered"]),
                         separate_date_not_used_to_repair_election_denominator=True,
                         group_or_party_turnout_inferred=False, demographic_population=None, map_approved=False)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-new-mexico-native-counties.csv": csv_bytes(counties),
        "complete-new-mexico-native-precincts.csv": csv_bytes(precincts),
        "complete-new-mexico-native-state.csv": csv_bytes([state]),
        "complete-new-mexico-native-model-comparison.csv": csv_bytes([comparison]),
        "complete-dated-registration-reference.csv": dated_raw,
        "complete-dated-registration-comparisons.csv": csv_bytes(dated_query),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(
            state_and_dc_rows=len(states), native_controls=len(controls), conditional_scenarios=len(scenarios),
            native_counties=len(counties), native_precincts=len(precincts), native_registered=registered,
            native_reported_participants=native_count, native_printed_pct=state["native_printed_turnout"],
            zero_denominator_precincts=sum(row["native_registered_voters"] == 0 for row in precincts),
            all_50_unaffected_state_rows_and_nine_prior_scenarios_preserved=True,
            native_general_votes_cast_not_generic_cast_ballot_measure=True, statewide_survey_allocations=0)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite an existing complete analysis")
    files = build(inputs)
    receipts = json.loads((inputs / "source-receipts.json").read_bytes())
    originals = {"official-native-turnout-export.xlsx", "Statewide_10-30-2026.pdf", "County_Precincts_10-30-2026.pdf"}
    if len(receipts) != 3 or {row["file"] for row in receipts} != originals:
        raise ValueError("Changed complete native original set")
    for row in receipts:
        body = (inputs / row["file"]).read_bytes()
        if len(body) != row["bytes"] or hashlib.sha256(body).hexdigest() != row["sha256"]:
            raise ValueError("Changed complete source original")
    for name in ("official-native-turnout-export.xlsx", "baseline-complete-analysis.zip",
                 "Statewide_10-30-2026.pdf", "County_Precincts_10-30-2026.pdf",
                 "complete-dated-registration-reference.csv", "source-receipts.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/new_mexico_participation.py"] = Path(__file__).read_bytes()
    files["tests/test_new_mexico_participation.py"] = Path(__file__).parents[1].joinpath("tests/test_new_mexico_participation.py").read_bytes()
    files["requirements.txt"] = b"openpyxl>=3.1\n"
    files["README.txt"] = (
        "New Mexico source-defined registered turnout, not candidate votes or certified final turnout.\n"
        "All33 counties/2204 precincts, source zeros/clock/status and complete51-state query.\n"
        "Conditional register units assume unvalidated Civic-to-register exchangeability.\n"
        "Distinct October30 registration figures do not repair the election register or identify cohort movement.\n"
        "Install requirements in a suitable environment before offline reproduction.\n"
        "python -m unittest discover -s tests -p test_new_mexico_participation.py\n"
        "python -m scripts.new_mexico_participation --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                      for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
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
