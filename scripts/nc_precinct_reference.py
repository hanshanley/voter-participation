"""Reproduce historical North Carolina count-only precinct reference maps."""

import argparse
import csv
import gzip
from hashlib import sha256
from html import escape
from io import BytesIO, StringIO
import json
from pathlib import Path
from zipfile import ZipFile

import shapefile
from shapely.geometry import shape
from shapely.strtree import STRtree

COUNTS = "0fe081642b3266c20d1813e2b225700f97cb4be08a2f34feca8090262179efc5"
ARCHIVES = {
    "20120901": "9f7da99d4fcb1503a46efa4a97a0e1c8c109f8904dad6959425321c1afdaac6e",
    "20141016": "53ddb20c47b2b382b05d5eec5e1dcb733a022d20efdee727253de6d7cf1ac44e",
    "20161004": "4739d58fe4681ec93d37771073b4b7c661bedc36180e57cd48f3f245972aeb63",
    "20170519": "f61cc84c9d69757dd74e5b1ae3c269a322267e8f739ec3399f4250412013962b",
    "20190507": "691f1bf6e3f3cb784f54463fcb72130eac39174e4e0d56b7c8712d5018986879",
    "20190827": "76de0fe26651529b6b34963864c9f25a24964b803636f2970ed7251c6fe2aeed",
    "20201018": "a31a68aab8761ce579ad853690eeef2845dccf8655d9638237ef3845e2405f5b",
    "20220831": "100e3171a14e0d8f6b5a827e8102101ff80abc554e24d7dd3be321fd204f982e",
    "20240723": "bd9d37ac1f59ca77c55ce94cb3fe10c7c42cf7fc00f4dece7c841afe2cfb03b9",
}
RESTORED = {("BUNCOMBE", "681"), ("HENDERSON", "CV"), ("WAKE", "01-07A"), ("WAKE", "07-07A")}
EDITIONS = {"2012-11-06": "20120901", "2014-11-04": "20141016",
            "2016-11-08": "20161004", "2018-11-06": "20170519", "2020-11-03": "20201018",
            "2022-11-08": "20220831", "2024-11-05": "20240723"}
CLOSED_ROSTERS = {"20120901", "20141016", "20220831", "20240723"}
BRACKETS = {"20170519": "20190507"}
COLORS = ("#d9e8ed", "#b3d2dc", "#79afbf", "#48879d", "#24586d")


def load(path, digest):
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError(f"{path.name} differs from its reviewed source")
    return body


def outline(path, edition, keys=None):
    with ZipFile(BytesIO(load(path, ARCHIVES[edition]))) as archive:
        def part(extension):
            names = [name for name in archive.namelist() if name.endswith(extension)]
            (name,) = names
            return BytesIO(archive.read(name))

        with shapefile.Reader(shp=part(".shp"), shx=part(".shx"), dbf=part(".dbf"),
                              encoding="latin1") as source:
            results = {}
            for record in source.iterShapeRecords():
                field = {k.lower(): v for k, v in record.record.as_dict().items()}
                key = field["county_nam"], field["prec_id"]
                if keys is not None and key not in keys:
                    continue
                if key in results:
                    raise ValueError(f"Duplicate reference precinct: {key}")
                results[key] = shape(record.shape.__geo_interface__)
    return results


def topology(geometries):
    keys, values = zip(*sorted(geometries.items()))
    tree = STRtree(values)
    held = {}
    for i, geometry in enumerate(values):
        for j in tree.query(geometry, predicate="intersects"):
            if j <= i:
                continue
            area = geometry.intersection(values[j]).area
            if area > 1:
                held.setdefault(keys[i], []).append((*keys[j], round(area, 3)))
                held.setdefault(keys[j], []).append((*keys[i], round(area, 3)))
    return {key: sorted(rows) for key, rows in held.items()}


def audit(counts, primary, supplement, *, closed_roster=False, after=None):
    if set(supplement) != (set(counts) - set(primary) if supplement else set()):
        raise ValueError("Supplement does not enumerate exactly the missing count-bearing keys")
    shapes = primary | supplement
    valid = {key: g for key, g in shapes.items()
             if g.geom_type in ("Polygon", "MultiPolygon") and g.is_valid and not g.is_empty}
    overlaps = topology(valid)
    held_counties = ({county.upper() for county, code in set(counts) ^ set(shapes) if code.strip()}
                     if closed_roster else set())
    if after is not None and counts.keys() != primary.keys():
        raise ValueError("The pre-election roster does not match the credit archive")
    unstable = ({key for key, geometry in valid.items()
                 if key not in after or not after[key].is_valid
                 or not geometry.equals_exact(after[key], 0, normalize=True)} if after is not None else set())
    records, accepted = [], {}
    for key in sorted(set(counts) | set(shapes)):
        if key not in counts:
            status = "geometry_only"
        elif key not in shapes:
            status = "no_shape"
        elif key not in valid:
            status = "invalid_geometry"
        elif key in overlaps:
            status = "overlapping_geometry"
        elif key in unstable:
            status = "bracketing_geometry_differs_or_missing"
        elif key[0].upper() in held_counties:
            status = "county_roster_differs"
        else:
            status = "reference_count_only"
            accepted[key] = valid[key]
        records.append([*key, counts.get(key), "supplement" if key in supplement else "primary" if key in shapes else "",
                        status, json.dumps(overlaps.get(key, []), separators=(",", ":"))])
    return records, accepted


def display_paths(shapes):
    bounds = [g.bounds for g in shapes.values()]
    x0, y0 = (min(b[i] for b in bounds) for i in (0, 1))
    x1, y1 = (max(b[i] for b in bounds) for i in (2, 3))
    scale = min(920 / (x1 - x0), 318 / (y1 - y0))
    dx, dy = (960 - scale * (x1 - x0)) / 2, (318 - scale * (y1 - y0)) / 2 + 57
    for key, geometry in sorted(shapes.items()):
        paths = []
        polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]
        for polygon in polygons:
            for ring in [polygon.exterior, *polygon.interiors]:
                points = [f"{dx+(x-x0)*scale:.1f},{dy+(y1-y)*scale:.1f}" for x, y in ring.coords]
                paths.append(f"M{'L'.join(points)}Z")
        yield key, "".join(paths)


def svg(election, edition, counts, shapes, paths=None):
    total = sum(counts.values())
    covered = sum(counts[k] for k in shapes)
    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 445" role="img" aria-labelledby="title description">',
        f'<title id="title">North Carolina voter-history credits, {election}</title>',
        f'<desc id="description">{len(shapes):,} of {len(counts):,} units shown; {covered:,} of {total:,} credits.</desc>',
        '<rect width="960" height="445" fill="white"/>',
        f'<text x="20" y="26" font-size="21">North Carolina voter-history credits · {election[:4]}</text>',
        f'<text x="20" y="48" font-size="13">Dated reference ({edition}); {len(shapes):,} of {len(counts):,} units shown. Not turnout rates.</text>',
    ]
    for key, path in paths if paths is not None else display_paths(shapes):
        n = counts[key]
        color = COLORS[sum(n >= threshold for threshold in (500, 1000, 2000, 3500))]
        title = f"{key[0]} · {key[1]}: {n:,} voter-history credits"
        rows.append(f'<path d="{path}" fill="{color}" fill-rule="evenodd" '
                    f'stroke="#596875" stroke-width=".08"><title>{escape(title)}</title></path>')
    for i, label in enumerate(("Under 500", "500–999", "1,000–1,999", "2,000–3,499", "3,500 or more")):
        x = 20 + i * 176
        rows.append(f'<rect x="{x}" y="389" width="17" height="12" fill="{COLORS[i]}"/>'
                    f'<text x="{x+22}" y="400" font-size="12">{label}</text>')
    rows += [f'<text x="20" y="427" font-size="12">White gaps are not zero. {total-covered:,} credits held off the map. '
             'Use the accompanying CSV for decisions and counts.</text>', "</svg>"]
    return "\n".join(rows) + "\n"


def build(inputs, output, *, display_layers=False):
    body = load(inputs / "participation-nc-general-native-precincts.csv.gz", COUNTS)
    raw = list(csv.DictReader(StringIO(gzip.decompress(body).decode())))
    output.mkdir(parents=True, exist_ok=True)
    summary = {}
    for election, edition in EDITIONS.items():
        counts = {}
        for row in raw:
            if row["election_date"] == election and row["voters_with_history"]:
                key = row["native_county"], row["native_precinct_code"]
                if key in counts:
                    raise ValueError("Duplicate count-bearing precinct")
                counts[key] = int(row["voters_with_history"])
        primary = outline(inputs / f"precinct-{edition}.zip", edition)
        supplement = (outline(inputs / "precinct-20190827.zip", "20190827", RESTORED)
                      if edition == "20201018" else {})
        comparison = BRACKETS.get(edition)
        after = outline(inputs / f"precinct-{comparison}.zip", comparison) if comparison else None
        records, accepted = audit(counts, primary, supplement, closed_roster=edition in CLOSED_ROSTERS, after=after)
        if comparison:
            records.extend([*key, None, "later_reference", "geometry_only", "[]"]
                           for key in sorted(after.keys() - primary.keys()))
        with (output / (election + "-precinct-decisions.csv")).open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(["native_county", "native_precinct", "voter_history_credits",
                             "reference_part", "status", "overlap_partners_and_square_feet"])
            writer.writerows(records)
        edition_label = f"{edition} and {comparison}" if comparison else edition
        paths = list(display_paths(accepted))
        (output / (election + "-precinct-reference.svg")).write_text(
            svg(election, edition_label, counts, accepted, paths), encoding="utf-8")
        if display_layers:
            layer = {"contract": "participation.nc_precinct_reference.v1", "election": election,
                     "edition": edition_label, "roster": sorted(counts),
                     "paths": [[*key, path] for key, path in paths]}
            (output / (election + "-precinct-reference.json.gz")).write_bytes(
                gzip.compress(json.dumps(layer, separators=(",", ":"), ensure_ascii=True).encode(),
                              compresslevel=9, mtime=0))
        summary[election] = {"reference_edition": edition, "count_records": len(counts),
                             "shown": len(accepted), "credits": sum(counts.values()),
                             "shown_credits": sum(counts[k] for k in accepted),
                             "not_election_effective_boundaries_or_rates": True}
        if comparison:
            summary[election]["comparison_edition"] = comparison
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--display-layers", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.inputs, args.output, display_layers=args.display_layers), indent=2))
