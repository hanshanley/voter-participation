"""Reproduce reviewed county layers from original Census shapefiles."""

import argparse
import gzip
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from shapely.geometry import MultiPolygon, mapping, shape


EDITIONS = {
    1990: ("PREVGENZ/co/co90shp/co99_d90_shp", "co99_d90", "ST", "CO", 1717439,
           "dffcc7043d71f25a1c20ecfd0e0b77bb12fea2e46915501f9f958f7689ffcfee"),
    2000: ("PREVGENZ/co/co00shp/co99_d00_shp", "co99_d00", "STATE", "COUNTY", 8889602,
           "ada4b2eee365e269c4c3c418f7e37f783b28d9fd4e02be2c4849e345e10fd7e8"),
    2023: ("GENZ2023/shp/cb_2023_us_county_500k", "cb_2023_us_county_500k", "STATEFP", "COUNTYFP", 11630077,
           "99d6597b1fc7767deef62e01d28d8b5dcbd578e151855f7dc0d173cbf5bf0868"),
    2025: ("GENZ2025/shp/cb_2025_us_county_500k", "cb_2025_us_county_500k", "STATEFP", "COUNTYFP", 11758981,
           "aa976c00b181939755d0da757f4c7c2dc0103c3b3b4530fb2a91c2bb62fc777c"),
    2026: ("TIGER2026/COUNTY/tl_2026_us_county", "tl_2026_us_county", "STATEFP", "COUNTYFP", 83378454,
           "b527c9ba7aeb8f17ef118f026eae5e5a938aa1d00b873bc32342d0dce59321c0"),
}
ROSTERS = {
    "CA": ("06", {f"06{n:03}" for n in range(1, 116, 2)}, {1990, 2000, 2026}),
    "NE": ("31", {f"31{n:03}" for n in range(1, 186, 2)}, {2026}),
    "NJ": ("34", {f"34{n:03}" for n in range(1, 42, 2)}, {2023, 2025}),
    "WY": ("56", {f"56{n:03}" for n in range(1, 46, 2)}, {2026}),
}


def build(body, year, state):
    archive_path, stem, state_column, county_column, size, checksum = EDITIONS[year]
    state_fips, expected, reviewed_years = ROSTERS[state]
    if year not in reviewed_years:
        raise ValueError(f"No reviewed county roster for {state}/{year}")
    if len(body) != size or hashlib.sha256(body).hexdigest() != checksum:
        raise ValueError("Census original differs from the reviewed edition")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        streams = {ext: io.BytesIO(archive.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")}
    pieces, names = defaultdict(list), {}
    with shapefile.Reader(**streams, encoding="latin-1") as source:
        for item in source.iterShapeRecords():
            if item.record[state_column] != state_fips:
                continue
            fips = state_fips + item.record[county_column]
            if year >= 2023 and (item.record["GEOID"] != fips
                                 or (year in (2023, 2025) and item.record["STUSPS"] != state)):
                raise ValueError(f"Census county identity differs: {fips}")
            name = item.record["NAME"].strip()
            geom = shape(item.shape.__geo_interface__)
            if (not name or names.setdefault(fips, name) != name or fips not in expected
                    or geom.geom_type not in ("Polygon", "MultiPolygon")
                    or geom.is_empty or not geom.is_valid):
                raise ValueError(f"Unverified county component: {fips}")
            pieces[fips].extend(geom.geoms if geom.geom_type == "MultiPolygon" else [geom])
    if pieces.keys() != expected:
        raise ValueError("Census county roster differs")
    features = []
    for fips, polygons in sorted(pieces.items()):
        geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        if not geom.is_valid:
            raise ValueError(f"Overlapping or invalid multipart county: {fips}")
        features.append({"type": "Feature", "properties": {
            "key": fips, "name": names[fips], "state_code": state, "boundary_year": year, "level": "county",
        }, "geometry": mapping(geom)})
    url = f"https://www2.census.gov/geo/tiger/{archive_path}.zip"
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
