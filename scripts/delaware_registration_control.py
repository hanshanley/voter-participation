"""Integrate a held source-defined statewide register frame, not certified turnout."""

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


BASELINE_SHA = "80b13e010d99fb607922039af8b74480aeb7fe166de1a4dbdc0d16fb629ed0c2"
NATIVE_SHA = "521c0849acedf949e7e31bd75ab5053d91630b2ec55118e03cd42275e82c9cd0"
CONTROL = "de-2026-held-state-and-house-district-turnout"
URL = "https://elections.delaware.gov/results/enr/GE2026.html?group=state"
MEASURE = "native_source_Ballots_Cast_missing_clock_and_completion"
BASIS = "native_Reg_Voters_same_report_definition_unqualified"
TIME = "Native turnout clock/timezone not supplied; candidate clock is separate and not substituted"
FIELDS = {"Election Id", "Election Name", "Results Type", "Representative District",
          "Ballots Cast", "Reg Voters", "Percentage"}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return target.getvalue().encode()


def integer(value):
    if type(value) is int and value >= 0:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d{0,2}(?:,\d{3})*)", value):
        raise ValueError("Invalid literal native count")
    return int(value.replace(",", ""))


def native_frame(source, native):
    if source["election_id"] != "GE2026" or source["election_date"] != "2026-11-03":
        raise ValueError("Different source election")
    if any(source[key] is not None for key in ("native_turnout_update_clock", "native_turnout_timezone", "native_fips")):
        raise ValueError("Missing native turnout clock, timezone or FIPS cannot be invented")
    if any(source[key] is not False for key in ("analysis_rate_approved", "maps_approved", "all_mode_complete", "certified")):
        raise ValueError("Do not promote native rate, map, completion or certification approvals")
    expected = {"ALL"} | {f"{index:02}" for index in range(1, 42)}
    if len(native) != 42 or {row["Representative District"] for row in native} != expected:
        raise ValueError("Incomplete or duplicate native state/district query")
    rows = []
    with localcontext() as context:
        context.prec = 80
        for row in native:
            if (set(row) != FIELDS or row["Election Id"] != "GE2026"
                    or row["Election Name"] != "2026 General Election" or row["Results Type"] != "UNOFFICIAL RESULTS"):
                raise ValueError("Changed native schema, election or status")
            cast, registered = integer(row["Ballots Cast"]), integer(row["Reg Voters"])
            if registered <= 0 or cast > registered:
                raise ValueError("Invalid source-defined registered fraction")
            if (100 * Decimal(cast) / registered).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(str(row["Percentage"])):
                raise ValueError("Native printed registered fraction does not reconcile")
            rows.append(dict(
                year=2026, state_code="DE", native_representative_district=row["Representative District"],
                geography_level="state" if row["Representative District"] == "ALL" else "representative_district",
                native_participants=cast, native_registered=registered, native_printed_percent=str(row["Percentage"]),
                native_numerator_literal="Ballots Cast", native_denominator_literal="Reg Voters",
                native_status=row["Results Type"], source_clock=None, source_timezone=None, native_fips=None,
                native_analysis_rate_approved=False, map_approved=False, all_mode_complete=False,
                certified=False, generic_cast_ballot_measure_approved=False, county_or_demographic_allocation=False))
    state = next(row for row in rows if row["native_representative_district"] == "ALL")
    districts = [row for row in rows if row is not state]
    if any(sum(row[key] for row in districts) != state[key] for key in ("native_participants", "native_registered")):
        raise ValueError("District accounting disagrees with separate statewide total")
    return state, rows


def public_civic(baseline):
    for _ in range(3):
        with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
            if "inputs/civic-selected-aggregates.json" in archive.namelist():
                return json.loads(archive.read("inputs/civic-selected-aggregates.json"))
            baseline = archive.read("inputs/baseline-complete-analysis.zip")
    raise ValueError("Complete sufficient Civic baseline missing")


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    original = (inputs / "delaware-complete-native-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(original).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed complete accepted baseline or immutable native input")
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        checksums = json.loads(archive.read("checksums.json"))["files"]
        for record in checksums:
            body = archive.read(record["path"])
            if len(body) != record["bytes"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
                raise ValueError("Changed sufficient native source member")
        source = json.loads(archive.read("source-qualification.json"))
        raw = json.loads(archive.read("native-turnout.json"))
        audit = json.loads(archive.read("audit.json"))
    if (audit["all_41_district_ballot_and_registration_sums_equal_separate_statewide_totals"] is not True
            or audit["candidate_clock_not_substituted_for_turnout"] is not True):
        raise ValueError("Changed reused native verification")
    state, native = native_frame(source, raw)
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if len(states) != 51 or len(controls) != 21 or len(scenarios) != 10:
        raise ValueError("Changed complete version05 coverage")
    target = next(row for row in states if row["state_code"] == "DE")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate or replace a Delaware control")
    civic = public_civic(baseline)
    survey = next(row for row in civic["participation"] if row["scope"] == "DE" and row["dimension"] == "overall")
    registered, participants = state["native_registered"], state["native_participants"]
    with localcontext() as context:
        context.prec = 80
        total, voter, nonvoter = (Decimal(survey[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if total <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != total or str(survey["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state group denominator")
        modeled, nonmodeled = registered * (voter / total), registered * (nonvoter / total)
        if abs(modeled + nonmodeled - registered) > Decimal("1e-60"):
            raise ValueError("Conditional source-register partition does not reconcile")
        comparison = dict(
            state_code="DE", year=2026, native_source_participants=participants, native_source_registered=registered,
            native_printed_percent=state["native_printed_percent"], native_measure_literal="Ballots Cast",
            native_denominator_literal="Reg Voters", native_turnout_clock=None, native_timezone=None,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            native_minus_conditional_participant_units=str(Decimal(participants) - modeled),
            native_analysis_rate_approved=False, source_population_and_cutoff_match_proved=False,
            transport_validation=False, design_confidence_interval=None, observed_staying_home=None,
            demographic_population=None, county_or_demographic_allocation=False, map_approved=False)
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=participants,
                  control_registered_denominator=registered, control_denominator_basis=BASIS,
                  control_native_time=TIME, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="DE", year=2026, geographic_level="state", geography="Delaware",
                   source_family=URL, measure=MEASURE, native_measure="Native Ballots Cast; missing turnout clock and completion",
                   numerator=participants, denominator=registered, denominator_basis=BASIS,
                   denominator_label="Native Reg Voters; register status/timing unqualified",
                   source_time_label=TIME, source_url=URL, native_status="UNOFFICIAL RESULTS; certification and all-mode completion unproved",
                   source_kind="reviewed_public_observation", scope_notes="Native ALL and 41 House-district sums reconcile; no county allocation or candidate-clock substitution.",
                   selected_state_reference=True, disposition="selected_state_reference_not_independent_validation")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="DE", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=registered,
                    native_denominator_basis=BASIS, source_time_label=TIME, source_url=URL,
                    civic_source_n=survey["n"], civic_weight=survey["weight"],
                    civic_modeled_voter_weight=survey["modeled_voter_weight"], civic_modeled_nonvoter_weight=survey["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None)
    scenarios.append(scenario)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-delaware-native-state-and-districts.csv": csv_bytes(native),
        "complete-delaware-native-model-comparison.csv": csv_bytes([comparison]),
        "source-qualification.json": encoded(source),
        "summary.json": encoded(dict(
            state_and_dc_rows=51, native_controls=len(controls), conditional_scenarios=len(scenarios),
            native_source_participants=participants, native_source_registered=registered, native_printed_percent=state["native_printed_percent"],
            native_turnout_rows=len(native), native_house_districts=41, native_clock=None, native_timezone=None,
            conditional_model_is_not_administratively_observed_staying_home=True,
            all_50_unaffected_state_rows_ten_prior_scenarios_and_twenty_one_controls_preserved=True,
            no_candidate_clock_substitution_or_county_allocation=True, no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "delaware-complete-native-query.zip", "native-publication-verification.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/delaware_registration_control.py"] = Path(__file__).read_bytes()
    files["tests/test_delaware_registration_control.py"] = Path(__file__).parents[1].joinpath("tests/test_delaware_registration_control.py").read_bytes()
    files["README.txt"] = (
        "Held Delaware source-defined register frame; not certified turnout or observed staying home.\n"
        "Native clock/timezone absent; do not borrow the separate candidate clock.\n"
        "Native rate/map/completion/certification flags remain false; no district allocation to counties.\n"
        "Complete51-state query/22controls/11conditionalframes preserves every prior unaffected output.\n"
        "All complete sufficient originals, earlier baseline, code/tests and queries included.\n"
        "python3 -m unittest discover -s tests -p test_delaware_registration_control.py\n"
        "python3 -m scripts.delaware_registration_control --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
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
