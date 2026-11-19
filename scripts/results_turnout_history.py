"""Read a public statewide general-election turnout series without guessing a missing year."""

import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html import unescape
from html.parser import HTMLParser
import io
import re
from urllib.parse import urljoin

from scripts.participation_intake.contract import count, encoded, pin


WA_FEED = "WA-general-election-turnout"
WA_URL = ("https://www.sos.wa.gov/elections/data-research/election-data-and-maps/"
          "reports-data-and-statistics/general-election-turnout")
WA_HEADER = ("Year", "Registered Voters", "Ballots Counted", "Turnout")
WA_FIRST = 1980
VA_FEED = "VA-general-election-turnout"
VA_URL = "https://www.elections.virginia.gov/resultsreports/registrationturnout-statistics/"
VA_HEADER = ("Year", "Total Registered", "Percentage Change from Previous Year", "Total Voting",
             "Turnout (% Voting of Total Registered)", "Voting Absentee (Included in Total Voting)")
VA_TITLE = "November General Elections: 1976 \u2013 Present"
VA_CERTIFICATION = ("The Department of Elections only publishes turnout statistics for November Elections "
                    "and turnout figures are only published after the election is certified.")
VA_FIELDS = ("native_year", "registration_change_literal", "voting_absentee_literal")
CURRENT_YEAR = 2026
KS_FEED = "KS-general-election-turnout-workbook"
KS_URL = "https://www.sos.ks.gov/elections/election-results.html"
KS_COUNTIES = {"bytes": 1737, "sha256": "a7dc594edcdb462f76861c8f1dfbc7f186b8929737c502771c7c3d264265b981"}
KS_HEADER = [["COUNTY", "ADVANCE BALLOTS", None, "TOTAL BALLOTS CAST", None, "REGISTERED"],
             [None, "RETURNED BY MAIL", None, None, None, "VOTERS"]]
NJ_FEED = "NJ-general-election-turnout-pdf"
NJ_URL = "https://www.nj.gov/state/elections/election-information-ballots-cast.shtml"
BUXTON_FEED = "ME-buxton-town-turnout"
BUXTON_URL = "https://www.buxton.me.us/news/11-3-2026-election-results"
BUXTON_TITLE = "Election Results for the Town of Buxton, Maine - November 3, 2026 State and Town Elections"
BUXTON_FIELDS = ("Registered Voters", "Absentee Ballots Cast", "Ballots Cast in Person",
                 "Total Ballots Cast", "Voter Turn Out Percent")
NJ_COUNTIES = (
    "Atlantic", "Bergen", "Burlington", "Camden", "Cape May", "Cumberland", "Essex",
    "Gloucester", "Hudson", "Hunterdon", "Mercer", "Middlesex", "Monmouth", "Morris", "Ocean",
    "Passaic", "Salem", "Somerset", "Sussex", "Union", "Warren",
)
NJ_HEADER = [
    "Total Number of Registered Voters, Ballots Cast, Ballots Rejected, Percentage of Ballots Cast and the",
    "Total Number of Election Districts in New Jersey",
    "COUNTY Total Number of Total Number of Total Number of Percent of Ballots Number of",
    "Registered Voters Ballots Cast Ballots Rejected Cast Election Districts",
]


def archive_link(body, url, pattern):
    class Links(HTMLParser):
        links = set()

        def handle_starttag(self, tag, attrs):
            if tag == "a" and (href := dict(attrs).get("href")):
                self.links.add(urljoin(url, href))

    parser = Links()
    parser.feed(body.decode("utf-8-sig"))
    links = [link for link in parser.links if re.fullmatch(pattern, link)]
    if len(links) > 1:
        raise ValueError("Ambiguous general-election turnout archive report")
    return links[0] if links else None


def kansas_link(body, year):
    return archive_link(body, KS_URL,
        rf"https://(?:www\.)?sos\.ks\.gov/elections/{year % 100:02d}elec/"
        rf"{year}-General-Election-Turnout-Information\.xlsx")


def new_jersey_report_url(year):
    return (r"https://(?:www\.)?nj\.gov/state/elections/assets/pdf/election-results/"
            rf"{year}/{year}-official-general-voter-turnout\.pdf")


def kansas_workbook(body):
    from openpyxl import load_workbook

    with io.BytesIO(body) as stream:
        workbook = load_workbook(stream, read_only=True, data_only=True)
        try:
            if len(workbook.worksheets) != 1 or workbook.active.max_column != 6 or not 110 <= workbook.active.max_row <= 150:
                raise ValueError("Kansas turnout workbook dimensions changed")
            rows = [list(row) for row in workbook.active.values]
        finally:
            workbook.close()
    if rows[:2] != KS_HEADER:
        raise ValueError("Kansas turnout workbook column labels changed")
    nonblank = [row for row in rows[2:] if any(value is not None for value in row)]
    if len(nonblank) != 106 or any(row[2] is not None or row[4] is not None for row in nonblank):
        raise ValueError("Kansas turnout workbook row inventory changed")
    counties, total = nonblank[:-1], nonblank[-1]
    query = {"counties": [[row[0], row[1], row[3], row[5]] for row in counties],
             "total": [total[1], total[3], total[5]]}
    if total[0] not in (None, "TOTAL", "STATE TOTAL"):
        raise ValueError("Kansas turnout workbook statewide selector changed")
    kansas_controls(query, allow_county_conflicts=True)
    return query


def kansas_controls(query, *, allow_county_conflicts=False):
    counties, total = query["counties"], query["total"]
    if (len(counties) != 105 or any(len(row) != 4 or not isinstance(row[0], str) for row in counties)
            or pin(encoded(sorted(row[0] for row in counties))) != KS_COUNTIES
            or len(total) != 3):
        raise ValueError("Kansas turnout county identities changed")
    for mail, ballots, registered in [row[1:] for row in counties] + [total]:
        if (type(ballots) is not int or type(registered) is not int or min(ballots, registered) < 0
                or not (mail == "N/A" or type(mail) is int and 0 <= mail <= ballots)):
            raise ValueError("Invalid Kansas turnout workbook figures")
    if (sum(row[2] for row in counties) != total[1] or sum(row[3] for row in counties) != total[2]
            or not 0 < total[1] <= total[2]):
        raise ValueError("Kansas county and statewide totals disagree")
    conflicts = [name for name, _, ballots, registered in counties if ballots > registered]
    if conflicts and not allow_county_conflicts:
        raise ValueError("Kansas county ballot counts exceed reported registrations: " + ", ".join(conflicts))
    return total[1], total[2]


def collect_kansas(collector):
    def parse(index):
        url = kansas_link(index, CURRENT_YEAR)
        if url is None:
            if (collector.prior.get(KS_FEED, {}).get("data") or {}).get("report"):
                raise ValueError("Previously reported Kansas turnout workbook is no longer linked")
            return {"current_election_status": "workbook_not_linked", "participation_observation_qualified": False}
        body, _ = collector.acquire(url)
        if len(body) > 2_000_000:
            raise ValueError("Kansas turnout workbook exceeds reviewed size bound")
        query = kansas_workbook(body)
        kansas_controls(query)
        return {"report": {"url": url, **pin(body)}, "complete_native_query": query,
                "current_election_status": "row_published", "participation_observation_qualified": False}

    return collector.capture(KS_FEED, KS_URL, parse)


def new_jersey_controls(query, election_date):
    counties, total = query["counties"], query["total"]
    if (query["election_date"] != election_date
            or query["published_date"] < election_date
            or [row["county"] for row in counties] != list(NJ_COUNTIES)
            or total["county"] != "TOTAL"):
        raise ValueError("New Jersey turnout report election or county inventory changed")
    fields = ("registered", "ballots_cast", "ballots_rejected", "election_districts")
    for row in counties + [total]:
        registered, ballots, rejected, districts = (row[field] for field in fields)
        reported = row["printed_percent"]
        if (any(type(row[field]) is not int for field in fields)
                or not registered or not 0 <= ballots <= registered
                or rejected < 0 or districts <= 0
                or type(reported) is not int
                or reported != (Decimal(ballots) * 100 / registered).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP)):
            raise ValueError("New Jersey turnout report has an invalid count or printed percentage")
    if any(total[field] != sum(row[field] for row in counties) for field in fields):
        raise ValueError("New Jersey turnout report county and statewide totals disagree")
    return total["ballots_cast"], total["registered"]


def new_jersey_report(body, election_date):
    from pypdf import PdfReader

    if len(body) > 2_000_000 or not body.startswith(b"%PDF-"):
        raise ValueError("New Jersey turnout report is not a bounded PDF")
    pdf = PdfReader(io.BytesIO(body))
    if pdf.is_encrypted or len(pdf.pages) != 1:
        raise ValueError("New Jersey turnout report page inventory changed")
    lines = [" ".join(line.split()) for line in
             pdf.pages[0].extract_text(extraction_mode="layout").splitlines() if line.strip()]
    if len(lines) != 28 or lines[:2] + lines[3:5] != NJ_HEADER:
        raise ValueError("New Jersey turnout report headings or row inventory changed")
    election = datetime.strptime(lines[2], "General Election %B %d, %Y").date().isoformat()
    published = datetime.strptime(lines[-1], "NJDOE-%m/%d/%Y").date().isoformat()
    rows = []
    number = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
    for county, line in zip((*NJ_COUNTIES, "TOTAL"), lines[5:-1]):
        match = re.fullmatch(re.escape(county) + rf" ({number}) ({number}) ({number}) ([0-9]+)% ({number})",
                             line)
        if not match:
            raise ValueError("New Jersey official turnout row changed: " + county)
        values = [int(value.replace(",", "")) for value in match.groups()]
        rows.append(dict(zip(("county", "registered", "ballots_cast", "ballots_rejected",
                              "printed_percent", "election_districts"), (county, *values))))
    query = {"election_date": election, "published_date": published,
             "counties": rows[:-1], "total": rows[-1]}
    new_jersey_controls(query, election_date)
    return query


def collect_new_jersey(collector):
    def parse(index):
        url = archive_link(index, NJ_URL, new_jersey_report_url(CURRENT_YEAR))
        prior = collector.prior.get(NJ_FEED, {}).get("data") or {}
        if url is None:
            if prior.get("report"):
                raise ValueError("Previously reported New Jersey turnout PDF is no longer linked")
            return {"current_election_status": "report_not_linked", "participation_observation_qualified": False}
        body, _ = collector.acquire(url)
        query = new_jersey_report(body, "2026-11-03")
        return {"report": {"url": url, **pin(body)}, "complete_native_query": query,
                "date": query["published_date"], "current_election_status": "row_published",
                "participation_observation_qualified": False}

    return collector.capture(NJ_FEED, NJ_URL, parse)


def buxton_controls(data):
    source, query = data["report"], data["complete_native_query"]
    if (source["url"] != BUXTON_URL or type(source["bytes"]) is not int or source["bytes"] <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
            or query["heading"] != BUXTON_TITLE or len(query["statistics"]) != len(BUXTON_FIELDS)):
        raise ValueError("Buxton town election identity or source receipt changed")
    values = []
    for label, line in zip(BUXTON_FIELDS, query["statistics"]):
        number = r"[0-9]+\.[0-9]{2}%" if label == BUXTON_FIELDS[-1] else r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"
        match = re.fullmatch(f"({number}) {label}", line)
        if not match:
            raise ValueError("Buxton town statistic missing or changed: " + label)
        values.append(match[1])
    registered, absentee, in_person, ballots = (int(value.replace(",", "")) for value in values[:-1])
    pct = values[-1]
    if (not registered or ballots > registered or absentee + in_person != ballots
            or (Decimal(ballots) * 100 / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(pct[:-1])):
        raise ValueError("Buxton town ballot components, register or printed rate disagree")
    return ballots, registered, pct


def buxton_report(body):
    class Blocks(HTMLParser):
        inside = False
        text = None
        tag = None

        def __init__(self):
            super().__init__()
            self.blocks = []

        def handle_starttag(self, tag, attrs):
            if tag == "article":
                self.inside = True
            if self.inside and tag in {"h2", "p"}:
                self.tag, self.text = tag, []

        def handle_data(self, text):
            if self.text is not None:
                self.text.append(text)

        def handle_endtag(self, tag):
            if tag == self.tag:
                self.blocks.append((tag, " ".join("".join(self.text).split())))
                self.tag = self.text = None
            if tag == "article":
                self.inside = False

    parser = Blocks()
    parser.feed(body.decode("utf-8-sig"))
    headings = [i for i, block in enumerate(parser.blocks) if block == ("h2", BUXTON_TITLE)]
    if len(headings) != 1:
        raise ValueError("Missing or repeated Buxton state-and-town election heading")
    start = headings[0] + 1
    fields = parser.blocks[start:start + 6]
    if not fields or fields[-1] != ("p", "State of Maine General Election") or any(
            tag != "p" for tag, _ in fields):
        raise ValueError("Buxton turnout is not in the reviewed pre-contest section")
    data = {"report": {"url": BUXTON_URL, **pin(body)}, "complete_native_query": {
        "heading": BUXTON_TITLE, "statistics": [text for _, text in fields[:-1]]}}
    buxton_controls(data)
    return data


def collect_buxton(collector):
    return collector.capture(BUXTON_FEED, BUXTON_URL, buxton_report)


def integer(value):
    if not re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", value):
        raise ValueError("Turnout table needs literal integer counts")
    return count(value.replace(",", ""))


def table_rows(rows, first, last):
    result = []
    for cells in rows:
        if len(cells) != 4 or not re.fullmatch(r"[0-9]{4}", cells[0]) or not re.fullmatch(
                r"[0-9]{1,3}(?:\.[0-9]{1,2})?%", cells[3]):
            raise ValueError("Turnout table row schema changed")
        year, registered, ballots, printed = int(cells[0]), integer(cells[1]), integer(cells[2]), cells[3]
        if registered is None or ballots is None or not 0 <= ballots <= registered or not registered:
            raise ValueError("Turnout table count is missing or outside its register")
        digits = len(printed.partition(".")[2].removesuffix("%"))
        period = Decimal(1).scaleb(-digits)
        rounded = (Decimal(ballots) * 100 / registered).quantize(period, rounding=ROUND_HALF_UP)
        result.append({"year": year, "registered_voters": registered, "ballots_counted": ballots,
                       "published_turnout": printed, "rate_qualified": rounded == Decimal(printed[:-1])})
    years = [r["year"] for r in result]
    if years not in (list(range(last, first - 1, -1)), list(range(last - 1, first - 1, -1))):
        raise ValueError("Unexpected election-year inventory; missing years are never zero")
    return result


def html_tables(body):
    from scripts.results_granular import FactualHTMLTables

    parser = FactualHTMLTables()
    parser.feed(body.decode("utf-8-sig"))
    return [[tuple(" ".join(cell["value"].split()) for cell in row["cells"]) for row in table["rows"]]
            for table in parser.tables]


def parse_washington(body):
    candidates = [rows[1:] for rows in html_tables(body) if rows and rows[0] == WA_HEADER]
    if len(candidates) != 1:
        raise ValueError("Missing or ambiguous Washington general-election turnout table")
    facts = table_rows(candidates[0], WA_FIRST, CURRENT_YEAR)
    return history_query(facts)


def parse_virginia(body):
    tables = [rows[2:] for rows in html_tables(body) if rows[:2] == [(VA_TITLE,), VA_HEADER]]
    notes = [" ".join(unescape(text).split()) for text in re.findall(
        r"<p>(\*[^<]+|The Department of Elections only publishes turnout statistics[^<]+)</p>",
        body.decode("utf-8-sig"))]
    if len(tables) != 1 or len(notes) != 4 or notes[0] != VA_CERTIFICATION:
        raise ValueError("Virginia November election table, certification policy or footnotes changed")
    native = tables[0]
    for row in native:
        if (len(row) != 6 or not re.fullmatch(r"[0-9]{4}\*?", row[0])
                or "*" in row[0] and row[0] != "1996*"):
            raise ValueError("Virginia November election row schema changed")
    facts = table_rows([(year.rstrip("*"), register, voting, rate)
                        for year, register, _, voting, rate, _ in native], 1976, CURRENT_YEAR)
    for row, (year, _, change, _, _, absentee) in zip(facts, native):
        if absentee != "***" and not 0 <= integer(absentee) <= row["ballots_counted"]:
            raise ValueError("Virginia absentee count is incompatible with Total Voting")
        row.update(zip(VA_FIELDS, (year, change, absentee)))
    query = history_query(facts)
    for row in facts:
        row["total_voting"] = row.pop("ballots_counted")
    return {**query, "native_measure": "Total Voting", "published_after_certification": True,
            "registered_includes": ["active", "inactive", "overseas"],
            "historical_qualifications": ["Virginia implemented NVRA in March 1996.",
                "** marks earlier roll purges; *** marks no separately reported absentee total."]}


def history_query(facts):
    if facts[0]["year"] == CURRENT_YEAR and not facts[0]["ballots_counted"]:
        raise ValueError("Current statewide count must be positive")
    return {"complete_native_query": facts,
            "current_election_status": "row_published" if facts[0]["year"] == CURRENT_YEAR else "not_yet_published",
            "participation_observation_qualified": False}


def collect_history(collector, feed, url, parser):
    def parse(body):
        data = parser(body)
        previous = (collector.prior.get(feed) or {}).get("data") or {}
        if (previous.get("current_election_status") == "row_published"
                and data["current_election_status"] != "row_published"):
            raise ValueError("Previously published general-election row is missing")
        return data

    return collector.capture(feed, url, parse)


def collect_washington(collector):
    return collect_history(collector, WA_FEED, WA_URL, parse_washington)


def collect_virginia(collector):
    return collect_history(collector, VA_FEED, VA_URL, parse_virginia)


def history_csv(entry, *, virginia=False):
    out = io.StringIO(newline="")
    count_field = "total_voting" if virginia else "ballots_counted"
    columns = ("year", "registered_voters", count_field, "published_turnout", "rate_qualified")
    columns += (VA_FIELDS if virginia else ()) + ("publication_status", "source_url", "source_sha256")
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in entry["data"]["complete_native_query"]:
        writer.writerow({**row, "publication_status": entry["status"],
                         "source_url": VA_URL if virginia else WA_URL, "source_sha256": entry["source"]["sha256"]})
    return out.getvalue().encode()


def washington_csv(entry):
    return history_csv(entry)
