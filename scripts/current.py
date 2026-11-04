"""Preserve unofficial 2026 NC reporting separately from historical turnout."""

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone

import requests

from scripts.download import ROOT, atomic_json

ELECTION = "2026-11-03"
BASE = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/"
SPECS = {
    "reporting.json": "https://er.ncsbe.gov/enr/20261103/data/county.txt",
    "absentee-state.csv": BASE + "2026_11_03/absentee_counts_state_20261103.csv",
    "absentee-counties.csv": BASE + "2026_11_03/absentee_counts_county_20261103.csv",
    "absentee-layout.txt": BASE + "layout_absentee_counts_state.txt",
    "absentee-catalog.html": "https://www.ncsbe.gov/results-data/absentee-and-provisional-data",
    "history-catalog.html": "https://www.ncsbe.gov/results-data/voter-history-data",
    "reporting-portal.html": "https://er.ncsbe.gov/",
}
METHODS = {"CIVILIAN", "EARLY VOTING", "MILITARY", "ONE-STOP", "OVERSEAS"}
FIELDS = ["abs_request_type", "party_cd", "gender", "race", "ethnicity"]


def integer(value):
    if not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"Invalid nonnegative count: {value!r}")
    return int(value)


def absentee_counts(content, county=False):
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    header = next(reader)
    expected = (["county_name"] if county else []) + FIELDS
    # The published 2026 CSV labels its count column "0", not "ballot_count".
    if header[:-1] != expected or header[-1] not in {"0", "ballot_count"}:
        raise ValueError(f"Unexpected aggregate absentee schema: {header}")
    joint, projected, seen = Counter(), Counter(), set()
    row_count = 0
    for values in reader:
        if len(values) != len(header):
            raise ValueError("Malformed aggregate absentee row")
        key, count = tuple(values[:-1]), integer(values[-1])
        if key in seen:
            raise ValueError("Duplicate aggregate absentee cell")
        seen.add(key)
        row = dict(zip(header, values))
        geography = row["county_name"] if county else "STATEWIDE"
        method = row["abs_request_type"]
        if method not in METHODS or not geography or any(not row[field] for field in FIELDS):
            raise ValueError("Unexpected absentee group or request type")
        joint[tuple(row[field] for field in FIELDS)] += count
        for selected_method in [method, "All methods"]:
            for dimension, group in [("overall", "All"), ("race", row["race"]),
                                     ("ethnicity", row["ethnicity"]), ("sex", row["gender"])]:
                projected[(geography, selected_method, dimension, group)] += count
        row_count += 1
    if not row_count:
        raise ValueError("Empty absentee aggregate")
    return joint, projected, row_count


def reporting_counts(payload):
    if not isinstance(payload, list) or not payload:
        raise ValueError("Expected county reporting array")
    records, seen = [], set()
    for row in payload:
        county_id = str(row["cid"])
        if county_id in seen or "11/03/2026" not in row["tle"]:
            raise ValueError("Duplicate county or wrong election in reporting feed")
        seen.add(county_id)
        ballots, registered = integer(row["bct"]), integer(row["rtl"])
        reported, total = integer(row["prt"]), integer(row["ptl"])
        if reported > total:
            raise ValueError("Reported precincts exceed source total")
        published = str(row["bpt"])
        if not re.fullmatch(r"\d+(?:\.\d+)?%", published):
            raise ValueError("Unexpected published turnout percentage")
        published_rate = float(published[:-1])
        quality = []
        if reported < total:
            quality.append("incomplete_precinct_reporting")
        rate = 100 * ballots / registered if registered > 0 else None
        if registered == 0:
            quality.append("registration_unavailable")
        if ballots == 0:
            quality.append("no_ballots_reported_yet")
            rate = None
        if ballots > registered:
            quality.append("ballots_exceed_registration")
            rate = None
        if rate is not None and abs(rate - published_rate) > 0.015:
            quality.append("published_percentage_disagrees_with_counts")
            rate = None
        records.append({
            "county_id": county_id,
            "county": "STATEWIDE" if county_id == "0" else row["cnm"],
            "ballots_cast": ballots, "registered_voters": registered,
            "reported_ballot_fraction_pct": round(rate, 3) if rate is not None else None,
            "source_published_pct": published_rate,
            "precincts_reporting": reported, "precincts_total": total,
            "source_update_label": row["imp"], "quality": quality,
        })
    statewide = [row for row in records if row["county_id"] == "0"]
    if len(statewide) != 1:
        raise ValueError("Expected one statewide reporting record")
    counties = [row for row in records if row["county_id"] != "0"]
    if len({row["county"] for row in counties}) != len(counties):
        raise ValueError("Duplicate county name")
    audit = {}
    for field in ["ballots_cast", "registered_voters", "precincts_reporting", "precincts_total"]:
        difference = sum(row[field] for row in counties) - statewide[0][field]
        audit[f"county_minus_state_{field}"] = difference
    if any(audit.values()):
        raise ValueError(f"County/state reporting reconciliation failed: {audit}")
    return sorted(records, key=lambda row: row["county"]), audit


def normalize(raw, sources, snapshot_id, retrieved_at):
    state_joint, state_groups, state_rows = absentee_counts(raw["absentee-state.csv"])
    county_joint, county_groups, county_rows = absentee_counts(raw["absentee-counties.csv"], county=True)
    if state_joint != county_joint:
        raise ValueError("State/county absentee cells disagree; do not combine different updates")
    reporting, audit = reporting_counts(json.loads(raw["reporting.json"]))
    counties = {key[0] for key in county_groups}
    if counties != {row["county"] for row in reporting if row["county_id"] != "0"}:
        raise ValueError("Absentee and reporting county coverage disagree")
    groups = state_groups + county_groups
    # Counter addition drops zero-valued groups; those source cells remain observed.
    for key in state_groups.keys() | county_groups.keys():
        groups.setdefault(key, 0)
    observations = [
        {"county": county, "request_type": method, "dimension": dimension,
         "group": group, "ballots": count, "turnout_pct": None}
        for (county, method, dimension, group), count in sorted(groups.items())
    ]
    return {
        "snapshot_id": snapshot_id, "election_date": ELECTION,
        "state": "North Carolina", "status": "preliminary", "retrieved_at": retrieved_at,
        "sources": sources,
        "measure": "Reported ballots, not candidate votes or finalized demographic turnout.",
        "limitations": [
            "Election-night reporting is incomplete and unofficial; these are saved snapshots, not a live feed.",
            "Reported ballots / registered voters is a partial reporting fraction, not final turnout or voting-eligible-population turnout.",
            "Zero ballots in an unreported county are not zero turnout; the displayed fraction is withheld.",
            "Absentee/early-voting demographic counts have a different update time and exclude Election Day in-person voting.",
            "The two feeds overlap: never add absentee counts to election-night ballots or infer all-voter demographic turnout.",
            "No matched group registration denominator is ingested; demographic turnout percentages remain null.",
            "Party affiliation is summed out. No candidate preferences, individual records, age, or education are inferred.",
            "2026 precinct-level demographic turnout and election-year geometry are not incorporated.",
        ],
        "history_archive_status": "listed_not_ingested" if b"history_stats_20261103.zip" in raw["history-catalog.html"] else "not_listed_in_retrieved_catalog",
        "audit": {**audit, "absentee_state_rows": state_rows, "absentee_county_rows": county_rows,
                  "county_count": len(counties), "absentee_state_county_cells_match": True},
        "reporting": reporting, "demographics": observations,
    }


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, list) else value
                             for key, value in row.items()})


def digest(content):
    return hashlib.sha256(content).hexdigest()


def refresh():
    started = datetime.now(timezone.utc)
    snapshot_id = started.strftime("%Y%m%dT%H%M%SZ")
    raw_dir = ROOT / "data/raw/current" / snapshot_id
    raw_dir.mkdir(parents=True, exist_ok=False)
    raw, sources = {}, []
    try:
        with requests.Session() as session:
            for name, url in SPECS.items():
                response = session.get(url, timeout=(15, 90), headers={"Cache-Control": "no-cache"})
                response.raise_for_status()
                content = response.content
                (raw_dir / name).write_bytes(content)
                raw[name] = content
                sources.append({
                    "file": name, "url": url, "bytes": len(content), "sha256": digest(content),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "last_modified": response.headers.get("Last-Modified"),
                    "etag": response.headers.get("ETag"),
                })
        snapshot = normalize(raw, sources, snapshot_id, datetime.now(timezone.utc).isoformat())
        if snapshot["audit"]["county_count"] != 100:
            raise ValueError("Expected all 100 NC counties")
        atomic_json(raw_dir / "manifest.json", {"status": "validated", "sources": sources})
    except Exception as error:
        atomic_json(raw_dir / "manifest.json", {"status": "rejected", "sources": sources,
                                              "error": str(error)})
        raise
    output = ROOT / "public/data/current" / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "snapshot.json", snapshot)
    write_csv(output / "demographics.csv", snapshot["demographics"])
    write_csv(output / "reporting.csv", snapshot["reporting"])
    with zipfile.ZipFile(output / "complete-snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(raw_dir.iterdir()):
            archive.write(path, "sources/" + path.name)
        for name in ["snapshot.json", "demographics.csv", "reporting.csv"]:
            archive.write(output / name, name)
    files = [{"path": f"current/{snapshot_id}/{path.name}", "bytes": path.stat().st_size,
              "sha256": digest(path.read_bytes())} for path in sorted(output.iterdir())]
    atomic_json(output.parent / "latest.json", {
        "snapshot_id": snapshot_id, "election_date": ELECTION, "status": "preliminary",
        "retrieved_at": snapshot["retrieved_at"], "files": files,
    })
    print(json.dumps({"snapshot_id": snapshot_id, "audit": snapshot["audit"],
                      "statewide_reporting": next(row for row in snapshot["reporting"]
                                                  if row["county_id"] == "0")}, indent=2))


if __name__ == "__main__":
    refresh()
