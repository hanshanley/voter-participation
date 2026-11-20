"""Discover Nebraska county reports and retain explicitly printed ballot totals."""

import io
import re
from datetime import datetime
from html.parser import HTMLParser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import quote

from scripts.nebraska_canvass import COUNTIES
from scripts.results_pdf_archive_ocr import DPI, MINIMUM, heading_key
from scripts.results_pdf_ocr import page_views
from scripts.participation_intake.contract import IntakeError, count, encoded, pin

FEED = "NE-2026-county-election-reports"
CSV = "participation-ne-2026-county-reports.csv"
INDEX = "https://countyelectionresults.nebraska.gov/default.aspx"
ROOT = INDEX.rsplit("/", 1)[0] + "/"
DATE = "2026-11-03"
MAX_BYTES = 16_000_000
STATUSES = {"Official Results": "official", "Unofficial Results": "unofficial"}
STOCK = r"(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)"
CLOCK = r"\d{1,2}/\d{1,2}/2026 \d{1,2}:\d{2} [AP]M"
BALLOT_LINE = re.compile(rf"(?:Ballots Cast - Total ({STOCK})(?: ({STOCK}) ({STOCK}) ({STOCK}))?"
                         rf"|({STOCK})\s*Ballots Cast - Total ({STOCK}) ({STOCK}) ({STOCK}))")
FOOTER = re.compile(rf".*\bElection Summary\s*-\s*({CLOCK})(?: (?:Page )?\d+ of \d+)?", re.I)
SCAN_FOOTER = re.compile(r"^[A-Za-z0-9 ]{3,90}-\s*(\d{1,2}/\d{1,2}/2026)\s*(\d{1,2}:\d{2})\s*([AP]M)$",
                         re.I)
SCAN_PAGE = re.compile(r"(?:Page\s*)?1\s*of\s*\d+", re.I)


def report_url(county, status):
    return ROOT + f"election_files/{quote(county)}/2026_General_{STATUSES[status]}_results.pdf"


def discovery(body):
    class Rows(HTMLParser):
        row, cell = None, None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row, self.cell = [], None
            elif tag == "td" and self.row is not None:
                self.cell = ["", []]
            elif tag == "a" and self.cell is not None:
                self.cell[1].append(dict(attrs).get("href"))

        def handle_data(self, data):
            if self.cell is not None:
                self.cell[0] += data

        def handle_endtag(self, tag):
            if tag == "td" and self.cell is not None:
                self.row.append(self.cell)
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row, self.cell = None, None

    parser = Rows()
    parser.rows = []
    text = body.decode("utf-8-sig")
    if "2026 General Election" not in text:
        raise ValueError("Missing Nebraska county general-election identity")
    parser.feed(text)
    reports = {}
    seen = set()
    for row in parser.rows:
        if len(row) != 3 or (county := row[0][0].strip()) not in COUNTIES:
            continue
        if county in seen:
            raise ValueError(f"Duplicate Nebraska county index row: {county}")
        seen.add(county)
        name, links = row[1]
        status, clock = name.strip(), " ".join(row[2][0].split())
        if (status in STATUSES and len(links) == 1 and isinstance(links[0], str)
                and ROOT + quote(links[0], safe="/%") == report_url(county, status)
                and re.fullmatch(CLOCK, clock)):
            reports[county] = {"url": report_url(county, status), "status": status, "index_clock": clock}
    if not reports:
        raise ValueError("No compatible county report links in the Nebraska index")
    return reports


def query(lines, county, status):
    headers = {"Summary Results Report", f"GN26 {county} County Unofficial Results"}
    county_labels = {county, f"{county} County", f"{county} County, Nebraska"}
    stats = next((i for i, line in enumerate(lines) if line.casefold().startswith("statistics")), None)
    if stats is None or not lines or lines[0] not in headers or "November 3, 2026" not in lines[:stats]:
        raise IntakeError("layout_unqualified", "No reviewed direct ballot-total table")
    preamble = [line for line in lines[1:stats] if line != "November 3, 2026"
                and line.casefold() not in {value.casefold() for value in STATUSES}]
    title_forms = {"General Election", "2026 General Election", "Nebraska Statewide General Election",
                   f"2026 General Election - {county} County", f"NE {county} 261103 General Election_6110"}
    if not preamble or preamble[-1] not in county_labels or any(line not in title_forms for line in preamble[:-1]):
        raise IntakeError("layout_unqualified", "No unambiguous countywide summary identity")
    if [line.casefold() for line in lines[:stats] if line.casefold() in
            {value.casefold() for value in STATUSES}] != [status.casefold()]:
        raise IntakeError("status_conflict", "Report and index disagree on official status")
    records = [(i, match) for i, line in enumerate(lines) if (match := BALLOT_LINE.fullmatch(line))]
    footer = FOOTER.fullmatch(lines[-1])
    if len(records) != 1 or not footer or records[0][0] <= stats:
        raise IntakeError("layout_unqualified", "Missing or ambiguous direct ballot count or report clock")
    end, record = records[0]
    values = record.groups()[:4] if record[1] else record.groups()[4:]
    total, day, early, provisional = (count(v) if v is not None else None for v in values)
    table = " ".join(lines[stats:end]).casefold()
    if not table.startswith("statistics total") or (day is not None and not table.startswith(
            "statistics total election day early voting provision")):
        raise IntakeError("layout_unqualified", "Unreviewed county ballot columns")
    if day is not None and total != day + early + provisional:
        raise IntakeError("ballot_modes_disagree", "Voting-mode components do not equal the reported total")
    report_clock = footer[1]
    if datetime.strptime(report_clock, "%m/%d/%Y %I:%M %p").date().isoformat() < DATE:
        raise IntakeError("report_clock_regressed", "Report clock precedes the election")
    return {"ballots": total, "election_day": day, "early": early, "provisional": provisional,
            "report_clock": report_clock}


def scan_query(evidence, county, status):
    results = []
    confidences = []
    county_key = heading_key(county)
    if len(evidence) != len(DPI):
        raise IntakeError("layout_unqualified", "Two county scan renders are required")
    for view, dpi in zip(evidence, DPI, strict=True):
        receipt, cells = view["receipt"], view["cells"]
        keys = [heading_key(" ".join(row)) for row in cells]
        indices = [i for i, row in enumerate(cells) if row and heading_key(row[0]) == "ballotscasttotal"]
        if (receipt["dpi"] != dpi or receipt["page"] != 1
                or not keys or keys[0] != "summaryresultsreport" + heading_key(status)
                or len(indices) != 1):
            raise IntakeError("layout_unqualified", "Unsupported county scan layout")
        index = indices[0]
        stats = next((i for i, key in enumerate(keys) if key.startswith("statisticstotal")), 0)
        expected = {"november32026" + county_key + ending for ending in ("", "county", "countynebraska")}
        if (not 2 <= stats < index <= 24 or keys[stats - 1] not in expected
                or (stats > 2 and (stats != 3 or keys[1] not in {
                    "generalelection", "2026generalelection", "nebraskastatewidegeneralelection",
                    f"ne{county_key}261103generalelection6110", f"2026generalelection{county_key}county"}))):
            raise IntakeError("layout_unqualified", "County scan does not identify a countywide general-election table")
        layout = "".join(keys[stats:index])
        if not layout.startswith(("statisticstotalelectionearlyprovisionaldayvoting",
                                  "statisticstotalelectiondayearlyvotingprovisional")):
            raise IntakeError("layout_unqualified", "Unreviewed county scan statistics columns")
        values = cells[index][1:]
        high = view["high_confidence"]
        if (len(values) != 4 or len(high) != 4 or any(type(v) is not bool for v in high)
                or not all(re.fullmatch(STOCK, value) for value in values)):
            raise IntakeError("layout_unqualified", "County scan ballot row was not read unambiguously")
        total, day, early, provisional = map(count, values)
        if total != day + early + provisional:
            raise IntakeError("ballot_modes_disagree", "Scanned voting-mode components do not sum to the total")
        footers = [match for row in cells[index + 1:] if len(row) == 2
                   and SCAN_PAGE.fullmatch(row[1])
                   and (match := SCAN_FOOTER.fullmatch(row[0]))]
        if len(footers) != 1:
            raise IntakeError("layout_unqualified", "Missing or ambiguous scanned native report clock")
        date_text, time_text, meridiem = footers[0].groups()
        clock = f"{date_text} {time_text} {meridiem.upper()}"
        if datetime.strptime(clock, "%m/%d/%Y %I:%M %p").date().isoformat() < DATE:
            raise IntakeError("report_clock_regressed", "Scanned report clock precedes the election")
        results.append({"ballots": total, "election_day": day, "early": early,
                        "provisional": provisional, "report_clock": clock})
        confidences.append(high)
    if results[0] != results[1] or not all(a or b for a, b in zip(*confidences, strict=True)):
        raise IntakeError("layout_unqualified", "County scan totals, clock, or confidence did not agree")
    return results[0]


def scan_evidence(views):
    result = []
    for view in views:
        rows = [[cell["text"] for cell in row] for row in view["role_cells"][:36]]
        ballots = [i for i, row in enumerate(rows) if row and heading_key(row[0]) == "ballotscasttotal"]
        if len(ballots) != 1:
            raise IntakeError("layout_unqualified", "No unique scanned ballot total")
        i = ballots[0]
        footers = [row for row in rows[i + 1:] if len(row) == 2 and SCAN_PAGE.fullmatch(row[1])
                   and SCAN_FOOTER.fullmatch(row[0])]
        result.append({"receipt": view["receipt"],
                       "cells": rows[:i + 1] + footers,
                       "high_confidence": [cell["confidence"] >= MINIMUM
                                           for cell in view["role_cells"][i][1:]]})
    return result


def extract(body, county, status):
    from pypdf import PdfReader

    if not 0 < len(body) <= MAX_BYTES or not body.startswith(b"%PDF-"):
        raise IntakeError("layout_unqualified", "Not a bounded county report PDF")
    document = PdfReader(io.BytesIO(body), strict=False)
    if not 1 <= len(document.pages) <= 500:
        raise IntakeError("layout_unqualified", "Unexpected county report page inventory")
    lines = [" ".join(line.split()) for line in document.pages[0].extract_text().splitlines() if line.strip()]
    if not lines:
        try:
            evidence = scan_evidence(page_views(body, strict_role_alignment=True, text_angle_classifier=False))
            return {"scan_evidence": evidence, **scan_query(evidence, county, status)}
        except ValueError as error:
            if isinstance(error, IntakeError):
                raise
            raise IntakeError("layout_unqualified", "Unverified county scan") from error
    # Keep only the statistics heading and fields, never contest rows.
    end = next((i for i, line in enumerate(lines) if FOOTER.fullmatch(line)), None)
    if end is None or end > 45:
        raise IntakeError("layout_unqualified", "No native-text first-page ballot summary")
    lines = lines[:end + 1]
    ballot_lines = [i for i, line in enumerate(lines) if BALLOT_LINE.fullmatch(line)]
    if len(ballot_lines) != 1:
        raise IntakeError("layout_unqualified", "No unique native ballot-total line")
    lines = lines[:ballot_lines[0] + 1] + lines[end:end + 1]
    return {"native_lines": lines, **query(lines, county, status)}


def collect(collector, *, check_unchanged=True):
    from scripts.results_intake import source_error

    prior = ((collector.prior.get(FEED) or {}).get("data") or {}).get("counties", {})
    versions = {}
    for package in ("pypdf", "PyMuPDF", "rapidocr-onnxruntime", "onnxruntime"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    directory = Path(__file__).parent
    parser_pin = pin(encoded({"versions": versions, "code": {
        name: pin((directory / name).read_bytes()) for name in (
            Path(__file__).name, "results_pdf_archive_ocr.py", "results_pdf_ocr.py")}}))["sha256"]

    def parse(index):
        reports = discovery(index)
        counties = {}
        for county in COUNTIES:
            old = prior.get(county, {})
            accepted = old.get("accepted")
            source = reports.get(county)
            if not source:
                counties[county] = {"accepted": accepted, "error": "compatible_report_not_linked"}
                continue
            rejection = old.get("rejection") if old.get("rejection_parser") == parser_pin else None
            prior_report = rejection or ((accepted or {}).get("report") if not old.get("error") else None)
            if not check_unchanged and prior_report and all(prior_report[key] == value for key, value in source.items()):
                counties[county] = old
                continue
            url = source["url"]
            report = None
            try:
                body, _ = collector.acquire(url)
                report = source | pin(body)
                if accepted and accepted["report"] == report:
                    counties[county] = {"accepted": accepted, "error": None}
                    continue
                if rejection == report:
                    counties[county] = old
                    continue
                facts = (accepted["facts"] if accepted and accepted["report"]["sha256"] == report["sha256"]
                         and accepted["report"]["status"] == source["status"]
                         else extract(body, county, source["status"]))
                if accepted and accepted["report"]["status"] == "Official Results" and source["status"] != "Official Results":
                    raise IntakeError("official_status_regressed", "An unofficial edition cannot replace official results")
                if accepted and datetime.strptime(facts["report_clock"], "%m/%d/%Y %I:%M %p") < datetime.strptime(
                        accepted["facts"]["report_clock"], "%m/%d/%Y %I:%M %p"):
                    raise IntakeError("report_clock_regressed", "The report's native clock moved backward")
                counties[county] = {"accepted": {"report": report, "facts": facts}, "error": None}
            except Exception as error:
                counties[county] = {"accepted": accepted, "error": source_error(error)}
                if report and isinstance(error, IntakeError):
                    counties[county]["rejection"] = report
                    counties[county]["rejection_parser"] = parser_pin
            finally:
                with collector.lock:
                    collector.bodies.pop(url, None)
        return {"election_date": DATE, "counties": counties}

    return collector.capture(FEED, INDEX, parse, equivalent=lambda old, new: old == new)


def rows(entries):
    entry = entries.get(FEED) or {}
    if not entry.get("data"):
        return []
    data = entry["data"]
    if (data["election_date"] != DATE or set(data["counties"]) != set(COUNTIES)
            or entry["source"]["url"] != INDEX or entry["status"] not in ("reported", "retained_after_failure")):
        raise ValueError("Invalid Nebraska county report inventory")
    result = []
    for county in COUNTIES:
        item = data["counties"][county]
        accepted = item["accepted"]
        row = {"county": county, "election_date": DATE, "disposition": item["error"] or (
            entry["error"] if entry["status"] == "retained_after_failure" else "reported")}
        if accepted:
            report, facts = accepted["report"], accepted["facts"]
            status = report["status"]
            reproduced = ({"scan_evidence": facts["scan_evidence"], **scan_query(facts["scan_evidence"], county, status)}
                          if "scan_evidence" in facts else
                          {"native_lines": facts["native_lines"], **query(facts["native_lines"], county, status)})
            if (report["url"] != report_url(county, report["status"])
                    or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                    or not 0 < report["bytes"] <= MAX_BYTES
                    or not re.fullmatch(CLOCK, report["index_clock"])
                    or facts != reproduced):
                raise ValueError(f"Invalid Nebraska county ballot evidence: {county}")
            row.update({name: facts[name] for name in ("ballots", "election_day", "early", "provisional", "report_clock")})
            row.update(report_status=STATUSES[report["status"]], source_status="reported"
                       if row["disposition"] == "reported" else "retained_after_failure",
                       source_url=report["url"], source_sha256=report["sha256"],
                       source_bytes=report["bytes"], index_clock=report["index_clock"])
        result.append(row)
    return result
