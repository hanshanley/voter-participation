"""Build count-only legislative precinct reference layers, not election-day joins."""

import argparse
from collections import defaultdict
import csv
import gzip
from html import escape
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile

from scripts.audit_louisiana_precinct_reference import PRECINCT_ID, digest, parish_name, unit_name, write_rows


def _parishes(body):
    collection = json.loads(gzip.decompress(body))
    result = {}
    for feature in collection["features"]:
        prop = feature["properties"]
        name, code = parish_name(prop["name"]), prop["key"]
        if (prop["state_code"] != "LA" or not re.fullmatch(r"22\d{3}", code)
                or name in result or code in result.values()):
            raise ValueError("Ambiguous Louisiana parish reference")
        result[name] = code
    if len(result) != 64:
        raise ValueError("Incomplete Louisiana parish reference")
    return result


def _counts(body, parishes, years):
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    keys, dates = set(), {}
    for row in csv.DictReader(io.StringIO(body.decode("utf-8"))):
        date = row["election_date"]
        year = int(date[:4])
        if year not in years:
            continue
        parish = parishes[parish_name(row["parish"])]
        match = PRECINCT_ID.fullmatch(row["native_precinct_id"])
        if (not match or match[1] != row["native_parish_id"]
                or row["geometry_qualified"] != "false" or row["rate_qualified"] != "false"
                or (date, row["native_precinct_id"]) in keys or dates.get(year, date) != date
                or not re.fullmatch(r"[a-f0-9]{64}", row["source_sha256"])
                or row["control_status"] not in {"parish_and_statewide_counts_agree",
                                                 "parish_rows_reconcile_statewide_control_differs"}
                or not row["voters_voting"].isdecimal()):
            raise ValueError("Invalid native count identity or provenance")
        dates[year] = date
        keys.add((date, row["native_precinct_id"]))
        name = unit_name(match[3] if match[2] == "00" else f"{match[2]}-{match[3]}")
        groups[year][parish][name].append(row)
    if set(groups) != years or any(set(group) != set(parishes.values()) for group in groups.values()):
        raise ValueError("Incomplete Louisiana historical precinct count scope")
    return groups


def _geometry(body, parishes):
    import shapefile
    from pyproj import CRS, Transformer
    from shapely import transform
    from shapely.geometry import shape

    def member(archive, extension):
        names = [name for name in archive.namelist() if name.lower().endswith("." + extension)]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 128_000_000:
            raise ValueError("Unexpected Louisiana precinct shape member")
        return archive.read(names[0])

    with ZipFile(io.BytesIO(body)) as archive:
        project = Transformer.from_crs(CRS.from_wkt(member(archive, "prj").decode("ascii")),
                                      "EPSG:4326", always_xy=True).transform
        groups = defaultdict(lambda: defaultdict(list))
        with shapefile.Reader(**{ext: io.BytesIO(member(archive, ext)) for ext in ("dbf", "shp", "shx")}) as reader:
            for item in reader.iterShapeRecords():
                fields = item.record.as_dict()
                parish = "22" + fields["COUNTY"]
                name = unit_name(re.sub(r"^Precinct\s+", "", fields["UNIT_NAME"], flags=re.I))
                if (parish not in parishes or fields["GLEVEL"] != "V" or not name
                        or any(fields[k] != fields["COUNTY"] for k in ("COUNTYFP10", "COUNTYFP20") if k in fields)
                        or any(fields[k] != "22" for k in ("STATEFP10", "STATEFP20") if k in fields)):
                    raise ValueError("Unexpected Louisiana legislative shape identity")
                try:
                    geometry = transform(shape(item.shape.__geo_interface__), project, interleaved=False)
                    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                        geometry = None
                except (TypeError, ValueError):
                    geometry = None
                groups[parish][name].append(geometry)
    return groups


def _preview(label, features, parish_features):
    from pyproj import Transformer
    from shapely import transform
    from shapely.geometry import shape

    projection = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform
    def projected(feature):
        return transform(shape(feature["geometry"]), projection, interleaved=False)

    parishes = [projected(feature) for feature in parish_features]
    west = min(g.bounds[0] for g in parishes)
    north = max(g.bounds[3] for g in parishes)
    span_x = max(g.bounds[2] for g in parishes) - west
    span_y = north - min(g.bounds[1] for g in parishes)
    scale = min(730 / span_x, 520 / span_y)

    def path(g):
        result = []
        for polygon in g.geoms if g.geom_type == "MultiPolygon" else [g]:
            for ring in [polygon.exterior, *polygon.interiors]:
                result.append("M" + "L".join(
                    f"{25 + (x-west)*scale:.1f} {55 + (north-y)*scale:.1f}"
                    for x, y in ring.coords[:-1]) + "Z")
        return "".join(result)

    colors = ("#ffffff", "#d9e8ed", "#b3d2dc", "#79afbf", "#24586d")
    labels = ("0", "1–99", "100–499", "500–999", "1,000+")
    scope = "Legislative reference only — not election-day precinct geometry"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 625" role="img" aria-labelledby="title description">',
           f'<title id="title">{escape(label)}</title><desc id="description">{scope}. '
           'Gray denotes no mapped count. Exact values are in the accompanying CSV.</desc>',
           '<rect width="780" height="625" fill="#ffffff"/>',
           f'<text x="25" y="24" font-size="18" font-family="system-ui">{escape(label)}</text>',
           f'<text x="25" y="43" font-size="13" font-family="system-ui">{scope}</text>']
    for g in parishes:
        out.append(f'<path d="{path(g)}" fill="#ebedf0" stroke="#aab4bb" stroke-width=".55" fill-rule="evenodd"/>')
    for feature in features:
        p = feature["properties"]
        count = p["voters_voting"]
        color = colors[0 if count == 0 else 1 if count < 100 else 2 if count < 500 else 3 if count < 1000 else 4]
        title = escape(f'{p["native_precinct_id"]}: {count:,} reported voters')
        out.append(f'<path d="{path(projected(feature))}" fill="{color}" stroke="#59727b" stroke-width=".3" '
                   f'fill-rule="evenodd"><title>{title}</title></path>')
    for i, (color, caption) in enumerate(zip(colors + ("#ebedf0",), labels + ("Not mapped",), strict=True)):
        x = 25 + i * 120
        out.append(f'<rect x="{x}" y="596" width="13" height="13" fill="{color}" stroke="#59727b"/>'
                   f'<text x="{x+19}" y="607" font-size="12" font-family="system-ui">{caption}</text>')
    out.append("</svg>")
    return ("\n".join(out) + "\n").encode()


def build(archive_dir, counts_body, parish_body, output):
    from shapely import coverage_is_valid
    from shapely.geometry import mapping

    parishes = _parishes(parish_body)
    parish_features = json.loads(gzip.decompress(parish_body))["features"]
    inventory = json.loads((archive_dir / "inventory.json").read_bytes())
    counts = _counts(counts_body, parishes, {int(label[:4]) for label, item in inventory.items() if "name" in item})
    output.mkdir(parents=True, exist_ok=True)
    summary, parish_checks, unit_checks = {}, [], []
    for label, item in sorted(inventory.items()):
        if "name" not in item:
            continue
        if Path(item["name"]).name != item["name"] or not item["url"].startswith("https://redist.legis.la.gov/"):
            raise ValueError("Unregistered Louisiana legislative reference source")
        body = (archive_dir / item["name"]).read_bytes()
        if len(body) != item["bytes"] or digest(body) != item["sha256"]:
            raise ValueError("Louisiana legislative archive differs from its pin")
        counts_year = counts[int(label[:4])]
        shapes = _geometry(body, counts_year)
        if set(shapes) != set(counts_year):
            raise ValueError("Incomplete legislative reference parish inventory")
        features, matched_parishes = [], 0
        for parish, local in sorted(counts_year.items()):
            units = shapes[parish]
            one_to_one = {key for key, claims in local.items() if len(claims) == len(units.get(key, ())) == 1}
            status = "roster_differs"
            if one_to_one == set(local) == set(units):
                geometries = [units[key][0] for key in sorted(units)]
                if any(row["control_status"] != "parish_and_statewide_counts_agree"
                       for claims in local.values() for row in claims):
                    status = "parish_count_control_differs"
                elif any(g is None for g in geometries):
                    status = "invalid_reference_shape"
                elif not coverage_is_valid(geometries):
                    status = "reference_coverage_topology_differs"
                else:
                    status = "legislative_reference_only"
                    matched_parishes += 1
            shared = {
                "election_date": next(iter(local.values()))[0]["election_date"],
                "reference_edition": label, "reference_sha256": item["sha256"],
                "reference_url": item["url"], "parish_fips": parish, "reference_status": status,
                "election_day_geometry_qualified": False,
            }
            parish_checks.append({**shared, "native_records": sum(map(len, local.values())),
                                  "reference_shapes": sum(map(len, units.values())), "one_to_one": len(one_to_one),
                                  "count_only_names": "|".join(sorted(local.keys() - units.keys())),
                                  "shape_only_names": "|".join(sorted(units.keys() - local.keys()))})
            for key, claims in sorted(local.items()):
                for row in claims:
                    fields = {**shared, "native_precinct_id": row["native_precinct_id"], "normalized_name": key,
                              "voters_voting": int(row["voters_voting"]), "count_source_sha256": row["source_sha256"],
                              "vote_allocation_performed": False, "rate_qualified": False,
                              "count_control_status": row["control_status"], "reference_candidates": len(units.get(key, ()))}
                    unit_checks.append(fields)
                    if status == "legislative_reference_only":
                        features.append({"type": "Feature", "geometry": mapping(units[key][0]), "properties": fields})
        stem = re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-")
        name, preview_name = stem + ".geojson.gz", stem + ".svg"
        collection = {"type": "FeatureCollection", "reference_scope": "legislative_reference_only",
                      "features": features}
        encoded = gzip.compress(json.dumps(collection, separators=(",", ":"), allow_nan=False).encode(), mtime=0)
        (output / name).write_bytes(encoded)
        preview = _preview(label, features, parish_features)
        (output / preview_name).write_bytes(preview)
        summary[label] = {"file": name, "bytes": len(encoded), "sha256": digest(encoded),
                          "preview": preview_name, "preview_sha256": digest(preview),
                          "reference_parishes": matched_parishes, "reference_precincts": len(features),
                          "election_day_qualified": 0}
    write_rows(output / "parish-reference-decisions.csv", parish_checks)
    write_rows(output / "precinct-reference-decisions.csv", unit_checks)
    (output / "layers.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    links = "\n".join(f'<li><a href="{row["preview"]}">{escape(label)}</a> · {row["reference_precincts"]:,} reference precincts'
                      f' · <a href="{row["file"]}">GeoJSON (gzip)</a></li>' for label, row in summary.items())
    (output / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Louisiana historical precinct reference maps</title><main>'
        '<h1>Louisiana historical precinct reference maps</h1>'
        '<p>These are counts of people recorded as voting, not physical ballots or turnout rates. '
        'The legislative boundaries are references, not verified election-day precincts. Only complete unique parish '
        'rosters with valid reference geometry appear. Gray indicates no mapped count, not zero.</p>'
        f'<ul>{links}</ul><p><a href="precinct-reference-decisions.csv">Complete count table and decisions</a> · '
        '<a href="parish-reference-decisions.csv">Parish roster checks</a></p></main>', encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive_dir", "counts_csv", "parish_reference", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.archive_dir, args.counts_csv.read_bytes(),
                           args.parish_reference.read_bytes(), args.output), indent=2))
