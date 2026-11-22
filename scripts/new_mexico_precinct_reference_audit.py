"""Audit historical turnout identifiers against dated GIS reference snapshots."""

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

from scripts import new_mexico_turnout_history as history

REFERENCES = {
    "20110913": (
        "https://www.nmlegis.gov/sessions/diy_redistricting/2011/Precincts_2011_shapefile.zip",
        "df54f0bc1edeb480bd13ec423cb524570f0f9979a7a852a8dd26baa670c4347c", 1483,
    ),
    "20211002": (
        "https://gstore.unm.edu/apps/rgis/datasets/79831c04-0610-4d8f-81e1-eec220b32379/NM_VTD_20211002.original.zip",
        "de1418b95da1b21beab7ff35220f5fdefd3c0ce95172f52ac503e88b013159b2", 2163,
    ),
    "20240703": (
        "https://gstore.unm.edu/apps/rgis/datasets/3b1de40a-b37e-4d35-abdd-fd40bbbbe39e/New_Mexico_Voting_Precinct_20240703.original.zip",
        "e780d3ded576f40a52ba562b468ea17068212ce0cf141a65c6de9b5d34d13c4d", 2169,
    ),
}
VINTAGES = {2016: "20110913", 2018: "20110913", 2020: "20211002",
            2022: "20211002", 2024: "20240703"}
ROW_DIGESTS = {
    "20110913": "8fb331584d308ffcbd5b7c08f8279a6e9e323ac8faec5f2274fdbc4f35c5194b",
    "20211002": "303f6eb1f0407a1a34390e5b2340c6f63779e155423e4b6b8dd88db59ddca1a7",
    "20240703": "c1e30537ed88990fa4662f23060f02c4ad06ebaed21d0e93021553c92129bf3d",
}
ARCHIVE_LIMIT = 40_000_000
MEMBER_LIMIT = 150_000_000
DISPOSITIONS = "precinct-reference-dispositions.csv"
REPRODUCE = """New Mexico historical precinct identifier audit

With Python 3.12, run from the extracted download:
  python3.12 -m scripts.new_mexico_precinct_reference_audit --turnout-facts inputs/turnout-facts.json --reference-rows inputs/reference-rows.json --output reproduced

Compare the two CSVs and summary.json, source-receipts.json, and inputs/ to
the corresponding files in reproduced/. accepted-checkpoint.json, when
present, is the publication handoff receipt, not a replayed query.

The source receipts pin the three original GIS archives. To verify the
extraction, name the originals by vintage (e.g. 20110913.zip), install
pyshp==3.1.8 and shapely==2.2.0, and replace --reference-rows and its
value with --reference-archives and the directory containing the ZIPs.

An identifier match is not proof of an election-day boundary.
"""


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def county_key(county):
    key = county.casefold()
    return "dona ana" if key == "doña ana" else key


def precinct_key(vtd):
    return vtd.lstrip("0") or "0"


def label_code(county, label):
    match = re.fullmatch(r"(?:(?:PCT|PREC|PRECINCT)\s+)?([0-9]+[A-Z]?)", label, re.I | re.ASCII)
    if match is None and county == "Hidalgo":
        match = re.fullmatch(r"PRECINCT ([0-9]+)\s*-\s*[A-Z/ ]+", label, re.I | re.ASCII)
    if match is None:
        raise ValueError(f"Unrecognized turnout label: {county}, {label}")
    return precinct_key(match[1].upper())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def reference_body(vintage, folder):
    url, digest, _ = REFERENCES[vintage]
    if folder is not None:
        with (folder / f"{vintage}.zip").open("rb") as stream:
            body = stream.read(ARCHIVE_LIMIT + 1)
    else:
        with urllib.request.build_opener(NoRedirect()).open(url, timeout=45) as stream:
            if stream.status != 200 or stream.geturl() != url:
                raise ValueError(f"Unexpected reference response: {vintage}")
            body = stream.read(ARCHIVE_LIMIT + 1)
    if not 0 < len(body) <= ARCHIVE_LIMIT or hashlib.sha256(body).hexdigest() != digest:
        raise ValueError(f"Changed reference original: {vintage}")
    return body


def reference_rows(vintage, body, counties):
    import shapefile
    from shapely.geometry import shape

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        (stem,) = [member[:-4] for member in names if member.endswith(".dbf")]
        parts = {}
        for ext in ("dbf", "shp", "shx"):
            member = f"{stem}.{ext}"
            if names.count(member) != 1 or archive.getinfo(member).file_size > MEMBER_LIMIT:
                raise ValueError(f"Invalid shapefile inventory: {vintage}, {member}")
            parts[ext] = io.BytesIO(archive.read(member))
        legacy = vintage == "20110913"
        with shapefile.Reader(**parts, encoding="cp1252" if legacy else "utf-8") as records:
            for entry in records.iterShapeRecords():
                r = entry.record
                if legacy:
                    state, county, vtd, code = r.STATEFP10, r.COUNTYFP10, r.VTDST10, r.GEOID10
                    name = counties[county]
                else:
                    state, county, vtd, code = r.STATE, r.COUNTY_FIP, r.VTD, r.GEOCODE
                    name = county_key(r.COUNTY_NAM)
                geom = shape(entry.shape.__geo_interface__)
                if state != "35" or geom.geom_type not in {"Polygon", "MultiPolygon"}:
                    raise ValueError(f"Invalid New Mexico reference record: {vintage}, {code}")
                yield [name, county, vtd, code, bool(geom.area > 0 and geom.is_valid)]


def extract_references(originals):
    result = {}
    for vintage in ("20211002", "20240703", "20110913"):
        counties = {row[1]: row[0] for row in result.get("20211002", [])}
        result[vintage] = sorted(reference_rows(vintage, originals[vintage], counties))
    return result


def reference_index(rows, expected):
    result, county_by_id, id_by_county = {}, {}, {}
    for name, county, vtd, code, valid in rows:
        key = name, precinct_key(vtd)
        if (not name or name != county_key(name) or not re.fullmatch(r"[0-9]{3}", county)
                or not re.fullmatch(r"[0-9]+[A-Z]?", vtd) or code != "35" + county + vtd
                or key in result or type(valid) is not bool
                or county_by_id.setdefault(county, name) != name
                or id_by_county.setdefault(name, county) != county):
            raise ValueError(f"Conflicting GIS reference identifier: {code}")
        result[key] = code, valid
    if len(result) != expected or len(county_by_id) != 33:
        raise ValueError("Incomplete GIS reference inventory")
    return result


def screen_year(year, reference, observed):
    seen = set()
    report = {"year": year, "reference": VINTAGES[year], "native_units": len(observed),
              "reference_units": len(reference), "matched_keys": 0, "matched_valid_polygons": 0,
              "matched_source_ballots": 0, "source_ballots": 0, "election_day_geometry_verified": False}
    out = []
    for r in observed:
        key = county_key(r["county"]), label_code(r["county"], r["unit"])
        if key in seen:
            raise ValueError(f"Ambiguous turnout key: {year}, {key}")
        seen.add(key)
        code, valid = reference.get(key, ("", False))
        ballots = r["source_reported_count"]
        report["source_ballots"] += ballots
        report["matched_keys"] += bool(code)
        report["matched_valid_polygons"] += valid
        report["matched_source_ballots"] += ballots if code else 0
        out.append({"election_year": year, "reference": VINTAGES[year], "county": r["county"],
                    "native_county_id": r["county_id"], "native_unit": r["unit"], "reference_geocode": code,
                    "reference_shape_valid": valid if code else None, "election_day_geometry_verified": False,
                    "ballots": ballots, "eligible": r["source_eligible_voters"], "rate_hold": r["rate_hold"],
                    "disposition": "key_only" if code else "turnout_only"})
    for key in sorted(reference.keys() - seen):
        code, valid = reference[key]
        out.append({"election_year": year, "reference": VINTAGES[year], "county": key[0],
                    "reference_geocode": code, "reference_shape_valid": valid,
                    "election_day_geometry_verified": False, "disposition": "reference_only"})
    report["reference_only_units"] = len(reference.keys() - seen)
    return report, out


def build(entries, references):
    from scripts.new_mexico_turnout_history_replay import build as build_turnout

    if (set(entries) != set(history.FEEDS) or any(not entry.get("data") for entry in entries.values())
            or set(references) != set(REFERENCES)):
        raise ValueError("All five turnout editions and three reviewed GIS references are required")
    for key, rows in references.items():
        if hashlib.sha256(json_bytes(rows)).hexdigest() != ROW_DIGESTS[key]:
            raise ValueError(f"Changed normalized GIS reference: {key}")
    observed = list(history.exports(entries))
    indexes = {key: reference_index(references[key], expected)
               for key, (_, _, expected) in REFERENCES.items()}
    screen, totals = [], []
    for year, vintage in VINTAGES.items():
        rows = [r for r in observed if r["geography_level"] == "reporting_unit"
                and r["election_date"].startswith(f"{year}-")]
        report, decisions = screen_year(year, indexes[vintage], rows)
        totals.append(report)
        screen.extend(decisions)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(screen[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(screen)
    turnout = build_turnout(entries)[history.CSV]
    return {
        DISPOSITIONS: stream.getvalue().encode(),
        "summary.json": json_bytes(totals),
        history.CSV: turnout,
        "REPRODUCE.txt": REPRODUCE.encode(),
        "source-receipts.json": json_bytes({
            "reference_sources": {key: {"url": url, "sha256": digest, "records": expected,
                                        "normalized_sha256": ROW_DIGESTS[key]}
                                  for key, (url, digest, expected) in REFERENCES.items()},
            "turnout_sources": {key: entry["source"] for key, entry in entries.items()},
            "scope": "Identifier audit only; no election-day geometry or allocation claim.",
        }),
    }


def accepted_entries(pointer_url):
    from scripts.automatic_runtime import fetch, results_pointer, uncompressed

    if not re.fullmatch(r"https://raw\.githubusercontent\.com/hanshanley/voter-participation/"
                        r"[a-f0-9]{40}/latest\.json", pointer_url):
        raise ValueError("Use the exact commit-pinned accepted results pointer")
    pointer = results_pointer(pointer_url)
    name = "granular-source-queries.json.gz"
    pin = pointer["files"].get(name)
    if not isinstance(pin, dict) or set(pin) != {"bytes", "sha256"}:
        raise ValueError("Accepted checkpoint lacks the granular query pin")
    body = fetch(pointer["base_url"] + name, pin, maximum=80_000_000)
    entries = json.loads(uncompressed(body))
    return {key: entries[key] for key in history.FEEDS if key in entries}, pointer["version"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--turnout-facts", type=Path)
    source.add_argument("--results-pointer")
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument("--reference-rows", type=Path)
    reference.add_argument("--reference-archives", type=Path)
    reference.add_argument("--fetch-references", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.results_pointer:
        entries, results_version = accepted_entries(args.results_pointer)
    else:
        entries, results_version = json.loads(args.turnout_facts.read_bytes()), None
    if set(entries) != set(history.FEEDS) or any(not entry.get("data") for entry in entries.values()):
        raise ValueError("Accepted inputs lack one or more complete New Mexico turnout editions")
    if args.reference_rows:
        refs = json.loads(args.reference_rows.read_bytes())
    else:
        originals = {vintage: reference_body(vintage, args.reference_archives) for vintage in REFERENCES}
        refs = extract_references(originals)
    outputs = build(entries, refs)
    args.output.mkdir()
    for name, body in outputs.items():
        (args.output / name).write_bytes(body)
    inputs = args.output / "inputs"
    inputs.mkdir()
    (inputs / "turnout-facts.json").write_bytes(json_bytes(entries))
    (inputs / "reference-rows.json").write_bytes(json_bytes(refs))
    if results_version:
        (args.output / "accepted-checkpoint.json").write_bytes(
            json_bytes({"pointer": args.results_pointer, "version": results_version}))


if __name__ == "__main__":
    main()
