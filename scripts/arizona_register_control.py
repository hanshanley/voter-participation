"""Use Arizona's explicit registration parent, preserving source component conflicts."""

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


BASELINE_SHA = "9827582220ea5cd94b7ca56e0a52f58752470f0017ecb22b64febab5f61b086c"
NATIVE_SHA = "8c8626b93899f8f9b935d1d7076a47b1bb75fd850c344f992066faa162ae0cc3"
ELECTION = "01000000-3e48-04ed-11b1-08df1107098b"
JURISDICTION = "01000000-0496-9e5d-0291-08dbda35db79"
CONTROL = "az-2026-held-explicit-register-parent-source-components-conflict"
MEASURE = "native_totalVoters_registration_only_ballot_zero_component_conflicts"
BASIS = "native_totalVoters_explicit_parent_active_inactive_components_inconsistent"
URL = "https://app.enhancedvoting.com/results/public/api/elections/Arizona/110326GeneralElection/data"


def parent_frame(facts):
    state, jurisdiction = facts["election"], facts["jurisdiction"]
    if (state["id"] != ELECTION or state["jurisdictionId"] != JURISDICTION
            or jurisdiction["id"] != JURISDICTION or jurisdiction["shortName"] != "Arizona"
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
    if len(localities) != 15 or len(registrations) != 15 or len(index) != 15:
        raise ValueError("Incomplete native county parent coverage")
    seen, parent_sum, ballots, components = set(), 0, 0, []
    for locality in localities:
        key = locality["jurisdictionId"]
        if key in seen or key not in index or locality["electionDate"] != "2026-11-03":
            raise ValueError("Changed native county identities or election")
        seen.add(key)
        row = index[key]
        total, active, inactive = (count(row.get(field)) for field in ("total", "activeVoters", "inactiveVoters"))
        if count(locality.get("totalVoters")) != total:
            raise ValueError("Native locality and registration parent totals disagree")
        parent_sum += total
        ballots += count(locality.get("ballotsCast"))
        components.append(dict(
            state_code="AZ", native_county_uuid=key, native_total=total, native_active=active,
            native_inactive=inactive, components_sum=active + inactive,
            native_total_minus_components=total - active - inactive, components_match_total=active + inactive == total,
            total_not_repaired_from_components=True))
    if parent_sum != registered:
        raise ValueError("County parent registrations disagree with explicit state parent")
    if ballots <= 0:
        raise ValueError("Changed held county-versus-state ballot conflict")
    return registered, ballots, components


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "arizona-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or pinned native input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        receipts = json.loads(archive.read("native-source/sources.json"))
        name = next(name for name, row in receipts.items() if row["url"] == URL)
        body = gzip.decompress(archive.read("native-source/originals/" + name + ".gz"))
        if hashlib.sha256(body).hexdigest() != receipts[name]["sha256"]:
            raise ValueError("Changed native statewide API original")
        facts = json.loads(body)
        audit = json.loads(archive.read("counts-review.json"))
        county_raw, precinct_raw = (archive.read(name) for name in ("county-participation.csv", "precinct-participation.csv"))
    registered, county_ballots, components = parent_frame(facts)
    review = audit["api_review"]
    missing = review["missing_participation_rows"]
    if (review["native_county_registration_sum"] != registered or review["observed_county_ballot_sum"] != county_ballots
            or review["native_state_ballot_field"] != 0 or review["native_registration_components_match_totals"] is not False
            or review["all_observed_precinct_county_participation_scopes_reconcile"] is not True
            or review["native_api_precincts"] != 1763 or review["native_participation_observations"] != 1762
            or len(missing) != 1 or missing[0]["native_observation_present"] is not False
            or missing[0]["ballots"] is not None or missing[0]["registered_voters"] is not None
            or all(row["components_match_total"] for row in components)
            or audit["maps_approved"] is not False or audit["rates_available"] is not False):
        raise ValueError("Changed previously completed native accounting or missing virtual record")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 24, 13):
        raise ValueError("Changed complete version08 coverage")
    target = next(row for row in states if row["state_code"] == "AZ")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Arizona frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "AZ" and row["dimension"] == "overall")
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
    control.update(id=CONTROL, state_code="AZ", year=2026, geographic_level="state", geography="Arizona",
                   source_family=URL, measure=MEASURE, native_measure="Native totalVoters registration parent only; ballot zero and component conflicts retained",
                   numerator=None, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Explicit statewide totalVoters; native active/inactive components do not explain totals",
                   source_time_label=time, source_url=URL, native_status="Unofficial; statewide reporting status missing",
                   source_kind="reviewed_public_registration_only_observation",
                   scope_notes="Registration totals not repaired from active/inactive components. State ballot zero retained but not observed zero; county ballot sum diagnostic only; virtual precinct remains missing.",
                   selected_state_reference=False, disposition="registration_frame_only_no_selected_state_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="AZ", control_id=CONTROL, control_measure=MEASURE,
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
        diagnostic_county_ballot_sum_not_statewide_result=county_ballots,
        selected_statewide_ballot_reference=None, native_minus_model=None,
        parent_registration_not_inferred_from_county_sum=True, native_register_definition=BASIS,
        registration_components_match_totals=False, registration_totals_not_repaired=True,
        registered_active_inactive_definition=None, survey_population_transport_validated=False,
        native_asOf=state["asOf"], native_lastUpdated=state["lastUpdated"], native_publishDate=state["publishDate"],
        native_precinct_reporting_status=state["precinctReportingStatus"], source_clocks_not_acquisition_time=True,
        native_precinct_inventory_rows=1763, missing_virtual_participation_rows=missing,
        original_county_and_precinct_bytes_preserved=True, complete=False, unofficial=True,
        native_rates_available=False, maps_approved=False, generic_cast_ballot_measure_approved=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        original_candidate_precinct_and_private_survey_reductions_reused_not_repeated=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-arizona-native-county-observations.csv": county_raw,
        "complete-arizona-native-precinct-observations.csv": precinct_raw,
        "complete-arizona-native-register-components.csv": csv_bytes(components),
        "complete-arizona-registration-frame.csv": csv_bytes([dict(
            state_code="AZ", year=2026, explicit_native_registered_parent=registered,
            native_state_ballotsCast=state["ballotsCast"], selected_statewide_ballots=None,
            diagnostic_county_ballot_sum_not_statewide_result=county_ballots,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            registration_components_match_totals=False, native_minus_model=None,
            rate_approved=False, map_approved=False, observed_staying_home=None)]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, native_control_records=25, conditional_scenarios=14,
                                    registration_only_controls_added=1, reported_state_ballot_controls_added=0,
                                    native_counties=15, native_precinct_inventory_rows=1763,
                                    explicit_native_registered_parent=registered, selected_statewide_ballots=None,
                                    registration_components_match_totals=False, missing_virtual_rows=1,
                                    all_fifty_unaffected_states_thirteen_frames_and_twenty_four_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "arizona-complete-native-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("arizona_register_control.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_arizona_register_control.py"] = Path(__file__).parents[1].joinpath("tests/test_arizona_register_control.py").read_bytes()
    files["README.txt"] = (
        "Arizona registration-only conditional frame; no selected observed statewide ballots.\n"
        "Explicit state totalVoters4374827 is not inferred from county sums or repaired active/inactive components.\n"
        "State ballotsCast=0 conflicts with county2248900; preserve it, never repair or call it zero turnout.\n"
        "All15county/1763precinct CSV rows and missing Mohave virtual participation remain byte-identical.\n"
        "Conditional register units assume unvalidated Civic-to-register exchangeability; no observed staying-home claim.\n"
        "Includes full version08 baseline/native inputs and unchanged maintained Washington shared helpers.\n"
        "python3 -m unittest discover -s tests -p test_arizona_register_control.py\n"
        "python3 -m scripts.arizona_register_control --inputs inputs --output reproduced\n").encode()
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
