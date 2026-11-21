"""Verify and render county tiles for the official 2008 and 2010 LCC-GIS vintages."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZipFile

from scripts import minnesota_precinct_history as mn
from scripts.participation_intake.contract import encoded, pin


EDITIONS = {
    "2008-11-04": ("elec08", "TOTVOTERS", "COUNTYID", "PRECINCT_1", 4145),
    "2010-11-02": ("elec2010", "TOTALVOTER", "COUNTYCODE", "PRECINCT", 4136),
}


def precinct_name(value):
    value = value.upper().replace(".", "")
    return " ".join(re.sub(r"\b([WP])-(?=\d+\b)", r"\1", value).split())


def identity_reason(row, matches, edition):
    if not matches:
        return "missing_polygon"
    if len(matches) != 1:
        return "duplicate_polygon_id"
    gis, _ = matches[0]
    _, vote_field, county_field, name_field, _ = EDITIONS[edition]
    def county_name(value):
        name = " ".join(str(value).upper().replace(".", "").split())
        return "SAINT LOUIS" if name == "ST LOUIS" and row["VTDID"].startswith("27137") else name

    if (str(gis[county_field]).zfill(2) != str(row["COUNTYCODE"]).zfill(2)
            or county_name(gis["COUNTY"]) != county_name(row["COUNTYNAME"])
            or str(gis["NUMBER_"]) != row["VTDID"]
            or (edition.startswith("2008") and str(gis["PRECINCTID"]) != row["VTDID"])):
        return "gis_identity_disagrees"
    if precinct_name(str(gis[name_field])) != precinct_name(row["PCTNAME"]):
        return "gis_name_disagrees"
    if type(gis[vote_field]) is not int or gis[vote_field] != row["TOTVOTING"]:
        return "gis_voter_count_disagrees"
    return None


def polygons(body, edition):
    from pyproj import CRS
    import shapefile

    stem, vote_field, county_field, name_field, expected = EDITIONS[edition]
    with ZipFile(BytesIO(body)) as archive:
        parts = {}
        for ext in ("prj", "shp", "shx", "dbf"):
            name = f"{stem}.{ext}"
            if archive.namelist().count(name) != 1 or archive.getinfo(name).file_size > 16_000_000:
                raise ValueError(f"Unexpected Minnesota archive member: {name}")
            parts[ext] = archive.read(name)
    if not CRS.from_wkt(parts.pop("prj").decode("ascii")).equals(CRS.from_epsg(26915)):
        raise ValueError("Unexpected Minnesota archive projection")
    keys = {"DISTRICT", "NUMBER_", "COUNTY", vote_field, county_field, name_field}
    if edition.startswith("2008"):
        keys.add("PRECINCTID")
    with shapefile.Reader(**{ext: BytesIO(data) for ext, data in parts.items()}, encoding="cp1252") as reader:
        source_fields = [f[0] for f in reader.fields[1:]]
        names = [name.upper() for name in source_fields]
        if len(reader) != expected or len(names) != len(set(names)) or keys - set(names):
            raise ValueError("Unexpected Minnesota GIS report schema or shape count")
        grouped = defaultdict(list)
        for feature in reader.iterShapeRecords(fields=[name for name in source_fields if name.upper() in keys]):
            row = {k.upper(): v for k, v in feature.record.as_dict().items()}
            if not re.fullmatch(r"27[0-9]{7}", str(row["DISTRICT"])):
                raise ValueError("Malformed Minnesota GIS precinct ID")
            grouped[str(row["DISTRICT"])].append((row, feature.shape))
        if sum(map(len, grouped.values())) != expected:
            raise ValueError("Incomplete Minnesota GIS shape inventory")
    return grouped


def overlaps(shapes):
    from shapely import STRtree

    keys = sorted(shapes)
    geometry = [shapes[key] for key in keys]
    held = set()
    for i, j in zip(*STRtree(geometry).query(geometry, predicate="intersects")):
        if i < j and geometry[i].intersection(geometry[j]).area > 0:
            held.update((keys[i], keys[j]))
    return held


def verified_features(query, grouped, edition):
    from pyproj import Transformer
    from shapely import transform
    from shapely.geometry import mapping, shape

    project = Transformer.from_crs(26915, 4326, always_xy=True).transform
    decisions, native, wgs84 = [], {}, {}
    _, vote_field, _, name_field, _ = EDITIONS[edition]
    for row in sorted(query["precincts"], key=lambda row: row["VTDID"]):
        key = row["VTDID"]
        matches = grouped.get(key, [])
        reason = identity_reason(row, matches, edition)
        if reason is None:
            original = shape(matches[0][1].__geo_interface__)
            if (original.is_empty or not original.is_valid or original.area <= 0
                    or original.geom_type not in {"Polygon", "MultiPolygon"}):
                reason = "invalid_polygon"
            else:
                projected = transform(original, project, interleaved=False)
                w, s, e, n = projected.bounds
                if not projected.is_valid or not (-98 < w < e < -89 and 43 < s < n < 50):
                    reason = "invalid_projected_polygon"
                else:
                    native[key], wgs84[key] = original, projected
        decisions.append({
            "election_date": edition, "county_geoid": key[:5], "precinct_id": key,
            "precinct_name": row["PCTNAME"], "reported_total_voters": row["TOTVOTING"],
            "gis_rows": len(matches), "gis_precinct_name": matches[0][0][name_field] if len(matches) == 1 else None,
            "gis_reported_voters": matches[0][0][vote_field] if len(matches) == 1 else None,
            "map_decision": reason or "mapped",
        })
    # Check topology in both the official projection and the delivered display coordinates.
    unsafe = overlaps(native) | overlaps(wgs84)
    for row in decisions:
        if row["precinct_id"] in unsafe:
            row["map_decision"] = "polygon_overlap"
    features = {
        row["precinct_id"]: {
            "type": "Feature", "properties": {"precinct_id": row["precinct_id"],
                                              "reported_total_voters": row["reported_total_voters"]},
            "geometry": mapping(wgs84[row["precinct_id"]]),
        } for row in decisions if row["map_decision"] == "mapped"
    }
    return decisions, features


def build(inputs, output, manifest):
    def checked(filename):
        body = (inputs / filename).read_bytes()
        if pin(body) != manifest[filename]:
            raise ValueError(f"Original differs from pin: {filename}")
        return body

    output.mkdir(parents=True, exist_ok=True)
    index = {}
    for edition, (stem, vote_field, _, _, _) in EDITIONS.items():
        year = edition[:4]
        query = mn.parse(checked(f"{year}.xls"), edition)
        grouped = polygons(checked(f"{stem}.zip"), edition)
        decisions, features = verified_features(query, grouped, edition)
        if not features:
            raise ValueError(f"No verified Minnesota precinct map records: {edition}")
        geographic = {row["precinct_id"] for row in decisions}
        gis_only = [{"precinct_id": key, "gis_rows": len(grouped[key]),
                     "gis_voter_values": [r[vote_field] for r, _ in grouped[key]]}
                    for key in sorted(grouped.keys() - geographic)]
        state_only = query.get("statewide_unallocated", [])
        receipt = index[edition] = {
            "workbook_precincts": len(decisions), "mapped_precincts": len(features),
            "mapped_voters": sum(r["reported_total_voters"] for r in decisions if r["map_decision"] == "mapped"),
            "workbook_geographic_voters": sum(r["reported_total_voters"] for r in decisions),
            "statewide_unallocated_voters": sum(r["TOTVOTING"] for r in state_only),
            "reasons": dict(Counter(r["map_decision"] for r in decisions)), "gis_only": gis_only, "counties": {},
            "workbook_sha256": manifest[f"{year}.xls"]["sha256"], "geometry_sha256": manifest[f"{stem}.zip"]["sha256"],
        }
        with (output / f"MN-{year}-decisions.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, decisions[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(decisions)
        (output / f"MN-{year}-participation-query.json").write_bytes(encoded(query))
        counties = defaultdict(list)
        for row in decisions:
            counties[row["county_geoid"]].append(row)
        for county, rows in counties.items():
            mapped = [features[r["precinct_id"]] for r in rows if r["precinct_id"] in features]
            body = gzip.compress(encoded({
                "contract": "participation.mn_historical_precinct_display.v1", "state_code": "MN",
                "election_date": edition, "county_geoid": county, "coordinate_system": "EPSG:4326",
                "display_only": True, "ballots_allocated_by_geometry": False,
                "workbook_precincts": len(rows), "workbook_sha256": receipt["workbook_sha256"],
                "held_precinct_ids": [r["precinct_id"] for r in rows if r["precinct_id"] not in features],
                "features": mapped,
            }), mtime=0)
            filename = f"precinct-MN-{year}-{county}.json.gz"
            (output / filename).write_bytes(body)
            receipt["counties"][county] = {"filename": filename, **pin(body)}
    (output / "mn-legacy-precinct-geometry.json").write_bytes(encoded(index))
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build(args.inputs, args.output, json.loads(args.manifest.read_bytes()))
    for date, data in result.items():
        print(date, data["mapped_precincts"], data["mapped_voters"], data["reasons"])
