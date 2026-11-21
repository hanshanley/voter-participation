"""Draw dated Hawaii precinct reference maps without asserting boundary equivalence."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import transform, union_all
from shapely.geometry import shape

from scripts.hawaii_precinct_turnout import FEED, HISTORICAL_FEED, exports
from scripts.nc_precinct_reference import display_paths, topology
from scripts.participation_intake.contract import pin


GIS_PIN = {"bytes": 9150411, "sha256": "63951856278c3e522cbb38abeda710e15f0e133ae8c8db3ec8b473cf2e6437bb"}
QUERY_PINS = {
    2024: "f25d32b87ea9d7419e73d4e8062adad8a391f58e7ac9423c84e2aad42e16bc6d",
    2026: "fd1d3c6193a26c5a5c90fb2088e41551cdcfcd905640f0270caef9849925dc20",
}
COLORS = ("#d5e4e9", "#9ebfca", "#5d96a8", "#2c697d", "#174c60")


def bind(features, rows):
    source = defaultdict(list)
    identities = defaultdict(set)
    project = Transformer.from_crs(4326, 26904, always_xy=True).transform
    counts = {row["native_unit"]: row for row in rows}
    geographic = {key for key, row in counts.items() if row["geography_level"] == "precinct"}
    for feature in features:
        props = feature["properties"]
        key = props["dp"]
        identities[key].add((props["dpnum"], props["county"]))
        geometry = shape(feature["geometry"])
        if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Invalid Hawaii reference polygon: {key}")
        source[key].append(transform(geometry, project, interleaved=False))
    if set(source) != geographic or len(counts) != len(rows):
        raise ValueError("Hawaii reference and native precinct code rosters differ")
    shapes = {}
    for key, parts in sorted(source.items()):
        (identifier, county), = identities[key]
        if identifier != int(key.replace("-", "")) or county not in {"HAWAII", "OAHU", "KAUAI", "MAUI"}:
            raise ValueError("Conflicting Hawaii reference code or county")
        # Multipart precincts carry one reporting count, never one count per shape.
        merged = union_all(parts)
        if merged.geom_type not in {"Polygon", "MultiPolygon"} or merged.is_empty or not merged.is_valid:
            raise ValueError(f"Invalid dissolved Hawaii precinct: {key}")
        shapes[(county, key)] = merged
    overlaps = topology(shapes)
    counties = {key: county for county, key in shapes}
    decisions = []
    for key, row in sorted(counts.items()):
        county = counties.get(key, "")
        status = ("nongeographic_reporting_unit" if not county
                  else "reference_overlap" if (county, key) in overlaps
                  else "reference_code_only")
        decisions.append({**row, "reference_county": county, "reference_parts": len(source.get(key, ())),
                          "reference_vintage": "2024-05", "reference_map_status": status,
                          "election_effective_boundary_verified": False})
    return decisions, shapes


def draw(decisions, shapes):
    rows = {r["native_unit"]: r for r in decisions}
    shaded = sum(row["reference_map_status"] == "reference_code_only" for row in decisions)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 446" role="img" aria-labelledby="title description">',
        '<title id="title">Hawaii 2026 reported counts on May 2024 precinct outlines</title>',
        f'<desc id="description">{shaded} reference units shaded by native counts, not rates. '
        'The outlines are not verified for the 2026 election. See the accompanying decision table.</desc>',
        '<rect width="960" height="446" fill="white"/>',
        '<text x="20" y="27" font-size="21">Hawaii · November 2026 precinct counts</text>',
        '<text x="20" y="49" font-size="14">May 2024 outlines, matched by code only · not 2026 election boundaries or rates</text>',
    ]
    for (_, key), path in display_paths(shapes):
        row = rows[key]
        n = row["reported_mode_sum"]
        accepted = row["reference_map_status"] == "reference_code_only"
        fill = COLORS[sum(n >= cut for cut in (1, 500, 1500, 3000))] if accepted else "#eceeef"
        label = f"{n:,} native reported ballots" if accepted else "reference overlap; not shaded"
        lines.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd" stroke="#68828a" '
                     f'stroke-width=".18"><title>{key}: {label}</title></path>')
    for i, label in enumerate(("Zero", "1–499", "500–1,499", "1,500–2,999", "3,000 or more")):
        x = 20 + i * 139
        lines.append(f'<rect x="{x}" y="391" width="17" height="12" fill="{COLORS[i]}"/>'
                     f'<text x="{x+22}" y="402" font-size="13">{label}</text>')
    lines.append('<text x="20" y="430" font-size="13">Gray: not shaded. Precinct totals differ from the state summary; rates withheld.</text></svg>')
    return "\n".join(lines) + "\n"


def draw_historical(decisions, shapes, *, rate):
    rows = {r["native_unit"]: r for r in decisions}
    field = "qualified_registration_fraction_pct" if rate else "reported_mode_sum"
    measure = "Percent of same-report registrations" if rate else "Native reported ballot counts"
    cuts = (40, 50, 60, 70) if rate else (1, 500, 1500, 3000)
    labels = ("Under 40%", "40–49%", "50–59%", "60–69%", "70% or more") if rate else (
        "Zero", "1–499", "500–1,499", "1,500–2,999", "3,000 or more")
    available = sum(r["reference_map_status"] == "reference_code_only" and r[field] is not None
                    for r in decisions)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 446" role="img" aria-labelledby="title description">',
        '<title id="title">Hawaii November 2024 participation</title>',
        f'<desc id="description">{measure}. {available} precincts are shaded on May 2024 reference outlines.</desc>',
        '<rect width="960" height="446" fill="white"/>',
        '<text x="20" y="27" font-size="21">Hawaii · November 2024 precinct participation</text>',
        f'<text x="20" y="49" font-size="14">{measure} · {available} shaded · May 2024 reference outlines</text>',
    ]
    for (_, key), path in display_paths(shapes):
        row = rows[key]
        value = row[field] if row["reference_map_status"] == "reference_code_only" else None
        fill = COLORS[sum(value >= cut for cut in cuts)] if value is not None else "#eceeef"
        label = "not shaded" if value is None else f"{value:.2f}%" if rate else f"{value:,} ballots"
        lines.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd" stroke="#68828a" '
                     f'stroke-width=".18"><title>{key}: {label}</title></path>')
    for i, label in enumerate(labels):
        x = 20 + i * 139
        lines.append(f'<rect x="{x}" y="391" width="17" height="12" fill="{COLORS[i]}"/>'
                     f'<text x="{x+22}" y="402" font-size="13">{label}</text>')
    lines.append('<text x="20" y="430" font-size="13">Gray: not shaded, not zero. See the complete decision table.</text></svg>')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, choices=QUERY_PINS, default=2026)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.geometry.read_bytes()
    query = args.query.read_bytes()
    if pin(original) != GIS_PIN or pin(query)["sha256"] != QUERY_PINS[args.year]:
        raise ValueError("Hawaii reference inputs differ from their reviewed editions")
    data = json.loads(query)
    feed = FEED if args.year == 2026 else HISTORICAL_FEED
    rows = exports({feed: {"status": "reported", "data": data}}, year=args.year)
    decisions, shapes = bind(json.loads(original)["features"], rows)
    args.output.mkdir()
    with (args.output / "precinct-reference-decisions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=decisions[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(decisions)
    if args.year == 2026:
        (args.output / "hawaii-2026-precinct-reference.svg").write_text(draw(decisions, shapes), encoding="utf-8")
    else:
        for rate in (False, True):
            name = "rate" if rate else "count"
            (args.output / f"hawaii-2024-precinct-{name}.svg").write_text(
                draw_historical(decisions, shapes, rate=rate), encoding="utf-8")


if __name__ == "__main__":
    main()
