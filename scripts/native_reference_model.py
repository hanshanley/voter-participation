"""Advance one existing source-native model reference without refitting its model."""

import argparse
import copy
import csv
from decimal import Decimal, localcontext
import gzip
import io
import json
from pathlib import Path
import zipfile

from scripts.registered_control_successor import (
    FLAGS, TABLES, csv_bytes, encoded, integer, number, packet, pin,
)


def json_member(body):
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return json.loads(body)


def manifest_packet(body, expected):
    if pin(body) != expected:
        raise ValueError("Changed complete native source packet")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        if (len(names) != len(set(names))
                or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names)
                or "manifest.json" not in names):
            raise ValueError("Unsafe or incomplete native source packet")
        manifest = json.loads(archive.read("manifest.json"))
        members = manifest["members"]
        if set(names) != set(members) | {"manifest.json"}:
            raise ValueError("Native source packet inventory differs from its manifest")
        result = {name: archive.read(name) for name in names}
    if any(pin(result[name]) != metadata for name, metadata in members.items()):
        raise ValueError("Changed native source packet member")
    return result, manifest


def rows(body):
    return list(csv.DictReader(io.StringIO(body.decode())))


def verified_prior_query(inputs, review):
    contract = review["prior_query_contract"]
    query_body = (inputs / contract["query_input"]).read_bytes()
    receipt_body = (inputs / contract["receipt_input"]).read_bytes()
    identity_body = (inputs / contract["identity_input"]).read_bytes()
    if (pin(query_body) != contract["query_pin"]
            or pin(receipt_body) != contract["receipt_pin"]
            or pin(identity_body) != contract["identity_pin"]):
        raise ValueError("Changed complete prior native query or identity source")
    receipt = json.loads(receipt_body)
    if (receipt["contract"] != contract["receipt_contract"]
            or receipt["key"] != contract["key_roles"]
            or receipt["query_rows"] != contract["expected_rows"]
            or receipt["identity_source_ids"] != contract["identity_source_ids"]
            or receipt["runtime_counts_or_registered_used_as_model_values"]):
        raise ValueError("Prior native query binding receipt changed")
    prior = rows(query_body)
    if len(prior) != contract["expected_rows"]:
        raise ValueError("Complete prior native query row count changed")
    canonical_fields = contract["canonical_fields"]
    for row in prior:
        row[canonical_fields["count"]] = integer(row[canonical_fields["count"]])
        row[canonical_fields["registered"]] = integer(row[canonical_fields["registered"]])
    key = lambda row: tuple(row[name] for name in contract["key_roles"])
    if len({key(row) for row in prior}) != len(prior):
        raise ValueError("Complete prior native query keys are duplicated")

    identity_packet = json_member(identity_body)
    identity_records = [
        row for row in identity_packet["records"]
        if row.get("source", {}).get("id") in contract["identity_source_ids"]]
    identity_keys = set()
    for record in identity_records:
        fields = record["source"]["fields"]
        identity_keys.add((
            record["geography"]["level"],
            fields["county_id"],
            fields["county"],
            fields.get("precinct") or fields.get("unit") or "",
        ))
    expected_identity_rows = contract["expected_rows"] - 1
    if len(identity_records) != expected_identity_rows or len(identity_keys) != expected_identity_rows:
        raise ValueError("Held complete prior county/reporting-unit identities changed")
    prior_keys = {key(row) for row in prior}
    if (prior_keys - {tuple(contract["state_identity"])} != identity_keys
            or tuple(contract["state_identity"]) not in prior_keys):
        raise ValueError("Prior native query county IDs do not match held complete identities")

    accepted = review["accepted_outputs"]
    columns = contract["accepted_columns"]
    state_rows = rows((inputs / accepted["state"]).read_bytes())
    county_rows = rows((inputs / accepted["counties"]).read_bytes())
    unit_rows = rows((inputs / accepted["reporting_units"]).read_bytes())
    if len(state_rows) != 1:
        raise ValueError("Accepted prior statewide native output changed")
    prior_by_key = {key(row): row for row in prior}
    state_key = tuple(contract["state_identity"])
    if (integer(state_rows[0][columns["count"]])
            != prior_by_key[state_key][canonical_fields["count"]]
            or integer(state_rows[0][columns["registered"]])
            != prior_by_key[state_key][canonical_fields["registered"]]):
        raise ValueError("Prior statewide query differs from accepted model source output")
    county_ids = {}
    for row in county_rows:
        matches = [
            item for item in prior
            if item[canonical_fields["level"]] == contract["level_roles"]["county"]
            and item[canonical_fields["county"]] == row[columns["county"]]
            and item[canonical_fields["unit"]] == ""]
        if len(matches) != 1:
            raise ValueError("Accepted prior county identity is missing or ambiguous")
        selected = matches[0]
        county_ids[row[columns["county"]]] = selected[canonical_fields["county_id"]]
        if (selected[canonical_fields["count"]] != integer(row[columns["count"]])
                or selected[canonical_fields["registered"]] != integer(row[columns["registered"]])):
            raise ValueError("Prior county query differs from accepted model source output")
    for row in unit_rows:
        selected_key = (
            contract["level_roles"]["reporting_unit"],
            county_ids[row[columns["county"]]],
            row[columns["county"]],
            row[columns["unit"]],
        )
        if selected_key not in prior_by_key:
            raise ValueError("Accepted prior reporting-unit county ID binding is missing")
        selected = prior_by_key[selected_key]
        if (selected[canonical_fields["count"]] != integer(row[columns["count"]])
                or selected[canonical_fields["registered"]] != integer(row[columns["registered"]])):
            raise ValueError("Prior reporting-unit query differs from accepted model source output")
    return prior


def compare_native_queries(prior, current, fields, review):
    contract = review["prior_query_contract"]
    canonical = contract["canonical_fields"]
    converted = []
    for row in current:
        converted.append({
            canonical["level"]: row[fields["geography_level"]],
            canonical["county_id"]: row[fields["county_id"]],
            canonical["county"]: row[fields["county"]],
            canonical["unit"]: row[fields["unit"]],
            canonical["count"]: row[fields["count"]],
            canonical["registered"]: row[fields["registered"]],
        })
    key = lambda row: tuple(row[name] for name in contract["key_roles"])
    before = {key(row): row for row in prior}
    after = {key(row): row for row in converted}
    if len(before) != len(prior) or len(after) != len(converted) or set(before) != set(after):
        raise ValueError("Prior and successor complete native keys differ")
    if any(before[item][canonical["registered"]] != after[item][canonical["registered"]]
           for item in before):
        raise ValueError("A prior/successor registered vector changed")
    changed = [
        item for item in before
        if before[item][canonical["count"]] != after[item][canonical["count"]]]
    levels = contract["level_roles"]
    level_changes = {
        role: [item for item in changed if item[0] == literal]
        for role, literal in levels.items()
    }
    deltas = {
        role: sum(after[item][canonical["count"]] - before[item][canonical["count"]]
                  for item in items)
        for role, items in level_changes.items()
    }
    return {
        "state_code": review["state_code"],
        "same_identities": True,
        "all_complete_keys_exact": True,
        "all_county_ids_exact": True,
        "complete_key_fields": contract["key_roles"],
        "complete_rows_compared": len(before),
        "state_rows": sum(item[0] == levels["state"] for item in before),
        "county_rows": sum(item[0] == levels["county"] for item in before),
        "reporting_unit_rows": sum(item[0] == levels["reporting_unit"] for item in before),
        "all_registered_values_unchanged": True,
        "previous_state_numerator": review["previous_reference"]["numerator"],
        "current_state_numerator": review["current_reference"]["numerator"],
        "state_numerator_difference": deltas["state"],
        "changed_counties": len(level_changes["county"]),
        "county_change_aggregate": deltas["county"],
        "changed_reporting_units": len(level_changes["reporting_unit"]),
        "reporting_unit_change_aggregate": deltas["reporting_unit"],
        "reported_units": review["current_reference"]["reported_units"],
        "total_units": review["current_reference"]["total_units"],
        "partially_reported_units": 0,
    }


def selected_native_facts(source, inputs, review):
    members = review["source_members"]
    facts = json_member(source[members["facts"]])
    recipe = json_member(source[members["recipe"]])
    statistics = json_member(source[members["statistics"]])
    policy = json.loads(source[members["private_original_policy"]])
    reader = json.loads(source[members["reader_contract"]])
    source_summary = json.loads(source[members["source_summary"]])
    integration_result = json.loads(source[members["integration_result"]])
    if (facts["contract"] != "participation.native_factual_tables.v1"
            or facts["source"] != statistics["source"]
            or facts["source"] != statistics["recipe"]["source"]
            or recipe["contract"] != "participation.native_product_recipe.v1"
            or policy["whole_publisher_html_redistributed"]
            or policy["claim_initial_html_parsing_reproduced_without_original"]
            or policy["numerical_input_replaced_by_metadata_only"]
            or reader["private_html_parse_reproduction_claimed"]
            or integration_result["source_requests"] != 0
            or integration_result["publication_attempts"] != 0):
        raise ValueError("Native public-fact, private-original, or offline scope changed")
    query_roles = review["source_query_roles"]
    query_ids = {item["id"] for item in recipe["queries"]}
    reader_queries = reader[query_roles["reader_query_collection"]]
    if (query_roles["complete_query_id"] not in query_ids
            or query_roles["state_query_id"] not in query_ids
            or query_roles["complete_query_id"] not in reader_queries
            or query_roles["state_query_id"] not in reader_queries):
        raise ValueError("Reviewed complete/state native query roles changed")
    source_pin = facts["source"]["pin"]
    if source_pin != review["private_original_pin"]:
        raise ValueError("Private original pin or selected fact lineage changed")
    if source_summary[review["state_code"]]["private_original_pin"] != source_pin:
        raise ValueError("Native source summary no longer agrees with selected facts")
    tables = facts["tables"]
    if len(tables) != 1:
        raise ValueError("Exactly one complete selected native factual table is required")
    table = tables[0]
    fields = review["source_fields"]
    expected_header = [fields[key] for key in (
        "geography_level", "county_id", "county", "unit", "count", "registered",
        "reported_units", "total_units", "printed_pct", "clock")]
    if table["header"] != expected_header:
        raise ValueError("Native factual table header changed")
    parsed = []
    for expected_index, raw in enumerate(table["rows"]):
        if raw["row"] != expected_index or len(raw["values"]) != len(expected_header):
            raise ValueError("Native factual table row address changed")
        row = dict(zip(expected_header, raw["values"]))
        for key in ("count", "registered"):
            row[fields[key]] = integer(row[fields[key]])
        for key in ("reported_units", "total_units"):
            value = row[fields[key]]
            row[fields[key]] = integer(value) if value != "" else None
        parsed.append(row)
    keys = [tuple(row[fields[name]]
                  for name in review["prior_query_contract"]["source_key_roles"])
            for row in parsed]
    if len(keys) != len(set(keys)) or len(parsed) != review["expected_source_rows"]:
        raise ValueError("Native source identities are incomplete or duplicated")
    state_rows = [row for row in parsed if row[fields["geography_level"]] == "state"]
    county_rows = [row for row in parsed if row[fields["geography_level"]] == "county"]
    unit_rows = [row for row in parsed if row[fields["geography_level"]] == "reporting_unit"]
    if [len(state_rows), len(county_rows), len(unit_rows)] != review["expected_source_levels"]:
        raise ValueError("Native state/county/reporting-unit inventory changed")
    state = state_rows[0]
    native = {
        "count": state[fields["count"]],
        "registered": state[fields["registered"]],
        "clock_literal": state[fields["clock"]],
        "reported_units": state[fields["reported_units"]],
        "total_units": state[fields["total_units"]],
        "printed_pct": state[fields["printed_pct"]],
        "source": facts["source"],
    }
    if native != {
            "count": review["current_reference"]["numerator"],
            "registered": review["current_reference"]["registered"],
            "clock_literal": review["current_reference"]["clock_literal"],
            "reported_units": review["current_reference"]["reported_units"],
            "total_units": review["current_reference"]["total_units"],
            "printed_pct": review["current_reference"]["printed_pct"],
            "source": facts["source"]}:
        raise ValueError("Reviewed native successor does not match complete selected facts")
    if (sum(row[fields["count"]] for row in county_rows) != native["count"]
            or sum(row[fields["registered"]] for row in county_rows) != native["registered"]
            or sum(row[fields["count"]] for row in unit_rows) != native["count"]
            or sum(row[fields["registered"]] for row in unit_rows) != native["registered"]):
        raise ValueError("Native county/reporting-unit controls do not reconcile")
    if (any(row[fields["clock"]] != native["clock_literal"] for row in parsed)
            or native["reported_units"] != native["total_units"]
            or native["reported_units"] != len(unit_rows)):
        raise ValueError("Native source clock or reporting coverage changed")
    statistic_fields = statistics["fields"]
    roles = statistics["recipe"]["roles"]
    if (statistic_fields[roles["count"]]["value"] != native["count"]
            or statistic_fields[roles["denominator"]]["value"] != native["registered"]
            or statistic_fields[roles["clock"]]["value"] != native["clock_literal"]
            or statistic_fields[roles["count"]]["native_label"] != fields["count"]
            or statistic_fields[roles["denominator"]]["native_label"] != fields["registered"]
            or [item["value"] for item in statistics["assertions"]]
            != review["required_source_assertions"]):
        raise ValueError("Selected statewide literals or election/reporting assertions changed")
    semantics = review["source_semantics"]
    if (fields["registered"] != semantics["denominator_source_literal"]
            or semantics["approved_interpretation"] != review["required_invariants"]["denominator_basis"]
            or any(semantics["qualification_flags"].values())):
        raise ValueError("Reviewed denominator literal or forbidden promotion changed")
    prior = verified_prior_query(inputs, review)
    concordance = compare_native_queries(prior, parsed, fields, review)
    if any(concordance[key] != value for key, value in review["expected_concordance"].items()):
        raise ValueError("Native source/model concordance differs from reviewed result")
    return native, parsed, prior, concordance, source[members["facts"]]


def revise(tables, native, review):
    current = copy.deepcopy(tables)
    states, controls, scenarios = current
    expected_current = review["current_reference"]
    if (native["count"] != expected_current["numerator"]
            or native["registered"] != expected_current["registered"]
            or native["clock_literal"] != expected_current["clock_literal"]
            or any(review["source_semantics"]["qualification_flags"].values())):
        raise ValueError("Reviewed native count, clock, registered stock, or source semantics changed")
    if ([len(table) for table in tables] != review["expected_table_rows"]
            or {row["state_code"] for row in states} != set(review["expected_states"])):
        raise ValueError("Complete accepted model inventory changed")
    code, identifier = review["state_code"], review["control_id"]
    selected = (
        [row for row in states if row["state_code"] == code],
        [row for row in controls if row["state_code"] == code and row["id"] == identifier],
        [row for row in scenarios if row["state_code"] == code and row["control_id"] == identifier],
    )
    if any(len(group) != 1 for group in selected):
        raise ValueError("One existing selected native reference is required")
    state, control, scenario = (group[0] for group in selected)
    previous = review["previous_reference"]
    invariants = review["required_invariants"]
    if (state["control_id"] != identifier
            or control["selected_state_reference"] != "True"
            or any(row["year"] != str(review["year"]) for row in (state, control, scenario))
            or any(value != invariants["control_measure"] for value in (
                state["control_measure"], control["measure"], scenario["control_measure"]))
            or any(value != invariants["denominator_basis"] for value in (
                state["control_denominator_basis"], control["denominator_basis"],
                scenario["native_denominator_basis"]))
            or any(value != invariants["source_url"] for value in (
                state["control_source_url"], control["source_url"], scenario["source_url"]))
            or any(value != previous["model_clock"] for value in (
                state["control_native_time"], control["source_time_label"], scenario["source_time_label"]))
            or any(integer(value) != previous["numerator"] for value in (
                state["control_native_numerator"], control["numerator"]))
            or any(integer(value) != previous["registered"] for value in (
                state["control_registered_denominator"], control["denominator"],
                scenario["native_registered_denominator"]))
            or state["reported_cast_ballots"] or state["reported_ballots_per_native_registered_denominator_pct"]
            or scenario["reported_cast_ballot_measure_control"]
            or scenario["reported_cast_minus_conditional_modeled_voter_count"]
            or any(scenario[key] != "False" for key in FLAGS)):
        raise ValueError("Accepted native reference preimage or withholding changed")
    for key, value in invariants["scenario_values"].items():
        if scenario[key] != value:
            raise ValueError("Accepted Civic weight, mean, or source size changed")
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (number(scenario[key]) for key in (
            "civic_weight", "civic_modeled_voter_weight", "civic_modeled_nonvoter_weight"))
        if weight <= 0 or voter + nonvoter != weight:
            raise ValueError("Accepted Civic weight partition changed")
        modeled_voter = number(scenario["conditional_modeled_voter_count"])
        modeled_nonvoter = number(scenario["conditional_modeled_nonvoter_count"])
        if (abs(modeled_voter + modeled_nonvoter - native["registered"]) > Decimal("1e-60")
                or native["registered"] != previous["registered"]):
            raise ValueError("Registered frame or accepted conditional means changed")
        full_gap = Decimal(native["count"]) - modeled_voter
        old_gap = Decimal(previous["numerator"]) - modeled_voter
        quantum = Decimal(review["diagnostic_quantum"])
        gap = str(full_gap.quantize(quantum))
        old_gap_rounded = str(old_gap.quantize(quantum))
    state["control_native_numerator"] = str(native["count"])
    state["control_native_time"] = review["current_reference"]["model_clock"]
    control["numerator"] = str(native["count"])
    control["source_time_label"] = review["current_reference"]["model_clock"]
    scenario["source_time_label"] = review["current_reference"]["model_clock"]
    for old_rows, new_rows, chosen in zip(tables, current, (state, control, scenario)):
        for old, new in zip(old_rows, new_rows):
            if new is not chosen and old != new:
                raise ValueError("An unrelated state, control, or scenario changed")
    allowed = review["allowed_changed_fields"]
    changes = {}
    for name, old_rows, new_rows, key_fields in (
            ("state", tables[0], states, ("state_code",)),
            ("control", tables[1], controls, ("state_code", "id")),
            ("scenario", tables[2], scenarios, ("state_code", "control_id"))):
        records = []
        for old, new in zip(old_rows, new_rows):
            fields = [key for key in old if old[key] != new[key]]
            if fields:
                identity = {key: old[key] for key in key_fields}
                records.append({
                    **identity,
                    "changed_fields": fields,
                    "previous": {key: old[key] for key in fields},
                    "current": {key: new[key] for key in fields},
                })
        if len(records) != 1 or records[0]["changed_fields"] != allowed[name]:
            raise ValueError("Changed model fields exceed the reviewed native-only scope")
        changes[name] = records
    if any(scenario[key] != tables[2][tables[2].index(next(
            row for row in tables[2] if row["state_code"] == code and row["control_id"] == identifier))][key]
            for key in FLAGS):
        raise ValueError("Behavioral qualification changed")
    delta = {
        "state_code": code,
        "control_id": identifier,
        "affected_states": [code],
        "previous_native_numerator": previous["numerator"],
        "current_native_numerator": native["count"],
        "native_numerator_difference": native["count"] - previous["numerator"],
        "registered_denominator": native["registered"],
        "registered_denominator_difference": 0,
        "previous_native_clock": previous["clock_literal"],
        "current_native_clock": native["clock_literal"],
        "conditional_modeled_voter_count": scenario["conditional_modeled_voter_count"],
        "conditional_modeled_nonvoter_count": scenario["conditional_modeled_nonvoter_count"],
        "previous_native_minus_model_diagnostic": old_gap_rounded,
        "current_native_minus_model_diagnostic": gap,
        "current_native_minus_model_full_precision": str(full_gap),
        "diagnostic_is_not_validated_model_error": True,
        "reported_cast_ballots": None,
        "reported_cast_ballot_measure_control": None,
        "fit_weights_priors_probabilities_conditional_means_changed": False,
        "house_endpoints_or_qualification_gates_changed": False,
    }
    return current, delta, changes


def preservation(inputs, review):
    result = {}
    for name, expected in review["preservation_inputs"].items():
        body = (inputs / name).read_bytes()
        if pin(body) != expected:
            raise ValueError("A pinned House endpoint, query, or withholding input changed")
        result[name] = expected
    contract = review["preservation_contract"]
    disclosure = json.loads((inputs / contract["disclosure_file"]).read_bytes())
    sensitivity = json.loads((inputs / contract["sensitivity_file"]).read_bytes())
    query_rows = rows((inputs / contract["query_file"]).read_bytes())
    if (disclosure["qualified_states"] != contract["qualified_states"]
            or disclosure["held_states"] != contract["held_states"]
            or disclosure["complete_state_group_metric_variant_witnesses"]
            != contract["query_rows"]
            or len(query_rows) != contract["query_rows"]
            or len(sensitivity["rows"]) != contract["state_rows"]
            or sum(bool(row["qualified"]) for row in sensitivity["rows"])
            != contract["qualified_states"]
            or sum(not bool(row["qualified"]) for row in sensitivity["rows"])
            != contract["held_states"]):
        raise ValueError("House endpoint/query/withholding inventory changed")
    return {
        "pins": result,
        "complete_state_group_metric_variant_rows": len(query_rows),
        "qualified_states": contract["qualified_states"],
        "held_states": contract["held_states"],
        "byte_exact_and_not_recomputed": True,
    }


def build(inputs):
    review_body = (inputs / "reviewed-successor.json").read_bytes()
    review = json.loads(review_body)
    required = {
        "contract", "version", "year", "state_code", "control_id", "expected_states",
        "expected_table_rows", "input_pins",         "source_members", "source_fields", "source_query_roles", "prior_query_contract",
        "accepted_outputs", "private_original_pin", "previous_reference",
        "current_reference", "required_source_assertions", "expected_source_rows",
        "expected_source_levels", "expected_concordance", "source_semantics",
        "required_invariants", "allowed_changed_fields", "diagnostic_quantum",
        "preservation_inputs", "preservation_contract", "source_code_pin",
        "regional_binding", "non_model_predecessors", "input_files", "package_input_files",
    }
    if (set(review) != required
            or review["contract"] != "participation.native_reference_model.v1"
            or set(review["expected_states"]) != {
                "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA",
                "HI", "IA", "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME",
                "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM",
                "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
                "UT", "VA", "VT", "WA", "WI", "WV", "WY"}):
        raise ValueError("Incomplete generic native-reference successor review")
    baseline_body = (inputs / review["input_files"]["baseline"]).read_bytes()
    source_body = (inputs / review["input_files"]["native_source"]).read_bytes()
    baseline = packet(baseline_body, review["input_pins"]["baseline"])
    source, source_manifest = manifest_packet(source_body, review["input_pins"]["native_source"])
    baseline_version = json.loads(baseline["summary.json"])["native_control_version"]
    if (review["version"] != baseline_version + 1
            or source_manifest["private_html_parse_reproduction_claimed"]
            or source_manifest["whole_project_complete"]):
        raise ValueError("Accepted predecessor version or native source packet contract changed")
    native, source_rows, prior_rows, concordance, selected_facts = selected_native_facts(
        source, inputs, review)
    model_tables = tuple(rows(baseline[name]) for name in TABLES)
    model_tables, delta, changes = revise(model_tables, native, review)
    house = preservation(inputs, review)
    files = {
        name: body for name, body in baseline.items()
        if "/" not in name
        and name not in {"checksums.json", "README.txt", "summary.json", "source-qualification.json"}
    }
    files.update({name: csv_bytes(table) for name, table in zip(TABLES, model_tables)})
    files["complete-native-reference-source-query.csv"] = csv_bytes(source_rows)
    files["complete-prior-native-reference-source-query.csv"] = csv_bytes(prior_rows)
    files["complete-native-reference-change-query.json"] = encoded(changes)
    files["complete-native-reference-identity-concordance.json"] = encoded(concordance)
    files["complete-selected-native-reference-facts.json.gz"] = selected_facts
    files["native-reference-change.json"] = encoded(delta)
    files["house-endpoint-query-withholding-preservation.json"] = encoded(house)
    files["integration-handoff.json"] = encoded({
        "contract": "participation.native_model_integration_handoff.v1",
        "model_successor_version": review["version"],
        "affected_states": [review["state_code"]],
        "control_id": review["control_id"],
        "required_combined_counts_predecessor": review["regional_binding"]["counts_predecessor"],
        "required_combined_native_predecessor": review["regional_binding"]["native_predecessor"],
        "bind_to_regional_source_record": {
            "state_code": review["state_code"],
            "count": native["count"],
            "registered": native["registered"],
            "source_clock": native["clock_literal"],
            "source_packet_sha256": review["input_pins"]["native_source"]["sha256"],
            "source_query": review["source_query_roles"]["state_query_id"],
        },
        "do_not_bind_non_model_predecessors": review["non_model_predecessors"],
        "regional_merge_must_preserve": {
            "registered": native["registered"],
            "accepted_predecessor_conditional_means": True,
            "accepted_predecessor_weights_and_priors": True,
            "house_endpoints_and_33_17_gates": True,
            "all_unaffected_model_rows": True,
        },
        "publication_authorized": False,
    })
    summary = {
        "native_control_version": review["version"],
        "state_and_dc_rows": len(model_tables[0]),
        "source_control_records": len(model_tables[1]),
        "conditional_scenarios": len(model_tables[2]),
        "affected_states": [review["state_code"]],
        "changed_state_rows": 1,
        "changed_control_rows": 1,
        "changed_existing_scenario_rows": 1,
        "changed_model_fields": review["allowed_changed_fields"],
        "new_model_variants_or_scenarios_created": 0,
        "registered_denominator_changed": False,
        "study_fit_weights_priors_probabilities_or_conditional_means_changed": False,
        "reported_cast_ballots_promoted": False,
        "native_count_used_for_outcome_fitting": False,
        "house_endpoints_or_qualification_gates_changed": False,
        "native_minus_model_diagnostic_is_validated_error": False,
        "changed_native_reference": delta,
        "source_identity_concordance": concordance,
        "publication_attempts": 0,
        "source_requests": 0,
        "whole_project_complete": False,
    }
    files["summary.json"] = encoded(summary)
    files["source-qualification.json"] = encoded({
        "contract": review["contract"],
        "native_control_version": review["version"],
        "same_election_source_family_measure_and_registered_vector_concordance": True,
        "denominator_source_literal": review["source_semantics"]["denominator_source_literal"],
        "denominator_approved_interpretation": review["source_semantics"]["approved_interpretation"],
        "denominator_forbidden_promotions": review["source_semantics"]["qualification_flags"],
        "generic_cast_ballot_measure_qualification": False,
        "reported_cast_ballots_remains_null": True,
        "counting_completion_or_certification_qualified": False,
        "native_clock_is_source_literal_not_retrieval_or_publication": True,
        "private_publisher_html_redistributed": False,
        "complete_public_selected_facts_replayed": True,
        "source_weights_priors_probabilities_fits_and_conditional_means_unchanged": True,
        "native_minus_model_is_diagnostic_not_validated_error_or_observed_nonparticipation": True,
        "prior_source_qualification": json.loads(baseline["source-qualification.json"]),
    })
    for name in review["package_input_files"]:
        files["inputs/" + name] = (inputs / name).read_bytes()
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh complete scientific output directory")
    files, summary = build(inputs)
    source = Path(__file__).parent
    for name in (
            "native_reference_model.py",
            "registered_control_successor.py",
            "state_reference_model.py",
            "reproduce_native_reference_model.py",
            "pdf_group_queries.py",
            "native_reconciliation.py",
            "native_products.py",
            "native_tabular.py",
            "native_pdf.py",
            "pdf_control_checks.py",
            "pdf_measure_queries.py",
            "state_reporting_successor.py",
            "html_statistics.py"):
        body = (source / name).read_bytes()
        if name == "native_reference_model.py" and pin(body) != json.loads(
                (inputs / "reviewed-successor.json").read_bytes())["source_code_pin"]:
            raise ValueError("Native reference model source differs from its reviewed pin")
        files["scripts/" + name] = body
    files["scripts/__init__.py"] = b""
    for path in (source / "participation_intake").glob("*.py"):
        files["scripts/participation_intake/" + path.name] = path.read_bytes()
    files["tests/test_native_reference_model.py"] = (
        source.parent / "tests/test_native_reference_model.py").read_bytes()
    review = json.loads((inputs / "reviewed-successor.json").read_bytes())
    files["README.txt"] = (
        f"Source-native control successor version {review['version']} from accepted "
        f"version {review['version'] - 1}.\n"
        f"Only the existing {review['state_code']} native numerator, source-literal clock, "
        "and separately exported\n"
        "native-minus-model diagnostic advance. Registered stock, Civic source N, weights,\n"
        "conditional means, all false qualification flags, reported-cast fields, other states,\n"
        "House endpoints and 33-qualified/17-held gates remain exact. The reviewed denominator\n"
        "literal keeps only its accepted model-basis interpretation; forbidden promotions stay false.\n"
        "Publisher HTML remains private; public replay starts from complete selected fact tables.\n"
        "Offline reproduction from a fresh extraction:\n"
        "  python3 -S -m unittest discover -s tests -p test_native_reference_model.py\n"
        "  python3 -S scripts/reproduce_native_reference_model.py --package-root . --output replay\n"
        "No fit, demographic reweight, runtime dispatch, publication, source request, or\n"
        "observed nonparticipation claim is introduced.\n"
    ).encode()
    files["checksums.json"] = encoded({name: pin(body) for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w",
                         compression=zipfile.ZIP_DEFLATED) as archive:
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
    arguments = parser.parse_args()
    print(json.dumps(export(arguments.inputs, arguments.output), indent=2, sort_keys=True))
