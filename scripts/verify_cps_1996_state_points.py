"""Independently verify fixed-column/CSV native cells and all 1996 query arithmetic."""

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import zipfile


AB = ("population_thousands", "registered_thousands", "registered_pct", "voted_thousands",
      "voted_pct", "source_nonvote_total_thousands", "registered_within_source_nonvote_thousands",
      "not_registered_within_source_nonvote_thousands", "noncitizen_within_source_nonvote_thousands",
      "unknown_registration_thousands")
C = ("population_thousands", "not_registered_thousands", "registered_thousands",
     "unknown_registration_thousands", "not_registered_pct", "registered_pct", "unknown_registration_pct",
     "not_voted_thousands", "voted_thousands", "unknown_voting_thousands", "not_voted_pct",
     "voted_pct", "unknown_voting_pct")
CM = ("not_registered", "registered", "unknown_registration", "not_voted", "voted", "unknown_voting")
AGE = {"TOTAL AGE 18 AND OVER.": "18_plus", "18 TO 24 YEARS . . . .": "18_24",
       "25 TO 44 YEARS . . . .": "25_44", "45 TO 64 YEARS . . . .": "45_64",
       "65 YEARS AND OVER. . .": "65_plus"}


def verify(inputs, output):
    checks = 0

    def require(condition):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(f"Independent 1996 check {checks} failed")

    def unpack(body):
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for name, expected in manifest["files"].items():
                value = archive.read(name)
                require(dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest()) == expected)
            return {name: archive.read(name) for name in manifest["files"]}

    frozen = json.loads((inputs / "manifest.json").read_bytes())
    for name, expected in frozen.items():
        require(Path(name).name == name)
        body = (inputs / name).read_bytes()
        require(dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) == expected)
    parent = unpack((inputs / "accepted-1998-science.zip").read_bytes())
    previous = json.loads(parent["results/complete-result.json"])
    codes = {row["geography"]: row["reference_state_code"] for row in previous["records"]}
    codes["TOTAL"] = codes.pop("UNITED STATES")
    require(len(codes) == 52)
    earlier = unpack(parent["inputs/predecessor-science.zip"])
    with zipfile.ZipFile(io.BytesIO(earlier["inputs/baseline-science.zip"])) as archive:
        history = list(csv.DictReader(io.StringIO(
            archive.read("complete-state-year-population-pairs.csv").decode())))
    baseline = {(int(row["year"]), row["reference_state_code"], row["population_frame"]): row for row in history}
    old = {(row["reference_state_code"], row["native_group"]): row for row in previous["records"]}
    native = {}
    for table, groups in (("A", ("ALL RACES", "WHITE", "BLACK", "HISPANIC ORIGIN")),
                          ("B", ("BOTH SEXES", "MALE", "FEMALE"))):
        geography, group = None, None
        for line_number, line in enumerate((inputs / f"tab4{table.lower()}.txt").read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped in codes:
                geography = codes[stripped]
            elif stripped in groups:
                group = stripped
            elif line[:22] in AGE:
                require(geography is not None and group is not None and len(line) == 124)
                boundaries = (22, 32, 42, 52, 62, 72, 82, 93, 103, 113, 124)
                fields = [line[start:end].strip() for start, end in zip(boundaries, boundaries[1:])]
                native[f"tab4{table.lower()}.txt:{line_number}"] = (
                    table, geography, group, AGE[line[:22]], dict(zip(AB, fields)))
    citizen_lines = list(csv.reader(io.StringIO((inputs / "tab4c.txt").read_text()), delimiter="|"))
    state = None
    for line_number, cells in enumerate(citizen_lines, 1):
        parts = [value.strip() for value in cells[1:-1]]
        if len(parts) == 14 and parts[0] == "ALL":
            native[f"tab4c.txt:{line_number}"] = ("C", "US", "ALL", "18_plus", dict(zip(C, parts[1:])))
        elif len(parts) == 15 and parts[1] in ("Male", "Female"):
            if parts[0]:
                label = parts[0].upper()
                if label not in codes:
                    suffix = citizen_lines[line_number][1].strip().upper()
                    label = label + " " + suffix
                state = codes[label]
            require(state is not None)
            native[f"tab4c.txt:{line_number}"] = ("C", state, parts[1], "18_plus", dict(zip(C, parts[2:])))
    require(Counter(value[0] for value in native.values()) == {"A": 1040, "B": 780, "C": 103})
    result = json.loads((output / "complete-result.json").read_bytes())
    require(result["policy"] == json.loads((inputs / "policy.json").read_bytes()))
    require(len(result["records"]) == len(native) == 1923)
    records = {row["source_key"]: row for row in result["records"]}
    require(records.keys() == native.keys())
    by_group = {(value[0], value[1], value[2], value[3]): key for key, value in native.items()}
    metric_keys = set()
    dispositions = Counter()
    for key, (table, code, group, age, values) in native.items():
        row = records[key]
        for name, expected in (("table", table), ("reference_state_code", code), ("native_group", group),
                               ("age", age), ("population_frame", "cvap" if table == "C" else "vap")):
            require(row[name] == expected)
        require(row["raw_values"].keys() == values.keys())
        for field, literal in values.items():
            require(row["raw_values"][field] == literal)
        require(row["count_unit"] == "rounded_thousands_not_sample_N" and row["local_allocation"] is False)
        require(all(row[name] is None for name in ("eligibility", "deaths", "migration", "individual_history")))
        require(row["duplicate_total"] == (table == "B" and group == "BOTH SEXES"))
        for metric in CM if table == "C" else ("registered", "voted"):
            raw, measure = values[metric + "_pct"], row["measures"][metric]
            selected = raw if raw != "(B)" and Decimal(values["population_thousands"]) > 0 else None
            status = ("withheld_native_B" if raw == "(B)" else "withheld_rounded_zero_base"
                      if Decimal(values["population_thousands"]) == 0 else "selected_native_percentage")
            require(measure["selected_percentage"] == selected and measure["raw_percentage"] == raw)
            require(measure["disposition"] == status)
            require(all(measure[name] is None for name in ("standard_error", "confidence_interval", "sample_n")))
            metric_keys.add((key, metric))
            dispositions[status] += 1
    actual_metrics = {(row["source_key"], row["measure"]): row for row in result["metric_decisions"]
                      if row["source_key"] is not None}
    require(actual_metrics.keys() == metric_keys)
    for (key, metric), row in actual_metrics.items():
        require(all(row[name] == value for name, value in records[key]["measures"][metric].items()))
        require(row["reference_state_code"] == records[key]["reference_state_code"]
                and row["population_frame"] == records[key]["population_frame"])
    missing = [row for row in result["metric_decisions"] if row["source_key"] is None]
    expected_missing = {(code, group, metric) for code in codes.values() for group in ("ALL", "Male", "Female")
                        for metric in CM if ("C", code, group, "18_plus") not in by_group}
    require(len(missing) == len(expected_missing) == 318)
    require({(row["reference_state_code"], row["native_group"], row["measure"]) for row in missing} == expected_missing)
    require(all(row["selected_percentage"] is None and
                row["disposition"] == "not_printed_citizen_geography_gender_cell" for row in missing))
    require(len(result["metric_decisions"]) == 4576)
    require(len(result["duplicate_total_checks"]) == 2600)
    require({(row["source_key"], row["field"]) for row in result["duplicate_total_checks"]} ==
            {(key, field) for key, value in native.items() if value[0] == "B" and value[2] == "BOTH SEXES"
             for field in AB})
    for row in result["duplicate_total_checks"]:
        table, code, group, age, values = native[row["source_key"]]
        target = by_group["A", code, "ALL RACES", age]
        require(table == "B" and group == "BOTH SEXES" and row["other_source_key"] == target)
        require(row["first_raw"] == values[row["field"]] == row["other_raw"] == native[target][4][row["field"]])
        require(row["literal_equal"] and row["summed"] is False and row["independent_observations"] is False)
    require(len(result["cross_frame_count_references"]) == 309)
    require({(row["source_key"], row["field"]) for row in result["cross_frame_count_references"]} ==
            {(key, field) for key, value in native.items() if value[0] == "C"
             for field in ("population_thousands", "registered_thousands", "voted_thousands")})
    for row in result["cross_frame_count_references"]:
        _, code, group, _, values = native[row["source_key"]]
        other = by_group[("A", "US", "ALL RACES", "18_plus") if code == "US" else ("B", code, group.upper(), "18_plus")]
        reference = Decimal(native[other][4][row["field"]])
        if row["field"] == "population_thousands":
            reference -= Decimal(native[other][4]["noncitizen_within_source_nonvote_thousands"])
        require(row["other_source_key"] == other and row["citizen_raw"] == values[row["field"]])
        require(Decimal(row["adult_reference_thousands"]) == reference)
        require(Decimal(row["citizen_minus_reference_thousands"]) == Decimal(values[row["field"]]) - reference)
        require(row["rates_across_denominators_compared"] is False and row["source_repaired"] is False)
    require(len(result["nonresponse_scenarios"]) == 206)
    require({(row["source_key"], row["measure"]) for row in result["nonresponse_scenarios"]} ==
            {(key, metric) for key, value in native.items() if value[0] == "C" for metric in ("registered", "voted")})
    for row in result["nonresponse_scenarios"]:
        values = native[row["source_key"]][4]
        metric = row["measure"]
        no, unknown = ("not_voted", "unknown_voting") if metric == "voted" else ("not_registered", "unknown_registration")
        base, yes, no_count, missing_count = [Decimal(values[name + "_thousands"])
                                            for name in ("population", metric, no, unknown)]
        require(Decimal(row["reported_no_thousands"]) == no_count and Decimal(row["reported_unknown_thousands"]) == missing_count)
        require(Decimal(row["rounding_residual_thousands"]) == base - yes - no_count - missing_count)
        require(Decimal(row["all_unknown_no_pct"]) == 100 * yes / base)
        require(Decimal(row["all_unknown_yes_pct"]) == 100 * (yes + missing_count) / base)
        require(row["unknown_assigned_to_observed_nonvoters"] is False and row["residual_assigned"] is False
                and row["confidence_interval"] is None)
    bridge = {"ALL RACES": "Total", "WHITE": "White", "BLACK": "Black", "HISPANIC ORIGIN": "Hispanic",
              "MALE": "Male", "FEMALE": "Female"}
    require(len(result["group_snapshot_comparisons"]) == 624)
    require({(row["source_key"], row["measure"]) for row in result["group_snapshot_comparisons"]} ==
            {(key, metric) for key, value in native.items() if value[0] != "C" and value[2] in bridge
             and value[3] == "18_plus" for metric in ("registered", "voted")})
    for row in result["group_snapshot_comparisons"]:
        source = records[row["source_key"]]
        target = old[source["reference_state_code"], bridge[source["native_group"]]]
        first = source["measures"][row["measure"]]["selected_percentage"]
        last = target["measures"][row["measure"]]["selected_percentage"]
        require(row["endpoint_source_key"] == target["source_key"] and row["endpoint_native_group"] == target["native_group"])
        require(row["from_percentage"] == first and row["to_percentage"] == last)
        require(row["difference_pp"] == (format(Decimal(last) - Decimal(first), "f")
                if first is not None and last is not None else None))
        require(row["same_election_type"] is False and row["from_year"] == 1996 and row["to_year"] == 1998)
        require(row["confidence_interval"] is None and row["harmonized_cohort"] is False)
    require(len(result["retrospective_reconciliations"]) == 104)
    overall_keys = {(key, metric) for key, value in native.items() if value[:1] == ("A",)
                    and value[2:4] == ("ALL RACES", "18_plus") for metric in ("registered", "voted")}
    require({(row["source_key"], row["measure"]) for row in result["retrospective_reconciliations"]} == overall_keys)
    for row in result["retrospective_reconciliations"]:
        target = baseline.get((1996, row["reference_state_code"], "vap"))
        value = target["reported_" + row["measure"] + "_pct"] if target else None
        point = records[row["source_key"]]["measures"][row["measure"]]["selected_percentage"]
        require(row["original_percentage"] == point and row["retrospective_percentage"] == value)
        require(row["retrospective_minus_original_pp"] ==
                (format(Decimal(value) - Decimal(point), "f") if value is not None and point is not None else None))
        require(row["source_repaired"] is False)
    require(len(result["overall_snapshot_comparisons"]) == 728)
    require({(row["source_key"], row["measure"], row["to_year"]) for row in result["overall_snapshot_comparisons"]} ==
            {(key, metric, year) for key, metric in overall_keys for year in (2000, 2004, 2008, 2012, 2016, 2020, 2024)})
    for row in result["overall_snapshot_comparisons"]:
        target = baseline.get((row["to_year"], row["reference_state_code"], "vap"))
        endpoint = target["reported_" + row["measure"] + "_pct"] if target else None
        point = records[row["source_key"]]["measures"][row["measure"]]["selected_percentage"]
        require(row["to_year"] in (2000, 2004, 2008, 2012, 2016, 2020, 2024))
        require(row["from_percentage"] == point and row["to_percentage"] == endpoint)
        require(row["difference_pp"] == (format(Decimal(endpoint) - Decimal(point), "f")
                if point is not None and endpoint is not None else None))
        require(row["population_frame"] == "vap" and row["election_type"] == "presidential"
                and row["significance"] is None and row["harmonized_cohort"] is False)
    summary = result["summary"]
    require(summary["native_cells"] == 19539 and summary["native_rows"] == 1923)
    require(summary["dispositions"] == dict(dispositions, not_printed_citizen_geography_gender_cell=318))
    exports = {name: result[name] for name in ("metric_decisions", "duplicate_total_checks",
        "cross_frame_count_references", "nonresponse_scenarios", "group_snapshot_comparisons",
        "retrospective_reconciliations", "overall_snapshot_comparisons")}
    exports["native_cells"] = [dict(source_key=key, reference_state_code=code, table=table, native_group=group,
        age=age, population_frame="cvap" if table == "C" else "vap", field=field, raw_value=values[field])
        for key, (table, code, group, age, values) in native.items() for field in sorted(values)]
    for name, rows in exports.items():
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        require((output / ("complete-" + name.replace("_", "-") + ".csv")).read_bytes() == stream.getvalue().encode())
    require(json.loads((output / "summary.json").read_bytes()) == summary)
    return dict(status="passed_independent_1996_native_and_complete_query_checks", checks=checks,
                native_rows=1923, native_metric_cells=19539, fixed_column_AB_and_csv_C=True,
                same_type_overall_decisions=728, full_query_exports=8, source_repairs=0,
                confidence_intervals_created=0, frontend_activation=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.inputs, args.results), sort_keys=True))


if __name__ == "__main__":
    main()
