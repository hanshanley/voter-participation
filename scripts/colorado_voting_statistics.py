"""Reconcile Colorado's official hierarchical Voting Statistics CSV exports."""

import csv
import io
import re
from datetime import date
from html import unescape

from scripts.participation_intake.contract import count

EDITIONS = {"2020-11-03": "25358", "2022-11-08": "25989", "2024-11-05": "26759"}
PARTY_SUBHEADER = ["", "", "Republican", "", "", ""]
REGISTRATION_HOLD = "registration_column_party_labeled"
REGISTRATION_BASIS = "Total registration (active plus inactive)"
REPORT = "https://co.elstats3.civera.com/api/download_contest/{id}_table.csv?split_party=false"
INDEX = "https://historicalelectiondata.coloradosos.gov/contest/"
COUNTIES = (
    "Adams|Alamosa|Arapahoe|Archuleta|Baca|Bent|Boulder|Broomfield|Chaffee|Cheyenne|Clear Creek|"
    "Conejos|Costilla|Crowley|Custer|Delta|Denver|Dolores|Douglas|Eagle|El Paso|Elbert|Fremont|"
    "Garfield|Gilpin|Grand|Gunnison|Hinsdale|Huerfano|Jackson|Jefferson|Kiowa|Kit Carson|La Plata|"
    "Lake|Larimer|Las Animas|Lincoln|Logan|Mesa|Mineral|Moffat|Montezuma|Montrose|Morgan|Otero|"
    "Ouray|Park|Phillips|Pitkin|Prowers|Pueblo|Rio Blanco|Rio Grande|Routt|Saguache|San Juan|"
    "San Miguel|Sedgwick|Summit|Teller|Washington|Weld|Yuma"
).split("|")
LABELS = {
    "Active Voters": "active", "Inactive Voters": "inactive",
    "Total Voters": "registered", "Total Registered Voters": "registered",
    "Registered Voters": "registered",
    "Total Ballots Cast": "ballots_cast",
}


def routes(election):
    identity = EDITIONS[election]
    return INDEX + identity, REPORT.format(id=identity)


def discover(body, election):
    identity = EDITIONS[election]
    day = date.fromisoformat(election)
    expected_title = (f"{day.year} Nov {day.day} • General • Voting Statistics • "
                      "State of Colorado | State of Colorado")
    html = unescape(body.decode("utf-8-sig"))
    if re.findall(r"<title(?:\s[^>]*)?>([^<]*)</title>", html) != [expected_title]:
        raise ValueError("Unreviewed Colorado voting statistics election identity")
    # Bind the authority page's contest ID to the reviewed provider export.
    url = routes(election)[1]
    links = set(re.findall(r'https://co\.elstats(?:3)?\.civera\.com/api/download_contest/\d+_table\.csv\?split_party=false', html))
    reviewed = {url, url.replace("co.elstats3.", "co.elstats.")}
    if not links & reviewed or not all(f"/{identity}_table.csv?" in link for link in links):
        raise ValueError("Unreviewed Colorado voting statistics export link")
    return url


def parse(body, election):
    return query(list(csv.reader(io.StringIO(body.decode("utf-8-sig")))), election)


def query(rows, election):
    count_only = (election == "2020-11-03" and len(rows) >= 2 and rows[:2] == [
        ["", "", "Registered Voters", "Active Voters", "Inactive Voters", "Total Ballots Cast"], PARTY_SUBHEADER])
    if (len(rows) < 68 or len(rows) > 20_000 or rows[0][:2] != ["", ""]
            or len(rows[0]) != 6 or (not count_only and (rows[1] != [""] * 6 or "Registered Voters" in rows[0]))
            or any(label not in LABELS for label in rows[0][2:])
            or set(map(LABELS.__getitem__, rows[0][2:])) != set(LABELS.values())):
        raise ValueError("Unexpected Colorado voting statistics schema")
    fields = [LABELS[label] for label in rows[0][2:]]
    total, counties, precincts, ids = None, {}, {}, set()
    for row in rows[2:]:
        if len(row) != 6 or not all(re.fullmatch(r"[0-9]+", value) for value in row[2:]):
            raise ValueError("Missing or noninteger Colorado voting statistics")
        level, name = row[:2]
        facts = dict(zip(fields, map(count, row[2:]), strict=True))
        if facts["registered"] != facts["active"] + facts["inactive"]:
            raise ValueError("Colorado active and inactive registration do not reconcile")
        if level == "State" and name == "Colorado" and total is None and not counties:
            total = {"county": "TOTAL", **facts}
        elif level == "County" and total is not None and name in COUNTIES and name not in counties:
            county = name
            counties[name] = {"county": name, **facts}
            precincts[name] = []
        elif level == "Precinct" and counties and re.fullmatch(r"[0-9]{10}", name) and name not in ids:
            ids.add(name)
            precincts[county].append({"precinct": name, **facts})
        else:
            raise ValueError("Unexpected or duplicate Colorado geography")
    if total is None or set(counties) != set(COUNTIES):
        raise ValueError("Incomplete Colorado county roster")
    if any(sum(row[field] for row in counties.values()) != total[field] for field in fields):
        raise ValueError("Colorado counties do not reconcile to the printed state control")
    if any(not precincts[name] or any(sum(row[field] for row in precincts[name]) != counties[name][field]
              for field in fields) for name in COUNTIES):
        raise ValueError("Colorado precincts do not reconcile to the printed county controls")
    return {"native_rows": rows, "counties": [counties[name] for name in COUNTIES], "total": total,
            "precincts": precincts, "registration_basis": None if count_only else REGISTRATION_BASIS,
            "report_note": ("Official Voting Statistics export. The registration column has a party subheader; "
                            "counts are shown without registration rates." if count_only else
                            "Official Voting Statistics export. Registration includes inactive voters. "
                            "Precinct counts are kept in a separate download."),
            "extraction_method": "state_county_precinct_voting_statistics_csv"}
