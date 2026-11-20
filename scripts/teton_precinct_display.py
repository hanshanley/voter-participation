"""Reproduce the reviewed Teton County 2026 precinct display layer offline."""

import argparse
from collections import defaultdict
import gzip
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sqlite3
import struct

from shapely import box, from_wkb, make_valid, normalize, union_all
from shapely.geometry import mapping


SOURCE = {
    "url": "https://maps.terragis.net/tetonwy/mapserver/download/data/precincts.gpkg",
    "bytes": 540672,
    "sha256": "191cf38eca6b9b010469c39c46276aa4d3f4e50281108dd38c64cf8e00b5ed6e",
}
KEYS = {f"1-{n}" for n in (1, 2, 3, 4, 5, 6, 7, 10, 11, 12)} | {
    "2-1", "3-1", "4-1", "4-2", "4-3", "4-4", "5-1",
}
POLYGONS = ("Polygon", "MultiPolygon")


def decode(blob):
    offset = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((blob[3] >> 1) & 7)
    if (blob[:3] != b"GP\0" or blob[3] & 248 or offset is None
            or struct.unpack("<i" if blob[3] & 1 else ">i", blob[4:8])[0] != 3739):
        raise ValueError("Unexpected GeoPackage precinct geometry header")
    geom = from_wkb(blob[8 + offset:])
    if geom.is_empty or geom.geom_type not in POLYGONS or geom.has_z:
        raise ValueError("Unexpected precinct polygon type")
    return geom


def build(original):
    body = original.read_bytes()
    if len(body) != SOURCE["bytes"] or hashlib.sha256(body).hexdigest() != SOURCE["sha256"]:
        raise ValueError("GeoPackage differs from the reviewed edition")
    with sqlite3.connect(original.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        edition = db.execute(
            "SELECT last_change, srs_id FROM gpkg_contents WHERE table_name='precincts'"
        ).fetchone()
        parts = db.execute("SELECT precinct, geom FROM precincts ORDER BY fid").fetchall()
    if edition != ("2026-03-17T23:11:40.896Z", 3739) or len(parts) != 18:
        raise ValueError("Unexpected precinct layer edition or record count")

    collected, repairs = defaultdict(list), {}
    for native, blob in parts:
        key = "-".join(str(int(item)) for item in native.split("-"))
        raw = decode(blob)
        geom = raw if raw.is_valid else make_valid(raw)
        delta = abs(geom.area - raw.area)
        if geom.geom_type not in POLYGONS or not geom.is_valid or geom.is_empty or delta > 0.1:
            raise ValueError("Unexpected precinct topology repair")
        if not raw.is_valid:
            repairs[key] = delta
        collected[key].append(geom)
    if set(collected) != KEYS or set(repairs) != {"1-6", "1-10"} or len(collected["1-5"]) != 2:
        raise ValueError("Unexpected precinct footprint or multipart inventory")
    shapes = {key: union_all(pieces) for key, pieces in sorted(collected.items())}
    overlaps = defaultdict(list)
    for (a, ga), (b, gb) in combinations(shapes.items(), 2):
        overlap = ga.intersection(gb)
        if overlap.area > 80:
            raise ValueError("Overlap exceeds display-only tolerance")
        if overlap.area:
            overlaps[a].append(overlap)
            overlaps[b].append(overlap)

    # Leave ambiguous slivers blank on both sides; do not allocate them to either precinct.
    projected, removed = {}, {}
    for key, geom in shapes.items():
        clipped = geom.difference(union_all(overlaps[key])) if overlaps[key] else geom
        removed[key] = max(0, geom.area - clipped.area)
        if (not clipped.is_valid or clipped.is_empty or clipped.geom_type not in POLYGONS
                or removed[key] > 100 or removed[key] / geom.area > 0.00001):
            raise ValueError("Display repair would materially change a precinct footprint")
        projected[key] = clipped
    if any(a.intersection(b).area > 0.001 for a, b in combinations(projected.values(), 2)):
        raise ValueError("Overlapping display polygons")

    features = []
    for key, geom in projected.items():
        if not geom.within(box(2_300_000, 1_300_000, 2_700_000, 1_900_000)):
            raise ValueError("Invalid projected display polygon")
        features.append({"properties": {"precinct_key": key}, "geometry": mapping(normalize(geom))})
    return {
        "contract": "participation.teton_precinct_display.v1", "coordinate_system": "EPSG:3739",
        "state_code": "WY", "county": "Teton", "election_date": "2026-11-03",
        "source": SOURCE, "source_updated_at": edition[0],
        "plan_adoption": "https://tetoncountywy.gov/AgendaCenter/ViewFile/Minutes/_05052026-2942",
        "plan_report": "https://tetoncountywy.gov/DocumentCenter/View/40625/05056-Resolution-of-Election-Districts",
        "display_only": True, "ballots_allocated_by_geometry": False,
        "repairs_signed_area_delta_sq_ft": repairs, "overlap_removed_sq_ft_by_precinct": removed,
        "features": features,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    body = json.dumps(build(args.original), sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    with args.output.open("xb") as target:
        target.write(gzip.compress(body, mtime=0))


if __name__ == "__main__":
    main()
