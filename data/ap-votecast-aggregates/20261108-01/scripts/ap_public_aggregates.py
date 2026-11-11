"""Package reviewed broad VoteCast aggregates without exporting private fine cells."""

import argparse
from collections import Counter
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


YEARS = ("2018", "2020", "2022", "2024")
STATES = tuple(sorted(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()))
WEIGHTS = tuple(stage + "_" + scope + "_WEIGHT"
                for stage in ("FINALVOTE", "POLLCLOSE") for scope in ("NATIONAL", "STATE"))
MASSES = (
    "weight", "modeled_voter_weight", "modeled_nonvoter_weight", "model_unknown_weight",
    "already_voted_self_report_weight", "unlikely_intent_weight",
)
KEYS = ("year", "weight_field", "scope", "dimension", "group")
FIELDS = (*KEYS, "native_labels", "n", "positive_weight_n", *MASSES, "inference_status")


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows, fields=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def dimensions(year):
    return {
        "AGE65": tuple(map(str, range(1, 7))),
        "EDUC": ("1", "2", "3", "4"),
        "INCOME": ("1", "2", "3", "4", "5"),
        "SEX" if year == "2018" else "GENDER": ("1", "2") if year == "2018" else ("1", "2", "3"),
        "RACETH": tuple(map(str, range(1, 8))),
        "RACETH5": ("1", "2", "3", "4", "5"),
    }


def requested(year):
    for field in WEIGHTS:
        if "_STATE_" in field:
            for state in STATES:
                yield dict(zip(KEYS, (year, field, state, "overall", "all")))
        else:
            yield dict(zip(KEYS, (year, field, "US50_SOURCE", "overall", "all")))
            for dimension, groups in dimensions(year).items():
                for group in (*groups, "99", *(("88",) if dimension.startswith("RACETH") else ())):
                    yield dict(zip(KEYS, (year, field, "US50_SOURCE", dimension, group)))


def eligibility(key, row):
    if key["group"] in {"88", "99", "MISSING"}:
        return "disclosure_removed_or_nonresponse_not_exported_separately"
    if key["year"] == "2022" and key["scope"] in {"DE", "WV"}:
        return "publisher_national_only_state_inference_withheld"
    if key["year"] == "2022" and key["dimension"] == "RACETH5":
        return "documented_dimension_absent_in_release"
    if row is None:
        return "documented_dimension_or_requested_group_not_released"
    if Decimal(row["weight"]) <= 0:
        return "no_positive_source_weight"
    threshold = 1000 if key["scope"] == "US50_SOURCE" else 500
    if int(row["positive_weight_n"]) < threshold:
        return "below_broad_aggregate_positive_weight_support"
    return "selected_broad_source_descriptive"


def select(waves, provenance):
    rows, dispositions = [], []
    for year in YEARS:
        index = {}
        for row in waves[year]:
            key = tuple(row[field] for field in KEYS)
            if key in index:
                raise ValueError("Duplicate cached source aggregate")
            index[key] = row
        for key in requested(year):
            source = index.get(tuple(key[field] for field in KEYS))
            reason = eligibility(key, source)
            chosen = reason == "selected_broad_source_descriptive"
            dispositions.append(dict(key, selected=chosen, disposition=reason))
            if chosen:
                rows.append({field: source[field] for field in FIELDS})
    return dict(schema="ap-public-participation-v1", provenance=provenance,
                selected_rows=rows, selection_dispositions=dispositions)


def validate(value):
    if set(value) != {"schema", "provenance", "selected_rows", "selection_dispositions"}:
        raise ValueError("Unapproved fields in public aggregate input")
    if value["schema"] != "ap-public-participation-v1":
        raise ValueError("Unknown public aggregate schema")
    provenance_years = []
    for row in value["provenance"]:
        if set(row) != {"year", "native_rows", "native_csv_sha256", "verified_aggregate_sha256",
                        "independent_native_checks"}:
            raise ValueError("Nonpermitted source provenance")
        for field in ("native_csv_sha256", "verified_aggregate_sha256"):
            if not re.fullmatch(r"[a-f0-9]{64}", row[field]):
                raise ValueError("Invalid source/proof hash")
        if any(not isinstance(row[field], int) or row[field] <= 0
               for field in ("native_rows", "independent_native_checks")):
            raise ValueError("Invalid native verification totals")
        provenance_years.append(row["year"])
    if sorted(provenance_years) != list(YEARS):
        raise ValueError("Incomplete four-wave source provenance")
    permitted = {tuple(key[field] for field in KEYS)
                 for year in YEARS for key in requested(year)}
    seen = set()
    with localcontext() as context:
        context.prec = 80
        for row in value["selected_rows"]:
            key = tuple(row[field] for field in KEYS)
            if key not in permitted or key in seen or set(row) != set(FIELDS):
                raise ValueError("Unapproved or duplicate public aggregate scope")
            seen.add(key)
            if eligibility(row, row) != "selected_broad_source_descriptive":
                raise ValueError("Private/withheld/undersupported aggregate in public input")
            counts = [row["n"], row["positive_weight_n"]]
            if any(not re.fullmatch(r"[0-9]+", str(n)) for n in counts):
                raise ValueError("Invalid raw aggregate count")
            if not 0 < int(counts[1]) <= int(counts[0]):
                raise ValueError("Invalid positive-weight support")
            masses = {field: Decimal(row[field]) for field in MASSES}
            if any(not n.is_finite() or n < 0 for n in masses.values()):
                raise ValueError("Invalid aggregate weight mass")
            total = masses["weight"]
            if sum(masses[f] for f in ("modeled_voter_weight", "modeled_nonvoter_weight",
                                       "model_unknown_weight")) != total:
                raise ValueError("Model classes do not reconcile to the full group denominator")
            if any(n > total for n in masses.values()):
                raise ValueError("Aggregate numerator exceeds full denominator")
            expected_inference = (
                "publisher_national_registered_source_frame" if row["scope"] == "US50_SOURCE" else
                "source_descriptive_only_publisher_reports_47_state_estimates" if row["year"] == "2018" else
                "publisher_state_weight_descriptive_not_administrative_turnout")
            if row["inference_status"] != expected_inference:
                raise ValueError("Missing or altered source inference qualification")
    disposition_keys = []
    selected = set()
    for row in value["selection_dispositions"]:
        if set(row) != set(KEYS) | {"selected", "disposition"}:
            raise ValueError("Nonpermitted statistics in the public selection disposition")
        key = tuple(row[field] for field in KEYS)
        disposition_keys.append(key)
        if row["selected"]:
            if row["disposition"] != "selected_broad_source_descriptive":
                raise ValueError("Inconsistent selected disposition")
            selected.add(key)
    if set(disposition_keys) != permitted or len(disposition_keys) != len(permitted) or selected != seen:
        raise ValueError("Incomplete or inconsistent public query selection")


def assemble(value):
    validate(value)
    rows, viewer = [], []
    with localcontext() as context:
        context.prec = 80
        for source in value["selected_rows"]:
            row = {field: source[field] for field in FIELDS}
            for numerator, name in (
                ("modeled_voter_weight", "modeled_voter_pct"),
                ("modeled_nonvoter_weight", "modeled_nonvoter_pct"),
                ("model_unknown_weight", "model_unknown_pct"),
                ("already_voted_self_report_weight", "already_voted_self_report_pct"),
                ("unlikely_intent_weight", "unlikely_intent_pct"),
            ):
                row[name] = str(100 * Decimal(row[numerator]) / Decimal(row["weight"]))
            row["administratively_observed_turnout"] = False
            row["source_weight_units_are_people"] = False
            rows.append(row)
            display = {field: row[field] for field in (*KEYS, "native_labels", "inference_status", "n",
                                                        "positive_weight_n")}
            for field in ("modeled_voter_pct", "modeled_nonvoter_pct", "model_unknown_pct",
                          "already_voted_self_report_pct", "unlikely_intent_pct"):
                display[field] = format(Decimal(row[field]).quantize(Decimal("0.00000001")), "f")
            viewer.append(display)
    notes = [
        "Source-weighted modeled participation among the source registered-voter frame, not administrative turnout.",
        "Keep all four state/national and poll-close/final native weights separate.",
        "Repeated cross-sections are not a linked panel or fixed demographic cohorts.",
        "Final weights reflect outcome calibration, not independent outcome validation.",
        "2018 state values are source descriptives: publisher reports 47 inference states despite all 50 sampled.",
        "2022 Delaware and West Virginia state inference is withheld; national rows retain their source cases.",
        "2022 RACETH5 was documented but absent from the released CSV and is not fabricated.",
        "Native SEX/GENDER and race/ethnicity definitions differ across years; labels are not harmonized.",
        "Current group membership is not historical group membership for the same people.",
        "No state demographics, respondent records, identifiers or county/precinct allocation are exported.",
        "Unknown and disclosure-removed groups remain in the full overall denominator, not recovered or redistributed.",
        "National positive-weight support minimum is 1000; whole-state overall minimum is 500.",
        "Support selection is not an anonymity or precision guarantee. Raw per-model-class support is not in the cache.",
        "Only total positive-weight support is asserted; no per-outcome support minimum or confidence interval is claimed.",
        "No cross-study turnout-change or switching estimate is inferred by joining these rows to Civic.",
    ]
    overall = [r for r in viewer if r["scope"] == "US50_SOURCE" and r["dimension"] == "overall"]
    summary = dict(schema=value["schema"], source="AP/NORC VoteCast", years=list(YEARS),
                   public_participation_rows=len(rows),
                   national_rows=sum(r["scope"] == "US50_SOURCE" for r in rows),
                   whole_state_overall_rows=sum(r["scope"] != "US50_SOURCE" for r in rows),
                   full_query_dispositions=len(value["selection_dispositions"]),
                   disposition_counts=dict(Counter(r["disposition"] for r in value["selection_dispositions"])),
                   national_overall=overall, provenance=value["provenance"], notes=notes)
    files = {
        "selected-aggregates.json": json_bytes(value),
        "participation.csv": csv_bytes(rows),
        "selection-dispositions.csv": csv_bytes(value["selection_dispositions"],
                                                (*KEYS, "selected", "disposition")),
        "viewer-data.json": json_bytes(dict(schema=value["schema"], rows=viewer)),
        "summary.json": json_bytes(summary),
        "scripts/ap_public_aggregates.py": Path(__file__).read_bytes(),
        "tests/test_ap_public_aggregates.py": Path(__file__).parents[1].joinpath(
            "tests/test_ap_public_aggregates.py").read_bytes(),
        "README.txt": (
            "Complete selected AP/NORC VoteCast participation aggregates, 2018/2020/2022/2024.\n"
            "Not raw respondent data, administrative turnout, a linked panel or comparable fixed cohorts.\n"
            "From the unpacked complete archive, without packages/network:\n"
            "  python3 -m unittest discover -s tests -p test_ap_public_aggregates.py\n"
            "  python3 -m scripts.ap_public_aggregates --inputs selected-aggregates.json --output reproduced\n"
            "All permitted selected aggregate inputs, complete queries, withheld-query dispositions,\n"
            "code and tests are included. Original microdata and private fine cells are excluded.\n"
            "Read every source/frame/inference/support qualification in summary.json before use.\n"
        ).encode(),
    }
    files["checksums.json"] = json_bytes({
        name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        for name, data in sorted(files.items())})
    return files, summary


def cached_input(directory, verification):
    proof = json.loads(verification.read_bytes())
    summary = json.loads((directory / "summary.json").read_bytes())
    if proof["status"] != "passed" or proof["estimator_imported"]:
        raise ValueError("Independent native verification required")
    waves, provenance = {}, []
    for year in YEARS:
        item = next(w for w in summary["waves"] if w["year"] == year)
        checked = next(w for w in proof["waves"] if w["year"] == year)
        content = (directory / ("participation-" + year + ".csv")).read_bytes()
        if hashlib.sha256(content).hexdigest() != checked["output_sha256"] or (
                item["output_sha256"] != checked["output_sha256"]):
            raise ValueError("Changed independently verified aggregate cache")
        waves[year] = list(csv.DictReader(io.StringIO(content.decode())))
        if len(waves[year]) != checked["aggregate_rows"]:
            raise ValueError("Changed verified aggregate row count")
        provenance.append(dict(year=year, native_rows=checked["native_rows"],
                               native_csv_sha256=item["native_csv_sha256"],
                               verified_aggregate_sha256=checked["output_sha256"],
                               independent_native_checks=checked["native_count_weight_checks"]))
    return select(waves, provenance)


def export(value, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    files, summary = assemble(value)
    output.mkdir(parents=True)
    for name, content in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps({key: summary[key] for key in (
        "public_participation_rows", "national_rows", "whole_state_overall_rows",
        "full_query_dispositions", "disposition_counts",
    )}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--inputs", type=Path)
    source.add_argument("--verified-aggregates", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.verified_aggregates and not args.verification:
        parser.error("--verified-aggregates requires --verification")
    selected = (json.loads(args.inputs.read_bytes()) if args.inputs else
                cached_input(args.verified_aggregates, args.verification))
    export(selected, args.output)
