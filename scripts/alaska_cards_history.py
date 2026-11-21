"""Reconcile legacy Alaska reporting-unit cards cast to official statewide summaries."""
import io
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser

from scripts.alaska_precinct_history import CENTRAL, MODE_NAMES, OVERSEAS, PRECINCT
from scripts.participation_intake.contract import pin
from scripts.southeast_turnout import collect_report

ELECTIONS = ("2014-11-04", "2016-11-08", "2018-11-06")
ROUTES = {
    f"AK-{date[:4]}-general-cards-cast-archive": (
        date, f"https://www.elections.alaska.gov/results/{date[2:4]}GENR/data/")
    for date in ELECTIONS
}
CSV = "participation-ak-general-cards-cast-archive.csv"
HEADER = "District/Reportunit VGroup1 VGroup2 Ballot Card TS Cast OS Cast"
ROW = re.compile(r"(.+?) TOTAL TOTAL ([0-9]+) ([0-9]+)")
CONTROL = re.compile(
    r"GEMS ELECTION RESULTS ([0-9]{4}) GENERAL ELECTION (November [0-9]+, [0-9]{4}) "
    r"Official Results ([0-9]{2}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) "
    r"Registered Voters ([0-9]+) - Cards Cast ([0-9]+) ([0-9]+\.[0-9]{2})% "
    r"Num\. Report Precinct ([0-9]+) - Num\. Reporting ([0-9]+) 100\.00%(?= |$)"
)


def sources(feed):
    election, root = ROUTES[feed]
    return election, root + "cards.pdf", root + ("results18.htm" if election.startswith("2018") else "results.htm")


class ReportText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.extend(data.split())


def control_line(body):
    if not 0 < len(body) <= 2_000_000:
        raise ValueError("Alaska cards control exceeds size limit")
    parser = ReportText()
    parser.feed(body.decode("windows-1252"))
    parser.close()
    match = CONTROL.match(" ".join(parser.parts))
    if not match:
        raise ValueError("Alaska official statewide Cards Cast control missing")
    return match[0]


def reconcile(election, table, control):
    match = CONTROL.fullmatch(control)
    if not match:
        raise ValueError("Alaska official cards control changed")
    year, raw_date, stamp, reg, cards, rate, precincts, reporting = match.groups()
    register, state_cards, n, reported = map(int, (reg, cards, precincts, reporting))
    edition = datetime.strptime(stamp, "%m/%d/%y %H:%M:%S")
    expected_precincts = 441 + (election != ELECTIONS[0])
    if (year != election[:4] or datetime.strptime(raw_date, "%B %d, %Y").date().isoformat() != election
            or edition.date().isoformat() < election or edition.year != int(year)
            or not 0 < state_cards <= register or n != reported or n != expected_precincts
            or Decimal(rate) != (Decimal(100 * state_cards) / register).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP)):
        raise ValueError("Alaska cards control identity, scope or arithmetic differs")
    if not table or table[-1][0] != "Total":
        raise ValueError("Missing Alaska statewide TS/OS totals")
    totals = [0, 0]
    physical, central = set(), set()
    overseas = []
    for label, ts, os in table[:-1]:
        if any(type(value) is not int or value < 0 for value in (ts, os)):
            raise ValueError("Invalid Alaska cards-cast count")
        totals[0] += ts
        totals[1] += os
        if match := PRECINCT.fullmatch(label):
            if match[1] in physical or not 1 <= int(match[1][:2]) <= 40:
                raise ValueError("Duplicated or invalid Alaska physical precinct")
            physical.add(match[1])
        elif match := CENTRAL.fullmatch(label):
            key = int(match[1]), match[2]
            if key in central:
                raise ValueError("Duplicated Alaska central reporting unit")
            central.add(key)
        elif label == OVERSEAS:
            overseas.append((ts, os))
        else:
            raise ValueError("Unknown Alaska cards reporting scope")
    valid_overseas = (not overseas if election == ELECTIONS[0]
                      else len(overseas) == 2 and sum(overseas[0]) > 0 and overseas[1] == (0, 0))
    if (len(physical) != 441 or central != {(i, mode) for i in range(1, 41) for mode in MODE_NAMES}
            or not valid_overseas or table[-1][1:] != totals or sum(totals) != state_cards):
        raise ValueError("Alaska reporting units do not reconcile to the complete cards controls")
    return edition.isoformat(), state_cards, register


def parse_report(body, election):
    from pypdf import PdfReader

    if not 0 < len(body) <= 4_000_000 or not body.startswith(b"%PDF-"):
        raise ValueError("Alaska cards source is not a bounded PDF")
    pdf = PdfReader(io.BytesIO(body), strict=True)
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 50:
        raise ValueError("Invalid Alaska cards PDF inventory")
    table = []
    expected_header = HEADER + (" E" if election == ELECTIONS[0] else "")
    for i, page in enumerate(pdf.pages):
        lines = [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines()
                 if line.strip()]
        if (not lines or lines[0] != expected_header
                or (i == 0 and lines[1:2] != ["Jurisdiction Wide"])):
            raise ValueError("Alaska cards PDF header changed")
        for line in lines[1:]:
            if "TOTAL TOTAL" not in line:
                continue
            match = ROW.fullmatch(line)
            if not match:
                raise ValueError("Malformed Alaska cards subtotal")
            label, ts, os = match.groups()
            label = label.removesuffix(" - Total").removesuffix(" - To")
            table.append([label, int(ts), int(os)])
    return table


def collect(collector, feed, *, reuse_checked_week=False):
    election, url, control_url = sources(feed)
    old = collector.prior.get(feed) or {}

    def parse(body, _):
        supporting, _ = collector.acquire(control_url)
        control_pin = {"url": control_url, **pin(supporting)}
        previous = old.get("data") or {}
        if old.get("source", {}).get("sha256") == pin(body)["sha256"] and previous.get("control_report") == control_pin:
            reconcile(election, previous["complete_native_query"], previous["native_control"])
            return previous
        control, table = control_line(supporting), parse_report(body, election)
        edition, _, _ = reconcile(election, table, control)
        return {"date": edition, "complete_native_query": table, "native_control": control,
                "control_report": control_pin, "participation_observation_qualified": False}

    return collect_report(collector, feed, url, parse, reuse_checked_week=reuse_checked_week)


def exports(entries):
    for feed in ROUTES:
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None or entry.get("status") not in {"reported", "retained_after_failure"}:
            continue
        election, url, control_url = sources(feed)
        control = data["control_report"]
        if (entry["source"]["url"] != url or control["url"] != control_url
                or not re.fullmatch(r"[a-f0-9]{64}", control.get("sha256", ""))
                or type(control.get("bytes")) is not int or not 0 < control["bytes"] <= 2_000_000):
            raise ValueError("Alaska cards source binding changed")
        table = data["complete_native_query"]
        edition, state_cards, registered = reconcile(election, table, data["native_control"])
        if data["date"] != edition:
            raise ValueError("Alaska cards edition clock changed")
        occurrences = Counter()
        for label, ts, os in table:
            match = PRECINCT.fullmatch(label)
            occurrences[label] += 1
            scope = ("state" if label == "Total" else "physical_precinct" if match
                     else "duplicate_zero_overseas_line" if occurrences[label] == 2 else "central_unallocated")
            yield {
                "state_code": "AK", "election_date": election, "reporting_unit": label,
                "source_unit_id": match[1] if match else "", "unit_scope": scope,
                "source_label_occurrence": occurrences[label], "ts_cast": ts, "os_cast": os, "cards_cast": ts + os,
                "official_statewide_cards_cast": state_cards, "official_statewide_registered": registered,
                "official_control_edition_local": edition, "source_status": entry["status"],
                "checked_week_utc": entry.get("archive_check_week_utc"),
                "source_url": url, "source_sha256": entry["source"]["sha256"],
                "official_control_url": control_url, "official_control_sha256": control["sha256"],
            }
