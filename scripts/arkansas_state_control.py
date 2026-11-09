"""Use explicit native Arkansas state/county parents without filling missing leaves."""

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile


BASELINE_SHA = "23a2200d20a92885cc9d9429c37f86024b0c6222176761981ca2b217ec0c9aaa"
NATIVE_SHA = "2a48bbc62c55b074c877172c94da4b02de0546211322c576200818e5b16548a9"
ELECTION = "11b07106-031e-4d7c-911a-d01fb473d6dd"
CONTROL = "ar-2026-held-explicit-state-county-parent-turnout"
URL = "https://arkansas.tally-enr.com/#bucket=results"
MEASURE = "native_totalBallotsCast_unofficial_partial_reporting"
BASIS = "native_registeredVoters_explicit_parent_active_inactive_unspecified"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError("Missing or invalid native parent count")
    return value


def parent_frames(identity, turnout):
    if (identity["electionID"] != ELECTION or turnout["electionID"] != ELECTION
            or identity["response"]["id"] != ELECTION
            or identity["response"]["date"] != "2026-11-03T00:00:00"
            or identity["response"]["name"] != "2026 General Election & Judical Runoff"):
        raise ValueError("Different native general-election identity")
    if (identity["versionID"] != turnout["versionID"] or identity["lastUpdated"] != turnout["lastUpdated"]
            or identity["isOfficial"] is not False or turnout["isOfficial"] is not False):
        raise ValueError("Changed native snapshot or certification status")
    if not identity["lastUpdated"].endswith("Z"):
        raise ValueError("Changed declared native UTC report clock")
    state = turnout["response"]
    fields = ("registeredVoters", "totalBallotsCast", "precinctsReporting", "precinctsPartiallyReporting", "totalPrecincts")
    for key in fields:
        if count(state.get(key)) != count(identity["turnout"].get(key)) or state[key] != turnout["turnout"].get(key):
            raise ValueError("Independent native parent snapshots disagree")
    if state["registeredVoters"] <= 0 or state["totalBallotsCast"] > state["registeredVoters"]:
        raise ValueError("Invalid source-defined parent registration frame")
    if state["precinctsReporting"] + state["precinctsPartiallyReporting"] != state["totalPrecincts"]:
        raise ValueError("Changed native reporting categories")
    if (100 * Decimal(state["totalBallotsCast"]) / state["registeredVoters"]).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(str(state["votePercent"])):
        raise ValueError("Native parent printed percentage disagrees")
    locations = state["locations"]
    if len(locations) != 75 or set(locations) != set(identity["response"]["locations"]):
        raise ValueError("Incomplete native county parent coverage")
    rows = []
    for code, row in locations.items():
        declaration = identity["response"]["locations"][code]
        if row["locationID"] != code or declaration["locationID"] != code:
            raise ValueError("Changed native county identity")
        for key in fields:
            count(row.get(key))
        if row["registeredVoters"] <= 0 or row["totalBallotsCast"] > row["registeredVoters"]:
            raise ValueError("Invalid native county parent frame")
        rows.append(dict(
            state_code="AR", year=2026, native_county_code=code, native_county=declaration["locationName"],
            native_registered=row["registeredVoters"], native_ballots=row["totalBallotsCast"],
            native_printed_pct=row.get("votePercent"), native_reporting=row["precinctsReporting"],
            native_partially_reporting=row["precinctsPartiallyReporting"], native_total_precincts=row["totalPrecincts"],
            native_version=identity["versionID"], native_lastUpdated=identity["lastUpdated"],
            unofficial=True, complete=False, native_rates_available=False, map_approved=False,
            county_or_demographic_survey_allocation=False))
    for field in ("native_registered", "native_ballots", "native_reporting", "native_partially_reporting", "native_total_precincts"):
        original = dict(native_registered="registeredVoters", native_ballots="totalBallotsCast",
                        native_reporting="precinctsReporting", native_partially_reporting="precinctsPartiallyReporting",
                        native_total_precincts="totalPrecincts")[field]
        if sum(row[field] for row in rows) != state[original]:
            raise ValueError("County parent sums disagree with separate native statewide parent")
    return state, rows


def civic_source(baseline):
    for _ in range(4):
        with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
            if "inputs/civic-selected-aggregates.json" in archive.namelist():
                return json.loads(archive.read("inputs/civic-selected-aggregates.json"))
            baseline = archive.read("inputs/baseline-complete-analysis.zip")
    raise ValueError("Missing complete public survey baseline")


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    original = (inputs / "arkansas-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(original).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or immutable native input")
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        checksums = json.loads(archive.read("checksums.json"))
        for name, metadata in checksums.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient native source member")
        receipts = json.loads(archive.read("native-source/sources.json"))
        def response(route):
            name = next(name for name, record in receipts.items() if route in record["url"])
            body = gzip.decompress(archive.read("native-source/originals/" + name + ".gz"))
            if hashlib.sha256(body).hexdigest() != receipts[name]["sha256"]:
                raise ValueError("Changed native API original")
            return json.loads(body)
        identity, turnout = response("/Election/GetElectionInfo?"), response("/Turnout/GetTurnout?")
        leaf_raw = archive.read("precinct-participation.csv")
        audit = json.loads(archive.read("counts-review.json"))
    state, counties = parent_frames(identity, turnout)
    leaves = list(csv.DictReader(io.StringIO(leaf_raw.decode())))
    if (len(leaves) != 2768 or len({(row["county_code"], row["precinct_code"]) for row in leaves}) != 2768
            or {row["county_code"] for row in leaves} != {row["native_county_code"] for row in counties}
            or audit["all_observed_ballot_scopes_reconcile"] is not True
            or audit["native_ballots"] != state["totalBallotsCast"]):
        raise ValueError("Changed reused complete native leaf query")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if len(states) != 51 or len(controls) != 22 or len(scenarios) != 11:
        raise ValueError("Changed complete version06 coverage")
    target = next(row for row in states if row["state_code"] == "AR")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Arkansas control")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "AR" and row["dimension"] == "overall")
    time = "Native API lastUpdated " + identity["lastUpdated"] + "; version " + identity["versionID"] + "; unofficial"
    registered, ballots = state["registeredVoters"], state["totalBallotsCast"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = registered * (voter / weight), registered * (nonvoter / weight)
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional parent-register partition failed")
        comparison = dict(
            state_code="AR", year=2026, native_ballots=ballots, native_registered_parent=registered,
            native_printed_pct=str(state["votePercent"]), native_version=identity["versionID"], native_clock=identity["lastUpdated"],
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            native_minus_conditional_participant_units=str(Decimal(ballots) - modeled),
            source_population_and_cutoff_match_proved=False, design_confidence_interval=None,
            observed_staying_home=None, group_population=None, native_rates_available=False,
            map_approved=False, county_or_demographic_allocation=False)
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=ballots,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="AR", year=2026, geographic_level="state", geography="Arkansas",
                   source_family=URL, measure=MEASURE, native_measure="Native totalBallotsCast; unofficial partial reporting",
                   numerator=ballots, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Explicit statewide registeredVoters parent; active/inactive definition not supplied",
                   source_time_label=time, source_url=URL, native_status="Unofficial; 2761 reporting and 7 partial of 2768",
                   source_kind="reviewed_public_observation", scope_notes="Both state headers and all75 county parents reconcile. Missing leaf registrations/ballots retained; no imputation or geographic approval.",
                   selected_state_reference=True, disposition="selected_state_reference_not_independent_validation")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="AR", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None)
    scenarios.append(scenario)
    qualification = dict(
        election_id=ELECTION, election_date="2026-11-03", native_version=identity["versionID"],
        native_lastUpdated=identity["lastUpdated"], source_clock_not_acquisition_time=True,
        independent_election_and_turnout_parent_snapshots_agree=True,
        explicit_state_registered_parent_not_inferred_from_partial_leaves=True,
        registered_active_inactive_definition=None, survey_population_transport_validated=False,
        leaf_missing_registrations=sum(row["registered_voters"] == "" for row in leaves),
        leaf_missing_ballots=sum(row["ballots"] == "" for row in leaves),
        missing_leaf_fields_not_imputed_or_allocated=True, complete=False, unofficial=True,
        native_rates_available=False, maps_approved=False, generic_cast_ballot_measure_approved=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-arkansas-native-county-parents.csv": csv_bytes(counties),
        "complete-arkansas-native-precinct-observations.csv": leaf_raw,
        "complete-arkansas-native-model-comparison.csv": csv_bytes([comparison]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(
            state_and_dc_rows=51, native_controls=23, conditional_scenarios=12,
            native_counties=75, native_leaf_rows=2768, native_ballots=ballots, explicit_native_registered=registered,
            native_printed_pct=state["votePercent"], leaf_missing_registrations=qualification["leaf_missing_registrations"],
            leaf_missing_ballots=qualification["leaf_missing_ballots"], all_fifty_unaffected_states_and_eleven_prior_frames_preserved=True,
            no_original_candidate_or_survey_reduction_repeated=True, no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "arkansas-complete-native-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/arkansas_state_control.py"] = Path(__file__).read_bytes()
    files["tests/test_arkansas_state_control.py"] = Path(__file__).parents[1].joinpath("tests/test_arkansas_state_control.py").read_bytes()
    files["README.txt"] = (
        "Explicit Arkansas state/county registered parents, not a reconstruction of missing precinct registration.\n"
        "All75 county parents reconcile to native1856404 registered/893026 ballots; unofficial v173 UTC clock retained.\n"
        "1108 missing leaf registrations and82 missing ballot totals remain absent, not zero or allocated.\n"
        "Conditional register units assume unvalidated Civic-to-register exchangeability; no observed staying-home claim.\n"
        "Complete51-state query/23controls/12frames includes sufficient native originals and full previous baseline.\n"
        "python3 -m unittest discover -s tests -p test_arkansas_state_control.py\n"
        "python3 -m scripts.arkansas_state_control --inputs inputs --output reproduced\n").encode()
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
