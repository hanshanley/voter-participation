"""Use Alaska's federal ballot/registration parents without blending reporting scopes."""

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


BASELINE_SHA = "0f6ae19dfb2484e19f7a572c4a1357bada64798d7089d9d996fccccfb2bfc89a"
NATIVE_SHA = "a38164a74cb3d433587891fdf243484f273a88f27f8439ceeeeb9da9c6772b3a"
HOUSE = "U.S. Representative"
SENATE = "U.S. Senator"
GOVERNOR = "Governor / Lieutenant Governor"
CONTROL = "ak-2026-held-native-federal-ballot-registration-parent"
MEASURE = "native_federal_scope_reported_ballots_b_unofficial_partial"
BASIS = "native_federal_scope_registered_v_status_definition_unspecified"
URL = "https://www.elections.alaska.gov/enr/26GENR/results/statewide.js"


def select(data, office):
    if data["contestNames"].count(office) != 1:
        raise ValueError("Missing or duplicate native contest identity")
    index = data["contestNames"].index(office)
    matches = [row for row in data["totals"] if row["n"] == index]
    if len(matches) != 1:
        raise ValueError("Missing or duplicate native contest parent")
    return matches[0]


def parent_frame(statewide, precincts, federal):
    for data in (statewide, precincts):
        if (data["name"] != "Alaska 2026 General Election" or data["format"] != "2024"
                or data["certified"] is not False):
            raise ValueError("Changed native election identity, export format or certification")
    for field in ("name", "updated", "certified", "format"):
        if statewide[field] != precincts[field]:
            raise ValueError("Native endpoint snapshots disagree")
    house = select(statewide, HOUSE)
    counterpart, senate, governor = (select(data, office) for data, office in (
        (precincts, HOUSE), (statewide, SENATE), (statewide, GOVERNOR)))
    for field in ("b", "v", "p", "r", "t"):
        if count(house.get(field)) != count(counterpart.get(field)):
            raise ValueError("Native federal parent snapshots disagree")
    for field in ("b", "v", "p", "r"):
        if house[field] != count(senate.get(field)):
            raise ValueError("Native federal contest scopes disagree")
    if (house["v"] <= 0 or house["b"] > house["v"] or house["p"] <= 0 or house["r"] > house["p"]):
        raise ValueError("Invalid native ballot/register/reporting parent")
    if (federal["reporting_unit_kind"] != "federal_overseas"
            or count(house["b"]) - count(governor.get("b")) != count(federal.get("ballots"))
            or count(house["v"]) - count(governor.get("v")) != count(federal.get("registered"))):
        raise ValueError("Federal-overseas and governor scopes must remain distinct")
    return house, governor


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "alaska-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or pinned native input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        receipts = json.loads(archive.read("sources.json"))
        originals = {}
        for name in ("statewide-original.json", "precincts-original.json"):
            body = gzip.decompress(archive.read("originals/" + name + ".gz"))
            if hashlib.sha256(body).hexdigest() != receipts[name]["sha256"]:
                raise ValueError("Changed native parent original")
            originals[name] = json.loads(body)
        audit = json.loads(archive.read("audit.json"))
        observations_raw = archive.read("participation.json.gz")
    observations = json.loads(gzip.decompress(observations_raw))
    federal_rows = [row for row in observations if row["reporting_unit_kind"] == "federal_overseas"]
    if len(federal_rows) != 1:
        raise ValueError("Changed native federal-overseas scope")
    state, precincts = originals["statewide-original.json"], originals["precincts-original.json"]
    parent, governor = parent_frame(state, precincts, federal_rows[0])
    registered, ballots = parent["v"], parent["b"]
    if (audit["registrations"] != registered or audit["ballots"] != ballots
            or audit["reporting_units"] != 523 or len(observations) != 523
            or audit["rates_available"] != 0 or audit["rates_withheld"] != 523
            or audit["reconciliation"]["geographic_precincts"] != 402
            or audit["reconciliation"]["pooled_reporting_units"] != 120
            or audit["reconciliation"]["federal_overseas_units"] != 1):
        raise ValueError("Changed previously completed native accounting")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 26, 15):
        raise ValueError("Changed complete version10 coverage")
    target = next(row for row in states if row["state_code"] == "AK")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Alaska frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "AK" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = registered * (voter / weight), registered * (nonvoter / weight)
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional registration partition failed")
        difference = Decimal(ballots) - modeled
    time = "Native updated=" + state["updated"] + "; timezone undeclared; uncertified"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=ballots,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="AK", year=2026, geographic_level="state", geography="Alaska federal reporting scope",
                   source_family=URL, measure=MEASURE, native_measure="Native federal contest b ballots, not t candidate selections",
                   numerator=ballots, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Explicit federal parent v registered; includes federal overseas; status definition unspecified",
                   source_time_label=time, source_url=URL, native_status="Unofficial; uncertified; 400 of 403 reporting",
                   source_kind="reviewed_public_native_federal_participation_observation",
                   scope_notes="Federal-overseas130 ballots/822 registrations retained; governor scope separate. No precinct/pooled allocation, native rate or final RCV/population approval.",
                   selected_state_reference=True, disposition="selected_native_federal_reference_not_independent_validation")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="AK", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None)
    scenarios.append(scenario)
    headers = []
    for row in state["totals"]:
        office = state["contestNames"][row["n"]]
        role = {HOUSE: "selected_native_federal_parent", SENATE: "federal_scope_header_corroboration_only",
                GOVERNOR: "different_scope_header_only_not_additive"}.get(office, "unreviewed_other_contest_header_not_additive")
        headers.append(dict(native_contest_index=row["n"], office=office, native_ballots_b=row.get("b"),
                            native_candidate_selections_t=row.get("t"), native_registered_v=row.get("v"),
                            native_precincts_expected_p=row.get("p"), native_precincts_reported_r=row.get("r"),
                            disposition=role))
    qualification = dict(
        election="Alaska 2026 General Election", year=2026, native_export_format=state["format"],
        export_format_not_election_year=True, native_updated=state["updated"], native_timezone=None,
        native_federal_registered_parent=registered, native_federal_ballots_b=ballots,
        native_house_candidate_selections_t=parent["t"], native_expected_precincts_p=parent["p"],
        native_reported_precincts_r=parent["r"], expected_precinct_count_is_not_percent=True,
        native_governor_ballots_b=governor["b"], native_governor_registered_v=governor["v"],
        native_federal_overseas=federal_rows[0], governor_and_federal_scopes_not_blended=True,
        parent_registration_not_inferred_from_unit_sum=True, native_register_definition=BASIS,
        registered_active_inactive_definition=None, survey_population_transport_validated=False,
        source_clock_not_acquisition_time=True, original_523_reporting_unit_bytes_preserved=True,
        source_reconciliation_holds=audit["reconciliation"], complete=False, unofficial=True, certified=False,
        native_rates_available=False, maps_approved=False, generic_cast_ballot_measure_approved=False,
        final_ranked_choice_outcome_approved=False, county_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        original_candidate_csv_geometry_and_private_survey_reductions_reused_not_repeated=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-alaska-native-contest-headers.csv": csv_bytes(headers),
        "complete-alaska-native-reporting-units.json.gz": observations_raw,
        "complete-alaska-native-model-comparison.csv": csv_bytes([dict(
            state_code="AK", year=2026, native_federal_ballots_b=ballots, native_registered_parent_v=registered,
            native_candidate_selections_t_not_ballots=parent["t"], native_updated=state["updated"], native_timezone=None,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            native_minus_conditional_participant_units=str(difference),
            source_population_and_cutoff_match_proved=False, native_rates_available=False,
            map_approved=False, observed_staying_home=None, design_confidence_interval=None)]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, native_control_records=27, conditional_scenarios=16,
                                    native_federal_participation_control_added=1, generic_cast_ballot_controls_added=0,
                                    native_reporting_units=523, native_contest_headers=len(headers),
                                    explicit_native_registered_parent=registered, native_federal_ballots_b=ballots,
                                    native_rates_available=False,
                                    all_fifty_unaffected_states_fifteen_frames_and_twenty_six_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "alaska-complete-native-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("alaska_state_control.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_alaska_state_control.py"] = Path(__file__).parents[1].joinpath("tests/test_alaska_state_control.py").read_bytes()
    files["README.txt"] = (
        "Alaska native federal b215906 ballots/v605433 registered; t213009 candidate selections are NOT ballots.\n"
        "Native p403 expected/r400 reported are counts, not percentages; uncertified, timezone undeclared.\n"
        "Export format2024 is not the election year: native identity is Alaska2026General.\n"
        "Federal-overseas130ballots/822registered explain governor header scope; no blending/allocation.\n"
        "All523 reporting-unit bytes/402geographic/120pooled/1federal and every original quality hold preserved.\n"
        "Conditional register units assume unvalidated Civic-to-register exchangeability; contrast is not validation/stayinghome.\n"
        "Includes full version10 baseline/native inputs and unchanged maintained Washington shared helpers.\n"
        "python3 -m unittest discover -s tests -p test_alaska_state_control.py\n"
        "python3 -m scripts.alaska_state_control --inputs inputs --output reproduced\n").encode()
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
