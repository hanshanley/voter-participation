"""Read a public statewide general-election turnout series without guessing a missing year."""

import csv
from decimal import Decimal, ROUND_HALF_UP
from html import unescape
import io
import re

from scripts.participation_intake.contract import count


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
