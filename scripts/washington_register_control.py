"""Use the held Washington registration parent without repairing its ballot zero."""

import argparse
import csv
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile


BASELINE_SHA = "1a3605a0f6258b260b556810d72052ef91bbbe1087cec0868ab3380a9227a1ee"
NATIVE_SHA = "2ec14a19014b561d3d1ac123e8bb93360ae661e2d4a0d919fc00e5d7ebd5eae1"
ELECTION = "01000000-a578-3971-654b-08defdf81b1d"
JURISDICTION = "01000000-f977-1a83-1ed4-08ddd69e9e69"
CONTROL = "wa-2026-held-explicit-register-parent-no-state-ballot-reference"
MEASURE = "native_totalVoters_registration_only_unusable_state_ballot_zero"
BASIS = "native_totalVoters_parent_corroborated_voterRegistration_active_inactive_unspecified"
URL = "https://results.votewa.gov/results/public/api/elections/washington/20261103/data"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def count(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError("Missing or invalid explicit native parent count")
    return int(value)


def parent_frame(facts):
    state, jurisdiction = facts["state_election"], facts["state_jurisdiction"]
    if (state["id"] != ELECTION or state["jurisdictionId"] != JURISDICTION
            or jurisdiction["id"] != JURISDICTION or jurisdiction["shortName"] != "washington"
            or state["electionDate"] != "2026-11-03" or state["isPrimary"] is not False
            or state["isOfficialResults"] is not False):
        raise ValueError("Changed native election identity or unofficial status")
    registered = count(state.get("totalVoters"))
    if registered <= 0:
        raise ValueError("Missing positive explicit statewide registration parent")
    if count(state.get("ballotsCast")) != 0:
        raise ValueError("Changed native ballot-zero conflict; review a new source version")
    for field in ("asOf", "lastUpdated", "publishDate"):
        if not isinstance(state.get(field), str) or not state[field].endswith("Z"):
            raise ValueError("Changed native declared UTC clocks")
    counties, localities = facts["counties"], facts["state_locality_elections"]
    index = {row["jurisdictionId"]: row for row in localities}
    if len(counties) != 39 or len(localities) != 39 or len(index) != 39:
        raise ValueError("Incomplete native county parent coverage")
    seen, registrations, ballots = set(), 0, 0
    for county in counties:
        election = county["election"]
        key = county["jurisdiction"]["id"]
        if key in seen or election["jurisdictionId"] != key or key not in index:
            raise ValueError("Changed native county identities")
        seen.add(key)
        other = index[key]
        if election["id"] != other["id"] or election["electionDate"] != state["electionDate"]:
            raise ValueError("Different native county election")
        for field in ("totalVoters", "ballotsCast"):
            if count(election.get(field)) != count(other.get(field)):
                raise ValueError("Independent native county parent counts disagree")
        registrations += count(election["totalVoters"])
        ballots += count(election["ballotsCast"])
    if registrations != registered:
        raise ValueError("County parent registrations disagree with explicit state parent")
    if ballots <= 0:
        raise ValueError("Changed held county-versus-state ballot conflict")
    return registered, ballots


def civic_source(baseline):
    visited = set()
    while True:
        digest = hashlib.sha256(baseline).hexdigest()
        if digest in visited:
            raise ValueError("Repeated sufficient baseline")
        visited.add(digest)
        with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
            if "inputs/civic-selected-aggregates.json" in archive.namelist():
                return json.loads(archive.read("inputs/civic-selected-aggregates.json"))
            baseline = archive.read("inputs/baseline-complete-analysis.zip")


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "washington-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or immutable native input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        facts = json.loads(gzip.decompress(archive.read("source-records.json.gz")))
        audit = json.loads(archive.read("audit.json"))
        county_raw, unit_raw = (archive.read(name) for name in ("county-participation.csv", "native-unit-participation.csv"))
    registered, county_ballots = parent_frame(facts)
    if (audit["county_observations"] != 39 or audit["native_unit_observations"] != 9588
            or audit["independently_matched_state_county_headers"] != 39
            or audit["native_state_total_voters"] != registered or audit["county_registered_sum"] != registered
            or audit["county_ballots_sum"] != county_ballots or audit["native_state_ballots"] != 0
            or audit["unallocated_county_ballots"] != 601199
            or audit["maps_approved"] is not False or audit["statewide_completion_approved"] is not False):
        raise ValueError("Changed previously completed native accounting")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 23, 12):
        raise ValueError("Changed complete version07 coverage")
    target = next(row for row in states if row["state_code"] == "WA")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Washington frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "WA" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = registered * (voter / weight), registered * (nonvoter / weight)
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional registration partition failed")
    state = facts["state_election"]
    time = "; ".join(field + "=" + state[field] for field in ("asOf", "lastUpdated", "publishDate"))
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="WA", year=2026, geographic_level="state", geography="Washington",
                   source_family=URL, measure=MEASURE, native_measure="Native totalVoters registration parent only; statewide ballotsCast=0 unusable",
                   numerator=None, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Explicit statewide totalVoters corroborated by native voterRegistration; active/inactive unspecified",
                   source_time_label=time, source_url=URL, native_status="Unofficial; statewide reporting status missing",
                   source_kind="reviewed_public_registration_only_observation",
                   scope_notes="Native state ballot zero retained, not used as observed zero; county ballot sum is diagnostic only. No statewide ballot reference, rate, residual or population validation.",
                   selected_state_reference=False, disposition="registration_frame_only_no_selected_state_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="WA", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None)
    scenarios.append(scenario)
    qualification = dict(
        election_id=ELECTION, native_state_registered_parent=registered, native_state_ballotsCast=state["ballotsCast"],
        diagnostic_county_ballot_sum_not_statewide_result=county_ballots,
        selected_statewide_ballot_reference=None, native_minus_model=None,
        parent_registration_not_inferred_from_county_sum=True, native_register_definition=BASIS,
        registered_active_inactive_definition=None, survey_population_transport_validated=False,
        native_asOf=state["asOf"], native_lastUpdated=state["lastUpdated"], native_publishDate=state["publishDate"],
        native_precinct_reporting_status=state["precinctReportingStatus"], source_clocks_not_acquisition_time=True,
        native_units=9588, unallocated_king_county_ballots=601199, king_unit_ballot_zeros_not_zero_participation=True,
        original_county_and_unit_bytes_preserved=True, complete=False, unofficial=True,
        native_rates_available=False, maps_approved=False, generic_cast_ballot_measure_approved=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        original_native_and_survey_reductions_reused_not_repeated=True, two_denied_routes_remain_stopped=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-washington-native-county-observations.csv": county_raw,
        "complete-washington-native-unit-observations.csv": unit_raw,
        "complete-washington-registration-frame.csv": csv_bytes([dict(
            state_code="WA", year=2026, explicit_native_registered_parent=registered,
            native_state_ballotsCast=state["ballotsCast"], selected_statewide_ballots=None,
            diagnostic_county_ballot_sum_not_statewide_result=county_ballots,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            native_minus_model=None, rate_approved=False, map_approved=False, observed_staying_home=None)]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, native_control_records=24, conditional_scenarios=13,
                                    registration_only_controls_added=1, reported_state_ballot_controls_added=0,
                                    native_counties=39, native_units=9588, explicit_native_registered_parent=registered,
                                    selected_statewide_ballots=None, native_ballot_zero_not_observed_zero=True,
                                    all_fifty_unaffected_states_twelve_frames_and_twenty_three_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "washington-complete-native-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/washington_register_control.py"] = Path(__file__).read_bytes()
    files["tests/test_washington_register_control.py"] = Path(__file__).parents[1].joinpath("tests/test_washington_register_control.py").read_bytes()
    files["README.txt"] = (
        "Washington registration-only conditional frame; no selected observed statewide ballots.\n"
        "Explicit state totalVoters5170951 is corroborated by native voterRegistration, not inferred from county sums.\n"
        "Native statewide ballotsCast=0 conflicts with county2266746; preserve it, never repair or call it zero turnout.\n"
        "All39county/9588unit rows remain byte-identical; King601199 ballots remain unallocated.\n"
        "Conditional register units assume unvalidated Civic-to-register exchangeability; no observed staying-home claim.\n"
        "Includes full version07 baseline/native inputs. Prior reductions/acquisitions are reused, not repeated.\n"
        "python3 -m unittest discover -s tests -p test_washington_register_control.py\n"
        "python3 -m scripts.washington_register_control --inputs inputs --output reproduced\n").encode()
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
