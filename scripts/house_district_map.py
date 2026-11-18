"""Compile dated Census district outlines; never infer electoral comparability."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile

from scripts.congressional_geography import FIPS


CONTRACT = "participation.house_district_geometry.v1"
METHOD = "nad83_albers_north_up_display_only_topology_preserving_0.25_viewbox_units"
CRS = "EPSG:4269"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def pin(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def compressed(body):
    result = bytearray(gzip.compress(body, mtime=0))
    result[9] = 3
    return bytes(result)


def district_key(state, district):
    require(state in FIPS and re.fullmatch(r"[0-9]{2}|ZZ", district) is not None,
            "Invalid literal state or district code")
    return state + "-" + ("AL" if district == "00" else district)


def read_archive(body, state, year, congress):
    import shapefile
    from pyproj import CRS as CoordinateReferenceSystem
    from shapely.geometry import shape

    stem = f"tl_{year}_{FIPS[state]}_cd{congress}"
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names))
                and all("/" not in name and "\\" not in name and name.startswith(stem + ".")
                        for name in names)
                and all(info.file_size < 200_000_000 for info in archive.infolist()),
                "Unexpected district archive member")
        for extension in (".shp", ".shx", ".dbf", ".prj"):
            require(stem + extension in names, "Incomplete district archive")
        projection = archive.read(stem + ".prj")
        require(CoordinateReferenceSystem.from_wkt(projection.decode()).to_epsg() == 4269,
                "District coordinates are not native NAD83 longitude/latitude")
        reader = shapefile.Reader(**{extension: io.BytesIO(archive.read(stem + "." + extension))
                                     for extension in ("shp", "shx", "dbf")})
        require(reader.shapeType == shapefile.POLYGON, "District source is not polygon geometry")
        records, shapes, seen = [], {}, set()
        for item in reader.iterShapeRecords():
            native = item.record.as_dict()
            district = native.get(f"CD{congress}FP")
            key = district_key(state, district)
            require(key not in seen and native.get("STATEFP") == FIPS[state]
                    and native.get("GEOID") == FIPS[state] + district
                    and native.get("CDSESSN") == str(congress),
                    "Duplicate district, wrong state, session or leading-zero GEOID")
            seen.add(key)
            rings = [list(map(list, item.shape.points[start:end]))
                     for start, end in zip(item.shape.parts,
                                           list(item.shape.parts)[1:] + [len(item.shape.points)])]
            require(rings and all(len(ring) >= 4 and ring[0] == ring[-1]
                                 and all(len(point) == 2 and all(math.isfinite(x) for x in point)
                                         and -180 <= point[0] <= 180 and -90 <= point[1] <= 90
                                         for point in ring) for ring in rings),
                    "Invalid, unclosed or nonfinite native district ring")
            geometry = shape(item.shape.__geo_interface__)
            require(geometry.geom_type in ("Polygon", "MultiPolygon") and not geometry.is_empty
                    and geometry.is_valid, "Empty, invalid or nonpolygon district")
            records.append({
                "district": key, "state_code": state, "state_fips": FIPS[state],
                "district_code": district, "geoid": native["GEOID"],
                "congress": congress, "product_year": year, "native_crs": CRS,
                "unassigned_area": district == "ZZ", "native_geometry_valid": geometry.is_valid,
                "native_ring_count": len(rings), "native_vertices": sum(map(len, rings)),
                "native_rings_sha256": pin(encoded(rings))["sha256"],
                "native_attributes": native,
            })
            shapes[key] = geometry
        require(len(records) == reader.numRecords, "Native shape/attribute inventory differs")
    voting = {row["district_code"] for row in records if not row["unassigned_area"]}
    require(voting == ({"00"} if len(voting) == 1 else
                       {f"{seat:02d}" for seat in range(1, len(voting) + 1)}),
            "Incomplete contiguous state voting-seat inventory")
    return records, shapes


def conic(meridian, lower, upper):
    radians = math.pi / 180
    n = (math.sin(lower * radians) + math.sin(upper * radians)) / 2
    c = math.cos(lower * radians) ** 2 + 2 * n * math.sin(lower * radians)

    def project(lon, lat, z=None):
        theta = n * (((lon - meridian + 540) % 360) - 180) * radians
        rho = math.sqrt(c - 2 * n * math.sin(lat * radians)) / n
        return rho * math.sin(theta), -rho * math.cos(theta)

    return project


def polygon_rings(geometry):
    polygons = [geometry] if geometry.geom_type == "Polygon" else geometry.geoms
    return [ring for polygon in polygons for ring in [polygon.exterior, *polygon.interiors]]


def display_paths(records, shapes):
    from shapely import affinity
    from shapely.ops import transform

    output = []
    for states, project, box in (
        (None, conic(-96, 29.5, 45.5), (25, 20, 950, 500)),
        ({"AK"}, conic(-154, 55, 65), (60, 465, 200, 125)),
        ({"HI"}, conic(-157, 8, 18), (310, 525, 120, 65)),
    ):
        selected = [row for row in records if (row["state_code"] in states if states
                    else row["state_code"] not in ("AK", "HI"))]
        projected = {row["district"]: transform(project, shapes[row["district"]]) for row in selected}
        bounds = [geometry.bounds for geometry in projected.values()]
        x0, y0 = min(b[0] for b in bounds), min(b[1] for b in bounds)
        x1, y1 = max(b[2] for b in bounds), max(b[3] for b in bounds)
        left, top, width, height = box
        scale = min(width / (x1 - x0), height / (y1 - y0))
        ox, oy = left + (width - (x1 - x0) * scale) / 2, top + (height - (y1 - y0) * scale) / 2
        for row in selected:
            geometry = projected[row["district"]]
            native_display = affinity.translate(affinity.scale(
                geometry, xfact=scale, yfact=-scale, origin=(0, 0)),
                xoff=ox - x0 * scale, yoff=oy + y1 * scale)
            simplified = native_display.simplify(0.25, preserve_topology=True)
            if (not simplified.is_valid or simplified.is_empty
                    or len(polygon_rings(simplified)) != len(polygon_rings(native_display))):
                simplified = native_display
            rings = [list(ring.coords) for ring in polygon_rings(simplified)]
            path = "".join("".join(("M" if i == 0 else "L") + f"{x:.2f},{y:.2f}"
                                   for i, (x, y) in enumerate(ring)) + "Z" for ring in rings)
            point = simplified.representative_point()
            output.append({
                "district": row["district"], "state_code": row["state_code"],
                "state_fips": row["state_fips"], "district_code": row["district_code"],
                "geoid": row["geoid"], "unassigned_area": row["unassigned_area"],
                "d": path, "point": [round(point.x, 2), round(point.y, 2)],
                "bounds": [round(value, 2) for value in simplified.bounds],
                "native_rings_sha256": row["native_rings_sha256"],
            })
    return sorted(output, key=lambda row: row["geoid"])


def compile_geometry(inputs):
    records, shapes, sources = {}, {}, {}
    for name, folder, year, congress in (
        ("previous", "baseline-originals", 2025, 119), ("current", "originals", 2026, 120),
    ):
        acquisition = json.loads((inputs / ("baseline-district-acquisition.json"
                                            if name == "previous" else "district-acquisition.json")).read_bytes())
        require(set(acquisition["outcomes"]) == set(FIPS.values()), "Incomplete 50-state acquisition")
        records[name], shapes[name], sources[name] = [], {}, {}
        for state, fips in sorted(FIPS.items()):
            receipt = acquisition["outcomes"][fips]
            require(receipt["status"] == "acquired", "District original is unavailable")
            body = (inputs / folder / receipt["file"]).read_bytes()
            require(pin(body) == {key: receipt["receipt"][key] for key in ("bytes", "sha256")}
                    and receipt["url"] == "https://www2.census.gov/geo/tiger/"
                    + f"TIGER{year}/CD/tl_{year}_{fips}_cd{congress}.zip",
                    "District original bytes or native source identity differ")
            rows, geometries = read_archive(body, state, year, congress)
            records[name].extend(rows)
            shapes[name].update(geometries)
            sources[name][state] = {**pin(body), "url": receipt["url"], "file": receipt["file"]}
        require(sum(not row["unassigned_area"] for row in records[name]) == 435,
                "National voting-district inventory is not 435")
    current = {row["district"]: row for row in records["current"]}
    previous = {row["district"]: row for row in records["previous"]}
    require(current.keys() == previous.keys(), "Cross-session native district identities differ")
    comparisons = []
    for key in sorted(current):
        old, new = previous[key], current[key]
        same = (old["native_geometry_valid"] and new["native_geometry_valid"]
                and shapes["previous"][key].equals(shapes["current"][key]))
        comparisons.append({
            "district": key, "state_code": new["state_code"], "geoid": new["geoid"],
            "previous": old, "current": new, "native_geometry_exactly_equal": same,
            "geometric_method": "valid_unsimplified_native_nad83_topological_equality_no_tolerance",
            "electoral_comparison_qualified": False,
            "note": "Geometric equality alone does not qualify parties, election stage or returns.",
        })
    path_data = {
        "contract": CONTRACT, "election_year": 2026, "congress": 120, "baseline_congress": 119,
        "voting_districts": 435, "state_count": 50, "native_crs": CRS,
        "display_method": METHOD, "view_box": [0, 0, 1000, 640],
        "paths": display_paths(records["current"], shapes["current"]),
        "sources": sources, "historical_votes_allocated": False,
        "behavioral_models_allocated": False, "legal_boundary_certification": False,
    }
    return path_data, comparisons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths, comparisons = compile_geometry(args.inputs)
    bodies = {
        "district-paths.json.gz": compressed(encoded(paths)),
        "district-geography.json.gz": compressed(encoded(comparisons)),
    }
    columns = ["district", "state_code", "geoid", "native_geometry_exactly_equal",
               "electoral_comparison_qualified", "geometric_method"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: row[key] for key in columns} for row in comparisons)
    bodies["district-geography.csv"] = stream.getvalue().encode()
    manifest = {"contract": CONTRACT, "voting_districts": 435, "state_count": 50,
                "files": {name: pin(body) for name, body in sorted(bodies.items())},
                "new_qualified_electoral_comparisons": 0}
    bodies["manifest.json"] = encoded(manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        target = args.output / name
        if target.exists():
            require(target.read_bytes() == body, "Different existing immutable geometry output")
        else:
            with target.open("xb") as output:
                output.write(body)
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
