"""Collect and verify dated TIGERweb county layers in state/year batches."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode

from scripts.census_county_reference import build
from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_intake import Collector, merge_stops, write


ROOT = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
VINTAGES = {2010: "Census2010", 2020: "Census2020", **{
    year: f"ACS{year}" for year in (*range(2012, 2020), *range(2021, 2027))
}}


def requested(profiles):
    seen = set()
    result = []
    for profile in profiles:
        code, fips, counties, years = (profile[k] for k in ("state", "state_fips", "counties", "years"))
        if (not re.fullmatch(r"[A-Z]{2}", code) or not re.fullmatch(r"[0-9]{2}", fips)
                or not isinstance(counties, list) or not counties
                or any(not isinstance(n, str) or not n or n.strip() != n for n in counties)
                or len(counties) != len(set(counties))
                or not isinstance(years, list) or not years or any(type(y) is not int or y not in VINTAGES for y in years)):
            raise ValueError("Invalid reviewed county geometry profile")
        for year in years:
            identity = f"{code}-{year}-county-reference"
            if identity in seen:
                raise ValueError("Duplicate requested county geometry edition")
            seen.add(identity)
            result.append((identity, code, fips, year, sorted(counties)))
    if not result:
        raise ValueError("No reviewed county geometry editions requested")
    return result


def discover(body, server, year, acquire):
    metadata = json.loads(body)
    expected = f"January 1, {year} vintage"
    layers = [row for row in metadata.get("layers", []) if row.get("name") == "Counties"]
    if (expected not in metadata.get("serviceDescription", "") or len(layers) != 1
            or type(layer_id := layers[0].get("id")) is not int or not 0 <= layer_id < 1000):
        raise IntakeError("county_layer_not_verified", "No unique dated TIGERweb county layer")
    target = f"{server}/{layer_id}"
    body, _ = acquire(f"{target}?f=json")
    layer = json.loads(body)
    if (layer.get("name") != "Counties" or layer.get("geometryType") != "esriGeometryPolygon"
            or expected not in layer.get("description", "")
            or not {"GEOID", "STATE", "BASENAME"} <= {field["name"] for field in layer.get("fields", [])}):
        raise IntakeError("county_layer_not_verified", "TIGERweb county fields or vintage differ")
    return target, pin(body)


def retain_tile(work, state, year, body):
    checksum = pin(body)
    tile = work / f"county-{state}-{year}-{checksum['sha256']}.geojson.gz"
    if not tile.exists():
        temporary = None
        try:
            with NamedTemporaryFile(dir=work, delete=False) as file:
                temporary = Path(file.name)
                file.write(body)
            temporary.replace(tile)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if pin(tile.read_bytes()) != checksum:
        raise IntakeError("county_geometry_integrity", "Cached county display layer differs")
    return {"file": tile.name, **checksum}


def capture_batch(collector, profiles):
    entries = {}
    for identity, code, fips, year, roster in requested(profiles):
        server = ROOT + f"tigerWMS_{VINTAGES[year]}/MapServer"

        def verify(body):
            layer, metadata_pin = discover(body, server, year, collector.acquire)
            query = layer + "/query?" + urlencode({
                "where": f"STATE='{fips}'", "outFields": "GEOID,STATE,BASENAME",
                "returnGeometry": "true", "outSR": "4326", "f": "geojson",
            })
            original, _ = collector.acquire(query)
            if not 0 < len(original) <= 16_000_000:
                raise IntakeError("county_geometry_size", "TIGERweb county response exceeds the reviewed file size")
            display = build(original, year, code, fips, set(roster))
            return {"date": f"{year}-01-01", "state_code": code, "state_fips": fips, "roster": roster,
                    "county_layer": {"url": layer + "?f=json", **metadata_pin},
                    "original": {"url": query, **pin(original)},
                    "display": retain_tile(collector.work, code, year, display),
                    "election_day_boundary_equivalence_claimed": False, "ballots_allocated_by_geometry": False}

        prior = (collector.prior.get(identity) or {}).get("data")
        if prior and (fips != prior["state_fips"] or roster != prior["roster"]):
            raise ValueError(f"Reviewed county scope changed; use a separate work directory: {identity}")
        entries[identity] = collector.capture(identity, server + "?f=json", verify, shared_acquisition=True)
        if (good := entries[identity]["data"]) is not None:
            desc = good["display"]
            tile = collector.work / f"county-{code}-{year}-{desc['sha256']}.geojson.gz"
            if tile.name != desc["file"] or not tile.is_file() or pin(tile.read_bytes()) != {
                key: desc[key] for key in ("bytes", "sha256")
            }:
                raise IntakeError("county_geometry_integrity", f"Last-good county display layer is missing or changed: {identity}")
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True, help="JSON array of reviewed state/year profiles")
    parser.add_argument("--source-stops", type=Path, required=True, help="Active guarded intake stop ledger")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true", help="Replay permitted cached originals without transport")
    args = parser.parse_args()
    profiles = json.loads(args.profiles.read_bytes())
    requested(profiles)
    catalog = args.work_dir / "county-reference-catalog.json"
    prior = json.loads(catalog.read_bytes()) if catalog.exists() else {}
    existing = args.work_dir / "source-stops.json"
    stopped = json.loads(args.source_stops.read_bytes())
    if existing.exists():
        stopped = merge_stops(stopped, json.loads(existing.read_bytes()))
    collector = Collector(args.work_dir, prior, stopped, datetime.now(timezone.utc), offline=args.offline)
    current = capture_batch(collector, profiles)
    successor = {**prior, **current}
    if successor != prior:
        write(catalog, successor)
    print(json.dumps({key: value["status"] for key, value in current.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
