"""Use Utah's dated active-registration parent without replacing election-time denominators."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .washington_register_control import civic_source, count, csv_bytes, encoded


BASELINE_SHA = "828409e756b42800f3278a0313268384ceb8b63e56437e19702f2892e8f7a4c8"
NATIVE_SHA = "6ef44592932d54e75f6a668ffa7ae2e3a2720992e3a982804d927106ccc64761"
CONTROL = "ut-2026-held-20261102-native-active-registration-parent"
MEASURE = "native_dated_active_registration_snapshot_not_election_time_denominator"
BASIS = "native_2026_11_02_Total_active_parent_not_election_time_register"
URL = "https://vote.utah.gov/wp-content/uploads/2026/11/11.02.2026-Active-Voters-by-County-and-Party.pdf"


def active_frame(registration, state_rows):
    if registration["source_date_literal"] != "11/02/2026":
        raise ValueError("Changed native registration snapshot date")
    parents = [row for row in registration["native_state_party_rows"] if row["party_literal"] == "Total"]
    csv_parents = [row for row in state_rows if row["party_literal"] == "Total"]
    if len(parents) != 1 or len(csv_parents) != 1:
        raise ValueError("Missing or duplicate native Total parent; no marginal fallback")
    parent, csv_parent = parents[0], csv_parents[0]
    for field in ("active", "inactive", "total"):
        if count(parent.get(field)) != count(int(csv_parent[field])):
            raise ValueError("Native parent and complete state accounting query disagree")
    if parent["active"] <= 0:
        raise ValueError("Missing positive native active-registration parent")
    return parent


def build(inputs):
    baseline = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native = (inputs / "utah-complete-native-numerical-query.zip").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != BASELINE_SHA or hashlib.sha256(native).hexdigest() != NATIVE_SHA:
        raise ValueError("Changed accepted complete baseline or pinned sufficient numerical input")
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        qualification = json.loads(archive.read("source-qualification.json"))
        audit = json.loads(archive.read("audit.json"))
        state_raw = archive.read("state-party-registrations.csv")
        county_raw = archive.read("county-party-registrations.csv")
        participation_raw = archive.read("county-participation.csv")
    registration = qualification["registration_review"]
    state_rows = list(csv.DictReader(io.StringIO(state_raw.decode())))
    parent = active_frame(registration, state_rows)
    if (qualification["election_date_literal"] != "2026-11-03"
            or registration["denominator_substitution_for_separate_native_snapshots_approved"] is not False
            or registration["complete_independent_extractions_match"] is not True
            or registration["discrepancies_not_corrected_or_allocated"] is not True
            or registration["absent_county_party_rows_not_invented"] is not True
            or parent["active"] != audit["source_counts"]["active_registrations"]
            or registration["native_parent_arithmetic_discrepancies"] != audit["native_parent_arithmetic_discrepancies"]
            or audit["source_counts"]["county_scope_withholds"] != 6
            or audit["source_counts"]["counties_missing_a_declared_report"] != 4):
        raise ValueError("Changed completed native registration or county scope qualification")
    with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
        read = lambda name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        states, controls, scenarios = (read(name) for name in (
            "complete-state-control-query.csv", "complete-native-control-dispositions.csv",
            "complete-conditional-registered-scenarios.csv"))
    if (len(states), len(controls), len(scenarios)) != (51, 28, 17):
        raise ValueError("Changed complete version12 coverage")
    target = next(row for row in states if row["state_code"] == "UT")
    if target["control_id"] or target["conditional_registered_frame_scenario_available"] != "False":
        raise ValueError("Do not duplicate an existing Utah frame")
    source = next(row for row in civic_source(baseline)["participation"] if row["scope"] == "UT" and row["dimension"] == "overall")
    active = parent["active"]
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (Decimal(source[key]) for key in ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight or min(voter, nonvoter) < 0 or str(source["n"]) != target["civic_source_n"]:
            raise ValueError("Changed full public Civic state denominator")
        modeled, nonmodeled = active * (voter / weight), active * (nonvoter / weight)
        if abs(modeled + nonmodeled - active) > Decimal("1e-60"):
            raise ValueError("Conditional dated-active partition failed")
    time = "Native registration date 11/02/2026; timezone/time-of-day absent; not an election-time denominator"
    target.update(control_id=CONTROL, control_measure=MEASURE, control_native_numerator=None,
                  control_registered_denominator=active, control_denominator_basis=BASIS,
                  control_native_time=time, control_source_url=URL, conditional_registered_frame_scenario_available="True")
    control = dict(controls[0])
    control.update(id=CONTROL, state_code="UT", year=2026, geographic_level="state", geography="Utah dated active-registration snapshot",
                   source_family=URL, measure=MEASURE, native_measure="Native Total active dated 11/02/2026; no election-time denominator or ballot reference",
                   numerator=None, denominator=active, denominator_basis=BASIS,
                   denominator_label="Native dated Total active parent, excluding inactive; not corrected combined total or county-report substitute",
                   source_time_label=time, source_url=URL, native_status="Dated registration snapshot; not election counting/certification",
                   source_kind="reviewed_public_dated_active_registration_snapshot",
                   scope_notes="Native active+inactive/combined total discrepancy retained. Party affiliation is registration accounting, not votes. County report denominators and missing/held counting scopes unchanged.",
                   selected_state_reference=False, disposition="dated_active_register_frame_no_election_time_population_or_native_ballot_reference")
    controls.append(control)
    scenario = dict(scenarios[0])
    scenario.update(year=2026, state_code="UT", control_id=CONTROL, control_measure=MEASURE,
                    control_native_status=control["native_status"], native_registered_denominator=active,
                    native_denominator_basis=BASIS, source_time_label=time, source_url=URL, civic_source_n=source["n"],
                    civic_weight=source["weight"], civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(modeled), conditional_modeled_nonvoter_count=str(nonmodeled),
                    reported_cast_ballot_measure_control=None, reported_cast_minus_conditional_modeled_voter_count=None,
                    assumption="native 11/02/2026 active-registration snapshot is exchangeable with source-weighted statewide survey propensity; not an election-time population",
                    scenario_units="dated_2026_11_02_native_active_registration_units_not_election_time_population")
    scenarios.append(scenario)
    new_qualification = dict(
        year=2026, registration_source_date=registration["source_date_literal"],
        registration_source_timezone=registration["source_timezone_literal"], native_active_registered_parent=active,
        native_inactive_parent=parent["inactive"], native_combined_total_parent=parent["total"],
        native_active_plus_inactive_minus_combined_total=active + parent["inactive"] - parent["total"],
        native_parent_arithmetic_discrepancies=registration["native_parent_arithmetic_discrepancies"],
        native_totals_not_repaired=True, parent_not_derived_from_county_or_party_sums=True,
        registered_status_literal="active", election_time_denominator_qualified=False,
        separate_county_report_denominators_not_substituted=True,
        source_affiliation_is_registration_accounting_not_party_votes=True,
        source_party_counts_not_used_to_infer_choice=True,
        original_state_county_affiliation_and_county_participation_bytes_preserved=True,
        prior_county_scope_audit=audit, prior_backend_zero_fields_unqualified=qualification["unqualified_backend_fields"],
        selected_native_statewide_ballot_reference=None, native_minus_model=None,
        survey_population_transport_validated=False, derived_state_frame_rate_approved=False,
        maps_approved=False, counting_completion_approved=False, certification_approved=False,
        generic_cast_ballot_measure_approved=False, county_or_demographic_survey_allocation=False,
        observed_staying_home=None, demographic_population=None, design_confidence_interval=None,
        complete_permitted_numerical_inputs_no_raw_operational_or_personal_worksheets=True,
        original_pdf_ocr_workbook_and_private_survey_reductions_reused_not_repeated=True)
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(controls),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "complete-utah-native-state-registration-accounting.csv": state_raw,
        "complete-utah-native-county-affiliation-accounting.csv": county_raw,
        "complete-utah-prior-county-participation.csv": participation_raw,
        "complete-utah-dated-active-frame.csv": csv_bytes([dict(
            state_code="UT", year=2026, native_source_date=registration["source_date_literal"],
            native_active_registered_parent=active, native_inactive_parent=parent["inactive"],
            native_combined_total_parent=parent["total"], election_time_denominator_qualified=False,
            conditional_modeled_participant_units=str(modeled), conditional_modeled_nonparticipant_units=str(nonmodeled),
            selected_native_statewide_ballots=None, native_minus_model=None, rate_approved=False,
            map_approved=False, observed_staying_home=None)]),
        "source-qualification.json": encoded(new_qualification),
        "summary.json": encoded(dict(state_and_dc_rows=51, source_control_records=29, conditional_scenarios=18,
                                    dated_active_registration_frame_added=1, native_statewide_ballot_controls_added=0,
                                    native_state_affiliation_rows=10, native_county_affiliation_rows=228,
                                    prior_county_participation_rows=29, native_dated_active_parent=active,
                                    election_time_denominator_qualified=False,
                                    all_fifty_unaffected_states_seventeen_frames_and_twenty_eight_controls_preserved=True,
                                    no_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    for name in ("baseline-complete-analysis.zip", "utah-complete-native-numerical-query.zip", "native-publication-reference.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("utah_dated_register.py", "washington_register_control.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    files["tests/test_utah_dated_register.py"] = Path(__file__).parents[1].joinpath("tests/test_utah_dated_register.py").read_bytes()
    files["README.txt"] = (
        "Utah native Total ACTIVE1784255 dated11/02/2026; not an election-time denominator or ballot reference.\n"
        "Nativeinactive314971/combinedtotal2099225 discrepancy1 retained, not repaired or reclassified.\n"
        "All10state/228county affiliationrows are registration accounting, NOT party votes or group turnout.\n"
        "All29county participationrows and sixholds/fourmissing reports/oldDavis/Wayne/zero-placeholder holds preserved.\n"
        "Dated PDF never replaces county-report denominators; no native statewide ballots/residual/rate/map approval.\n"
        "Conditional dated-active units assume unvalidated Civic exchangeability; no observed staying-home claim.\n"
        "Includes complete permitted numerical native inputs/version12baseline/code/tests, not private operational worksheets.\n"
        "python3 -m unittest discover -s tests -p test_utah_dated_register.py\n"
        "python3 -m scripts.utah_dated_register --inputs inputs --output reproduced\n").encode()
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
