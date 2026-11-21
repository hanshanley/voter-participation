"""Reconcile South Carolina's bulk voting-statistics tables to its statewide series."""

from collections import defaultdict
import csv
from io import BytesIO, TextIOWrapper
import json
import re
from urllib.parse import urlencode

from scripts import southeast_turnout as controls
from scripts.participation_intake.contract import IntakeError, federal_general, pin


FEED = "SC-general-county-precinct-voting-statistics"
CSV = "participation-sc-county-precinct-voting-statistics.csv"
AUDIT = "participation-sc-voting-statistics-reconciliation.csv"
BASE = "https://sc.elstats3.civera.com/api/"
CATALOG = BASE + "download_search.csv?" + urlencode({"search": json.dumps({
    "global": {"events": []}, "voterStats": True, "stages": [], "specialElectionsOnly": False,
}, separators=(",", ":"))})
CATALOG_LIMIT = 80_000_000
TABLE_LIMIT = 500_000
YEARS = tuple(range(2008, 2027, 2))
REVIEWED = {2008, 2010, 2012, 2020, 2022, 2024}
COUNTIES = (
    "Abbeville Aiken Allendale Anderson Bamberg Barnwell Beaufort Berkeley Calhoun Charleston Cherokee Chester "
    "Chesterfield Clarendon Colleton Darlington Dillon Dorchester Edgefield Fairfield Florence Georgetown Greenville "
    "Greenwood Hampton Horry Jasper Kershaw Lancaster Laurens Lee Lexington Marion Marlboro McCormick Newberry Oconee "
    "Orangeburg Pickens Richland Saluda Spartanburg Sumter Union Williamsburg York"
).split()
CATALOG_COLUMNS = (
    "contest_id election_id election_date election_type primary_party question_text question_type office_id "
    "office_name office_modifier district_id district_type district_name candidate_id candidate_name "
    "retention_candidate_id retention_candidate_name division_id division_type division_name vote_channel is_winner "
    "number_seats candidate_party_id candidate_party_name votes"
).split()


def table_url(contest):
    if not re.fullmatch(r"[1-9][0-9]{0,8}", contest):
        raise ValueError("Invalid South Carolina voter-statistics identifier")
    return BASE + f"download_contest/{contest}_table.csv?split_party=false"


def catalog(body):
    if not 0 < len(body) <= CATALOG_LIMIT:
        raise ValueError("South Carolina voting-statistics catalog exceeds bounds")
    dates = {f"{federal_general(year).isoformat()}T00:00:00Z": year for year in YEARS}
    selections = defaultdict(set)
    contest_dates = {}
    with TextIOWrapper(BytesIO(body), encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != CATALOG_COLUMNS:
            raise ValueError("Unexpected South Carolina voting-statistics catalog columns")
        for row in reader:
            if len(row) != len(CATALOG_COLUMNS) or row[8] != "Voting Statistics":
                raise ValueError("Unexpected South Carolina voting-statistics catalog row")
            contest, event, date, stage = row[:4]
            year = dates.get(date)
            if (year is None or stage != "General" or row[10:13] != ["1", "State", "South Carolina"]
                    or row[14] != "Total Ballots Cast" or row[18] != "County"):
                continue
            table_url(contest)
            if not re.fullmatch(r"[1-9][0-9]{0,8}", event):
                raise ValueError("Invalid South Carolina event identifier")
            if contest_dates.setdefault(contest, (year, event)) != (year, event):
                raise ValueError("Mixed South Carolina contest identity")
            selections[year, event, contest].add(row[19])
    return [{"year": year, "event": event, "contest": contest, "counties": sorted(counties)}
            for (year, event, contest), counties in sorted(selections.items())]


def table(body):
    if not 0 < len(body) <= TABLE_LIMIT:
        raise ValueError("South Carolina voting-statistics table exceeds bounds")
    reader = csv.reader(TextIOWrapper(BytesIO(body), encoding="utf-8-sig", newline=""), strict=True)
    if next(reader, None) != ["", "", "Total Ballots Cast", "Registered Voters"] or next(reader, None) != [""] * 4:
        raise ValueError("Expected South Carolina ballot and registration columns")
    rows = []
    for row in reader:
        if (len(row) != 4 or row[0] not in ("State", "County", "Precinct")
                or not row[1].strip() or row[1] != row[1].strip()
                or any(not re.fullmatch(r"[0-9]{1,9}", n) for n in row[2:])):
            raise ValueError("Invalid South Carolina voting-statistics table row")
        rows.append([*row[:2], int(row[2]), int(row[3])])
    rows_by_scope(rows)
    return rows


def rows_by_scope(rows):
    if not rows or rows[0][:2] != ["State", "South Carolina"]:
        raise ValueError("Missing statewide voting-statistics control")
    divisions, parent = {}, None
    for ordinal, (level, name, ballots, registration) in enumerate(rows):
        if any(type(n) is not int or n < 0 for n in (ballots, registration)):
            raise ValueError("Invalid retained South Carolina voter-statistics count")
        if ordinal == 0:
            continue
        if level == "County" and name not in divisions:
            parent = name
            divisions[parent] = ((ballots, registration), [])
        elif level == "Precinct" and parent is not None:
            divisions[parent][1].append((ordinal, name, ballots, registration))
        else:
            raise ValueError("Invalid South Carolina county/precinct inventory")
    if set(divisions) != set(COUNTIES):
        raise ValueError("Incomplete South Carolina county inventory")
    for totals, units in divisions.values():
        if not units or totals != tuple(sum(row[i] for row in units) for i in (2, 3)):
            raise ValueError("South Carolina native units do not sum to county controls")
    if rows[0][2:] != [sum(totals[i] for totals, _ in divisions.values()) for i in (0, 1)]:
        raise ValueError("South Carolina counties do not sum to the statewide table control")
    return divisions


def decisions(candidates, previous):
    selected, audit = {}, []
    for year in YEARS:
        matches = [r for r in candidates if r["year"] == year]
        full = [r for r in matches if r["counties"] == COUNTIES]
        if len(full) == 1:
            selected[year] = full[0]
        elif year in REVIEWED or str(year) in previous:
            raise IntakeError("report_catalog_changed", "A previously supported statewide South Carolina table is no longer unique")
        audit.append({
            "election_date": federal_general(year).isoformat(),
            "status": "reported" if year in selected else ("ambiguous_statewide_tables" if full else "no_statewide_table"),
            "native_candidate_contests": ";".join(r["contest"] for r in matches),
            "complete_46_county_contest": full[0]["contest"] if year in selected else "",
        })
    return selected, audit


def collect(collector, feed, *, reuse_checked_week=False):
    def checked(body, _):
        prior = (collector.prior.get(feed) or {}).get("data") or {}
        catalog_pin = pin(body)
        candidates = prior["candidates"] if prior.get("catalog_pin") == catalog_pin else catalog(body)
        selected, _ = decisions(candidates, prior.get("reports", {}))
        control_url = controls.URLS[controls.SC]
        control_body, _ = collector.acquire(control_url)
        control_pin = {"url": control_url, **pin(control_body)}
        control = (prior["control"] if prior.get("control_pin") == control_pin
                   else controls.parse(control_body, controls.SC)["complete_native_query"])
        reports = {}
        for year, item in selected.items():
            url = table_url(item["contest"])
            raw, _ = collector.acquire(url)
            source = {"url": url, **pin(raw)}
            old = prior.get("reports", {}).get(str(year), {})
            facts = old["rows"] if old.get("source") == source else table(raw)
            reports[str(year)] = {"source": source, "rows": facts}
        data = {"catalog_pin": catalog_pin, "candidates": candidates, "control_pin": control_pin, "control": control,
                "reports": reports, "participation_observation_qualified": False}
        exports({feed: {"status": "reported", "data": data}})
        return data

    return controls.collect_report(collector, feed, CATALOG, checked, reuse_checked_week=reuse_checked_week,
                                   shared_acquisition=True)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return [], []
    selected, audit = decisions(data["candidates"], data["reports"])
    if set(data["reports"]) != {str(year) for year in selected}:
        raise ValueError("Incomplete retained South Carolina voting-statistics tables")
    control = {row["year"]: row for row in data["control"]}
    output = []
    for row in audit:
        year = int(row["election_date"][:4])
        report = data["reports"].get(str(year))
        row["source_status"] = entry["status"]
        row["summary_reported_ballots"] = control[year]["reported_participation"]
        row["summary_reported_registration"] = control[year]["reported_registered"]
        row["catalog_source_url"] = CATALOG
        row["catalog_sha256"] = data["catalog_pin"]["sha256"]
        if report is None:
            continue
        if report["source"]["url"] != table_url(selected[year]["contest"]):
            raise ValueError("Retained South Carolina source identity differs from catalog")
        original = report["rows"]
        divisions = rows_by_scope(original)
        if control[year]["numerator_basis"] != "ballots_cast" or row["summary_reported_ballots"] != original[0][2]:
            raise ValueError("South Carolina voting-statistics ballots differ from the official statewide control")
        row["detailed_reported_ballots"], row["detailed_reported_registration"] = original[0][2:]
        row["registration_difference"] = original[0][3] - row["summary_reported_registration"]
        row["table_source_url"] = report["source"]["url"]
        row["table_sha256"] = report["source"]["sha256"]
        row["control_source_url"] = data["control_pin"]["url"]
        row["control_sha256"] = data["control_pin"]["sha256"]
        provenance = {
            "state_code": "SC", "election_date": row["election_date"], "source_status": entry["status"],
            "source_url": report["source"]["url"], "source_sha256": report["source"]["sha256"],
            "rate_hold_reason": "different_registration_totals_between_official_sources" if row["registration_difference"]
            else "local_registration_scope_not_independently_verified",
        }

        def append(level, county, name, index, ballots, registered):
            output.append({**provenance, "geography_level": level, "county": county, "native_name": name,
                           "source_row_ordinal": index, "reported_ballots_cast": ballots,
                           "source_labeled_registered_voters": registered, "qualified_rate_pct": None,
                           "geometry_hold_reason": "native_reporting_unit_not_verified_as_election_day_precinct"
                           if level == "reporting_unit" else None})

        append("state", None, "South Carolina", None, *original[0][2:])
        for county, (counts, units) in divisions.items():
            append("county", county, county, None, *counts)
            for index, name, ballots, registered in units:
                append("reporting_unit", county, name, index, ballots, registered)
    return output, audit
