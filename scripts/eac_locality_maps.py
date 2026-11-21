"""Reproduce EAC locality maps on election-year Census reference boundaries."""

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


STATES = {
    "MA": ("Massachusetts", "25"), "ME": ("Maine", "23"),
    "NH": ("New Hampshire", "33"), "VT": ("Vermont", "50"),
}
REFERENCES = {
    ("ME", 2008): "8ab52b9be6c2ff561e1cbdb181a58fa0fd2ca689a1e5841adcecc74e168ec84a",
    ("MA", 2010): "8b8fe344b6b402cd7bec3102419228bea0ca7c3644dab365dc683a1917b4228b",
    ("ME", 2010): "594a6ddfcaf102479ba8847ee67510f14251755bf570a4546e8dc64bf3ba6ebf",
    ("VT", 2010): "82307b3eb0cc9f165ed921558428ab4fa563f6a3e9598689aeca0a1e37b90dc1",
    ("ME", 2012): "e483faa48374d797b37161d2f0acd8b717e0939b809c6cea5004da443efb515a",
    ("VT", 2012): "abb844b2a58efbfc3e5df7d22bb067d955d7cc97b22156d23287446fa69d372f",
    ("MA", 2018): "ea29c74bdfc053f5a7f33be05367ab7090ca67b9bb8fdbfad2351855d442e618",
    ("ME", 2018): "6f45ea5425d1c2a96fbd0cfe234689d82b988b583255b0d449745e21d4b6d648",
    ("NH", 2018): "b201e0f3820c4dab71285f51344b35a13a698827e1bdb96f8e21f9b556e748a8",
    ("VT", 2018): "365d7e2ad766012928fb9fd26931415748de333457114121f278481ccba49c0e",
    ("MA", 2020): "80d17a1f28862e50bbbc29b5475937bb1d4a9106f627453f80adbf204a74ccfd",
    ("ME", 2020): "209be6f89629e4b10e5e677cb1418a277ca1577c443c07df090cf0efcd34732f",
    ("NH", 2020): "7aaa81a1c7d2f0bdf187f007a4c27755e83825c4de49744d034822d0ae7b818b",
    ("VT", 2020): "08864ceeedc2bf40fb10f9409cd42ee4603f65c7d1ca140dd0a97ac5b5fb71da",
    ("ME", 2022): "04488c1b5d55ba1d183e73293a69559577481f74530049040cd013278b6f4d07",
    ("NH", 2022): "fe041e6f7a30ae367a2b43a8f483cc09ce868b37c8934178bea9ca2fccb17167",
    ("VT", 2022): "07ace4d8c2611775e9dc2bf472731f3de942fd60787121c12bf43eab2b478056",
    ("ME", 2024): "74e835f154e6832709d69e1f20a020b1cd4ee804c64073ba61f4c6007bb50daa",
    ("VT", 2024): "5c832fef2382399b04a2f26a5d308b6da4181f7795b650b15d2354058aac1671",
}
LEGACY_SUFFIX = {"25": " city", "31": " gore", "39": " plantation", "43": " town", "46": " UT"}
COLORS = ("#e4eef0", "#c5dde1", "#8cbac4", "#55939f", "#306f80", "#17475c")


def county_subdivisions(body, state, year):
    _, fips = STATES[state]
    expected = REFERENCES[state, year]
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
                if year == 2010:
                    fields = {k.removesuffix("10"): value for k, value in fields.items()}
                key = fields["COSBIDFP" if year == 2008 else "GEOID"]
                if key != fields["STATEFP"] + fields["COUNTYFP"] + fields["COUSUBFP"] \
                        or not re.fullmatch(fips + r"\d{8}", key) or key in result:
                    raise ValueError("Incompatible Census subdivision identity")
                geometry = shape(record.shape.__geo_interface__)
                if not geometry.is_empty and geometry.is_valid:
                    geometry = transform(geometry, project, interleaved=False)
                name = fields["NAME"]
                label = (name + LEGACY_SUFFIX.get(fields["LSAD"], "") if year == 2018 else fields["NAMELSAD"])
                result[key] = (name, label, geometry)
            return result


def name_key(name):
    value = name.upper().replace("’", "'")
    value = re.sub(r"\bST\.?\s+", "SAINT ", value)
    value = re.sub(r"\s+(?:PLT|PLANTATION)$", " PLANTATION", value)
    return re.sub(r"[^A-Z0-9]", "", value)


def bind(state, rows, boundaries, *, year=2024):
    shapes = {(state, key): geometry for key, (_, _, geometry) in boundaries.items()
              if geometry.geom_type in {"Polygon", "MultiPolygon"} and geometry.is_valid and not geometry.is_empty}
    overlaps = topology(shapes) if shapes else {}
    decisions, matched = [], {}
    for row in rows:
        key = row["native_fips"]
        native_name, census_names = row["native_name"], boundaries.get(key, ("", "", None))[:2]
        # NH marks undivided localities with a ward code of 00. Never strip a real ward number.
        compare_name = re.sub(r" 00$", "", native_name) if state == "NH" else native_name
        if not row["reported_counted_ballot_participants"]:
            decision = "count_withheld"
        elif key not in boundaries:
            decision = "no_same_year_subdivision_code"
        elif name_key(compare_name) not in {name_key(n) for n in census_names}:
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
        decisions.append({"state_code": state, "year": str(year), "native_fips": key,
                          "census_name": boundaries[key][1],
                          "reference_map_decision": "geometry_only" if (state, key) in shapes
                          else "invalid_geometry_without_record"})
    return decisions, matched, shapes


def draw(state, matched, shapes, rate, *, year=2024):
    name = STATES[state][0]
    field = "same_report_registration_fraction_pct" if rate else "reported_counted_ballot_participants"
    measure = "Percent of same-report registrations" if rate else "Counted-ballot participants"
    cuts = (40, 50, 60, 70, 80) if rate else (100, 500, 1000, 2500, 10000)
    labels = ("Under 40%", "40–49%", "50–59%", "60–69%", "70–79%", "80% or more") if rate else (
        "Under 100", "100–499", "500–999", "1,000–2,499", "2,500–9,999", "10,000 or more")
    available = sum(bool(row[field]) for row in matched.values())
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 446" role="img" aria-labelledby="title description">',
        f'<title id="title">{name} reported participation, November {year}</title>',
        f'<desc id="description">{measure}. {available} reporting units are shaded. Gray is not zero.</desc>',
        '<rect width="960" height="446" fill="white"/>',
        f'<text x="20" y="27" font-size="21">{name} local participation · November {year}</text>',
        f'<text x="20" y="49" font-size="13">{measure} · {available} shaded · {year} Census reference</text>',
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


def build(inputs, output, *, years=(2024,)):
    csv_body = gzip.decompress((inputs / "participation-eac-locality-history.csv.gz").read_bytes()).decode()
    rows = list(csv.DictReader(StringIO(csv_body)))
    output.mkdir(parents=True, exist_ok=True)
    for state, year in REFERENCES:
        if year not in years:
            continue
        prefix = f"{state}-{year}"
        native = [row for row in rows if row["state_code"] == state and row["year"] == str(year)]
        boundaries = county_subdivisions((inputs / f"{prefix}-cousub.zip").read_bytes(), state, year)
        decisions, matched, shapes = bind(state, native, boundaries, year=year)
        if not matched:
            raise ValueError(f"No qualified source records joined the {prefix} boundaries")
        fields = sorted({key for row in decisions for key in row})
        with (output / f"{prefix}-decisions.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(decisions)
        for rate in (False, True):
            suffix = "rate" if rate else "count"
            (output / f"{prefix}-{suffix}.svg").write_text(
                draw(state, matched, shapes, rate, year=year), encoding="utf-8")
        print(prefix, len(matched), len(native), len(shapes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--historical", action="store_true", help="Build the 2018–2024 map batch")
    group.add_argument("--legacy", action="store_true", help="Build the 2008–2012 map batch")
    args = parser.parse_args()
    years = (2008, 2010, 2012) if args.legacy else (2018, 2020, 2022, 2024) if args.historical else (2024,)
    build(args.inputs, args.output, years=years)
