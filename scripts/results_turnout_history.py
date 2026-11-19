"""Read a public statewide general-election turnout series without guessing a missing year."""

import csv
from decimal import Decimal, ROUND_HALF_UP
import io
import re

from scripts.participation_intake.contract import count


WA_FEED = "WA-general-election-turnout"
WA_URL = ("https://www.sos.wa.gov/elections/data-research/election-data-and-maps/"
          "reports-data-and-statistics/general-election-turnout")
WA_HEADER = ("Year", "Registered Voters", "Ballots Counted", "Turnout")
WA_FIRST = 1980
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


def parse_washington(body):
    from scripts.results_granular import FactualHTMLTables

    parser = FactualHTMLTables()
    parser.feed(body.decode("utf-8-sig"))
    candidates = []
    for table in parser.tables:
        rows = [tuple(" ".join(cell["value"].split()) for cell in row["cells"]) for row in table["rows"]]
        if rows and rows[0] == WA_HEADER:
            candidates.append(rows[1:])
    if len(candidates) != 1:
        raise ValueError("Missing or ambiguous Washington general-election turnout table")
    facts = table_rows(candidates[0], WA_FIRST, CURRENT_YEAR)
    if facts[0]["year"] == CURRENT_YEAR and not facts[0]["ballots_counted"]:
        raise ValueError("Current Washington statewide count must be positive")
    return {"complete_native_query": facts,
            "current_election_status": "row_published" if facts[0]["year"] == CURRENT_YEAR else "not_yet_published",
            "participation_observation_qualified": False}


def collect_washington(collector):
    def parse(body):
        data = parse_washington(body)
        previous = (collector.prior.get(WA_FEED) or {}).get("data") or {}
        if (previous.get("current_election_status") == "row_published"
                and data["current_election_status"] != "row_published"):
            raise ValueError("Previously published Washington general-election row is missing")
        return data

    return collector.capture(WA_FEED, WA_URL, parse)


def washington_csv(entry):
    out = io.StringIO(newline="")
    columns = ("year", "registered_voters", "ballots_counted", "published_turnout", "rate_qualified",
               "publication_status", "source_url", "source_sha256")
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in entry["data"]["complete_native_query"]:
        writer.writerow({**row, "publication_status": entry["status"], "source_url": WA_URL,
                         "source_sha256": entry["source"]["sha256"]})
    return out.getvalue().encode()
