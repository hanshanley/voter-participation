"""Reproduce reviewed county layers from original Census cartographic shapefiles."""

import argparse
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from shapely.geometry import MultiPolygon, mapping, shape


EDITIONS = {
    1990: ("co99_d90", "ST", "CO", 1717439,
           "dffcc7043d71f25a1c20ecfd0e0b77bb12fea2e46915501f9f958f7689ffcfee"),
    2000: ("co99_d00", "STATE", "COUNTY", 8889602,
           "ada4b2eee365e269c4c3c418f7e37f783b28d9fd4e02be2c4849e345e10fd7e8"),
}
ROSTERS = {"CA": ("06", {f"06{n:03}" for n in range(1, 116, 2)})}


def build(body, year, state):
    stem, state_column, county_column, size, checksum = EDITIONS[year]
    if len(body) != size or hashlib.sha256(body).hexdigest() != checksum:
        raise ValueError("Decennial Census original differs from the reviewed edition")
    state_fips, expected = ROSTERS[state]
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        streams = {ext: io.BytesIO(archive.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")}
    pieces, names = defaultdict(list), {}
    with shapefile.Reader(**streams, encoding="latin-1") as source:
        for item in source.iterShapeRecords():
            if item.record[state_column] != state_fips:
                continue
            fips = state_fips + item.record[county_column]
            name = item.record["NAME"].strip()
            geom = shape(item.shape.__geo_interface__)
            if (not name or names.setdefault(fips, name) != name or fips not in expected
                    or geom.geom_type not in ("Polygon", "MultiPolygon")
                    or geom.is_empty or not geom.is_valid):
                raise ValueError(f"Unverified county component: {fips}")
            pieces[fips].extend(geom.geoms if geom.geom_type == "MultiPolygon" else [geom])
    if pieces.keys() != expected:
        raise ValueError("Decennial county roster differs")
    features = []
    for fips, polygons in sorted(pieces.items()):
        geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        if not geom.is_valid:
            raise ValueError(f"Overlapping or invalid multipart county: {fips}")
        features.append({"type": "Feature", "properties": {
            "key": fips, "name": names[fips], "state_code": state, "boundary_year": year, "level": "county",
        }, "geometry": mapping(geom)})
    folder = re.search(r"\d\d$", stem)[0]
    url = f"https://www2.census.gov/geo/tiger/PREVGENZ/co/co{folder}shp/{stem}_shp.zip"
    return {"type": "FeatureCollection", "boundary_vintage": year, "features": features,
            "source": {"url": url, "bytes": size, "sha256": checksum}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, choices=EDITIONS)
    parser.add_argument("state", choices=ROSTERS)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    collection = build(args.original.read_bytes(), args.year, args.state)
    body = json.dumps(collection, separators=(",", ":"), sort_keys=True, allow_nan=False).encode() + b"\n"
    with args.output.open("xb") as target:
        target.write(gzip.compress(body, mtime=0))


if __name__ == "__main__":
    main()
