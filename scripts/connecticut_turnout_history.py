"""Extract Connecticut's general-election town participation archive."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from scripts import results_pdf_archive_ocr as scan
from scripts.participation_intake.contract import IntakeError, pin

INDEX = ("https://portal.ct.gov/sots/election-services/election-day-voter-registration-turnout-and-absentee-ballot-"
         "stats-pdfs/election-day-registration-turnout-and-absentee-ballot-statistics-1998--current?archived=true")
STATEMENT_INDEX = ("https://portal.ct.gov/SOTS/Election-Services/Statement-Of-Vote-PDFs/"
                   "General-Elections-Statement-of-Vote-1922")
PRESS_INDEX = "https://portal.ct.gov/SOTS/Press-Releases/Previous-Years/2016-Press-Releases"
DATES = dict(zip(range(1998, 2010, 2), (
    "1998-11-03", "2000-11-07", "2002-11-05", "2004-11-02", "2006-11-07", "2008-11-04",
)))
STATEMENTS = {
    2010: ("2010-11-02", "2010sovpdf.pdf", 3, 5),
    2012: ("2012-11-06", "2012statementofvotebookpdf.pdf", 3, 5),
    2014: ("2014-11-04", "2014sovpdf.pdf", 3, 5),
    2016: ("2016-11-08", "turnout11082016novemberpresidentialelectionpdf.pdf", 6, 10),
    2018: ("2018-11-06", "2018-sov.pdf", 6, 10),
    2020: ("2020-11-03", "2020-sov.pdf", 6, 6),
    2022: ("2022-11-08", "sov_2022.pdf", 6, 9),
    2024: ("2024-11-05", "2024_statement_of_vote.pdf", 9, 6),
    2026: ("2026-11-03", None, 9, None),
}
SDR_YEARS = (2024, 2026)
SDR_HEADER_SHA256 = "1418b3380caae1fcd19b507505389f7d7a3317ad05d0add43e488fe4650fcf98"
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
PARTIAL_TOWNS = {2018: {"East Granby", "Torrington"}, 2020: {"New Canaan", "North Branford"}}
STATEMENT_LIMIT = 12_000_000
SCAN_LIMIT = 20_000_000
SCAN_FIRST = 171
SCAN_CHECKPOINT = "connecticut_2018_verified_scan.json"
SCAN_BANDS = ((80, 139), (140, 185), (185, 235), (235, 282), (285, 329),
              (330, 379), (380, 425), (426, 468), (469, 504), (505, 560))
SCAN_NAMES = {"Brookdyn": "Brooklyn", "Brookyn": "Brooklyn", "Burling ton": "Burlington",
              "Frankin": "Franklin", "Harford": "Hartford", "Kilingly": "Killingly",
              "Kilingworth": "Killingworth", "Kiling worth": "Killingworth", "Montille": "Montville",
              "Stoning ton": "Stonington", "StatewideTotal": "Statewide Totals"}
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
    if p.scheme != "https" or p.netloc != "portal.ct.gov" or p.fragment or (
            p.query and not re.fullmatch(r"rev=[a-f0-9]{32}&hash=[A-Fa-f0-9]{32}", p.query)):
        return False
    if year == 2026:
        return re.fullmatch(r"/-/media/sots/electionservices/statementofvote_pdfs/[^/]*2026[^/]*\.pdf",
                            p.path.lower()) is not None
    if year == 2016:
        path = f"/-/media/sots/releases/2016/{STATEMENTS[year][1]}"
    elif year in STATEMENTS:
        path = f"/-/media/sots/electionservices/statementofvote_pdfs/{STATEMENTS[year][1]}"
    else:
        path = f"/-/media/sots/electionservices/elecdaystats_pdfs/regturnoutabsentee{year}pdf.pdf"
    return p.path.lower() == path


def discover(body, year):
    if not 0 < len(body) <= 1_000_000:
        raise ValueError("Connecticut archive index exceeds bounds")
    if year == 2026:
        from scripts import national_turnout_release_watch as watch

        links = watch.discover(body, watch.CT)["complete_native_query"]["links"]
        if not links:
            raise IntakeError("report_not_linked", "Connecticut town turnout report not linked")
        return links[0]["url"]
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
    pct = r"(?: (\d{1,3}\.\d{2}%))?" if year == 2016 else r" (\d{1,3}\.\d{2}%)"
    mode_cell = rf"-?{NUMBER}" if year == 2016 else NUMBER
    pattern = re.compile(rf"(?:(.+?) )?({NUMBER}) ({NUMBER}){pct}((?: {mode_cell}){{{columns}}})")
    rows = []
    for line in lines:
        if not (match := pattern.fullmatch(line)):
            raise ValueError("Unrecognized Connecticut Statement of Vote row")
        name, registered, voted, rate, rest = match.groups()
        if name is None and year not in SDR_YEARS:
            raise ValueError("Unexpected unlabeled Connecticut row")
        if (name, year) in {("Statewide", 2010), ("Statewide", 2012), ("Statewide", 2014), ("Statewide", 2016),
                            ("Statewide Total", 2020), ("Statewide Totals", 2022)} or (
                                year in SDR_YEARS and name in (None, "Statewide Total", "Statewide Totals")):
            name = "Statewide Totals"
        elif name == "New Millford" and year <= 2016:
            name = "New Milford"
        elif year in (2012, 2014):
            name = re.sub(r" (?:CD [1-5]|\([1-5](?:st|nd|rd|th) CD\))$", "", name)
        values = [int(value.replace(",", "")) for value in (registered, voted, *rest.split())]
        negative = [(i, n) for i, n in enumerate(values) if n < 0]
        if negative and (year != 2016 or name != "Kent" or negative != [(4, -2)]):
            raise ValueError("Unexpected Connecticut negative ballot-mode cell")
        if rate is None and (year != 2016 or name != "Statewide Totals"):
            raise ValueError("Missing Connecticut printed turnout percentage")
        if values[1] > values[0] or (rate is not None and Decimal(rate.rstrip("%")) > 100):
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
    if year == 2026 and deltas != [0, 0]:
        raise ValueError("Connecticut 2026 town and statewide checklist controls disagree")
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


def scan_number(cell):
    if not re.fullmatch(r"[0-9]+(?:(?:[.,] *| )[0-9]{3})*", cell):
        return None
    return int(re.sub(r"[,. ]", "", cell))


def scan_view(view):
    dpi = view["receipt"]["dpi"]
    rows = []
    for row in view["role_cells"]:
        cells = [" ".join(c["text"] for c in row if left <=
                          (c["left"] + c["right"]) * 36 / dpi < right) for left, right in SCAN_BANDS]
        if "%" not in cells[3] and not all(re.fullmatch(r"[0-9,. ]+", s) for s in cells[1:3]):
            continue
        if rows and rows[-1] == cells and cells[0] == "StatewideTotal":
            continue  # Both renders duplicate the same printed control line.
        rows.append(cells)
    return {"receipt": view["receipt"], "header": view["text"].splitlines()[:9], "rows": rows}


def scanned_statement_rows(pages):
    from scripts.results_pdf_archive_ocr import DPI, heading_key

    if len(pages) != STATEMENTS[2018][3]:
        raise ValueError("Incomplete Connecticut scanned town table")
    rows = []
    for page, pair in enumerate(pages, SCAN_FIRST):
        for dpi, view in zip(DPI, pair, strict=True):
            receipt = view["receipt"]
            header = heading_key(" ".join(view["header"]))
            if (receipt["page"] != page or receipt["dpi"] != dpi or receipt.get("rotation_degrees") != 90
                    or not all(term in header for term in (
                        "electiondayregistrationturnoutandabsenteeballotstatistics", "checklist", "percentage",
                        "edrreceived", "edrrejected", "edrvoted", "town"))
                    or page == SCAN_FIRST and "election11062018november2018stateelection" not in header):
                raise ValueError("Connecticut scanned table page, headings or election changed")
        for left, right in zip(pair[0]["rows"], pair[1]["rows"], strict=True):
            a, b = [SCAN_NAMES.get(cells[0], cells[0]) for cells in (left, right)]
            n, voted = [scan_number(cell) for cell in left[1:3]]
            if (a != b or n is None or voted is None or not 0 <= voted <= n or n == 0
                    or [n, voted] != [scan_number(cell) for cell in right[1:3]]
                    or left[3] != right[3] or not re.fullmatch(r"\d{1,3}\.\d{2}%", left[3])
                    or Decimal(left[3][:-1]) != (Decimal(voted) * 100 / n).quantize(
                        Decimal(".01"), rounding=ROUND_HALF_UP)):
                raise ValueError("Connecticut scanned town counts or printed rate disagree")
            modes = [x if x == y else None for x, y in zip(map(scan_number, left[4:]),
                                                          map(scan_number, right[4:]), strict=True)]
            rows.append((a, False, [n, voted, *modes], left[3], [left, right]))
    if not rows or rows[-1][0] != "Statewide Totals":
        raise ValueError("Missing statewide Connecticut scan control")
    names = [row[0] for row in rows[:-1]]
    roster = set(names) | PARTIAL_TOWNS[2018]
    deltas = [sum(row[2][i] for row in rows[:-1]) - rows[-1][2][i] for i in range(2)]
    if (names != sorted(set(names)) or "Statewide Totals" in names or deltas != [0, 0]
            or hashlib.sha256("\n".join(sorted(roster)).encode()).hexdigest() != ROSTER):
        raise ValueError("Connecticut scanned town roster or statewide controls disagree")
    return rows, deltas


def scanned_statement(body):
    import pymupdf

    if not body.startswith(b"%PDF-") or len(body) > SCAN_LIMIT:
        raise ValueError("Connecticut scanned Statement exceeds PDF bounds")
    with pymupdf.open(stream=body, filetype="pdf") as report:
        if (report.needs_pass or not report.permissions & pymupdf.PDF_PERM_COPY
                or not SCAN_FIRST + 9 <= len(report) <= 235):
            raise ValueError("Connecticut scanned Statement does not permit bounded extraction")
    views = [[scan_view(view) for view in pair]
             for pair in scan.extract(body, range(SCAN_FIRST - 1, SCAN_FIRST + 9), rotation=90).values()]
    try:
        scanned_statement_rows(views)
    except ValueError as error:
        scan.fail(str(error))
    return {"complete_native_query": views, "participation_observation_qualified": False}


def reviewed_scan_checkpoint(receipt):
    checkpoint = json.loads(Path(__file__).with_name(SCAN_CHECKPOINT).read_bytes())
    if not valid_link(receipt["url"], 2018) or checkpoint["source"] != {
            key: receipt[key] for key in ("bytes", "sha256")}:
        return None
    views = checkpoint["views"]
    scanned_statement_rows(views)
    return {"complete_native_query": views, "participation_observation_qualified": False}


def statement_query(body, year):
    import pymupdf

    if not body.startswith(b"%PDF-") or len(body) > STATEMENT_LIMIT:
        raise ValueError("Connecticut Statement of Vote exceeds PDF bounds")
    wanted = ("samedayregistrationsdrturnoutabsenteeearlyvotingballotstatistics" if year in SDR_YEARS
              else "electiondayregistrationturnoutandabsenteeballotstatistics")
    compact = lambda value: re.sub(r"[^a-z0-9]", "", value.lower())
    with pymupdf.open(stream=body, filetype="pdf") as report:
        if report.needs_pass or not report.permissions & pymupdf.PDF_PERM_COPY or not 1 <= len(report) <= 300:
            raise ValueError("Connecticut Statement PDF does not permit bounded extraction")
        if year == 2016:
            cover = compact(report[0].get_text())
            if len(report) < 11 or not all(name in cover for name in (
                    "stateofconnecticut", "officeofthesecretaryofthestate", wanted)):
                raise ValueError("Connecticut voter-statistics release authority differs")
            first = physical_text(report[1], pymupdf)
            town_start = next((i for i, line in enumerate(first) if line.startswith("Andover ")), None)
            if (town_start is None
                    or not all(term in compact(" ".join(first[:town_start])) for term in
                               ("town", "official", "checklist", "havingvoted", "absenteeballots"))):
                raise ValueError("Connecticut voter-statistics release town table differs")
            region = first[town_start:] + [line for page in report[2:11] for line in physical_text(page, pymupdf)]
            rows = [line for line in region if re.search(r"\d\.\d{2}%", line) or line.startswith("Statewide ")]
            parsed, _ = statement_rows(rows, year)
            county_totals = [re.fullmatch(rf"Totals ({NUMBER}) ({NUMBER}) \d{{1,3}}\.\d{{2}}%"
                                         rf"((?: {NUMBER}){{6}})", line) for line in first[:town_start]]
            controls = [[int(value.replace(",", "")) for value in (match[1], match[2], *match[3].split())]
                        for match in county_totals if match]
            if controls != [parsed[-1][2]]:
                raise ValueError("Connecticut county and town statewide controls disagree")
            return {"complete_native_query": rows, "participation_observation_qualified": False}
        start = None
        pages = []
        expected = STATEMENTS[year][3]
        for i in range(max(0, len(report) - 48), len(report)):
            if start is not None and expected is not None and i >= start + expected:
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
                if year in (2022, *SDR_YEARS):
                    cover_date = datetime.fromisoformat(DATES[year])
                    title = compact(report[0].get_text())
                    if ("stateofconnecticut" not in title or "statementofvotegeneralelection" not in title
                            or f"november{cover_date.day}{year}" not in title):
                        raise ValueError("Connecticut Statement cover election date disagrees")
                if year == 2020 and "2020connecticutcandidatesforelectorsofpresident" not in compact(report[2].get_text()):
                    raise ValueError("Connecticut Statement table of contents does not identify this election")
            if year == 2026 and hashlib.sha256(compact(" ".join(lines[:7])).encode()).hexdigest() != SDR_HEADER_SHA256:
                break
            page_rows = [line for line in lines if re.search(r"\d\.\d{2}%", line)]
            if not page_rows:
                raise ValueError("Missing Connecticut Statement table page")
            pages.append(page_rows)
        if not pages or (expected is not None and len(pages) != expected):
            raise ValueError("Incomplete Connecticut Statement turnout section")
    rows = [line for page in pages for line in page]
    statement_rows(rows, year)
    return {"complete_native_query": rows, "participation_observation_qualified": False}


def parse(body, year):
    if year == 2018:
        return scanned_statement(body)
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
    rejected_scan = scan.ScanRejection(old)

    def read_report(index):
        url = discover(index, year)
        body, _ = collector.acquire(url)
        receipt = {"url": url, **pin(body)}
        previous = old.get("data") or {}
        if previous.get("report") == receipt:
            rejected_scan.receipt = None
            return previous
        if year == 2018:
            facts = reviewed_scan_checkpoint(receipt)
            if facts is None:
                facts = rejected_scan.parse(receipt, scan.scan_policy(__file__, year), lambda: parse(body, year))
            else:
                rejected_scan.receipt = None
        else:
            facts = parse(body, year)
        return {"report": receipt, **facts}

    entry = collector.capture(feed, archive_index(year), read_report, shared_acquisition=True, equivalent=lambda a, b: a == b)
    rejected_scan.attach(entry)
    if not collector.offline:
        entry["archive_check_week_utc"] = week
    return entry


def archive_index(year):
    return PRESS_INDEX if year == 2016 else STATEMENT_INDEX if year in STATEMENTS else INDEX


def exports(entries):
    for feed, year in FEEDS.items():
        entry = entries.get(feed, {})
        data = entry.get("data")
        if not data or entry.get("status") not in {"reported", "retained_after_failure"}:
            continue
        report = data["report"]
        statement = year in STATEMENTS
        limit = SCAN_LIMIT if year == 2018 else STATEMENT_LIMIT if statement else 2_000_000
        if (entry["source"]["url"] != archive_index(year) or not valid_link(report["url"], year)
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                or not 0 < report["bytes"] <= limit):
            raise ValueError("Connecticut turnout source lineage changed")
        if year == 2018:
            rows, deltas = scanned_statement_rows(data["complete_native_query"])
        else:
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
                      "printed_percentage_differs" if rate is not None and Decimal(rate.rstrip("%")) !=
                      (computed * 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) else None)
            yield {
                "state_code": "CT", "election_date": DATES[year], "geography_level": (
                    "state" if state else "town_part" if part else "town"),
                "reporting_unit": name, "source_unit_occurrence": seen[name],
                "active_checklist": n, "checked_as_voted": voted, "source_reported_percent": rate,
                "checked_as_voted_fraction": f"{computed:.8f}" if reason is None else None,
                "rate_hold_reason": reason, "absentee_received": received, "absentee_rejected": rejected,
                "absentee_voted": cast, "absentee_accounting_difference": (
                    received - rejected - cast if None not in (received, rejected, cast) else None),
                "town_minus_state_checklist": deltas[0] if state else None,
                "town_minus_state_checked_as_voted": deltas[1] if state else None,
                "native_row": literal, "source_status": entry["status"], "source_url": report["url"],
                "source_sha256": report["sha256"], "checked_week_utc": entry.get("archive_check_week_utc"),
                **(dict(zip(
                    ("early_received", "early_rejected", "early_voted", "sdr_received", "sdr_rejected", "sdr_voted")
                    if year in SDR_YEARS else ("edr_received", "edr_rejected", "edr_voted"), other_modes))
                   if other_modes else {}),
            }
