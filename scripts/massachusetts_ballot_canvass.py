"""Reconcile total ballots including blanks across official MA canvass exports."""

from collections import Counter
import csv
from functools import partial
import io
import re

from scripts.participation_intake.contract import IntakeError, federal_general, pin
from scripts.results_turnout_history import archive_link, html_tables
from scripts.southeast_turnout import collect_report


FEED = "MA-2026-paired-canvass-ballot-counts"
CSV = "participation-ma-2026-paired-canvass-ballot-counts.csv"
BASE = "https://electionstats.state.ma.us/elections/"
CONTESTS = {"173530": ("Secretary of the Commonwealth", 2), "173526": ("Governor", 3)}
PAIRS = {
    2020: {"140751": ("President", 4), "140755": ("U.S. Senate", 3)},
    2022: {"154341": ("Secretary of the Commonwealth", 3), "154338": ("Governor", 3)},
    2024: {"165300": ("President", 8), "165304": ("U.S. Senate", 2)},
    2026: CONTESTS,
}
FEEDS = {year: f"MA-{year}-paired-canvass-ballot-counts" for year in PAIRS}
HISTORY_CSV = "participation-ma-2020-2024-paired-canvass-ballot-counts.csv"
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


def page(body, *, contest, year=2026):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Massachusetts canvass page exceeds bounds")
    office, candidates = PAIRS[year][contest]
    if not re.search(rf"<h1>\s*{year} " + re.escape(office) + r" General Election\s*</h1>", body.decode("utf-8-sig")):
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
    counties, columns, component_gaps = {}, [0] * (len(header) - 1), {}
    for name, *values in rows:
        county = name.removesuffix(" More »")
        if county not in COUNTIES or county in counties or len(values) != len(columns):
            raise ValueError("Invalid or repeated Massachusetts county")
        counts = list(map(number, values))
        if gap := counts[-1] - sum(counts[:-1]):
            component_gaps[county] = gap
        counties[county] = counts[-1]
        columns = [a + b for a, b in zip(columns, counts, strict=True)]
    declared = checked_counts(total[1:])
    statewide_gaps = [printed - summed for printed, summed in zip(declared, columns, strict=True)]
    if year >= 2024 and (component_gaps or any(statewide_gaps)):
        raise ValueError("Massachusetts counties do not reconcile to the state control")
    if (year == 2020 and statewide_gaps[-1]) or statewide_gaps[-1] < 0:
        raise ValueError("Massachusetts county ballot totals do not reconcile to the state control")
    return {"csv_url": url, "counties": counties, "columns_total": declared,
            **({"county_row_ballot_minus_components": component_gaps,
                "state_columns_minus_county_sum": dict(zip(header[1:], statewide_gaps, strict=True))}
               if year < 2026 else {})}


def precincts(body, *, contest, year=2026):
    if not 0 < len(body) <= LIMIT:
        raise ValueError("Massachusetts precinct export exceeds bounds")
    _, candidates = PAIRS[year][contest]
    reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    header, parties = tuple(next(reader, ())), next(reader, ())
    if (header[:3] != ("City/Town", "Ward", "Pct") or header[-3:] != TAIL
            or len(header) != candidates + 6 or parties[:3] != ["", "", ""]
            or len(parties) != candidates + 3 or not all(parties[3:])):
        raise ValueError("Massachusetts precinct export schema changed")
    values, totals, municipality_only, detailed = {}, None, set(), set()
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
        native_unit = (bool(re.fullmatch(r"-|\d{1,3}", ward) or town == "Lawrence" and ward in tuple("ABCDEF"))
                       and bool(re.fullmatch(r"[A-Za-z0-9]{1,8}", precinct)))
        aggregate = year == 2022 and not ward and not precinct
        if (not town or town.strip() != town or len(town) > 60 or key in values or not (native_unit or aggregate)):
            raise ValueError("Invalid or repeated Massachusetts reporting unit")
        (municipality_only if aggregate else detailed).add(town)
        values[key] = counts[-1]
        columns = [a + b for a, b in zip(columns, counts, strict=True)]
    if municipality_only & detailed or len(municipality_only | detailed) != 351 or totals != columns:
        raise ValueError("Massachusetts reporting units do not reconcile to the export control")
    return {"units": [[*key, value] for key, value in sorted(values.items())], "columns_total": columns}


def reconcile(reports, *, year=2026):
    pair = PAIRS[year]
    if reports.keys() != pair.keys():
        raise ValueError("Massachusetts canvass pair differs from the reviewed election")
    a, b = [reports[key] for key in pair]
    for report in (a, b):
        if report["page"]["columns_total"] != report["csv"]["columns_total"]:
            raise ValueError("Massachusetts pages and exports disagree")
    if a["page"]["counties"] != b["page"]["counties"] or a["csv"]["units"] != b["csv"]["units"]:
        raise ValueError("Massachusetts canvasses disagree on all-ballot reporting counts")
    return a["page"]["counties"], a["csv"]["units"]


def collect(collector, *, year=2026, reuse_checked_week=False):
    first = next(iter(PAIRS[year]))
    feed = FEEDS[year]

    def checked(body, _):
        reports = {}
        for contest in PAIRS[year]:
            url = BASE + f"view/{contest}/"
            original = body if contest == first else collector.acquire(url)[0]
            control = page(original, contest=contest, year=year)
            raw, _ = collector.acquire(control["csv_url"])
            reports[contest] = {
                "page": control, "csv": precincts(raw, contest=contest, year=year),
                "page_source": {"url": url, **pin(original)},
                "csv_source": {"url": control["csv_url"], **pin(raw)},
            }
        reconcile(reports, year=year)
        prior = (collector.prior.get(feed) or {}).get("data") or {}
        if prior and all((report["page"], report["csv"]) == (
                prior["reports"][contest]["page"], prior["reports"][contest]["csv"])
                for contest, report in reports.items()):
            return prior
        return {"reports": reports, "participation_observation_qualified": False}

    return collect_report(collector, feed, BASE + f"view/{first}/", checked, reuse_checked_week=reuse_checked_week)


def exports(entries, *, year=2026):
    entry = entries.get(FEEDS[year]) or {}
    if (data := entry.get("data")) is None:
        return
    if entry["status"] not in ("reported", "retained_after_failure"):
        raise ValueError("Invalid Massachusetts canvass status")
    reports = data["reports"]
    counties, units = reconcile(reports, year=year)
    sources = {}
    for i, (contest, (office, _)) in enumerate(PAIRS[year].items(), 1):
        prefix = office.split()[0].lower() if year == 2026 else f"source_{i}"
        if year != 2026:
            sources[prefix + "_office"] = office
        report = reports[contest]
        for role, url in (("page", BASE + f"view/{contest}/"),
                          ("csv", BASE + f"download/{contest}/precincts_include:1/")):
            source = report[role + "_source"]
            if source["url"] != url or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"]):
                raise ValueError("Massachusetts canvass original provenance changed")
            sources.update({f"{prefix}_{role}_{key}": source[key] for key in ("url", "sha256")})
    statewide = reports[next(iter(PAIRS[year]))]["csv"]["columns_total"][-1]
    county_gap = statewide - sum(counties.values())
    municipalities = Counter()
    for name, _, _, count in units:
        municipalities[name] += count
    common = {"state_code": "MA", "election_date": federal_general(year).isoformat(), "source_status": entry["status"],
              "rate_hold_reason": "no_registration_denominator_in_paired_canvasses",
              "precinct_geometry_verified": False, **sources}
    if year != 2026:
        common["county_ballot_shortfall"] = county_gap
    for scope, rows in (
            ("statewide", [("Massachusetts", "", "", statewide)]),
            ("county", [(name, "", "", count) for name, count in sorted(counties.items())]),
            ("municipality", [(name, "", "", count) for name, count in sorted(municipalities.items())]),
            ("reporting_unit", [row for row in units if row[2]]),
            ("municipality_only_source_row", [row for row in units if not row[2]])):
        for name, ward, precinct, count in rows:
            yield {**common, "geography_level": "county_page_with_statewide_shortfall"
                   if scope == "county" and county_gap else scope, "name": name, "native_ward": ward,
                   "native_precinct": precinct, "ballots_including_blanks": count}


def history_exports(entries):
    for year in (2020, 2022, 2024):
        yield from exports(entries, year=year)


def original_reports(entries):
    for year, feed in FEEDS.items():
        if (data := (entries.get(feed) or {}).get("data")) is None:
            continue
        for contest, report in data["reports"].items():
            for role, suffix, parser, route in (
                    ("page", ".html", page, f"view/{contest}/"),
                    ("csv", ".csv", precincts, f"download/{contest}/precincts_include:1/")):
                source = report[role + "_source"]
                yield (f"{feed}-{contest}-{role}", source, suffix, LIMIT, source["url"] == BASE + route,
                       partial(parser, contest=contest, year=year), report[role])
