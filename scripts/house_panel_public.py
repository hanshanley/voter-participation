"""Replay all public historical House concordance outputs from coarse sufficient cells."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import io
import json
from pathlib import Path


STATES = "AK AL AR AZ CA CO CT DC DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split()
WEIGHTS = ("commonpostweight_24", "commonpostweight_22", "vvweight_post_22")
SELECTIONS = ("both_major_choices", "both_major_choices_and_positive_history")
RATE = "gross_D_R_switch_pct_within_selected_both_major_choices"
AP_QUERY = ("AP2024_source", "POOLED_SOURCE_NOT_NATIONAL_POPULATION", "POLLCLOSE_STATE_WEIGHT",
            "modeled_current_voter_both_recalled22_and_current24_major_choices")
CES_QUERY = ("CES_retained_panel", "ALL_SOURCE", "commonpostweight_24", SELECTIONS[1])


def json_bytes(value):
    def convert(item):
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, dict):
            return {key: convert(v) for key, v in item.items()}
        if isinstance(item, list):
            return [convert(v) for v in item]
        return item
    return (json.dumps(convert(value), indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def replay(inputs):
    expected = {("CES_retained_panel", scope, weight, selection)
                for scope in (*STATES, "UNLOCATED", "ALL_SOURCE")
                for weight in WEIGHTS for selection in SELECTIONS} | {AP_QUERY}
    seen, decisions = set(), []
    selected, joint_rows = {}, []
    decision_rows = []
    with localcontext() as context:
        context.prec = 70
        for raw in inputs["decisions"]:
            if set(raw) != {"source", "scope", "weight_frame", "selection", "available", "reason", "cells"}:
                raise ValueError("Unexpected fields in public sufficient input")
            row = dict(raw)
            identity = tuple(row[key] for key in ("source", "scope", "weight_frame", "selection"))
            if identity not in expected or identity in seen:
                raise ValueError("Missing, duplicate or unrecognized public query")
            seen.add(identity)
            eligible = identity in (AP_QUERY, CES_QUERY)
            if not eligible and (row["available"] or row["cells"] is not None or
                                 row["reason"] != "outside_prespecified_public_scope"):
                raise ValueError("Fine/state/sensitivity source cells must remain held whole")
            if not row["available"]:
                if row["cells"] is not None:
                    raise ValueError("Partial suppressed table could reveal complements")
                row["statistics"] = None
            else:
                if not eligible or row["reason"] is not None or set(row["cells"]) != {"DD", "DR", "RD", "RR"}:
                    raise ValueError("Unqualified public source table")
                values = {}
                for pair, item in row["cells"].items():
                    if set(item) != {"n", "weight", "squared_weight"} or type(item["n"]) is not int or item["n"] < 30:
                        raise ValueError("Whole-table raw support rule failed")
                    weight = Fraction(item["weight"])
                    squared = Fraction(item["squared_weight"])
                    if weight <= 0 or squared <= 0 or weight * weight > item["n"] * squared:
                        raise ValueError("Invalid coarse weighted sufficient cell")
                    values[pair] = Decimal(item["weight"])
                    joint_rows.append(dict(source=row["source"], scope=row["scope"],
                        weight_frame=row["weight_frame"], previous_house=pair[0],
                        current_house=pair[1], raw_cases=item["n"],
                        weighted_sum=item["weight"], squared_weight_sum=item["squared_weight"]))
                total = sum(values.values())
                row["statistics"] = {RATE: 100 * (values["DR"] + values["RD"]) / total}
                for previous in "DR":
                    row["statistics"][previous + "_to_opposite_pct_within_selected_previous_choice"] = (
                        100 * values[previous + ("R" if previous == "D" else "D")] /
                        sum(values[previous + current] for current in "DR"))
                selected[row["source"]] = row
            decisions.append(row)
            decision_rows.append({key: row[key] for key in
                                  ("source", "scope", "weight_frame", "selection", "available", "reason")})
        if seen != expected:
            raise ValueError("Incomplete public query set")
        differences = None
        comparison_rows = []
        if len(selected) == 2:
            differences = {}
            for key, ces in selected["CES_retained_panel"]["statistics"].items():
                ap = selected["AP2024_source"]["statistics"][key]
                differences[key] = ap - ces
                comparison_rows.append(dict(metric=key, CES_selected_source_percent=ces,
                    AP_selected_source_percent=ap, AP_minus_CES_percentage_points=ap - ces,
                    interpretation="unmatched_source_concordance_not_population_validation"))
        result = dict(contract="participation.house_panel_concordance.v1", decisions=decisions,
            available_source_tables=len(selected), unmatched_source_differences_pp=differences,
            current_2026_model_changed=False, independent_individual_truth=False,
            population_validation=False, source_code_transport_assumption_required=True,
            design_confidence_intervals=None, precinct_allocation=False)
        summary = dict(contract=result["contract"], source_CES_retained_cases=6175,
            query_decisions=len(decisions), available_source_tables=len(selected),
            whole_table_holds=len(decisions) - len(selected),
            selected_raw_cases={key: sum(v["n"] for v in value["cells"].values())
                                for key, value in selected.items()},
            selected_source_rates={key: value["statistics"] for key, value in selected.items()},
            unmatched_source_differences_pp=differences, design_confidence_intervals=None,
            conditional_source_code_transport=True, independent_population_validation=False,
            private_source_extraction_rerun_by_public_replay=False, accepted_models_changed=False,
            native_respondents_and_private_fine_cells_exported=False)
        return {
            "source-concordance.json": json_bytes(result),
            "query-decisions.csv": csv_bytes(
                ["source", "scope", "weight_frame", "selection", "available", "reason"], decision_rows),
            "pooled-joints.csv": csv_bytes(
                ["source", "scope", "weight_frame", "previous_house", "current_house",
                 "raw_cases", "weighted_sum", "squared_weight_sum"], joint_rows),
            "source-comparison.csv": csv_bytes(
                ["metric", "CES_selected_source_percent", "AP_selected_source_percent",
                 "AP_minus_CES_percentage_points", "interpretation"], comparison_rows),
            "summary.json": json_bytes(summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh replay output directory")
    result = replay(json.loads(args.inputs.read_bytes()))
    args.output.mkdir(parents=True)
    for name, body in result.items():
        (args.output / name).write_bytes(body)
    print(json.dumps(dict(status="public_coarse_numeric_replay_complete", output_files=len(result),
                          native_cases_or_fine_cells_used=False)))


if __name__ == "__main__":
    main()
