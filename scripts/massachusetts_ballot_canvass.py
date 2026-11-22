"""Reconcile total ballots including blanks across official MA canvass exports."""

from collections import Counter
import csv
from functools import partial
import io
from pathlib import Path
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
COUNTY_FIPS = {f"25{code:03d}": name for code, name in zip(range(1, 28, 2),
    "Barnstable Berkshire Bristol Dukes Essex Franklin Hampden Hampshire Middlesex Nantucket Norfolk Plymouth Suffolk Worcester".split(),
    strict=True)}
COUNTIES = set(COUNTY_FIPS.values())
CROSSWALK_FEED = "MA-2022-census-county-subdivisions"
CROSSWALK_CSV = "participation-ma-2022-county-rollup.csv"
CROSSWALK_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2022_Gazetteer/2022_gaz_cousubs_25.txt"
CROSSWALK_PIN = {"bytes": 71948, "sha256": "db62cf01ebb90b6577eb99b0f40c357fe3d32fa75bec39ca0f324dc5ca41c135"}
CROSSWALK_ORIGINAL = "data/results-intake/massachusetts-historical-reference/2022_gaz_cousubs_25.txt"
CROSSWALK_MEMBER = "inputs/massachusetts-reference/2022_gaz_cousubs_25.txt"
CROSSWALK_STATUS = "reviewed_historical_reference"
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


def parse_crosswalk(body):
    if pin(body) != CROSSWALK_PIN:
        raise ValueError("Massachusetts Census crosswalk differs from its reviewed edition")
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")), delimiter="\t")
    names, codes = {}, set()
    for row in reader:
        name, geoid = row["NAME"], row["GEOID"]
        if name == "County subdivisions not defined" and geoid.endswith("00000") and row["ALAND"] == "0":
            continue
        match = re.fullmatch(r"(.+?) (?:Town city|town|city)", name)
        if (row["USPS"] != "MA" or not re.fullmatch(r"25\d{8}", geoid) or geoid[:5] not in COUNTY_FIPS
                or not match or match[1].casefold() in names or geoid in codes):
            raise ValueError("Invalid Massachusetts municipality in Census crosswalk")
        names[match[1].casefold()] = [name, geoid]
        codes.add(geoid)
    if len(names) != 351 or {code[:5] for code in codes} != COUNTY_FIPS.keys():
        raise ValueError("Incomplete Massachusetts Census crosswalk")
    return {"municipalities": names, "participation_observation_qualified": False}


def crosswalk_original(root):
    root = Path(root)
    original = root / CROSSWALK_ORIGINAL
    if not original.exists() and root.name == "code":
        original = root.parent / CROSSWALK_MEMBER
    return original.read_bytes()


def collect_crosswalk(collector, *, reuse_checked_week=False):
    body = crosswalk_original(Path(__file__).resolve().parents[1])
    data = parse_crosswalk(body)
    source = {"url": CROSSWALK_URL, **CROSSWALK_PIN}
    with collector.lock:
        collector.attempts.append({"id": CROSSWALK_FEED, "status": CROSSWALK_STATUS, **source})
    return {"status": CROSSWALK_STATUS, "source": source, "data": data, "error": None,
            "first_observed_at": None}


def verify_pinned_crosswalk(entries, body):
    crosswalk = entries.get(CROSSWALK_FEED, {})
    if (crosswalk["source"] != {"url": CROSSWALK_URL, **CROSSWALK_PIN}
            or crosswalk["data"] != parse_crosswalk(body)):
        raise ValueError("Massachusetts pinned reference does not reproduce the accepted crosswalk")


def rollup_exports(entries):
    crosswalk, election = (entries.get(feed) or {} for feed in (CROSSWALK_FEED, FEEDS[2022]))
    if not crosswalk.get("data") or not election.get("data"):
        return
    expected = {"url": CROSSWALK_URL, **CROSSWALK_PIN}
    if (crosswalk["source"] != expected
            or crosswalk["status"] not in ("reported", "retained_after_failure", CROSSWALK_STATUS)
            or election["status"] not in ("reported", "retained_after_failure")):
        raise ValueError("Unreviewed Massachusetts county crosswalk receipt")
    native = crosswalk["data"]["municipalities"]
    counties, units = reconcile(election["data"]["reports"], year=2022)
    towns = Counter()
    for name, _, _, count in units:
        towns[name] += count
    directions = dict(N="North", S="South", E="East", W="West")
    matched, county_counts, municipalities = set(), Counter(), []
    for town, count in sorted(towns.items()):
        key = re.sub(r"^([NSEW])\. ", lambda match: directions[match[1]] + " ", town).casefold()
        if key in matched or key not in native:
            return  # Keep the original county audit when a successor cannot be matched exactly.
        matched.add(key)
        name, geoid = native[key]
        county_counts[geoid[:5]] += count
        municipalities.append(("municipality", town, name, geoid, geoid[:5], count, None))
    if matched != native.keys() or county_counts.keys() != COUNTY_FIPS.keys():
        return
    for scope, name, census_name, geoid, county_fips, ballots, reported in (
            ("statewide", "Massachusetts", "", "", "", sum(county_counts.values()), sum(counties.values())),
            *(("county", county, "", fips, fips, county_counts[fips], counties[county])
              for fips, county in COUNTY_FIPS.items()),
            *municipalities):
        yield {"state_code": "MA", "election_date": "2022-11-08", "geography_level": scope, "name": name,
               "census_name": census_name, "census_geoid": geoid, "county_fips": county_fips,
               "ballots_including_blanks": ballots, "original_county_page_ballots": reported,
               "difference_from_original_county_pages": ballots - reported if reported is not None else None,
               "county_ballot_shortfall": 0,
               "source_status": election["status"], "census_source_status": crosswalk["status"],
               "census_source_url": CROSSWALK_URL, "census_source_sha256": CROSSWALK_PIN["sha256"],
               "rate_hold_reason": "no_registration_denominator_in_paired_canvasses",
               "precinct_geometry_verified": False}


def original_reports(entries):
    crosswalk = entries.get(CROSSWALK_FEED) or {}
    if (data := crosswalk.get("data")) is not None:
        source = crosswalk["source"]
        yield (CROSSWALK_FEED, source, ".txt", CROSSWALK_PIN["bytes"], source == {"url": CROSSWALK_URL, **CROSSWALK_PIN},
               parse_crosswalk, data)
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
