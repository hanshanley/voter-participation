"""Build dated New Mexico county reference maps from reconciled turnout rows."""

import argparse
import csv
import gzip
import html
import io
import json
from pathlib import Path

from pyproj import Transformer
from shapely import transform
from shapely.geometry import shape

from scripts.census_county_reference import build as county_reference
from scripts.nc_precinct_reference import display_paths
from scripts.new_mexico_turnout_history_replay import build as turnout
from scripts.participation_intake.contract import pin


YEARS = ("2016", "2018", "2020", "2022", "2024")
COLORS = ("#e0e9ec", "#b9d1da", "#87acbb", "#54889e", "#305e78")
THRESHOLDS = (45, 55, 65, 75)
LABELS = ("Below 45%", "45–<55%", "55–<65%", "65–<75%", "75% and above")
ALIAS = {"Dona Ana": "Doña Ana"}


def build(inputs):
    rows = json.loads((inputs / "source-facts.json").read_bytes())
    csv_body = turnout(rows)["participation-nm-historical-native-turnout.csv"]
    facts = list(csv.DictReader(io.StringIO(csv_body.decode())))
    sources = json.loads((inputs / "county-sources.json").read_bytes())
    if set(sources) != set(YEARS):
        raise ValueError("Incomplete New Mexico county vintages")
    project = Transformer.from_crs(
        4326, "+proj=aea +lat_1=29.5 +lat_2=45.5 +lat_0=23 +lon_0=-106 "
        "+datum=NAD83 +units=m +no_defs +type=crs", always_xy=True).transform
    decisions, outputs, figures = [], {}, []
    for year in YEARS:
        selected = {ALIAS.get(r["county"], r["county"]): r for r in facts
                    if r["geography_level"] == "county" and r["election_date"][:4] == year}
        original = (inputs / f"{year}.geojson").read_bytes()
        source = sources[year]
        if len(selected) != 33 or pin(original) != {key: source[key] for key in ("bytes", "sha256")}:
            raise ValueError("Missing or changed New Mexico county source")
        layer = county_reference(original, int(year), "NM", "35", set(selected))
        outputs[f"county-NM-{year}.geojson.gz"] = layer
        geometries, map_rows = {}, {}
        for feature in json.loads(gzip.decompress(layer))["features"]:
            county = feature["properties"]
            geoid = county["key"]
            row = selected[county["name"]]
            if row["county"] in ALIAS and geoid != "35013":
                raise ValueError("New Mexico county alias does not identify Doña Ana")
            geometry = transform(shape(feature["geometry"]), project, interleaved=False)
            if not geometry.is_valid or geometry.is_empty:
                raise ValueError("Invalid projected county outline")
            geometries[geoid] = geometry
            record = {**row, "county_geoid": geoid, "census_name": county["name"],
                      "reference_date": year + "-01-01", "geometry_sha256": source["sha256"],
                      "reference_only": True, "votes_allocated": False}
            decisions.append(record)
            map_rows[geoid] = record

        paths, cells = [], []
        for geoid, path in display_paths(geometries):
            row = map_rows[geoid]
            value = row["source_eligible_rate_pct"]
            rate = float(value) if value else None
            name = html.escape(row["census_name"])
            status = f"{rate:.2f}%" if rate is not None else "Rate withheld"
            color = COLORS[sum(rate >= threshold for threshold in THRESHOLDS)] if rate is not None else "#d2d0c9"
            paths.append(f'<path data-county="{geoid}" fill="{color}" d="{path}"><title>{name}: {status}</title></path>')
            cells.append(f'<tr><th scope="row">{name}</th><td>{int(row["source_reported_count"]):,}</td>'
                         f'<td>{int(row["source_eligible_voters"]):,}</td><td>{status}</td></tr>')
        held = sum(not r["source_eligible_rate_pct"] for r in map_rows.values())
        legend = "".join(f'<rect x="{40 + 175*i}" y="397" width="18" height="14" fill="{color}"/>'
                         f'<text x="{64 + 175*i}" y="409">{html.escape(label)}</text>'
                         for i, (color, label) in enumerate(zip(COLORS, LABELS)))
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 453" role="img"
aria-labelledby="title-{year} desc-{year}"><title id="title-{year}">New Mexico county turnout, {year}</title>
<desc id="desc-{year}">{33-held} of 33 county rates, using the official report's Eligible Voters denominator.</desc>
<rect width="960" height="453" fill="#F2EFE7"/>
<text x="34" y="34" font-family="Georgia,serif" font-size="29" fill="#1a1a1a">New Mexico county turnout, {year}</text>
<g fill-rule="evenodd" stroke="#647079" stroke-width=".6">{''.join(paths)}</g>
<g fill="#333" font-family="system-ui,sans-serif" font-size="14">{legend}
<text x="40" y="435">Ballots Cast ÷ source-reported Eligible Voters · gray: rate withheld · Census county reference</text>
</g></svg>\n'''
        outputs[f"new-mexico-county-{year}.svg"] = svg.encode()
        outputs[f"new-mexico-county-{year}-substack.svg"] = svg.replace('fill="#F2EFE7"', 'fill="#F7F5F0"', 1).encode()
        figures.append(f'<section><h2>{year} general election</h2>{svg}<details><summary>All 33 county counts and rates</summary>'
                       '<div class="table" tabindex="0" role="region" aria-label="County counts and rates"><table>'
                       '<thead><tr><th scope="col">County</th><th scope="col">Ballots Cast</th>'
                       '<th scope="col">Eligible Voters</th><th scope="col">Rate</th></tr></thead>'
                       f'<tbody>{"".join(cells)}</tbody></table></div></details></section>')
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(decisions[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(decisions)
    outputs["new-mexico-county-map-values.csv"] = stream.getvalue().encode()
    outputs["new-mexico-county-maps.html"] = ('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>New Mexico county turnout maps</title>
<style>body{max-width:60rem;margin:auto;padding:1rem;font:1rem/1.5 system-ui,sans-serif;color:#1a1a1a;background:#F2EFE7}
svg{width:100%;height:auto}.table{overflow:auto}td,th{padding:.35rem;text-align:left;border-bottom:1px solid #ccc}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}summary{cursor:pointer}</style>
<main><h1>New Mexico county turnout, 2016–2024</h1>
<p>Same-report rates from five official elections, shown on dated Census county outlines.
Gray means the report contains an unusable denominator, not zero turnout.
Reporting-unit counts are not given precinct locations.</p>
<p><a href="new-mexico-county-map-values.csv">Download the exact map values and holds (CSV)</a></p>
''' + "".join(figures) + "</main></html>\n").encode()
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = build(args.inputs)
    args.output.mkdir()
    for name, body in files.items():
        (args.output / name).write_bytes(body)
