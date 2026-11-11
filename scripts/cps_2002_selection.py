"""Select reported 2002 CPS points without interpreting unqualified precision fields."""

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import zipfile


NATIVE_SHA = "8b4bf57db10e2f5a75199b979b890708692a2e8f560aad99119db98a9458d05b"
BASELINE_SHA = "bda083bac82cd4ac43a7f50e99a02a1c0d15113da9cb0341e9e5a1908a77152e"
METHODOLOGY_SHA = "4ead438af1ad9177261596293dc2dd3f1b49a7e4fa747b09b0c4fdcbe067fb2c"
POLICY_CONTRACT = "participation.cps_2002_point_selection.v1"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def number(value):
    return type(value) in (int, float)


def difference(current, previous):
    return format(Decimal(str(current)) - Decimal(str(previous)), "f")


def validate_policy(policy):
    if (policy["contract"] != POLICY_CONTRACT or policy["year"] != 2002
            or policy["selection"] != "reported_native_points_only"
            or policy["minimum_weighted_population_thousands"] != 75
            or policy["same_type_comparison_years"] != [2018, 2022]
            or policy["comparison_population_frame"] != "cvap"
            or policy["confidence_scalar_interpretation"]
                != "unqualified_except_direct_national_citizen_report_anchor"
            or policy["comparisons_are_snapshots_not_cohorts"] is not True
            or policy["exact_native_group_labels_required"] is not True
            or any(policy[key] is not False for key in (
                "minimum_is_sample_size", "minimum_guarantees_precision", "new_intervals_allowed",
                "new_standard_errors_allowed", "race_harmonization_allowed",
                "suppressed_rates_reconstructed", "native_defects_repaired",
                "conflicting_pennsylvania_totals_selected", "local_allocation_allowed",
                "frontend_activation"))):
        raise ValueError("Unqualified change to the point-only selection policy")


def load_inputs(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    if manifest["contract"] != "participation.cps_2002_selection_inputs.v1":
        raise ValueError("Unknown frozen input contract")
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe input path")
        if pin((root / name).read_bytes()) != expected:
            raise ValueError("Changed sufficient input: " + name)
    if (manifest["native_review_sha256"] != NATIVE_SHA
            or pin((root / "native-review.json").read_bytes())["sha256"] != NATIVE_SHA
            or pin((root / "methodology-review.json").read_bytes())["sha256"] != METHODOLOGY_SHA
            or manifest["baseline_sha256"] != BASELINE_SHA
            or pin((root / "baseline-science.zip").read_bytes())["sha256"] != BASELINE_SHA):
        raise ValueError("Changed accepted native or baseline reduction")
    native = json.loads((root / "native-review.json").read_bytes())
    verification = json.loads((root / "native-verification.json").read_bytes())
    methods = json.loads((root / "methodology-review.json").read_bytes())
    policy = json.loads((root / "policy.json").read_bytes())
    validate_policy(policy)
    for evidence in (native, methods):
        for name, expected in evidence["source_pins"].items():
            if name.endswith((".xls", ".pdf")) and pin(
                    (root / "originals" / name).read_bytes())["sha256"] != expected:
                raise ValueError("Original differs from accepted factual reduction")
    if (not native["native_review_passed"]
            or not verification["independent_native_verification_passed"]
            or verification["review_sha256"] != NATIVE_SHA
            or not methods["automated_methodology_evidence_checks_passed"]
            or methods["native_review_sha256"] != NATIVE_SHA
            or methods["workbook_precision_mapping_qualified"] is not False):
        raise ValueError("Missing or changed accepted evidence")
    with zipfile.ZipFile(root / "baseline-science.zip") as archive:
        checksums = json.loads(archive.read("checksums.json"))
        for name, expected in checksums.items():
            if pin(archive.read(name)) != expected:
                raise ValueError("Changed complete predecessor member")
        baseline = list(csv.DictReader(io.StringIO(
            archive.read("complete-state-year-population-pairs.csv").decode())))
    return native, methods, baseline, policy


def build(native, methods, baseline, policy):
    validate_policy(policy)
    evidence = methods["evidence"]
    if (evidence["confidence_level"]["percent"] != 90
            or evidence["normal_interval_multiplier"]["value"] != 1.645
            or evidence["population_base_caution"]["persons"] != 75000):
        raise ValueError("Changed source methodology")
    lookup = {(int(row["year"]), row["reference_state_code"], row["population_frame"]): row
        for row in baseline}
    if len(lookup) != len(baseline):
        raise ValueError("Duplicate historical reference")
    codes = {row["native_state_name"].upper(): row["reference_state_code"] for row in baseline}
    records, reconciliations, comparisons = [], [], []
    for source in native["observations"]:
        if source["year"] != 2002:
            raise ValueError("Wrong native election year")
        values = source["values"]
        citizen = source["role"] == "citizen_overall"
        if source["denominator"] != ("citizen" if citizen else "18+"):
            raise ValueError("Native denominator differs from its source table")
        frame = "cvap" if citizen else "vap"
        base = values["citizen_adults_thousands" if citizen else "adults_thousands"]
        decision = source["display_disposition"]
        if decision == "candidate_native_rate_pending_precision_and_public_selection":
            if source["native_flags"] or not number(values["voted_pct"]):
                raise ValueError("Candidate source row contains a defect or absent rate")
            decision = ("selected_reported_point_only" if number(base) and base > 75
                else "withheld_weighted_population_caution")
        elif not decision.startswith("withheld_"):
            raise ValueError("Unknown accepted source disposition")
        selected = decision == "selected_reported_point_only"
        anchor = evidence["citizen_national_report_anchor"] if (
            citizen and source["geography"] == "UNITED STATES" and selected) else None
        if anchor and (values["voted_pct"] != anchor["voted_pct"]
                or values["registered_pct"] != anchor["registered_pct"]
                or values["voted_native_confidence"] != anchor["native_confidence_value"]
                or values["registered_native_confidence"] != anchor["native_confidence_value"]):
            raise ValueError("Direct national report anchor differs")
        record = dict(native=source, source_key=f"{source['file']}:{source['row']}",
            reference_state_code=codes.get(source["geography"]),
            population_frame=frame, decision=decision,
            selected_voted_pct=values["voted_pct"] if selected else None,
            selected_registered_pct=values["registered_pct"] if selected else None,
            source_reported_precision_values=dict(voted=values["voted_native_confidence"],
                registered=values["registered_native_confidence"]),
            published_national_citizen_interval=(
                dict(confidence_level=90, voted=anchor["voted_printed_ci"],
                    registered=anchor["registered_printed_ci"], source=anchor["source"],
                    page=anchor["page"], derived=False) if anchor else None),
            interpreted_workbook_interval=None, standard_error=None,
            weighted_population_is_sample_size=False, race_categories_harmonized=False,
            administrative_turnout=False, individual_history=False, local_allocation=False)
        records.append(record)
        total = citizen or source["native_label"] == ".Total"
        reference = lookup.get((2002, record["reference_state_code"], frame)) if total else None
        status = ("not_overall_native_query" if not total else
            "no_national_retrospective_state_frame" if record["reference_state_code"] is None else
            "held_native_selection" if not selected else
            "no_qualified_retrospective_frame" if not reference
                or not reference["reported_voted_pct"] or not reference["reported_registered_pct"] else
            "reported_same_frame_percentage_comparison")
        comparable = status == "reported_same_frame_percentage_comparison"
        reconciliations.append(dict(source_key=record["source_key"],
            geography=source["geography"], population_frame=frame, disposition=status,
            reference=reference, voted_difference_pp=(
                difference(values["voted_pct"], reference["reported_voted_pct"]) if comparable else None),
            registered_difference_pp=(
                difference(values["registered_pct"], reference["reported_registered_pct"]) if comparable else None),
            source_counts_repaired=False))
        if not citizen:
            continue
        for year in policy["same_type_comparison_years"]:
            endpoint = lookup.get((year, record["reference_state_code"], "cvap"))
            status = ("held_2002_native_selection" if not selected else
                "no_national_retrospective_state_frame" if record["reference_state_code"] is None else
                "held_missing_same_frame_endpoint" if not endpoint
                    or not endpoint["reported_voted_pct"] or not endpoint["reported_registered_pct"] else
                "same_type_reported_snapshot_difference_not_cohort")
            comparable = status == "same_type_reported_snapshot_difference_not_cohort"
            comparisons.append(dict(source_key=record["source_key"], geography=source["geography"],
                reference_state_code=record["reference_state_code"], from_year=2002, to_year=year,
                election_type="midterm", population_frame="cvap", disposition=status, endpoint=endpoint,
                reported_voted_difference_pp=(difference(
                    endpoint["reported_voted_pct"], values["voted_pct"]) if comparable else None),
                reported_registered_difference_pp=(difference(
                    endpoint["reported_registered_pct"], values["registered_pct"]) if comparable else None),
                definitions_harmonized=False, change_interval=None, statistical_significance=None,
                individual_retention=None, population_count=None, local_allocation=False))
    summary = dict(native_rows=len(records), metric_cells=sum(len(row["native"]["values"]) for row in records),
        selected_reported_point_rows=sum(row["decision"] == "selected_reported_point_only" for row in records),
        selected_distinct_geography_frame_group_cells=len({
            (row["native"]["geography"], row["population_frame"],
                "overall" if row["native"]["role"] == "citizen_overall" else row["native"]["native_label"])
            for row in records if row["decision"] == "selected_reported_point_only"}),
        selected_non_total_group_rows=sum(row["decision"] == "selected_reported_point_only"
            and row["native"]["role"] != "citizen_overall" and row["native"]["native_label"] != ".Total"
            for row in records),
        point_decisions=dict(sorted(Counter(row["decision"] for row in records).items())),
        flagged_native_rows=sum(bool(row["native"]["native_flags"]) for row in records),
        reconciliation_decisions=dict(sorted(Counter(row["disposition"] for row in reconciliations).items())),
        snapshot_decisions=dict(sorted(Counter(row["disposition"] for row in comparisons).items())),
        full_reconciliation_rows=len(reconciliations), full_snapshot_rows=len(comparisons),
        new_intervals=0, new_standard_errors=0, native_precision_mapping_qualified=False,
        new_population_or_2026_estimates=0, frontend_activation=False)
    return dict(contract="participation.cps_2002_reported_points.v1", policy=policy,
        qualification="reported_point_estimates_only_not_precision_or_category_harmonization",
        records=records, reconciliations=reconciliations, snapshot_comparisons=comparisons,
        summary=summary)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def result_files(result):
    points = []
    for record in result["records"]:
        native = record["native"]
        points.append(dict(source_key=record["source_key"], geography=native["geography"],
            native_group=native["native_label"], native_table_role=native["role"],
            population_frame=record["population_frame"], decision=record["decision"],
            selected_voted_pct=record["selected_voted_pct"],
            selected_registered_pct=record["selected_registered_pct"],
            **native["values"], flags=json.dumps(native["native_flags"], separators=(",", ":"))))
    reconciliation = [{key: value for key, value in row.items() if key != "reference"}
        for row in result["reconciliations"]]
    snapshots = [{key: value for key, value in row.items() if key != "endpoint"}
        for row in result["snapshot_comparisons"]]
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
        "complete-point-decisions.csv": csv_bytes(points),
        "complete-source-reconciliation.csv": csv_bytes(reconciliation),
        "complete-midterm-snapshot-comparisons.csv": csv_bytes(snapshots)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output directory")
    result = build(*load_inputs(args.inputs))
    args.output.mkdir(parents=True)
    for name, body in result_files(result).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
