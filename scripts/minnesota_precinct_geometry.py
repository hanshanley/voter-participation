"""Build dated Minnesota precinct display layers from pinned MnGeo responses."""

import argparse
import gzip
import io
import json
from pathlib import Path

from scripts import minnesota_precinct_history as mn
from scripts.participation_intake.contract import encoded, pin


def build(inputs, output, manifest):
    from shapely.geometry import shape

    def checked(filename):
        body = (inputs / filename).read_bytes()
        if pin(body) != manifest[filename]:
            raise ValueError(f"Original differs from pin: {filename}")
        return body

    def valid(feature):
        polygon = shape(feature["geometry"])
        west, south, east, north = polygon.bounds
        return (polygon.geom_type in {"Polygon", "MultiPolygon"} and polygon.is_valid
                and polygon.area > 0 and -98 < west < east < -89 and 43 < south < north < 50)

    output.mkdir(parents=True, exist_ok=True)
    receipts = {}
    for election in mn.EDITIONS:
        year = election[:4]
        if (inputs / f"{year}.xlsx").exists():
            query = mn.parse(checked(f"{year}.xlsx"), election)
        else:
            query = json.loads(checked(f"{year}-precinct-query.json"))
            if query != mn.query(query["fields"], query["precincts"], query["county_roster"],
                                 query["printed_total"], election):
                raise ValueError(f"Retained precinct query differs: {year}")
        voters = {mn.precinct_key(r, election): r["TOTVOTING"] for r in query["precincts"]}
        id_field = "vtd" if year == "2012" else "vtdid"
        features, invalid = {}, set()
        for offset in range(0, len(voters), 1000):
            batch = json.loads(checked(f"{year}-gis-geometry-{offset}.json"))
            if batch.get("type") != "FeatureCollection" or len(batch["features"]) != min(1000, len(voters) - offset):
                raise ValueError(f"Unexpected MnGeo response extent: {year}, offset {offset}")
            for f in batch["features"]:
                key = str(f["properties"][id_field])
                if key not in voters or key in features or f["properties"]["totvoting"] != voters[key]:
                    raise ValueError(f"Wrong or duplicate MnGeo participation record: {year}, {key}")
                features[key] = f["geometry"]
                if not valid(f):
                    invalid.add(key)
        retried = set()
        if invalid:
            exact = json.loads(checked(f"{year}-gis-exact-retry.json"))
            for f in exact["features"]:
                key = str(f["properties"][id_field])
                if key not in invalid or key in retried or f["properties"]["totvoting"] != voters[key] or not valid(f):
                    raise ValueError(f"Wrong or invalid original polygon: {year}, {key}")
                retried.add(key)
                features[key] = f["geometry"]
        if invalid != retried or voters.keys() != features.keys():
            raise ValueError(f"Incomplete dated Minnesota geometry: {year}")
        families = {}
        for key in sorted(features):
            families.setdefault(key[:5], []).append({
                "type": "Feature", "properties": {"precinct_id": key, "reported_total_voters": voters[key]},
                "geometry": features[key],
            })
        receipt = {"precincts": len(voters), "total_voters": sum(voters.values()),
                   "exact_replacements": sorted(retried), "counties": {}}
        for county, county_features in families.items():
            filename = f"precinct-MN-{year}-{county}.json.gz"
            decoded = encoded({
                "contract": "participation.mn_historical_precinct_display.v1", "state_code": "MN",
                "election_date": election, "county_geoid": county, "coordinate_system": "EPSG:4326",
                "display_only": True, "ballots_allocated_by_geometry": False,
                "features": county_features,
            })
            buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
                compressed.write(decoded)
            body = buffer.getvalue()
            (output / filename).write_bytes(body)
            receipt["counties"][county] = {"filename": filename, **pin(body)}
        receipts[election] = receipt
    (output / "mn-precinct-geometry.json").write_bytes(encoded(receipts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.inputs, args.output, json.loads(args.manifest.read_bytes()))
