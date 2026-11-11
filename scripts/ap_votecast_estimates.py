"""Private repeated-cross-section VoteCast participation estimates."""

import argparse
import codecs
import csv
import hashlib
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from contextlib import ExitStack
from decimal import Decimal, getcontext
from pathlib import Path

from scripts.civic_estimates import STATES, private_destination


ZERO = Decimal(0)


def formatted_code(value):
    value = value.strip()
    if not value:
        return "MISSING"
    match = re.match(r"^\((\d+)\)(?:\s|$)", value)
    if not match:
        raise ValueError("Unexpected unqualified formatted categorical value")
    return match.group(1)


def csv_encoding(prefix):
    try:
        codecs.getincrementaldecoder("utf-8-sig")().decode(prefix, final=False)
        return "utf-8-sig"
    except UnicodeDecodeError:
        prefix.decode("cp1252")
        return "cp1252"


def postal_state(value):
    value = value.strip()
    match = re.match(r"^\(([A-Z]{2})\)(?:\s|$)", value)
    state = match.group(1) if match else value
    if state not in STATES:
        raise ValueError("Unexpected source state")
    return state


def new_cell():
    return {"n": 0, "positive_weight_n": 0, "weight": ZERO,
            "weight_squared": ZERO, "modeled_voter_weight": ZERO,
            "modeled_nonvoter_weight": ZERO, "model_unknown_weight": ZERO,
            "already_voted_self_report_weight": ZERO, "unlikely_intent_weight": ZERO}


def add(cell, weight, model, likelihood):
    cell["n"] += 1
    if not weight.is_finite() or weight < 0:
        raise ValueError("Invalid source weight")
    if weight == 0:
        return
    cell["positive_weight_n"] += 1
    cell["weight"] += weight
    cell["weight_squared"] += weight * weight
    cell[{"1": "modeled_voter_weight", "2": "modeled_nonvoter_weight"}.get(
        model, "model_unknown_weight")] += weight
    if likelihood == "5":
        cell["already_voted_self_report_weight"] += weight
    if likelihood in {"3", "4"}:
        cell["unlikely_intent_weight"] += weight


class HashReader(io.RawIOBase):
    def __init__(self, source):
        self.source = source
        self.sha256 = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.source.read(len(buffer))
        buffer[:len(data)] = data
        self.sha256.update(data)
        return len(data)


def open_member(stack, archive, basename):
    matches = [name for name in archive.namelist()
               if name.split("/")[-1] == basename and not name.startswith("__MACOSX/")]
    if len(matches) > 1:
        raise ValueError("Ambiguous native CSV member")
    if matches:
        return stack.enter_context(archive.open(matches[0]))
    nested = sorted((name for name in archive.namelist() if name.lower().endswith(".zip")),
                    key=lambda name: ("general" not in name.lower(), name))
    for name in nested:
        child = stack.enter_context(zipfile.ZipFile(io.BytesIO(archive.read(name))))
        result = open_member(stack, child, basename)
        if result is not None:
            return result
    return None


def state_inference(year, state, weight):
    if "NATIONAL" in weight:
        return "publisher_national_registered_source_frame"
    if year == "2018":
        return "source_descriptive_only_publisher_reports_47_state_estimates"
    if year == "2022" and state in {"DE", "WV"}:
        return "withheld_publisher_national_only_state"
    return "publisher_state_weight_descriptive_not_administrative_turnout"


def reduce_wave(year, contract):
    documented_dimensions = contract["demographics"]["variables"]
    weights = list(contract["weights"]["fields"])
    aggregates = defaultdict(new_cell)
    labels = {}
    with ExitStack() as stack:
        archive = stack.enter_context(zipfile.ZipFile(contract["archive"]["path"]))
        expected = contract["archive"]["selected_members"]["csv"]
        source = open_member(stack, archive, expected["name"])
        if source is None:
            raise ValueError("Documented general-election CSV not present")
        hashing = HashReader(source)
        buffered = io.BufferedReader(hashing)
        encoding = csv_encoding(buffered.peek(8192))
        stream = stack.enter_context(io.TextIOWrapper(buffered, encoding=encoding, newline=""))
        reader = csv.reader(stream)
        header = next(reader)
        if len(header) != len(set(header)):
            raise ValueError("Duplicate native columns")
        dimensions = [field for field in documented_dimensions if field in header]
        missing_dimensions = [field for field in documented_dimensions if field not in header]
        required = ("P_STATE", "LIKELYVOTER", "LVB", *dimensions, *weights)
        positions = {field: header.index(field) for field in required}
        count = 0
        for raw in reader:
            if len(raw) != len(header):
                raise ValueError("Invalid CSV width; no record data logged")
            state = postal_state(raw[positions["P_STATE"]])
            model = formatted_code(raw[positions["LIKELYVOTER"]])
            if model not in {"1", "2"}:
                raise ValueError("Unexpected modeled participation code")
            likelihood = formatted_code(raw[positions["LVB"]])
            groups = [("overall", "all")]
            for dimension in dimensions:
                label = raw[positions[dimension]].strip()
                code = formatted_code(label)
                groups.append((dimension, code))
                labels.setdefault((dimension, code), set()).add(label or "Missing")
            for weight_field in weights:
                text = raw[positions[weight_field]].strip()
                weight = Decimal(text) if text else ZERO
                scope = "US50_SOURCE" if "NATIONAL" in weight_field else state
                for dimension, group in groups:
                    add(aggregates[weight_field, scope, dimension, group], weight, model, likelihood)
            count += 1
        if count != contract["rows"] or hashing.sha256.hexdigest() != expected["sha256"]:
            raise ValueError("Native count or CSV hash changed")
    rows = []
    for (weight_field, scope, dimension, group), values in sorted(aggregates.items()):
        total = values["weight"]
        if values["modeled_voter_weight"] + values["modeled_nonvoter_weight"] + values["model_unknown_weight"] != total:
            raise AssertionError("Full model frame fails to reconcile")
        row = {
            "year": year, "weight_field": weight_field, "scope": scope, "dimension": dimension,
            "group": group,
            "native_labels": "All respondents" if dimension == "overall" else " | ".join(sorted(labels[dimension, group])),
            **values,
            "modeled_voter_pct": 100 * values["modeled_voter_weight"] / total if total else None,
            "modeled_nonvoter_pct": 100 * values["modeled_nonvoter_weight"] / total if total else None,
            "source_effective_n": total * total / values["weight_squared"] if total else None,
            "inference_status": state_inference(year, scope, weight_field),
            "administratively_observed_turnout": False,
            "source_weight_units_are_people": False,
        }
        rows.append(row)
    partitions = defaultdict(list)
    for (weight_field, scope, dimension, _), values in aggregates.items():
        if dimension != "overall":
            partitions[weight_field, scope, dimension].append(values)
    for (weight_field, scope, dimension), selected in partitions.items():
        control = aggregates[weight_field, scope, "overall", "all"]
        for field in new_cell():
            if sum((cell[field] for cell in selected), ZERO) != control[field]:
                raise AssertionError("Native demographic partition does not reconcile")
    return rows, {
        "year": year, "native_rows": count, "native_csv_sha256": expected["sha256"],
        "aggregate_rows": len(rows), "weight_fields": weights,
        "native_csv_encoding": encoding,
        "native_demographic_dimensions": dimensions, "partition_checks_passed": True,
        "documented_demographics_not_in_released_csv": missing_dimensions,
    }


def main():
    getcontext().prec = 80
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--years", nargs="+", choices=("2018", "2020", "2022", "2024"),
                        default=("2018", "2020", "2022", "2024"))
    args = parser.parse_args()
    args.output = private_destination(args.output)
    if args.output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    contract = json.loads(args.contract.read_text())
    args.output.mkdir(mode=0o700)
    results = []
    for year in args.years:
        print(json.dumps({"starting": year}), flush=True)
        rows, result = reduce_wave(year, contract["waves"][year])
        target = args.output / ("participation-" + year + ".csv")
        with target.open("x", encoding="utf-8", newline="") as stream:
            os.chmod(target, 0o600)
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        result["output"] = target.name
        result["output_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        results.append(result)
        print(json.dumps(result), flush=True)
    summary = {
        "status": "computed_private_four_wave_source_weighted_descriptives",
        "waves": results,
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest(),
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "public_release_qualified": False,
        "longitudinal_or_administrative_population_validation": False,
        "do_not_pool_distinct_native_groups_or_treat_repeated_cross_sections_as_a_panel": True,
    }
    with (args.output / "summary.json").open("x") as stream:
        os.chmod(stream.name, 0o600)
        json.dump(summary, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
