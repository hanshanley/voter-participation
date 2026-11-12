"""Preserve native 1996 CPS participation cells, frames and complete comparisons."""

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


PINS = {
    "tab4a.txt": "da7bb07383701ea3c1bd49ad917ac494c70bf83fd172047a927cbc5b70610d0a",
    "tab4b.txt": "66c0f2068338464f74f210ea96ecc4019d44347e6e0aa90c27401cd779f38d1f",
    "tab4c.txt": "957569808ecbc66c8f71ac33ddb9561c604e0c4193c1b206d7af91406f8e518d",
    "accepted-1998-science.zip": "c94bc51267849010ea393af44cb2dd3da7a507e86f45d8dfdd796033c8939a8b",
    "policy.json": "1df8201f4ecbe470814319fde6aef786ad45329c400372883c3a6ef73a8c10f4",
}
AB_FIELDS = (
    "population_thousands", "registered_thousands", "registered_pct",
    "voted_thousands", "voted_pct", "source_nonvote_total_thousands",
    "registered_within_source_nonvote_thousands", "not_registered_within_source_nonvote_thousands",
    "noncitizen_within_source_nonvote_thousands", "unknown_registration_thousands",
)
C_FIELDS = (
    "population_thousands", "not_registered_thousands", "registered_thousands",
    "unknown_registration_thousands", "not_registered_pct", "registered_pct",
    "unknown_registration_pct", "not_voted_thousands", "voted_thousands",
    "unknown_voting_thousands", "not_voted_pct", "voted_pct", "unknown_voting_pct",
)
AGES = {
    "TOTAL AGE 18 AND OVER.": "18_plus", "18 TO 24 YEARS . . . .": "18_24",
    "25 TO 44 YEARS . . . .": "25_44", "45 TO 64 YEARS . . . .": "45_64",
    "65 YEARS AND OVER. . .": "65_plus",
}
GROUPS = {"A": ("ALL RACES", "WHITE", "BLACK", "HISPANIC ORIGIN"),
          "B": ("BOTH SEXES", "MALE", "FEMALE"), "C": ("ALL", "Male", "Female")}
METRICS = ("registered", "voted")
C_METRICS = ("not_registered", "registered", "unknown_registration",
             "not_voted", "voted", "unknown_voting")
BRIDGE = {"ALL RACES": "Total", "WHITE": "White", "BLACK": "Black",
          "HISPANIC ORIGIN": "Hispanic", "MALE": "Male", "FEMALE": "Female"}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def number(raw):
    return Decimal(raw) if re.fullmatch(r"\d+(?:\.\d+)?", raw) else None


def text(value):
    return None if value is None else format(value, "f")


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sorted(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def archive_members(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, expected in manifest["files"].items():
            if pin(archive.read(name)) != expected:
                raise ValueError("Changed accepted predecessor member")
        return {name: archive.read(name) for name in manifest["files"]}


def load_inputs(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, expected in manifest.items():
        if Path(name).name != name or pin((root / name).read_bytes()) != expected:
            raise ValueError("Changed or unsafe frozen input")
    for name, expected in PINS.items():
        if pin((root / name).read_bytes())["sha256"] != expected:
            raise ValueError("Changed pinned native input or policy")
    parent = archive_members((root / "accepted-1998-science.zip").read_bytes())
    earlier = archive_members(parent["inputs/predecessor-science.zip"])
    with zipfile.ZipFile(io.BytesIO(earlier["inputs/baseline-science.zip"])) as archive:
        for name, expected in json.loads(archive.read("checksums.json")).items():
            if pin(archive.read(name)) != expected:
                raise ValueError("Changed accepted historical pair")
        history = list(csv.DictReader(io.StringIO(
            archive.read("complete-state-year-population-pairs.csv").decode())))
    sources = {table: (root / ("tab4" + table.lower() + ".txt")).read_text(encoding="ascii")
               for table in GROUPS}
    return sources, json.loads(parent["results/complete-result.json"]), history, json.loads(
        (root / "policy.json").read_bytes())


def select(raw, base):
    value = number(raw)
    status = ("withheld_native_B" if raw == "(B)" else
              "withheld_invalid_native_percentage" if value is None or value > 100 else
              "withheld_rounded_zero_base" if number(base) == 0 else
              "withheld_invalid_native_base" if number(base) is None else "selected_native_percentage")
    return dict(raw_percentage=raw, selected_percentage=text(value) if status == "selected_native_percentage"
                else None, disposition=status, standard_error=None, confidence_interval=None, sample_n=None)


def record(table, line, geography, code, group, age, values):
    return dict(source_key=f"tab4{table.lower()}.txt:{line}", source_line=line,
                table=table, geography=geography, reference_state_code=code, native_group=group,
                age=age, year=1996, election_type="presidential",
                population_frame="cvap" if table == "C" else "vap", raw_values=values,
                measures={metric: select(values[metric + "_pct"], values["population_thousands"])
                          for metric in (C_METRICS if table == "C" else METRICS)},
                duplicate_total=table == "B" and group == "BOTH SEXES",
                count_unit="rounded_thousands_not_sample_N", eligibility=None, deaths=None,
                migration=None, individual_history=None, local_allocation=False)


def parse_ab(source, table, codes):
    if (f"TABLE 4{table}." not in source or "NOVEMBER 1996" not in source
            or "August 17, 1998" not in source or "REPORTED VOTED" not in source):
        raise ValueError("Changed native title or release")
    result, current, group, seen = [], None, None, set()
    for ordinal, line in enumerate(source.splitlines(), 1):
        label = line.strip()
        if label == "TOTAL" or label in codes:
            geography = "TOTAL" if label == "TOTAL" else label
            if current != geography:
                group = None
            current = geography
        elif label in GROUPS[table]:
            group = label
        else:
            match = re.fullmatch(r"(.*?)(?: {2,})([0-9(].*)", line)
            if not match:
                continue
            age, tokens = match[1].strip(), match[2].split()
            key = (current, group, age)
            if (current is None or group is None or age not in AGES or len(tokens) != 10
                    or key in seen or any(number(value) is None and value != "(B)" for value in tokens)):
                raise ValueError("Unqualified or duplicate native age row")
            seen.add(key)
            result.append(record(table, ordinal, current, "US" if current == "TOTAL" else codes[current],
                                 group, AGES[age], dict(zip(AB_FIELDS, tokens))))
    expected = {(geography, group, age) for geography in ("TOTAL", *codes)
                for group in GROUPS[table] for age in AGES}
    if seen != expected:
        raise ValueError("Incomplete native state/group/age inventory")
    return result


def parse_c(source, codes):
    if ("Among Citizens, by Gender" not in source or "November 1996.  Numbers in thousands" not in source
            or "August 17, 1998" not in source or "Did not " not in source):
        raise ValueError("Changed citizen source definition")
    result, current, seen = [], None, set()
    lines = source.splitlines()
    for ordinal, line in enumerate(lines, 1):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if not cells or number(cells[-1]) is None:
            continue
        if cells[0] == "ALL":
            geography, code, group, tokens = "TOTAL", "US", "ALL", cells[1:]
        else:
            if len(cells) != 15 or cells[1] not in ("Male", "Female"):
                raise ValueError("Changed citizen row layout")
            if cells[0]:
                current = cells[0].upper()
                if current not in codes and ordinal < len(lines):
                    continuation = lines[ordinal].split("|")
                    if len(continuation) > 2:
                        current += " " + continuation[1].strip().upper()
            if current not in codes:
                raise ValueError("Unknown citizen state")
            geography, code, group, tokens = current, codes[current], cells[1], cells[2:]
        key = (code, group)
        if len(tokens) != 13 or key in seen or any(number(value) is None for value in tokens):
            raise ValueError("Unqualified or duplicate citizen cells")
        seen.add(key)
        result.append(record("C", ordinal, geography, code, group, "18_plus", dict(zip(C_FIELDS, tokens))))
    if seen != {("US", "ALL")} | {(code, group) for code in codes.values() for group in ("Male", "Female")}:
        raise ValueError("Incomplete printed citizen inventory")
    return result


def build(sources, previous, history, policy):
    if pin(encoded(policy))["sha256"] != PINS["policy.json"]:
        raise ValueError("Unqualified selection policy")
    codes = {row["native_state_name"].upper(): row["reference_state_code"] for row in history}
    if len(codes) != 51:
        raise ValueError("Incomplete accepted geography roster")
    records = parse_ab(sources["A"], "A", codes) + parse_ab(sources["B"], "B", codes) + parse_c(sources["C"], codes)
    lookup = {(row["table"], row["reference_state_code"], row["native_group"], row["age"]): row for row in records}
    metrics, duplicate_checks, cross_frames, scenarios = [], [], [], []
    for row in records:
        for metric, measure in row["measures"].items():
            metrics.append(dict(source_key=row["source_key"], reference_state_code=row["reference_state_code"],
                table=row["table"], native_group=row["native_group"], age=row["age"],
                population_frame=row["population_frame"], measure=metric,
                duplicate_total_not_independent=row["duplicate_total"], **measure))
        if row["table"] == "B" and row["native_group"] == "BOTH SEXES":
            other = lookup["A", row["reference_state_code"], "ALL RACES", row["age"]]
            for name in AB_FIELDS:
                duplicate_checks.append(dict(source_key=row["source_key"], other_source_key=other["source_key"],
                    field=name, first_raw=row["raw_values"][name], other_raw=other["raw_values"][name],
                    literal_equal=row["raw_values"][name] == other["raw_values"][name],
                    independent_observations=False, summed=False))
        if row["table"] != "C":
            continue
        other = lookup[("A", "US", "ALL RACES", "18_plus") if row["reference_state_code"] == "US" else
                       ("B", row["reference_state_code"], row["native_group"].upper(), "18_plus")]
        for field in ("population_thousands", "registered_thousands", "voted_thousands"):
            reference = number(other["raw_values"][field])
            if field == "population_thousands":
                reference -= number(other["raw_values"]["noncitizen_within_source_nonvote_thousands"])
            cross_frames.append(dict(source_key=row["source_key"], other_source_key=other["source_key"],
                field=field, citizen_raw=row["raw_values"][field],
                adult_reference_definition="adult_minus_noncitizen_rounded_counts" if field == "population_thousands"
                    else "same_source_reported_count_not_rate",
                adult_reference_thousands=text(reference),
                citizen_minus_reference_thousands=text(number(row["raw_values"][field]) - reference),
                rates_across_denominators_compared=False, source_repaired=False))
        for metric, no, unknown in (("registered", "not_registered", "unknown_registration"),
                                    ("voted", "not_voted", "unknown_voting")):
            raw = row["raw_values"]
            base, yes, no_count, missing = [number(raw[name + "_thousands"])
                                          for name in ("population", metric, no, unknown)]
            valid = base > 0 and 0 <= yes <= yes + missing <= base
            scenarios.append(dict(source_key=row["source_key"], reference_state_code=row["reference_state_code"],
                native_group=row["native_group"], population_frame="cvap", measure=metric,
                source_reported_percentage=raw[metric + "_pct"], reported_no_thousands=text(no_count),
                reported_unknown_thousands=text(missing), rounding_residual_thousands=text(base - yes - no_count - missing),
                all_unknown_no_pct=text(100 * yes / base) if valid else None,
                all_unknown_yes_pct=text(100 * (yes + missing) / base) if valid else None,
                disposition="rounded_count_allocation_assumption_not_CI" if valid else "held_rounded_count_conflict",
                unknown_assigned_to_observed_nonvoters=False, residual_assigned=False,
                confidence_interval=None, observed_individual_participation=False))
    for code in ("US", *sorted(codes.values())):
        for group in GROUPS["C"]:
            if ("C", code, group, "18_plus") not in lookup:
                for metric in C_METRICS:
                    metrics.append(dict(source_key=None, reference_state_code=code, table="C",
                        native_group=group, age="18_plus", population_frame="cvap", measure=metric,
                        duplicate_total_not_independent=False, raw_percentage=None, selected_percentage=None,
                        disposition="not_printed_citizen_geography_gender_cell", standard_error=None,
                        confidence_interval=None, sample_n=None))
    old = {(row["reference_state_code"], row["native_group"]): row for row in previous["records"]}
    historical = {(int(row["year"]), row["reference_state_code"], row["population_frame"]): row for row in history}
    endpoints = sorted({int(row["year"]) for row in history
                        if int(row["year"]) > 1996 and row["election_type"] == "presidential"})
    comparisons, reconciliations, snapshots = [], [], []
    for row in records:
        if row["age"] != "18_plus" or row["native_group"] not in BRIDGE or row["table"] == "C":
            continue
        reference = old[row["reference_state_code"], BRIDGE[row["native_group"]]]
        for metric in METRICS:
            first = row["measures"][metric]["selected_percentage"]
            last = reference["measures"][metric]["selected_percentage"]
            comparisons.append(dict(source_key=row["source_key"], endpoint_source_key=reference["source_key"],
                reference_state_code=row["reference_state_code"], native_group=row["native_group"],
                endpoint_native_group=BRIDGE[row["native_group"]], measure=metric, population_frame="vap",
                from_year=1996, to_year=1998, from_election_type="presidential", to_election_type="midterm",
                same_election_type=False, from_percentage=first, to_percentage=last,
                difference_pp=text(Decimal(last) - Decimal(first)) if first is not None and last is not None else None,
                disposition="descriptive_cross_election_type_snapshot" if first is not None and last is not None
                    else "held_native_metric", significance=None, confidence_interval=None,
                harmonized_cohort=False, observed_staying_home=False, local_allocation=False))
        if row["table"] != "A" or row["native_group"] != "ALL RACES":
            continue
        for metric in METRICS:
            point = row["measures"][metric]["selected_percentage"]
            current = historical.get((1996, row["reference_state_code"], "vap"))
            retrospective = current["reported_" + metric + "_pct"] if current else None
            reconciliations.append(dict(source_key=row["source_key"], reference_state_code=row["reference_state_code"],
                measure=metric, population_frame="vap", original_percentage=point,
                retrospective_percentage=retrospective,
                retrospective_minus_original_pp=text(Decimal(retrospective) - Decimal(point))
                    if retrospective is not None and point is not None else None, source_repaired=False))
            for year in endpoints:
                reference = historical.get((year, row["reference_state_code"], "vap"))
                endpoint = reference["reported_" + metric + "_pct"] if reference else None
                available = point is not None and endpoint not in (None, "")
                snapshots.append(dict(source_key=row["source_key"], reference_state_code=row["reference_state_code"],
                    measure=metric, population_frame="vap", from_year=1996, to_year=year,
                    election_type="presidential", from_percentage=point, to_percentage=endpoint,
                    difference_pp=text(Decimal(endpoint) - Decimal(point)) if available else None,
                    disposition="same_frame_same_election_type_source_snapshot" if available
                        else "held_unavailable_native_or_national_endpoint",
                    harmonized_cohort=False, confidence_interval=None, significance=None,
                    individual_retention=None, observed_staying_home=None, local_allocation=False))
    summary = dict(native_rows=len(records), native_cells=sum(len(row["raw_values"]) for row in records),
        table_rows=dict(sorted(Counter(row["table"] for row in records).items())),
        geographies=52, native_B_cells=sum(value == "(B)" for row in records for value in row["raw_values"].values()),
        metric_decisions=len(metrics), dispositions=dict(sorted(Counter(row["disposition"] for row in metrics).items())),
        duplicate_total_cell_checks=len(duplicate_checks),
        duplicate_total_mismatches=sum(not row["literal_equal"] for row in duplicate_checks),
        cross_frame_count_references=len(cross_frames), nonresponse_scenarios=len(scenarios),
        cross_election_type_group_decisions=len(comparisons), same_year_reconciliations=len(reconciliations),
        same_type_overall_decisions=len(snapshots), same_type_endpoint_years=endpoints,
        native_zeros_preserved=sum(value == "0" for row in records for value in row["raw_values"].values()),
        population_frames_not_merged=True, new_confidence_intervals=0, frontend_activation=False,
        house_model_refits=0, source_acquisitions_or_accepted_reductions_repeated=False)
    return dict(contract="participation.cps_1996_state_points.v1", policy=policy, summary=summary, records=records,
        metric_decisions=metrics, duplicate_total_checks=duplicate_checks, cross_frame_count_references=cross_frames,
        nonresponse_scenarios=scenarios, group_snapshot_comparisons=comparisons,
        retrospective_reconciliations=reconciliations, overall_snapshot_comparisons=snapshots)


def result_files(result):
    names = ("metric_decisions", "duplicate_total_checks", "cross_frame_count_references", "nonresponse_scenarios",
             "group_snapshot_comparisons", "retrospective_reconciliations", "overall_snapshot_comparisons")
    cells = [dict(source_key=row["source_key"], reference_state_code=row["reference_state_code"],
                  table=row["table"], native_group=row["native_group"], age=row["age"],
                  population_frame=row["population_frame"], field=name, raw_value=value)
             for row in result["records"] for name in sorted(row["raw_values"])
             for value in (row["raw_values"][name],)]
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
            "complete-native-cells.csv": csv_bytes(cells),
            **{"complete-" + name.replace("_", "-") + ".csv": csv_bytes(result[name]) for name in names}}


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
