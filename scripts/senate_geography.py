"""Resolve source-missing county IDs using held Census-backed and cross-feed evidence."""

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


def county_name(value):
    return re.sub(r"\s+county$", "", value.casefold().replace(".", "")).strip()


def named_vector(rows):
    result = {}
    for row in rows:
        if "write" in row["candidate"].casefold():
            continue
        key = re.sub(r"[^a-z0-9]", "", row["candidate"].casefold())
        if not key or key in result or not re.fullmatch(r"[0-9]+", row["votes"]):
            raise ValueError("Nonunique or invalid named candidate evidence")
        result[key] = row
    return result


def resolve(native, house, state_codes):
    missing, cnn, house_index = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in native:
        if row["provider"] == "civic" and row["county_equivalent_scope"] == "True" and not row["fips"]:
            missing[row["state"], row["contest"], row["native_unit_id"]].append(row)
        if (row["provider"] == "cnn" and row["eligible_for_fips_name_count_comparison"] == "True"
                and row["native_unit_name"].casefold().endswith(" county")):
            cnn[row["state"], row["contest"], county_name(row["native_unit_name"])].append(row)
    for row in house:
        if row["year"] != 2026 or row["level"] != "county":
            continue
        for fragment in row["district_fragments"]:
            if (fragment.get("native_type") == "County" and fragment.get("join_strategy") in {
                    "unique_census_name_casefold_periods", "explicit_native_fips"}
                    and fragment.get("source_url", "").startswith("https://civicapi.org/api/v2/race/")):
                house_index[row["state_code"], fragment["source_key"]].append(fragment)
    joins, checks, resolved = [], [], {}
    for (state, contest, unit), source in sorted(missing.items()):
        record = dict(state=state, contest=contest, native_unit_id=unit,
                      native_unit_name=source[0]["native_unit_name"], native_fips="",
                      resolved_fips="", status="withheld_insufficient_or_nonunique_reference_evidence")
        h = [row for row in house_index[state, unit]
             if county_name(row["native_name"]) == county_name(source[0]["native_unit_name"])]
        other = cnn[state, contest, county_name(source[0]["native_unit_name"])]
        h_ids = {row["geography"] for row in h}
        other_ids = {row["fips"] for row in other}
        other_units = {row["native_unit_id"] for row in other}
        if (source[0]["native_unit_type"] != "County" or len(h_ids) != 1
                or h_ids != other_ids or len(other_units) != 1):
            joins.append(record)
            continue
        fips = next(iter(h_ids))
        if not re.fullmatch(r"[0-9]{5}", fips) or not fips.startswith(state_codes[state]):
            joins.append(record)
            continue
        first, second = named_vector(source), named_vector(other)
        if first.keys() != second.keys() or sum(int(r["votes"]) > 0 for r in first.values()) < 2:
            joins.append(record)
            continue
        record.update(resolved_fips=fips,
                      status="reference_joined_not_native_declared",
                      house_reference_methods=";".join(sorted({row["join_strategy"] for row in h})),
                      house_native_source_urls=";".join(sorted({row["source_url"] for row in h})),
                      cnn_native_unit_id=next(iter(other_units)),
                      matching_named_candidate_identities=len(first),
                      exact_named_count_vector_equal=all(first[k]["votes"] == second[k]["votes"] for k in first))
        joins.append(record)
        resolved[state, contest, unit] = fips
        for key in sorted(first):
            left, right = first[key], second[key]
            checks.append(dict(state=state, contest=contest, civic_native_unit_id=unit,
                resolved_fips=fips, civic_candidate=left["candidate"], cnn_candidate=right["candidate"],
                civic_party=left["party"], cnn_party=right["party"],
                civic_votes=left["votes"], cnn_votes=right["votes"],
                civic_minus_cnn=int(left["votes"]) - int(right["votes"]),
                civic_clock=left["native_updated"], cnn_clock=right["native_updated"],
                same_round_independently_qualified=False, independent_outcome_validation=False))
    enriched = []
    for row in native:
        key = row["state"], row["contest"], row["native_unit_id"]
        added = resolved.get(key) if row["provider"] == "civic" and not row["fips"] else None
        enriched.append(dict(row, resolved_fips=added or row["fips"],
                             fips_resolution="reference_joined_not_native_declared" if added else
                             "original_query_identifier" if row["fips"] else "unresolved_or_noncounty"))
    summary = dict(native_candidate_unit_rows=len(native), source_missing_county_units=len(missing),
                   reference_joined_county_units=len(resolved),
                   unresolved_source_missing_county_units=len(missing)-len(resolved),
                   candidate_rows_with_reference_join=sum(r["fips_resolution"] ==
                                                         "reference_joined_not_native_declared" for r in enriched),
                   additional_named_candidate_checks=len(checks),
                   additional_equal_named_counts=sum(r["civic_minus_cnn"] == 0 for r in checks),
                   additional_different_named_counts=sum(r["civic_minus_cnn"] != 0 for r in checks),
                   notes=[
                       "Original query fields, native blank FIPS, counts, parties and clocks are preserved.",
                       "Reference IDs are not retrospectively declared native feed identifiers.",
                       "House native namespace keys plus unique previously qualified 2026 Census county joins and CNN declared IDs support geography.",
                       "All named Senate candidate identities must match; count differences remain rather than preventing a corroborated geography join.",
                       "Matching source counts are not independent outcome validation or same-round qualification.",
                       "No county/town/Alaska aggregation, redistribution, inferred turnout or Maine write-in repair is performed.",
                   ])
    return enriched, joins, checks, summary


def csv_bytes(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def export(query, house_path, codes_path, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    with query.open(newline="") as stream:
        native = list(csv.DictReader(stream))
    if not native:
        raise ValueError("Missing complete native candidate-unit query")
    with gzip.open(house_path, "rt") as stream:
        house = json.load(stream)
    enriched, joins, checks, summary = resolve(native, house, json.loads(codes_path.read_bytes()))
    join_fields = list(dict.fromkeys(k for row in joins for k in row)) or [
        "state", "contest", "native_unit_id", "native_unit_name", "native_fips", "resolved_fips", "status"]
    check_fields = list(checks[0]) if checks else [
        "state", "contest", "civic_native_unit_id", "resolved_fips", "civic_candidate", "cnn_candidate",
        "civic_party", "cnn_party", "civic_votes", "cnn_votes", "civic_minus_cnn", "civic_clock", "cnn_clock",
        "same_round_independently_qualified", "independent_outcome_validation"]
    files = {
        "complete-native-units-with-reference-ids.csv": csv_bytes(enriched, list(enriched[0])),
        "complete-missing-county-identifier-joins.csv": csv_bytes(joins, join_fields),
        "complete-additional-named-candidate-checks.csv": csv_bytes(checks, check_fields),
        "summary.json": (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode(),
        "scripts/senate_geography.py": Path(__file__).read_bytes(),
        "tests/test_senate_geography.py": Path(__file__).parents[1].joinpath(
            "tests/test_senate_geography.py").read_bytes(),
        "README.txt": (
            "Source-missing Senate county identifier joins, not native declarations or outcome validation.\n"
            "All original candidate-unit fields/counts/clocks remain unchanged in the complete query.\n"
            "From the unpacked complete archive, without packages/network:\n"
            "  python3 -m unittest discover -s tests -p test_senate_geography.py\n"
            "  python3 -m scripts.senate_geography --native-query inputs/native-query.csv "
            "--house-counties inputs/house-counties.json.gz --state-codes inputs/state-codes.json "
            "--output reproduced\n"
            "Held Census-backed House namespace IDs and CNN declared IDs support geography.\n"
            "Matching candidate identities do not mean equal counts, matched rounds or independent validation.\n"
            "Maine write-ins and all earlier unmatched control scopes remain unresolved.\n"
        ).encode(),
    }
    receipts = {}
    for name, path in (("native-query.csv", query), ("house-counties.json.gz", house_path),
                       ("state-codes.json", codes_path)):
        content = path.read_bytes()
        files["inputs/" + name] = content
        receipts[name] = dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    files["source-manifest.json"] = (json.dumps(dict(
        inputs=receipts,
        primary_reference="https://www2.census.gov/geo/tiger/TIGER2026/COUNTY/tl_2026_us_county.zip",
        reference_use="Previously qualified House county_reference() and namespace joins reused; no new Census download",
        same_round_or_independent_outcome_validation=False,
    ), indent=2, sort_keys=True) + "\n").encode()
    files["checksums.json"] = (json.dumps({
        name: dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        for name, content in sorted(files.items())}, indent=2, sort_keys=True) + "\n").encode()
    output.mkdir(parents=True)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-query", type=Path, required=True)
    parser.add_argument("--house-counties", type=Path, required=True)
    parser.add_argument("--state-codes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.native_query, args.house_counties, args.state_codes, args.output)
