"""Discover and validate complete county statistical parents, not contest totals."""

import copy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html import unescape
from html.parser import HTMLParser
import io
import re
from urllib.parse import urljoin, urlsplit

from scripts.participation_intake.contract import count, pin


IDENTITY = "OH-cuyahoga-countywide-turnout"
INDEX_URL = "https://www.boe.cuyahogacounty.gov/elections/GetElectionById/269/"
COUNTY = "Cuyahoga County"
ELECTION = "2026-11-03"
TITLE = f"{COUNTY}, November 3, 2026 General Election"
SCOPE = "All Precincts, All Districts, All Counter Groups, All ScanStations, All Contests, All Boxes"
REPORT = "/elections/GetDocumentById/"
LINK = re.compile(REPORT + r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/", re.I)
STATISTICS = re.compile(
    r"Total Ballots Cast: ([0-9]+), Registered Voters: ([0-9]+), Overall Turnout: ([0-9]+\.[0-9]{2})%")
STATUSES = ("Unofficial Results by Contest", "Official Results by Contest")
PHILADELPHIA_FEED = "PA-philadelphia-countywide-turnout"
PHILADELPHIA_URL = "https://philadelphiaresults.azurewebsites.us/VoterTurnoutDetails.aspx"
SUMMIT_FEED = "UT-summit-county-canvass"
SUMMIT_INDEX = "https://www.summitcountyutah.gov/281/Voter-Registration-Elections"
SUMMIT_PATH = re.compile(r"/DocumentCenter/View/[0-9]+/2026-General-Canvass-Packet(?:-[a-zA-Z0-9]+)*")
SUMMIT_MODES = (
    "Mail ballots counted", "In-person early voting period ballots counted",
    "In-person election day ballots counted", "Disability ballots counted returned electronically",
    "UOCAVA ballots counted returned electronically", "Provisional ballots counted", "Emergency ballots counted",
)
SUSSEX_FEED = "NJ-sussex-county-canvass"
SUSSEX_INDEX = "https://www.sussexcountyclerk.org/939/General-Election"
SUSSEX_PATH = re.compile(r"/DocumentCenter/View/[0-9]+/2026-NOV-3-GE---OFFICIAL-results---countywide-SUPP")
SUSSEX_MODES = ("Election Day", "Early Voting", "Mail-In", "Provisional", "Emergency", "Overseas")
DOUGLAS_FEED = "WI-douglas-county-canvass"
DOUGLAS_INDEX = "https://www.douglascountywi.gov/1237/Election-Results"
DOUGLAS_PATH = re.compile(r"/Archive\.aspx\?ADID=[1-9][0-9]*")
DOUGLAS_HEADER = (
    r"Summary Results Report General Election November 3, 2026 CERTIFIED RESULTS "
    r"([1-9]\d*) of \1 Reporting COMPLETE Douglas County, Wisconsin"
)
DOUGLAS_FOOTER = (
    r"Election Summary - (\d{1,2}/\d{1,2}/2026) (\d{1,2}:\d\d [AP]M) "
    r"(?:Page )?([1-9]\d*) of ([1-9]\d*) Report generated with Electionware Copyright © \d{4}-\d{4}"
)


def douglas_discovery(body):
    text = body.decode("utf-8-sig")
    sections = re.findall(r">November 3, 2026 Election Results</h1>\s*<ul>(.*?)</ul>", text, re.S)
    if len(sections) != 1:
        raise ValueError("Douglas County general-election archive section changed")
    links = re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>Results County-wide</a>\s*-\s*COMPLETE', sections[0])
    if len(links) != 1 or not DOUGLAS_PATH.fullmatch(unescape(links[0])):
        raise ValueError("Missing or incompatible Douglas County countywide summary link")
    return urljoin(DOUGLAS_INDEX, unescape(links[0]))


def douglas_controls(data):
    report, pages = data["report"], data["complete_native_query"]
    parts = urlsplit(report["url"])
    if (parts.scheme != "https" or parts.netloc != urlsplit(DOUGLAS_INDEX).netloc or parts.fragment
            or not DOUGLAS_PATH.fullmatch(parts.path + "?" + parts.query)
            or type(report["bytes"]) is not int or not 0 < report["bytes"] <= 4_000_000
            or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
            or not isinstance(pages, list) or not 1 <= len(pages) <= 100):
        raise ValueError("Invalid Douglas County countywide report receipt")
    clocks = []
    number = r"([1-9]\d{0,2}(?:,\d{3})+|0|[1-9]\d*)"
    statistics = (
        rf"Statistics TOTAL Registered Voters - Total {number} Ballots Cast - Total {number} "
        r"Voter Turnout - Total (\d{1,3}\.\d{2}%)"
    )
    first = None
    for physical_page, text in enumerate(pages, 1):
        content = f" {statistics} " if physical_page == 1 else " "
        match = re.fullmatch(DOUGLAS_HEADER + content + DOUGLAS_FOOTER, text)
        if not match:
            raise ValueError("Douglas County certified scope or statistics changed")
        if first is None:
            first = match
        *_, date, clock, page, total = match.groups()
        if (int(page), int(total)) != (physical_page, len(pages)) or match[1] != first[1]:
            raise ValueError("Douglas County report page or reporting inventory changed")
        clocks.append(datetime.strptime(f"{date} {clock}", "%m/%d/%Y %I:%M %p"))
    registered, ballots = (count(first[i].replace(",", "")) for i in (2, 3))
    printed = first[4]
    if (len(set(clocks)) != 1 or clocks[0] < datetime(2026, 11, 3) or data["date"] != clocks[0].isoformat()
            or not 0 < ballots <= registered
            or (100 * Decimal(ballots) / registered).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            != Decimal(printed[:-1])):
        raise ValueError("Douglas County ballot counts, registration fraction or report clocks do not reconcile")
    return clocks[0].isoformat(), ballots, registered, printed, int(first[1])


def collect_douglas(collector):
    def parse(index):
        from pypdf import PdfReader

        url = douglas_discovery(index)
        body, _ = collector.acquire(url)
        if len(body) > 4_000_000 or not body.startswith(b"%PDF-") or not body.rstrip().endswith(b"%%EOF"):
            raise ValueError("Incomplete Douglas County report")
        pdf = PdfReader(io.BytesIO(body), strict=True)
        if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100:
            raise ValueError("Unreviewed Douglas County report shape")
        pages = []
        for i, original in enumerate(pdf.pages):
            page = " ".join(original.extract_text().split())
            header = re.match(DOUGLAS_HEADER, page)
            footer = re.search(DOUGLAS_FOOTER + r"$", page)
            if not header or not footer:
                raise ValueError("Douglas County report header or footer changed")
            pages.append(page if i == 0 else f"{header[0]} {footer[0]}")
        date = datetime.strptime(f"{footer[1]} {footer[2]}", "%m/%d/%Y %I:%M %p").isoformat()
        data = {"report": {"url": url, **pin(body)}, "complete_native_query": pages, "date": date,
                "participation_observation_qualified": False}
        douglas_controls(data)
        return data

    return collector.capture(DOUGLAS_FEED, DOUGLAS_INDEX, parse)


def sussex_discovery(body):
    text = body.decode("utf-8-sig")
    heading = r">2026 November 3 General Election</strong></h2>"
    sections = re.findall(heading + r"(.*?)(?:</p>)", text, re.S)
    if len(sections) != 1:
        raise ValueError("Sussex 2026 general-election archive section changed")
    links = re.findall(
        r'<a\b[^>]*href="([^"]+)"[^>]*><strong\b[^>]*>OFFICIAL Results</strong>'
        r"\s*-\s*Countywide Summary</a>\s*\(certified (\d{1,2}/\d{1,2}/2026)\)",
        sections[0],
    )
    if len(links) != 1:
        raise ValueError("Missing or repeated Sussex certified countywide summary")
    path, date = links[0]
    url = urljoin(SUSSEX_INDEX, unescape(path))
    sussex_url(url)
    return url, date


def sussex_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc != urlsplit(SUSSEX_INDEX).netloc
            or not SUSSEX_PATH.fullmatch(parts.path) or parts.query or parts.fragment):
        raise ValueError("Unreviewed Sussex countywide report destination")


def sussex_statistics(text, certification_date):
    prefix = ("Countywide OFFICIAL RESULTSSussex County, New Jersey General Election "
              "Summary Results ReportNovember 3, 2026 Statistics TOTAL Election Day Early Voting "
              "Mail-InProvisional Emergenc y Overseas ")
    if not text.startswith(prefix):
        raise ValueError("Sussex election, geography, official status or mode order changed")
    number = r"([1-9]\d{0,2}(?:,\d{3})+|0|[1-9]\d*)(?![\d,])"
    match = re.fullmatch(
        r"Election Day Precincts Reporting ([1-9]\d*) of \1 \1 0 0 0 0 0 "
        r"Precincts Complete \1 of \1 \1 0 0 0 0 0 "
        rf"Registered Voters - Total {number} {number}\s*Ballots Cast - Total "
        + " ".join([number] * len(SUSSEX_MODES))
        + r" Voter Turnout - Total (\d{1,3}\.\d{2}%) (?:Election Summary - )"
        r"(\d{1,2}/\d{1,2}/2026) (\d{1,2}:\d\d[AP]M) \d+Page 1 of",
        text[len(prefix):],
    )
    if not match:
        raise ValueError("Missing or incompatible Sussex countywide statistics")
    precincts, registered, ballots, *rest = match.groups()
    *components, printed, report_date, clock = rest
    date = datetime.strptime(f"{report_date} {clock}", "%m/%d/%Y %I:%M%p")
    certified = datetime.strptime(certification_date, "%m/%d/%Y")
    def as_count(value):
        return count(value.replace(",", ""))
    registered, ballots = as_count(registered), as_count(ballots)
    modes = dict(zip(SUSSEX_MODES, map(as_count, components)))
    if (date.date() != certified.date() or certified <= datetime(2026, 11, 3)
            or not 0 < ballots <= registered or sum(modes.values()) != ballots
            or (100 * Decimal(ballots) / registered).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            != Decimal(printed[:-1])):
        raise ValueError("Sussex ballot modes, registrations, rate or certification date do not reconcile")
    return date.isoformat(), ballots, registered, printed, modes, int(precincts)


def sussex_controls(data):
    source, facts = data["report"], data["complete_native_query"]
    sussex_url(source["url"])
    if (type(source["bytes"]) is not int or not 0 < source["bytes"] <= 4_000_000
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or set(facts) != {"statistics", "archive_certification_date"}):
        raise ValueError("Invalid Sussex countywide report receipt")
    result = sussex_statistics(facts["statistics"], facts["archive_certification_date"])
    if data["date"] != result[0]:
        raise ValueError("Sussex County report clock changed")
    return result


def collect_sussex(collector):
    def parse(index):
        from pypdf import PdfReader

        url, certification = sussex_discovery(index)
        body, _ = collector.acquire(url)
        if len(body) > 4_000_000 or not body.startswith(b"%PDF-") or not body.rstrip().endswith(b"%%EOF"):
            raise ValueError("Incomplete Sussex countywide report")
        pdf = PdfReader(io.BytesIO(body), strict=True)
        if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100:
            raise ValueError("Unreviewed Sussex countywide report shape")
        page = " ".join(pdf.pages[0].extract_text().split())
        stats = re.match(r".*? Voter Turnout - Total \d{1,3}\.\d{2}%(?= )", page)
        footer = re.search(r"Election Summary - \d{1,2}/\d{1,2}/2026 \d{1,2}:\d\d[AP]M \d+Page 1 of$", page)
        if not stats or not footer or not footer[0].endswith(f" {len(pdf.pages)}Page 1 of"):
            raise ValueError("Sussex first-page scope or document pagination changed")
        facts = {"statistics": f"{stats[0]} {footer[0]}", "archive_certification_date": certification}
        date, *_ = sussex_statistics(facts["statistics"], certification)
        return {"report": {"url": url, **pin(body)}, "complete_native_query": facts, "date": date,
                "participation_observation_qualified": False}

    return collector.capture(SUSSEX_FEED, SUSSEX_INDEX, parse)


def summit_discovery(body):
    text = body.decode("utf-8-sig")
    sections = re.findall(r"Official results for the 2026 General Election:</strong></p>\s*(<ul>.*?</ul>)", text, re.S)
    if len(sections) != 1:
        raise ValueError("Summit County 2026 general-election archive section changed")
    links = re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>\s*Canvass Packet\s*</a>', sections[0])
    if len(links) != 1:
        raise ValueError("Missing or repeated Summit County canvass packet")
    url = urljoin(SUMMIT_INDEX, unescape(links[0]))
    summit_url(url)
    return url


def summit_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.netloc != urlsplit(SUMMIT_INDEX).netloc
            or not SUMMIT_PATH.fullmatch(parts.path) or parts.query or parts.fragment):
        raise ValueError("Unreviewed Summit County canvass packet destination")


def summit_pages(pages):
    cover, form, summary = (" ".join(page.split()) for page in pages)
    number = r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?![\d,])"

    def field(pattern, text):
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise ValueError("Missing or repeated Summit canvass field: " + pattern)
        return matches[0]

    prefix = ("Summit County General Election November 3, 2026 OFFICIAL RESULTS "
              "General 2026 County Summary Results STATISTICS TOTAL ")
    if (not summary.startswith(prefix) or "Summit County General Election 11/3/26 Final Ballot Summary" not in cover
            or not all(label in form for label in ("Standardized Canvass Statistics Report",
                "County Name - November 3, 2026", "Yes Does total ballots counted match the number of voters given vote history in VISTA?"))):
        raise ValueError("Summit canvass election, county or scope changed")
    ballot_clock, time, meridiem = field(
        r"General 2026 County Summary Results - (\d{1,2}/\d{1,2}/2026) (\d{1,2}:\d\d)(AM|PM)", summary)
    if not cover.startswith(ballot_clock + " "):
        raise ValueError("Summit County canvass dates disagree")
    date = datetime.strptime(f"{ballot_clock} {time} {meridiem}", "%m/%d/%Y %I:%M %p").isoformat()
    def as_count(pattern, text):
        return count(field(pattern, text).replace(",", ""))
    ballots = as_count(number + r"\s*Ballots Cast - Total", summary)
    registered = as_count(r"Registered Voters - Total " + number, summary)
    counted_section = form.split("Vote histories given", 1)[0]
    modes = {label: as_count(r"(?<![\d,])" + number + " " + re.escape(label), counted_section)
             for label in SUMMIT_MODES}
    printed = field(r"Voter Turnout - Total ([0-9]{1,3}\.[0-9]{2}%)", summary)
    form_rate = field(r"([0-9]{1,3}\.[0-9]%) Voter turnout", form)
    if (not 0 < ballots <= registered or date[:10] < "2026-11-17"
            or ballots != sum(modes.values())
            or ballots != as_count(r"Number of Ballots Counted: " + number, cover)
            or ballots != as_count(r"(?<![\d,])" + number + r" Total ballots counted", form)
            or ballots != as_count(r"(?<![\d,])" + number + r" Vote histories given", form)
            or registered != as_count(r"(?<![\d,])" + number + r" Active voters \(use only", form)
            or any((100 * Decimal(ballots) / registered).quantize(precision, rounding=ROUND_HALF_UP)
                   != Decimal(rate[:-1]) for precision, rate in ((Decimal(".01"), printed), (Decimal(".1"), form_rate)))):
        raise ValueError("Summit countywide ballot modes, registrations or rates do not reconcile")
    return date, ballots, registered, printed, modes


def summit_controls(data):
    source, pages = data["report"], data["complete_native_query"]
    summit_url(source["url"])
    if (type(source["bytes"]) is not int or not 0 < source["bytes"] <= 16_000_000
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or not isinstance(pages, list) or len(pages) != 3):
        raise ValueError("Invalid Summit countywide report receipt")
    result = summit_pages(pages)
    if data["date"] != result[0]:
        raise ValueError("Summit County report clock changed")
    return result


def collect_summit(collector):
    def parse(index):
        from pypdf import PdfReader

        url = summit_discovery(index)
        body, _ = collector.acquire(url)
        if len(body) > 16_000_000 or not body.startswith(b"%PDF-") or not body.rstrip().endswith(b"%%EOF"):
            raise ValueError("Incomplete Summit County canvass packet")
        pdf = PdfReader(io.BytesIO(body), strict=True)
        if pdf.is_encrypted or not 3 <= len(pdf.pages) <= 200:
            raise ValueError("Unreviewed Summit County canvass packet shape")
        pages = [pdf.pages[i].extract_text() for i in range(3)]
        date, *_ = summit_pages(pages)
        return {"report": {"url": url, **pin(body)}, "complete_native_query": pages, "date": date,
                "participation_observation_qualified": False}

    return collector.capture(SUMMIT_FEED, SUMMIT_INDEX, parse)


PHILADELPHIA_DIVISION = re.compile(
    r'<div class="county-precinct (odd|even)">\s*([0-9]{2}-[0-9]{2,3})\s*</div>'
    r'((?:(?:\s*<div class="vertical-line-turnout"></div>)?\s*'
    r'<div class="county-cast \1">[0-9,]+</div>){5})')


def philadelphia_controls(data):
    source, query = data["report"], data["complete_native_query"]
    status, clock = query["status"], query["clock"]
    ballots, registered, mail, polls, provisional, reported, divisions = query["parent"]
    rate = query["printed_rate"]
    rows = query["divisions"]
    if (source["url"] != PHILADELPHIA_URL or type(source["bytes"]) is not int or source["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or status not in {"Official", "Unofficial"} or query["election_date"] != ELECTION
            or not re.fullmatch(r"[0-9]+\.[0-9]{2}%", rate)
            or any(type(n) is not int or n < 0 for n in query["parent"])
            or not 0 < ballots <= registered or mail + polls + provisional != ballots
            or (Decimal(ballots) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(rate[:-1])
            or not 0 <= reported <= divisions or divisions != len(rows)
            or len({row[0] for row in rows}) != divisions
            or {row[0][:2] for row in rows} != {f"{i:02}" for i in range(1, 67)}):
        raise ValueError("Philadelphia turnout summary, division inventory or source scope changed")
    if datetime.strptime(clock, "%m/%d/%Y %I:%M:%S %p EST").date().isoformat() < ELECTION:
        raise ValueError("Philadelphia report clock predates the election")
    for key, reg, total, place, mailed, prov in rows:
        if (not re.fullmatch(r"[0-9]{2}-[0-9]{2,3}", key)
                or any(type(n) is not int or n < 0 for n in (reg, total, place, mailed, prov))
                or total > reg or total != place + mailed + prov):
            raise ValueError("Invalid Philadelphia division turnout row: " + key)
    sum_reg, sum_total, sum_polls, sum_mail, sum_prov = map(sum, zip(*(r[1:] for r in rows)))
    if (sum_reg, sum_polls, sum_prov) != (registered, polls, provisional) or not (
            0 <= mail - sum_mail == ballots - sum_total):
        raise ValueError("Philadelphia division totals differ outside the unassigned mail residual")
    return ballots, registered, rate, status, clock, mail - sum_mail


def philadelphia_report(body):
    html = body.decode("utf-8-sig")
    number = r"([0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"

    def single(pattern):
        matches = re.findall(pattern, html)
        if len(matches) != 1:
            raise ValueError("Missing or repeated Philadelphia turnout field: " + pattern)
        return matches[0]

    testing = single(r'<div id="pnlTestBanner"[^>]+style="([^"]*)"')
    if "display:none" not in re.sub(r"\s+", "", testing).lower().split(";"):
        raise ValueError("Philadelphia results portal is in testing mode")
    status = single(r'<a id="lnkElectionInfo"[^>]+><h1><span>(Unofficial|Official)</span>'
                    r' 2026 General Election Results</h1><h2>November 3, 2026</h2>')
    clock = single(r'class="turnout-last-updated-time">([^<]+)</span>')
    registered = single(r'Total Ballots Cast<span>' + number + r'</span><br/>Registered Voters<span>'
                        + number + r'</span>')
    modes = single(r'Ballots Cast by Mail:<span>' + number + r'</span><br/>Ballots Cast at Polling Place:<span>'
                   + number + r'</span><br/>Ballots Cast by Provisional:<span>' + number + r'</span>')
    reporting = single(r'Divisions Reported<span>' + number + r'</span><br/>Total Divisions<span>' + number + r'</span>')
    rate = "".join(single(r'<canvas id="voter-turnout"[^>]*></canvas><div class="dough-percent">'
                          r'<span class="int">([0-9]+)</span><span class="dec">(\.[0-9]{2}%)</span>'))
    parse_int = lambda value: int(value.replace(",", ""))
    rows = [[key, *(parse_int(n) for n in re.findall(r">([0-9,]+)</div>", cells))]
            for _, key, cells in PHILADELPHIA_DIVISION.findall(html)]
    data = {"report": {"url": PHILADELPHIA_URL, **pin(body)}, "complete_native_query": {
        "status": status, "election_date": ELECTION, "clock": clock, "printed_rate": rate,
        "parent": [parse_int(n) for n in (*registered, *modes, *reporting)], "divisions": rows,
    }}
    philadelphia_controls(data)
    return data


def collect_philadelphia(collector):
    def parse(body):
        data = philadelphia_report(body)
        clock = data["complete_native_query"]["clock"]
        data["date"] = datetime.strptime(clock, "%m/%d/%Y %I:%M:%S %p EST").isoformat()
        prior = (collector.prior.get(PHILADELPHIA_FEED) or {}).get("data")
        if prior and prior["complete_native_query"]["status"] == "Official" and (
                data["complete_native_query"]["status"] != "Official"):
            raise ValueError("Philadelphia official results reverted to unofficial")
        return data

    return collector.capture(PHILADELPHIA_FEED, PHILADELPHIA_URL, parse,
                             equivalent=lambda old, new: {
                                 key: value for key, value in old.items() if key != "report"
                             } == {key: value for key, value in new.items() if key != "report"})


class ReportLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchor = None
        self.links = {status: set() for status in STATUSES}

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchor = (dict(attrs).get("href") or "", [])

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            href, text = self.anchor
            self.anchor = None
            label = " ".join(" ".join(text).split())
            if label in self.links and LINK.fullmatch(href):
                self.links[label].add(urljoin(INDEX_URL, href))


def discovery(body):
    parser = ReportLinks()
    parser.feed(body.decode("utf-8-sig"))
    label = STATUSES[1] if parser.links[STATUSES[1]] else STATUSES[0]
    urls = parser.links[label]
    if len(urls) != 1:
        raise ValueError("County contest report link is missing or ambiguous")
    return label, next(iter(urls))


def checked_pages(pages, label):
    if not 1 <= len(pages) <= 150 or label not in STATUSES:
        raise ValueError("Unreviewed county report status or page inventory")
    for number, page in enumerate(pages, 1):
        if (set(page) != {"title", "election", "scope", "statistics", "clock", "page"}
                or page["title"] != label or page["election"] != TITLE or page["scope"] != SCOPE
                or page["page"] != f"Page: {number} of {len(pages)}"
                or any(page[key] != pages[0][key] for key in ("statistics", "clock"))):
            raise ValueError("County report scope, clock, totals or page sequence differs")
    match = STATISTICS.fullmatch(pages[0]["statistics"])
    if not match:
        raise ValueError("Countywide ballot and same-report registration row is absent")
    ballots, registered = map(count, match.groups()[:2])
    fraction = Decimal(match[3])
    clock = datetime.strptime(pages[0]["clock"], "%Y-%m-%d %H:%M:%S")
    if (clock.date().isoformat() < ELECTION or ballots is None or registered is None
            or not 0 < ballots <= registered
            or (Decimal(ballots) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != fraction):
        raise ValueError("County report date, numerator, denominator or printed fraction disagrees")
    return clock.isoformat(), ballots, registered, f"{fraction}%"


def parse_report(body):
    from pypdf import PdfReader

    if not body.startswith(b"%PDF-") or not body.rstrip().endswith(b"%%EOF"):
        raise ValueError("Missing complete county report PDF")
    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 150:
        raise ValueError("Unreviewed county PDF inventory")
    pages = []
    for page in reader.pages:
        lines = [" ".join(line.split()) for line in page.extract_text().splitlines() if line.strip()]
        footers = [line for line in lines if re.fullmatch(r"Page: [0-9]+ of [0-9]+", line)]
        if len(lines) < 7 or len(footers) != 1 or lines.count("NOV26GEN") != 1:
            raise ValueError("Missing native county election report selectors")
        pages.append(dict(zip(("title", "election", "scope", "statistics", "clock", "page"),
                              (*lines[:4], " ".join(lines[4:6]), footers[0]))))
    return pages


def validate_data(data):
    source = data["report"]
    parts = urlsplit(source["url"])
    if (data["source_url"] != source["url"] or data["election_date"] != ELECTION
            or set(source) != {"url", "bytes", "sha256"} or parts.scheme != "https"
            or parts.netloc != urlsplit(INDEX_URL).netloc or not LINK.fullmatch(parts.path)
            or parts.query or parts.fragment or type(source["bytes"]) is not int
            or not 0 < source["bytes"] <= 4_000_000 or not re.fullmatch("[a-f0-9]{64}", source["sha256"])):
        raise ValueError("County report URL or complete body receipt differs")
    evidence = checked_pages(data["complete_native_query"], data["report_status"])
    if data["date"] != evidence[0]:
        raise ValueError("County report summary clock differs")
    return evidence


def collect(collector):
    def parse(index):
        label, url = discovery(index)
        old = (collector.prior.get(IDENTITY) or {}).get("data") or {}
        if old.get("report_status") == STATUSES[1] and label != STATUSES[1]:
            raise ValueError("Previously accepted official county report is missing")
        body, _ = collector.acquire(url)
        if len(body) > 4_000_000:
            raise ValueError("County aggregate report exceeds reviewed size bound")
        pages = parse_report(body)
        data = {"source_url": url, "report": {"url": url, **pin(body)},
                "report_status": label, "election_date": ELECTION,
                "complete_native_query": pages, "date": checked_pages(pages, label)[0]}
        validate_data(data)
        return data

    return collector.capture(IDENTITY, INDEX_URL, parse)


WILSON_FEED = "TN-wilson-countywide-turnout"
WILSON_URL = "https://www.wilsontnvotes.gov/election-results-reporting/"
WILSON_COUNTY = "Wilson County"
WILSON_CELLS = {
    (0, 0): "Election Summary Results Report",
    (0, 20): "STATE/FEDERAL GENERAL AND MUNICIPAL ELECTIONS",
    (0, 40): "NOVEMBER 3, 2026",
    (311, 40): "WILSON COUNTY, TENNESSEE",
    (1, 70): "STATISTICS",
    (171, 87): "TOTAL", (231, 87): "Absentee", (286, 87): "Early Voting",
    (341, 87): "Election Day", (396, 87): "Provisional",
    (1, 127): "Registered Voters - Total",
    (1, 146): "Ballots Cast - Total", (1, 165): "Voter Turnout - Total",
}
WILSON_VALUES = ((311, 0), (171, 127), (171, 146), (231, 146), (286, 146),
                 (341, 146), (396, 146), (171, 165))


def wilson_controls(data):
    source = data["report"]
    cells = {(x, y): text for x, y, text in data["complete_native_query"]}
    if (source["url"] != WILSON_URL or set(source) != {"url", "bytes", "sha256"}
            or type(source["bytes"]) is not int or not 0 < source["bytes"] <= 4_000_000
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or len(cells) != len(data["complete_native_query"]) or set(cells) != set(WILSON_CELLS) | set(WILSON_VALUES)
            or any(cells[key] != value for key, value in WILSON_CELLS.items())):
        raise ValueError("Wilson County report identity or statistics grid changed")
    status, registered, ballots, *modes, printed = (cells[key] for key in WILSON_VALUES)
    if (status not in {"UNOFFICIAL RESULTS", "OFFICIAL RESULTS"}
            or any(not re.fullmatch(r"0|[1-9]\d{0,2}(?:,\d{3})*|[1-9]\d*", value)
                   for value in (registered, ballots, *modes))
            or not re.fullmatch(r"\d{1,3}\.\d{2}%", printed)):
        raise ValueError("Invalid Wilson County native count or report status")
    registered, ballots, *modes = (count(value.replace(",", "")) for value in (registered, ballots, *modes))
    if (any(value is None for value in (registered, ballots, *modes)) or not 0 < ballots <= registered
            or sum(modes) != ballots
            or (100 * Decimal(ballots) / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(printed[:-1])):
        raise ValueError("Wilson County counts or printed rate do not reconcile")
    return ballots, registered, printed, status


def wilson_summary(body):
    text = body.decode("utf-8-sig")
    anchors = ('<a name="JR_PAGE_ANCHOR_0_1"></a>', '<a name="JR_PAGE_ANCHOR_0_2"></a>')
    if (any(text.count(anchor) != 1 for anchor in anchors)
            or not text.rstrip().endswith("</html>")):
        raise ValueError("Incomplete Wilson County election report")
    page = text.split(anchors[0], 1)[1].split(anchors[1], 1)[0]
    cells = []
    for x, y, cell in re.findall(
        r'<div style="position:absolute;left:(\d+)px;top:(\d+)px;[^>]*>(.*?)</div>', page, re.S
    ):
        cell = " ".join(unescape(re.sub(r"<[^>]+>", " ", cell)).split())
        if cell:
            cells.append([int(x), int(y), cell])
    data = {"report": {"url": WILSON_URL, **pin(body)}, "complete_native_query": sorted(cells)}
    wilson_controls(data)
    return data


def collect_wilson(collector):
    def parse(body):
        data = wilson_summary(body)
        prior = (collector.prior.get(WILSON_FEED) or {}).get("data")
        if (prior and wilson_controls(prior)[3] == "OFFICIAL RESULTS"
                and wilson_controls(data)[3] != "OFFICIAL RESULTS"):
            raise ValueError("Wilson County report status regressed")
        return data

    return collector.capture(WILSON_FEED, WILSON_URL, parse)


SUMNER_FEED = "TN-sumner-countywide-turnout"
SUMNER_INDEX = "https://www.votesumnertn.org/november-general-and-city-elections/"
SUMNER_LINK = re.compile(r"/uploads/files/[a-f0-9]{40}\.pdf")
SUMNER_ROLES = {
    "E-#OFELECTIONDAY": "election_day",
    "A-#OFPAPERABSENTEE": "absentee",
    "W-#OFWALK-INEARLYVOTING": "early",
    "PUBLICCOUNT:": "ballots",
    "REGISTEREDVOTERS:": "registered",
    "VOTERTURNOUT:": "printed",
    "NUMBEROFPRECINCTS:": "total",
    "#OFPRECINCTSREPORTED:": "reported",
    "#OFPRECINCTSNOTREPORTED:": "missing",
    "#OFPRECINCTSINCOMPLETE:": "incomplete",
    "#OFEQUIPMENTPROGRAMMED:": "equipment",
    "#OFEQUIPMENTREPORTED:": "equipment_reported",
}


def sumner_discovery(body):
    text = body.decode("utf-8-sig")
    sections = re.findall(r"<h2><strong>2026</strong></h2>(.*?)(?=<h2>)", text, re.S)
    if len(sections) != 1:
        raise ValueError("Missing or repeated Sumner election archive section")
    links = re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>\s*Federal and State, County General, and Municipal Elections\b',
                       sections[0])
    if len(links) != 1 or not SUMNER_LINK.fullmatch(links[0]):
        raise ValueError("Missing or ambiguous Sumner county summary link")
    return urljoin(SUMNER_INDEX, links[0])


def sumner_view(view):
    lines = [re.sub(r"\s+", "", line.upper()) for line in view["text"].splitlines()[:24]]
    clock = re.fullmatch(r"(\d{1,2}/\d{1,2}/2026)-(\d{1,2}:\d\d:\d\d)(AM|PM)", lines[0])
    if (clock is None or not {"ELECTIONDATE:11/3/2026", "SUMNERCOUNTY,TENNESSEE",
                              "2026GENERALELECTION", "TNSUMG26"} <= set(lines)):
        raise ValueError("Sumner countywide report identity changed")
    text = "\n".join(lines)
    if "ELECTIONSUMMARYREPORT" not in text or "PRECINCTSUMMARYREPORT" in text:
        raise ValueError("Sumner report is not a countywide summary")
    # The upright OCR occasionally reads the I in Walk-In as a lowercase l.
    text = text.replace("WALK-LNEARLYVOTING", "WALK-INEARLYVOTING")
    values = {}
    for label, key in SUMNER_ROLES.items():
        pattern = r"(\d{1,3}\.\d{2}%)" if key == "printed" else r"(\d+)(?![\d.,])"
        found = re.findall(re.escape(label) + r"\n?" + pattern, text)
        if len(found) != 1:
            raise ValueError("Missing or ambiguous Sumner statistics cell: " + key)
        values[key] = found[0] if key == "printed" else count(found[0])
    native_clock = datetime.strptime(" ".join(clock.groups()), "%m/%d/%Y %I:%M:%S %p").isoformat()
    return {"date": native_clock, "values": values, "native_lines": lines,
            "receipt": view["receipt"]}


def sumner_controls(data):
    source, views = data["report"], data["complete_native_query"]
    parts = urlsplit(source["url"])
    if (set(source) != {"url", "bytes", "sha256"} or parts.scheme != "https"
            or parts.netloc != urlsplit(SUMNER_INDEX).netloc or not SUMNER_LINK.fullmatch(parts.path)
            or parts.query or parts.fragment or type(source["bytes"]) is not int
            or not 0 < source["bytes"] <= 4_000_000 or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or len(views) != 2 or [row["receipt"]["dpi"] for row in views] != [180, 240]):
        raise ValueError("Invalid Sumner scanned report receipt")
    for item in views:
        receipt = item["receipt"]
        replay = sumner_view({"text": "\n".join(item["native_lines"]), "receipt": receipt})
        if (replay != item or receipt["page"] != 1 or receipt["rotation_degrees"] != 0
                or receipt["text_angle_classifier_enabled"] is not False):
            raise ValueError("Sumner OCR evidence changed")
    if any(views[0][field] != views[1][field] for field in ("date", "values")):
        raise ValueError("Sumner OCR passes disagree")
    values, clock = views[0]["values"], views[0]["date"]
    ballots, registered = (values[key] for key in ("ballots", "registered"))
    if (clock != data["date"] or clock < ELECTION
            or any(value is None for value in values.values()) or not 0 < ballots <= registered
            or sum(values[key] for key in ("election_day", "absentee", "early")) != ballots
            or not (values["reported"] == values["total"] > 0 and values["missing"] == values["incomplete"] == 0
                    and values["equipment"] == values["equipment_reported"] > 0)
            or (100 * Decimal(ballots) / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(values["printed"][:-1])):
        raise ValueError("Sumner scanned counts, report completeness or rate disagree")
    return clock, ballots, registered, values["printed"]


def collect_sumner(collector):
    def parse(index):
        from pypdf import PdfReader
        from scripts.results_pdf_ocr import first_page_views

        url = sumner_discovery(index)
        body, _ = collector.acquire(url)
        if (len(body) > 4_000_000 or not body.startswith(b"%PDF-")
                or not body.rstrip().endswith(b"%%EOF")):
            raise ValueError("Incomplete Sumner county summary PDF")
        pdf = PdfReader(io.BytesIO(body), strict=True)
        if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100 or pdf.pages[0].extract_text().strip():
            raise ValueError("Unreviewed Sumner scanned PDF")
        views = [sumner_view(view) for view in first_page_views(
            body, strict_role_alignment=True, text_angle_classifier=False)]
        data = {"report": {"url": url, **pin(body)}, "complete_native_query": views, "date": views[0]["date"]}
        sumner_controls(data)
        prior = (collector.prior.get(SUMNER_FEED) or {}).get("data")
        if prior and data["date"] < prior["date"]:
            raise ValueError("Sumner county report clock regressed")
        return data

    return collector.capture(SUMNER_FEED, SUMNER_INDEX, parse)


OKTIBBEHA_FEED = "MS-oktibbeha-countywide-turnout"
OKTIBBEHA_INDEX = "https://www.oktibbeha.ms.gov/332/2026-Election-Results"
OKTIBBEHA_LABEL = "2026 General Election Official Results"
OKTIBBEHA_PATH = re.compile(r"/DocumentCenter/View/[1-9]\d*/2026-General-Election-Official-Results")
OKTIBBEHA_REVIEWED = {
    "url": urljoin(OKTIBBEHA_INDEX, "/DocumentCenter/View/537/2026-General-Election-Official-Results"),
    "bytes": 198490,
    "sha256": "08d63cb418816839263b2e529e9e3651ac33a7e3f07a20d3ad0aff5942a3178e",
}
OKTIBBEHA_COLUMNS = ("TOTAL", "Election Day", "In Person Absentee", "Mail in Absentee",
                     "5 Day Absentee", "Affidavit")
OKTIBBEHA_REVIEWED_QUERY = {
    "election": ELECTION,
    "county": "Oktibbeha County",
    "status": "OFFICIAL RESULTS",
    "columns": list(OKTIBBEHA_COLUMNS),
    "precincts_reporting": ["20 of 20", "20", "0", "0", "0", "20"],
    "registered_voters": "27,148",
    "ballots_cast": ["15,771", "13,319", "1,768", "161", "10", "513"],
    "voter_turnout": "58.09%",
    "report_clock": "11/12/2026 12:07 PM",
    "physical_page": 1,
}


class OktibbehaLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchor = None
        self.matches = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchor = (dict(attrs).get("href") or "", [])

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            href, text = self.anchor
            self.anchor = None
            if " ".join("".join(text).split()) == OKTIBBEHA_LABEL:
                self.matches.append(href)


def oktibbeha_discovery(body):
    parser = OktibbehaLinks()
    parser.feed(body.decode("utf-8-sig"))
    if len(parser.matches) != 1 or not OKTIBBEHA_PATH.fullmatch(parser.matches[0]):
        raise ValueError("Missing or ambiguous Oktibbeha official general-election report")
    return urljoin(OKTIBBEHA_INDEX, parser.matches[0])


def oktibbeha_controls(data):
    report, q = data["report"], data["complete_native_query"]
    parts = urlsplit(report["url"])
    if (set(report) != {"url", "bytes", "sha256"} or parts.scheme != "https"
            or parts.netloc != urlsplit(OKTIBBEHA_INDEX).netloc or parts.query or parts.fragment
            or not OKTIBBEHA_PATH.fullmatch(parts.path) or type(report["bytes"]) is not int
            or not 0 < report["bytes"] <= 4_000_000 or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
            or set(q) != set(OKTIBBEHA_REVIEWED_QUERY) or type(q["physical_page"]) is not int
            or (q["election"], q["county"], q["status"], q["columns"], q["physical_page"])
            != (ELECTION, "Oktibbeha County", "OFFICIAL RESULTS", list(OKTIBBEHA_COLUMNS), 1)):
        raise ValueError("Oktibbeha official report identity changed")
    if data["extraction"] == "visually_reviewed_exact_edition":
        if report != OKTIBBEHA_REVIEWED or q != OKTIBBEHA_REVIEWED_QUERY:
            raise ValueError("Oktibbeha reviewed edition differs")
    elif data["extraction"] != "native_text":
        raise ValueError("Unknown Oktibbeha extraction method")
    def integer(value):
        if not re.fullmatch(r"(?:0|[1-9]\d{0,2}(?:,\d{3})*)", value, re.ASCII):
            raise ValueError("Invalid Oktibbeha statistical count")
        return int(value.replace(",", ""))
    registered = integer(q["registered_voters"])
    ballots, *modes = map(integer, q["ballots_cast"])
    reporting, *reporting_modes = q["precincts_reporting"]
    pair = re.fullmatch(r"([1-9]\d*) of \1", reporting)
    if (len(modes) != 5 or len(reporting_modes) != 5 or pair is None
            or integer(reporting_modes[0]) != int(pair[1])
            or any(integer(value) > int(pair[1]) for value in reporting_modes)
            or not 0 < ballots <= registered or sum(modes) != ballots
            or not re.fullmatch(r"\d{1,3}\.\d{2}%", q["voter_turnout"], re.ASCII)
            or (100 * Decimal(ballots) / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(q["voter_turnout"][:-1])):
        raise ValueError("Oktibbeha reporting, ballot modes or turnout fraction do not reconcile")
    clock = datetime.strptime(q["report_clock"], "%m/%d/%Y %I:%M %p").isoformat()
    if clock != data["date"] or not ELECTION <= clock < "2027":
        raise ValueError("Invalid Oktibbeha report clock")
    return clock, ballots, registered, q["voter_turnout"]


def oktibbeha_text_query(text):
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    # Keep the six printed roles and the direct TOTAL cell mandatory for revisions.
    required = ("Summary Results", "OFFICIAL RESULTS", "2026 General Election",
                "November 3, 2026", "Oktibbeha County")
    if any(lines.count(label) != 1 for label in required) or any("UNOFFICIAL" in line for line in lines):
        raise ValueError("Oktibbeha PDF is not the official county summary")
    def one(pattern):
        found = [match.groups() for line in lines if (match := re.fullmatch(pattern, line))]
        if len(found) != 1:
            raise ValueError("Missing or ambiguous Oktibbeha native statistical row")
        return found[0]
    one(r"Statistics TOTAL Election Day In Person Absentee Mail in Absentee 5 Day Absentee Affidavit")
    cell = r"([0-9,]+)"
    return {
        "election": ELECTION, "county": "Oktibbeha County", "status": "OFFICIAL RESULTS",
        "columns": list(OKTIBBEHA_COLUMNS), "physical_page": 1,
        "precincts_reporting": list(one(r"Election Day Precincts Reporting (\d+ of \d+)" + (" " + cell) * 5)),
        "registered_voters": one(r"Registered Voters - Total " + cell)[0],
        "ballots_cast": list(one(r"Ballots Cast - Total" + (" " + cell) * 6)),
        "voter_turnout": one(r"Voter Turnout - Total (\d{1,3}\.\d{2}%)")[0],
        "report_clock": one(r"Election Summary - (\d{1,2}/\d{1,2}/2026 \d{1,2}:\d\d [AP]M) 1 of \d+")[0],
    }


def collect_oktibbeha(collector):
    def parse(index):
        url = oktibbeha_discovery(index)
        body, _ = collector.acquire(url)
        report = {"url": url, **pin(body)}
        if report == OKTIBBEHA_REVIEWED:
            query, method = copy.deepcopy(OKTIBBEHA_REVIEWED_QUERY), "visually_reviewed_exact_edition"
        else:
            from pypdf import PdfReader

            if (not body.startswith(b"%PDF-") or len(body) > 4_000_000
                    or not body.rstrip().endswith(b"%%EOF")):
                raise ValueError("Incomplete Oktibbeha county summary PDF")
            pdf = PdfReader(io.BytesIO(body), strict=True)
            if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100:
                raise ValueError("Unreviewed Oktibbeha county summary PDF")
            text = pdf.pages[0].extract_text()
            if not text.strip():
                raise ValueError("New Oktibbeha scan has no verified statistical transcription")
            query, method = oktibbeha_text_query(text), "native_text"
        clock = datetime.strptime(query["report_clock"], "%m/%d/%Y %I:%M %p").isoformat()
        data = {"report": report, "complete_native_query": query, "extraction": method, "date": clock}
        oktibbeha_controls(data)
        prior = (collector.prior.get(OKTIBBEHA_FEED) or {}).get("data")
        if prior and (clock < prior["date"] or (clock == prior["date"] and
                     query != prior["complete_native_query"])):
            raise ValueError("Oktibbeha county report clock regressed or conflicts at the same clock")
        return data

    return collector.capture(OKTIBBEHA_FEED, OKTIBBEHA_INDEX, parse,
                             equivalent=lambda old, new: old == new)
