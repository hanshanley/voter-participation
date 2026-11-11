"""Keep native 1998 state demographic participation points and compatible source snapshots."""

import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


NATIVE_SHA = "bc998b4ac2db5c65b2aa55839df907c70d599eddeca0f988500ef80339095833"
PREDECESSOR_SHA = "4d651c36c02a8dd5b413897deccad01d8b2ee05f1f08b9ce2cd068b167858a8b"
FIELDS = ("adults_thousands", "citizen_adults_thousands", "citizen_adults_pct",
    "citizen_adults_printed_se_pp", "registered_thousands", "registered_pct",
    "registered_printed_se_pp", "voted_thousands", "voted_pct", "voted_printed_se_pp")
METRICS = ("citizen_adults", "registered", "voted")
GROUPS = ("Total", "Male", "Female", "N-H White", "N-H Black", "N-H API", "Hispanic", "White", "Black")
BRIDGE = {"Total": ".Total", "Male": ".Male", "Female": ".Female",
    "N-H White": ".Non-Hispanic White", "N-H Black": ".Non-Hispanic Black",
    "N-H API": None, "Hispanic": ".Hispanic (of any race)", "White": ".White", "Black": ".Black"}
ROW = re.compile(r"(.*?)\s+(" + "|".join(re.escape(group) for group in GROUPS)
    + r")\s+([\d.(].*?)\s*")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def decimal(value):
    if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?", value):
        return None
    try:
        number = Decimal(value.replace(",", ""))
        return number if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def percentage(value):
    number = decimal(value)
    return number if number is not None and number <= 100 else None


def text(value):
    return None if value is None else format(value, "f")


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sorted(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def policy_check(policy):
    if (policy["contract"] != "participation.cps_1998_state_points_policy.v1"
            or policy["year"] != 1998 or policy["population_frame"] != "vap"
            or policy["selection"] != "literal_source_metric_specific_points_and_printed_standard_errors"
            or policy["native_count_unit"] != "thousands"
            or policy["standard_errors"] != "directly_printed_only_not_new_confidence_intervals"
            or policy["suppression"] != "preserve_B_per_metric_and_do_not_reconstruct"
            or policy["dot_counts"] != "literal_unqualified_missing_symbol_not_zero"
            or policy["minimum_sample_size"] is not None or not policy["native_zeros_preserved"]
            or policy["grouped_same_type_endpoint"] != 2002
            or policy["overall_same_type_endpoints"] != [2018, 2022]
            or any(policy[key] is not False for key in ("race_harmonization",
                "unknown_or_suppressed_reconstruction", "native_defects_repaired",
                "derived_citizen_turnout", "derived_intervals", "significance_tests",
                "local_allocation", "frontend_activation", "individual_history"))):
        raise ValueError("Unqualified change to native source selection")


def load_inputs(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    if manifest["contract"] != "participation.cps_1998_state_points_inputs.v1":
        raise ValueError("Unknown frozen inputs")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or pin((root / name).read_bytes()) != expected:
            raise ValueError("Unsafe or changed input")
    original, predecessor = (root / "1998-tab04.txt").read_bytes(), (root / "predecessor-science.zip").read_bytes()
    if pin(original)["sha256"] != NATIVE_SHA or pin(predecessor)["sha256"] != PREDECESSOR_SHA:
        raise ValueError("Changed original or complete accepted science")
    policy = json.loads((root / "policy.json").read_bytes())
    policy_check(policy)
    with zipfile.ZipFile(io.BytesIO(predecessor)) as archive:
        members = json.loads(archive.read("manifest.json"))
        for name, expected in members["files"].items():
            if pin(archive.read(name)) != expected:
                raise ValueError("Changed accepted predecessor member")
        previous = json.loads(archive.read("results/complete-result.json"))
        with zipfile.ZipFile(io.BytesIO(archive.read("inputs/baseline-science.zip"))) as baseline:
            for name, expected in json.loads(baseline.read("checksums.json")).items():
                if pin(baseline.read(name)) != expected:
                    raise ValueError("Changed held historical frame")
            history = list(csv.DictReader(io.StringIO(
                baseline.read("complete-state-year-population-pairs.csv").decode())))
    return original.decode("ascii"), previous, history, policy


def parse_native(source, codes):
    lines = source.splitlines()
    if (not lines[0].endswith("for States: November 1998")
            or "Internet Release Date:  July 19, 2000" not in source
            or "(In thousands)" not in lines or lines[7].count("Standard") != 3
            or "N-H represents Non-Hispanic." not in source
            or "API includes Asian and Pacific Islander." not in source
            or "Hispanics may be of any race." not in source):
        raise ValueError("Changed native title, units, errors or category definitions")
    result, current, seen = [], None, set()
    for ordinal, line in enumerate(lines, 1):
        match = ROW.fullmatch(line)
        if not match:
            continue
        geography, group, tokens = match[1].strip(), match[2], match[3].split()
        if geography:
            current = geography
        if current not in codes or len(tokens) != len(FIELDS) or (current, group) in seen:
            raise ValueError("Unqualified source row or duplicate")
        seen.add((current, group))
        values = dict(zip(FIELDS, tokens))
        measures = {}
        for metric in METRICS:
            raw, error = values[metric + "_pct"], values[metric + "_printed_se_pp"]
            point, se = percentage(raw), percentage(error)
            disposition = ("withheld_native_small_base" if raw == "(B)" else
                "withheld_invalid_native_percentage" if point is None else "selected_reported_native_point")
            measures[metric] = dict(raw_percentage=raw, raw_standard_error=error,
                selected_percentage=text(point), selected_source_standard_error_pp=(
                    text(se) if point is not None else None), disposition=disposition,
                standard_error_disposition=("not_selected_without_point" if point is None else
                    "withheld_native_standard_error" if error == "(B)" else
                    "withheld_invalid_native_standard_error" if se is None else "source_printed_standard_error"),
                derived_interval=None)
        result.append(dict(source_key=f"1998-tab04.txt:{ordinal}", source_line=ordinal,
            geography=current, reference_state_code=codes[current], native_group=group,
            year=1998, population_frame="vap", raw_values=values, measures=measures,
            count_symbols={name: value for name, value in values.items()
                if name.endswith("_thousands") and decimal(value) is None},
            count_values_are_rounded_thousands_not_sample_n=True, sample_n=None,
            citizen_turnout=None, individual_history=None, eligibility=None, deaths=None,
            migration=None, race_categories_harmonized=False, local_allocation=False))
    if seen != {(name, group) for name in codes for group in GROUPS}:
        raise ValueError("Incomplete native geography/group roster")
    return result


def build(source, previous, history, policy):
    policy_check(policy)
    codes = {row["native_state_name"].upper(): row["reference_state_code"] for row in history}
    if len(codes) != 51:
        raise ValueError("Incomplete accepted state roster")
    codes["UNITED STATES"] = "US"
    records = parse_native(source, codes)
    old = {(row["native"]["geography"], row["native"]["native_label"]): row
        for row in previous["records"] if row["native"]["role"] == "sex_race"}
    if len(old) != 468:
        raise ValueError("Changed complete accepted 2002 native records")
    baseline = {(int(row["year"]), row["reference_state_code"], row["population_frame"]): row
        for row in history}
    metric_rows, comparisons, reconciliations, snapshots = [], [], [], []
    for row in records:
        for metric, measure in row["measures"].items():
            metric_rows.append(dict(source_key=row["source_key"], geography=row["geography"],
                reference_state_code=row["reference_state_code"], native_group=row["native_group"],
                year=1998, population_frame="vap", measure=metric,
                measure_meaning="citizenship_share_not_turnout" if metric == "citizen_adults"
                    else "reported_participation_within_all_adults",
                **measure))
        native_2002 = old.get((row["geography"], BRIDGE[row["native_group"]]))
        for metric in ("registered", "voted"):
            point = row["measures"][metric]["selected_percentage"]
            endpoint = native_2002["selected_" + metric + "_pct"] if native_2002 else None
            status = ("held_non_hispanic_API_not_all_API" if native_2002 is None else
                "held_1998_metric" if point is None else "held_2002_source_selection"
                if endpoint is None else "same_label_source_snapshot_not_harmonized_cohort")
            comparisons.append(dict(source_key=row["source_key"], geography=row["geography"],
                reference_state_code=row["reference_state_code"], native_1998_group=row["native_group"],
                native_2002_group=BRIDGE[row["native_group"]], measure=metric,
                from_year=1998, to_year=2002, population_frame="vap", election_type="midterm",
                disposition=status, from_percentage=point, to_percentage=endpoint,
                difference_pp=text(Decimal(str(endpoint)) - Decimal(point)) if
                    status == "same_label_source_snapshot_not_harmonized_cohort" else None,
                endpoint_source_key=native_2002["source_key"] if native_2002 else None,
                source_1998_standard_error=row["measures"][metric]["selected_source_standard_error_pp"],
                source_2002_precision_scalar=native_2002["source_reported_precision_values"][metric]
                    if native_2002 else None,
                change_interval=None, significance=None, definitions_harmonized=False,
                individual_retention=None, observed_staying_home=None, local_allocation=False))
        if row["native_group"] != "Total":
            continue
        for metric in ("registered", "voted"):
            point = row["measures"][metric]["selected_percentage"]
            current = baseline.get((1998, row["reference_state_code"], "vap"))
            reference = current["reported_" + metric + "_pct"] if current else None
            difference = text(Decimal(reference) - Decimal(point)) if reference and point is not None else None
            reconciliations.append(dict(source_key=row["source_key"], geography=row["geography"],
                reference_state_code=row["reference_state_code"], measure=metric, population_frame="vap",
                original_percentage=point, retrospective_percentage=reference,
                retrospective_minus_original_pp=difference,
                disposition="no_national_retrospective_state_frame" if current is None else
                    "source_versions_differ_preserved" if difference is not None and Decimal(difference) else
                    "same_source_percentage_matches" if difference is not None else "held_source_metric",
                source_repaired=False))
            for year in policy["overall_same_type_endpoints"]:
                reference = baseline.get((year, row["reference_state_code"], "vap"))
                endpoint = reference["reported_" + metric + "_pct"] if reference else None
                available = point is not None and endpoint not in (None, "")
                snapshots.append(dict(source_key=row["source_key"], geography=row["geography"],
                    reference_state_code=row["reference_state_code"], measure=metric, from_year=1998,
                    to_year=year, population_frame="vap", election_type="midterm",
                    from_percentage=point, to_percentage=endpoint,
                    difference_pp=text(Decimal(endpoint) - Decimal(point)) if available else None,
                    disposition="same_frame_source_snapshot_not_cohort" if available
                        else "held_unavailable_national_or_native_endpoint",
                    definitions_harmonized=False, change_interval=None, significance=None,
                    individual_retention=None, eligibility=None, deaths=None, migration=None,
                    local_allocation=False))
    summary = dict(native_rows=len(records), native_metric_cells=len(records) * len(FIELDS),
        geographies=len(codes), native_groups=len(GROUPS), complete_metric_decisions=len(metric_rows),
        metric_decisions=dict(sorted(Counter(row["disposition"] for row in metric_rows).items())),
        standard_error_decisions=dict(sorted(Counter(row["standard_error_disposition"] for row in metric_rows).items())),
        complete_1998_to_2002_decisions=len(comparisons),
        historical_group_decisions=dict(sorted(Counter(row["disposition"] for row in comparisons).items())),
        complete_retrospective_reconciliations=len(reconciliations),
        reconciliations=dict(sorted(Counter(row["disposition"] for row in reconciliations).items())),
        complete_2018_2022_overall_decisions=len(snapshots),
        overall_snapshot_decisions=dict(sorted(Counter(row["disposition"] for row in snapshots).items())),
        literal_dot_count_cells=sum(len(row["count_symbols"]) for row in records),
        literal_zero_count_cells=sum(value == "0" for row in records
            for name, value in row["raw_values"].items() if name.endswith("_thousands")),
        source_numeric_zero_standard_errors=sum(
            row["selected_source_standard_error_pp"] is not None and Decimal(row["selected_source_standard_error_pp"]) == 0
            for row in metric_rows),
        source_counts_repaired=0, new_intervals=0, derived_citizen_turnout_rates=0,
        frontend_activation=False)
    return dict(contract="participation.cps_1998_native_state_points.v1", policy=policy,
        summary=summary, records=records, metric_decisions=metric_rows,
        group_snapshot_comparisons=comparisons, retrospective_reconciliations=reconciliations,
        overall_snapshot_comparisons=snapshots)


def result_files(result):
    rows = {name: result[name] for name in ("metric_decisions", "group_snapshot_comparisons",
        "retrospective_reconciliations", "overall_snapshot_comparisons")}
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
        **{"complete-" + key.replace("_", "-") + ".csv": csv_bytes(value) for key, value in rows.items()}}


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
