"""Verify and draw a dated county precinct reference against native NM totals."""

import argparse
import csv
import json
import re
from hashlib import sha256
from html import escape
from pathlib import Path

from pyproj import Transformer
from shapely import transform
from shapely.geometry import shape

from scripts.nc_precinct_reference import display_paths, topology


COUNTY = "San Juan"
FIPS = "35045"
COUNT = 113
GEOMETRY_SHA = "395e825881ce7bb683f5c2047f34037312d60e666d626e8dc5f2555e3a510d4c"


def bind(features, facts, *, county=COUNTY, fips=FIPS, expected=COUNT):
    rows = [r for r in facts if r.get("county") == county and r["geography_level"] == "reporting_unit"]
    parents = [r for r in facts if r.get("county") == county and r["geography_level"] == "county"]
    if len(parents) != 1 or len(rows) != expected or len(features) != expected:
        raise ValueError("Incomplete county reporting or geometry roster")
    parent, = parents
    counts = {}
    for row in rows:
        match = re.fullmatch(r"PRECINCT (\d{3})", row["unit"])
        if (match is None or match[1] in counts or row["county_id"] != parent["county_id"]
                or row["source_clock"] != parent["source_clock"]
                or any(type(row[k]) is not int or row[k] < 0 for k in ("count", "registered"))
                or row["count"] > row["registered"]):
            raise ValueError("Incompatible or duplicate native precinct")
        counts[match[1]] = row
    if any(sum(r[field] for r in rows) != parent[field] for field in ("count", "registered")):
        raise ValueError("Native precinct counts do not reconcile to the county")
    project = Transformer.from_crs(4326, 26913, always_xy=True).transform
    shapes, source, ambiguous = {}, {}, set()
    for feature in features:
        p = feature["properties"]
        key = f'{p["Pct2026"]:03d}'
        if (feature["type"] != "Feature" or key in source or p["State"] != fips[:2]
                or not re.fullmatch(r"\d{1,3}", p["County"]) or p["County"].zfill(3) != fips[2:]
                or not re.fullmatch(r"\d{1,3}", p["PctTxt"]) or p["PctTxt"].zfill(3) != key):
            raise ValueError("Incompatible or duplicate county GIS identity")
        legacy = p["PctCode"].strip()
        if legacy and legacy != fips + key:
            ambiguous.add(key)
            if re.fullmatch(fips + r"\d{3}", legacy):
                ambiguous.add(legacy[-3:])
        source[key] = p
        geometry = shape(feature["geometry"])
        if geometry.geom_type in {"Polygon", "MultiPolygon"} and geometry.is_valid and not geometry.is_empty:
            projected = transform(geometry, project, interleaved=False)
            if projected.is_valid and not projected.is_empty:
                shapes[(county, key)] = projected
    if set(source) != set(counts):
        raise ValueError("County GIS and November reporting rosters differ")
    overlapping = topology(shapes) if shapes else {}
    decisions = []
    for key in sorted(counts):
        native, gis = counts[key], source[key]
        shape_key = (county, key)
        status = ("conflicting_compound_code" if key in ambiguous
                  else "invalid_geometry" if shape_key not in shapes
                  else "overlapping_geometry" if shape_key in overlapping
                  else "reference_count_only")
        decisions.append({
            "county_fips": fips, "county": county, "precinct": key, "native_unit": native["unit"],
            "source_clock": native["source_clock"], "native_reported_participants": native["count"],
            "native_eligible_voters": native["registered"], "gis_object_id": gis["OBJECTID"],
            "gis_compound_code": gis["PctCode"], "gis_split_from_1": gis["Split_fr1"],
            "gis_split_from_2": gis["Split_fr2"], "decision": status,
        })
    return decisions, shapes


def draw(decisions, shapes):
    rows = {r["precinct"]: r for r in decisions}
    safe = [r for r in decisions if r["decision"] == "reference_count_only"]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 420" role="img" aria-labelledby="title description">',
        '<title id="title">San Juan County reported participation, November 2026</title>',
        f'<desc id="description">{len(safe)} of {len(rows)} precincts shaded by counts, not rates. '
        'County 2026 reference boundaries. See the accompanying evidence table.</desc>',
        '<rect width="960" height="420" fill="white"/>',
        '<text x="20" y="27" font-size="22">San Juan County · reported participation, November 2026</text>',
        f'<text x="20" y="50" font-size="14">County 2026 precinct reference · {len(safe)} of {len(rows)} reporting units shaded</text>',
    ]
    colors = ("#d5e4e9", "#9ebfca", "#5d96a8", "#2c697d", "#174c60")
    for (_, key), path in display_paths(shapes):
        row = rows[key]
        n = row["native_reported_participants"]
        accepted = row["decision"] == "reference_count_only"
        title = f'Precinct {key}: {n:,} reported participants' if accepted else f'Precinct {key}: withheld'
        fill = colors[sum(n >= cut for cut in (100, 250, 500, 750))] if accepted else "#eceeef"
        lines.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd" stroke="#68828a" '
                     f'stroke-width=".18"><title>{escape(title)}</title></path>')
    for i, label in enumerate(("Under 100", "100–249", "250–499", "500–749", "750 or more")):
        x = 20 + i * 139
        lines.append(f'<rect x="{x}" y="391" width="17" height="12" fill="{colors[i]}"/>'
                     f'<text x="{x+22}" y="402" font-size="13">{label}</text>')
    lines.append('<text x="725" y="402" font-size="13">Gray: withheld, not zero</text></svg>')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.geometry.read_bytes()
    if sha256(original).hexdigest() != GEOMETRY_SHA:
        raise ValueError("San Juan reference edition changed")
    decisions, shapes = bind(json.loads(original)["features"], json.loads(args.facts.read_bytes()))
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "precinct-decisions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=decisions[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(decisions)
    (args.output / "precinct-participation.svg").write_text(draw(decisions, shapes))


if __name__ == "__main__":
    main()
