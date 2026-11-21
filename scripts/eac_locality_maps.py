"""Reproduce the 2024 Maine and Vermont EAC locality reference maps."""

import argparse
import csv
import gzip
from hashlib import sha256
from html import escape
from io import BytesIO, StringIO
from pathlib import Path
import re
from zipfile import ZipFile

from pyproj import Transformer
import shapefile
from shapely import transform
from shapely.geometry import shape

from scripts.nc_precinct_reference import display_paths, topology


REFERENCES = {
    "ME": ("Maine", "23", "74e835f154e6832709d69e1f20a020b1cd4ee804c64073ba61f4c6007bb50daa"),
    "VT": ("Vermont", "50", "5c832fef2382399b04a2f26a5d308b6da4181f7795b650b15d2354058aac1671"),
}
COLORS = ("#e4eef0", "#c5dde1", "#8cbac4", "#55939f", "#306f80", "#17475c")


def county_subdivisions(body, state):
    _, fips, expected = REFERENCES[state]
    if sha256(body).hexdigest() != expected:
        raise ValueError("Unexpected Census subdivision edition")
    project = Transformer.from_crs(4269, 5070, always_xy=True).transform
    with ZipFile(BytesIO(body)) as archive:
        stem, = (name[:-4] for name in archive.namelist() if name.endswith(".shp"))
        with shapefile.Reader(**{ext: BytesIO(archive.read(f"{stem}.{ext}"))
                                for ext in ("dbf", "shx", "shp")}) as layer:
            result = {}
            for record in layer.iterShapeRecords():
                fields = record.record.as_dict()
                key = fields["GEOID"]
                if key != fields["STATEFP"] + fields["COUNTYFP"] + fields["COUSUBFP"] \
                        or not re.fullmatch(fips + r"\d{8}", key) or key in result:
                    raise ValueError("Incompatible Census subdivision identity")
                geometry = shape(record.shape.__geo_interface__)
                if not geometry.is_empty and geometry.is_valid:
                    geometry = transform(geometry, project, interleaved=False)
                result[key] = (fields["NAME"], fields["NAMELSAD"], geometry)
            return result


def name_key(name):
    value = name.upper().replace("’", "'")
    value = re.sub(r"\bST\.?\s+", "SAINT ", value)
    value = re.sub(r"\s+(?:PLT|PLANTATION)$", " PLANTATION", value)
    return re.sub(r"[^A-Z0-9]", "", value)


def bind(state, rows, boundaries):
    shapes = {(state, key): geometry for key, (_, _, geometry) in boundaries.items()
              if geometry.geom_type in {"Polygon", "MultiPolygon"} and geometry.is_valid and not geometry.is_empty}
    overlaps = topology(shapes) if shapes else {}
    decisions, matched = [], {}
    for row in rows:
        key = row["native_fips"]
        native_name, census_names = row["native_name"], boundaries.get(key, ("", "", None))[:2]
        if not row["reported_counted_ballot_participants"]:
            decision = "count_withheld"
        elif key not in boundaries:
            decision = "no_same_year_subdivision_code"
        elif name_key(native_name) not in {name_key(n) for n in census_names}:
            decision = "name_disagrees_with_subdivision_code"
        elif (state, key) not in shapes:
            decision = "invalid_geometry"
        elif (state, key) in overlaps:
            decision = "overlapping_geometry"
        else:
            decision = "matched_reference"
            if key in matched:
                raise ValueError("Multiple accepted records match one subdivision")
            matched[key] = row
        decisions.append({**row, "census_name": census_names[1], "reference_map_decision": decision})
    observed = {row["native_fips"] for row in rows}
    for key in sorted(boundaries.keys() - observed):
        decisions.append({"state_code": state, "year": "2024", "native_fips": key,
                          "census_name": boundaries[key][1],
                          "reference_map_decision": "geometry_only" if (state, key) in shapes
                          else "invalid_geometry_without_record"})
    return decisions, matched, shapes


def draw(state, matched, shapes, rate):
    name = REFERENCES[state][0]
    field = "same_report_registration_fraction_pct" if rate else "reported_counted_ballot_participants"
    measure = "Percent of same-report registrations" if rate else "Counted-ballot participants"
    cuts = (40, 50, 60, 70, 80) if rate else (100, 500, 1000, 2500, 10000)
    labels = ("Under 40%", "40–49%", "50–59%", "60–69%", "70–79%", "80% or more") if rate else (
        "Under 100", "100–499", "500–999", "1,000–2,499", "2,500–9,999", "10,000 or more")
    available = sum(bool(row[field]) for row in matched.values())
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 446" role="img" aria-labelledby="title description">',
        f'<title id="title">{name} reported participation, November 2024</title>',
        f'<desc id="description">{measure}. {available} reporting units are shaded. Gray is not zero.</desc>',
        '<rect width="960" height="446" fill="white"/>',
        f'<text x="20" y="27" font-size="21">{name} local participation · November 2024</text>',
        f'<text x="20" y="49" font-size="13">{measure} · {available} shaded · 2024 Census reference</text>',
    ]
    for (_, key), path in display_paths(shapes):
        row = matched.get(key)
        value = row[field] if row else ""
        if value:
            number = float(value) if rate else int(value)
            fill = COLORS[sum(number >= cut for cut in cuts)]
            label = f"{number:.2f}%" if rate else f"{number:,}"
        else:
            fill, label = "#e7e8eb", "no verified mapped value"
        title = f"{row['native_name'] if row else key}: {label}"
        lines.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd" stroke="#69808d" '
                     f'stroke-width=".18"><title>{escape(title)}</title></path>')
    for i, label in enumerate(labels):
        x = 20 + i * 154
        lines.append(f'<rect x="{x}" y="391" width="17" height="12" fill="{COLORS[i]}"/>'
                     f'<text x="{x+22}" y="402" font-size="13">{label}</text>')
    lines.append('<text x="20" y="429" font-size="13">Gray means no verified mapped value, not zero. '
                 'See the decision CSV for unmapped records.</text></svg>')
    return "\n".join(lines) + "\n"


def build(inputs, output):
    csv_body = gzip.decompress((inputs / "participation-eac-locality-history.csv.gz").read_bytes()).decode()
    rows = list(csv.DictReader(StringIO(csv_body)))
    output.mkdir(parents=True, exist_ok=True)
    for state in REFERENCES:
        native = [row for row in rows if row["state_code"] == state and row["year"] == "2024"]
        boundaries = county_subdivisions((inputs / f"{state}-2024-cousub.zip").read_bytes(), state)
        decisions, matched, shapes = bind(state, native, boundaries)
        fields = sorted({key for row in decisions for key in row})
        with (output / f"{state}-2024-decisions.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(decisions)
        for rate in (False, True):
            suffix = "rate" if rate else "count"
            (output / f"{state}-2024-{suffix}.svg").write_text(draw(state, matched, shapes, rate), encoding="utf-8")
        print(state, len(matched), len(native), len(shapes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.inputs, args.output)
