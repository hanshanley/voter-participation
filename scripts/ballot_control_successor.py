"""Refresh an existing ballot-only reference without changing registered-frame models."""

import argparse
import copy
import csv
import gzip
import io
import json
from pathlib import Path
import zipfile

from scripts.native_products import query
from scripts.native_tabular import values
from scripts.registered_control_successor import TABLES, csv_bytes, encoded, integer, packet, pin


def native_facts(source, review):
    if set(review["native_queries"]) != {"state", "county", "unit", "contest"} or not review["state_total_selector"]:
        raise ValueError("Explicit separate native state/county/unit and contest query roles are required")
    members = review["source_members"]
    facts = json.loads(gzip.decompress(source[members["facts"]]))
    recipe = json.loads(source[members["recipe"]])
    if (facts["contract"] != "participation.native_factual_tables.v1"
            or recipe["contract"] != "participation.native_product_recipe.v1"
            or facts["source"]["id"] != review["source_id"]
            or facts["source"]["state_code"] != review["state_code"]
            or facts["source"]["election_year"] != review["year"]):
        raise ValueError("Native factual source, jurisdiction or election changed")
    sources = [p for p in recipe["products"] if p["id"] == review["source_id"]]
    if len(sources) != 1 or any(facts["source"][key] != sources[0][key] for key in (
            "id", "url", "pin", "native_updated_at", "retrieved_at_utc")):
        raise ValueError("Complete native facts and query recipe disagree")
    queries = {}
    for role, identifier in review["native_queries"].items():
        definitions = [q for q in recipe["queries"] if q["id"] == identifier]
        if len(definitions) != 1 or definitions[0]["product"] != review["source_id"]:
            raise ValueError("Native query role is absent or ambiguous")
        definition = definitions[0]
        queries[role] = query(facts, definition)
        if role != "contest":
            column = definition["fields"][review["count_field"]]
            tables = [t for t in facts["tables"] if t.get("workbook") == definition.get("workbook")
                      and (not definition.get("tables") or t["name"] in definition["tables"])]
            guards = {(int(row), columns[column]) for peer in recipe["queries"]
                      if peer["product"] == review["source_id"]
                      and peer.get("workbook") == definition.get("workbook")
                      and peer.get("fields", {}).get(review["count_field"]) == column
                      for row, columns in peer.get("require", {}).items()
                      if column in columns and columns[column] == review["native_measure_literal"]}
            guards = sorted(guards)
            if (review["count_field"] not in queries[role]["count_fields"] or len(guards) != 1
                    or not tables or any(values(t, guards[0][0]).get(column) != guards[0][1] for t in tables)):
                raise ValueError("Native ballot count needs its literal guarded statistical column")
    total_rows = [r for r in queries["state"]["rows"] if all(
        r[k] == v for k, v in review["state_total_selector"].items())]
    if len(total_rows) != 1:
        raise ValueError("One separate native state control is required")
    total = integer(total_rows[0][review["count_field"]])
    county_field, unit_field = review["county_field"], review["unit_field"]
    state_counties = {r[county_field]: r[review["count_field"]] for r in queries["state"]["rows"]
                      if r is not total_rows[0]}
    counties = {r[county_field]: r[review["count_field"]] for r in queries["county"]["rows"]}
    units = queries["unit"]["rows"]
    if (len(state_counties) != review["expected_counties"]
            or len(state_counties) != len(queries["state"]["rows"]) - 1
            or len(counties) != len(queries["county"]["rows"]) or counties != state_counties
            or len(units) != review["expected_units"]
            or len({(r[county_field], r[unit_field]) for r in units}) != len(units)
            or {r[county_field] for r in units} != set(counties)
            or sum(counties.values()) != total):
        raise ValueError("Complete native county/unit inventory or state sum changed")
    if any(sum(r[review["count_field"]] for r in units if r[county_field] == county) != count
           for county, count in counties.items()):
        raise ValueError("Native unit sums differ from separate county ballot controls")
    contest = [r for r in queries["contest"]["rows"] if all(
        r[k] == v for k, v in review["state_total_selector"].items())]
    roles = review["choice_fields"] + review["nonchoice_fields"]
    if (not review["choice_fields"] or not review["nonchoice_fields"]
            or len(contest) != 1 or len(roles) != len(set(roles))
            or set(roles) != set(queries["contest"]["count_fields"])
            or sum(integer(contest[0][k]) for k in roles) != total):
        raise ValueError("Native valid-choice/over/under accounting differs from separate ballots")
    choice_count = sum(integer(contest[0][k]) for k in review["choice_fields"])
    code = review["state_code"]
    def runtime(prefix):
        index = json.loads(source[prefix + "/index.json"])
        state = json.loads(gzip.decompress(source[prefix + "/" + index["states"][code]["file"]]))
        ids = set(state["views"]["official"]["counties"])
        rows = [r for r in state["records"] if r["id"] in ids]
        if len(rows) != len(ids) or len({r["geography"]["name"] for r in rows}) != len(rows):
            raise ValueError("Complete current county runtime identity changed")
        return {r["geography"]["name"]: r["count"]["value"] for r in rows}
    old_runtime = runtime(members["old_count_root"])
    current_runtime = runtime(members["new_count_root"])
    if current_runtime != counties or set(old_runtime) != set(counties):
        raise ValueError("Verified common count runtime differs from original native controls")
    native_index = json.loads(source[members["new_native_root"] + "/index.json"])
    native = json.loads(gzip.decompress(source[members["new_native_root"] + "/"
        + native_index["reporting_tables"][code]["file"]]))
    current_units = {(r["properties"]["county"], r["properties"]["source_precinct_label"]):
                     r["properties"]["ballots"] for r in native["records"]}
    if (len(current_units) != len(native["records"]) or current_units != {
            (r[county_field], r[unit_field]): r[review["count_field"]] for r in units}):
        raise ValueError("Current reporting-unit runtime differs from complete native counts")
    return dict(total=total, previous_runtime_total=sum(old_runtime.values()),
                valid_choice_context=choice_count, native_source=facts["source"],
                counties=counties, queries=queries, native_current_units=current_units)


def revise(tables, facts, review):
    states, controls, scenarios = copy.deepcopy(tables)
    if ([len(rows) for rows in tables] != review["expected_table_rows"]
            or len({r["state_code"] for r in states}) != len(states)
            or {r["state_code"] for r in states} != set(review["expected_states"])):
        raise ValueError("Complete state/control/scenario inventory changed")
    code, identifier = review["state_code"], review["control_id"]
    selected_states = [r for r in states if r["state_code"] == code]
    selected_controls = [r for r in controls if r["id"] == identifier and r["state_code"] == code]
    if len(selected_states) != 1 or len(selected_controls) != 1:
        raise ValueError("Exactly one existing state and ballot reference are required")
    state, control = selected_states[0], selected_controls[0]
    if (state["control_id"] != identifier or control["selected_state_reference"] != "True"
            or any(r["control_id"] == identifier for r in scenarios)
            or any(r["year"] != str(review["year"]) for r in (state, control))
            or state["control_measure"] != "reported_cast_ballots" or control["measure"] != "reported_cast_ballots"
            or control["geographic_level"] != "state" or state["control_registered_denominator"]
            or control["denominator"] or state["reported_ballots_per_native_registered_denominator_pct"]
            or state["conditional_registered_frame_scenario_available"] != "False"):
        raise ValueError("Only an existing ballot-only reference without a registered scenario may change")
    previous = integer(control["numerator"])
    if (integer(state["control_native_numerator"]) != previous
            or integer(state["reported_cast_ballots"]) != previous
            or previous != facts["previous_runtime_total"]):
        raise ValueError("Prior model reference and complete old county counter disagree")
    if previous == facts["total"] and integer(state["house_candidate_vote_sum_context"]) == facts["valid_choice_context"]:
        raise ValueError("No changed native count/context; reuse the current complete analysis")
    source = facts["native_source"]
    if source["native_updated_at"] is not None:
        raise ValueError("A newly supplied native clock requires an explicit reviewed clock contract")
    clock = "Native workbook result clock/timezone not supplied; acquisition time is separate"
    old_state, old_control = copy.deepcopy(state), copy.deepcopy(control)
    state.update(control_native_numerator=str(facts["total"]), reported_cast_ballots=str(facts["total"]),
                 house_candidate_vote_sum_context=str(facts["valid_choice_context"]),
                 control_native_time=clock, control_source_url=source["url"])
    control.update(numerator=str(facts["total"]), native_measure=review["native_measure_literal"],
                   source_time_label=clock, source_family=source["url"], source_url=source["url"],
                   source_kind="reviewed_native_ballot_controls_and_reporting_units",
                   native_status="official_workbook_filename_not_independent_final_counting_certification",
                   scope_notes=review["scope_review"])
    if scenarios != tables[2]:
        raise ValueError("A registered source mean, fit or scenario changed")
    if any(a != b for a, b in zip(tables[0], states) if a["state_code"] != code):
        raise ValueError("An unrelated state changed")
    if sum(a != b for a, b in zip(tables[1], controls)) != 1:
        raise ValueError("An unrelated native control changed")
    changes = [dict(state_code=old["state_code"], control_id=old["id"], changed=old != new,
                    previous=old, current=new) for old, new in zip(tables[1], controls)]
    delta = dict(
        state_code=code, control_id=identifier, previous_ballot_reference=previous,
        current_ballot_reference=facts["total"], ballot_reference_difference=facts["total"] - previous,
        previous_valid_choice_context=integer(old_state["house_candidate_vote_sum_context"]),
        current_valid_choice_context=facts["valid_choice_context"],
        valid_choice_context_fields=review["choice_fields"],
        valid_choices_are_not_ballots_or_unique_people=True,
        previous_control=old_control, current_control=control,
        study_fit_weights_source_probability_or_registered_means_changed=False,
        native_outcome_calibration_applied=False, observed_staying_home=False)
    return (states, controls, scenarios), changes, delta


def build(inputs):
    body = (inputs / "reviewed-successor.json").read_bytes()
    review = json.loads(body)
    if set(review) != {
            "contract", "version", "year", "state_code", "control_id", "input_pins", "source_members",
            "source_id", "native_queries", "count_field", "county_field", "unit_field",
            "native_measure_literal", "state_total_selector", "expected_counties", "expected_units",
            "choice_fields", "nonchoice_fields", "expected_states", "expected_table_rows", "scope_review"}:
        raise ValueError("Unreviewed option; metadata cannot supply replacement counts")
    if review["contract"] != "participation.ballot_control_successor.v1" or not review["scope_review"].strip():
        raise ValueError("A reviewed ballot-only source contract is required")
    baseline_body = (inputs / "baseline-complete-analysis.zip").read_bytes()
    source_body = (inputs / "native-batch-complete-analysis.zip").read_bytes()
    baseline = packet(baseline_body, review["input_pins"]["baseline"])
    source = packet(source_body, review["input_pins"]["native_batch"], ("REPRODUCE.txt",))
    if review["version"] != json.loads(baseline["summary.json"])["native_control_version"] + 1:
        raise ValueError("Use the next version of the complete current model ledger")
    facts = native_facts(source, review)
    read = lambda name: list(csv.DictReader(io.StringIO(baseline[name].decode())))
    tables, changes, delta = revise(tuple(read(name) for name in TABLES), facts, review)
    files = {name: value for name, value in baseline.items() if "/" not in name
             and name not in ("checksums.json", "README.txt", "summary.json", "source-qualification.json")}
    files[TABLES[0]], files[TABLES[1]] = csv_bytes(tables[0]), csv_bytes(tables[1])
    files["complete-ballot-control-queries.json.gz"] = gzip.compress(encoded(dict(
        native_source=facts["native_source"], queries=facts["queries"],
        current_counties=facts["counties"], previous_runtime_total=facts["previous_runtime_total"],
        current_state_control=facts["total"], valid_choice_context=facts["valid_choice_context"])), mtime=0)
    files["complete-ballot-control-change-query.json"] = encoded(changes)
    files["ballot-control-change.json"] = encoded(delta)
    summary = dict(
        native_control_version=review["version"], state_and_dc_rows=len(tables[0]),
        source_control_records=len(tables[1]), conditional_scenarios=len(tables[2]),
        changed_state_rows=1, changed_control_rows=1, changed_existing_scenarios=0,
        study_fit_weights_or_probabilities_changed=False,
        new_model_variants_or_scenarios_created=0, native_count_used_for_outcome_fitting=False,
        state_to_county_or_demographic_allocation=False, observed_staying_home=False,
        changed_ballot_reference=delta)
    files["summary.json"] = encoded(summary)
    files["source-qualification.json"] = encoded(dict(
        contract=review["contract"], native_control_version=review["version"],
        native_source=facts["native_source"], explicit_same_measure_review=review["scope_review"],
        current_count_and_reporting_runtimes_verified_against_all_native_controls=True,
        registered_frames_and_all_conditional_scenarios_unchanged=True,
        prior_source_qualification=json.loads(baseline["source-qualification.json"]),
        physical_counter_does_not_establish_unique_people_or_observed_staying_home=True,
        no_new_bridge_or_native_outcome_calibration=True))
    files["inputs/baseline-complete-analysis.zip"] = baseline_body
    files["inputs/native-batch-complete-analysis.zip"] = source_body
    files["inputs/reviewed-successor.json"] = body
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh complete scientific output directory")
    files, summary = build(inputs)
    source = Path(__file__).parent
    for name in ("ballot_control_successor.py", "registered_control_successor.py", "pdf_group_queries.py",
                 "native_reconciliation.py", "native_products.py", "native_tabular.py",
                 "native_pdf.py", "pdf_control_checks.py", "pdf_measure_queries.py"):
        files["scripts/" + name] = (source / name).read_bytes()
    files["tests/test_ballot_control_successor.py"] = source.parent.joinpath(
        "tests/test_ballot_control_successor.py").read_bytes()
    files["README.txt"] = (
        "Existing ballot-only reference successor; no new registered scenario or survey fit.\n"
        "Includes the entire previous model and complete coherent count/reporting batch,\n"
        "all current state/control/scenario queries, complete native controls and change queries.\n"
        "The valid-choice context includes source-unassigned write-ins and excludes over/under;\n"
        "its scope change is not participation or switching. Missing registrations remain absent.\n"
        "Official workbook filename is not independent final-counting or population certification.\n"
        "Fresh extraction, standard library only, no network or dependencies:\n"
        "  python3 -S -m unittest discover -s tests -p test_ballot_control_successor.py\n"
        "  python3 -S -m scripts.ballot_control_successor --inputs inputs --output /new/replay\n"
        "Compare every complete numerical output and the entire ZIP, not just summary.\n"
    ).encode()
    files["checksums.json"] = encoded({name: pin(value) for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.inputs, args.output), indent=2, sort_keys=True))
