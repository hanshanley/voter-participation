"""Reproduce the reviewed Maryland 2022 precinct activity display layers."""

import argparse
from collections import Counter
import gzip
import io
import json
from pathlib import Path
import re

from scripts import maryland_precinct_history as md
from scripts.participation_intake.contract import encoded, pin

DATE = "2022-11-08"
COUNTIES = {"24027": ("Howard", "20220802", 118), "24041": ("Talbot", "20220818", 12)}
AGENCY = "State of Maryland, Maryland Department of Planning and MD iMAP"


def reference_ids(body):
    from openpyxl import load_workbook

    upper_names = {name.upper(): key for key, (name, _, _) in COUNTIES.items()}
    workbook = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        rows = iter(workbook.worksheets[0].values)
        name_col, precinct_col = map(next(rows).index, ("COUNTY_NAME", "PRECINCT_CODE"))
        return {f"{upper_names[row[name_col]]}{row[precinct_col] // 1000:02}-{row[precinct_col] % 1000:03}"
                for row in rows if row[name_col] in upper_names
                and type(row[precinct_col]) is int and 0 <= row[precinct_col] < 100_000}
    finally:
        workbook.close()


def build(inputs, output, manifest):
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    def checked(filename):
        body = (inputs / filename).read_bytes()
        if pin(body) != manifest[filename]:
            raise ValueError(f"Original differs from pin: {filename}")
        return body

    if (inputs / "2022-original.csv").exists():
        query = md.parse(checked("2022-original.csv"), checked("2022-original-county.pdf"), DATE)
        refs = reference_ids(checked("2022-reference.xlsx"))
    else:
        original_query = json.loads(checked("2022-participation-query.json"))
        query = md.query(original_query["native_rows"], original_query["control_page"], DATE)
        if query != original_query:
            raise ValueError("Maryland retained turnout query differs")
        refs = set(json.loads(checked("2022-precinct-reference-ids.json")))
    totals, unplaced = Counter(), Counter()
    counties_by_name = {name: key for key, (name, _, _) in COUNTIES.items()}
    for row in query["native_rows"]:
        name, _, _, precinct, _ = row[:5]
        if name in counties_by_name:
            count = sum(map(int, row[5:9]))
            if re.fullmatch(r"0\d{2}-\d{3}", precinct):
                totals[counties_by_name[name] + precinct[1:]] += count
            else:
                unplaced[name] += count
    if refs != totals.keys():
        raise ValueError("Maryland activity and election-reference rosters differ")
    features = {}
    collection = json.loads(checked("2022-howard-talbot-exact.json"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("Missing Maryland precinct features")
    for feature in collection["features"]:
        props = feature["properties"]
        county = props["COUNTY"]
        key = props["VTD"]
        _, stamp, _ = COUNTIES[county]
        if key not in refs or key != county + props["LABEL"] or props["SRC_DATE"] != stamp:
            raise ValueError("Maryland precinct geometry key or vintage differs")
        if key in features:
            raise ValueError("Duplicate Maryland precinct feature")
        features[key] = feature["geometry"]
    if features.keys() != refs:
        raise ValueError("Maryland geometry is incomplete")

    metadata = json.loads(checked("2022-layer-iteminfo.json"))
    if metadata.get("title") != "Maryland Precincts - 2022" or not metadata.get("licenseInfo"):
        raise ValueError("Missing original Maryland layer metadata")
    export = {}
    for geoid, (county, stamp, count) in COUNTIES.items():
        matching = [key for key in sorted(refs) if key.startswith(geoid)]
        if len(matching) != count:
            raise ValueError("Incorrect Maryland county precinct inventory")
        control = next(values for name, values, rate in query["county_controls"] if name == county)
        if sum(totals[key] for key in matching) + unplaced[county] != sum(control[:4]):
            raise ValueError("Maryland map does not preserve unassigned activity")
        mapped, polygons = [], []
        for key in matching:
            polygon = shape(features[key])
            west, south, east, north = polygon.bounds
            if (not polygon.is_valid or polygon.geom_type not in {"Polygon", "MultiPolygon"}
                    or polygon.area <= 0 or not (-80 < west < east < -74 and 37 < south < north < 41)):
                raise ValueError("Invalid Maryland display geometry")
            polygons.append(polygon)
            mapped.append({"type": "Feature", "properties": {"precinct": "0" + key[5:],
                           "activity": totals[key]}, "geometry": features[key]})
        tree = STRtree(polygons)
        if any(p.intersection(polygons[j]).area > 1e-8 * min(p.area, polygons[j].area)
               for i, p in enumerate(polygons) for j in tree.query(p) if j > i):
            raise ValueError("Maryland precincts materially overlap")
        export[county] = {"county_geoid": geoid, "source_date": stamp, "activity_without_precinct": unplaced[county],
                          "features": mapped}
    raw = encoded({"contract": "participation.md_precinct_activity_display.v1", "election_date": DATE,
                   "participation_measure": md.NUMERATOR, "source_sha256": manifest["2022-original.csv"]["sha256"],
                   "display_only": True, "attribution": AGENCY, "counties": export})
    output.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(raw)
    (output / "precinct-MD-2022.json.gz").write_bytes(buffer.getvalue())
    (output / "precinct-MD-2022-original-metadata.json").write_bytes(checked("2022-layer-iteminfo.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.inputs, args.output, json.loads(args.manifest.read_bytes()))
