"""Refresh a reported-ballot reference while holding its registered model fixed."""

import argparse
import copy
import csv
from decimal import Decimal, localcontext
import gzip
import io
import json
from pathlib import Path
import re
import zipfile

from scripts.participation_intake.adapters import field, verify_native_reproduction
from scripts.participation_intake.contract import STATES
from scripts.registered_control_successor import FLAGS, TABLES, csv_bytes, encoded, integer, number, packet, pin


def canonical_id_list(values, label):
    if (not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values)
            or values != sorted(values) or len(values) != len(set(values))):
        raise ValueError(f"{label} must be a unique canonical identity list")
    return values


def retained_control_reviews(review):
    values = review.get("retained_historical_same_source_controls", [])
    if not isinstance(values, list):
        raise ValueError("Retained same-source controls need accepted baseline row pins")
    identities = []
    for item in values:
        metadata = item.get("accepted_baseline_row_pin") if isinstance(item, dict) else None
        if (not isinstance(item, dict)
                or set(item) != {"id", "accepted_baseline_row_pin"}
                or not isinstance(item["id"], str) or not item["id"]
                or not isinstance(metadata, dict)
                or set(metadata) != {"bytes", "sha256"}
                or type(metadata["bytes"]) is not int
                or metadata["bytes"] <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", metadata["sha256"])):
            raise ValueError("Retained same-source controls need complete accepted baseline row pins")
        identities.append(item["id"])
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("Retained same-source control reviews must be unique and canonical")
    return values


def group_controls(queries, declaration, state_code, counties):
    state_query, county_query = (queries[declaration[key]] for key in ("state_query", "county_query"))
    count_field, county_field = declaration["count_field"], declaration["county_field"]
    keys, dimensions = declaration["joint_fields"], declaration["dimensions"]
    state_rows, county_rows = state_query["rows"], county_query["rows"]
    if (state_query["count_fields"] != [count_field] or county_query["count_fields"] != [count_field]
            or len(keys) != len(set(keys)) or not dimensions
            or set(row[county_field] for row in county_rows) != set(counties)):
        raise ValueError("Complete paired native group/count roles and county identities are required")
    expected = {tuple(row[key] for key in keys): integer(row[count_field]) for row in state_rows}
    if len(expected) != len(state_rows):
        raise ValueError("Duplicate native state group key")
    actual, seen = dict.fromkeys(expected, 0), set()
    for row in county_rows:
        key = tuple(row[name] for name in keys)
        identity = (row[county_field], key)
        if key not in actual or identity in seen:
            raise ValueError("Native county group inventory differs")
        seen.add(identity)
        actual[key] += integer(row[count_field])
    if actual != expected or len(seen) != len(counties) * len(expected):
        raise ValueError("Every native state/county aggregate cell must reconcile, including zeros")
    projected = {}
    for scope, rows in (("state", state_rows), ("county", county_rows)):
        for row in rows:
            county = "STATEWIDE" if scope == "state" else row[county_field]
            method = row[declaration["method_field"]]
            for dimension, group in [("overall", "All"), *[
                    (name, row[field]) for name, field in dimensions.items()]]:
                key = (scope, county, method, dimension, group)
                projected[key] = projected.get(key, 0) + integer(row[count_field])
    rows = [dict(state_code=state_code, geographic_level=scope, geography=county,
        native_method=method, native_dimension=dimension, native_group=group,
        reported_source_ballots=count, demographic_registered_denominator="",
        full_demographic_turnout_qualified=False, observed_staying_home=False,
        deduplicated_or_added_to_enr=False)
        for (scope, county, method, dimension, group), count in sorted(projected.items())]
    return rows, dict(native_state_joint_cells=len(state_rows),
        native_county_joint_cells=len(county_rows), complete_counties=len(counties),
        every_joint_cell_matches=True, source_record_count_repairs=0,
        projected_native_group_rows=len(rows), full_group_turnout_or_allmode_alignment_qualified=False)


def native_facts(source, review):
    registry = json.loads(source["originals/registry.json"])
    entries = [entry for entry in registry["sources"] if entry["id"] == review["source_entry"]]
    if len(entries) != 1 or entries[0].get("target", "counts") != "counts":
        raise ValueError("One complete reviewed native count source is required")
    entry, prefix = entries[0], "originals/supplied/" + review["source_entry"] + "/"
    spec = entry["spec"]
    if (spec["classification"] != "public_aggregate"
            or spec["geography"]["state_code"] != review["state_code"]
            or spec["election"]["year"] != review["year"]):
        raise ValueError("Native source jurisdiction, year or public-aggregate role changed")
    inputs = {name: source[prefix + name] for name in spec["inputs"]}
    verify_native_reproduction(spec, inputs)
    preparation = json.loads(inputs["preparation-review"])
    if (preparation["state_code"] != review["state_code"] or preparation["year"] != review["year"]
            or preparation["contract"] != "participation.native_count_refresh.v1"
            or preparation["refresh_current_reporting"] is not True):
        raise ValueError("A coherent county and current-state reference refresh is required")
    recipe = json.loads(inputs["recipe"])
    queries_body = inputs["controls"]
    queries = json.loads(gzip.decompress(queries_body))["queries"]
    state_query, county_query = (queries[preparation[key]] for key in ("state_query", "county_query"))
    if len(state_query["rows"]) != 1:
        raise ValueError("Exactly one separately reported native state control is required")
    state = state_query["rows"][0]
    roles = {role: preparation[role + "_field"] for role in (
        "count", "denominator", "reported_units", "total_units", "clock", "published_pct")}
    sources = [product for product in recipe["products"] if product["id"] == preparation["source_id"]]
    if len(sources) != 1:
        raise ValueError("Native source identity is absent or ambiguous")
    native_source = sources[0]
    for role in ("count", "denominator", "reported_units", "total_units"):
        if (roles[role] not in state_query["count_fields"] or roles[role] not in county_query["count_fields"]
                or sum(integer(row[roles[role]]) for row in county_query["rows"]) != integer(state[roles[role]])):
            raise ValueError("Separate native state and county statistical controls disagree")
    identities = preparation["identity_fields"]
    native = {tuple(row[key] for key in identities): row for row in county_query["rows"]}
    if len(native) != len(county_query["rows"]):
        raise ValueError("Duplicate native county identity")

    def runtime(root):
        index = json.loads(source[root + "/index.json"])
        data = json.loads(gzip.decompress(source[root + "/" + index["states"][review["state_code"]]["file"]]))
        ids = set(data["views"]["official"]["counties"])
        rows = [row for row in data["records"] if row["id"] in ids]
        keys = [tuple(field(row, path) for path in identities.values()) for row in rows]
        if len(set(keys)) != len(keys) or len(rows) != len(ids):
            raise ValueError("Complete county runtime identity changed")
        return dict(zip(keys, rows)), index

    previous, _ = runtime("originals/baseline")
    current, index = runtime("queries/counts")
    if set(current) != set(native) or set(previous) != set(native):
        raise ValueError("Full current/previous county inventories differ from native identities")
    for key, row in current.items():
        if (row["count"]["value"] != native[key][roles["count"]]
                or row["denominator"]["value"] != native[key][roles["denominator"]]):
            raise ValueError("Current county runtime differs from original native count/registration fields")
    current_snapshot = json.loads(gzip.decompress(source[
        "queries/counts/" + index["current_snapshot"]["file"]]))
    current_states = [row for row in current_snapshot["snapshot"]["reporting"]
        if row["state_code"] == review["state_code"] and row["source_url"] == native_source["url"]]
    if (len(current_states) != 1 or current_states[0]["ballots"] != state[roles["count"]]
            or current_states[0]["denominator"] != state[roles["denominator"]]
            or current_states[0]["source_update_label"] != state[roles["clock"]]):
        raise ValueError("Current state and county runtimes were not coherently refreshed")
    names = {row["geography"]["name"] for row in current.values()}
    groups, accounting = group_controls(queries, review["group_queries"], review["state_code"], names)
    return dict(total=integer(state[roles["count"]]), registered=integer(state[roles["denominator"]]),
        clock=state[roles["clock"]], source_url=native_source["url"], native_source=native_source,
        previous_county_runtime_total=sum(row["count"]["value"] for row in previous.values()),
        current_county_runtime_total=sum(row["count"]["value"] for row in current.values()),
        reported_units=state[roles["reported_units"]], total_units=state[roles["total_units"]],
        native_queries_body=queries_body, group_rows=groups, group_accounting=accounting)


def revise(tables, facts, review):
    states, controls, scenarios = copy.deepcopy(tables)
    if ([len(rows) for rows in tables] != review["expected_table_rows"]
            or {row["state_code"] for row in states} != set(review["expected_states"])):
        raise ValueError("Full accepted model state/control/scenario inventory changed")
    code, identifier = review["state_code"], review["control_id"]
    selections = ([row for row in states if row["state_code"] == code],
        [row for row in controls if row["state_code"] == code and row["id"] == identifier],
        [row for row in scenarios if row["state_code"] == code and row["control_id"] == identifier])
    if any(len(rows) != 1 for rows in selections):
        raise ValueError("One existing selected registered reference and scenario are required")
    state, control, scenario = (rows[0] for rows in selections)
    if (state["control_id"] != identifier or control["selected_state_reference"] != "True"
            or control["geographic_level"] != "state"
            or any(row["year"] != str(review["year"]) for row in (state, control, scenario))
            or any(value != "reported_cast_ballots" for value in (
                state["control_measure"], control["measure"], scenario["control_measure"]))
            or any(scenario[key] != "False" for key in FLAGS)
            or state["control_source_url"] != facts["source_url"] or control["source_url"] != facts["source_url"]):
        raise ValueError("The accepted reported-ballot registered reference identity or qualifications changed")
    registered, previous = integer(control["denominator"]), integer(control["numerator"])
    if integer(facts["total"]) > registered:
        raise ValueError("Native reported count exceeds the unchanged registered source stock")
    if (registered != facts["registered"] or registered <= 0
            or any(integer(value) != registered for value in (
                state["control_registered_denominator"], scenario["native_registered_denominator"]))
            or any(integer(value) != previous for value in (
                state["control_native_numerator"], state["reported_cast_ballots"],
                scenario["reported_cast_ballot_measure_control"]))
            or state["civic_source_n"] != scenario["civic_source_n"]
            or state["control_denominator_basis"] != control["denominator_basis"]
            or scenario["native_denominator_basis"] != control["denominator_basis"]):
        raise ValueError("Changed registered stock or inconsistent accepted native/model reference")
    if previous == facts["total"] and control["source_time_label"] == facts["clock"]:
        raise ValueError("No changed native reference; reuse the accepted analysis")
    old_state, old_control, old_scenario = map(copy.deepcopy, (state, control, scenario))
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (number(scenario[key]) for key in
            ("civic_weight", "civic_modeled_voter_weight", "civic_modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight:
            raise ValueError("Accepted study weight partition changed")
        for expected, key in ((registered * voter / weight, "conditional_modeled_voter_count"),
                (registered * nonvoter / weight, "conditional_modeled_nonvoter_count")):
            if abs(expected - number(scenario[key])) > Decimal("1e-60"):
                raise ValueError("Accepted conditional source means no longer reproduce from unchanged weights")
        ratio = str(Decimal(100 * facts["total"]) / registered)
        gap = str(Decimal(facts["total"]) - number(scenario["conditional_modeled_voter_count"]))
    clock = facts["clock"]
    if not isinstance(clock, str) or not clock:
        raise ValueError("This operation requires an explicitly supplied native result literal")
    status = "Unofficial native reporting; source units reported, not final-counting certification"
    state.update(control_native_numerator=str(facts["total"]), reported_cast_ballots=str(facts["total"]),
        reported_ballots_per_native_registered_denominator_pct=ratio, control_native_time=clock)
    control.update(numerator=str(facts["total"]), source_time_label=clock,
        native_measure="Reviewed native reported-ballot statistical field",
        native_status=status, source_kind="reviewed_native_record_reference", scope_notes=review["scope_review"])
    scenario.update(source_time_label=clock, control_native_status=status,
        reported_cast_ballot_measure_control=str(facts["total"]),
        reported_cast_minus_conditional_modeled_voter_count=gap)
    historical_controls = canonical_id_list(
        review["historical_same_source_controls"], "Historical same-source controls")
    retained_historical = retained_control_reviews(review)
    if set(historical_controls) & {item["id"] for item in retained_historical}:
        raise ValueError("Current duplicate and already-retained historical reviews overlap")
    for identity in historical_controls:
        rows = [row for row in controls if row["id"] == identity and row["state_code"] == code]
        if (len(rows) != 1 or rows[0]["selected_state_reference"] != "False"
                or rows[0]["source_url"] != facts["source_url"] or integer(rows[0]["numerator"]) != previous
                or integer(rows[0]["denominator"]) != registered
                or rows[0]["disposition"] != "same_source_same_counts_duplicate_not_added"):
            raise ValueError("Historical same-source duplicate identity changed")
        rows[0].update(disposition="retained_older_same_source_snapshot_not_current_duplicate",
            scope_notes="Dated earlier source counts retained; not a duplicate of the newer selected reference or independent current validation.")
    for retained in retained_historical:
        rows = [row for row in controls
                if row["id"] == retained["id"] and row["state_code"] == code]
        if (len(rows) != 1
                or pin(encoded(rows[0])) != retained["accepted_baseline_row_pin"]
                or rows[0]["selected_state_reference"] != "False"
                or rows[0]["measure"] != "reported_cast_ballots"
                or rows[0]["year"] != str(review["year"])
                or rows[0]["state_code"] != code
                or rows[0]["source_url"] != facts["source_url"]
                or integer(rows[0]["denominator"]) != registered
                or not rows[0]["source_time_label"]
                or rows[0]["disposition"] != "retained_older_same_source_snapshot_not_current_duplicate"):
            raise ValueError("Retained same-source historical reference identity changed")
    if any(a != b for a, b in zip(tables[0], states) if a["state_code"] != code):
        raise ValueError("An unrelated state changed")
    allowed = {"source_time_label", "control_native_status", "reported_cast_ballot_measure_control",
        "reported_cast_minus_conditional_modeled_voter_count"}
    for before, after in zip(tables[2], scenarios):
        if any(before[key] != after[key] for key in before if key not in allowed
                or before["control_id"] != identifier):
            raise ValueError("A conditional mean, registered frame, source weight or unrelated scenario changed")
    expected_changes = {identifier, *historical_controls}
    if {a["id"] for a, b in zip(tables[1], controls) if a != b} != expected_changes:
        raise ValueError("Unexpected native control changes")
    changes = [dict(control_id=old["id"], state_code=old["state_code"], changed=old != new,
        previous=old, current=new) for old, new in zip(tables[1], controls)]
    delta = dict(state_code=code, control_id=identifier, previous_selected_reference=previous,
        current_selected_reference=facts["total"], selected_reference_difference=facts["total"] - previous,
        previous_county_runtime_total=facts["previous_county_runtime_total"],
        current_county_runtime_total=facts["current_county_runtime_total"],
        old_county_and_model_snapshots_are_distinct=True, registered_source_units=registered,
        registered_denominator_changed=False, all_conditional_source_means_and_weights_unchanged=True,
        current_reported_minus_modeled_nominal_not_validated_error=gap,
        previous_state=old_state, previous_control=old_control, previous_scenario=old_scenario,
        observed_staying_home=False, native_outcome_calibration_applied=False,
        demographic_or_local_model_allocation_applied=False, house_endpoints_or_family_outputs_changed=False)
    if retained_historical:
        delta["retained_historical_same_source_controls"] = [
            item["id"] for item in retained_historical]
    return (states, controls, scenarios), changes, delta


def build(inputs):
    review_body = (inputs / "reviewed-successor.json").read_bytes()
    review = json.loads(review_body)
    required = {"contract", "version", "year", "state_code", "control_id", "source_entry",
        "expected_states", "expected_table_rows", "input_pins", "historical_same_source_controls",
        "group_queries", "scope_review"}
    optional = {"retained_historical_same_source_controls"}
    retained = retained_control_reviews(review)
    historical = canonical_id_list(
        review.get("historical_same_source_controls"), "Historical same-source controls")
    if (not required <= set(review) or set(review) - required - optional
            or set(historical) & {item["id"] for item in retained}
            or review["contract"] != "participation.reported_registered_reference.v1"
            or not review["scope_review"].strip() or set(review["expected_states"]) != set(STATES)):
        raise ValueError("An explicit complete reported-registered reference review is required")
    baseline_body = (inputs / "baseline-complete-analysis.zip").read_bytes()
    source_body = (inputs / "native-batch-complete-analysis.zip").read_bytes()
    baseline = packet(baseline_body, review["input_pins"]["baseline"])
    source = packet(source_body, review["input_pins"]["native_batch"], ("REPRODUCE.txt",))
    if review["version"] != json.loads(baseline["summary.json"])["native_control_version"] + 1:
        raise ValueError("Use the next version of the complete current model")
    facts = native_facts(source, review)
    read = lambda name: list(csv.DictReader(io.StringIO(baseline[name].decode())))
    tables, changes, delta = revise(tuple(read(name) for name in TABLES), facts, review)
    files = {name: body for name, body in baseline.items() if "/" not in name
        and name not in ("checksums.json", "README.txt", "summary.json", "source-qualification.json")}
    for name, rows in zip(TABLES, tables):
        files[name] = csv_bytes(rows)
    files["complete-reported-registered-reference-change-query.json"] = encoded(changes)
    files["reported-registered-reference-change.json"] = encoded(delta)
    files["complete-native-participation-group-controls.csv"] = csv_bytes(facts["group_rows"])
    files["complete-current-native-source-queries.json.gz"] = facts["native_queries_body"]
    files["native-participation-source-accounting.json"] = encoded(dict(
        native_source=facts["native_source"], paired_group_accounting=facts["group_accounting"],
        reported_ballots=facts["total"], registered_source_units=facts["registered"],
        source_result_clock_literal=facts["clock"], source_timezone=None,
        native_reported_units=facts["reported_units"], native_total_units=facts["total_units"],
        source_result_and_group_file_cutoffs_not_assumed_aligned=True,
        native_group_counts_added_to_reporting_or_used_for_full_turnout=False))
    summary = dict(native_control_version=review["version"], state_and_dc_rows=len(tables[0]),
        source_control_records=len(tables[1]), conditional_scenarios=len(tables[2]),
        changed_state_rows=1, changed_control_rows=1 + len(review["historical_same_source_controls"]),
        changed_existing_scenario_bookkeeping=1, changed_conditional_source_means=0,
        study_fit_weights_or_probabilities_changed=False, new_model_variants_or_scenarios_created=0,
        native_count_used_for_outcome_fitting=False, state_to_county_or_demographic_allocation=False,
        observed_staying_home=False, changed_registered_reference=delta)
    files["summary.json"] = encoded(summary)
    qualification = dict(contract=review["contract"],
        native_control_version=review["version"], explicit_same_source_review=review["scope_review"],
        unchanged_registered_stock_source_weights_and_conditional_means=True,
        source_early_group_counts_are_separate_native_observations_not_full_demographic_turnout=True,
        cross_feed_modes_and_clocks_not_deduplicated_or_assumed_aligned=True,
        historical_duplicate_retained_with_older_scope=True, no_native_outcome_or_causal_calibration=True,
        prior_source_qualification=json.loads(baseline["source-qualification.json"]))
    if retained:
        qualification["retained_historical_same_source_controls"] = retained
    files["source-qualification.json"] = encoded(qualification)
    files["inputs/baseline-complete-analysis.zip"] = baseline_body
    files["inputs/native-batch-complete-analysis.zip"] = source_body
    files["inputs/reviewed-successor.json"] = review_body
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh scientific output directory")
    files, summary = build(inputs)
    source = Path(__file__).parent
    for name in ("reported_registered_reference.py", "registered_control_successor.py",
            "pdf_group_queries.py", "native_reconciliation.py", "native_products.py", "native_tabular.py",
            "native_pdf.py", "pdf_control_checks.py", "pdf_measure_queries.py"):
        files["scripts/" + name] = (source / name).read_bytes()
    for path in sorted((source / "participation_intake").glob("*.py")):
        files["scripts/participation_intake/" + path.name] = path.read_bytes()
    files["tests/test_reported_registered_reference.py"] = source.parent.joinpath(
        "tests/test_reported_registered_reference.py").read_bytes()
    files["README.txt"] = (
        "Existing reported-ballot registered-reference successor; no new model or fitted probabilities.\n"
        "Complete prior model, coherent all-jurisdiction count batch, permitted native originals,\n"
        "all current state/control/scenario queries, every native group cell and projection are included.\n"
        "Registration stocks, source weights and all conditional means remain unchanged.\n"
        "Partial source-mode group counts are not all-mode demographic turnout or observed staying home.\n"
        "Fresh extraction, standard library only, no networking:\n"
        "  python3 -S -m unittest discover -s tests -p test_reported_registered_reference.py\n"
        "  python3 -S -m scripts.reported_registered_reference --inputs inputs --output /new/replay\n"
        "Compare every complete numerical output and the entire ZIP.\n"
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
