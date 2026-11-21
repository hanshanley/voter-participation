"""Compare November 2026 participation with the January legislative reference."""

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile


BOUNDARY_SHA = "ee7c4fab405f60fb1e21653605378754ab93b1566c7a1b2e7a010ac349609766"
PARISH_SHA = "63af804e471ee34dab6af115bdb47f23d3e1435965584d0c5c21564ea161f096"
BOUNDARY_DATE = "2026-01-27"
ELECTION = "2026-11-03"
SOURCE = "https://electionstatistics.sos.la.gov/Data/Post_Election_Statistics/parish/2026_1103_par.xlsx"
PRECINCT_ID = re.compile(r"(PAR [0-9]{2}) W ([A-Z0-9-]+) P ([A-Z0-9-]+)")


def require(condition, label):
    if not condition:
        raise ValueError(label)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def parish_name(name):
    return re.sub(r"[^A-Z0-9]", "", name.strip().upper().removesuffix(" PARISH"))


def unit_name(name):
    return re.sub(r"(?<![A-Z0-9])0+(?=[0-9])", "", name.strip().upper())


def participation(body, parishes):
    snapshot = json.loads(gzip.decompress(body))
    require(snapshot.get("state_code") == "LA" and snapshot.get("year") == 2026,
            "Expected the Louisiana 2026 count snapshot")
    parents, children, editions = {}, defaultdict(list), set()
    statewide = []
    for row in snapshot["records"]:
        view = row["view"]
        if view.get("participation_measure_kind") != "voters_reported":
            continue
        native = view.get("native_record", {})
        level, key = view.get("geography_level"), native.get("native_id")
        n = native.get("voters_participating")
        require(row["election"]["date"] == ELECTION and row["measure"]["literal"] == "# VOTING"
                and view["source_mode"] == "all_methods" and type(n) is int and n >= 0
                and n == view["ballots"] and view["denominator"] is None,
                "Changed Louisiana participation measure")
        if level == "state":
            statewide.append(n)
            continue
        fips = parishes.get(parish_name(view["county"]))
        sha = view["source_sha256"]
        require(fips is not None and view["source_url"] == SOURCE and re.fullmatch(r"[a-f0-9]{64}", sha),
                "Unrecognized Louisiana parish or source provenance")
        editions.add(sha)
        if level == "county_equivalent":
            require(fips not in parents, "Duplicate Louisiana parish total")
            parents[fips] = (key, n)
        else:
            match = PRECINCT_ID.fullmatch(key or "")
            require(level == "precinct" and match and key == view["unit_key"], "Unrecognized Louisiana precinct key")
            local = unit_name(match[3] if match[2] == "00" else f"{match[2]}-{match[3]}")
            children[fips].append((key, match[1], local, n))
    require(len(editions) == len(statewide) == 1 and set(parishes.values()) == parents.keys() == children.keys(),
            "Incomplete or mixed Louisiana snapshot")
    require(sum(n for _, n in parents.values()) == statewide[0], "Parish and state counts do not reconcile")
    for fips, rows in children.items():
        parent, n = parents[fips]
        require(len({r[0] for r in rows}) == len(rows) and all(r[1] == parent for r in rows)
                and sum(r[3] for r in rows) == n, "Precinct roster or parish counts do not reconcile")
    return children, editions.pop()


def audit(archive, reference, counts):
    from pyproj import CRS, Transformer
    import shapefile
    from shapely import transform
    from shapely.geometry import mapping, shape

    require(digest(archive) == BOUNDARY_SHA and digest(reference) == PARISH_SHA,
            "Boundary inputs are not the reviewed editions")
    features = json.loads(gzip.decompress(reference))["features"]
    parishes = {parish_name(p["properties"]["name"]): p["properties"]["key"] for p in features}
    require(len(features) == len(parishes) == len(set(parishes.values())) == 64, "Incomplete parish reference")
    children, edition = participation(counts, parishes)
    geometry = defaultdict(lambda: defaultdict(list))
    with ZipFile(io.BytesIO(archive)) as zip_file:
        prj = zip_file.read(next(name for name in zip_file.namelist() if name.endswith(".prj"))).decode("ascii")
        to_wgs84 = Transformer.from_crs(CRS.from_wkt(prj), "EPSG:4326", always_xy=True).transform
        with shapefile.Reader(**{ext: io.BytesIO(zip_file.read(next(
            name for name in zip_file.namelist() if name.endswith("." + ext))))
            for ext in ("dbf", "shp", "shx")}) as reader:
            for item in reader.iterShapeRecords():
                fields = item.record.as_dict()
                fips = "22" + fields["COUNTYFP20"]
                require(fips in children and fields["STATEFP20"] == "22" and fields["GLEVEL"] == "V",
                        "Unexpected legislative geometry identity")
                geometry[fips][unit_name(fields["UNIT_NAME"])].append(item)

    decisions, shape_decisions, contextual = [], [], []
    for fips, rows in sorted(children.items()):
        by_unit = defaultdict(list)
        for key, _, local, n in rows:
            by_unit[local].append((key, n))
        shapes = geometry[fips]
        exact = set(by_unit) == set(shapes) and all(len(by_unit[k]) == len(shapes[k]) == 1 for k in by_unit)
        mapped = set()
        for local, claims in sorted(by_unit.items()):
            candidates = shapes.get(local, ())
            valid = False
            if exact:
                try:
                    original = shape(candidates[0].shape.__geo_interface__)
                    g = transform(original, to_wgs84, interleaved=False)
                    valid = g.geom_type in {"Polygon", "MultiPolygon"} and g.is_valid and not g.is_empty
                except (TypeError, ValueError):
                    pass
            status = ("january_reference_match_only" if valid else "invalid_reference_geometry" if exact
                      else "geographic_roster_differs")
            for key, n in claims:
                properties = {"parish_fips": fips, "normalized_unit": local, "native_precinct": key,
                              "reported_voters": n, "reference_status": status,
                              "source_sha256": edition, "election_date": ELECTION,
                              "boundary_reference_date": BOUNDARY_DATE, "november_geometry_qualified": False}
                decisions.append({**properties, "local_shape_candidates": len(candidates)})
                if valid:
                    mapped.add(local)
                    contextual.append({"type": "Feature", "geometry": mapping(g), "properties": properties})
        for local, candidates in sorted(shapes.items()):
            for item in candidates:
                shape_decisions.append({"parish_fips": fips, "normalized_unit": local,
                                        "reference_name": item.record["UNIT_NAME"],
                                        "reference_unit_code": item.record["UNIT_CODE"],
                                        "local_count_candidates": len(by_unit.get(local, ())),
                                        "shown_as_january_context": local in mapped})
    return decisions, shape_decisions, {"type": "FeatureCollection", "features": contextual}


def write_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("legislature_zip", "parish_reference", "count_snapshot", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    counts, shapes, reference = audit(*(path.read_bytes() for path in (
        args.legislature_zip, args.parish_reference, args.count_snapshot)))
    args.output.mkdir(parents=True, exist_ok=True)
    write_rows(args.output / "precinct-count-decisions.csv", counts)
    write_rows(args.output / "reference-shape-decisions.csv", shapes)
    (args.output / "january-reference-matches.geojson").write_text(
        json.dumps(reference, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"precinct_counts": len(counts), "reference_shapes": len(shapes),
                      "january_only_matches": len(reference["features"]), "november_geometry_qualified": 0}))


if __name__ == "__main__":
    main()
