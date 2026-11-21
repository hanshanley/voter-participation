"""Reconcile Idaho's historical statewide series and 2024 bulk turnout workbook."""
from collections import defaultdict
from decimal import Decimal
from functools import partial
from io import BytesIO
import math
import re
import zipfile

from scripts.participation_intake.contract import IntakeError, federal_general, pin
from scripts.results_turnout_history import archive_link, html_tables
from scripts.southeast_turnout import collect_report


FEED = "ID-general-election-turnout-history"
INDEX = "https://voteidaho.gov/election-results/"
STATE_CSV = "participation-id-statewide-general-turnout.csv"
LOCAL_CSV = "participation-id-2024-native-turnout-workbook.csv"
BOOK = "https://archive.sos.idaho.gov/elections/data/results/2024/raw_stats_general.xlsx"
MAX_BYTES = 2_000_000
HISTORY_HEADER = ("Year", "Voting Age Pop.", "Registered Voters", "Ballots Cast",
                  "% of Registered", "% of Voting Age Pop.")
WORKBOOK_HEADER = ("County", "Precinct", "Registration at Cutoff", "Election Day Registrations",
                   "Total Registered Voters", "Ballots Cast", "Voter Turnout")
COUNTIES = set(("Ada;Adams;Bannock;Bear Lake;Benewah;Bingham;Blaine;Boise;Bonner;Bonneville;"
                "Boundary;Butte;Camas;Canyon;Caribou;Cassia;Clark;Clearwater;Custer;Elmore;"
                "Franklin;Fremont;Gem;Gooding;Idaho;Jefferson;Jerome;Kootenai;Latah;Lemhi;"
                "Lewis;Lincoln;Madison;Minidoka;Nez Perce;Oneida;Owyhee;Payette;Power;"
                "Shoshone;Teton;Twin Falls;Valley;Washington").split(";"))


def parse_number(value):
    if not re.fullmatch(r"[1-9][0-9]{0,2}(?:,[0-9]{3})*", value):
        raise ValueError("Invalid Idaho statewide count")
    return int(value.replace(",", ""))


def statewide_rows(literals):
    years = []
    for year, pop, registered, ballots, reg_pct, vap_pct in literals:
        years.append(int(year))
        p, r, b = map(parse_number, (pop, registered, ballots))
        rates = {}
        for label, denominator, literal in (("registered", r, reg_pct), ("vap", p, vap_pct)):
            if not re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,2}\s?%", literal):
                raise ValueError("Invalid Idaho statewide turnout percentage")
            printed = Decimal(literal.strip("% "))
            actual = 100 * Decimal(b) / denominator
            rounded_delta = abs(printed - actual)
            rate = denominator >= b and rounded_delta <= Decimal(".5").scaleb(printed.as_tuple().exponent)
            rates.update({f"{label}_printed_pct": literal,
                          f"{label}_reconciled_pct": float(actual) if rate else None,
                          f"{label}_rate_hold": "" if rate else "printed_rate_or_denominator_disagrees"})
        yield {"election_date": federal_general(int(year)).isoformat(), "ballots_cast": b,
               "registered_voters": r, "source_reported_voting_age_population": p, **rates}
    if not years or years[0] < 2024 or years[0] > 2100 or years != list(range(years[0], 1979, -2)):
        raise ValueError("Incomplete Idaho statewide general-election history")


def index(body):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Unexpected Idaho index size")
    html = body.decode("utf-8-sig")
    sections = re.findall(r">General Elections \(1980-20[0-9]{2}\)</h3>(.*?)>Primary Elections \(1980-20[0-9]{2}\)</h3>",
                          html, re.S)
    if len(sections) != 1:
        raise ValueError("Unknown Idaho general-election history section")
    tables = [t for t in html_tables(sections[0].encode()) if t and t[0] == HISTORY_HEADER]
    if len(tables) != 1:
        raise ValueError("No unique Idaho statewide general-election table")
    literals = []
    for row in tables[0][1:]:
        if len(row) == 1 and re.match(r"(General by county:|County Breakdowns:)", row[0]):
            continue
        if len(row) != 6 or not re.fullmatch(r"[0-9]{4}", row[0]):
            raise ValueError("Invalid Idaho general-election history row")
        literals.append(list(row))
    list(statewide_rows(literals))
    general = re.findall(r">General Election - November 5, 2024</h4>(.*?)<h4\b", html, re.S)
    if len(general) != 1 or archive_link(general[0].encode(), INDEX, re.escape(BOOK),
                                        label=r"Data for turnout") != BOOK:
        raise IntakeError("report_not_linked", "Idaho 2024 general turnout workbook not linked")
    return literals


def workbook(body):
    from openpyxl import load_workbook

    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Unexpected Idaho workbook size")
    with zipfile.ZipFile(BytesIO(body)) as z:
        if sum(i.file_size for i in z.infolist()) > 10_000_000:
            raise ValueError("Idaho workbook expansion exceeds bounds")
    book = load_workbook(BytesIO(body), read_only=True, data_only=True)
    try:
        if book.sheetnames != ["raw_stats"]:
            raise ValueError("Idaho workbook sheet inventory changed")
        sheet = book["raw_stats"]
        if sheet.max_column != len(WORKBOOK_HEADER) or not 1 < sheet.max_row <= 10_000:
            raise ValueError("Idaho workbook bounds differ")
        values = iter(sheet.values)
        if next(values, None) != WORKBOOK_HEADER:
            raise ValueError("Idaho workbook column roles changed")
        return [list(row) for row in values]
    finally:
        book.close()


def local_rows(native, control):
    counties, parents, seen, pooled_counties = defaultdict(list), {}, set(), set()
    observations = []
    for ordinal, (county, label, cutoff, day, registered, ballots, rate) in enumerate(native, 2):
        if not isinstance(county, str) or not county.endswith(" County") or county[:-7] not in COUNTIES:
            raise ValueError("Unknown Idaho county")
        if not (type(label) is int and label >= 0 or isinstance(label, str) and label.strip() and len(label) <= 120):
            raise ValueError("Invalid Idaho native reporting label")
        county, label = county[:-7], str(label).strip()
        identity = county, label
        if (identity in seen or any(type(n) is not int or n < 0 for n in (cutoff, day, registered, ballots))
                or cutoff + day != registered or rate is not None
                and (type(rate) not in (int, float) or not math.isfinite(rate))):
            raise ValueError("Invalid or duplicate Idaho workbook row")
        seen.add(identity)
        counts = cutoff, day, registered, ballots
        is_county = label == "Total"
        if is_county:
            parents[county] = counts
        else:
            counties[county].append(counts)
        pooled = bool(re.search(r"\b(?:absentee|abs)\b", label, re.I))
        if pooled and ballots:
            pooled_counties.add(county)
        held = ("pooled_absentee_reporting_unit" if pooled else "no_registration" if not registered
                else "missing_or_incompatible_printed_rate" if ballots > registered or rate is None
                or not math.isclose(rate, ballots / registered, rel_tol=0, abs_tol=1e-12) else "")
        observations.append({"county": county, "native_label": label, "source_row": ordinal,
               "geography_level": "county" if is_county else "native_reporting_unit",
               "registration_at_cutoff": cutoff, "election_day_registrations": day,
               "registered_voters": registered, "ballots_cast": ballots, "source_printed_fraction": rate,
               "reconciled_pct": 100 * ballots / registered if not held else None,
               "rate_hold": held, "election_day_precinct_geometry_verified": False})
    if set(parents) != COUNTIES or set(counties) != COUNTIES:
        raise ValueError("Incomplete Idaho county workbook roster")
    for county, totals in parents.items():
        if tuple(sum(row[i] for row in counties[county]) for i in range(4)) != totals:
            raise ValueError("Idaho reporting units differ from county control: " + county)
    if tuple(sum(row[i] for row in parents.values()) for i in (2, 3)) != (
            control["registered_voters"], control["ballots_cast"]):
        raise ValueError("Idaho county roll-up differs from statewide control")
    for row in observations:
        if (row["geography_level"] == "native_reporting_unit" and row["county"] in pooled_counties
                and not row["rate_hold"]):
            row.update(reconciled_pct=None, rate_hold="county_has_separately_reported_absentee_ballots")
        yield row


def collect(collector, *, reuse_checked_week=False):
    def checked(body, _):
        state = index(body)
        if federal_general(int(state[0][0])) > collector.observation_time().date():
            raise ValueError("Idaho general-election history is future-dated")
        previous = (collector.prior.get(FEED) or {}).get("data") or {}
        if previous and int(state[0][0]) < int(previous["state"][0][0]):
            raise ValueError("Idaho statewide history regressed")
        raw, _ = collector.acquire(BOOK)
        report = {"url": BOOK, **pin(raw)}
        if previous.get("report") == report and previous["state"] == state:
            return previous
        native = previous["local"] if previous.get("report") == report else workbook(raw)
        control = next(row for row in statewide_rows(state) if row["election_date"] == "2024-11-05")
        list(local_rows(native, control))
        return {"report": report, "state": state, "local": native,
                "participation_observation_qualified": False}

    return collect_report(collector, FEED, INDEX, checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return [], []
    sources = {"state": entry["source"], "local": data["report"]}
    if entry["status"] not in ("reported", "retained_after_failure"):
        raise ValueError("Unexpected Idaho source status")
    for key, url in (("state", INDEX), ("local", BOOK)):
        source = sources[key]
        if (source["url"] != url or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
                or type(source["bytes"]) is not int or not 0 < source["bytes"] <= MAX_BYTES):
            raise ValueError("Changed Idaho turnout provenance")

    def stamp(key, rows):
        return [{"state_code": "ID", "source_status": entry["status"], "source_url": sources[key]["url"],
                 "source_sha256": sources[key]["sha256"], **row} for row in rows]

    state = stamp("state", statewide_rows(data["state"]))
    control = next(row for row in state if row["election_date"] == "2024-11-05")
    return state, stamp("local", ({"election_date": control["election_date"], **row}
                                  for row in local_rows(data["local"], control)))


def original_reports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is not None:
        source, report = entry["source"], data["report"]
        yield FEED + "-index", source, ".html", MAX_BYTES, source["url"] == INDEX, index, data["state"]
        yield FEED + "-workbook", report, ".xlsx", MAX_BYTES, report["url"] == BOOK, workbook, data["local"]
