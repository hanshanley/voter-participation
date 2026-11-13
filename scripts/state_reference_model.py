"""Revise an existing state reported-count/register reference without refitting priors."""

import argparse
import copy
import csv
from decimal import Decimal, localcontext
import gzip
import io
import json
from pathlib import Path
import zipfile

from scripts.participation_intake.adapters import verify_fact_bindings
from scripts.participation_intake.contract import STATES, validate_all
from scripts.registered_control_successor import (
    FLAGS, TABLES, csv_bytes, encoded, integer, number, packet, pin,
)
from scripts.state_reporting_successor import facts as state_facts


def native_facts(source, review):
    registry = json.loads(source["originals/registry.json"])
    entries = [item for item in registry["sources"] if item["id"] == review["source_entry"]]
    if len(entries) != 1 or entries[0].get("target") != "state_reporting":
        raise ValueError("One reviewed state-only reference operation is required")
    entry = entries[0]
    spec = entry["spec"]
    inputs = {name: source["originals/supplied/" + entry["id"] + "/" + name]
              for name in spec["inputs"]}
    if any(pin(body) != spec["inputs"][name]["pin"] for name, body in inputs.items()):
        raise ValueError("A complete selected factual input changed")
    rows = json.loads(inputs[spec["primary_input"]])
    if len(rows) != 1:
        raise ValueError("An explicit native statewide statistic, not a county subtotal, is required")
    validate_all(rows)
    verify_fact_bindings(spec, rows, inputs)
    selected, values, binding = state_facts(rows[0], spec)
    if (spec["classification"] != "public_aggregate"
            or selected["source"]["state_code"] != review["state_code"]
            or selected["source"]["election_year"] != review["year"]):
        raise ValueError("Native factual state/election scope changed")
    runtime = []
    for root in ("originals/baseline", "queries/counts"):
        index = json.loads(source[root + "/index.json"])
        snapshot = json.loads(gzip.decompress(source[root + "/" + index["current_snapshot"]["file"]]))
        matches = [item for item in snapshot["snapshot"]["reporting"]
                   if item["state_code"] == review["state_code"]
                   and item["source_url"] == selected["source"]["url"]]
        if len(matches) != 1:
            raise ValueError("Exactly one original/current same-source state reference is required")
        runtime.append(matches[0])
    previous, current = runtime
    if (any(previous[key] != binding["previous_reference"][key]
            for key in ("ballots", "denominator", "source_update_label"))
            or current["ballots"] != values["count"]
            or current["denominator"] != values["denominator"]
            or current["source_update_label"] != values["clock"]
            or current["source_sha256"] != selected["source"]["pin"]["sha256"]):
        raise ValueError("Actual previous/current runtime does not match the reviewed native source")
    return dict(numerator=values["count"], denominator=values["denominator"],
        source_url=selected["source"]["url"], source_time_label=values["clock"],
        native_measure=selected["fields"][selected["recipe"]["roles"]["count"]]["native_label"],
        denominator_label=selected["fields"][selected["recipe"]["roles"]["denominator"]]["native_label"],
        native_source=selected["source"], complete_selected_statistics=selected,
        native_status=binding["source_status_literal"],
        previous_runtime_ballots=previous["ballots"], previous_runtime_registered=previous["denominator"])


def revise(tables, native, review):
    current = copy.deepcopy(tables)
    states, controls, scenarios = current
    if ([len(rows) for rows in tables] != review["expected_table_rows"]
            or len({row["state_code"] for row in states}) != len(states)
            or {row["state_code"] for row in states} != set(review["expected_states"])
            or not review["registered_frame_review"].strip()):
        raise ValueError("The complete accepted model and an explicit registration-stock review are required")
    code, identifier = review["state_code"], review["control_id"]
    selections = (
        [row for row in states if row["state_code"] == code],
        [row for row in controls if row["state_code"] == code and row["id"] == identifier],
        [row for row in scenarios if row["state_code"] == code and row["control_id"] == identifier])
    if any(len(rows) != 1 for rows in selections):
        raise ValueError("One existing selected state/control/registered scenario is required")
    state, control, scenario = (rows[0] for rows in selections)
    previous_scenario = copy.deepcopy(scenario)
    previous = review["previous_model_reference"]
    if (set(previous) != {"ballots", "registered", "clock", "denominator_basis"}
            or state["control_id"] != identifier or control["selected_state_reference"] != "True"
            or control["geographic_level"] != "state"
            or any(row["year"] != str(review["year"]) for row in (state, control, scenario))
            or any(value != "reported_cast_ballots" for value in (
                state["control_measure"], control["measure"], scenario["control_measure"]))
            or any(value != native["source_url"] for value in (
                state["control_source_url"], control["source_url"], scenario["source_url"]))
            or any(value != previous["clock"] for value in (
                state["control_native_time"], control["source_time_label"], scenario["source_time_label"]))
            or any(value != previous["denominator_basis"] for value in (
                state["control_denominator_basis"], control["denominator_basis"], scenario["native_denominator_basis"]))
            or any(integer(value) != previous["ballots"] for value in (
                state["control_native_numerator"], state["reported_cast_ballots"], control["numerator"],
                scenario["reported_cast_ballot_measure_control"]))
            or any(integer(value) != previous["registered"] for value in (
                state["control_registered_denominator"], control["denominator"], scenario["native_registered_denominator"]))
            or state["civic_source_n"] != scenario["civic_source_n"]
            or any(scenario[key] != "False" for key in FLAGS)):
        raise ValueError("Accepted model preimage, source measure, registration basis or qualification changed")
    count, registered = native["numerator"], native["denominator"]
    if (type(count) is not int or type(registered) is not int or registered <= 0
            or not 0 <= count <= registered or not native["source_time_label"]):
        raise ValueError("Separately reported native counted and registered statistics are required")
    if (count, registered, native["source_time_label"]) == (
            previous["ballots"], previous["registered"], previous["clock"]):
        raise ValueError("No changed native reference; reuse the accepted analysis")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (number(scenario[key]) for key in (
            "civic_weight", "civic_modeled_voter_weight", "civic_modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight:
            raise ValueError("Accepted source weights do not form the unchanged full partition")
        old_v, old_n = (previous["registered"] * part / weight for part in (voter, nonvoter))
        if any(abs(actual - number(scenario[key])) > Decimal("1e-60") for actual, key in (
                (old_v, "conditional_modeled_voter_count"), (old_n, "conditional_modeled_nonvoter_count"))):
            raise ValueError("Accepted conditional means no longer reproduce from their source weights")
        new_v, new_n = (registered * part / weight for part in (voter, nonvoter))
        if abs(new_v + new_n - registered) > Decimal("1e-60"):
            raise ValueError("Updated registered source-unit partition does not reconcile")
        ratio, gap = str(Decimal(100 * count) / registered), str(Decimal(count) - new_v)
        delta = dict(
            state_code=code, control_id=identifier, previous_model_reference=previous,
            current_native_count=count, current_registered=registered,
            model_reference_count_difference=count-previous["ballots"],
            model_registered_difference=registered-previous["registered"],
            runtime_reference_count_difference=count-native["previous_runtime_ballots"],
            runtime_registered_difference=registered-native["previous_runtime_registered"],
            previous_conditional_voter_units=str(old_v), current_conditional_voter_units=str(new_v),
            previous_conditional_nonvoter_units=str(old_n), current_conditional_nonvoter_units=str(new_n),
            conditional_voter_unit_difference=str(new_v-old_v),
            conditional_nonvoter_unit_difference=str(new_n-old_n),
            native_minus_model_nominal_not_validated_error=gap,
            source_weights_probabilities_and_fits_unchanged=True, outcome_calibration_applied=False,
            observed_staying_home=False, independent_population_validation=False,
            death_migration_eligibility_components=None, local_or_demographic_allocation_applied=False)
    state.update(control_native_numerator=str(count), control_registered_denominator=str(registered),
        control_native_time=native["source_time_label"], reported_cast_ballots=str(count),
        reported_ballots_per_native_registered_denominator_pct=ratio)
    control.update(numerator=str(count), denominator=str(registered),
        source_time_label=native["source_time_label"], native_measure=native["native_measure"],
        denominator_label=native["denominator_label"], native_status=native["native_status"],
        source_kind="reviewed_selected_native_state_statistics", scope_notes=review["registered_frame_review"])
    scenario.update(native_registered_denominator=str(registered),
        source_time_label=native["source_time_label"], control_native_status=native["native_status"],
        conditional_modeled_voter_count=str(new_v), conditional_modeled_nonvoter_count=str(new_n),
        reported_cast_ballot_measure_control=str(count),
        reported_cast_minus_conditional_modeled_voter_count=gap)
    for before_rows, after_rows, selected in zip(tables, current, (state, control, scenario)):
        if any(old != new for old, new in zip(before_rows, after_rows) if new is not selected):
            raise ValueError("An unrelated state, monthly frame, held context or scenario changed")
    if any(scenario[key] != previous_scenario[key] for key in FLAGS):
        raise ValueError("Behavioral qualification changed")
    changes = [dict(state_code=old["state_code"], control_id=old["id"],
                    changed=old != new, previous=old, current=new)
               for old, new in zip(tables[1], controls)]
    return current, delta, changes


def build(inputs):
    review_body = (inputs / "reviewed-successor.json").read_bytes()
    review = json.loads(review_body)
    if (set(review) != {"contract", "version", "year", "state_code", "control_id", "source_entry",
            "expected_states", "expected_table_rows", "input_pins", "previous_model_reference",
            "registered_frame_review"}
            or review["contract"] != "participation.state_reference_model.v1"
            or set(review["expected_states"]) != set(STATES)):
        raise ValueError("A complete state-only registered-reference model review is required")
    baseline_body = (inputs / "baseline-complete-analysis.zip").read_bytes()
    source_body = (inputs / "native-batch-complete-analysis.zip").read_bytes()
    baseline = packet(baseline_body, review["input_pins"]["baseline"])
    source = packet(source_body, review["input_pins"]["native_batch"], ("REPRODUCE.txt",))
    if review["version"] != json.loads(baseline["summary.json"])["native_control_version"] + 1:
        raise ValueError("Use the next version of the complete current model")
    native = native_facts(source, review)
    tables = tuple(list(csv.DictReader(io.StringIO(baseline[name].decode()))) for name in TABLES)
    tables, delta, changes = revise(tables, native, review)
    files = {name: body for name, body in baseline.items() if "/" not in name
             and name not in ("checksums.json", "README.txt", "summary.json", "source-qualification.json")}
    files.update({name: csv_bytes(rows) for name, rows in zip(TABLES, tables)})
    files["complete-state-reference-change-query.json"] = encoded(changes)
    files["state-reference-change.json"] = encoded(delta)
    files["complete-selected-native-state-statistics.json"] = encoded(native["complete_selected_statistics"])
    summary = dict(native_control_version=review["version"], state_and_dc_rows=len(tables[0]),
        source_control_records=len(tables[1]), conditional_scenarios=len(tables[2]),
        changed_state_rows=1, changed_control_rows=1, changed_existing_scenarios=1,
        new_model_variants_or_scenarios_created=0, study_fit_weights_or_probabilities_changed=False,
        native_count_used_for_outcome_fitting=False, observed_staying_home=False,
        state_to_county_or_demographic_allocation=False, changed_registered_reference=delta)
    files["summary.json"] = encoded(summary)
    files["source-qualification.json"] = encoded(dict(
        contract=review["contract"], native_control_version=review["version"],
        explicit_registered_frame_review=review["registered_frame_review"],
        complete_public_selected_facts_replayed=True, excluded_publisher_html_extraction_replayed=False,
        original_population_weight_target_and_cutoff_qualification_not_lifted=True,
        source_weights_probabilities_and_fits_unchanged=True,
        native_register_units_not_observed_voter_or_nonvoter_people=True,
        separate_monthly_registration_and_formal_analysis_warning_context_preserved=True,
        prior_source_qualification=json.loads(baseline["source-qualification.json"])))
    files["inputs/baseline-complete-analysis.zip"] = baseline_body
    files["inputs/native-batch-complete-analysis.zip"] = source_body
    files["inputs/reviewed-successor.json"] = review_body
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh complete scientific output directory")
    files, summary = build(inputs)
    source = Path(__file__).parent
    for name in ("state_reference_model.py", "state_reporting_successor.py", "html_statistics.py",
            "registered_control_successor.py", "pdf_group_queries.py", "native_reconciliation.py",
            "native_products.py", "native_tabular.py", "native_pdf.py",
            "pdf_control_checks.py", "pdf_measure_queries.py"):
        files["scripts/" + name] = (source / name).read_bytes()
    for path in (source / "participation_intake").glob("*.py"):
        files["scripts/participation_intake/" + path.name] = path.read_bytes()
    files["tests/test_state_reference_model.py"] = (
        source.parent / "tests/test_state_reference_model.py").read_bytes()
    files["README.txt"] = (
        "Existing state-only counted/reference and reviewed registered-stock successor.\n"
        "Complete prior all-state model, complete count batch, selected native numerical facts,\n"
        "full query sets and exact maintained code/tests remain included. No raw respondents,\n"
        "new fit, outcome-derived probability, local allocation or observed staying-home claim.\n"
        "The pinned original publisher HTML is held privately. Public replay validates every\n"
        "selected factual literal/provenance/recipe and numerical transform, not extraction of\n"
        "the excluded publisher application. Opaque native backend fields remain unqualified.\n"
        "From a fresh extraction, using only the Python standard library offline:\n"
        "  python3 -S -m unittest discover -s tests -p test_state_reference_model.py\n"
        "  python3 -S -m scripts.state_reference_model --inputs inputs --output /new/replay\n"
        "Compare every complete output and the entire deterministic ZIP byte-for-byte.\n"
        "Registration cutoff/status/survey transport remain unvalidated; modeled complements\n"
        "are source units, not administrative staying home, migration or eligibility counts.\n"
    ).encode()
    files["checksums.json"] = encoded({name: pin(body) for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.inputs, args.output), indent=2, sort_keys=True))
