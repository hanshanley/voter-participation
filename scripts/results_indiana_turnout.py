"""Reconcile Indiana's statewide bulk turnout reports without repairing source counts."""

from datetime import date, datetime
from html.parser import HTMLParser
import io
import re
from urllib.parse import urljoin, urlsplit

from scripts.participation_intake.contract import IntakeError, digest, pin
from scripts.southeast_turnout import collect_report

INDEX = ("https://www.in.gov/sos/elections/voter-information/register-to-vote/"
         "voter-registration-and-turnout-statistics/")
DATES = {year: date(year, 11, day) for year, day in (
    (2008, 4), (2010, 2), (2012, 6), (2014, 4), (2016, 8), (2018, 6),
    (2020, 3), (2022, 8), (2024, 5), (2026, 3),
)}
FEEDS = {year: f"IN-{year}-general-turnout-and-registration" for year in DATES}
LEGACY_IN_PERSON = frozenset((2010, 2012, 2014, 2016))
MAX_BYTES = 5_000_000
COUNTIES_SHA = "4e54cfbef1979708ffd5be41b5e6219d61ae23c08650a4080e03ed8aa1441f02"
HEADER = "County Registered Voters Voters Voting Turnout Election Day Vote Absentee Absentee"
WORKSHEET_HEADER = ("Registered", "County Voters Voters Voting Turnout % Election Day Absentee Absentee %")
WORKSHEET_TITLE = "2018 General Election Turnout from the ENR page (2).xlsx"
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
ROW = re.compile(
    rf"(?:(?P<county>[A-Za-z. ]+?)\s{{2,}})?({NUMBER})\s+({NUMBER})\s+(\d+) %"
    rf"\s+({NUMBER})\s+({NUMBER})\s+(\d+) %"
)
WORKSHEET_ROW = re.compile(
    r"(?P<county>[A-Za-z. ]+) (\d+) (\d+) (\d+)% (\d+) (\d+) (\d+)%"
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
                if label in {f"{year} General Election Registration {join} Turnout Data" for join in ("and", "&")}:
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
        if year == 2018:
            if len(pages) != 3 or (i == 1 and tuple(" ".join(s.split()) for s in lines[:2]) != WORKSHEET_HEADER):
                raise ValueError("Indiana 2018 worksheet headings or page inventory changed")
            body, pattern = lines[2:] if i == 1 else lines, WORKSHEET_ROW
        elif year in LEGACY_IN_PERSON:
            if len(pages) != 2 or [" ".join(s.split()) for s in lines[:3]] != [
                f"{year} General Election General Election Turnout and Registration", label,
                HEADER.replace("Election Day Vote", "In Person"),
            ]:
                raise ValueError("Indiana in-person report heading or columns changed")
            body, pattern = lines[3:], ROW
        else:
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
            body, pattern = lines[3:-1], ROW
        for line in body:
            match = pattern.fullmatch(" ".join(line.split()) if year == 2018 else line)
            if not match:
                raise ValueError("Indiana turnout row does not match the archive layout")
            county, *numbers = match.groups()
            facts.append(["" if county == "Totals" and year == 2018 else county or "",
                          *(int(n.replace(",", "")) for n in numbers)])
    if len(editions) > 1:
        raise ValueError("Indiana turnout report contains mixed editions")
    return {"date": editions.pop().isoformat() if editions else None, "year": year, "complete_native_query": facts,
            "participation_observation_qualified": False}


def query(data):
    facts = data["complete_native_query"]
    counties = sorted("LaPorte" if row[0] == "La Porte" else row[0] for row in facts[:-1])
    if (len(facts) != 93 or facts[-1][0] != "" or len(set(counties)) != 92
            or digest(("\n".join(counties) + "\n").encode()) != COUNTIES_SHA
            or any(len(row) != 7 or any(type(n) is not int or n < 0 for n in row[1:]) for row in facts)):
        raise ValueError("Indiana turnout county inventory or row counts changed")
    for i in (1, 2, 4, 5):
        if facts[-1][i] != sum(row[i] for row in facts[:-1]):
            raise ValueError("Indiana statewide and county column totals do not reconcile")
    return facts


def parse(original, year):
    if not original.startswith(b"%PDF-") or len(original) > MAX_BYTES:
        raise ValueError("Invalid Indiana turnout archive PDF")
    if year in LEGACY_IN_PERSON or year == 2018:
        # Coordinate ordering preserves the printed column roles in these digital editions.
        import fitz
        with fitz.open(stream=original, filetype="pdf") as document:
            expected = 3 if year == 2018 else 2
            if len(document) != expected:
                raise ValueError("Unexpected Indiana turnout report page inventory")
            if year == 2018 and document.metadata.get("title") != WORKSHEET_TITLE:
                raise ValueError("Indiana worksheet election identity differs")
            pages = [page.get_text(sort=True) for page in document]
    else:
        from pypdf import PdfReader
        document = PdfReader(io.BytesIO(original))
        if not 1 <= len(document.pages) <= 5:
            raise ValueError("Unexpected Indiana turnout report page inventory")
        pages = [page.extract_text(extraction_mode="layout") for page in document.pages]
    data = parse_pages(pages, year)
    query(data)
    return data


def collect(collector, year, *, reuse_checked_week=False):
    def checked(body, feed):
        url = report_link(body, year)
        if url is None:
            raise IntakeError("report_not_linked", f"No Indiana {year} general-election report linked in the official archive")
        original, _ = collector.acquire(url)
        source = {"url": url, **pin(original)}
        previous = (collector.prior.get(feed) or {}).get("data")
        if previous and previous.get("report") == source:
            return previous
        return {**parse(original, year), "report": source}

    return collect_report(collector, FEEDS[year], INDEX, checked,
                          reuse_checked_week=reuse_checked_week and year < max(FEEDS), shared_acquisition=True)


def rows(entries):
    result = []
    for year, feed in sorted(FEEDS.items(), reverse=True):
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None:
            continue
        report = data["report"]
        unprinted_edition = year in LEGACY_IN_PERSON or year == 2018
        if (data["year"] != year
                or (data["date"] is None) != unprinted_edition
                or (data["date"] is not None and date.fromisoformat(data["date"]) < DATES[year])
                or entry["status"] not in ("reported", "retained_after_failure")
                or not report_route(report["url"]) or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
                or type(report["bytes"]) is not int or not 0 < report["bytes"] <= MAX_BYTES):
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
                "election_day_vote": None if year in LEGACY_IN_PERSON else election_day,
                "in_person": election_day if year in LEGACY_IN_PERSON else None, "absentee": absentee,
                "printed_absentee_pct": absentee_pct, "mode_count_minus_voters_voting": gap,
                "qualified_registered_fraction_pct": None if holds else 100 * voted / registered,
                "qualification_holds": holds, "source_status": entry["status"],
                "report_edition": data["date"], "source_url": report["url"], "source_sha256": report["sha256"],
                "source_bytes": report["bytes"],
            })
    return result
