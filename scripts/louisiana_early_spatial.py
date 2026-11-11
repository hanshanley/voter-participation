"""Bind accepted native group compositions to unchanged contextual parish geometry."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re


SOURCE_SCIENCE = "f788b1d388d52efbba78121513cd16c82445c2ad4acd89fb8f9bb44379708bfe"
RUNTIME_SCIENCE = "9e753a4f8b363713f9752ba4448993250d9e49eaff68b196b20f0d72cc42e285"
REFERENCE_SHA = "7eeec4d3ebb2ca1fd2897e5f914e925a3b1fb88748bc25c51bd7977bfd930eac"
COUNT_VERSION = "d63083706c7a4b7c8e912dae24503bee068181db9f85183c0ecf8926562c6997"
NATIVE_VERSION = "67d36be354685dbd75e1ad7cd0fda4eaeaa57fcdd605029f292ae4d4d3f460bf"
MODES = (("in_person_early", "INPER"), ("mail_returned", "ABS"))
NOTES = [
    "Counts and shares describe this source-defined early/absentee report, not full-election turnout or unique people.",
    "Shares use own native VOTES, not registrations or a classified-sex subtotal; group turnout remains unknown.",
    "Race, sex and method are separate margins, not joint populations or standardized CPS/resident categories.",
    "Sex residuals are unallocated arithmetic, not an identified sex or nonvoter category.",
    "ABS remains the native source label, not a qualification as mail-returned activity.",
    "The 2026 Census county reference is contextual geography, not certified election precinct boundaries.",
    "Provider and official-source clocks/populations are not established equivalent; numeric matches are not independent validation.",
    "No existing live count, map geometry, model or dataset catalog is changed.",
]


def encoded(value, compact=False):
    return (json.dumps(value, sort_keys=True, allow_nan=False,
        **({"separators": (",", ":")} if compact else {"indent": 2})) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def file_pin(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return dict(bytes=path.stat().st_size, sha256=digest.hexdigest())


def name_key(name):
    return re.sub("[^A-Z0-9]", "", re.sub(r"\s+Parish$", "", name, flags=re.I).upper())


def load_inputs(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    if manifest["contract"] != "participation.louisiana_early_spatial_inputs.v1":
        raise ValueError("Unknown frozen spatial inputs")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or file_pin(root / name) != expected:
            raise ValueError("Changed or unsafe sufficient input")
    data = {key: json.loads((root / filename).read_bytes()) for key, filename in (
        ("source", "source-result.json"), ("facts", "source-native-facts.json"),
        ("counts_index", "counts-index.json"), ("count_dataset", "counts-dataset.json"),
        ("native", "native-index.json"), ("native_dataset", "native-dataset.json"),
        ("policy", "policy.json"), ("provenance", "provenance.json"))}
    for key, filename in (("counts", "counts-LA.json.gz"), ("reference", "LA-reference.geojson.gz")):
        data[key] = json.loads(gzip.decompress((root / filename).read_bytes()))
    if (pin((root / "LA-reference.geojson.gz").read_bytes())["sha256"] != REFERENCE_SHA
            or data["count_dataset"]["version"] != COUNT_VERSION
            or data["native_dataset"]["version"] != NATIVE_VERSION
            or pin((root / "source-result.json").read_bytes())["sha256"]
                != "4d74f813dfad9cb4fe29518a918ce967b0bd5b91d9efaa2062dbd48290eb3e71"):
        raise ValueError("Changed accepted source, count runtime or reference")
    for dataset, filename, local in (("count_dataset", "states/LA.json.gz", "counts-LA.json.gz"),
            ("count_dataset", "index.json", "counts-index.json"),
            ("native_dataset", "index.json", "native-index.json")):
        if data[dataset]["files"][filename] != pin((root / local).read_bytes()):
            raise ValueError("Changed accepted runtime member")
    if (manifest["complete_predecessors"]["complete-native-science.zip"]["sha256"] != SOURCE_SCIENCE
            or manifest["complete_predecessors"]["complete-runtime-science.zip"]["sha256"] != RUNTIME_SCIENCE):
        raise ValueError("Changed complete predecessor declarations")
    return data


def build(data):
    source, counts, native, reference = (data[key] for key in ("source", "counts", "native", "reference"))
    if (data["policy"]["contract"] != "participation.louisiana_early_spatial_policy.v1"
            or data["policy"]["binding"] != "unique_native_parish_name_to_accepted_context_reference"
            or any(data["policy"][key] is not False for key in (
                "native_codes_inferred_as_FIPS", "counts_replaced", "geometry_repaired",
                "election_boundaries_certified", "provider_method_or_clock_requalified",
                "group_turnout_inferred", "frontend_or_catalog_activation"))):
        raise ValueError("Unqualified change to spatial source scope")
    if (counts["state_code"] != "LA" or counts["year"] != 2026
            or source["contract"] != "participation.louisiana_early_group_compositions.v1"
            or len(reference["features"]) != 64):
        raise ValueError("Changed source/reference frame")
    binding = native["county_bindings"]["LA"]["in_person_early"]
    if binding["sha256"] != REFERENCE_SHA:
        raise ValueError("Changed qualified reference identity")
    features = {str(f["properties"]["key"]): f for f in reference["features"]}
    if len(features) != 64 or set(features) != set(binding["feature_keys"]):
        raise ValueError("Duplicate or incomplete contextual reference")
    approved = {row["feature_key"]: row for row in binding["rows"]}
    if len(approved) != 64:
        raise ValueError("Incomplete accepted reference bindings")
    by_name = {}
    for key, feature in features.items():
        p, scope, row = feature["properties"], binding["feature_scopes"][key], approved[key]
        if (p["state_code"] != "LA" or p["boundary_year"] != 2026
                or scope != {k: p[k] for k in ("state_code", "name", "boundary_year")}
                or row["qualifier"]["county_fips"] != key
                or row["qualifier"]["state_code"] != "LA"
                or row["qualifier"]["county"] != p["name"]):
            raise ValueError("Changed accepted reference scope")
        by_name.setdefault(name_key(p["name"]), []).append(key)
    by_id = {row["id"]: row for row in counts["records"]}
    selected = {}
    for mode, _ in MODES:
        ids = counts["views"][mode]["counties"]
        rows = [by_id[rid] for rid in ids]
        selected[mode] = {row["view"]["county_fips"]: row for row in rows}
        if len(rows) != len(selected[mode]) or len(rows) != 64:
            raise ValueError("Changed accepted provider frame")
    profiles = [row for row in source["source_profiles"] if row["scope_kind"] == "parish"]
    parent = [row for row in source["source_profiles"] if row["scope_kind"] == "state_parent"]
    if len(profiles) != 64 or len(parent) != 1 or len({p["source_key"] for p in profiles}) != 64:
        raise ValueError("Incomplete accepted native profiles")
    native_names = [name_key(p["native_label"].rsplit("-", 1)[0]) for p in profiles]
    bindings, comparisons, compositions, accounting, mapped = [], [], [], [], []
    for profile in profiles:
        label, code = profile["native_label"], profile["native_code"]
        if not label.endswith("-" + code):
            raise ValueError("Native label/code disagreement")
        normalized = name_key(label[:-(len(code) + 1)])
        candidates = by_name.get(normalized, [])
        status = ("qualified_contextual_name_binding" if len(candidates) == 1 else
            "held_no_reference_name_match" if not candidates else "held_ambiguous_reference_name")
        key = candidates[0] if len(candidates) == 1 else None
        if native_names.count(normalized) != 1:
            status, key = "held_ambiguous_native_name", None
        if key and any(selected[mode][key]["view"]["county_id"] != approved[key]["county_id"]
                or name_key(selected[mode][key]["geography"]["name"])
                    != name_key(features[key]["properties"]["name"]) for mode, _ in MODES):
            status, key = "held_provider_identity_conflict", None
        decision = dict(source_key=profile["source_key"], native_label=label, native_code=code,
            disposition=status, reference_key=key,
            reference_name=features[key]["properties"]["name"] if key else None,
            county_id=approved[key]["county_id"] if key else None,
            state_code="LA", boundary_year=2026, reference_sha256=REFERENCE_SHA,
            native_code_is_FIPS=False, reference_is_context_not_election_boundary=True,
            numeric_agreement_required_for_name_binding=False)
        bindings.append(decision)
        if key is None:
            continue
        for mode, field in MODES:
            old = selected[mode][key]
            value = old["count"]["value"]
            difference = profile["raw_counts"][field] - value if value is not None else None
            comparisons.append(dict(source_key=profile["source_key"], reference_key=key,
                native_label=label, native_field=field, native_count=profile["raw_counts"][field],
                provider_mode=mode, provider_observation_id=old["id"],
                provider_count=value, provider_count_status=old["count"]["status"],
                native_minus_provider=difference,
                disposition="equal_numeric_value_only" if difference == 0 else
                    "different_numeric_value_preserved" if difference is not None else "held_provider_missing_count",
                native_source_print_clock=profile["source_print_clock"],
                native_source_print_timezone=profile["source_print_timezone"],
                native_filter_begin=profile["report_filter_begin"], native_filter_end=profile["report_filter_end"],
                provider_source_clock=old["source_clock"], provider_source_date=old["view"]["source_date"],
                provider_source_url=old["view"]["source_url"], difference_reason=None,
                independent_validation=False, population_equivalence_qualified=False,
                method_equivalence_qualified=False, clock_equivalence_qualified=False,
                automatic_source_replacement=False))
        shared = dict(reference_key=key, reference_name=decision["reference_name"], reference_sha256=REFERENCE_SHA)
        own_compositions = [row for row in source["group_compositions"] if row["source_key"] == profile["source_key"]]
        own_accounts = [row for row in source["margin_accounting"] if row["source_key"] == profile["source_key"]]
        if len(own_compositions) != 7 or len(own_accounts) != 4:
            raise ValueError("Incomplete accepted source margins")
        compositions.extend(dict(**row, **shared) for row in own_compositions)
        accounting.extend(dict(**row, **shared) for row in own_accounts)
        flat = {field: value for row in own_compositions for field, value in (
            (row["native_group"] + "_count", row["native_count"]),
            (row["native_group"] + "_report_share_pct",
                float(row["source_composition_pct"]) if row["source_composition_pct"] is not None else None))}
        mapped.append(dict(type="Feature", id=key, geometry=features[key]["geometry"],
            properties=dict(**flat, reference_key=key, reference_name=decision["reference_name"],
                reference=features[key]["properties"], binding=decision,
                native_source_profile=profile, native_compositions=own_compositions,
                native_margin_accounting=own_accounts)))
    reference_coverage = [dict(reference_key=key, reference_name=features[key]["properties"]["name"],
        bound_source_keys=[row["source_key"] for row in bindings if row["reference_key"] == key],
        disposition="bound_native_source" if any(row["reference_key"] == key for row in bindings)
            else "no_qualified_native_binding") for key in sorted(features)]
    geojson = dict(type="FeatureCollection", features=mapped, source_state_parent=parent[0],
        source_state_compositions=[row for row in source["group_compositions"] if row["scope_kind"] == "state_parent"],
        source_state_margin_accounting=[row for row in source["margin_accounting"] if row["scope_kind"] == "state_parent"],
        unbound_source_profiles=[p for p, b in zip(profiles, bindings) if b["reference_key"] is None],
        scope_notes=NOTES, provenance=data["provenance"],
        gis_numeric_share_representation="binary floats copied from accepted exact decimal strings; originals retained in native_compositions and CSV")
    summary = dict(native_parishes=64, source_binding_decisions=len(bindings),
        qualified_contextual_bindings=len(mapped), held_source_bindings=64-len(mapped),
        provider_numeric_comparisons=len(comparisons),
        equal_numeric_pairs=sum(row["native_minus_provider"] == 0 for row in comparisons),
        differing_numeric_pairs=sum(row["native_minus_provider"] not in (0, None) for row in comparisons),
        missing_provider_counts=sum(row["native_minus_provider"] is None for row in comparisons),
        spatial_group_compositions=len(compositions), spatial_margin_accounts=len(accounting),
        reference_coverage_decisions=len(reference_coverage), source_state_coverage_decisions=51,
        source_state_votes=parent[0]["source_votes"], source_sex_residual=next(
            row["signed_arithmetic_residual"] for row in geojson["source_state_margin_accounting"] if row["dimension"] == "sex"),
        geometry_changes=0, source_count_changes=0, group_turnout_rates_inferred=0,
        original_reductions_repeated=False, live_dataset_or_frontend_activation=False)
    result = dict(contract="participation.louisiana_early_spatial.v1", summary=summary,
        policy=data["policy"], provenance=data["provenance"], scope_notes=NOTES,
        bindings=bindings, provider_comparisons=comparisons, spatial_group_compositions=compositions,
        spatial_margin_accounting=accounting, reference_coverage=reference_coverage,
        source_state_coverage=source["state_coverage"])
    return result, geojson


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    flattened = [{k: json.dumps(v, sort_keys=True, separators=(",", ":"))
        if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows]
    writer = csv.DictWriter(stream, fieldnames=sorted({k for row in rows for k in row}), lineterminator="\n")
    writer.writeheader()
    writer.writerows(flattened)
    return stream.getvalue().encode()


def result_files(result, geojson):
    geometry = encoded(geojson, compact=True)
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0, compresslevel=9) as archive:
        archive.write(geometry)
    template = (Path(__file__).parent / "templates/louisiana-early-group-map.html").read_text()
    html = template.replace("__COMPLETE_GEOJSON__", geometry.decode().replace("<", "\\u003c")).encode()
    tables = ("bindings", "provider_comparisons", "spatial_group_compositions",
        "spatial_margin_accounting", "reference_coverage", "source_state_coverage")
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
        "complete-parish-profiles.geojson": geometry, "complete-parish-profiles.geojson.gz": stream.getvalue(),
        "louisiana-early-group-map.html": html,
        **{"complete-" + key.replace("_", "-") + ".csv": csv_bytes(result[key]) for key in tables}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    result, geojson = build(load_inputs(args.inputs))
    args.output.mkdir(parents=True)
    for name, body in result_files(result, geojson).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"], sort_keys=True))
