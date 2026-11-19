"""Reconcile Indiana's statewide bulk turnout reports without repairing source counts."""

from datetime import date, datetime
from html.parser import HTMLParser
import io
import re
from urllib.parse import urljoin, urlsplit

from scripts.participation_intake.contract import IntakeError, digest, pin

INDEX = ("https://www.in.gov/sos/elections/voter-information/register-to-vote/"
         "voter-registration-and-turnout-statistics/")
DATES = {2022: date(2022, 11, 8), 2024: date(2024, 11, 5), 2026: date(2026, 11, 3)}
FEEDS = {year: f"IN-{year}-general-turnout-and-registration" for year in DATES}
COUNTIES_SHA = "4e54cfbef1979708ffd5be41b5e6219d61ae23c08650a4080e03ed8aa1441f02"
HEADER = "County Registered Voters Voters Voting Turnout Election Day Vote Absentee Absentee"
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
ROW = re.compile(
    rf"(?:(?P<county>[A-Za-z. ]+?)\s{{2,}})?({NUMBER})\s+({NUMBER})\s+(\d+) %"
    rf"\s+({NUMBER})\s+({NUMBER})\s+(\d+) %"
)


def report_route(url):
    p = urlsplit(url)
    return (p.scheme == "https" and p.netloc == "www.in.gov" and not p.fragment
            and ((re.fullmatch(r"/dA/[0-9a-f]{10}/[A-Za-z0-9_.-]+\.pdf", p.path)
                  and p.query in ("", "language_id=1"))
                 or (re.fullmatch(r"/sos/elections/voter-information/files/[A-Za-z0-9_.-]+\.pdf", p.path)
                     and not p.query)))


def report_link(body, year):
    class Links(HTMLParser):
        href = None

        def __init__(self):
            super().__init__()
            self.matches = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.href = dict(attrs).get("href")
                self.text = []

        def handle_data(self, text):
            if self.href:
                self.text.append(text)

        def handle_endtag(self, tag):
            if tag == "a" and self.href:
                label = " ".join("".join(self.text).split())
                if label == f"{year} General Election Registration and Turnout Data":
                    self.matches.append(urljoin(INDEX, self.href))
                self.href = None

    parser = Links()
    parser.feed(body.decode("utf-8-sig"))
    parser.close()
    matches = set(parser.matches)
    if not matches:
        return None
    if len(matches) != 1 or not report_route(next(iter(matches))):
        raise ValueError("Indiana general-election report route is ambiguous or outside the reviewed archive")
    return next(iter(matches))


def parse_pages(pages, year):
    election = DATES[year]
    label = f"{election:%A, %B} {election.day}, {year}"
    if not 1 <= len(pages) <= 5:
        raise ValueError("Unexpected Indiana turnout report page inventory")
    facts, editions = [], set()
    for i, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if (len(lines) < 5 or lines[0] != f"{year} General Election"
                or " ".join(lines[1].split()) != label + " General Election Turnout and Registration"
                or " ".join(lines[2].split()) != HEADER):
            raise ValueError("Indiana general-election heading or columns changed")
        footer = re.fullmatch(rf"Page {i} of {len(pages)}\s+(.+)", lines[-1])
        if footer is None:
            raise ValueError("Indiana turnout report page footer changed")
        edition = datetime.strptime(footer[1], "%A, %B %d, %Y").date()
        editions.add(edition)
        if edition < election:
            raise ValueError("Indiana turnout report predates its election")
        for line in lines[3:-1]:
            match = ROW.fullmatch(line)
            if not match:
                raise ValueError("Indiana turnout row does not match the archive layout")
            county, *numbers = match.groups()
            facts.append([county or "", *(int(n.replace(",", "")) for n in numbers)])
    if len(editions) != 1:
        raise ValueError("Indiana turnout report contains mixed editions")
    return {"date": editions.pop().isoformat(), "year": year, "complete_native_query": facts,
            "participation_observation_qualified": False}


def query(data):
    facts = data["complete_native_query"]
    counties = sorted(row[0] for row in facts[:-1])
    if (len(facts) != 93 or facts[-1][0] != "" or len(set(counties)) != 92
            or digest(("\n".join(counties) + "\n").encode()) != COUNTIES_SHA
            or any(len(row) != 7 or any(type(n) is not int or n < 0 for n in row[1:]) for row in facts)):
        raise ValueError("Indiana turnout county inventory or row counts changed")
    for i in (1, 2, 4, 5):
        if facts[-1][i] != sum(row[i] for row in facts[:-1]):
            raise ValueError("Indiana statewide and county column totals do not reconcile")
    return facts


def collect(collector, year):
    def parse(body):
        url = report_link(body, year)
        if url is None:
            raise IntakeError("report_not_linked", f"No Indiana {year} general-election report linked in the official archive")
        original, _ = collector.acquire(url)
        source = {"url": url, **pin(original)}
        previous = (collector.prior.get(FEEDS[year]) or {}).get("data")
        if previous and previous.get("report") == source:
            return previous
        if not original.startswith(b"%PDF-") or len(original) > 5_000_000:
            raise ValueError("Invalid Indiana turnout archive PDF")
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(original)).pages
        if not 1 <= len(pages) <= 5:
            raise ValueError("Unexpected Indiana turnout report page inventory")
        data = parse_pages([page.extract_text(extraction_mode="layout") for page in pages], year)
        query(data)
        return {**data, "report": source}

    return collector.capture(FEEDS[year], INDEX, parse, equivalent=lambda old, new: old == new)


def rows(entries):
    result = []
    for year, feed in sorted(FEEDS.items(), reverse=True):
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None:
            continue
        report = data["report"]
        if (data["year"] != year or date.fromisoformat(data["date"]) < DATES[year]
                or entry["status"] not in ("reported", "retained_after_failure")
                or not report_route(report["url"]) or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                or type(report["bytes"]) is not int or not 0 < report["bytes"] <= 5_000_000):
            raise ValueError("Incompatible Indiana turnout source evidence")
        for county, registered, voted, printed, election_day, absentee, absentee_pct in query(data):
            gap = election_day + absentee - voted
            holds = []
            if not registered or not 0 <= voted <= registered:
                holds.append("invalid_registration_frame")
            elif abs(200 * voted - 2 * printed * registered) > registered:
                holds.append("reported_turnout_percentage_disagrees")
            if gap:
                holds.append("mode_counts_do_not_sum_to_voters_voting")
            if voted and abs(200 * absentee - 2 * absentee_pct * voted) > voted:
                holds.append("reported_absentee_percentage_disagrees")
            result.append({
                "state_code": "IN", "year": year, "election_date": DATES[year].isoformat(),
                "geography_level": "county" if county else "state", "geography": county or "Indiana",
                "registered_voters": registered, "voters_voting": voted, "printed_turnout_pct": printed,
                "election_day_vote": election_day, "absentee": absentee,
                "printed_absentee_pct": absentee_pct, "mode_count_minus_voters_voting": gap,
                "qualified_registered_fraction_pct": None if holds else 100 * voted / registered,
                "qualification_holds": holds, "source_status": entry["status"],
                "report_edition": data["date"], "source_url": report["url"], "source_sha256": report["sha256"],
                "source_bytes": report["bytes"],
            })
    return result
