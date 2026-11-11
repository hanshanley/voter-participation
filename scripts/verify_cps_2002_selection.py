"""Independently verify every selected source cell, hold, precision field and difference."""

import argparse
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile


METRICS = ("adults_thousands", "citizen_adults_thousands", "citizen_adults_pct",
    "citizen_adults_native_confidence", "registered_thousands", "registered_pct",
    "registered_native_confidence", "voted_thousands", "voted_pct", "voted_native_confidence")
NATIVE_SHA = "8b4bf57db10e2f5a75199b979b890708692a2e8f560aad99119db98a9458d05b"
BASELINE_SHA = "bda083bac82cd4ac43a7f50e99a02a1c0d15113da9cb0341e9e5a1908a77152e"
METHODOLOGY_SHA = "4ead438af1ad9177261596293dc2dd3f1b49a7e4fa747b09b0c4fdcbe067fb2c"


def verify(inputs, output):
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(message)

    def scalar(value):
        return "" if value is None else str(value)

    def check_difference(value, right, left):
        require(value is not None and Fraction(value) == Fraction(str(right)) - Fraction(str(left)),
            "Source snapshot difference differs")

    manifest = json.loads((inputs / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        body = (inputs / name).read_bytes()
        require(dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) == expected,
            "Changed complete sufficient input")
    require(hashlib.sha256((inputs / "native-review.json").read_bytes()).hexdigest() == NATIVE_SHA,
        "Changed accepted native review")
    require(hashlib.sha256((inputs / "baseline-science.zip").read_bytes()).hexdigest() == BASELINE_SHA,
        "Changed complete predecessor")
    require(hashlib.sha256((inputs / "methodology-review.json").read_bytes()).hexdigest() == METHODOLOGY_SHA,
        "Changed accepted methodology")
    native = json.loads((inputs / "native-review.json").read_bytes())
    methods = json.loads((inputs / "methodology-review.json").read_bytes())
    accepted = json.loads((inputs / "native-verification.json").read_bytes())
    for evidence in (native, methods):
        for name, expected in evidence["source_pins"].items():
            if name.endswith((".xls", ".pdf")):
                require(hashlib.sha256((inputs / "originals" / name).read_bytes()).hexdigest() == expected,
                    "Original differs from accepted factual reduction")
    result = json.loads((output / "complete-result.json").read_bytes())
    require(accepted["independent_native_verification_passed"]
        and accepted["review_sha256"] == NATIVE_SHA, "Original independent reduction not accepted")
    require(result["contract"] == "participation.cps_2002_reported_points.v1", "Result contract differs")
    require(result["policy"] == json.loads((inputs / "policy.json").read_bytes()), "Policy differs")
    policy = result["policy"]
    require(policy["selection"] == "reported_native_points_only"
        and policy["minimum_weighted_population_thousands"] == 75
        and policy["same_type_comparison_years"] == [2018, 2022]
        and policy["comparison_population_frame"] == "cvap", "Point-only selection differs")
    for field in ("new_intervals_allowed", "new_standard_errors_allowed",
            "race_harmonization_allowed", "suppressed_rates_reconstructed", "native_defects_repaired",
            "conflicting_pennsylvania_totals_selected", "local_allocation_allowed",
            "minimum_is_sample_size", "minimum_guarantees_precision", "frontend_activation"):
        require(policy[field] is False, "Unqualified policy promotion")
    with zipfile.ZipFile(inputs / "baseline-science.zip") as archive:
        for name, expected in json.loads(archive.read("checksums.json")).items():
            body = archive.read(name)
            require(dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) == expected,
                "Changed predecessor member")
        baseline = list(csv.DictReader(io.StringIO(
            archive.read("complete-state-year-population-pairs.csv").decode())))
    lookup = {(int(row["year"]), row["reference_state_code"], row["population_frame"]): row for row in baseline}
    codes = {row["native_state_name"].upper(): row["reference_state_code"] for row in baseline}
    records, reconciliations, comparisons = result["records"], result["reconciliations"], result["snapshot_comparisons"]
    require(len(records) == len(reconciliations) == len(native["observations"]) == 832, "Incomplete point inventory")
    require(len(comparisons) == 104, "Incomplete midterm snapshot inventory")
    keys, point_rows = [], []
    comparison_index = 0
    for source, record, reconciliation in zip(native["observations"], records, reconciliations):
        require(record["native"] == source, "Source field, defect, suppression or literal repaired")
        require(source["year"] == 2002, "Wrong native election year")
        raw = native["native_sheets"][source["file"]][source["row"] - 1]
        for column, metric in enumerate(METRICS, 1):
            require(source["values"][metric] == raw[column], "Native factual worksheet cell differs")
        values = source["values"]
        citizen = source["role"] == "citizen_overall"
        frame = "cvap" if citizen else "vap"
        require(source["denominator"] == ("citizen" if citizen else "18+"), "Adult/citizen frame relabeled")
        source_key = f"{source['file']}:{source['row']}"
        keys.append(source_key)
        code = codes.get(source["geography"])
        require(record["source_key"] == reconciliation["source_key"] == source_key
            and record["reference_state_code"] == code
            and record["population_frame"] == reconciliation["population_frame"] == frame,
            "Identity or population frame differs")
        candidate = source["display_disposition"] == "candidate_native_rate_pending_precision_and_public_selection"
        base = values["citizen_adults_thousands" if citizen else "adults_thousands"]
        selected = candidate and type(base) in (int, float) and base > 75
        expected_decision = ("selected_reported_point_only" if selected else
            "withheld_weighted_population_caution" if candidate else source["display_disposition"])
        require(record["decision"] == expected_decision, "Source hold or population caution promoted")
        require(record["selected_voted_pct"] == (values["voted_pct"] if selected else None)
            and record["selected_registered_pct"] == (values["registered_pct"] if selected else None),
            "Selected reported point differs")
        require(record["source_reported_precision_values"] == dict(
            voted=values["voted_native_confidence"], registered=values["registered_native_confidence"]),
            "Native confidence scalar changed")
        require(record["interpreted_workbook_interval"] is None and record["standard_error"] is None,
            "Workbook confidence scalar interpreted without support")
        anchor = record["published_national_citizen_interval"]
        if citizen and source["geography"] == "UNITED STATES":
            evidence = methods["evidence"]["citizen_national_report_anchor"]
            require(anchor == dict(confidence_level=90, voted=evidence["voted_printed_ci"],
                registered=evidence["registered_printed_ci"], source=evidence["source"],
                page=evidence["page"], derived=False), "Direct national printed interval differs")
        else:
            require(anchor is None, "National interval mapping allocated to another source row")
        for flag in ("weighted_population_is_sample_size", "race_categories_harmonized",
                "administrative_turnout", "individual_history", "local_allocation"):
            require(record[flag] is False, "Unsupported point claim")
        total = citizen or source["native_label"] == ".Total"
        reference = lookup.get((2002, code, frame)) if total else None
        disposition = ("not_overall_native_query" if not total else
            "no_national_retrospective_state_frame" if code is None else
            "held_native_selection" if not selected else
            "no_qualified_retrospective_frame" if not reference
                or not reference["reported_voted_pct"] or not reference["reported_registered_pct"] else
            "reported_same_frame_percentage_comparison")
        require(reconciliation["disposition"] == disposition and reconciliation["reference"] == reference
            and reconciliation["source_counts_repaired"] is False, "Source reconciliation scope differs")
        if disposition == "reported_same_frame_percentage_comparison":
            check_difference(reconciliation["voted_difference_pp"], values["voted_pct"], reference["reported_voted_pct"])
            check_difference(reconciliation["registered_difference_pp"], values["registered_pct"], reference["reported_registered_pct"])
        else:
            require(reconciliation["voted_difference_pp"] is None
                and reconciliation["registered_difference_pp"] is None, "Unsupported source difference")
        point_rows.append(dict(source_key=source_key, geography=source["geography"],
            native_group=source["native_label"], native_table_role=source["role"],
            population_frame=frame, decision=expected_decision,
            selected_voted_pct=values["voted_pct"] if selected else None,
            selected_registered_pct=values["registered_pct"] if selected else None,
            **values, flags=json.dumps(source["native_flags"], separators=(",", ":"))))
        if not citizen:
            continue
        for year in (2018, 2022):
            comparison = comparisons[comparison_index]
            comparison_index += 1
            endpoint = lookup.get((year, code, "cvap"))
            disposition = ("held_2002_native_selection" if not selected else
                "no_national_retrospective_state_frame" if code is None else
                "held_missing_same_frame_endpoint" if not endpoint
                    or not endpoint["reported_voted_pct"] or not endpoint["reported_registered_pct"] else
                "same_type_reported_snapshot_difference_not_cohort")
            require(comparison["source_key"] == source_key and comparison["geography"] == source["geography"]
                and comparison["reference_state_code"] == code and comparison["from_year"] == 2002
                and comparison["to_year"] == year and comparison["population_frame"] == "cvap"
                and comparison["election_type"] == "midterm" and comparison["endpoint"] == endpoint
                and comparison["disposition"] == disposition, "Wrong frame, year or complete endpoint")
            if disposition == "same_type_reported_snapshot_difference_not_cohort":
                check_difference(comparison["reported_voted_difference_pp"], endpoint["reported_voted_pct"], values["voted_pct"])
                check_difference(comparison["reported_registered_difference_pp"], endpoint["reported_registered_pct"], values["registered_pct"])
            else:
                require(comparison["reported_voted_difference_pp"] is None
                    and comparison["reported_registered_difference_pp"] is None, "Held endpoint promoted")
            for field in ("change_interval", "statistical_significance", "individual_retention", "population_count"):
                require(comparison[field] is None, "Invented uncertainty, cohort or population")
            require(comparison["definitions_harmonized"] is False
                and comparison["local_allocation"] is False, "Unsupported snapshot claim")
    require(len(set(keys)) == len(keys), "Duplicate native source key")
    for name, expected_rows in (
            ("complete-point-decisions.csv", point_rows),
            ("complete-source-reconciliation.csv", [
                {key: value for key, value in row.items() if key != "reference"} for row in reconciliations]),
            ("complete-midterm-snapshot-comparisons.csv", [
                {key: value for key, value in row.items() if key != "endpoint"} for row in comparisons])):
        with (output / name).open(newline="") as stream:
            actual_rows = list(csv.DictReader(stream))
        require(len(actual_rows) == len(expected_rows), "Incomplete full query export")
        for actual, expected in zip(actual_rows, expected_rows):
            require(actual == {key: scalar(value) for key, value in expected.items()}, "Full query field differs")
    summary = result["summary"]
    require(summary == json.loads((output / "summary.json").read_bytes()), "Summary export differs")
    require(summary["point_decisions"] == dict(Counter(row["decision"] for row in records))
        and summary["reconciliation_decisions"] == dict(Counter(row["disposition"] for row in reconciliations))
        and summary["snapshot_decisions"] == dict(Counter(row["disposition"] for row in comparisons)),
        "Summary dispositions differ")
    require(summary["native_rows"] == 832 and summary["metric_cells"] == 8320
        and summary["selected_reported_point_rows"] == 693 and summary["flagged_native_rows"] == 6
        and summary["selected_distinct_geography_frame_group_cells"] == len({
            (row["native"]["geography"], row["population_frame"],
                "overall" if row["native"]["role"] == "citizen_overall" else row["native"]["native_label"])
            for row in records if row["decision"] == "selected_reported_point_only"}) == 642
        and summary["selected_non_total_group_rows"] == sum(
            row["decision"] == "selected_reported_point_only"
            and row["native"]["role"] != "citizen_overall" and row["native"]["native_label"] != ".Total"
            for row in records) == 540
        and summary["full_reconciliation_rows"] == 832 and summary["full_snapshot_rows"] == 104
        and summary["new_intervals"] == summary["new_standard_errors"] == summary["new_population_or_2026_estimates"] == 0
        and summary["native_precision_mapping_qualified"] is False
        and summary["frontend_activation"] is False, "Incomplete or promoted numerical summary")
    return dict(status="passed_independent_cps_2002_point_selection", checks=checks,
        selected_reported_point_rows=693, complete_native_rows=832, native_metric_cells=8320,
        native_defects_preserved=6, suppressed_or_missing_rows_preserved=131,
        conflicting_pennsylvania_totals_preserved=3, complete_midterm_snapshot_decisions=104,
        workbook_precision_mapping_qualified=False, new_intervals=0, frontend_activation=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.inputs, args.output)
    with args.proof.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
