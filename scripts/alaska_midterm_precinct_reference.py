"""Reproduce the strict 2022 Alaska Election Day precinct reference map."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import re

from pyproj import Transformer, network
from shapely import transform
from shapely.geometry import shape
from shapely.strtree import STRtree

from scripts.alaska_midterm_district_map import build as district_map
from scripts.alaska_precinct_history import MIDTERM_FEED, midterm_exports
from scripts.supported_analytical_release import csv_bytes


SOURCE = "https://maps.commerce.alaska.gov/server/rest/services/Govt_Related/Govt_House_and_Senate_Districts/MapServer/4"
NOTICE = "https://aws.state.ak.us/OnlinePublicNotices/Notices/View.aspx?id=208191"
VINTAGE = 1653379200000  # 2022-05-24, Alaska DCRA's AsOfDate
TOLERANCE_M2 = 1
COLORS = ("#dce9ef", "#afcedd", "#74a7bc", "#3b7c98", "#174761")
LIMITS = (100, 250, 500, 1000)
PINS = {
    "state-roster.json": "081c23b168ac33de291dbe0e7b2afb5d90e81062f68fcc0a3e8cc00f3ad95c35",
    "state-object-ids.json": "b54bb0ee0171326d1361cf08dd9b19cbe363daf4dc179495906668dcef9f6c26",
    "state-precinct-geometry.geojson": "8f8def72d205048a59c0aa61a5962ba02b6f45b925f0b8d9e7cd85cd2a66508b",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized(label):
    return re.sub(r"\s*[/\-]\s*", "-", label.strip().casefold())


def audit(facts, roster, ids, geometry, district_bytes):
    rows = {r["source_unit_id"]: r for r in midterm_exports(facts) if r["source_unit_id"]}
    members = [r["attributes"] for r in roster["features"]]
    feature_ids = [r["OBJECTID"] for r in members]
    require(len(rows) == len(members) == len(set(feature_ids)) == 401
            and len(ids["objectIds"]) == 401 and set(ids["objectIds"]) == set(feature_ids)
            and not any(x.get("exceededTransferLimit") for x in (geometry, roster)),
            "Incomplete official Alaska precinct object inventory")
    by_id = {r["OBJECTID"]: r for r in members}
    require(geometry["type"] == "FeatureCollection", "Missing Alaska precinct geometry collection")
    network.set_network_enabled(False)
    project = Transformer.from_crs(4326, 3338, always_xy=True).transform
    parents = {f["id"]: transform(shape(f["geometry"]), project, interleaved=False)
               for f in json.loads(district_bytes)["features"]}
    seen, by_code, projected, issues, outside, overlap = set(), {}, {}, {}, {}, {}
    for feature in geometry["features"]:
        props = feature["properties"]
        oid = props["OBJECTID"]
        label = props["Precinct_Name"]
        match = re.fullmatch(r"(\d{2}-\d{3}) .+", label)
        code = match[1] if match else ""
        require(oid not in seen and props == by_id.get(oid) and code in rows and code not in by_code
                and props["AsOfDate"] == VINTAGE and props["HouseDistrict"] == int(rows[code]["district"])
                and normalized(label) == normalized(rows[code]["reporting_unit"]),
                "Alaska precinct geometry differs from the dated reporting roster")
        seen.add(oid)
        by_code[code] = feature
        polygon = shape(feature["geometry"])
        issues[code] = set()
        overlap[code] = {}
        if (polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid):
            issues[code].add("invalid_source_polygon")
            continue
        local = transform(polygon, project, interleaved=False)
        if not local.is_valid or local.is_empty:
            issues[code].add("invalid_projected_polygon")
            continue
        projected[code] = local
        outside_area = local.difference(parents[props["HouseDistrict"]]).area
        outside[code] = (round(outside_area, 3), round(100 * outside_area / local.area, 6))
        if outside_area > TOLERANCE_M2:
            issues[code].add("outside_interim_house_district")
    require(seen == set(by_id) and by_code.keys() == rows.keys(), "Alaska precinct geometry inventory differs")
    keys, values = list(projected), list(projected.values())
    tree = STRtree(values)
    for i, current in enumerate(values):
        for j in tree.query(current, predicate="intersects"):
            if j <= i:
                continue
            area = current.intersection(values[j]).area
            if area > TOLERANCE_M2:
                issues[keys[i]].add("overlapping_precinct_polygon")
                issues[keys[j]].add("overlapping_precinct_polygon")
                overlap[keys[i]][keys[j]] = overlap[keys[j]][keys[i]] = round(area, 3)
    decisions, eligible = [], []
    for code, row in sorted(rows.items()):
        props = by_code[code]["properties"]
        outside_m2, outside_percent = outside.get(code, (None, None))
        detail = {
            "precinct_code": code, "reporting_unit": row["reporting_unit"], "gis_name": props["Precinct_Name"],
            "gis_object_id": props["OBJECTID"],
            "house_district": props["HouseDistrict"], "election_day_ballots": row["reported_ballots"],
            "outside_district_m2": outside_m2, "outside_district_percent": outside_percent,
            "overlaps_m2_by_code": ";".join(f"{key}={value}" for key, value in sorted(overlap[code].items())),
            "map_qualified": not issues[code],
            "issues": ";".join(sorted(issues[code])),
        }
        decisions.append(detail)
        if not issues[code]:
            eligible.append({"type": "Feature", "id": code, "properties": detail,
                             "geometry": by_code[code]["geometry"]})
    return decisions, eligible, projected


def render(rows, polygons, central):
    visible = [r for r in rows if r["map_qualified"]]
    mapped_spots = [polygons[r["precinct_code"]] for r in visible]
    bounds = [g.bounds for g in mapped_spots]
    x0, y0 = min(b[0] for b in bounds), min(b[1] for b in bounds)
    x1, y1 = max(b[2] for b in bounds), max(b[3] for b in bounds)
    scale = min(730 / (x1 - x0), 400 / (y1 - y0))
    dx, dy = (750 - (x1 - x0) * scale) / 2, (420 - (y1 - y0) * scale) / 2
    svg, table = [], []
    for row in rows:
        name, ballots = html.escape(row["reporting_unit"]), row["election_day_ballots"]
        label = "Mapped reference" if row["map_qualified"] else row["issues"].replace("_", " ").replace(";", "; ")
        table.append(f'<tr><th scope="row">{name}</th><td>{ballots:,}</td><td>{label}</td></tr>')
        if row["map_qualified"]:
            g = polygons[row["precinct_code"]]
            parts = g.geoms if g.geom_type == "MultiPolygon" else [g]
            path = "".join(
                "M" + "L".join(f"{dx+(x-x0)*scale:.1f},{dy+(y1-y)*scale:.1f}" for x, y in ring.coords) + "Z"
                for part in parts for ring in [part.exterior, *part.interiors])
            svg.append(f'<path fill="{COLORS[sum(ballots >= k for k in LIMITS)]}" d="{path}">'
                       f"<title>{name}: {ballots:,} Election Day ballots</title></path>")
    legend = " &middot; ".join(f'<span style="color:{color}">&#9632;</span> {label}' for color, label in
                              zip(COLORS, ("Below 100", "100–249", "250–499", "500–999", "1,000 or more")))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Alaska 2022 Election Day ballots</title>
<style>body{{font:1rem/1.5 system-ui,sans-serif;color:#142c39;margin:auto;padding:1rem;max-width:54rem}}
svg{{width:100%;height:auto}}path{{stroke:#edf4f6;stroke-width:.35;fill-rule:evenodd}}table{{width:100%;border-collapse:collapse}}
td,th{{border-bottom:1px solid #ccd7db;padding:.25rem;text-align:left}}td:nth-child(2){{text-align:right}}caption{{text-align:left}}</style>
<main><h1>Alaska 2022 Election Day ballots by precinct</h1>
<p>November 8, 2022. State GIS reference dated May 24, 2022. Shading shows Election Day counts, not rates.
{len(visible):,} of {len(rows):,} precincts are mapped, representing
{sum(r["election_day_ballots"] for r in visible):,} Election Day ballots. The
{sum(r["election_day_ballots"] for r in rows if not r["map_qualified"]):,} ballots in held precincts
remain in the table; unshaded areas are not zero turnout.
{central:,} central and overseas ballots are not assigned to a home precinct.</p>
<svg viewBox="0 0 750 420" role="img" aria-labelledby="map-title">
<title id="map-title">Election Day ballot counts in matched Alaska precinct references.</title>{''.join(svg)}</svg><p>{legend}</p>
<p>Geometry: <a href="{SOURCE}">Alaska DCCED DCRA and Division of Elections</a>. This informational layer is not
the <a href="{NOTICE}">adopted legal boundary record</a>. Shapes are not clipped or repaired.
The map tests identity, validity, overlap between valid polygons, and containment in the interim district plan.
The area checks allow one square meter of numerical noise; shapes that exceed it are held.</p>
<table><caption>All official Election Day precinct counts, including withheld shapes</caption>
<thead><tr><th scope="col">Reporting unit</th><th scope="col">Ballots</th><th scope="col">Map status</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></main></html>
"""


def outputs(facts, roster, ids, geometry, interim):
    district_bytes = district_map(interim, facts)["ak-2022-house-district-turnout.geojson"]
    decisions, eligible, projected = audit(facts, roster, ids, geometry, district_bytes)
    require(bool(eligible), "No Alaska precinct polygons passed the reference checks")
    statewide = facts[MIDTERM_FEED]["data"]["control"]["ballots"]
    election_day = sum(row["election_day_ballots"] for row in decisions)
    central = statewide - election_day
    counts = {"statewide_ballots": statewide, "central_and_overseas_ballots": central,
              "election_day_ballots": election_day, "reported_precincts": len(decisions),
              "mapped_precincts": len(eligible), "held_precincts": len(decisions) - len(eligible),
              "mapped_ballots": sum(f["properties"]["election_day_ballots"] for f in eligible)}
    counts["held_election_day_ballots"] = election_day - counts["mapped_ballots"]
    layer = {"type": "FeatureCollection", "features": eligible, "source": SOURCE,
             "reference_date": "2022-05-24", "election_date": "2022-11-08", "complete_precinct_map": False,
             "counts": counts, "projected_area_crs": "EPSG:3338", "tolerance_m2": TOLERANCE_M2,
             "source_geometry_sha256": PINS["state-precinct-geometry.geojson"]}
    counts_bytes = (json.dumps(counts, indent=2, sort_keys=True) + "\n").encode()
    return {
        "ak-2022-precinct-reference-audit.csv": csv_bytes(decisions),
        "ak-2022-precinct-reference-counts.json": counts_bytes,
        "ak-2022-precinct-reference.geojson": (
            json.dumps(layer, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(),
        "ak-2022-precinct-reference.html": render(decisions, projected, central).encode(),
    }


def read_pinned(root, name):
    body = (root / name).read_bytes()
    require(hashlib.sha256(body).hexdigest() == PINS[name], f"Alaska precinct pin differs: {name}")
    return json.loads(body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("originals", type=Path)
    parser.add_argument("facts", type=Path)
    parser.add_argument("interim", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    roster, ids, geometry = (read_pinned(args.originals, name) for name in PINS)
    files = outputs(json.loads(args.facts.read_bytes()), roster, ids, geometry, args.interim.read_bytes())
    args.output.mkdir()
    for name, body in files.items():
        (args.output / name).write_bytes(body)
