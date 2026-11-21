"""Replay a conservative two-election Massachusetts precinct reference from bulk MassGIS data."""

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re

from pyproj import Transformer, network
from shapely import transform
from shapely.geometry import shape
from shapely.strtree import STRtree

from massachusetts_municipality_map import BINS, require


YEARS = {2022: "2022-11-08", 2024: "2024-11-05"}
SOURCE = "https://www.mass.gov/info-details/massgis-data-2022-wards-and-precincts"
SERIES = ("WardsPrecincts2022", "Subprecincts2022")


def town(name):
    directions = dict(N="NORTH", S="SOUTH", E="EAST", W="WEST")
    return re.sub(r"^([NSEW])\. ", lambda m: directions[m[1]] + " ", name.upper())


def roster(directory, series):
    pages = [directory / f"{series}-roster.json", *sorted(directory.glob(f"{series}-roster-offset-*.json"))]
    ids = json.loads((directory / f"{series}-ids.json").read_bytes())["objectIds"]
    records = [row["attributes"] for p in pages for row in json.loads(p.read_bytes())["features"]]
    require(len(records) == len(ids) == len(set(ids)) and
            [row["OBJECTID"] for row in records] == sorted(ids), "Incomplete MassGIS roster")
    return records


def candidates(rows, parents, sub_towns, date):
    counts, totals, status = defaultdict(dict), {}, {}
    for row in rows:
        if row["election_date"] != date:
            continue
        key, level = town(row["name"]), row["geography_level"]
        if level == "municipality":
            require(key not in totals, "Duplicate native municipality")
            totals[key] = int(row["ballots_including_blanks"])
        if level == "reporting_unit":
            ward = "" if row["native_ward"] == "-" else row["native_ward"]
            unit = ward, row["native_precinct"]
            require(unit not in counts[key], "Duplicate native precinct")
            counts[key][unit] = int(row["ballots_including_blanks"])
    require(totals.keys() == parents.keys(), "Different municipality inventories")
    for key, units in parents.items():
        if key == "GROTON":
            status[key] = "documented_groton_boundary_change_hold"
        elif key in sub_towns:
            status[key] = "parent_subprecinct_overlap_unresolved"
        elif not counts[key]:
            status[key] = "municipality_count_only"
        elif units.keys() != counts[key].keys() or sum(counts[key].values()) != totals[key]:
            status[key] = "native_scope_does_not_match_parent_roster"
        else:
            status[key] = "matched"
    return counts, totals, status


def geometry(directory, required):
    network.set_network_enabled(False)
    project = Transformer.from_crs(4326, 26986, always_xy=True).transform
    inputs = json.loads((directory / "geometry-receipts.json").read_bytes())
    features, projected, hold = {}, {}, {}
    for name, receipt in sorted(inputs.items()):
        require(re.fullmatch(r"ward-parent-geometry-\d{4}\.geojson", name), "Unexpected geometry file")
        raw = (directory / name).read_bytes()
        require(len(raw) == receipt["bytes"] and hashlib.sha256(raw).hexdigest() == receipt["sha256"],
                "MassGIS geometry source pin differs")
        for feature in json.loads(raw)["features"]:
            props = feature["properties"]
            key = props["OBJECTID"]
            require(key in required and key not in features and props == required[key],
                    "Geometry does not exactly match the official roster attributes")
            features[key] = feature
            polygon = shape(feature["geometry"])
            if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid:
                hold[town(props["TOWN"])] = "invalid_source_polygon"
                continue
            projected[key] = transform(polygon, project, interleaved=False)
    require(features.keys() == required.keys(), "Incomplete candidate geometry")
    keys, values = list(projected), list(projected.values())
    tree = STRtree(values)
    for i, current in enumerate(values):
        for j in tree.query(current):
            if j > i and current.intersection(values[j]).area > 1:
                for key in (keys[i], keys[j]):
                    hold[town(required[key]["TOWN"])] = "interior_polygon_overlap"
    return features, projected, hold


def map_html(year, features, polygons, mapped):
    shapes = [polygons[f["properties"]["OBJECTID"]] for f in features]
    bounds = [(p.bounds) for p in shapes]
    x0, y0 = min(b[0] for b in bounds), min(b[1] for b in bounds)
    x1, y1 = max(b[2] for b in bounds), max(b[3] for b in bounds)
    scale = min(730 / (x1 - x0), 350 / (y1 - y0))
    dx, dy = (750 - (x1 - x0) * scale) / 2, (370 - (y1 - y0) * scale) / 2
    paths, rows = [], []
    for feature, polygon in zip(features, shapes, strict=True):
        props = feature["properties"]
        label = html.escape(f"{props['TOWN'].title()} · {props['WP_DISTRICT']}")
        count = props["ballots_including_blanks"]
        color = next(color for limit, color, _ in BINS if count < limit)
        parts = polygon.geoms if polygon.geom_type == "MultiPolygon" else [polygon]
        path = "".join("M" + "L".join(f"{dx+(x-x0)*scale:.1f},{dy+(y1-y)*scale:.1f}" for x,y in ring.coords)
                       + "Z" for part in parts for ring in [part.exterior, *part.interiors])
        paths.append(f'<path fill="{color}" d="{path}"><title>{label}: {count:,} ballots</title></path>')
        rows.append(f'<tr><th scope="row">{label}</th><td>{count:,}</td></tr>')
    legend = " · ".join(f'<span style="color:{color}">■</span> {label}' for _, color, label in BINS)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Massachusetts {year} precinct ballot counts</title>
<style>body{{font:1rem/1.5 system-ui,sans-serif;color:#142c39;margin:auto;padding:1.2rem;max-width:52rem}}
svg{{width:100%;height:auto}}path{{stroke:#f4f8fa;stroke-width:.4;fill-rule:evenodd}}table{{width:100%;border-collapse:collapse}}
td,th{{border-bottom:1px solid #ccd7db;padding:.25rem;text-align:left}}td{{text-align:right}}caption{{text-align:left}}</style>
<main><h1>Massachusetts {year} precinct ballot counts</h1>
<p>{len(features):,} parent precincts and {mapped:,} ballots where the complete municipal roster and polygons passed.
This is a partial map. Blank areas are not zero turnout. Counts include blanks; no turnout rates are calculated.</p>
<svg viewBox="0 0 750 370" role="img" aria-labelledby="map-title">
<title id="map-title">Mapped parent precinct ballot counts, tabulated below.</title>{''.join(paths)}</svg><p>{legend}</p>
<p><a href="{SOURCE}">MassGIS 2022 wards and precincts</a>, November 2023 edition.
This is a dated reference, not a reconstruction of every election-day boundary.</p>
<table><caption>Ballots including blanks in mapped precincts</caption>
<thead><tr><th scope="col">Municipality and precinct</th><th scope="col">Ballots</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></main></html>
"""


def build(directory, history, output):
    parents, by_id = defaultdict(dict), {}
    for row in roster(directory, SERIES[0]):
        key, unit = town(row["TOWN"]), (row["WARD"] or "", row["PRECINCT"])
        require(unit not in parents[key], "Duplicate MassGIS parent precinct")
        parents[key][unit] = row["OBJECTID"]
        by_id[row["OBJECTID"]] = row
    sub_towns = {town(row["TOWN"]) for row in roster(directory, SERIES[1])}
    require(len(parents) == 351 and sub_towns <= parents.keys(), "MassGIS municipality inventory differs")
    rows = list(csv.DictReader(io.StringIO(history.decode())))
    by_year = {year: candidates(rows, parents, sub_towns, date) for year, date in YEARS.items()}
    needed = {obj: by_id[obj] for _, _, status in by_year.values() for key, disposition in status.items()
              if disposition == "matched" for obj in parents[key].values()}
    features, projected, holds = geometry(directory, needed)
    output.mkdir()
    with (output / "precinct-reference-coverage.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("election_date", "municipality", "reference_status", "parent_precincts",
                         "mapped_precincts", "municipality_ballots", "mapped_ballots"))
        for year, (counts, totals, status) in by_year.items():
            mapped, layer = 0, []
            for key, units in sorted(parents.items()):
                eligible = status[key] == "matched" and key not in holds
                ballots = totals[key] if eligible else 0
                label = "mapped_reference" if eligible else holds.get(key, status[key])
                writer.writerow((YEARS[year], key, label, len(units), len(units) if eligible else 0, totals[key], ballots))
                if eligible:
                    for unit, object_id in sorted(units.items()):
                        feature = features[object_id]
                        layer.append({**feature, "properties": {**feature["properties"],
                            "ballots_including_blanks": counts[key][unit], "election_date": YEARS[year]}})
                    mapped += ballots
            require(mapped == sum(f["properties"]["ballots_including_blanks"] for f in layer),
                    "Mapped precincts do not reconcile")
            with (output / f"massachusetts-{year}-precinct-reference.geojson.gz").open("xb") as file:
                body = json.dumps({"type": "FeatureCollection", "features": layer, "source": SOURCE,
                    "election_date": YEARS[year], "reference_edition": "November 2023", "complete": False},
                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                zipped = bytearray(gzip.compress(body, mtime=0))
                zipped[9] = 3
                file.write(zipped)
            (output / f"massachusetts-{year}-precinct-reference.html").write_text(
                map_html(year, layer, projected, mapped), encoding="utf-8")
            print(year, len(layer), mapped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("originals", type=Path)
    parser.add_argument("historical_csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.originals, args.historical_csv.read_bytes(), args.output)
