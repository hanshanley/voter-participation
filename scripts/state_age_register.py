"""Conditional age-register source units, not observed group turnout."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .extract_state_age_register import CA_BINS, SC_BINS, cells, matching_bins, register_frames


INPUT_SHA = "05de693ab03287d8e9a03d28d3d070c6d4f11aa49f710fb331454d28c5c05dbe"
GROUPS = ("18_29", "30_49", "50_64", "65_plus", "unknown")
STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def scope_check(scope):
    if (scope["year"] != 2026 or scope["sc_declared_report_label"] != "2026-11-02"
            or any(scope[key] is not None for key in ("sc_embedded_registration_cutoff",
                "sc_embedded_report_clock", "sc_source_timezone", "sc_age_reference_date", "civic_age_reference_date"))
            or scope["source_age_reference_dates_harmonized"] is not False
            or scope["source_population_frame_equivalence_validated"] is not False
            or scope["compatible_boundary_labels_not_population_frame_validation"] is not True
            or scope["all_three_native_gender_cells_required_no_sex_category_crosswalk"] is not True
            or scope["no_age_bin_splitting_or_unknown_complement_recovery"] is not True
            or scope["no_statewide_or_pooled_probability_allocated_to_groups_or_localities"] is not True
            or scope["matching_state_age_group_specific_propensity_not_statewide_propensity"] is not True):
        raise ValueError("Keep unknown clocks, complete gender coverage and unvalidated population transport separate")


def query_rows(snapshot, frames, scope):
    scope_check(scope)
    age_sources = [r for r in snapshot["groups"] if r["dimension"] == "AGE6"]
    sources = {(r["state_code"], r["group"]): r for r in age_sources}
    if len(age_sources) != len(sources) or set(sources) != {(state, group) for state in STATES for group in GROUPS}:
        raise ValueError("Incomplete 255 public state/age source queries")
    native = {r["native_age_label"]: r for r in frames}
    decisions, boundaries = [], []
    for state in STATES:
        for group in GROUPS:
            source = sources[state, group]
            bins = SC_BINS if state == "SC" else CA_BINS if state == "CA" else None
            labels = matching_bins(bins, group) if bins else None
            frame_status = ("no_native_age_register_selected_in_this_package" if bins is None else
                            "unknown_age_not_a_native_register_frame" if group == "unknown" else
                            "whole_native_age_boundaries_compatible" if labels else "incompatible_boundaries_no_splitting")
            total = None
            if state == "SC" and labels:
                values = [native[label]["derived_all_gender_age_register"] for label in labels]
                if all(value is not None for value in values):
                    total = sum(values)
                else:
                    frame_status = "incomplete_native_gender_age_cells_no_partial_frame"
            if bins:
                boundaries.append(dict(state_code=state, civic_age_group=group,
                    native_age_labels=" | ".join(label for label, _, _ in bins),
                    matched_whole_bins=" | ".join(labels) if labels else None,
                    disposition=frame_status, bin_split_or_age_reconstruction=False,
                    boundary_match_not_population_or_age_clock_validation=True))
            supported = source["disposition"] == "selected_broad_source_model"
            weight = voter = nonvoter = modeled = complement = pct = None
            if supported:
                with localcontext() as context:
                    context.prec = 80
                    weight, voter, nonvoter = (Decimal(source[key]) for key in
                                              ("weight", "modeled_voter_weight", "modeled_nonvoter_weight"))
                    if (source["n"] < 100 or min(source["native_model_voter_cases"], source["native_model_nonvoter_cases"]) < 30
                            or source["native_model_voter_cases"] + source["native_model_nonvoter_cases"] != source["n"]
                            or min(weight, voter, nonvoter) <= 0 or voter + nonvoter != weight):
                        raise ValueError("Changed accepted complete public source/model-class support")
                    pct = str(100 * voter / weight)
                    if total is not None:
                        modeled, complement = str(total * voter / weight), str(total * nonvoter / weight)
                        if abs(Decimal(modeled) + Decimal(complement) - total) > Decimal("1e-60"):
                            raise ValueError("Conditional source-register partition failed")
            else:
                if any(source[key] is not None for key in ("n", "weight", "modeled_voter_weight",
                        "modeled_nonvoter_weight", "native_model_voter_cases", "native_model_nonvoter_cases")):
                    raise ValueError("Private held source statistics must remain absent")
            disposition = ("no_dc_source_sample" if state == "DC" else
                           "held_source_support_or_complementary_disclosure" if not supported else
                           "conditional_age_register_transport_unvalidated" if modeled is not None else frame_status)
            decisions.append(dict(year=2026, state_code=state, dimension="AGE6", group=group,
                label=source["label"], source_model_disposition=source["disposition"],
                source_n=source["n"], source_weight=str(weight) if supported else None,
                source_modeled_voter_weight=str(voter) if supported else None,
                source_modeled_nonvoter_weight=str(nonvoter) if supported else None,
                source_modeled_participant_pct=pct, native_frame_disposition=frame_status,
                native_matching_whole_age_bins=" | ".join(labels) if labels else None,
                derived_native_age_register=total, native_age_parent_is_printed=False,
                conditional_participant_source_units=modeled, conditional_nonparticipant_source_units=complement,
                disposition=disposition, registration_report_label="2026-11-02" if state == "SC" else None,
                registration_cutoff_date=None, source_age_reference_dates_harmonized=False,
                source_population_frame_equivalence_validated=False,
                administratively_observed_group_participation=False, observed_staying_home=None,
                native_card_or_ballot_minus_model=None, design_confidence_interval=None,
                population_point_estimate_approved=False, local_probability_allocated=False))
    return decisions, boundaries


def build(inputs):
    raw = (inputs / "complete-age-register-sufficient-inputs.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError("Changed complete qualified sufficient inputs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed sufficient input inventory")
        for name, metadata in sums.items():
            value = archive.read(name)
            if len(value) != metadata["bytes"] or hashlib.sha256(value).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed pinned source bytes")
        with zipfile.ZipFile(io.BytesIO(archive.read("sc-native-inputs.zip"))) as native:
            source = cells(native.read("registration.xlsx"))
            independent = {r["cell"]: {k: r[k] for k in ("kind", "value")} for r in
                           json.loads(native.read("openpyxl-cells.json")) if r["sheet"] == "Sheet1"}
        selected_addresses = ["C1", "B3", "C7", "D58", "H58", "I9", "O9", "U9",
            *[col + "10" for col in ("K", "L", "M", "N", "Q", "R", "S", "T", "X", "Y", "Z", "AA")],
            *[col + "58" for col in ("J", "K", "L", "M", "N", "P", "Q", "R", "S", "T", "W", "X", "Y", "Z", "AA")]]
        if any(source.get(address, dict(kind="blank", value=None)) != independent[address] for address in selected_addresses):
            raise ValueError("Independent native state/header cells disagree")
        parent, original_rows, frames, accounting = register_frames(source)
        ca = cells(archive.read("ca-age.xlsx"))
        if [ca[col + "1"]["value"] for col in "ABCDEFGH"] != [
                "County", "Total Registered", *[label for label, _, _ in CA_BINS]]:
            raise ValueError("Changed California age boundaries; no replacement crosswalk")
        snapshot = json.loads(archive.read("civic-selected-inputs.json"))
        scope = json.loads(archive.read("source-scope.json"))
        decisions, boundaries = query_rows(snapshot, frames, scope)
        preserved = {output: archive.read(name) for output, name in {
            "preserved-2026-state-demographic-query.csv": "preserved-civic-demographic-query.csv",
            "preserved-native28-state-query.csv": "native28-state-query.csv",
            "preserved-native28-control-dispositions.csv": "native28-control-dispositions.csv",
            "preserved-native28-registered-scenarios.csv": "native28-registered-scenarios.csv"}.items()}
    if any(row["complete"] and row["complete_sum_minus_parent"] != 0 for row in accounting):
        raise ValueError("Native parent discrepancy retained; review before selecting a group frame")
    base = list(csv.DictReader(io.StringIO(preserved["preserved-native28-state-query.csv"].decode())))
    sc = next(row for row in base if row["state_code"] == "SC")
    if int(sc["control_registered_denominator"]) != parent:
        raise ValueError("Different accepted native28 South Carolina parent")
    selected = [row for row in decisions if row["conditional_participant_source_units"] is not None]
    if len(selected) != 1 or (selected[0]["state_code"], selected[0]["group"]) != ("SC", "65_plus"):
        raise ValueError("Changed supported target selection; review a new source version")
    public = {(r["state_code"], r["dimension"], r["group"]): r for r in
              csv.DictReader(io.StringIO(preserved["preserved-2026-state-demographic-query.csv"].decode()))}
    for row in decisions:
        old = public[row["state_code"], "AGE6", row["group"]]
        if ((row["source_n"] is not None and str(row["source_n"]) != old["n"])
                or row["source_model_disposition"] != old["disposition"]
                or (row["source_modeled_participant_pct"] or "") != old["modeled_voter_pct"]):
            raise ValueError("Changed accepted public 2026 source model")
    qualification = dict(
        status="conditional_source_age_register_units_not_observed_group_turnout",
        complete_state_age_decisions=255, selected_conditional_age_frames=1, held_decisions=254,
        native_SC_age_cells=12, native_SC_age_stocks=4, boundary_decisions=10,
        native_state_register_parent=parent, selected_SC_65plus_derived_register=selected[0]["derived_native_age_register"],
        state_65plus_cell_derivation=["Sheet1!N58", "Sheet1!T58", "Sheet1!AA58"],
        printed_all_gender_65plus_parent=None, unknown_native_gender_included_count=150,
        registration_report_label="2026-11-02", embedded_registration_cutoff=None,
        embedded_registration_clock=None, timezone=None, age_reference_dates_harmonized=False,
        source_population_frame_exchangeability_validated=False,
        exact_boundary_labels_not_full_construct_or_population_validation=True,
        CA66plus_not_promoted_to65plus=True, no_native_bins_split=True,
        no_held_source_group_or_unknown_cells_recovered=True,
        no_under65_complement_or_statewide_age_standardized_total=True,
        original_native28_and_all1530_public_model_query_bytes_preserved=True,
        no_observed_group_turnout_staying_home_ballot_residual_or_population_CI=True,
        no_new_acquisition_native_survey_campaign_or_website_view=True,
        no_statewide_or_pooled_probability_allocated_to_groups_or_localities=True, maps_approved=False,
        native_source_url=scope["sc_native_source_url"],
        source_csv_sha256=snapshot["original_csv_sha256"], codebook_sha256=snapshot["codebook_sha256"])
    return {**preserved, "complete-state-age-register-query.csv": csv_bytes(decisions),
        "complete-selected-age-register-scenarios.csv": csv_bytes(selected),
        "complete-native-state-age-cells.csv": csv_bytes(original_rows),
        "complete-native-state-age-stocks.csv": csv_bytes(frames),
        "complete-native-age-accounting.csv": csv_bytes(accounting),
        "complete-age-boundary-decisions.csv": csv_bytes(boundaries),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(complete_state_age_decisions=255, selected_scenarios=1,
            held_decisions=254, selected_state="SC", selected_group="65_plus",
            derived_native_65plus_register=selected[0]["derived_native_age_register"],
            civic_source_group_n=selected[0]["source_n"],
            conditional_participant_source_units=selected[0]["conditional_participant_source_units"],
            conditional_nonparticipant_source_units=selected[0]["conditional_nonparticipant_source_units"],
            original_native28_and_all1530_public_model_queries_unchanged=True,
            source_population_frame_exchangeability_validated=False,
            administratively_observed_group_participation=False, new_website_view=False))}


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    name = "complete-age-register-sufficient-inputs.zip"
    files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("state_age_register.py", "extract_state_age_register.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_state_age_register.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "2026 age-register SOURCE UNITS, not observed group turnout or staying home.\n"
        "255 complete state/age decisions; ONE unvalidated SC65+ frame,254holds.\n"
        "Native65-Up stock is DERIVED from Female580268+Male465059+Unknown150=1045477.\n"
        "No printed all-gender age parent. Report labelNov2 is NOTknown cutoff/clock/timezone.\n"
        "Civic65+ n553 uses native model classes518/35 and COMPLETE published source weights.\n"
        "Compatible65+ boundary labels do NOTvalidate age clocks/status/population exchangeability.\n"
        "No CA66+->65+ substitution, bin splitting, unknown recovery or under65 complement.\n"
        "Uses matching STATE/AGE group propensity, NEVER statewide/pooled probability allocated to groups.\n"
        "No county/precinct allocation, observed ballots, fakeCI or new website view.\n"
        "No new acquisition or old native/survey campaign rerun. Native28/all1530 old query bytes preserved.\n"
        "OriginalSCworkbook/independent snapshot/provenance, CAage workbook, fullpublic Civic inputs,\n"
        "accepted query references, source scope, standard-library code/tests and EVERYquery/result included.\n"
        "python3 -m unittest discover -s tests -p test_state_age_register.py\n"
        "python3 -m scripts.state_age_register --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
        for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
