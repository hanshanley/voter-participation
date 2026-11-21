"""Reconcile total ballots including blanks across official MA canvass exports."""

from collections import Counter
import csv
from functools import partial
import io
import re

from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_turnout_history import archive_link, html_tables
from scripts.southeast_turnout import collect_report


FEED = "MA-2026-paired-canvass-ballot-counts"
CSV = "participation-ma-2026-paired-canvass-ballot-counts.csv"
BASE = "https://electionstats.state.ma.us/elections/"
CONTESTS = {"173530": ("Secretary of the Commonwealth", 2), "173526": ("Governor", 3)}
COUNTIES = set("Barnstable Berkshire Bristol Dukes Essex Franklin Hampden Hampshire Middlesex Nantucket Norfolk Plymouth Suffolk Worcester".split())
LIMIT = 2_000_000
TAIL = ("All Others", "Blanks", "Total Votes Cast")


def number(text):
    if not re.fullmatch(r"0|[1-9]\d{0,8}|[1-9]\d{0,2}(?:,\d{3}){1,2}", text):
        raise ValueError("Invalid Massachusetts canvass count")
    return int(text.replace(",", ""))


def checked_counts(values):
    counts = list(map(number, values))
    if sum(counts[:-1]) != counts[-1]:
        raise ValueError("Massachusetts canvass total differs from its ballot columns")
    return counts


def page(body, *, contest):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Massachusetts canvass page exceeds bounds")
    office, candidates = CONTESTS[contest]
    if not re.search(r"<h1>\s*2026 " + re.escape(office) + r" General Election\s*</h1>", body.decode("utf-8-sig")):
        raise ValueError("Massachusetts canvass election identity changed")
    url = BASE + f"download/{contest}/precincts_include:1/"
    if archive_link(body, BASE, re.escape(url), label="Precinct Results") != url:
        raise IntakeError("report_not_linked", "Massachusetts precinct export not linked")
    tables = [t for t in html_tables(body) if t and t[0][0] == "County" and t[0][-3:] == TAIL]
    if len(tables) != 1:
        raise ValueError("No unique Massachusetts county table")
    header, *rows, total = tables[0]
    if len(header) != candidates + 4 or len(rows) != len(COUNTIES) or total[0] != "Totals":
        raise ValueError("Incomplete Massachusetts county table")
    counties, columns = {}, [0] * (len(header) - 1)
    for name, *values in rows:
        county = name.removesuffix(" More »")
        if county not in COUNTIES or county in counties or len(values) != len(columns):
            raise ValueError("Invalid or repeated Massachusetts county")
        counts = checked_counts(values)
        counties[county] = counts[-1]
        columns = [a + b for a, b in zip(columns, counts, strict=True)]
    if checked_counts(total[1:]) != columns:
        raise ValueError("Massachusetts counties do not reconcile to the state control")
    return {"csv_url": url, "counties": counties, "columns_total": columns}


def precincts(body, *, contest):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Massachusetts precinct export exceeds bounds")
    _, candidates = CONTESTS[contest]
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    header, parties = tuple(next(reader, ())), next(reader, ())
    if (header[:3] != ("City/Town", "Ward", "Pct") or header[-3:] != TAIL
            or len(header) != candidates + 6 or parties[:3] != ["", "", ""]
            or len(parties) != candidates + 3 or not all(parties[3:])):
        raise ValueError("Massachusetts precinct export schema changed")
    values, totals = {}, None
    columns = [0] * (len(header) - 3)
    for row in reader:
        if len(row) != len(header) or totals is not None:
            raise ValueError("Malformed or trailing Massachusetts precinct row")
        town, ward, precinct = row[:3]
        counts = checked_counts(row[3:])
        if town == "TOTALS" and not ward and not precinct:
            totals = counts
            continue
        key = town, ward, precinct
        if (not town or town.strip() != town or len(town) > 60 or key in values
                or not (re.fullmatch(r"-|\d{1,3}", ward) or town == "Lawrence" and ward in "ABCDEF" and len(ward) == 1)
                or not re.fullmatch(r"[A-Za-z0-9]{1,8}", precinct)):
            raise ValueError("Invalid or repeated Massachusetts reporting unit")
        values[key] = counts[-1]
        columns = [a + b for a, b in zip(columns, counts, strict=True)]
    if len({key[0] for key in values}) != 351 or totals != columns:
        raise ValueError("Massachusetts reporting units do not reconcile to the export control")
    return {"units": [[*key, value] for key, value in sorted(values.items())], "columns_total": columns}


def reconcile(reports):
    a, b = [reports[key] for key in CONTESTS]
    for report in (a, b):
        if report["page"]["columns_total"] != report["csv"]["columns_total"]:
            raise ValueError("Massachusetts pages and exports disagree")
    if a["page"]["counties"] != b["page"]["counties"] or a["csv"]["units"] != b["csv"]["units"]:
        raise ValueError("Massachusetts canvasses disagree on all-ballot reporting counts")
    return a["page"]["counties"], a["csv"]["units"]


def collect(collector, *, reuse_checked_week=False):
    first = next(iter(CONTESTS))

    def checked(body, _):
        reports = {}
        for contest in CONTESTS:
            url = BASE + f"view/{contest}/"
            original = body if contest == first else collector.acquire(url)[0]
            control = page(original, contest=contest)
            raw, _ = collector.acquire(control["csv_url"])
            reports[contest] = {
                "page": control, "csv": precincts(raw, contest=contest),
                "page_source": {"url": url, **pin(original)},
                "csv_source": {"url": control["csv_url"], **pin(raw)},
            }
        reconcile(reports)
        prior = (collector.prior.get(FEED) or {}).get("data") or {}
        if prior and all((report["page"], report["csv"]) == (
                prior["reports"][contest]["page"], prior["reports"][contest]["csv"])
                for contest, report in reports.items()):
            return prior
        return {"reports": reports, "participation_observation_qualified": False}

    return collect_report(collector, FEED, BASE + f"view/{first}/", checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    if entry["status"] not in ("reported", "retained_after_failure"):
        raise ValueError("Invalid Massachusetts canvass status")
    reports = data["reports"]
    counties, units = reconcile(reports)
    sources = {}
    for contest, (office, _) in CONTESTS.items():
        report = reports[contest]
        for role, url in (("page", BASE + f"view/{contest}/"),
                          ("csv", BASE + f"download/{contest}/precincts_include:1/")):
            source = report[role + "_source"]
            if source["url"] != url or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"]):
                raise ValueError("Massachusetts canvass original provenance changed")
            sources.update({f"{office.split()[0].lower()}_{role}_{key}": source[key] for key in ("url", "sha256")})
    municipalities = Counter()
    for name, _, _, count in units:
        municipalities[name] += count
    common = {"state_code": "MA", "election_date": "2026-11-03", "source_status": entry["status"],
              "rate_hold_reason": "no_registration_denominator_in_paired_canvasses",
              "precinct_geometry_verified": False, **sources}
    for scope, rows in (
            ("statewide", [("Massachusetts", "", "", sum(counties.values()))]),
            ("county", [(name, "", "", count) for name, count in sorted(counties.items())]),
            ("municipality", [(name, "", "", count) for name, count in sorted(municipalities.items())]),
            ("reporting_unit", units)):
        for name, ward, precinct, count in rows:
            yield {**common, "geography_level": scope, "name": name, "native_ward": ward,
                   "native_precinct": precinct, "ballots_including_blanks": count}


def original_reports(entries):
    if (data := (entries.get(FEED) or {}).get("data")) is None:
        return
    for contest, report in data["reports"].items():
        for role, suffix, parser, route in (
                ("page", ".html", page, f"view/{contest}/"),
                ("csv", ".csv", precincts, f"download/{contest}/precincts_include:1/")):
            source = report[role + "_source"]
            yield (f"{FEED}-{contest}-{role}", source, suffix, LIMIT, source["url"] == BASE + route,
                   partial(parser, contest=contest), report[role])
