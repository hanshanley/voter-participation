"""Build a labeled count preview from a reviewed Virginia precinct reference layer."""

import argparse
import csv
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from shapely import coverage_is_valid, transform
from shapely.geometry import shape
from pyproj import Transformer


LOCALITY = "SUFFOLK CITY"
DATE = "2022-11-08"
SOURCE = "https://suffolkgis.suffolk-va.net/hosting/rest/services/Public_Website/Voting_Information/MapServer/42"
QUERY = SOURCE + "/query?" + urlencode({
    "where": "1=1", "outFields": "Precinct_Number,Precinct_Name", "returnGeometry": "true",
    "outSR": "4326", "f": "geojson",
})
SOURCE_SHA256 = "713e74f1d9ada76fbb96280683fed602fa330d19bbe4a836fe685af50e396604"
COLORS = ("#f0f3f5", "#c5e1e3", "#84bdc4", "#428a9d", "#24596e")
LABELS = ("No match", "0-499", "500-999", "1,000-1,499", "1,500+")


def name_key(text):
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def join(rows, features, locality, id_field, name_field):
    physical = {}
    central = control = 0
    for row in rows:
        if row["locality"] != locality:
            continue
        if row["election_date"] != DATE:
            raise ValueError("Reference map can only use the reviewed election")
        n = int(row["ballots"])
        if n < 0:
            raise ValueError("Ballot count is negative")
        anchor = int(row["locality_ballots_control"])
        if control and anchor != control:
            raise ValueError("Mixed locality controls")
        control = anchor
        if row["unit_kind"] == "central_reporting_unit" and not row["precinct_code"]:
            central += n
            continue
        code = row["precinct_code"]
        if (row["unit_kind"], row["ballot_component"]) != ("physical_precinct", "election_day") or not re.fullmatch(r"\d{3}", code):
            raise ValueError("Expected Election Day physical precinct units")
        key = name_key(row["reporting_unit"][3:])
        if not key or key in physical or any(p[0] == code for p in physical.values()):
            raise ValueError("Ambiguous native precinct identity")
        physical[key] = (code, row["reporting_unit"], n)
    if not physical or sum(p[2] for p in physical.values()) + central != control:
        raise ValueError("Locality controls do not reconcile")
    seen, keys, decisions, joined = set(), set(), [], []
    for feature in features:
        p = feature["properties"]
        ident, name = p[id_field], p[name_field]
        key = name_key(name)
        if not ident or not key or ident in seen or key in keys:
            raise ValueError("Ambiguous geometry precinct identity")
        seen.add(ident)
        keys.add(key)
        code, native, count = physical.get(key, ("", "", None))
        record = {"geometry_id": ident, "geometry_name": name, "precinct_code": code,
                  "reporting_unit": native, "election_day_ballots": count,
                  "decision": "matched_reference_name" if code else "geometry_only"}
        joined.append((shape(feature["geometry"]), record))
        decisions.append(record)
    if not joined or any(g.is_empty or not g.is_valid or g.geom_type not in ("Polygon", "MultiPolygon")
                         for g, _ in joined) or not coverage_is_valid([g for g, _ in joined]):
        raise ValueError("Invalid or overlapping reference polygons")
    for key in sorted(physical.keys() - keys):
        code, native, count = physical[key]
        decisions.append({"geometry_id": "", "geometry_name": "", "precinct_code": code, "reporting_unit": native,
                          "election_day_ballots": count, "decision": "count_only"})
    return joined, decisions, central, control


def preview(joined, central, control):
    projection = Transformer.from_crs(4326, 5070, always_xy=True).transform
    projected = [(transform(g, projection, interleaved=False), row) for g, row in joined]
    west = min(g.bounds[0] for g, _ in projected)
    north = max(g.bounds[3] for g, _ in projected)
    height = north - min(g.bounds[1] for g, _ in projected)
    width = max(g.bounds[2] for g, _ in projected) - west
    scale = min(660 / width, 480 / height)

    def path(geom):
        return "".join("M" + "L".join(f"{28 + (x-west)*scale:.2f} {96 + (north-y)*scale:.2f}"
                                    for x, y in ring.coords[:-1]) + "Z"
                       for poly in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom])
                       for ring in [poly.exterior, *poly.interiors])

    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 648" role="img" aria-labelledby="title summary">',
           '<title id="title">Suffolk, Virginia: Election Day ballots by precinct</title>',
           '<desc id="summary">November 8, 2022. Reference boundaries; gray means no verified match. '
           'Central voting units are not placed on the map. Read exact counts in the accompanying table.</desc>',
           '<rect width="720" height="648" fill="white"/>',
           '<g font-family="system-ui,sans-serif" fill="#172b34">',
           '<text x="28" y="34" font-size="21">Suffolk, Virginia: Election Day ballots by precinct</text>',
           '<text x="28" y="57" font-size="14">November 8, 2022 | City GIS reference boundaries</text>',
           f'<text x="28" y="77" font-size="13">{central:,} central ballots are not mapped ({control:,} total).</text>']
    for g, row in projected:
        count = row["election_day_ballots"]
        color = COLORS[0 if count is None else 1 + min(count // 500, 3)]
        label = "not matched" if count is None else f"{count:,} ballots"
        out.append(f'<path d="{path(g)}" fill="{color}" stroke="#4d6870" stroke-width=".45" fill-rule="evenodd">'
                   f'<title>{escape(row["geometry_name"])}: {label}</title></path>')
    for i, (color, label) in enumerate(zip(COLORS, LABELS, strict=True)):
        x = 28 + i * 124
        out.append(f'<rect x="{x}" y="589" width="13" height="13" fill="{color}" stroke="#4d6870"/>'
                   f'<text x="{x+19}" y="601" font-size="13">{label}</text>')
    out.append('<text x="28" y="631" font-size="12">Ballots: Virginia Department of Elections  |  Boundaries: City of Suffolk GIS</text>')
    return "\n".join([*out, "</g></svg>", ""])


def build(counts, geometry, output):
    body = geometry.read_bytes()
    if sha256(body).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unreviewed Suffolk geometry edition")
    with counts.open(newline="") as stream:
        joined, decisions, central, control = join(csv.DictReader(stream), json.loads(body)["features"],
                                                   LOCALITY, "Precinct_Number", "Precinct_Name")
    if len(joined) != 30 or sum(row["decision"] == "matched_reference_name" for row in decisions) != 29:
        raise ValueError("Suffolk reference map roster changed")
    output.mkdir()
    (output / "suffolk-2022-election-day.svg").write_text(preview(joined, central, control), encoding="utf-8")
    with (output / "suffolk-2022-join.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=decisions[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(decisions)
    (output / "sources.json").write_text(json.dumps({
        "election_date": DATE, "source": SOURCE, "source_query": QUERY, "source_sha256": SOURCE_SHA256,
        "counts_sha256": sha256(counts.read_bytes()).hexdigest(), "central_ballots_unmapped": central,
        "locality_ballots": control, "scope": "reference_geometry_only",
    }, indent=2) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("counts", type=Path)
    cli.add_argument("geometry", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    build(args.counts, args.geometry, args.output)
