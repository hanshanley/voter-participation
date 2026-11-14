import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

from shapely.geometry import shape
from shapely.strtree import STRtree
from shapely.validation import explain_validity


SOURCE_ID = "ky-jefferson-2026-native-statistics-precinct"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def pin(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def load(path):
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if body.startswith(b"\x1f\x8b") else body)


def csv_body(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def identity_pairs(features, attribute_key):
    pairs = [(feature[attribute_key]["OBJECTID"], feature[attribute_key]["PRECINCT"])
             for feature in features]
    require(all(type(oid) is int and oid >= 0 and isinstance(name, str) and name
                for oid, name in pairs), "Missing or noninteger reference identity")
    require(len(pairs) == len(set(pairs))
            and len({oid for oid, _ in pairs}) == len(pairs)
            and len({name for _, name in pairs}) == len(pairs),
            "Duplicate native reference identity")
    return set(pairs)


def build(observations, reference, expected_count, identities, native_export):
    require(reference.get("type") == "FeatureCollection"
            and not reference.get("exceededTransferLimit"), "Unqualified reference envelope")
    features = reference["features"]
    require(type(expected_count) is int and len(features) == expected_count,
            "Reference count differs from the independent native count query")
    require(not identities.get("exceededTransferLimit") and not native_export.get("exceededTransferLimit")
            and len(identities["features"]) == len(native_export["features"]) == expected_count,
            "An independent source identity/geometry query is incomplete")
    pairs = identity_pairs(features, "properties")
    require(pairs == identity_pairs(identities["features"], "attributes")
            == identity_pairs(native_export["features"], "attributes"),
            "Independent identity/native/WGS84 query pairs differ")
    names = [feature["properties"]["PRECINCT"] for feature in features]
    oids = [feature["properties"]["OBJECTID"] for feature in features]
    require(all(isinstance(name, str) and name for name in names)
            and len(names) == len(set(names)) and len(oids) == len(set(oids)),
            "Duplicate or missing native reference identity")
    native = [row for row in observations if row["source"]["id"] == SOURCE_ID]
    require(len(native) == expected_count, "Native reporting inventory differs from the reviewed scope")
    native_names = [row["geography"]["name"] for row in native]
    require(len(native_names) == len(set(native_names)), "Duplicate literal source reporting labels")
    require(all(row["count"]["status"] == "reported"
                and type(row["count"]["value"]) is int and row["count"]["value"] >= 0
                and row["geography"]["level"] == "reporting_unit" for row in native),
            "Unqualified native source observation")
    geometries = [shape(feature["geometry"]) for feature in features]
    require(all(geometry.geom_type in ("Polygon", "MultiPolygon") and not geometry.is_empty
                for geometry in geometries), "Empty or nonpolygon reference geometry")
    require(all(-180 <= geometry.bounds[0] <= geometry.bounds[2] <= 180
                and -90 <= geometry.bounds[1] <= geometry.bounds[3] <= 90
                for geometry in geometries), "Reference is not longitude/latitude geometry")
    invalid = {name: explain_validity(geometry) for name, geometry in zip(names, geometries)
               if not geometry.is_valid}
    invalid_bounds = {name: geometry.bounds for name, geometry in zip(names, geometries)
                      if name in invalid}
    valid = [index for index, name in enumerate(names) if name not in invalid]
    tree = STRtree([geometries[index] for index in valid])
    overlaps = []
    for left, index in enumerate(valid):
        for right in tree.query(geometries[index], predicate="intersects"):
            right = int(right)
            if right <= left:
                continue
            area = geometries[index].intersection(geometries[valid[right]]).area
            if area > 0:
                overlaps.append({"left_reference_code": names[index],
                                 "right_reference_code": names[valid[right]],
                                 "area_square_degrees": area})
    overlapping = {row[key] for row in overlaps
                   for key in ("left_reference_code", "right_reference_code")}
    invalid_neighbors, invalid_neighbor_pairs = set(), []
    for name, geometry in zip(names, geometries):
        if name in invalid:
            continue
        left, bottom, right, top = geometry.bounds
        for invalid_name, (x0, y0, x1, y1) in invalid_bounds.items():
            width, height = min(right, x1) - max(left, x0), min(top, y1) - max(bottom, y0)
            if width > 0 and height > 0:
                invalid_neighbors.add(name)
                invalid_neighbor_pairs.append({
                    "invalid_reference_code": invalid_name, "potential_neighbor_code": name,
                    "bbox_overlap_square_degrees": width * height,
                })
    by_name = {feature["properties"]["PRECINCT"]: feature for feature in features}
    source_by_name = {row["geography"]["name"]: row for row in native}
    decisions, eligible_features = [], []
    for row in native:
        label = row["geography"]["name"]
        reasons = []
        if label not in by_name:
            reasons.append("no_exact_literal_reference_label")
        if label in invalid:
            reasons.append("invalid_server_export_geometry")
        if label in overlapping:
            reasons.append("positive_area_overlap_in_server_export")
        if label in invalid_neighbors:
            reasons.append("potential_overlap_with_invalid_reference_bbox")
        eligible = not reasons
        decisions.append({
            "observation_id": row["id"], "native_label": label,
            "native_unit_key": row["view"]["unit_key"], "native_ballots": row["count"]["value"],
            "native_source_clock": row["source_clock"]["literal"],
            "reference_code": label if label in by_name else None,
            "candidate_reference_join_eligible": eligible,
            "hold_reasons": ";".join(reasons),
            "source_denominator": None, "analysis_rate": None,
        })
        if eligible:
            feature = by_name[label]
            eligible_features.append({
                "type": "Feature", "geometry": feature["geometry"],
                "properties": {
                    "reference_code": label, "native_label": label,
                    "observation_id": row["id"], "native_unit_key": row["view"]["unit_key"],
                    "native_ballots": row["count"]["value"],
                    "source_geometry_unrepaired": True,
                    "geometry_scope": "public_authoritative_reference_retrieved_2026_11_14_not_certified_election_day_boundary",
                    "candidate_only_not_an_approval": True,
                },
            })
    reference_decisions = [{
        "reference_code": name, "reference_objectid": oid,
        "literal_native_label": name if name in source_by_name else None,
        "native_ballots": source_by_name[name]["count"]["value"] if name in source_by_name else None,
        "valid_export_geometry": name not in invalid, "invalid_reason": invalid.get(name),
        "positive_area_overlap": name in overlapping,
        "potential_overlap_with_invalid_reference_bbox": name in invalid_neighbors,
        "literal_source_observation": name in source_by_name,
    } for name, oid in zip(names, oids)]
    summary = {
        "native_labels": len(native), "reference_features": len(features),
        "exact_literal_matches": len(set(native_names) & set(names)),
        "nonliteral_source_labels_held_without_suffix_stripping": len(set(native_names) - set(names)),
        "invalid_export_geometries": len(invalid), "positive_area_pairs": len(overlaps),
        "positive_area_pairs_are_among_valid_exports_only": True,
        "invalid_geometry_neighbors_conservatively_held": len(invalid_neighbors),
        "invalid_geometry_bbox_neighbor_pairs": len(invalid_neighbor_pairs),
        "candidate_eligible_literal_joins": len(eligible_features),
        "candidate_held_source_labels": len(native) - len(eligible_features),
        "candidate_eligible_true_zero_counts": sum(row["candidate_reference_join_eligible"]
                                                 and row["native_ballots"] == 0 for row in decisions),
        "hold_reason_counts_nonexclusive": dict(Counter(reason for row in decisions
                                                       for reason in row["hold_reasons"].split(";") if reason)),
        "suffixes_stripped_or_inferred": False, "geometries_repaired_or_clipped": False,
        "source_counts_changed": False, "denominators_rates_or_model_allocation_added": False,
        "reference_or_election_day_approval_claimed": False, "publication": False,
    }
    collection = {
        "type": "FeatureCollection", "features": eligible_features,
        "reference_scope": {
            "geometry_retrieved_at_utc": "2026-11-14T07:29:17.538470+00:00",
            "companion_map_printed_date": "2026-11-07",
            "companion_map_date_is_not_assigned_to_geometry": True,
            "election_day_legal_boundaries_certified": False,
        },
        "coverage": summary,
        "legend": (
            "Exact literal matches only; omitted reporting units are unmapped/held, not zero. "
            "All 646 counts remain available."
        ),
    }
    return {
        "complete-reference-dispositions.json": encoded({
            "source_rows": decisions, "reference_rows": reference_decisions,
            "valid_export_positive_area_pairs": overlaps,
            "invalid_geometry_neighbor_holds": invalid_neighbor_pairs,
            "summary": summary, "reference_scope": collection["reference_scope"],
            "legend": collection["legend"],
        }),
        "source-reporting-dispositions.csv": csv_body(decisions, tuple(decisions[0])),
        "reference-identity-dispositions.csv": csv_body(reference_decisions, tuple(reference_decisions[0])),
        "complete-positive-area-pairs.csv": csv_body(
            overlaps, ("left_reference_code", "right_reference_code", "area_square_degrees")),
        "complete-invalid-geometry-neighbor-holds.csv": csv_body(
            invalid_neighbor_pairs, ("invalid_reference_code", "potential_neighbor_code",
                                     "bbox_overlap_square_degrees")),
        "candidate-literal-only-reference.geojson": encoded(collection),
        "summary.json": encoded(summary),
    }


def main():
    parser = argparse.ArgumentParser(description="Review all literal reference identities without aliases or repairs.")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--native-count-query", type=Path, required=True)
    parser.add_argument("--identity-query", type=Path, required=True)
    parser.add_argument("--native-export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Use a fresh reference compilation directory")
    outputs = build(load(args.observations), load(args.reference), load(args.native_count_query)["count"],
                    load(args.identity_query), load(args.native_export))
    args.output.mkdir()
    for name, body in outputs.items():
        with (args.output / name).open("xb") as stream:
            stream.write(body)
    print(json.dumps(json.loads(outputs["summary.json"]), sort_keys=True))


if __name__ == "__main__":
    main()
