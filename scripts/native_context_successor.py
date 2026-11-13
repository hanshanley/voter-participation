"""Refresh a non-model native context from complete pinned reporting-unit facts."""

import argparse
from collections import defaultdict
import copy
import csv
import gzip
import io
import json
from pathlib import Path
import re
import zipfile

from scripts.registered_control_successor import TABLES, csv_bytes, encoded, integer, packet, pin


MEASURE = "native_reported_participation_count_not_qualified_physical_ballots_or_unique_people"
BASIS = "complete_native_registration_components_not_unique_eligible_population"


def source_packet(body, expected):
    if pin(body) != expected:
        raise ValueError("Changed complete accepted native source packet")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))["files"]
        if (len(names) != len(set(names)) or set(names) != set(manifest) | {"manifest.json"}
                or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names)):
            raise ValueError("Incomplete or unsafe native packet inventory")
        files = {name: archive.read(name) for name in names}
    if any(pin(files[name]) != expected for name, expected in manifest.items()):
        raise ValueError("Changed native source member")
    return files


def source_facts(files, review):
    if set(review) != {
            "contract", "version", "year", "state_code", "control_id", "input_pins",
            "expected_states", "expected_table_rows", "source_members", "source_url",
            "expected_units", "expected_parents", "table", "query", "page", "scope_review"}:
        raise ValueError("Unreviewed context option; metadata cannot supply replacement counts")
    if (review["contract"] != "participation.native_context_successor.v1"
            or not review["scope_review"].strip() or type(review["year"]) is not int):
        raise ValueError("An explicit native-context scope review is required")
    members, spec, query, page_spec = (review[k] for k in ("source_members", "table", "query", "page"))
    if set(members) != {"table", "receipt", "queries", "page"}:
        raise ValueError("Complete original, receipt, numerical queries and page facts are required")
    if set(spec) != {
            "delimiter", "columns", "numeric_fields", "identity_fields", "parent_field",
            "state_field", "reported_field", "numerator_field", "denominator_fields", "component_fields"}:
        raise ValueError("Unreviewed native column role")
    columns = spec["columns"]
    numeric = spec["numeric_fields"]
    count_roles = [spec["numerator_field"], *spec["denominator_fields"], *spec["component_fields"]]
    if (not columns or len(columns) != len(set(columns)) or any(not isinstance(c, str) for c in columns)
            or len(numeric) != len(set(numeric)) or not set(numeric) <= set(columns)
            or not set(count_roles) <= set(numeric)
            or len(spec["denominator_fields"]) != len(set(spec["denominator_fields"]))
            or not spec["denominator_fields"] or not spec["component_fields"]
            or len(spec["component_fields"]) != len(set(spec["component_fields"]))
            or spec["numerator_field"] in spec["denominator_fields"] + spec["component_fields"]
            or set(spec["denominator_fields"]) & set(spec["component_fields"])
            or not spec["identity_fields"]
            or len(spec["identity_fields"]) != len(set(spec["identity_fields"]))
            or not set(spec["identity_fields"]) <= set(columns)
            or any(spec[k] not in columns for k in ("parent_field", "state_field", "reported_field"))):
        raise ValueError("Invalid native identity/count/registration role")
    if set(query) != {
            "units", "parents", "source_record", "parent_id", "parent_native_record",
            "reported", "numerator", "component_residual", "electorate_excess", "rate",
            "parent_rows", "parent_numerator", "parent_registered_fields",
            "parent_conflicts", "parent_excesses"}:
        raise ValueError("Unreviewed accepted-query field")
    if set(query["parent_registered_fields"]) != set(spec["denominator_fields"]):
        raise ValueError("Every native registration component needs its parent comparison")
    raw = files[members["table"]]
    receipt = json.loads(files[members["receipt"]])
    if (receipt["status"] != 200 or receipt["url"] != review["source_url"]
            or pin(raw) != {key: receipt[key] for key in ("bytes", "sha256")}):
        raise ValueError("Original, source identity and native receipt disagree")
    accepted = json.loads(files[members["queries"]])
    page = json.loads(files[members["page"]])
    if (set(page_spec) != {"year_literal", "clock", "timezone", "register_control", "register_field"}
            or page_spec["year_literal"] not in page["source_text"]
            or re.findall(r"(?<!\d)\d{4}(?!\d)", page_spec["year_literal"]) != [str(review["year"])]
            or not isinstance(page[page_spec["clock"]], str) or not page[page_spec["clock"]]
            or page[page_spec["timezone"]] is not None):
        raise ValueError("Native election, source clock or unknown-timezone contract changed")
    raw_rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""),
                               delimiter=spec["delimiter"], strict=True))
    if len(raw_rows) != review["expected_units"] or any(len(r) != len(columns) for r in raw_rows):
        raise ValueError("Complete native reporting-unit inventory changed")
    old_units = accepted[query["units"]]
    old_by_id = {}
    for row in old_units:
        identity = tuple(row[query["source_record"]][field] for field in spec["identity_fields"])
        if identity in old_by_id:
            raise ValueError("Duplicated accepted unit identity")
        old_by_id[identity] = row
    if len(old_by_id) != review["expected_units"]:
        raise ValueError("Accepted complete unit inventory changed")
    units, parents, seen = [], defaultdict(list), set()
    for line, literals in enumerate(raw_rows, 1):
        row = dict(zip(columns, literals))
        if row[spec["state_field"]] != review["state_code"] or row[spec["reported_field"]] != "1":
            raise ValueError("Wrong jurisdiction or unreported unit; estimates cannot fill counts")
        for field in numeric:
            if not re.fullmatch(r"[0-9]+", row[field]) or int(row[field]) > 2**53 - 1:
                raise ValueError("A literal nonnegative native safe count is required")
            row[field] = int(row[field])
        identity = tuple(row[field] for field in spec["identity_fields"])
        prior = old_by_id.get(identity)
        if identity in seen or prior is None:
            raise ValueError("Duplicated or unknown native unit identity")
        seen.add(identity)
        value = row[spec["numerator_field"]]
        registered = sum(row[field] for field in spec["denominator_fields"])
        residual = value - sum(row[field] for field in spec["component_fields"])
        excess = value - registered
        if (prior[query["source_record"]] != row or prior[query["reported"]] is not True
                or prior[query["numerator"]] != value
                or prior[query["component_residual"]] != residual
                or prior[query["electorate_excess"]] != excess or prior[query["rate"]] is not None):
            raise ValueError("Complete original and accepted numerical unit query disagree")
        item = dict(source_row=line, source_record=row, reported=True,
                    native_numerator=value, registration_components={
                        field: row[field] for field in spec["denominator_fields"]},
                    component_residual=residual, electorate_excess=excess, analysis_rate=None)
        units.append(item)
        parents[row[spec["parent_field"]]].append(item)
    if seen != set(old_by_id) or len(parents) != review["expected_parents"]:
        raise ValueError("Complete reporting-unit/parent universe changed")
    old_parents = accepted[query["parents"]]
    old_parent_ids = [r[query["parent_id"]] for r in old_parents]
    if len(old_parent_ids) != len(set(old_parent_ids)) or set(old_parent_ids) != set(parents):
        raise ValueError("Accepted complete parent inventory changed")
    parent_queries = []
    for prior in old_parents:
        identity = prior[query["parent_id"]]
        selected = parents[identity]
        counts = {field: sum(item["source_record"][field] for item in selected) for field in numeric}
        conflicts = sum(item["component_residual"] != 0 for item in selected)
        excesses = sum(item["electorate_excess"] > 0 for item in selected)
        native_parent = prior[query["parent_native_record"]]
        if (native_parent[query["parent_rows"]] != len(selected)
                or native_parent[query["parent_numerator"]] != counts[spec["numerator_field"]]
                or native_parent[query["parent_conflicts"]] != conflicts
                or native_parent[query["parent_excesses"]] != excesses
                or any(native_parent[native] != counts[field]
                       for field, native in query["parent_registered_fields"].items())):
            raise ValueError("Native parent totals/components disagree with complete unit queries")
        parent_queries.append(dict(parent_id=identity, reporting_units=len(selected),
                                   native_counts=counts, component_conflicts=conflicts,
                                   electorate_excesses=excesses))
    totals = {field: sum(row["source_record"][field] for row in units) for field in numeric}
    labels = page["source_text"]
    indices = [i for i, text in enumerate(labels) if text == page_spec["register_control"]]
    if (len(indices) != 1 or indices[0] + 1 >= len(labels)
            or page_spec["register_field"] not in spec["denominator_fields"]
            or integer(labels[indices[0] + 1].replace(",", "")) != totals[page_spec["register_field"]]):
        raise ValueError("Separate printed registration control disagrees with native unit sums")
    result = dict(
        contract=review["contract"], state_code=review["state_code"], year=review["year"],
        complete_native_units=len(units), complete_native_parents=len(parents),
        derived_native_numerator=totals[spec["numerator_field"]],
        native_registration_components={field: totals[field] for field in spec["denominator_fields"]},
        native_component_conflicts=sum(item["component_residual"] != 0 for item in units),
        native_electorate_excesses=sum(item["electorate_excess"] > 0 for item in units),
        explicit_reported_zero_rows=sum(item["native_numerator"] == 0 for item in units),
        source_time_label=page[page_spec["clock"]], source_timezone=None,
        source_url=receipt["url"], original_pin=pin(raw),
        source_counts_repaired=False, independently_printed_state_count=None,
        physical_ballots_unique_people_or_observed_staying_home_qualified=False,
        precinct_rates_allocations_or_geometry_changes=0,
        native_column_schema_is_reviewed_not_a_printed_header=True)
    return dict(summary=result, units=units, parents=parent_queries)


def revise(tables, facts, review):
    states, controls, scenarios = copy.deepcopy(tables)
    if ([len(rows) for rows in tables] != review["expected_table_rows"]
            or len({r["state_code"] for r in states}) != len(states)
            or {r["state_code"] for r in states} != set(review["expected_states"])):
        raise ValueError("Complete state/control/scenario universe changed")
    identifier, code = review["control_id"], review["state_code"]
    selected = [r for r in controls if r["id"] == identifier and r["state_code"] == code]
    if len(selected) != 1:
        raise ValueError("Exactly one existing non-model native context is required")
    control = selected[0]
    if (control["selected_state_reference"] != "False"
            or any(r["control_id"] == identifier for r in states + scenarios)
            or control["year"] != str(review["year"])
            or control["source_url"] != review["source_url"]
            or control["geographic_level"] not in (
                "partial_state_reporting_units", "complete_state_reporting_units")):
        raise ValueError("Do not change a selected reference, model scenario or other native source scope")
    original = copy.deepcopy(control)
    summary = facts["summary"]
    if (summary["state_code"] != code or summary["year"] != review["year"]
            or summary["source_url"] != control["source_url"]):
        raise ValueError("Derived native source and existing context identity disagree")
    numerator = summary["derived_native_numerator"]
    denominator = sum(summary["native_registration_components"].values())
    if (control["numerator"] == str(numerator) and control["denominator"] == str(denominator)
            and control["geographic_level"] == "complete_state_reporting_units"):
        raise ValueError("No numerical or native-coverage change; reuse the current complete analysis")
    control.update(
        geographic_level="complete_state_reporting_units", measure=MEASURE,
        native_measure="Native reporting-unit participation count; see complete original and column schema",
        numerator=str(numerator), denominator=str(denominator), denominator_basis=BASIS,
        denominator_label=" + ".join(summary["native_registration_components"]),
        source_time_label=summary["source_time_label"] + "; timezone not supplied",
        native_status="unofficial_native_reporting_context_not_certified_unique_people",
        source_kind="reviewed_complete_native_reporting_units",
        scope_notes=review["scope_review"],
        disposition="complete_native_context_separate_from_selected_registration_and_survey_frame")
    if states != tables[0] or scenarios != tables[2]:
        raise ValueError("A state estimate, source propensity or conditional scenario changed")
    changes = [dict(state_code=old["state_code"], control_id=old["id"],
                    changed=old != new, previous=old, current=new)
               for old, new in zip(tables[1], controls)]
    if sum(row["changed"] for row in changes) != 1:
        raise ValueError("An unrelated native control changed")
    return (states, controls, scenarios), changes, dict(
        state_code=code, control_id=identifier, previous=original, current=control,
        selected_state_reference_changed=False, selected_registered_frame_changed=False,
        conditional_modeled_counts_changed=False, native_context_only=True)


def build(inputs):
    review_body = (inputs / "reviewed-successor.json").read_bytes()
    review = json.loads(review_body)
    baseline_body = (inputs / "baseline-complete-analysis.zip").read_bytes()
    source_body = (inputs / "native-source-complete-analysis.zip").read_bytes()
    baseline = packet(baseline_body, review["input_pins"]["baseline"])
    if review["version"] != json.loads(baseline["summary.json"])["native_control_version"] + 1:
        raise ValueError("Use the next version of the complete accepted control analysis")
    source = source_packet(source_body, review["input_pins"]["native_source"])
    facts = source_facts(source, review)
    read = lambda name: list(csv.DictReader(io.StringIO(baseline[name].decode())))
    tables, changes, change = revise(tuple(read(name) for name in TABLES), facts, review)
    files = {name: body for name, body in baseline.items()
             if "/" not in name and name not in ("checksums.json", "README.txt", "summary.json",
                                                "source-qualification.json")}
    files[TABLES[1]] = csv_bytes(tables[1])
    summary = dict(
        native_control_version=review["version"], state_and_dc_rows=len(tables[0]),
        source_control_records=len(tables[1]), conditional_scenarios=len(tables[2]),
        changed_state_rows=0, changed_control_rows=1, changed_existing_scenarios=0,
        study_fit_weights_or_probabilities_changed=False,
        new_model_variants_or_scenarios_created=0, native_count_used_for_outcome_fitting=False,
        state_to_county_or_demographic_allocation=False, observed_staying_home=False,
        native_context_update=facts["summary"])
    files["summary.json"] = encoded(summary)
    files["complete-native-context-query.json.gz"] = gzip.compress(encoded(facts), mtime=0)
    files["complete-native-context-change-query.json"] = encoded(changes)
    files["native-context-change.json"] = encoded(change)
    files["source-qualification.json"] = encoded(dict(
        contract=review["contract"], native_control_version=review["version"],
        current_native_context=facts["summary"], explicit_scope_review=review["scope_review"],
        prior_source_qualification=json.loads(baseline["source-qualification.json"]),
        selected_registration_population_and_qualification_unchanged=True,
        physical_ballots_unique_people_or_observed_staying_home_qualified=False,
        no_new_bridge_or_native_outcome_calibration=True))
    files["inputs/baseline-complete-analysis.zip"] = baseline_body
    files["inputs/native-source-complete-analysis.zip"] = source_body
    files["inputs/reviewed-successor.json"] = review_body
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh complete analysis directory")
    files, summary = build(inputs)
    source = Path(__file__).parent
    for name in ("native_context_successor.py", "registered_control_successor.py",
                 "pdf_group_queries.py", "native_reconciliation.py", "native_products.py",
                 "native_tabular.py", "native_pdf.py", "pdf_control_checks.py", "pdf_measure_queries.py"):
        files["scripts/" + name] = (source / name).read_bytes()
    files["tests/test_native_context_successor.py"] = source.parent.joinpath(
        "tests/test_native_context_successor.py").read_bytes()
    files["README.txt"] = (
        "Complete native reporting context successor, not a new model or turnout population.\n"
        "The complete previous all-state model and complete accepted native packet are included.\n"
        "All state rows and conditional scenario CSV bytes remain unchanged. The separate dated\n"
        "register is NOT replaced by reporting-unit registration components. Counts retain\n"
        "component discrepancies/excesses/zeros; no source counts or missing values are repaired.\n"
        "Native derived counts are not independently printed state totals or unique people.\n"
        "Fresh full extraction, Python standard library only, no network or dependencies:\n"
        "  python3 -S -m unittest discover -s tests -p test_native_context_successor.py\n"
        "  python3 -S -m scripts.native_context_successor --inputs inputs --output /new/replay\n"
        "Compare all complete outputs and the entire ZIP, not only summaries.\n"
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
