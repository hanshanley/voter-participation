"""Read Kansas's statewide turnout and advance-voting history in one report."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re

from scripts.participation_intake.contract import count
from scripts.southeast_turnout import collect_report


FEED = "KS-1996-2008-statewide-turnout-study"
URL = "https://www.sos.ks.gov/elections/10elec/2010_Future_of_Kansas_Elections_report.pdf"
CSV = "participation-ks-statewide-turnout-study.csv"
MAX_BYTES = 1_000_000
TITLE = "Registration, Turnout and Advance Voting in General Elections"
HEADER = "General Election Year Registration % Advance Votes % of Vote Turnout"
COUNT = r"\d{1,3}(?:,\d{3})*"
ROW = re.compile(rf"(\d{{4}}) ({COUNT}) ({COUNT}) (\d{{1,3}}) ({COUNT}) (\d{{1,3}}\.\d)", re.ASCII)


def rounded_percent(numerator, denominator, digits):
    return (Decimal(numerator) * 100 / denominator).quantize(
        Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def rows(native):
    years = list(range(2008, 1994, -2))
    if len(native) != len(years):
        raise ValueError("Incomplete Kansas study turnout series")
    for year, line in zip(years, native, strict=True):
        match = ROW.fullmatch(line)
        if not match or int(match[1]) != year:
            raise ValueError("Kansas study row or general-election year differs")
        registered, voted, advance = map(count, (match[2], match[3], match[5]))
        if not 0 < voted <= registered or not 0 <= advance <= voted:
            raise ValueError("Kansas study count components do not reconcile")
        if rounded_percent(voted, registered, 0) != Decimal(match[4]):
            raise ValueError("Kansas study turnout percentage disagrees with reported counts")
        advance_matches = rounded_percent(advance, voted, 1) == Decimal(match[6])
        first = date(year, 11, 1)
        election = first + timedelta(days=(7 - first.weekday()) % 7 + 1)
        yield {
            "state_code": "KS", "year": year, "election_date": election.isoformat(),
            "election_type": "presidential" if year % 4 == 0 else "midterm",
            "reported_general_election_turnout": voted, "reported_registration": registered,
            "reported_turnout_percent": match[4],
            "turnout_per_reported_registration": str(
                (Decimal(voted) / registered).quantize(Decimal(".00000001"), rounding=ROUND_HALF_UP)),
            "reported_advance_votes": advance, "reported_advance_share_percent": match[6],
            "advance_share_hold_reason": "" if advance_matches else "printed_advance_share_disagrees",
            "source_line": line,
        }


def parse(body):
    import pymupdf

    if not body.startswith(b"%PDF-") or len(body) > MAX_BYTES:
        raise ValueError("Kansas study is not a bounded PDF")
    with pymupdf.open(stream=body, filetype="pdf") as report:
        if report.needs_pass or not report.permissions & pymupdf.PDF_PERM_COPY or len(report) != 27:
            raise ValueError("Kansas study PDF permissions or inventory differ")
        cover = " ".join(report[0].get_text(sort=True).split())
        if not cover.startswith(
                "Kansas Secretary of State Report of the Study Group on the Future of Elections in Kansas December 2009"):
            raise ValueError("Kansas study publisher or edition differs")
        page = [" ".join(line.split()) for line in report[3].get_text(sort=True).splitlines() if line.strip()]
    if page.count(TITLE) != 1 or page.count(HEADER) != 1 or page.index(HEADER) != page.index(TITLE) + 1:
        raise ValueError("Kansas study turnout headings differ")
    start = page.index(HEADER) + 1
    table = page[start:start + 7]
    if len(page) <= start + 7 or re.match(r"\d{4}\s", page[start + 7]):
        raise ValueError("Kansas study turnout table inventory differs")
    list(rows(table))
    return {"complete_native_query": table, "participation_observation_qualified": False}


def collect(collector, *, reuse_checked_week=False):
    return collect_report(collector, FEED, URL, lambda body, _: parse(body),
                          reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return
    source = entry["source"]
    if (entry["status"] not in {"reported", "retained_after_failure"} or source["url"] != URL
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or type(source["bytes"]) is not int or not 0 < source["bytes"] <= MAX_BYTES):
        raise ValueError("Kansas study source lineage differs")
    for row in rows(data["complete_native_query"]):
        yield {**row, "registration_basis": "Registration in the same statewide study table",
               "report_edition": "2009-12", "source_status": entry["status"], "source_url": URL,
               "source_sha256": source["sha256"], "source_bytes": source["bytes"]}
