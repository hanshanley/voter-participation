"""Derive a complete-county registration frame without inventing a native state field."""

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


BASELINE_SHA = "807201daef6a86bffd42f76d90ba5fff8c76a7b273bd6fff2d6bf8e0184e0ae4"
NATIVE_SHA = "e925f182618c1b9c6195ce1f204479df38270ad7145a37868a6f5fb6876439a8"
CONTROL = "sd-2026-derived-complete-county-registration-frame"
MEASURE = "derived_complete_66_county_registered_Voters_sum_not_native_state_field"
BASIS = "derived_sum_all_66_native_county_Voters_parents_counted_once"
URL = "https://electionresults.sd.gov/VoterTurnoutDetails.aspx?map=TURN"


def aggregate_frame(api, facts):
    if facts["year"] != 2026 or facts["election"] != "General Election November 3, 2026":
        raise ValueError("Changed native election identity")
    parents, counties = api["d"], facts["counties"]
    catalog = {row["code"]: row for row in counties}
    if len(parents) != 66 or len(counties) != 66 or len(catalog) != 66:
        raise ValueError("Incomplete source county coverage")
    seen, registered, numerator, rows = set(), 0, 0, []
    for row in parents:
        key = row["CountyID"]
        if key in seen or key not in catalog:
            raise ValueError("Duplicate or unknown source county parent")
        seen.add(key)
        county = catalog[key]
        expected = county["county"] + (" (Vote Center)" if county["vote_center"] else "")
        if (" ".join(row["CountyName"].split()) != expected
                or " ".join(county["raw_county"].split()) != expected):
            raise ValueError("Native county identity mismatch")
        value = count(row.get("Voters"))
        if value <= 0:
            raise ValueError("Missing positive county registration parent; no leaf fallback")
        registered += value
        numerator += count(row.get("calcVoterTurnout"))
        rows.append(dict(row, source_vote_center=county["vote_center"],
                         county_id_not_fips=True, survey_allocated_to_county=False))
    if seen != set(catalog):
        raise ValueError("Incomplete source county coverage")
    return registered, numerator, rows


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "south-dakota-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or pinned native input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        receipts = json.loads(archive.read("sources.json"))
        sources = {}
        for name in ("county-turnout-api.json", "turnout-facts.json"):
            body = gzip.decompress(archive.read("originals/" + name + ".gz"))
            if hashlib.sha256(body).hexdigest() != receipts[name]["sha256"]:
                raise ValueError("Changed native county or factual source original")
            sources[name] = json.loads(body)
        audit = json.loads(archive.read("audit.json"))
        observations_raw = archive.read("participation.json.gz")
    registered, numerator, parents = aggregate_frame(sources["county-turnout-api.json"], sources["turnout-facts.json"])
    if (audit["counties"] != 66 or audit["registrations"] != registered or audit["ballots"] != numerator
            or audit["reporting_units"] != 671 or audit["rates_available"] != 596 or audit["rates_withheld"] != 75):
        raise ValueError("Changed completed county accounting or existing rate decisions")
    for row in parents:
        reviewed = audit["reconciliation"][row["CountyID"]]
        if reviewed["registrations"] != row["Voters"] or reviewed["ballots"] != row["calcVoterTurnout"]:
            raise ValueError("Changed cached native county parent")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 27, 16):
        raise ValueError("Changed complete version11 coverage")
    target = next(row for row in states if row["state_code"] == "SD")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing South Dakota frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "SD" and row["dimension"] == "overall")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = registered * (voter / weight), registered * (nonvoter / weight)
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional registration partition failed")
    time = "Native CurrentDateTime retained per county; update-clock meaning/timezone unqualified"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="SD", year=2026, geographic_level="derived_state_from_complete_source_counties",
                   geography="South Dakota complete 66-county registration aggregate",
                   source_family=URL, measure=MEASURE, native_measure="Derived sum of 66 native county Voters parents; no native statewide field",
                   numerator=None, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Each source county Voters counted once; not repeated vote-center or precinct registrations",
                   source_time_label=time, source_url=URL, native_status="County reported flags retained; certification/completion unqualified",
                   source_kind="derived_complete_source_county_registration_aggregate",
                   scope_notes="Derived, not a native statewide parent. County calcVoterTurnout sum diagnostic only; CurrentDateTime is not a qualified update clock. Prior 596 available/75 held unit rates unchanged.",
                   selected_state_reference=False, disposition="derived_county_register_frame_no_native_statewide_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="SD", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="complete 66-county registration sum is exchangeable with source-weighted statewide survey propensity; derived, not a native statewide field",
                    scenario_units="derived_sum_county_registered_denominator_units_not_administratively_observed_people")
    scenarios.append(scenario)
    qualification = dict(
        year=2026, source_election=sources["turnout-facts.json"]["election"],
        derived_complete_county_registered_frame=registered,
        derived_county_calcVoterTurnout_sum_not_native_statewide_result=numerator,
        native_statewide_parent_present=False, selected_native_statewide_ballot_reference=None, native_minus_model=None,
        native_county_ids_not_fips=True, all_66_source_counties_present_once=True,
        vote_center_count=sum(row["source_vote_center"] for row in parents),
        repeated_vote_center_or_precinct_registrations_not_summed=True,
        native_clock_field="CurrentDateTime", native_update_clock_semantics_qualified=False,
        native_update_clock=None, native_timezone=None, counting_completion_approved=False, certification_approved=False,
        native_register_definition=BASIS, registered_active_inactive_definition=None,
        legacy_denominator_column_does_not_make_aggregate_a_native_state_field=True,
        survey_population_transport_validated=False, original_671_reporting_unit_gzip_bytes_preserved=True,
        prior_reporting_unit_rates_available=596, prior_reporting_unit_rates_withheld=75,
        prior_source_reconciliation_holds=audit["reconciliation"],
        derived_state_frame_rate_approved=False, maps_approved=False, generic_cast_ballot_measure_approved=False,
        county_or_demographic_survey_allocation=False, observed_staying_home=None,
        demographic_population=None, design_confidence_interval=None,
        original_candidate_workbook_html_and_private_survey_reductions_reused_not_repeated=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-south-dakota-native-county-parents.csv": csv_bytes(parents),
        "complete-south-dakota-prior-reporting-units.json.gz": observations_raw,
        "complete-south-dakota-derived-frame.csv": csv_bytes([dict(
            state_code="SD", year=2026, derived_county_registered_frame=registered,
            derived_county_calcVoterTurnout_sum=numerator, is_native_statewide_field=False,
            selected_native_statewide_ballots=None,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            native_minus_model=None, rate_approved=False, map_approved=False, observed_staying_home=None)]),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=28, conditional_scenarios=17,
                                    derived_complete_county_registration_frame_added=1, native_statewide_ballot_controls_added=0,
                                    native_county_parents=66, prior_reporting_unit_rows=671,
                                    derived_registered_frame=registered, is_native_statewide_field=False,
                                    all_fifty_unaffected_states_sixteen_frames_and_twenty_seven_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "south-dakota-complete-native-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("south_dakota_county_frame.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_south_dakota_county_frame.py"] = Path(__file__).parents[1].joinpath("tests/test_south_dakota_county_frame.py").read_bytes()
    files["README.txt"] = (
        "South Dakota DERIVED complete66-county registration frame628563; NOT a native statewide parent.\n"
        "Each county Voters counted once; repeated vote-center/precinct registrations never summed.\n"
        "County calcVoterTurnout sum310298 is diagnostic only; native statewide ballots/residual remainNULL.\n"
        "CurrentDateTime clock meaning/timezone unqualified; native reported flags do not certify completed counting.\n"
        "All671 prior reporting-unit gzipbytes and596available/75held rate decisions preserved.\n"
        "Conditional register units assume unvalidated county-frame/Civic exchangeability; no observed staying-home claim.\n"
        "Includes full version11 baseline/native inputs and unchanged maintained Washington shared helpers.\n"
        "python3 -m unittest discover -s tests -p test_south_dakota_county_frame.py\n"
        "python3 -m scripts.south_dakota_county_frame --inputs inputs --output reproduced\n").encode()
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
