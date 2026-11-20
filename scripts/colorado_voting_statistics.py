"""Reconcile Colorado's official hierarchical Voting Statistics CSV exports."""

import csv
import io
import json
import re
from datetime import date
from hashlib import sha256
from html import unescape

from scripts.participation_intake.contract import count

EDITIONS = {
    "1992-11-03": "25290", "1996-11-05": "8245", "2000-11-07": "7901",
    "2002-11-05": "25268", "2004-11-02": "15046", "2006-11-07": "15044",
    "2008-11-04": "25357", "2010-11-02": "25359", "2012-11-06": "25363",
    "2014-11-04": "25361", "2016-11-08": "25362", "2018-11-06": "25360",
    "2020-11-03": "25358", "2022-11-08": "25989", "2024-11-05": "26759",
}
PARTY_SUBHEADER = ["", "", "Republican", "", "", ""]
REGISTRATION_HOLD = "registration_column_party_labeled"
REGISTRATION_BASIS = "Total registration (active plus inactive)"
ACTIVE_REGISTRATION_HOLD = "active_registration_only"
REGISTRATION_NOT_REPORTED = "registration_not_in_report"
PARTY_EDITIONS = {"2012-11-06", "2018-11-06", "2020-11-03"}
STATE_BALLOT_GAPS = {"1992-11-03": 30, "2012-11-06": 1240, "2014-11-04": 36}
COUNTY_BALLOT_GAPS = {
    "2012-11-06": {
        "Broomfield": 474, "Clear Creek": 126, "Conejos": 59, "Delta": 224, "Dolores": 27,
        "Douglas": 3635, "Grand": 168, "Gunnison": 97, "Kit Carson": 178, "Larimer": 2052,
        "Moffat": 126, "Montrose": 383, "Pitkin": 205, "Rio Blanco": 43, "San Miguel": 2,
        "Summit": 229, "Weld": 2662, "Yuma": 64,
    },
    "2014-11-04": {"Larimer": 43, "Rio Grande": 48, "Summit": 78},
    "2016-11-08": {"Larimer": 32},
}
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
WIDE_HEADERS = {
    "1992-11-03": "8d7c03ece1f505d40d45570ee64da48f58a886e6d495012700efb811cefa43c0",
    "1996-11-05": "a57bfd2cacb91724c52b9bb800e8d19671b4f1646180fa4589cb546ba90f1c5d",
    "2002-11-05": "aafe55d6099cfeba021c68471dc86ee014dc18877839fdc33a358e61d242fe4c",
}
MODES = ["Early Voting", "Absentee Ballot", "Provisional Ballot", "Regular Ballot"]
BALLOTS = "Total Ballots Cast"


def ballot_gap(parent, children, reviewed_gap, description):
    gap = parent["ballots_cast"] - sum(row["ballots_cast"] for row in children)
    if (not children or gap not in (0, reviewed_gap)
            or any(sum(row[field] for row in children) != parent[field] for field in parent
                   if field not in ("ballots_cast", "county", "precinct"))):
        raise ValueError(f"Colorado {description} do not reconcile")
    return gap


def legacy_query(rows, election):
    names = [name for name in COUNTIES if name != "Broomfield" or election >= "2002"]
    county_only = election <= "2002-11-05"
    mode_report = election in ("2004-11-02", "2006-11-07")
    precinct_export = election == "2010-11-02"
    if election in WIDE_HEADERS:
        identity = sha256(json.dumps(rows[:2], separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        if identity != WIDE_HEADERS[election]:
            raise ValueError("Unexpected Colorado legacy wide header")
        hold, basis = REGISTRATION_HOLD, None
    else:
        labels, hold, basis = (
            (["Registered Voters", BALLOTS], None, "Registered voters in the same report")
            if county_only else (MODES + [BALLOTS], REGISTRATION_NOT_REPORTED, None)
            if mode_report else (["Active Voters", BALLOTS], ACTIVE_REGISTRATION_HOLD, None)
        )
        if rows[:2] != [["", "", *labels], [""] * (len(labels) + 2)]:
            raise ValueError("Unexpected Colorado legacy voting statistics schema")
    fields = rows[0][2:]
    native_fields = [LABELS.get(field, field) for field in fields]
    total, counties, units, ids = None, {}, {}, set()
    for row in rows[2:]:
        if len(row) != len(fields) + 2 or not all(re.fullmatch(r"[0-9]+", value) for value in row[2:]):
            raise ValueError("Missing or noninteger Colorado legacy voting statistics")
        level, name = row[:2]
        facts = dict(zip(native_fields, map(count, row[2:]), strict=True))
        if mode_report and sum(facts[key] for key in MODES) != facts["ballots_cast"]:
            raise ValueError("Colorado voting modes do not reconcile")
        if level == "State" and name == "Colorado" and total is None:
            total = {"county": "TOTAL", **facts}
        elif level == "County" and total is not None and name in names and name not in counties:
            county = name
            counties[name], units[name] = {"county": name, **facts}, []
        elif level == "Precinct" and counties and not county_only:
            key = name if precinct_export else (county, name)
            pattern = r"[0-9]{10}" if precinct_export else r"[A-Za-z0-9][A-Za-z0-9 .&'/-]{0,59}"
            if key in ids or not re.fullmatch(pattern, name) or name != name.strip():
                raise ValueError("Unexpected or duplicate Colorado legacy reporting label")
            ids.add(key)
            units[county].append({"precinct": name, **facts})
        else:
            raise ValueError("Unexpected or duplicate Colorado legacy geography")
    if total is None or set(counties) != set(names):
        raise ValueError("Incomplete Colorado legacy county roster")
    state_gap = ballot_gap(total, counties.values(), STATE_BALLOT_GAPS.get(election, 0), "counties to the state control")
    if not county_only:
        for name in names:
            ballot_gap(counties[name], units[name], 0, f"{name} reporting units to the county control")
    note = {
        REGISTRATION_HOLD: "The registration column has a party subheader; counts only.",
        ACTIVE_REGISTRATION_HOLD: "Only active registration is reported; counts only.",
        REGISTRATION_NOT_REPORTED: "The report has voting modes but no registration denominator.",
        None: "Registration and ballot counts come from the same report.",
    }[hold]
    if not county_only and not precinct_export:
        note += " Mixed reporting labels are retained in the complete source query, not treated as precincts."
    if state_gap:
        note += f" Printed statewide ballots exceed the sum of county counts by {state_gap}."

    def published(row):
        return {key: row.get(key) for key in ("county", "ballots_cast", "registered")}

    return {"native_rows": rows, "counties": [published(counties[name]) for name in names],
            "total": published(total), "precincts": units if precinct_export else {},
            "registration_basis": basis, "registration_hold": hold, "report_note": note,
            **({"state_ballot_shortfall": state_gap} if state_gap else {}),
            "extraction_method": "historical_voting_statistics_csv"}


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
    if not 66 <= len(rows) <= 20_000:
        raise ValueError("Unexpected Colorado voting statistics row inventory")
    if election < "2012":
        return legacy_query(rows, election)
    count_only = (election in PARTY_EDITIONS and rows[:2] == [
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
    state_gap = ballot_gap(total, counties.values(), STATE_BALLOT_GAPS.get(election, 0), "counties to the state control")
    county_gaps = {}
    for name in COUNTIES:
        gap = ballot_gap(counties[name], precincts[name], COUNTY_BALLOT_GAPS.get(election, {}).get(name, 0),
                         f"{name} precincts to the county control")
        if gap:
            county_gaps[name] = gap
    note = ("Official Voting Statistics export. The registration column has a party subheader; "
            "counts are shown without registration rates." if count_only else
            "Official Voting Statistics export. Registration includes inactive voters. "
            "Precinct counts are kept in a separate download.")
    if state_gap:
        note += f" Printed statewide ballots exceed the sum of county counts by {state_gap}; the statewide rate is held."
    if county_gaps:
        gaps = ", ".join(f"{name}: {gap}" for name, gap in county_gaps.items())
        note += f" Precinct counts fall short of the printed county controls ({gaps}); affected precinct rates are held."
    return {"native_rows": rows, "counties": [counties[name] for name in COUNTIES], "total": total,
            "precincts": precincts, "registration_basis": None if count_only else REGISTRATION_BASIS,
            "report_note": note,
            **({"state_ballot_shortfall": state_gap} if state_gap else {}),
            **({"county_ballot_shortfalls": county_gaps} if county_gaps else {}),
            "extraction_method": "state_county_precinct_voting_statistics_csv"}
