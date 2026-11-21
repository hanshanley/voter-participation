"""Join dated Census cartographic counties to a reviewed, same-year turnout report."""

import argparse
import csv
import gzip
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
from zipfile import ZipFile

from scripts.participation_intake.contract import encoded, pin


VINTAGES = {1990: ("co99_d90", "ST", "CO"), 2000: ("co99_d00", "STATE", "COUNTY")}


def build(archive, turnout, profile):
    import shapefile
    from shapely import coverage_is_valid
    from shapely.geometry import shape

    date, code, fips = (profile[k] for k in ("election_date", "state_code", "state_fips"))
    year = int(date[:4])
    stem, state_field, county_field = VINTAGES[year]
    aliases = profile.get("census_county_name_aliases", {})
    if pin(archive) != profile["geometry_pin"] or pin(turnout) != profile["turnout_pin"]:
        raise ValueError("Decennial geometry or turnout original differs from its pin")
    rows = [r for r in csv.DictReader(StringIO(turnout.decode("utf-8-sig")))
            if r["election_date"] == date and r["state_code"] == code]
    counties = {r["native_geography"]: r for r in rows if r["geography_level"] == "county"}
    parents = [r for r in rows if r["geography_level"] == "state"]
    if (len(rows) != len(counties) + 1 or len(parents) != 1
            or len(counties) != profile["county_count"]
            or any(r["geometry_hold"] for r in counties.values())
            or any(sum(int(r[field]) for r in counties.values()) != int(parents[0][field])
                   for field in ("reported_voter_turnout", "reported_registered_voters"))):
        raise ValueError("Turnout does not have a complete, reconciled, unambiguous county inventory")
    features, decisions = {}, {}
    seen_names = set()
    with ZipFile(BytesIO(archive)) as files:
        parts = {}
        for ext in ("dbf", "shp", "shx"):
            name = f"{stem}.{ext}"
            if files.namelist().count(name) != 1 or files.getinfo(name).file_size > 30_000_000:
                raise ValueError("Unexpected decennial county archive member")
            parts[ext] = BytesIO(files.read(name))
        with shapefile.Reader(**parts, encoding="cp1252") as reader:
            for record in reader.iterShapeRecords():
                if record.record[state_field] != fips:
                    continue
                key = fips + record.record[county_field]
                census_name = record.record["NAME"]
                name = aliases.get(census_name, census_name)
                if not re.fullmatch(r"[0-9]{5}", key) or key in features or name in seen_names or name not in counties:
                    raise ValueError("County identity differs from dated Census roster")
                seen_names.add(name)
                geo = record.shape.__geo_interface__
                features[key] = {"type": "Feature", "geometry": geo, "properties": {
                    "state_code": code, "level": "county", "key": key, "name": name, "boundary_year": year}}
                decisions[key] = {"election_date": date, "county_geoid": key, "census_name": census_name,
                                  **counties[name], "geometry_status": "mapped_dated_reference"}
    if seen_names != set(counties):
        raise ValueError("Incomplete decennial mapping")
    geometry = [shape(f["geometry"]) for f in features.values()]
    if any(not g.is_valid or g.area <= 0 or g.geom_type not in {"Polygon", "MultiPolygon"}
           for g in geometry) or not coverage_is_valid(geometry):
        raise ValueError("Decennial county reference is not valid nonoverlapping coverage")
    layer = {"type": "FeatureCollection", "boundary_vintage": year, "display_only": True,
             "source_sha256": profile["geometry_pin"]["sha256"],
             "features": [features[k] for k in sorted(features)]}
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, sorted(next(iter(decisions.values()))), lineterminator="\n")
    writer.writeheader()
    writer.writerows(decisions[k] for k in sorted(decisions))
    return gzip.compress(encoded(layer), mtime=0), stream.getvalue().encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "turnout", "profile", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_bytes())
    layer, decisions = build(args.archive.read_bytes(), args.turnout.read_bytes(), profile)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / profile["layer"]).write_bytes(layer)
    (args.output / "county-map-decisions.csv").write_bytes(decisions)
    print(json.dumps(pin(layer)))


if __name__ == "__main__":
    main()
