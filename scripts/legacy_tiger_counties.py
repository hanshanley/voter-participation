"""Reconstruct county display outlines from Census 2006 Second Edition TIGER/Line."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import zipfile

from shapely import MultiLineString, build_area, normalize, polygonize_full
from shapely.geometry import mapping


VERSIONS = {b"0906", b"1006", b"1106", b"1206", b"0107"}
REFERENCE_DATE = "2006-01-01"
ARCHIVE = "https://www2.census.gov/geo/tiger/tiger2006se/"


def module_roster(body, state_fips):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.modules = set()

        def handle_starttag(self, tag, attrs):
            if tag != "a":
                return
            href = dict(attrs).get("href") or ""
            match = re.fullmatch(r"TGR(" + state_fips + r"[0-9]{3})\.ZIP", href)
            if match:
                self.modules.add(match[1])

    links = Links()
    links.feed(body.decode("utf-8"))
    return links.modules


def acquire_modules(collector, roster, originals):
    from scripts.participation_intake.contract import IntakeError, pin
    from scripts.results_intake import source_error

    state, fips = roster["state"], roster["state_fips"]
    if not re.fullmatch(r"[A-Z]{2}", state) or not re.fullmatch(r"[0-9]{2}", fips):
        raise ValueError("Invalid state identity")
    modules = roster["modules"]
    expected = {item["fips"] for item in modules}
    if not expected or len(expected) != len(modules) or any(
        not re.fullmatch(fips + r"[0-9]{3}", key) for key in expected
    ):
        raise ValueError("Invalid reviewed county roster")
    index = f"{ARCHIVE}{state}/"
    body, _ = collector.acquire(index)
    if module_roster(body, fips) != expected:
        raise ValueError("Census archive and reviewed county rosters differ")
    result = {"state": state, "state_name": roster["state_name"], "state_fips": fips,
              "expected_module_ids": sorted(expected),
              "index": {"url": index, **pin(body)}, "modules": [], "holds": []}
    originals.mkdir(parents=True, exist_ok=True)
    for item in sorted(modules, key=lambda item: item["fips"]):
        key = item["fips"]
        filename = f"TGR{key}.ZIP"
        url = index + filename
        path = originals / filename
        try:
            collector.guard(url)
            retained = path.read_bytes() if path.exists() else None
            expected_pin = {k: item.get(k) for k in ("bytes", "sha256")}
            if retained is not None and all(value is not None for value in expected_pin.values()):
                if pin(retained) != expected_pin:
                    raise ValueError("Retained Census module differs from its reviewed pin")
                data = retained
            else:
                data, _ = collector.acquire(url)
                if retained is not None and retained != data:
                    raise ValueError("Existing unpinned Census module differs from the verified source")
            county_outline(data, key, roster["state_name"], item["census_title"])
            if not path.exists():
                with path.open("xb") as target:
                    target.write(data)
        except (IntakeError, ValueError, zipfile.BadZipFile) as error:
            result["holds"].append({"fips": key, "url": url, "status": source_error(error), "reason": str(error)})
        else:
            result["modules"].append({"fips": key, "name": item["name"], "census_title": item["census_title"],
                                      "url": url, **pin(data)})
        finally:
            # This sequential acquisition does not need to keep each county body in RAM.
            collector.bodies.pop(url, None)
    return result


def county_outline(body, fips, state_name, county_title):
    if not re.fullmatch(r"[0-9]{5}", fips) or not 0 < len(body) <= 64 * 1024**2:
        raise ValueError("Invalid county module ID or size")
    stem = f"TGR{fips}"
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        def member(suffix, bound):
            name = f"{stem}.{suffix}"
            if archive.namelist().count(name) != 1 or archive.getinfo(name).file_size > bound:
                raise ValueError(f"Invalid TIGER member {name}")
            return archive.read(name)

        title = f"Title: TIGER/Line Files, 2006 Second Edition, {state_name}, {county_title}".encode("ascii")
        metadata = member("MET", 1_000_000)
        if title not in {line.strip() for line in metadata.splitlines()}:
            raise ValueError(f"County metadata differs for {fips}")
        return boundary_area(member("RT1", 128 * 1024**2), member("RT2", 128 * 1024**2))


def boundary_area(rt1, rt2):
    chains, shape = {}, defaultdict(dict)
    for row in rt1.splitlines():
        if len(row) != 228 or row[:1] != b"1" or row[1:5] not in VERSIONS or row[15:16] not in (b" ", b"1"):
            raise ValueError("Invalid TIGER complete-chain record")
        if row[15:16] != b"1":
            continue
        key = int(row[5:15])
        if key in chains:
            raise ValueError("Duplicate TIGER boundary chain")
        chains[key] = (point(row, 190), point(row, 209))
    for row in rt2.splitlines():
        if len(row) != 208 or row[:1] != b"2" or row[1:5] not in VERSIONS:
            raise ValueError("Invalid TIGER shape record")
        key = int(row[5:15])
        if key not in chains:
            continue
        sequence = int(row[15:18])
        if sequence < 1 or sequence in shape[key]:
            raise ValueError("Repeated or invalid TIGER shape sequence")
        points = [point(row, start) for start in range(18, 208, 19)]
        end = points.index((0, 0)) if (0, 0) in points else len(points)
        if not end or any(p != (0, 0) for p in points[end:]):
            raise ValueError("Invalid TIGER shape padding")
        shape[key][sequence] = points[:end]

    lines = []
    for key, (start, end) in chains.items():
        segments = shape.get(key, {})
        if sorted(segments) != list(range(1, len(segments) + 1)):
            raise ValueError("Noncontiguous TIGER shape sequence")
        if any(len(segments[i]) != 10 for i in range(1, len(segments))):
            raise ValueError("Short intermediate TIGER shape record")
        points = [start, *(p for i in sorted(segments) for p in segments[i]), end]
        if any(abs(x) > 180_000_000 or abs(y) > 90_000_000 for x, y in points):
            raise ValueError("TIGER coordinates outside longitude/latitude range")
        if any(abs(a[0] - b[0]) > 180_000_000 for a, b in zip(points, points[1:])):
            raise ValueError("Antimeridian-spanning TIGER chain needs separate review")
        if len(set(points)) < 2:
            raise ValueError("Degenerate TIGER boundary chain")
        lines.append(points)
    polygons, cuts, dangles, invalid = polygonize_full(MultiLineString(lines).geoms)
    if polygons.is_empty or any(not obj.is_empty for obj in (cuts, dangles, invalid)):
        raise ValueError("TIGER chains do not form closed county linework")
    linework = MultiLineString(lines)
    area = build_area(linework)
    if (area.geom_type not in ("Polygon", "MultiPolygon") or not area.is_valid or area.is_empty
            or not area.boundary.equals(linework)):
        raise ValueError("Reconstructed TIGER county does not preserve its boundary")
    return scaled_geojson(mapping(normalize(area)))


def point(row, start):
    return int(row[start:start + 10]), int(row[start + 10:start + 19])


def scaled_geojson(geometry):
    def scale(value):
        if len(value) == 2 and isinstance(value[0], float):
            return [n / 1_000_000 for n in value]
        return [scale(item) for item in value]
    return {"type": geometry["type"], "coordinates": scale(geometry["coordinates"])}


def build(manifest, directory):
    state, state_name, features, seen = manifest["state"], manifest["state_name"], [], set()
    if not re.fullmatch(r"[A-Z]{2}", state) or not re.fullmatch(r"[0-9]{2}", manifest["state_fips"]):
        raise ValueError("Invalid state identity")
    if manifest.get("holds"):
        raise ValueError("County outline publication requires a complete reviewed roster")
    for module in sorted(manifest["modules"], key=lambda item: item["fips"]):
        fips = module["fips"]
        if not re.fullmatch(manifest["state_fips"] + r"[0-9]{3}", fips) or fips in seen:
            raise ValueError("Unexpected or duplicate county module")
        seen.add(fips)
        data = (directory / f"TGR{fips}.ZIP").read_bytes()
        if len(data) != module["bytes"] or hashlib.sha256(data).hexdigest() != module["sha256"]:
            raise ValueError(f"Changed Census original: {fips}")
        features.append({
            "type": "Feature",
            "properties": {"key": fips, "name": module["name"], "state_code": state,
                           "boundary_year": 2006, "level": "county"},
            "geometry": county_outline(data, fips, state_name, module["census_title"]),
        })
    if not features or ("expected_module_ids" in manifest
                        and sorted(seen) != manifest["expected_module_ids"]):
        raise ValueError("Incomplete verified county module roster")
    return {"type": "FeatureCollection", "reference_date": REFERENCE_DATE, "features": features}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("originals", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--acquire", action="store_true", help="Acquire a reviewed state roster; output a manifest instead")
    parser.add_argument("--work-dir", type=Path, help="Cache and durable source-stop directory for acquisition")
    parser.add_argument("--registry", type=Path, default=Path("data/results-intake/registry.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_bytes())
    if args.acquire:
        from scripts.participation_intake.contract import encoded
        from scripts.results_intake import Collector, merge_stops, registry_config

        if args.work_dir is None or args.output.exists():
            parser.error("--acquire requires --work-dir and a new output manifest")
        prior = args.work_dir / "source-stops.json"
        config = registry_config(args.registry)
        stops = config["source_stops"]
        if prior.exists():
            stops = merge_stops(stops, json.loads(prior.read_bytes()))
        collector = Collector(args.work_dir, {}, stops, datetime.now(timezone.utc))
        captured = acquire_modules(collector, manifest, args.originals)
        with args.output.open("xb") as target:
            target.write(encoded(captured))
        print(f"Verified {len(captured['modules'])} county modules; held {len(captured['holds'])}")
        return
    collection = build(manifest, args.originals)
    payload = json.dumps(collection, separators=(",", ":"), sort_keys=True, allow_nan=False).encode() + b"\n"
    with args.output.open("xb") as target:
        target.write(gzip.compress(payload, mtime=0))
    print(f"Reconstructed {len(collection['features'])} Census county outlines")


if __name__ == "__main__":
    main()
