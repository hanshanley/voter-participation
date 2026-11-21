"""Extract Connecticut's digital general-election town participation archive."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from html.parser import HTMLParser
import io
import re
from urllib.parse import urljoin, urlsplit

from scripts.participation_intake.contract import IntakeError, pin

INDEX = ("https://portal.ct.gov/sots/election-services/election-day-voter-registration-turnout-and-absentee-ballot-"
         "stats-pdfs/election-day-registration-turnout-and-absentee-ballot-statistics-1998--current?archived=true")
DATES = dict(zip(range(1998, 2010, 2), (
    "1998-11-03", "2000-11-07", "2002-11-05", "2004-11-02", "2006-11-07", "2008-11-04",
)))
FEEDS = {f"CT-{year}-general-town-turnout-archive": year for year in DATES}
CSV = "participation-ct-general-town-turnout-archive.csv"
ROSTER = "c661188e0b7bfdc977cfd16eb6208554acabd36e2ff5bb997b5c39e751b67f5d"
NUMBER = r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
ROW = re.compile(rf"([A-Za-z .'-]+?)( \(part\))? ({NUMBER}|6\.395) ({NUMBER}|7,l90) "
                 rf"([0-9]{{1,3}}\.[0-9]{{2,3}}%?) ({NUMBER}) ({NUMBER}) ({NUMBER})")
STATE = {"Total", "Totals", "Statewide Totals"}
SPLIT = {"Durham", "Glastonbury", "Middletown", "Torrington"}
MALFORMED = {(1998, "Southbury", 1, "7,l90"), (2004, "Griswold", 0, "6.395")}


class ReportLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.urls.append(urljoin(INDEX, href))


def valid_link(url, year):
    p = urlsplit(url)
    return (p.scheme == "https" and p.netloc == "portal.ct.gov" and not p.fragment
            and p.path.lower() == f"/-/media/sots/electionservices/elecdaystats_pdfs/regturnoutabsentee{year}pdf.pdf"
            and (not p.query or re.fullmatch(r"rev=[a-f0-9]{32}&hash=[A-Fa-f0-9]{32}", p.query)))


def discover(body, year):
    if not 0 < len(body) <= 1_000_000:
        raise ValueError("Connecticut archive index exceeds bounds")
    parser = ReportLinks()
    parser.feed(body.decode("utf-8-sig"))
    parser.close()
    urls = {url for url in parser.urls if valid_link(url, year)}
    if not urls:
        raise IntakeError("report_not_linked", "Connecticut town turnout report not linked")
    if len(urls) != 1:
        raise ValueError("Connecticut archive has ambiguous report links")
    return urls.pop()


def documented_rows(pages, year):
    election = datetime.strptime(DATES[year], "%Y-%m-%d")
    date = f"November {election.day}, {year}"
    rows = []
    for i, page in enumerate(pages, start=1):
        if (f"Page {i} of {len(pages)} From the {year} Edition of the Connecticut State Register and Manual"
                not in " ".join(page.split())):
            raise ValueError("Connecticut report pagination or vintage changed")
        if "BY TOWN" not in page:
            continue
        upper = " ".join(page.split()).replace("*", "").replace("Offical", "Official")
        if not (all(x in upper for x in (date, "ELECTION DAY REGISTRATION, TURNOUT AND",
                                         "Names on Official Check List (Active)", "Number Checked as Having Voted",
                                         "Absentee Ballots Received from Town Clerk",
                                         "Absentee Ballots Rejected", "Absentee Ballots Voted"))):
            raise ValueError("Connecticut turnout table scope changed")
        page = re.sub(r"\b((?:North|South|West|East|Windsor|Statewide|Glastonbury)) *\n *(?=\S)", r"\1 ", page)
        for line in page.splitlines():
            literal = " ".join(line.split())
            if ROW.fullmatch(literal):
                rows.append(literal)
    return rows


def qualified(lines, year):
    rows = []
    for line in lines:
        match = ROW.fullmatch(line)
        if not match:
            raise ValueError("Unrecognized Connecticut numerical row")
        name, part, reg, voted, rate, received, rejected, cast = match.groups()
        nums = [reg, voted, received, rejected, cast]
        for i, value in enumerate(nums):
            if not re.fullmatch(NUMBER, value) and (year, name, i, value) not in MALFORMED:
                raise ValueError("Unknown Connecticut malformed number")
        values = [int(value.replace(",", "")) if re.fullmatch(NUMBER, value) else None for value in nums]
        n, v, *_ = values
        if n is not None and v is not None and not 0 <= v <= n:
            raise ValueError("Connecticut turnout exceeds printed checklist")
        rows.append((name, bool(part), values, rate, line))
    if not rows or rows[-1][0] not in STATE or rows[-1][1] or None in rows[-1][2]:
        raise ValueError("Missing Connecticut statewide control")
    counts = Counter(row[0] for row in rows[:-1])
    expected_split = SPLIT if year == 2008 else set()
    if (hashlib.sha256("\n".join(sorted(counts)).encode()).hexdigest() != ROSTER
            or any(count != 1 + (name in expected_split) for name, count in counts.items())
            or any(part != (name in expected_split) for name, part, *_ in rows[:-1])):
        raise ValueError("Connecticut town or split-component roster changed")
    deltas = [None if any(r[2][i] is None for r in rows[:-1])
              else sum(r[2][i] for r in rows[:-1]) - rows[-1][2][i] for i in range(5)]
    return rows, deltas


def parse(body, year):
    from pypdf import PdfReader
    from pypdf.constants import UserAccessPermissions

    if not body.startswith(b"%PDF-") or len(body) > 2_000_000:
        raise ValueError("Connecticut town statistics source is not a bounded PDF")
    report = PdfReader(io.BytesIO(body), strict=False)
    if report.is_encrypted and not (report.user_access_permissions & UserAccessPermissions.EXTRACT):
        raise ValueError("Connecticut turnout PDF does not permit extraction")
    if not 1 <= len(report.pages) <= 16:
        raise ValueError("Unrecognized Connecticut turnout PDF pagination")
    lines = documented_rows([page.extract_text() for page in report.pages], year)
    qualified(lines, year)
    return {"complete_native_query": lines, "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    year = FEEDS[feed]
    old = collector.prior.get(feed) or {}
    day = collector.now.astimezone(timezone.utc).date()
    week = (day - timedelta(days=day.weekday())).isoformat()
    if (reuse_checked_week and not collector.offline and old.get("archive_check_week_utc") == week
            and old.get("status") == "reported" and old.get("data") is not None):
        return old

    def read_report(index):
        url = discover(index, year)
        body, _ = collector.acquire(url)
        receipt = {"url": url, **pin(body)}
        previous = old.get("data") or {}
        return previous if previous.get("report") == receipt else {"report": receipt, **parse(body, year)}

    entry = collector.capture(feed, INDEX, read_report, shared_acquisition=True, equivalent=lambda a, b: a == b)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def exports(entries):
    for feed, year in FEEDS.items():
        entry = entries.get(feed, {})
        data = entry.get("data")
        if not data or entry.get("status") not in {"reported", "retained_after_failure"}:
            continue
        report = data["report"]
        if (entry["source"]["url"] != INDEX or not valid_link(report["url"], year)
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                or not 0 < report["bytes"] <= 2_000_000):
            raise ValueError("Connecticut turnout source lineage changed")
        rows, deltas = qualified(data["complete_native_query"], year)
        seen = Counter()
        for name, part, values, rate, literal in rows:
            seen[name] += 1
            state = name in STATE
            n, voted, received, rejected, cast = values
            computed = Decimal(voted) / n if n and voted is not None else None
            reason = ("malformed_count" if computed is None else
                      "town_counts_do_not_reconcile" if state and any(delta != 0 for delta in deltas[:2]) else
                      "printed_percentage_differs" if Decimal(rate.rstrip("%")) !=
                      (computed * 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) else None)
            yield {
                "state_code": "CT", "election_date": DATES[year], "geography_level": (
                    "state" if state else "town_part" if part else "town"),
                "reporting_unit": name, "source_unit_occurrence": seen[name],
                "active_checklist": n, "checked_as_voted": voted, "source_reported_percent": rate,
                "checked_as_voted_fraction": f"{computed:.8f}" if reason is None else None,
                "rate_hold_reason": reason, "absentee_received": received, "absentee_rejected": rejected,
                "absentee_voted": cast, "absentee_accounting_difference": received - rejected - cast,
                "town_minus_state_checklist": deltas[0] if state else None,
                "town_minus_state_checked_as_voted": deltas[1] if state else None,
                "native_row": literal, "source_status": entry["status"], "source_url": report["url"],
                "source_sha256": report["sha256"], "checked_week_utc": entry.get("archive_check_week_utc"),
            }
