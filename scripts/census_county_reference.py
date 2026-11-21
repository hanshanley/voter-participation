"""Build dated display county geometry from pinned Census TIGERweb responses."""

import argparse
import gzip
import json
from pathlib import Path
import re

from scripts.participation_intake.contract import encoded, pin


def build(original, year, state, fips, roster, tolerance=0.002):
    from shapely import coverage_is_valid, coverage_simplify
    from shapely.geometry import mapping, shape

    raw = json.loads(original)
    if raw.get("type") != "FeatureCollection" or not 0 < len(raw["features"]) == len(roster):
        raise ValueError("Incomplete Census county response")
    items, names = {}, set()
    for feature in raw["features"]:
        prop = feature["properties"]
        key, name = prop["GEOID"], prop["BASENAME"]
        if (feature.get("type") != "Feature" or prop["STATE"] != fips
                or not re.fullmatch(f"{fips}[0-9]{{3}}", key)
                or key in items or name not in roster or name in names):
            raise ValueError("Census county identity differs")
        items[key] = name, shape(feature["geometry"])
        names.add(name)
    keys = sorted(items)
    geometry = [items[key][1] for key in keys]

    def valid(geometries):
        return all(not g.is_empty and g.is_valid and g.area > 0
                   and g.geom_type in {"Polygon", "MultiPolygon"} for g in geometries) and coverage_is_valid(geometries)

    if not valid(geometry):
        raise ValueError("Census county original is not a valid polygon coverage")
    display = coverage_simplify(geometry, tolerance)
    if not valid(display):
        raise ValueError("Census display simplification introduced invalid coverage")
    return gzip.compress(encoded({
        "type": "FeatureCollection", "reference_date": f"{year}-01-01",
        "source_sha256": pin(original)["sha256"], "display_only": True,
        "features": [{
            "type": "Feature", "properties": {"state_code": state, "level": "county", "key": key,
                                              "name": items[key][0], "boundary_year": year},
            "geometry": mapping(polygon),
        } for key, polygon in zip(keys, display, strict=True)],
    }), mtime=0)


def reproduce(originals, manifest, output):
    state, fips, names = (manifest[key] for key in ("state", "state_fips", "counties"))
    if (not re.fullmatch(r"[A-Z]{2}", state) or not re.fullmatch(r"[0-9]{2}", fips)
            or len(names) != len(set(names))):
        raise ValueError("Invalid Census requested identity")
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for edition, source in sorted(manifest["vintages"].items()):
        if not re.fullmatch(r"20\d{2}", edition):
            raise ValueError("Invalid Census boundary vintage")
        original = (originals / f"{edition}.geojson").read_bytes()
        if not 0 < len(original) <= 16_000_000 or pin(original) != {key: source[key] for key in ("bytes", "sha256")}:
            raise ValueError(f"Census geometry original differs from pin: {edition}")
        file = f"county-{state}-{edition}.geojson.gz"
        body = build(original, int(edition), state, fips, set(names))
        (output / file).write_bytes(body)
        result[file] = {**pin(body), "reference_date": f"{edition}-01-01"}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("originals", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.originals, json.loads(args.manifest.read_bytes()), args.output), indent=2))
