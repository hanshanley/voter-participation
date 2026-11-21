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
STATEMENT_INDEX = ("https://portal.ct.gov/SOTS/Election-Services/Statement-Of-Vote-PDFs/"
                   "General-Elections-Statement-of-Vote-1922")
DATES = dict(zip(range(1998, 2010, 2), (
    "1998-11-03", "2000-11-07", "2002-11-05", "2004-11-02", "2006-11-07", "2008-11-04",
)))
STATEMENTS = {
    2010: ("2010-11-02", "2010sovpdf.pdf", 3, 5),
    2012: ("2012-11-06", "2012statementofvotebookpdf.pdf", 3, 5),
    2014: ("2014-11-04", "2014sovpdf.pdf", 3, 5),
    2020: ("2020-11-03", "2020-sov.pdf", 6, 6),
    2022: ("2022-11-08", "sov_2022.pdf", 6, 9),
    2024: ("2024-11-05", "2024_statement_of_vote.pdf", 9, 6),
}
DATES.update({year: profile[0] for year, profile in STATEMENTS.items()})
FEEDS = {f"CT-{year}-general-town-turnout-archive": year for year in DATES}
CSV = "participation-ct-general-town-turnout-archive.csv"
ROSTER = "c661188e0b7bfdc977cfd16eb6208554acabd36e2ff5bb997b5c39e751b67f5d"
NUMBER = r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
ROW = re.compile(rf"([A-Za-z .'-]+?)( \(part\))? ({NUMBER}|6\.395) ({NUMBER}|7,l90) "
                 rf"([0-9]{{1,3}}\.[0-9]{{2,3}}%?) ({NUMBER}) ({NUMBER}) ({NUMBER})")
STATE = {"Total", "Totals", "Statewide Totals"}
SPLIT = {"Durham", "Glastonbury", "Middletown", "Torrington"}
STATEMENT_SPLIT = {"Glastonbury", "Middletown", "Shelton", "Torrington", "Waterbury"}
# The 2020 table does not list these two towns, even though its own subtotals reconcile.
PARTIAL_TOWNS = {2020: {"New Canaan", "North Branford"}}
STATEMENT_LIMIT = 12_000_000
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
    path = (f"/-/media/sots/electionservices/statementofvote_pdfs/{STATEMENTS[year][1]}" if year in STATEMENTS
            else f"/-/media/sots/electionservices/elecdaystats_pdfs/regturnoutabsentee{year}pdf.pdf")
    return (p.scheme == "https" and p.netloc == "portal.ct.gov" and not p.fragment
            and p.path.lower() == path
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


def statement_rows(lines, year):
    profile = STATEMENTS[year]
    columns = profile[2]
    pattern = re.compile(rf"(?:(.+?) )?({NUMBER}) ({NUMBER}) (\d{{1,3}}\.\d{{2}}%)((?: {NUMBER}){{{columns}}})")
    rows = []
    for line in lines:
        if not (match := pattern.fullmatch(line)):
            raise ValueError("Unrecognized Connecticut Statement of Vote row")
        name, registered, voted, rate, rest = match.groups()
        if name is None and year != 2024:
            raise ValueError("Unexpected unlabeled Connecticut row")
        if (name, year) in {("Statewide", 2010), ("Statewide", 2012), ("Statewide", 2014),
                            ("Statewide Total", 2020), ("Statewide Totals", 2022), (None, 2024)}:
            name = "Statewide Totals"
        elif name == "New Millford" and year <= 2014:
            name = "New Milford"
        elif year in (2012, 2014):
            name = re.sub(r" (?:CD [1-5]|\([1-5](?:st|nd|rd|th) CD\))$", "", name)
        values = [int(value.replace(",", "")) for value in (registered, voted, *rest.split())]
        if values[1] > values[0] or Decimal(rate.rstrip("%")) > 100:
            raise ValueError("Connecticut Statement turnout exceeds checklist")
        rows.append((name, values, rate, line))
    if not rows or rows[-1][0] != "Statewide Totals" or any(row[0] in STATE for row in rows[:-1]):
        raise ValueError("Missing or repeated Connecticut statewide original")
    counts = Counter(row[0] for row in rows[:-1])
    absent = PARTIAL_TOWNS.get(year, set())
    split = (STATEMENT_SPLIT | {"Durham"} if year == 2010 else STATEMENT_SPLIT if year <= 2014 else set())
    if (hashlib.sha256("\n".join(sorted(counts.keys() | absent)).encode()).hexdigest() != ROSTER
            or any(count != 1 + (name in split) for name, count in counts.items())):
        raise ValueError("Connecticut Statement town or split-component roster changed")
    deltas = [sum(row[1][i] for row in rows[:-1]) - rows[-1][1][i] for i in range(2)]
    return [(name, name in split, values, rate, literal) for name, values, rate, literal in rows], deltas


def physical_text(page, pymupdf):
    axes = Counter()
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", ()):
            axes[tuple(round(c) for c in line["dir"])] += sum(len(s["text"]) for s in line["spans"])
    if not axes:
        return []
    a, b = axes.most_common(1)[0][0]
    if abs(a) + abs(b) != 1:
        raise ValueError("Unsupported Connecticut turnout table rotation")
    words = sorted((-b * (x0 + x1) / 2 + a * (y0 + y1) / 2,
                    a * (x0 + x1) / 2 + b * (y0 + y1) / 2, word)
                   for x0, y0, x1, y1, word, *_ in page.get_text("words"))
    lines = []
    for y, x, word in words:
        if not lines or y - lines[-1][0] > 2.5:
            lines.append((y, []))
        lines[-1][1].append((x, word))
    return [" ".join(word for _, word in sorted(cells)) for _, cells in lines]


def statement_query(body, year):
    import pymupdf

    if not body.startswith(b"%PDF-") or len(body) > STATEMENT_LIMIT:
        raise ValueError("Connecticut Statement of Vote exceeds PDF bounds")
    wanted = ("samedayregistrationsdrturnoutabsenteeearlyvotingballotstatistics" if year == 2024
              else "electiondayregistrationturnoutandabsenteeballotstatistics")
    compact = lambda value: re.sub(r"[^a-z0-9]", "", value.lower())
    with pymupdf.open(stream=body, filetype="pdf") as report:
        if report.needs_pass or not report.permissions & pymupdf.PDF_PERM_COPY or not 1 <= len(report) <= 300:
            raise ValueError("Connecticut Statement PDF does not permit bounded extraction")
        start = None
        pages = []
        expected = STATEMENTS[year][3]
        for i in range(max(0, len(report) - 48), len(report)):
            if start is not None and i >= start + expected:
                break
            lines = physical_text(report[i], pymupdf)
            if start is None:
                headings = compact(" ".join(lines[:16]))
                if (wanted not in headings or "official" not in headings or "absentee" not in headings
                        or "town" not in headings or "percentage" not in headings or "havingvoted" not in headings):
                    continue
                start = i
                if year <= 2014 and datetime.fromisoformat(DATES[year]).strftime("%m/%d/%Y") not in lines[0]:
                    raise ValueError("Connecticut turnout table election date disagrees")
                if year in (2022, 2024):
                    cover_date = datetime.fromisoformat(DATES[year])
                    title = compact(report[0].get_text())
                    if ("stateofconnecticut" not in title or "statementofvotegeneralelection" not in title
                            or f"november{cover_date.day}{year}" not in title):
                        raise ValueError("Connecticut Statement cover election date disagrees")
                if year == 2020 and "2020connecticutcandidatesforelectorsofpresident" not in compact(report[2].get_text()):
                    raise ValueError("Connecticut Statement table of contents does not identify this election")
            page_rows = [line for line in lines if re.search(r"\d\.\d{2}%", line)]
            if not page_rows:
                raise ValueError("Missing Connecticut Statement table page")
            pages.append(page_rows)
        if len(pages) != expected:
            raise ValueError("Incomplete Connecticut Statement turnout section")
    rows = [line for page in pages for line in page]
    statement_rows(rows, year)
    return {"complete_native_query": rows, "participation_observation_qualified": False}


def parse(body, year):
    if year in STATEMENTS:
        return statement_query(body, year)
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

    index = STATEMENT_INDEX if year in STATEMENTS else INDEX
    entry = collector.capture(feed, index, read_report, shared_acquisition=True, equivalent=lambda a, b: a == b)
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
        statement = year in STATEMENTS
        if (entry["source"]["url"] != (STATEMENT_INDEX if statement else INDEX) or not valid_link(report["url"], year)
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                or not 0 < report["bytes"] <= (STATEMENT_LIMIT if statement else 2_000_000)):
            raise ValueError("Connecticut turnout source lineage changed")
        rows, deltas = (statement_rows if statement else qualified)(data["complete_native_query"], year)
        missing_towns = PARTIAL_TOWNS.get(year, set()) - {row[0] for row in rows}
        seen = Counter()
        for name, part, values, rate, literal in rows:
            seen[name] += 1
            state = name in STATE
            n, voted, received, rejected, cast, *other_modes = values
            computed = Decimal(voted) / n if n and voted is not None else None
            reason = ("malformed_count" if computed is None else
                      "incomplete_town_inventory" if state and missing_towns else
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
                **(dict(zip(
                    ("early_received", "early_rejected", "early_voted", "sdr_received", "sdr_rejected", "sdr_voted")
                    if year == 2024 else ("edr_received", "edr_rejected", "edr_voted"), other_modes))
                   if other_modes else {}),
            }
