"""Reconcile Maryland's precinct affiliation snapshots to their county controls."""

import csv
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO, StringIO
import re

from scripts.participation_intake.contract import IntakeError, count

BASE = "https://elections.maryland.gov/"
GUIDE = BASE + "press_room/Navigating_Official_Turnout_Statistics.pdf"
EDITIONS = {
    "2016-11-08": ("elections/archive/2016/turnout/general/Official%20by%20Party%20and%20", "November 08, 2016",
                   "2016 Presidential General Election", None, 12084, None),
    "2018-11-06": ("elections/archive/2018/turnout/general/Official%20by%20Party%20and%20", "November 06, 2018",
                   "2018 Gubernatorial General Election", None, 12096, None),
    "2020-11-03": ("press_room/2020_stats/Official%20by%20Party%20and%20", "November 03, 2020",
                   "2020 Presidential General Election", None, 16320, None),
    "2022-11-08": ("press_room/2022_stats/GG22/Official%20by%20Party%20and%20", "November 8, 2022",
                   "2022 Gubernatorial General Election", "December 8, 2022", 14686, "WORKING CLASS PARTY"),
    "2024-11-05": ("press_room/2024_stats/PG24/Updated-Official_by_Party_and_", "November 5, 2024",
                   "2024 Presidential General Election", "April 29, 2026", 13874, "NO LABELS MARYLAND"),
}
COUNTIES = (
    "Allegany|Anne Arundel|Baltimore City|Baltimore County|Calvert|Caroline|Carroll|Cecil|Charles|"
    "Dorchester|Frederick|Garrett|Harford|Howard|Kent|Montgomery|Prince George's|Queen Anne's|"
    "Saint Mary's|Somerset|Talbot|Washington|Wicomico|Worcester"
).split("|")
PARTIES = {"DEMOCRATIC", "GREEN", "LIBERTARIAN", "OTHER PARTIES", "REPUBLICAN", "UNAFFILIATED"}
MEASURES = ("polls", "early_voting", "mail", "provisional", "eligible_registered")
ROW_CSV = "participation-md-precinct-affiliation-snapshots.csv"
GROUP_CSV = "participation-md-county-affiliation-snapshots.csv"
NUMERATOR = "reported_ballot_activity_voter_file_snapshot"


def routes(election):
    base = BASE + EDITIONS[election][0]
    return base + "Precinct.csv", base + "County.pdf"


def header(election):
    modes = ("EARLY_VOTING", "VBM") if election.startswith("2024-") else ("EARLY_VOING", "ABSENTEE")
    return ["LBE", "CONGRESSIONAL_DISTRICT_CODE", "LEGISLATIVE_DISTRICT_CODE", "PRECINCT", "PARTY",
            "POLLS", *modes, "PROVISIONAL", "ELIGIBLE_VOTERS"]


def query(native, control, election):
    _, day, title, edition, size, minor = EDITIONS[election]
    dates = [line.strip() for line in control.splitlines() if line.strip().startswith("Election Date:")]
    editions = [line.strip() for line in control.splitlines() if line.strip().startswith("As of:")]
    if (len(native) != size or dates != [f"Election Date: {day}"]
            or f"Election: {title}" not in control or editions != ([f"As of: {edition}"] if edition else [])):
        raise IntakeError("md_scope", "Maryland precinct inventory or county-control election differs")
    legacy_fragments = election == "2020-11-03"
    parties = (PARTIES | {minor}) if minor else (PARTIES - {"DEMOCRATIC"}) | {"DEMOCRAT"}
    if legacy_fragments:
        parties |= {"BREAD AND ROSES", "WORKING CLASS PARTY"}
    rows = []
    pattern = re.compile(r"(\D.*?)\s+((?:[\d,]+\s+){5})([\d.]+)%")
    for line in control.splitlines():
        if match := pattern.fullmatch(line.strip()):
            name, values, rate = match.groups()
            values = [count(v) for v in values.split()]
            if (not values[-1] or (Decimal(sum(values[:4])) * 100 / values[-1]).quantize(
                    Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(rate)):
                raise IntakeError("md_control_rate", "Maryland county control fraction does not reconcile")
            rows.append((name.strip(), values, rate))
            if name.strip() == "TOTAL":
                break
    if [r[0] for r in rows] != [*COUNTIES, "TOTAL"]:
        raise IntakeError("md_roster", "Maryland county-control roster is incomplete")

    totals = defaultdict(lambda: [0] * 5)
    group_totals = defaultdict(lambda: [0] * 5)
    identities = set()
    unknown = set()
    for row in native:
        if len(row) != 10:
            raise IntakeError("md_schema", "Unexpected Maryland turnout field count")
        county, congress, district, precinct, party = row[:5]
        key = tuple(row[:5])
        values = [count(v) for v in row[5:]]
        unassigned = precinct == "Unable to Determine"
        if (county not in COUNTIES or party not in parties
                or (key in identities and not (legacy_fragments and unassigned))
                or any(v is None for v in values[:4])
                or (unassigned and (congress or district or values[-1] is not None or any(values[:3])))
                or (not unassigned and (not congress or not district or values[-1] is None
                    or not (re.fullmatch(r"[0-9]{3}-[0-9]{3}", precinct)
                            or (election.startswith("2022-") and county == "Frederick"
                                and precinct == "0.1-" and not any(values)))))):
            raise IntakeError("md_identity", "Invalid or duplicate Maryland precinct/group identity")
        if unassigned:
            unknown.add((county, party))
        identities.add(key)
        for i, value in enumerate(values):
            totals[county][i] += value or 0
            if legacy_fragments:
                group_totals[(party, county)][i] += value or 0
                group_totals[(party, "TOTAL")][i] += value or 0
    totals["TOTAL"] = list(map(sum, zip(*totals.values())))
    if (unknown != {(c, p) for c in COUNTIES for p in parties}
            or any(totals[name] != values for name, values, _ in rows)):
        raise IntakeError("md_reconciliation", "Maryland turnout differs from county controls")
    if legacy_fragments:
        checked = set()
        group = None
        for line in control.splitlines():
            literal = line.strip()
            if literal.upper() in parties:
                group = literal.upper()
            if group and (match := pattern.fullmatch(literal)):
                name, values, _ = match.groups()
                key = (group, name.strip())
                if key in checked or key not in group_totals or group_totals[key] != [count(v) for v in values.split()]:
                    raise IntakeError("md_group_control", "2020 unassigned rows no longer reconcile by affiliation")
                checked.add(key)
        if checked != set(group_totals):
            raise IntakeError("md_group_control", "Missing 2020 county/affiliation controls")
    return {"election_date": election, "edition": edition, "header": header(election),
            "native_rows": native, "control_page": control,
            "county_controls": [[name, values, rate] for name, values, rate in rows], "guide_url": GUIDE}


def parse(body, supporting, election):
    from pypdf import PdfReader

    if not (0 < len(body) <= 2_000_000 and 0 < len(supporting) <= 2_000_000 and supporting.startswith(b"%PDF-")):
        raise IntakeError("md_download", "Unexpected Maryland turnout source type or size")
    reader = csv.reader(StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    if next(reader, None) != header(election):
        raise IntakeError("md_schema", "Maryland turnout columns changed")
    with BytesIO(supporting) as stream:
        pages = PdfReader(stream).pages
        if election == "2020-11-03" and len(pages) != 6:
            raise IntakeError("md_group_control", "2020 county/affiliation report page inventory changed")
        control = "\n".join(p.extract_text(extraction_mode="layout")
                            for p in (pages if election == "2020-11-03" else pages[:1]))
    return query([r for r in reader if r], control, election)


def exports(entries):
    units, groups = [], []
    for election in EDITIONS:
        feed = f"MD-{election[:4]}-general-precinct-affiliation-turnout"
        entry = entries.get(feed) or {}
        data = entry.get("data")
        if not data:
            continue
        url, control_url = routes(election)
        report, supporting, retained = (data[key] for key in ("report", "supporting_report", "complete_native_query"))
        if (data["election_date"] != election or entry["status"] not in ("reported", "retained_after_failure")
                or data.get("participation_observation_qualified") is not False
                or report["url"] != url or supporting["url"] != control_url
                or any(entry["source"].get(k) != report[k] for k in ("url", "sha256", "bytes"))
                or retained != query(retained["native_rows"], retained["control_page"], election)):
            raise ValueError("Invalid Maryland turnout snapshot binding")
        base = {"state_code": "MD", "election_date": election, "report_edition": retained["edition"],
                "participation_measure": NUMERATOR, "registration_basis": "active, inactive and pending; excludes incomplete and cancelled",
                "source_status": entry["status"], "source_url": url, "source_sha256": report["sha256"],
                "county_control_url": control_url, "county_control_sha256": supporting["sha256"], "guide_url": GUIDE}
        sums = defaultdict(lambda: [0] * 6)
        for source_row, (county, cd, ld, precinct, party, *values) in enumerate(retained["native_rows"], 1):
            mode = [count(v) for v in values]
            located = bool(re.fullmatch(r"[0-9]{3}-[0-9]{3}", precinct))
            units.append({**base, "local_election_board": county, "congressional_district_code": cd,
                          "legislative_district_code": ld, "native_precinct": precinct,
                          "registration_affiliation": party, **dict(zip(MEASURES, mode)),
                          **({"source_record_ordinal": source_row} if election == "2020-11-03" else {}),
                          "reported_ballot_activity": sum(mode[:4]), "has_native_precinct_id": located})
            for key in ((county, party), ("Maryland", party)):
                for i, value in enumerate(mode):
                    sums[key][i] += value or 0
                sums[key][-1] += 0 if located else sum(mode[:4])
        for (area, party), values in sorted(sums.items()):
            groups.append({**base, "geography_level": "state" if area == "Maryland" else "county_equivalent",
                           "geography": area, "registration_affiliation": party,
                           **dict(zip(MEASURES, values[:5])), "reported_ballot_activity": sum(values[:4]),
                           "reported_ballot_activity_without_precinct": values[-1]})
    return units, groups
