"""Reproduce the reviewed Denver 2022 precinct display layer offline."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re

from shapely import STRtree, normalize, union_all
from shapely.geometry import box, mapping, shape

SOURCE = {
    "url": "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
           "Precincts_2022_MPU2/FeatureServer/0/query?where=1%3D1&outFields=ID%2CNAME"
           "&outSR=4326&orderByFields=FID%20ASC&f=geojson",
    "bytes": 2013909,
    "sha256": "201f70438c09e350d020610604a2ce8b6e3c085a199482adc6f0066ed423239c",
}
ELECTION = "2022-11-08"
POLYGONS = ("Polygon", "MultiPolygon")
TURNOUT_SHA = "78425f6de4eeeabb839e85021f9e11cac299ab0fdad044b5a74cf994cc193879"


def build(body, turnout):
    if len(body) != SOURCE["bytes"] or hashlib.sha256(body).hexdigest() != SOURCE["sha256"]:
        raise ValueError("Denver source differs from the reviewed edition")
    raw = json.loads(body)
    if raw["crs"] != {"type": "name", "properties": {"name": "EPSG:4326"}}:
        raise ValueError("Unexpected Denver precinct coordinate system")
    bounds = box(-106, 39, -104, 41)
    polygons, repairs = {}, []
    for feature in raw["features"]:
        key = feature["properties"]["NAME"]
        geom = shape(feature["geometry"])
        if not re.fullmatch(r"[0-9]{3}", key) or key in polygons or geom.geom_type not in POLYGONS:
            raise ValueError("Unexpected Denver precinct identity or geometry type")
        # Dissolve same-ID shells without buffering, filling gaps, or transferring area.
        if not geom.is_valid and key == "915" and geom.geom_type == "MultiPolygon":
            parts = list(geom.geoms)
            if not all(part.is_valid for part in parts):
                raise ValueError("Unreviewed invalid Denver precinct shell")
            geom = union_all(parts)
            repairs.append(key)
        if geom.geom_type not in POLYGONS or not geom.is_valid or geom.is_empty or not geom.within(bounds):
            raise ValueError("Invalid Denver precinct display polygon")
        polygons[key] = geom
    if len(polygons) != 301 or repairs != ["915"]:
        raise ValueError("Denver precinct inventory differs")
    if hashlib.sha256(turnout).hexdigest() != TURNOUT_SHA:
        raise ValueError("Denver turnout original differs from the reviewed edition")
    ids, county, controls = {}, None, None
    counts = 0
    for level, name, *_registration, ballots in list(csv.reader(io.StringIO(turnout.decode("utf-8-sig"))))[2:]:
        if level == "County":
            county = name
            if county == "Denver":
                controls = int(ballots)
        if level == "Precinct" and county == "Denver":
            key = name[-3:]
            if not re.fullmatch(r"[0-9]{5}16[0-9]{3}", name) or key in ids:
                raise ValueError("Ambiguous Denver precinct turnout identity")
            ids[key] = name
            counts += int(ballots)
    if ids.keys() != polygons.keys() or counts != controls:
        raise ValueError("Denver precincts do not reconcile to the printed county")
    values = list(polygons.values())
    tree = STRtree(values)
    for i, j in zip(*tree.query(values, predicate="intersects")):
        if i < j and values[i].intersection(values[j]).area > 1e-14:
            raise ValueError("Unreviewed Denver precinct overlap")
    return {
        "contract": "participation.denver_precinct_display.v1",
        "state_code": "CO", "county": "Denver", "election_date": ELECTION,
        "coordinate_system": "EPSG:4326", "display_only": True, "ballots_allocated_by_geometry": False,
        "source": SOURCE, "same_precinct_shells_dissolved": repairs, "turnout_sha256": TURNOUT_SHA,
        "features": [{"properties": {"precinct": ids[key]}, "geometry": mapping(normalize(geom))}
                     for key, geom in sorted(polygons.items())],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("turnout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    body = json.dumps(build(args.original.read_bytes(), args.turnout.read_bytes()),
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    with args.output.open("xb") as target:
        target.write(gzip.compress((body + "\n").encode(), mtime=0))


if __name__ == "__main__":
    main()
