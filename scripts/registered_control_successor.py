"""Revise an existing registered-frame scenario using reviewed native group facts."""

import argparse
import copy
import csv
from decimal import Decimal, InvalidOperation, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from scripts.pdf_group_queries import build as grouped
from scripts.native_reconciliation import reconcile


TABLES = (
    "complete-state-control-query.csv",
    "complete-native-control-dispositions.csv",
    "complete-conditional-registered-scenarios.csv",
)
FLAGS = (
    "assumption_validated", "survey_weight_target_qualified",
    "same_frame_and_cutoff_independently_qualified", "bridge_outcome_calibration_applied",
    "model_nonvoter_is_administratively_observed_staying_home",
)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def integer(value):
    if not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("A native literal nonnegative integer is required")
    return int(value)


def number(value):
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("A finite accepted source weight is required") from error
    if not result.is_finite():
        raise ValueError("A finite accepted source weight is required")
    return result


def packet(body, expected, unlisted_documentation=()):
    if pin(body) != expected:
        raise ValueError("Changed complete sufficient input")
    if set(unlisted_documentation) - {"REPRODUCE.txt"}:
        raise ValueError("Only the known legacy explanatory note may be outside the internal manifest")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        checksums = json.loads(archive.read("checksums.json"))
        if (len(names) != len(set(names))
                or set(names) != set(checksums) | {"checksums.json"} | set(unlisted_documentation)
                or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names)):
            raise ValueError("Complete input member inventory changed")
        result = {name: archive.read(name) for name in names}
    if any(pin(result[name]) != metadata for name, metadata in checksums.items()):
        raise ValueError("Changed complete input member")
    return result


def native_control(grids, group_recipe, review):
    if set(review) != {
            "contract", "version", "year", "state_code", "control_id", "input_pins",
            "expected_states", "expected_table_rows", "prior_measure", "denominator_basis",
            "source_id", "source_url", "source_annotations", "source_members",
            "numerator_field", "denominator_field", "expected_native_rates",
            "same_scope_review_evidence"}:
        raise ValueError("Unreviewed successor option; metadata cannot supply replacement counts")
    if (review["contract"] != "participation.registered_control_successor.v1"
            or not review["same_scope_review_evidence"].strip()
            or group_recipe["source_id"] != review["source_id"]):
        raise ValueError("An explicit same-scope review and source identity are required")
    if re.findall(r"(?<!\d)\d{4}(?!\d)", review["source_annotations"].get(
            "native_election_date", "")) != [str(review["year"])]:
        raise ValueError("Native election year differs from the accepted scenario year")
    products = [p for p in grids["products"] if p["source"]["id"] == review["source_id"]]
    if len(products) != 1 or products[0]["source"]["url"] != review["source_url"]:
        raise ValueError("Native statistical product changed")
    product = products[0]
    tables = [t for t in product["tables"]
              if t["id"] in group_recipe["part_tables"] + group_recipe["summary_tables"]]
    for table in tables:
        if any(table["source_annotations"].get(key) != value
               for key, value in review["source_annotations"].items()):
            raise ValueError("Native election, clock or measure annotations changed")
    fields = review["numerator_field"], review["denominator_field"]
    if len(set(fields)) != 2 or not set(fields) <= set(group_recipe["count_fields"]):
        raise ValueError("Only reviewed native count fields can bind a control")
    with localcontext() as context:
        context.prec = 28
        queries = grouped(grids, group_recipe)
        queries["reconciliation"] = reconcile(queries["queries"], queries["checks"])
    if (not queries["reconciliation"]["required_checks_passed"]
            or queries["reconciliation"]["discrepancies"]
            or len(queries["native_rate_checks"]) != review["expected_native_rates"]
            or any(r["status"] != "matched" for r in queries["native_rate_checks"])):
        raise ValueError("Native cross-level or printed-percentage checks do not match")
    rows = queries["queries"]["summary_total"]["rows"]
    if len(rows) != 1:
        raise ValueError("An explicit single native statewide control is required")
    row = rows[0]
    numerator, denominator = (row[field] for field in fields)
    if (type(numerator) is not int or type(denominator) is not int
            or not 0 <= numerator <= denominator or denominator <= 0):
        raise ValueError("Native registered-frame counts are not qualified")
    headers = [table["source_annotations"]["native_column_headers"] for table in tables]
    labels = {}
    for field in fields:
        literals = {" ".join(header[field].split()) for header in headers}
        if len(literals) != 1:
            raise ValueError("Native count-column literal is ambiguous")
        labels[field] = literals.pop()
    return dict(numerator=numerator, denominator=denominator,
                native_measure=labels[fields[0]], denominator_label=labels[fields[1]],
                source_url=product["source"]["url"],
                source_time_label=review["source_annotations"]["native_report_date"],
                source_ref=row["source_ref"], native_source=product["source"]), queries


def revise(tables, native, review):
    states, controls, scenarios = copy.deepcopy(tables)
    before = copy.deepcopy(tables)
    if [len(rows) for rows in tables] != review["expected_table_rows"]:
        raise ValueError("Complete baseline table inventory changed")
    state_codes = [row["state_code"] for row in states]
    if (len(state_codes) != len(set(state_codes))
            or set(state_codes) != set(review["expected_states"])):
        raise ValueError("Complete state/D.C. inventory changed")
    code, identifier = review["state_code"], review["control_id"]
    selections = (
        [r for r in states if r["state_code"] == code],
        [r for r in controls if r["state_code"] == code and r["id"] == identifier],
        [r for r in scenarios if r["state_code"] == code and r["control_id"] == identifier],
    )
    if any(len(rows) != 1 for rows in selections):
        raise ValueError("Only one existing state/control/scenario may be replaced")
    state, control, scenario = (rows[0] for rows in selections)
    if (state["control_id"] != identifier
            or any(r["year"] != str(review["year"]) for r in (state, control, scenario))
            or any(value != review["prior_measure"] for value in
                   (state["control_measure"], control["measure"], scenario["control_measure"]))
            or any(value != review["denominator_basis"] for value in (
                state["control_denominator_basis"], control["denominator_basis"],
                scenario["native_denominator_basis"]))):
        raise ValueError("Existing election/measure/registered-frame identity changed")
    if (state["reported_cast_ballots"] or state["reported_ballots_per_native_registered_denominator_pct"]
            or scenario["reported_cast_ballot_measure_control"]
            or scenario["reported_cast_minus_conditional_modeled_voter_count"]
            or any(scenario[field] != "False" for field in FLAGS)):
        raise ValueError("This operation cannot promote cast ballots or behavioral qualification")
    old_registered = integer(scenario["native_registered_denominator"])
    if (old_registered <= 0
            or integer(state["control_registered_denominator"]) != old_registered
            or integer(control["denominator"]) != old_registered
            or state["control_native_numerator"] != control["numerator"]
            or scenario["civic_source_n"] != state["civic_source_n"]):
        raise ValueError("Prior state, control and accepted survey scenario disagree")
    if (native["denominator"] == old_registered
            and native["numerator"] == integer(control["numerator"])):
        raise ValueError("No changed native counts; reuse the accepted numerical analysis")
    previous_scenario = copy.deepcopy(scenario)
    with localcontext() as context:
        context.prec = 80
        weight, voter, nonvoter = (number(scenario[key]) for key in
            ("civic_weight", "civic_modeled_voter_weight", "civic_modeled_nonvoter_weight"))
        if weight <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight:
            raise ValueError("Accepted full survey weight partition changed")
        p, q = voter / weight, nonvoter / weight
        prior_v, prior_n = old_registered * p, old_registered * q
        if any(abs(a - number(scenario[field])) > Decimal("1e-60") for a, field in (
                (prior_v, "conditional_modeled_voter_count"),
                (prior_n, "conditional_modeled_nonvoter_count"))):
            raise ValueError("Prior accepted scenario no longer reproduces from its source weights")
        new_v, new_n = native["denominator"] * p, native["denominator"] * q
        if abs(new_v + new_n - native["denominator"]) > Decimal("1e-60"):
            raise ValueError("Updated registered source-unit partition failed")
        delta = dict(
            state_code=code, control_id=identifier,
            previous_registered=old_registered, current_registered=native["denominator"],
            registered_difference=native["denominator"]-old_registered,
            previous_native_reported_count=integer(control["numerator"]),
            current_native_reported_count=native["numerator"],
            previous_conditional_voter_units=str(prior_v), current_conditional_voter_units=str(new_v),
            previous_conditional_nonvoter_units=str(prior_n), current_conditional_nonvoter_units=str(new_n),
            conditional_voter_unit_difference=str(new_v-prior_v),
            conditional_nonvoter_unit_difference=str(new_n-prior_n),
            native_count_minus_modeled_voter_units_nominal_not_validated_error=str(
                Decimal(native["numerator"])-new_v),
            survey_probability_unchanged=True, outcome_calibration_applied=False,
            native_reported_count_is_qualified_cast_ballots=False,
            observed_staying_home=False, independent_population_validation=False)
    state.update(control_native_numerator=native["numerator"],
                 control_registered_denominator=native["denominator"],
                 control_native_time=native["source_time_label"],
                 control_source_url=native["source_url"])
    control.update(numerator=native["numerator"], denominator=native["denominator"],
                   source_family=native["source_url"], source_url=native["source_url"],
                   source_time_label=native["source_time_label"],
                   native_measure=native["native_measure"], denominator_label=native["denominator_label"],
                   native_status="native_report_certification_status_unspecified",
                   source_kind="reviewed_native_pdf_group_statistics",
                   scope_notes=review["same_scope_review_evidence"])
    scenario.update(
        native_registered_denominator=native["denominator"],
        source_time_label=native["source_time_label"], source_url=native["source_url"],
        control_native_status=control["native_status"],
        conditional_modeled_voter_count=str(new_v), conditional_modeled_nonvoter_count=str(new_n))
    for old_rows, new_rows, selected in zip(before, (states, controls, scenarios), (state, control, scenario)):
        for old, new in zip(old_rows, new_rows):
            if new is not selected and old != new:
                raise ValueError("An unrelated state/control/scenario changed")
    if any(previous_scenario[field] != scenario[field] for field in FLAGS):
        raise ValueError("A behavioral/weight/frame qualification changed")
    changes = [dict(state_code=old["state_code"], control_id=old["id"],
                    changed=old != new, previous=old, current=new)
               for old, new in zip(before[1], controls)]
    return (states, controls, scenarios), delta, changes


def build(inputs):
    review_body = (inputs / "reviewed-successor.json").read_bytes()
    review = json.loads(review_body)
    baseline_body = (inputs / "baseline-complete-analysis.zip").read_bytes()
    native_body = (inputs / "native-source-complete-analysis.zip").read_bytes()
    baseline = packet(baseline_body, review["input_pins"]["baseline"])
    source = packet(native_body, review["input_pins"]["native_source"], ("REPRODUCE.txt",))
    members = review["source_members"]
    grids = json.loads(gzip.decompress(source[members["grids"]]))
    native, queries = native_control(grids, json.loads(source[members["group_recipe"]]), review)
    if queries != json.loads(source[members["complete_controls"]]):
        raise ValueError("Complete native numerical query replay differs from the accepted packet")
    read = lambda name: list(csv.DictReader(io.StringIO(baseline[name].decode())))
    tables, delta, changes = revise(tuple(read(name) for name in TABLES), native, review)
    files = {name: body for name, body in baseline.items()
             if "/" not in name and name.startswith("complete-") and name.endswith(".csv")}
    files.update({name: csv_bytes(rows) for name, rows in zip(TABLES, tables)})
    files["complete-native-group-control-query.json"] = encoded(queries)
    files["complete-registered-control-change-query.json"] = encoded(changes)
    files["registered-frame-change.json"] = encoded(delta)
    summary = dict(
        native_control_version=review["version"], state_and_dc_rows=len(tables[0]),
        source_control_records=len(tables[1]), conditional_scenarios=len(tables[2]),
        changed_state_rows=1, changed_control_rows=1, changed_existing_scenarios=1,
        preserved_other_states=len(tables[0])-1, preserved_other_controls=len(tables[1])-1,
        preserved_other_scenarios=len(tables[2])-1,
        study_fit_weights_or_probabilities_changed=False,
        new_model_variants_or_scenarios_created=0, native_count_used_for_outcome_fitting=False,
        state_to_county_or_demographic_allocation=False, observed_staying_home=False,
        changed_registered_frame=delta)
    files["summary.json"] = encoded(summary)
    files["source-qualification.json"] = encoded(dict(
        contract=review["contract"], native_control_version=review["version"],
        same_scope_review=review["same_scope_review_evidence"],
        source=native["native_source"], source_ref=native["source_ref"],
        original_population_weight_target_and_cutoff_qualification_not_lifted=True,
        registered_source_units_not_individuals=True,
        physical_ballot_unique_voter_eligible_population_or_staying_home_qualification=False,
        no_new_bridge_or_native_outcome_calibration=True))
    files["inputs/baseline-complete-analysis.zip"] = baseline_body
    files["inputs/native-source-complete-analysis.zip"] = native_body
    files["inputs/reviewed-successor.json"] = review_body
    return files, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh complete analysis directory")
    files, summary = build(inputs)
    source = Path(__file__).parent
    for name in ("registered_control_successor.py", "pdf_group_queries.py", "native_reconciliation.py",
                 "native_products.py", "native_tabular.py", "native_pdf.py",
                 "pdf_control_checks.py", "pdf_measure_queries.py"):
        files["scripts/" + name] = (source / name).read_bytes()
    files["tests/test_registered_control_successor.py"] = source.parent.joinpath(
        "tests/test_registered_control_successor.py").read_bytes()
    files["README.txt"] = (
        "Existing registered-frame scenario successor, not observed voter/nonvoter counts.\n"
        "Complete prior all-state analysis and complete accepted native factual source packet\n"
        "remain nested sufficient inputs. Every current state/control/scenario query and all\n"
        "other prior top-level complete CSVs are included. No raw respondents, publisher app\n"
        "code, new survey fit/weights, group allocation or outcome calibration is introduced.\n"
        "From a fresh full extraction, offline with the Python standard library only:\n"
        "  python3 -S -m unittest discover -s tests -p test_registered_control_successor.py\n"
        "  python3 -S -m scripts.registered_control_successor --inputs inputs --output /new/replay\n"
        "Compare every complete output, source qualification and change query, not only summary.\n"
        "Native source registration/cutoff/status exchangeability remains UNVALIDATED. The\n"
        "native Votes Cast count is context, not a cast-ballot target or observed staying home.\n"
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
    args = parser.parse_args()
    print(json.dumps(export(args.inputs, args.output), indent=2, sort_keys=True))
