"""Reconcile Alaska's statewide Voters Cast report to native federal ballot controls."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io
import json
import re

from scripts.participation_intake.contract import count, pin


FEED = "AK-statewide-summary-turnout"
ROOT = "https://www.elections.alaska.gov/enr/26GENR/results/"
URL = ROOT + "statewide.js"
REPORT = ROOT + "ElectionSummaryReportRPT.pdf"
OFFICES = ("U.S. Senator", "U.S. Representative")
STATUS = ("UNOFFICIAL RESULTS", "OFFICIAL RESULTS")
HEADER = re.compile(
    r"Precincts Reported: ([0-9,]+) of ([0-9,]+) \(\s*([0-9.]+%)\s*\) "
    r"Voters Cast: ([0-9,]+) of ([0-9,]+) \(\s*([0-9.]+%)\s*\) "
    r"State of Alaska 2026 GENERAL ELECTION Election Summary Report November 3\s*,\s*2026 "
    r"(UNOFFICIAL RESULTS|OFFICIAL RESULTS)$")
CLOCK = re.compile(r"(\d{2}/\d{2}/2026 \d{1,2}:\d\d:\d\d [AP]M) Page: (\d+) of (\d+)")


def require(condition, detail):
    if not condition:
        raise ValueError(f"Alaska statewide turnout: {detail}")


def controls(body):
    data = json.loads(body)
    require(data["name"] == "Alaska 2026 General Election" and data["format"] == "2024"
            and data["summaryReportUrl"] == REPORT and type(data["certified"]) is bool,
            "election identity or summary pointer changed")
    names = data["contestNames"]
    require(all(names.count(office) == 1 for office in OFFICES), "federal contest identities changed")
    rows = []
    for office in OFFICES:
        row, = [r for r in data["totals"] if r["n"] == names.index(office)]
        rows.append({"office": office, **{k: row[k] for k in ("b", "v", "p", "r")}})
    return {"updated": data["updated"], "certified": data["certified"], "federal_controls": rows}


def parse_report(body):
    from pypdf import PdfReader

    require(body.startswith(b"%PDF-") and body.rstrip().endswith(b"%%EOF"), "incomplete summary PDF")
    report = PdfReader(io.BytesIO(body), strict=True)
    require(not report.is_encrypted and 1 <= len(report.pages) <= 80, "invalid PDF inventory")
    pages = []
    first = None
    for page in report.pages:
        text = " ".join(page.extract_text().split())
        matches = CLOCK.findall(text)
        require(len(matches) == 1, "missing or repeated page ordinal/clock")
        pages.append(list(matches[0]))
        if first is None:
            match = HEADER.search(text)
            require(match is not None, "missing standalone statewide Voters Cast header")
            first = list(match.groups())
    return {"statewide_header": first, "page_clocks_and_ordinals": pages}


def reconcile(pdf, native):
    pages = pdf["page_clocks_and_ordinals"]
    require(isinstance(pages, list) and 1 <= len(pages) <= 80
            and all(page == [pages[0][0], str(i), str(len(pages))]
                    for i, page in enumerate(pages, 1)), "inconsistent report pagination or clock")
    clock = datetime.strptime(pages[0][0], "%m/%d/%Y %I:%M:%S %p")
    update = datetime.strptime(native["updated"], "%m/%d/%Y %I:%M %p")
    require(datetime(2026, 11, 3) <= clock <= update, "report and statewide-feed clocks disagree")
    reported, total, p_pct, voters, registered, fraction, status = pdf["statewide_header"]
    require(all(isinstance(x, str) and re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", x)
                for x in (reported, total, voters, registered))
            and status in STATUS and all(re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}%", x)
                                         for x in (p_pct, fraction)), "invalid statewide source literals")
    reported, total, voters, registered = (count(x.replace(",", "")) for x in
                                           (reported, total, voters, registered))
    require(None not in (reported, total, voters, registered) and 0 < reported <= total
            and 0 < voters <= registered and type(native["certified"]) is bool
            and native["certified"] == (status == STATUS[1]), "invalid counts or inconsistent result status")
    rounded = lambda a, b: f"{(Decimal(a) * 100 / b).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)}%"
    require(rounded(reported, total) == p_pct and rounded(voters, registered) == fraction,
            "printed fractions disagree with the reported counts")
    rows = native["federal_controls"]
    require(tuple(r["office"] for r in rows) == OFFICES and all(
        all(type(row[k]) is int and count(row[k]) == row[k] for k in ("b", "v", "p", "r"))
        and (row["b"], row["v"], row["r"]) == (voters, registered, reported)
        and row["p"] >= row["r"] for row in rows), "federal ballot, register or reporting controls disagree")
    return {"date": clock.isoformat(), "registered": registered, "voters": voters,
            "printed_fraction": fraction, "source_status": status,
            "reported_precincts": reported, "pdf_total_precincts": total,
            "feed_total_precincts": {row["office"]: row["p"] for row in rows}}


def collect(collector):
    def parse(body):
        native = controls(body)
        report, _ = collector.acquire(REPORT)
        require(len(report) <= 4_000_000, "summary PDF exceeds reviewed size bound")
        pdf = parse_report(report)
        result = reconcile(pdf, native)
        prior = (collector.prior.get(FEED) or {}).get("data") or {}
        require(prior.get("reconciliation", {}).get("source_status") != STATUS[1]
                or result["source_status"] == STATUS[1], "official result status regressed")
        return {"date": result["date"], "complete_native_query": {"pdf": pdf, "statewide_feed": native},
                "reconciliation": result, "report": {"url": REPORT, **pin(report)}}

    return collector.capture(FEED, URL, parse)
