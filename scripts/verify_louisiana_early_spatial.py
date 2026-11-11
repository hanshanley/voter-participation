"""Verify new joins, complete comparisons and unchanged spatial/source payloads."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re


def verify(inputs, output):
    checks = 0

    def check(value):
        nonlocal checks
        checks += 1
        if not value:
            raise ValueError(f"Independent spatial verification failed at check{checks}")

    source = json.loads((inputs / "source-result.json").read_bytes())
    counts = json.loads(gzip.decompress((inputs / "counts-LA.json.gz").read_bytes()))
    native = json.loads((inputs / "native-index.json").read_bytes())
    reference = json.loads(gzip.decompress((inputs / "LA-reference.geojson.gz").read_bytes()))
    result = json.loads((output / "complete-result.json").read_bytes())
    geometry = json.loads((output / "complete-parish-profiles.geojson").read_bytes())
    check(hashlib.sha256((inputs / "source-result.json").read_bytes()).hexdigest()
        == "4d74f813dfad9cb4fe29518a918ce967b0bd5b91d9efaa2062dbd48290eb3e71")
    check(hashlib.sha256((inputs / "LA-reference.geojson.gz").read_bytes()).hexdigest()
        == "7eeec4d3ebb2ca1fd2897e5f914e925a3b1fb88748bc25c51bd7977bfd930eac")
    old_features = {f["properties"]["key"]: f for f in reference["features"]}
    new_features = {f["id"]: f for f in geometry["features"]}
    check(len(old_features) == len(new_features) == 64 and old_features.keys() == new_features.keys())
    bindings = {r["source_key"]: r for r in result["bindings"]}
    profiles = {r["source_key"]: r for r in source["source_profiles"] if r["scope_kind"] == "parish"}
    comparisons = {(r["source_key"], r["native_field"]): r for r in result["provider_comparisons"]}
    check(len(bindings) == len(profiles) == 64 and bindings.keys() == profiles.keys())
    check(len(comparisons) == len(result["provider_comparisons"]) == 128)
    old_records = {r["id"]: r for r in counts["records"]}
    actual_differences = {}
    for source_key, profile in profiles.items():
        decision = bindings[source_key]
        key = decision["reference_key"]
        feature, old = new_features[key], old_features[key]
        p = feature["properties"]
        check(decision["disposition"] == "qualified_contextual_name_binding")
        native_name = profile["native_label"].rsplit("-", 1)[0].upper()
        ref_name = old["properties"]["name"].upper().removesuffix(" PARISH")
        check("".join(c for c in native_name if c.isalnum()) == "".join(c for c in ref_name if c.isalnum()))
        check(decision["native_code_is_FIPS"] is False)
        check(decision["reference_is_context_not_election_boundary"] is True)
        check(p["binding"] == decision and p["reference"] == old["properties"])
        check(feature["geometry"] == old["geometry"])
        check(p["native_source_profile"] == profile)
        check(profile["geographic_FIPS"] is profile["approved_map_reference"] is None)
        check(profile["group_turnout_rate"] is profile["registered_population"] is None)
        check(profile["native_ABS_relabelled_mail_returned"] is False)
        for field, mode in (("INPER", "in_person_early"), ("ABS", "mail_returned")):
            row = comparisons[source_key, field]
            accepted = old_records[row["provider_observation_id"]]
            check(accepted["id"] in counts["views"][mode]["counties"])
            check(accepted["view"]["county_fips"] == key)
            check(accepted["view"]["county_id"] == decision["county_id"])
            check(row["provider_count"] == accepted["count"]["value"])
            check(row["native_count"] == profile["raw_counts"][field])
            difference = profile["raw_counts"][field] - accepted["count"]["value"]
            check(row["native_minus_provider"] == difference)
            check(row["provider_source_clock"] == accepted["source_clock"])
            check(row["native_source_print_clock"] == profile["source_print_clock"])
            check(row["native_source_print_timezone"] is None and row["native_filter_end"] == "2026-11-09")
            for flag in ("independent_validation", "population_equivalence_qualified",
                    "method_equivalence_qualified", "clock_equivalence_qualified", "automatic_source_replacement"):
                check(row[flag] is False)
            check(row["difference_reason"] is None)
            check(row["disposition"] == ("equal_numeric_value_only" if difference == 0 else "different_numeric_value_preserved"))
            if difference:
                actual_differences[profile["native_label"], field] = difference
        own = [r for r in source["group_compositions"] if r["source_key"] == source_key]
        accounts = [r for r in source["margin_accounting"] if r["source_key"] == source_key]
        check(p["native_compositions"] == own and len(own) == 7)
        check(p["reference_key"] == key and p["reference_name"] == old["properties"]["name"])
        for row in own:
            check(p[row["native_group"] + "_count"] == row["native_count"])
            check(p[row["native_group"] + "_report_share_pct"] == float(row["source_composition_pct"]))
        check(p["native_margin_accounting"] == accounts and len(accounts) == 4)
        for table, originals in (("spatial_group_compositions", own), ("spatial_margin_accounting", accounts)):
            rows = [r for r in result[table] if r["source_key"] == source_key]
            check(len(rows) == len(originals))
            for actual, original in zip(rows, originals):
                check({k: v for k, v in actual.items() if not k.startswith("reference_")} == original)
                check(actual["reference_key"] == key and actual["reference_name"] == old["properties"]["name"])
    check(actual_differences == {("BOSSIER-08", "ABS"): -1, ("EAST FELICIANA-19", "INPER"): 1,
        ("JEFFERSON-26", "ABS"): 4, ("LAFAYETTE-28", "ABS"): 1})
    parent = next(r for r in source["source_profiles"] if r["scope_kind"] == "state_parent")
    check(geometry["source_state_parent"] == parent and parent["source_votes"] == 536190)
    check(geometry["source_state_compositions"] == [r for r in source["group_compositions"] if r["scope_kind"] == "state_parent"])
    check(geometry["unbound_source_profiles"] == [])
    check(len(result["reference_coverage"]) == 64)
    for row in result["reference_coverage"]:
        check(row["disposition"] == "bound_native_source" and len(row["bound_source_keys"]) == 1)
        check(bindings[row["bound_source_keys"][0]]["reference_key"] == row["reference_key"])
    check(result["source_state_coverage"] == source["state_coverage"])
    check(native["county_bindings"]["LA"]["in_person_early"]["feature_keys"] == list(old_features))
    summary = result["summary"]
    for key, value in dict(qualified_contextual_bindings=64, equal_numeric_pairs=124,
            differing_numeric_pairs=4, spatial_group_compositions=448, spatial_margin_accounts=256,
            source_sex_residual=278, geometry_changes=0, source_count_changes=0,
            group_turnout_rates_inferred=0, live_dataset_or_frontend_activation=False).items():
        check(summary[key] == value)
    for key in ("bindings", "provider_comparisons", "spatial_group_compositions",
            "spatial_margin_accounting", "reference_coverage", "source_state_coverage"):
        rows = result[key]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted({k for r in rows for k in r}), lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True, separators=(",", ":"))
            if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows)
        check((output / ("complete-" + key.replace("_", "-") + ".csv")).read_bytes() == stream.getvalue().encode())
    check(json.loads((output / "summary.json").read_bytes()) == summary)
    check(gzip.decompress((output / "complete-parish-profiles.geojson.gz").read_bytes())
        == (output / "complete-parish-profiles.geojson").read_bytes())
    html = (output / "louisiana-early-group-map.html").read_text()
    embedded = re.search(r'<script id="source-data" type="application/json">(.*?)</script>', html, re.S)
    check(embedded is not None and json.loads(embedded[1]) == geometry)
    check("fetch(" not in html and not re.search(
        r'<(?:script|img|link|iframe)\b[^>]*\b(?:src|href)\s*=\s*["\']https?:', html, re.I))
    return dict(status="passed_independent_louisiana_spatial_queries", checks=checks,
        exact_name_bindings=64, unchanged_geometry_features=64, provider_comparisons=128,
        numeric_matches=124, numerical_differences=4, copied_source_compositions=448,
        copied_margin_accounts=256, no_existing_count_or_clock_semantics_changed=True,
        all_complete_result_query_map_bytes_checked=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.inputs, args.results), sort_keys=True))
