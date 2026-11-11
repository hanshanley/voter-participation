"""Use Virginia's explicit registration parent, not its unusable state ballot zero."""

import argparse
import csv
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .washington_register_control import civic_source, count, csv_bytes, encoded


BASELINE_SHA = "acbdea7ae4d4d0c060f2b3ce94537bd63b8a169af7ef8e2fc300aeab948e1b6d"
NATIVE_SHA = "c4c28d7f426cd878b3b50672f4e5858b415c44c0cdcf7347f0ac339bc9521f43"
ELECTION = "01000000-ebdd-00dc-0143-08df1fee4ade"
JURISDICTION = "d2c804ee-4ec2-46bb-91d7-5b41526eab03"
CONTROL = "va-2026-held-explicit-register-parent-no-state-ballot-reference"
MEASURE = "native_totalVoters_registration_only_unusable_state_ballot_zero"
BASIS = "native_totalVoters_explicit_parent_active_inactive_components_reconcile_definition_unspecified"
URL = "https://enr.elections.virginia.gov/results/public/api/elections/virginia/2026-November-General/data"


def parent_frame(facts):
    state, jurisdiction = facts["election"], facts["jurisdiction"]
    if (state["id"] != ELECTION or state["jurisdictionId"] != JURISDICTION
            or jurisdiction["id"] != JURISDICTION or jurisdiction["shortName"] != "virginia"
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
    localities, registrations = facts["localityElections"], facts["voterRegistration"]
    index = {row["id"]: row for row in registrations}
    if len(localities) != 133 or len(registrations) != 133 or len(index) != 133:
        raise ValueError("Incomplete native locality parent coverage")
    seen, parent_sum, ballots, rows = set(), 0, 0, []
    for locality in localities:
        key = locality["jurisdictionId"]
        if key in seen or key not in index or locality["electionDate"] != "2026-11-03":
            raise ValueError("Changed native locality identities or election")
        seen.add(key)
        row = index[key]
        total, active, inactive = (count(row.get(field)) for field in ("total", "activeVoters", "inactiveVoters"))
        if count(locality.get("totalVoters")) != total:
            raise ValueError("Native locality and registration parent totals disagree")
        parent_sum += total
        native_ballots = count(locality.get("ballotsCast"))
        ballots += native_ballots
        rows.append(dict(
            state_code="VA", native_locality_uuid=key,
            locality=next(item["text"] for item in row["localityName"] if item["languageId"] == "en"),
            native_total=total, native_active=active, native_inactive=inactive,
            components_match_total=active + inactive == total, native_ballots=native_ballots,
            native_asOf=locality["asOf"], native_lastUpdated=locality["lastUpdated"],
            native_publishDate=locality["publishDate"],
            native_group_reporting_status=json.dumps(locality["groupReportingStatus"], sort_keys=True),
            native_precinct_reporting_status=json.dumps(locality["precinctReportingStatus"], sort_keys=True),
            native_rates_available=False, maps_approved=False, county_or_demographic_survey_allocation=False))
    if parent_sum != registered:
        raise ValueError("Locality parent registrations disagree with explicit state parent")
    if ballots <= 0:
        raise ValueError("Changed held locality-versus-state ballot conflict")
    return registered, ballots, rows


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "virginia-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or pinned native input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        receipt = json.loads(archive.read("native-locality-source/sources.json"))["parent-state"]
        body = gzip.decompress(archive.read("native-locality-source/originals/parent-state.gz"))
        if receipt["url"] != URL or hashlib.sha256(body).hexdigest() != receipt["sha256"]:
            raise ValueError("Changed native statewide API original")
        facts = json.loads(body)
        audit = json.loads(archive.read("counts-review.json"))
        precinct_raw = archive.read("precinct-turnout.csv")
    registered, locality_ballots, parents = parent_frame(facts)
    if (audit["localities"] != 133 or audit["native_locality_ballots"] != locality_ballots
            or audit["native_turnout_rows"] != 2529 or audit["native_precinct_turnout"] != 2798626
            or audit["incomplete_locality_house_scopes"] != 69
            or audit["maps_approved"] is not False or audit["rates_available"] is not False
            or not all(row["components_match_total"] for row in parents)):
        raise ValueError("Changed completed locality/precinct accounting or component reconciliation")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 25, 14):
        raise ValueError("Changed complete version09 coverage")
    target = next(row for row in states if row["state_code"] == "VA")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Virginia frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "VA" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = registered * (voter / weight), registered * (nonvoter / weight)
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional registration partition failed")
    state = facts["election"]
    time = "; ".join(field + "=" + state[field] for field in ("asOf", "lastUpdated", "publishDate"))
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="VA", year=2026, geographic_level="state", geography="Virginia",
                   source_family=URL, measure=MEASURE, native_measure="Native totalVoters registration parent only; statewide ballotsCast=0 unusable",
                   numerator=None, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Explicit statewide totalVoters; native active/inactive components reconcile; definitions unqualified",
                   source_time_label=time, source_url=URL, native_status="Unofficial; statewide reporting status missing",
                   source_kind="reviewed_public_registration_only_observation",
                   scope_notes="State ballot zero not observed zero; locality sums diagnostic only. Distinct clocks, unreported modes and all 69 locality/House residual scopes preserved; no local survey allocation.",
                   selected_state_reference=False, disposition="registration_frame_only_no_selected_state_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="VA", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None)
    scenarios.append(scenario)
    qualification = dict(
        election_id=ELECTION, native_publish_version=state["publishVersionId"],
        native_state_registered_parent=registered, native_state_ballotsCast=state["ballotsCast"],
        diagnostic_locality_ballot_sum_not_statewide_result=locality_ballots,
        selected_statewide_ballot_reference=None, native_minus_model=None,
        parent_registration_not_inferred_from_locality_sum=True, native_register_definition=BASIS,
        registration_components_match_totals=True, registered_active_inactive_definition=None,
        survey_population_transport_validated=False,
        native_asOf=state["asOf"], native_lastUpdated=state["lastUpdated"], native_publishDate=state["publishDate"],
        native_precinct_reporting_status=state["precinctReportingStatus"], source_clocks_not_acquisition_time=True,
        native_precinct_observation_rows=2529, partial_native_precinct_turnout_not_statewide=2798626,
        incomplete_locality_house_scopes=69, locality_mode_residuals_and_distinct_clocks_not_allocated=True,
        original_precinct_observation_bytes_preserved=True, complete=False, unofficial=True,
        native_rates_available=False, maps_approved=False, generic_cast_ballot_measure_approved=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        original_candidate_precinct_geometry_and_private_survey_reductions_reused_not_repeated=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-virginia-native-locality-parents.csv": csv_bytes(parents),
        "complete-virginia-prior-precinct-observations.csv": precinct_raw,
        "complete-virginia-registration-frame.csv": csv_bytes([dict(
            state_code="VA", year=2026, explicit_native_registered_parent=registered,
            native_state_ballotsCast=state["ballotsCast"], selected_statewide_ballots=None,
            diagnostic_locality_ballot_sum_not_statewide_result=locality_ballots,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            registration_components_match_totals=True, native_minus_model=None,
            rate_approved=False, map_approved=False, observed_staying_home=None)]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, native_control_records=26, conditional_scenarios=15,
                                    registration_only_controls_added=1, reported_state_ballot_controls_added=0,
                                    native_localities=133, native_precinct_observation_rows=2529,
                                    explicit_native_registered_parent=registered, selected_statewide_ballots=None,
                                    registration_components_match_totals=True,
                                    all_fifty_unaffected_states_fourteen_frames_and_twenty_five_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "virginia-complete-native-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("virginia_register_control.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_virginia_register_control.py"] = Path(__file__).parents[1].joinpath("tests/test_virginia_register_control.py").read_bytes()
    files["README.txt"] = (
        "Virginia registration-only conditional frame; no selected observed statewide ballots.\n"
        "Explicit state totalVoters6494441 is not inferred from locality or precinct sums.\n"
        "State ballotsCast=0 conflicts with locality3593781; preserve it, never repair or call it zero turnout.\n"
        "All133 locality parent clocks/statuses and2529 old precinct observation bytes retained.\n"
        "Precinct2798626 and69 locality/House residual scopes remain partial/unallocated; no local survey allocation.\n"
        "Conditional register units assume unvalidated Civic-to-register exchangeability; no observed staying-home claim.\n"
        "Includes full version09 baseline/native inputs and unchanged maintained Washington shared helpers.\n"
        "python3 -m unittest discover -s tests -p test_virginia_register_control.py\n"
        "python3 -m scripts.virginia_register_control --inputs inputs --output reproduced\n").encode()
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
