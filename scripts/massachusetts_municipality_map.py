"""Reproduce the 2022 Massachusetts municipality ballot-count reference map."""

import argparse
from collections import Counter
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import zipfile

import shapefile
from pyproj import CRS, Transformer, network
from shapely import transform
from shapely.geometry import mapping, shape


SOURCE = "https://www2.census.gov/geo/tiger/TIGER2022/COUSUB/tl_2022_25_cousub.zip"
SOURCE_SHA256 = "04eda5c5e07089abf22341a0e7b24339a009b891bd5fba6e4c9d0c0262d8141b"
DATE = "2022-11-08"
STEM = "tl_2022_25_cousub"
BINS = ((1_000, "#dce9ef", "Fewer than 1,000"), (5_000, "#b4d2df", "1,000–4,999"),
        (10_000, "#7caec2", "5,000–9,999"), (25_000, "#3b7c98", "10,000–24,999"),
        (float("inf"), "#174761", "25,000 or more"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_rows(body):
    towns, counties, statewide = {}, {}, None
    for row in csv.DictReader(io.StringIO(body.decode())):
        require(row["state_code"] == "MA" and row["election_date"] == DATE
                and row["rate_hold_reason"] == "no_registration_denominator_in_paired_canvasses",
                "Unexpected Massachusetts election or count scope")
        count = int(row["ballots_including_blanks"])
        require(count >= 0, "Negative ballot count")
        key, fips = row["census_geoid"], row["county_fips"]
        level = row["geography_level"]
        if level == "municipality":
            require(len(key) == 10 and key.isascii() and key.isdecimal() and key.startswith(fips)
                    and key not in towns, "Duplicate or invalid municipality")
            towns[key] = (row["census_name"], count)
        elif level == "county":
            require(key == fips and len(fips) == 5 and key not in counties, "Duplicate or invalid county")
            counties[key] = count
        else:
            require(level == "statewide" and statewide is None, "Duplicate or invalid statewide row")
            statewide = count
    parents = Counter()
    for key, (_, count) in towns.items():
        parents[key[:5]] += count
    require(len(towns) == 351 and len(counties) == 14 and parents == counties
            and statewide == sum(parents.values()), "Counts do not reconcile across all municipalities")
    return towns, statewide


def join(geometry, counts):
    require(hashlib.sha256(geometry).hexdigest() == SOURCE_SHA256, "Census source pin differs")
    towns, statewide = load_rows(counts)
    network.set_network_enabled(False)
    matched, projected = {}, {}
    with zipfile.ZipFile(io.BytesIO(geometry)) as archive:
        names = {suffix: archive.read(f"{STEM}.{suffix}") for suffix in ("shp", "shx", "dbf", "prj")}
        crs = CRS.from_wkt(names.pop("prj").decode())
        wgs = Transformer.from_crs(crs, 4326, always_xy=True).transform
        local = Transformer.from_crs(crs, 26986, always_xy=True).transform
        with shapefile.Reader(**{suffix: io.BytesIO(data) for suffix, data in names.items()}) as reader:
            for record in reader.iterShapeRecords():
                info = record.record
                key = info["GEOID"]
                if (info["ALAND"] == 0 and info["CLASSFP"] == "Z9" and key.endswith("00000")
                        and info["NAMELSAD"] == "County subdivisions not defined"):
                    continue
                require(key in towns and key not in matched and info["STATEFP"] == "25"
                        and info["ALAND"] > 0 and info["CLASSFP"] in ("C5", "T1")
                        and key == "25" + info["COUNTYFP"] + info["COUSUBFP"]
                        and info["NAMELSAD"] == towns[key][0], "Census municipality identity differs")
                polygon = shape(record.shape)
                require(polygon.geom_type in ("Polygon", "MultiPolygon")
                        and not polygon.is_empty and polygon.is_valid, "Invalid Census municipality polygon")
                matched[key] = {"type": "Feature", "id": key,
                                "geometry": mapping(transform(polygon, wgs, interleaved=False)),
                                "properties": {"municipality": info["NAME"], "census_name": towns[key][0],
                                               "census_geoid": key, "county_fips": key[:5],
                                               "ballots_including_blanks": towns[key][1]}}
                projected[key] = transform(polygon, local, interleaved=False)
    require(matched.keys() == towns.keys(), "Incomplete Census municipality geometry")
    layer = {"type": "FeatureCollection", "features": [matched[key] for key in sorted(matched)],
             "boundary_reference_date": "2022-01-01", "election_date": DATE,
             "source_url": SOURCE, "source_sha256": SOURCE_SHA256,
             "ballot_source_sha256": hashlib.sha256(counts).hexdigest(), "rate_qualified": False}
    return layer, projected, statewide


def render(layer, polygons, statewide):
    parts = list(polygons.values())
    x0 = min(p.bounds[0] for p in parts)
    x1 = max(p.bounds[2] for p in parts)
    y0 = min(p.bounds[1] for p in parts)
    y1 = max(p.bounds[3] for p in parts)
    scale = min(730 / (x1 - x0), 350 / (y1 - y0))
    dx, dy = (750 - (x1 - x0) * scale) / 2, (370 - (y1 - y0) * scale) / 2

    def path(polygon):
        rings = [ring for poly in (polygon.geoms if polygon.geom_type == "MultiPolygon" else [polygon])
                 for ring in [poly.exterior, *poly.interiors]]
        return "".join("M" + "L".join(f"{dx + (x - x0) * scale:.1f},{dy + (y1 - y) * scale:.1f}"
                                      for x, y in ring.coords) + "Z" for ring in rings)

    paths, rows = [], []
    for feature in sorted(layer["features"], key=lambda f: f["properties"]["municipality"].casefold()):
        key, properties = feature["id"], feature["properties"]
        name, count = html.escape(properties["municipality"]), properties["ballots_including_blanks"]
        color = next(color for limit, color, _ in BINS if count < limit)
        paths.append(f'<path data-geoid="{key}" fill="{color}" d="{path(polygons[key])}">'
                     f"<title>{name}: {count:,} ballots</title></path>")
        rows.append(f'<tr><th scope="row">{name}</th><td>{count:,}</td></tr>')
    legend = "".join(f'<li><span style="background:{color}"></span>{label}</li>' for _, color, label in BINS)
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Massachusetts 2022 midterm ballot counts</title>
<style>
body{{font:1rem/1.5 system-ui,sans-serif;color:#142c39;margin:auto;padding:1.2rem;max-width:52rem}}
h1{{font-size:clamp(1.55rem,4vw,2.4rem);line-height:1.16}}
figure{{margin:1rem 0}} svg{{width:100%;height:auto}} path{{stroke:#f4f8fa;stroke-width:.4;fill-rule:evenodd}}
ul{{display:flex;flex-wrap:wrap;gap:.45rem 1rem;margin:0;padding:0;list-style:none}}
li span{{display:inline-block;width:.8rem;height:.8rem;margin-right:.35rem;border:1px solid #546873}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
caption{{text-align:left;font-weight:bold}} th,td{{border-bottom:1px solid #ccd7db;padding:.25rem;text-align:left}}
td{{text-align:right}} thead th:last-child{{text-align:right}}
</style><main><h1>Massachusetts 2022 midterm ballot counts</h1>
<p>November 8, 2022 · {statewide:,} ballots across all 351 cities and towns. Counts include blank ballots.
Shading shows numbers of ballots, not turnout rates.</p>
<figure><svg viewBox="0 0 750 370" role="img" aria-labelledby="map-title">
<title id="map-title">Ballot counts by city and town, with all numbers in the table below.</title>
{''.join(paths)}</svg><figcaption><ul>{legend}</ul></figcaption></figure>
<p>Source: Massachusetts paired statewide canvasses and <a href="{SOURCE}">2022 Census TIGER/Line</a>
municipal references dated January 1, 2022. These are not precinct boundaries.</p>
<table><caption>Ballots including blanks by municipality</caption>
<thead><tr><th scope="col">City or town</th><th scope="col">Ballots</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></main></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("rollup", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    layer, projected, statewide = join(args.geometry.read_bytes(), args.rollup.read_bytes())
    args.output.mkdir()
    (args.output / "municipality-MA-2022.geojson").write_text(
        json.dumps(layer, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "massachusetts-2022-municipality-map.html").write_text(
        render(layer, projected, statewide), encoding="utf-8")
    print(f"{len(layer['features'])} municipality shapes, {statewide:,} ballots")


if __name__ == "__main__":
    main()
