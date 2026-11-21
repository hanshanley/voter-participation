"""Reproduce the 2022 Alaska House district turnout map from the interim plan."""

import argparse
import io
import json
from pathlib import Path
import zipfile

import shapefile
from pyproj import CRS, Transformer, network
from shapely import transform
from shapely.geometry import mapping, shape

from scripts import alaska_precinct_history as ak
from scripts.participation_intake.contract import pin
from scripts.supported_analytical_release import csv_bytes


STEM = "2022-May-Interim-Proclamation-Plan"
SOURCE = f"https://www.akredistrict.org/files/5916/5349/2050/{STEM}.zip"
SHA = "f353a616fcf4e04e195f5ef75ae684eec098061b764c999457cbd1c5b4255695"
COLORS = ("#dce9ef", "#afcedd", "#74a7bc", "#3b7c98", "#174761")
LABELS = ("Below 25%", "25–34.99%", "35–44.99%", "45–54.99%", "55% or higher")


def build(original, facts):
    if pin(original)["sha256"] != SHA:
        raise ValueError("Alaska interim district boundary pin differs")
    data = facts[ak.MIDTERM_FEED]["data"]
    ak.reconcile_midterm(data["districts"], data["control"])
    network.set_network_enabled(False)
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        source = CRS.from_wkt(archive.read(f"{STEM}.prj").decode())
        reader = shapefile.Reader(**{suffix: io.BytesIO(archive.read(f"{STEM}.{suffix}"))
                                    for suffix in ("shp", "shx", "dbf")})
        shapes = {}
        for feature in reader.iterShapeRecords():
            district = feature.record["DISTRICTN"]
            polygon = shape(feature.shape)
            if (type(district) is not int or district in shapes or feature.record["ID"] != district
                    or feature.record["DISTRICT"] != str(district) or not polygon.is_valid or polygon.is_empty
                    or polygon.geom_type not in ("Polygon", "MultiPolygon")):
                raise ValueError("Invalid Alaska interim district shape or identity")
            shapes[district] = polygon
    if set(shapes) != set(range(1, 41)):
        raise ValueError("Incomplete Alaska interim district geometry")
    info, features = [], []
    district_rate = {}
    wgs84 = Transformer.from_crs(source, 4326, always_xy=True).transform
    alaska = Transformer.from_crs(source, 3338, always_xy=True).transform
    projected = {key: transform(poly, alaska, interleaved=False) for key, poly in shapes.items()}
    for key in (*range(1, 41), 99):
        registered, ballots, _, printed = data["districts"][str(key)]["total"]
        row = {"source_district": key, "election_date": "2022-11-08", "ballots": ballots,
               "registered": registered, "registered_turnout": printed, "mapped": key != 99}
        info.append(row)
        if key != 99:
            rate = float(printed.removesuffix("%"))
            district_rate[key] = rate
            features.append({"type": "Feature", "id": key, "properties": row,
                             "geometry": mapping(transform(shapes[key], wgs84, interleaved=False))})
    layer = {"type": "FeatureCollection", "features": features, "boundary_date": "2022-05-24",
             "boundary_source": SOURCE, "boundary_sha256": SHA, "precinct_geometry_verified": False}
    return {
        "ak-2022-house-district-turnout.csv": csv_bytes(info),
        "ak-2022-house-district-turnout.geojson": (
            json.dumps(layer, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(),
        "ak-2022-house-district-turnout.html": render(projected, district_rate, info).encode(),
    }


def render(polygons, rates, rows):
    bounds = [g.bounds for g in polygons.values()]
    x0, y0 = min(b[0] for b in bounds), min(b[1] for b in bounds)
    x1, y1 = max(b[2] for b in bounds), max(b[3] for b in bounds)
    scale = min(730 / (x1 - x0), 400 / (y1 - y0))
    dx, dy = (750 - (x1 - x0) * scale) / 2, (420 - (y1 - y0) * scale) / 2
    paths, table = [], []
    for row in rows:
        key, rate = row["source_district"], row["registered_turnout"]
        label = f"House district {key}" if row["mapped"] else "Federal overseas (not mapped)"
        if row["mapped"]:
            g = polygons[key]
            parts = g.geoms if g.geom_type == "MultiPolygon" else [g]
            rings = [ring for poly in parts for ring in [poly.exterior, *poly.interiors]]
            path = "".join("M" + "L".join(f"{dx + (x - x0) * scale:.1f},{dy + (y1 - y) * scale:.1f}"
                                            for x, y in ring.coords) + "Z" for ring in rings)
            color = COLORS[sum(rates[key] >= boundary for boundary in (25, 35, 45, 55))]
            paths.append(f'<path fill="{color}" d="{path}"><title>{label}: {rate}</title></path>')
        table.append(f'<tr><th scope="row">{label}</th><td>{row["ballots"]:,}</td>'
                     f'<td>{row["registered"]:,}</td><td>{rate}</td></tr>')
    legend = " · ".join(f'<span style="color:{color}">■</span> {label}' for color, label in zip(COLORS, LABELS))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alaska 2022 turnout by House district</title>
<style>body{{font:1rem/1.5 system-ui,sans-serif;color:#142c39;margin:auto;padding:1rem;max-width:54rem}}
svg{{width:100%;height:auto}}path{{stroke:#edf4f6;stroke-width:.35;fill-rule:evenodd}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
td,th{{border-bottom:1px solid #ccd7db;padding:.25rem;text-align:right}}th:first-child,caption{{text-align:left}}</style>
<main><h1>Alaska 2022 turnout by House district</h1>
<p>November 8, 2022. Shading shows ballots as a percentage of registered voters in the official district reports.
This is not a precinct map. The {rows[-1]['ballots']:,} federal overseas ballots are shown only in the table.</p>
<svg viewBox="0 0 750 420" role="img" aria-labelledby="map-title">
<title id="map-title">Registered turnout by state House district, with all values in the table.</title>
{''.join(paths)}</svg><p>{legend}</p>
<p>Boundaries: <a href="{SOURCE}">May 24, 2022 Alaska Redistricting Board interim plan</a>.</p>
<table><caption>Official district totals</caption>
<thead><tr><th scope="col">Reporting area</th><th scope="col">Ballots</th>
<th scope="col">Registered</th><th scope="col">Turnout</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></main></html>
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("ballot_facts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = build(args.geometry.read_bytes(), json.loads(args.ballot_facts.read_bytes()))
    args.output.mkdir()
    for name, body in files.items():
        (args.output / name).write_bytes(body)
