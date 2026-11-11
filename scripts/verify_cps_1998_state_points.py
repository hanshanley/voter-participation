"""Independently verify every new native cell, query and source-snapshot difference."""

import argparse
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile


def verify(inputs, output):
    checks = 0

    def check(value):
        nonlocal checks
        checks += 1
        if not value:
            raise ValueError(f"Independent CPS1998 verification failed at check{checks}")

    def number(value):
        if not value or any(char not in "0123456789,." for char in value) or value.count(".") > 1:
            return None
        try:
            return Fraction(value.replace(",", ""))
        except ValueError:
            return None

    def rate(value):
        value = number(value)
        return value if value is not None and 0 <= value <= 100 else None

    def same(value, expected):
        return value is None if expected is None else value is not None and Fraction(str(value)) == expected

    names = ("adults_thousands", "citizen_adults_thousands", "citizen_adults_pct",
        "citizen_adults_printed_se_pp", "registered_thousands", "registered_pct",
        "registered_printed_se_pp", "voted_thousands", "voted_pct", "voted_printed_se_pp")
    labels = ("N-H White", "N-H Black", "N-H API", "Hispanic", "Female", "Total", "Male", "White", "Black")
    mapping = {"Total": ".Total", "Male": ".Male", "Female": ".Female",
        "N-H White": ".Non-Hispanic White", "N-H Black": ".Non-Hispanic Black",
        "Hispanic": ".Hispanic (of any race)", "White": ".White", "Black": ".Black"}
    original = (inputs / "1998-tab04.txt").read_bytes()
    check(hashlib.sha256(original).hexdigest() == "bc998b4ac2db5c65b2aa55839df907c70d599eddeca0f988500ef80339095833")
    check(hashlib.sha256((inputs / "predecessor-science.zip").read_bytes()).hexdigest()
        == "4d651c36c02a8dd5b413897deccad01d8b2ee05f1f08b9ce2cd068b167858a8b")
    native, state = [], None
    for ordinal, line in enumerate(original.decode("ascii").splitlines(), 1):
        parts = line.rsplit(None, 10)
        if len(parts) != 11 or any(char.isalpha() for cell in parts[1:] for char in cell.replace("(B)", "")):
            continue
        head = parts[0].strip()
        label = next((label for label in labels if head == label or head.endswith(" " + label)), None)
        if label is None:
            continue
        prefix = head[:-len(label)].strip()
        state = prefix or state
        native.append(dict(line=ordinal, geography=state, label=label, values=dict(zip(names, parts[1:]))))
    result = json.loads((output / "complete-result.json").read_bytes())
    with zipfile.ZipFile(inputs / "predecessor-science.zip") as archive:
        old_result = json.loads(archive.read("results/complete-result.json"))
        with zipfile.ZipFile(io.BytesIO(archive.read("inputs/baseline-science.zip"))) as baseline:
            history = list(csv.DictReader(io.StringIO(
                baseline.read("complete-state-year-population-pairs.csv").decode())))
    old = {(row["native"]["geography"], row["native"]["native_label"]): row
        for row in old_result["records"] if row["native"]["role"] == "sex_race"}
    historic = {(int(row["year"]), row["reference_state_code"], row["population_frame"]): row
        for row in history}
    codes = {row["native_state_name"].upper(): row["reference_state_code"] for row in history}
    codes["UNITED STATES"] = "US"
    check(len(native) == len(result["records"]) == 468)
    check({(row["geography"], row["label"]) for row in native} == {(s, g) for s in codes for g in labels})
    check(len(result["metric_decisions"]) == 1404)
    check(len(result["group_snapshot_comparisons"]) == 936)
    check(len(result["retrospective_reconciliations"]) == 104)
    check(len(result["overall_snapshot_comparisons"]) == 208)
    metrics = {(row["source_key"], row["measure"]): row for row in result["metric_decisions"]}
    grouped = {(row["source_key"], row["measure"]): row for row in result["group_snapshot_comparisons"]}
    recon = {(row["source_key"], row["measure"]): row for row in result["retrospective_reconciliations"]}
    later = {(row["source_key"], row["measure"], row["to_year"]): row for row in result["overall_snapshot_comparisons"]}
    for source, record in zip(native, result["records"]):
        key = f"1998-tab04.txt:{source['line']}"
        check(record["source_key"] == key and record["source_line"] == source["line"])
        check(record["geography"] == source["geography"] and record["native_group"] == source["label"])
        check(record["reference_state_code"] == codes[source["geography"]])
        for field in names:
            check(record["raw_values"][field] == source["values"][field])
        for field in ("sample_n", "citizen_turnout", "individual_history", "eligibility", "deaths", "migration"):
            check(record[field] is None)
        check(record["population_frame"] == "vap" and record["year"] == 1998)
        check(record["race_categories_harmonized"] is record["local_allocation"] is False)
        expected_symbols = {name: raw for name, raw in source["values"].items()
            if name.endswith("_thousands") and number(raw) is None}
        check(record["count_symbols"] == expected_symbols)
        for metric in ("citizen_adults", "registered", "voted"):
            raw, error = source["values"][metric + "_pct"], source["values"][metric + "_printed_se_pp"]
            point, se = rate(raw), rate(error)
            measure = record["measures"][metric]
            row = metrics[key, metric]
            check(measure["raw_percentage"] == row["raw_percentage"] == raw)
            check(measure["raw_standard_error"] == row["raw_standard_error"] == error)
            check(same(measure["selected_percentage"], point) and same(row["selected_percentage"], point))
            check(same(measure["selected_source_standard_error_pp"], se if point is not None else None))
            check(measure["selected_source_standard_error_pp"] == row["selected_source_standard_error_pp"])
            expected = ("withheld_native_small_base" if raw == "(B)" else
                "withheld_invalid_native_percentage" if point is None else "selected_reported_native_point")
            check(row["disposition"] == measure["disposition"] == expected)
            expected = ("not_selected_without_point" if point is None else
                "withheld_native_standard_error" if error == "(B)" else
                "withheld_invalid_native_standard_error" if se is None else "source_printed_standard_error")
            check(measure["standard_error_disposition"] == row["standard_error_disposition"] == expected)
            check(measure["derived_interval"] is row["derived_interval"] is None)
            check(row["population_frame"] == "vap")
            if metric == "citizen_adults":
                check(row["measure_meaning"] == "citizenship_share_not_turnout")
                continue
            comparison = grouped[key, metric]
            target = old.get((source["geography"], mapping.get(source["label"])))
            endpoint = target["selected_" + metric + "_pct"] if target else None
            expected = ("held_non_hispanic_API_not_all_API" if target is None else
                "held_1998_metric" if point is None else "held_2002_source_selection"
                if endpoint is None else "same_label_source_snapshot_not_harmonized_cohort")
            check(comparison["disposition"] == expected)
            check(comparison["native_2002_group"] == mapping.get(source["label"]))
            check(comparison["to_percentage"] == endpoint)
            check(same(comparison["from_percentage"], point))
            difference = Fraction(str(endpoint)) - point if expected == "same_label_source_snapshot_not_harmonized_cohort" else None
            check(same(comparison["difference_pp"], difference))
            check(comparison["source_1998_standard_error"] == row["selected_source_standard_error_pp"])
            check(comparison["source_2002_precision_scalar"] ==
                (target["source_reported_precision_values"][metric] if target else None))
            for name in ("change_interval", "significance", "individual_retention", "observed_staying_home"):
                check(comparison[name] is None)
            check(comparison["definitions_harmonized"] is comparison["local_allocation"] is False)
            if source["label"] != "Total":
                continue
            historical = historic.get((1998, codes[source["geography"]], "vap"))
            value = historical["reported_" + metric + "_pct"] if historical else None
            row = recon[key, metric]
            check(row["retrospective_percentage"] == value)
            check(same(row["retrospective_minus_original_pp"], Fraction(value) - point if value and point is not None else None))
            check(row["source_repaired"] is False)
            for year in (2018, 2022):
                row = later[key, metric, year]
                endpoint = historic.get((year, codes[source["geography"]], "vap"))
                value = endpoint["reported_" + metric + "_pct"] if endpoint else None
                check(row["to_percentage"] == value)
                check(same(row["difference_pp"], Fraction(value) - point if value and point is not None else None))
                check(row["population_frame"] == "vap" and row["election_type"] == "midterm")
                for name in ("change_interval", "significance", "individual_retention", "eligibility", "deaths", "migration"):
                    check(row[name] is None)
                check(row["definitions_harmonized"] is row["local_allocation"] is False)
    for name in ("metric_decisions", "group_snapshot_comparisons", "retrospective_reconciliations",
            "overall_snapshot_comparisons"):
        rows = result[name]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        check((output / ("complete-" + name.replace("_", "-") + ".csv")).read_bytes() == stream.getvalue().encode())
    check(json.loads((output / "summary.json").read_bytes()) == result["summary"])
    check(result["summary"]["metric_decisions"] == dict(
        selected_reported_native_point=1060, withheld_invalid_native_percentage=1, withheld_native_small_base=343))
    check(result["summary"]["literal_dot_count_cells"] == 32)
    check(result["summary"]["literal_zero_count_cells"] == 14)
    check(result["summary"]["source_numeric_zero_standard_errors"] == 10)
    provenance = json.loads((inputs / "provenance.json").read_bytes())
    check(provenance["source"]["status"] == provenance["independent_native_directory"]["status"] == 200)
    check(provenance["blocked_landing_page"]["status"] == 403)
    check(provenance["blocked_landing_page_retried"] is provenance["alternate_client_cache_or_mirror"] is False)
    return dict(status="passed_independent_cps_1998_native_state_points", checks=checks,
        native_rows=468, native_metric_cells=4680, metric_decisions=1404,
        group_snapshot_decisions=936, retrospective_decisions=104, later_overall_decisions=208,
        source_defects_and_suppression_preserved=True, native_SEs_not_new_CIs=True,
        non_hispanic_API_not_all_API=True, no_citizen_turnout_or_individual_history_inferred=True,
        every_complete_query_byte_checked=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "output", "proof"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.inputs, args.output)
    args.proof.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
