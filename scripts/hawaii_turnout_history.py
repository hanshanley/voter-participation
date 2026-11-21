"""Reconcile Hawaii's official general-election participation tables."""
from decimal import Decimal
from html import unescape
import re

from scripts.participation_intake.contract import count
from scripts.southeast_turnout import collect_report


FEED = "HI-general-election-county-turnout-history"
URL = "https://elections.hawaii.gov/resources/registration-voter-turnout-statistics/"
CSV = "participation-hi-general-election-county-turnout.csv"
MAX_BYTES = 2_000_000
AREAS = ("Statewide", "County of Hawaii", "County of Maui", "County of Kauai", "City & County of Honolulu")
HEADER = ("Year", "Registered Voters", "Voter Turnout", "Turnout %")


def rows(tables, last_year):
    years = ["1959", *map(str, range(1960, last_year + 1, 2))]
    if not 2024 <= last_year <= 2100 or last_year % 2:
        raise ValueError("Unreviewed Hawaii general-election range")
    if list(tables) != list(AREAS) or any(
            [row[0] for row in table] != years for table in tables.values()):
        raise ValueError("Incomplete Hawaii general-election area or year roster")
    for group in zip(*tables.values(), strict=True):
        counts = []
        for year, registered, turnout, percentage in group:
            if not re.fullmatch(r"\d{1,3}\.\d%", percentage):
                raise ValueError("Invalid Hawaii published turnout percentage")
            registered, turnout = count(registered), count(turnout)
            if not 0 < turnout <= registered:
                raise ValueError("Invalid Hawaii turnout or registration count")
            rate = 100 * Decimal(turnout) / registered
            holds = [] if abs(rate - Decimal(percentage[:-1])) <= Decimal(".05") else [
                "printed_turnout_percent_disagrees"]
            counts.append((registered, turnout, percentage, rate, holds))
        state_register, state_turnout = counts[0][:2]
        register_gap = state_register - sum(r[0] for r in counts[1:])
        turnout_gap = state_turnout - sum(r[1] for r in counts[1:])
        if register_gap or turnout_gap:
            counts[0][-1].append("county_totals_do_not_reconcile")
        for area, (registered, turnout, percentage, rate, holds) in zip(AREAS, counts, strict=True):
            yield {"state_code": "HI", "year": int(year), "geography": area,
                   "geography_level": "state" if area == "Statewide" else "county_reporting_area",
                   "reported_voter_turnout": turnout, "reported_registered_voters": registered,
                   "reported_turnout_percent": percentage,
                   "qualified_turnout_percent": None if holds else str(rate.quantize(Decimal(".000001"))),
                   "rate_hold_reason": ";".join(holds),
                   "state_minus_county_turnout": turnout_gap if area == "Statewide" else None,
                   "state_minus_county_registration": register_gap if area == "Statewide" else None}


def parse(body):
    from scripts.results_turnout_history import html_tables

    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Hawaii turnout page exceeds reviewed bounds")
    html = body.decode("utf-8-sig")
    section = list(re.finditer(r"<h4>General Elections \(1959-(20\d{2})\)</h4>", html))
    if len(section) != 1:
        raise ValueError("Missing or repeated Hawaii general-election section")
    last_year = int(section[0][1])
    remainder = html[section[0].end():]
    source = re.split(r"<h4>", remainder, maxsplit=1)[0]
    heading = r'<span class="ac_title_class">\s*([^<>]+?)\s*</span>'
    parts = re.split(heading, source)
    if len(parts) != 11 or html_tables(parts[0].encode()):
        raise ValueError("Unexpected Hawaii general-election panel inventory")
    tables = {}
    for label, panel in zip(parts[1::2], parts[2::2], strict=True):
        label = " ".join(unescape(label).split())
        parsed = html_tables(panel.encode())
        if label in tables or len(parsed) != 1 or parsed[0][0] != HEADER:
            raise ValueError("Hawaii general-election panel label or columns differ")
        tables[label] = [list(row) for row in parsed[0][1:]]
    list(rows(tables, last_year))
    return {"first_year": 1959, "last_year": last_year,
            "complete_native_query": [[area, table] for area, table in tables.items()],
            "participation_observation_qualified": False}


def collect(collector, *, reuse_checked_week=False):
    def checked(body, _):
        data = parse(body)
        prior = (collector.prior.get(FEED) or {}).get("data") or {}
        if data["last_year"] < prior.get("last_year", 1959):
            raise ValueError("Hawaii turnout archive year range regressed")
        return data

    return collect_report(collector, FEED, URL, checked,
                          reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    source = entry["source"]
    if (entry["status"] not in {"reported", "retained_after_failure"} or source["url"] != URL
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or type(source["bytes"]) is not int or not 0 < source["bytes"] <= MAX_BYTES):
        raise ValueError("Hawaii turnout source lineage differs")
    for row in rows(dict(data["complete_native_query"]), data["last_year"]):
        yield {**row, "registration_basis": "Registration in the same Office of Elections table",
               "source_status": entry["status"], "source_url": URL, "source_sha256": source["sha256"],
               "source_bytes": source["bytes"]}
