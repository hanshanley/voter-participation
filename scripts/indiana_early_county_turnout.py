"""Reconcile Indiana's digital 1990–1998 county turnout reports."""

from datetime import datetime
from io import BytesIO
import re

from scripts.california_turnout_history import federal_general
from scripts.indiana_early_state_turnout import FOOT, fraction
from scripts.participation_intake.contract import IntakeError, digest, pin
from scripts.results_indiana_turnout import COUNTIES_SHA, INDEX, NUMBER
from scripts.results_turnout_history import archive_link, html_tables
from scripts.southeast_turnout import collect_report


FEEDS = {f"IN-{year}-early-county-turnout": year for year in range(1990, 1999, 2)}
URLS = {
    1990: "https://www.in.gov/dA/56566627ff/genl90.pdf?language_id=1",
    1992: "https://www.in.gov/dA/dfcdd3a85e/genl92.pdf?language_id=1",
    1994: "https://www.in.gov/dA/f19a3cf5d3/genl94.pdf?language_id=1",
    1996: INDEX + "1996-general-election-registration-and-turnout-data",
    1998: "https://www.in.gov/dA/3c1031e871/genl98.pdf?language_id=1",
}
CSV = "participation-in-early-county-turnout-history.csv"
MAX_BYTES = 500_000
TITLES = {1990: "1990 General Election - State of Indiana", 1992: "1992 General Election",
          1994: "GENERAL ELECTION - 1994", 1998: "1998 General Election Registration and Turnout"}
HEAD_1996 = [("INDIANA", "NO. REG.", "VOTER", "% OF RV", "VOTERS", "VOTING", "ELECTION", "COST PER"),
             ("COUNTY", "VOTERS", "TURNOUT", "TURNOUT", "IN PERSON", "ABSENTEE", "BUDGET", "VOTER")]
ROSTER = {
    1996: "95d5da027afa5328154d8c9de616c675fd4f2e55f184af5c0c3c3b50b630c9b3",
    1998: "d0b7d6e6893c610823cc53cc6264296771cc039f874c9d600d29a4b10649540a",
}
NAME = r"[A-Za-z. -]+"
PCT = r"\d{1,3}(?:\.\d{1,2})?"
ROW = re.compile(rf"({NAME}) ({NUMBER}) ({NUMBER}) ({PCT})% (?:(?:({NUMBER}) ({NUMBER}) ({PCT})%)|('not provided by county))")
ROW98 = re.compile(rf"(?:({NAME}) )?({NUMBER}) ({NUMBER}) ({PCT})%")
FOOTER_STAT = re.compile(r"(?:HIGH|LOW|AVG)-+ \d+\.\d%-+ \d+\.\d%")


def query(facts, year):
    roster = [row[0] for row in facts[:-1]]
    if (len(facts) != 93 or facts[-1][0] != "" or len(set(roster)) != 92
            or digest(("\n".join(sorted(roster)) + "\n").encode()) != ROSTER.get(year, COUNTIES_SHA)):
        raise ValueError("Indiana early county roster differs")
    values = []
    for name, registered, voted, printed, in_person, absentee, absentee_pct in facts:
        counts = (registered, voted, in_person, absentee)
        if (not all(x is None or re.fullmatch(NUMBER, x) for x in counts) or registered is None or voted is None
                or not re.fullmatch(PCT, printed) or (absentee_pct is not None and not re.fullmatch(PCT, absentee_pct))):
            raise ValueError("Indiana early county count or percentage changed")
        n, v, p, a = (int(x.replace(",", "")) if x is not None else None for x in counts)
        geo_hold = "source_county_identity_unresolved" if year == 1998 and name in ("Starke", "St. Joseph") else None
        gap = None if p is None or a is None else p + a - v
        rate, hold = fraction(v, n, printed + "%", estimated=False)
        hold = geo_hold or ("mode_counts_do_not_sum_to_voters_voting" if gap else hold)
        values.append({
            "state_code": "IN", "election_date": federal_general(year).isoformat(),
            "geography_level": "county" if name else "state", "native_geography": name or "INDIANA",
            "reported_registered_voters": n, "reported_voter_turnout": v, "reported_in_person": p,
            "reported_absentee": a, "printed_registered_pct": printed, "printed_absentee_pct": absentee_pct,
            "mode_count_minus_reported_turnout": gap, "geometry_hold": geo_hold,
            "qualified_registered_fraction_pct": None if hold else rate, "registration_fraction_hold": hold,
        })
    for key in ("reported_registered_voters", "reported_voter_turnout", "reported_in_person", "reported_absentee"):
        expected = values[-1][key]
        if expected is not None and expected != sum(row[key] or 0 for row in values[:-1]):
            raise ValueError("Indiana early county totals disagree with the state control")
    return values


def parse(original, year):
    if not 0 < len(original) <= MAX_BYTES:
        raise ValueError("Indiana early county report size differs")
    facts, editions = [], set()
    if year == 1996:
        tables = [t for t in html_tables(original) if t[:2] == HEAD_1996]
        if len(tables) != 1 or len(tables[0]) != 98 or not all(len(row) == 8 for row in tables[0]):
            raise ValueError("Indiana 1996 county table inventory differs")
        for name, reg, n, pct, p, a, _, _ in tables[0][2:]:
            if not name and not any((reg, n, pct, p, a)):
                continue
            facts.append(["" if name == "Totals" else name, reg, n, pct, p, a, None])
    else:
        from pypdf import PdfReader

        pages = PdfReader(BytesIO(original)).pages
        if len(pages) != 2:
            raise ValueError("Indiana early county page inventory differs")
        for i, page in enumerate(pages, 1):
            lines = [" ".join(s.split()) for s in page.extract_text(extraction_mode="layout").splitlines() if s.strip()]
            if i == 1 and (not lines or lines.pop(0) != TITLES[year]):
                raise ValueError("Indiana early county report title differs")
            if year == 1998:
                if i == 1 and lines.pop(0) != "County Number of Registered Voters Voter Turnout % Voter Turnout":
                    raise ValueError("Indiana 1998 source columns differ")
                for line in lines:
                    if not (match := ROW98.fullmatch(line)):
                        raise ValueError("Invalid Indiana 1998 county row")
                    name, reg, n, pct = match.groups()
                    facts.append([name or "", reg, n, pct, None, None, None])
                continue
            if i == 1:
                expected = (["County # Regis. Total Turnout Voting at Voting b% Voting",
                             "Voters Turnout % of RV Polls AbsenteeAbsentee"] if year == 1990 else
                            ["# Regis. Total Turnout Voting atVoting by% Voting",
                             "County Voters Turnout % of RV Polls Absentee Absentee"])
                if lines[:2] != expected:
                    raise ValueError("Indiana early county report columns differ")
                del lines[:2]
            elif lines.pop(0) != f"http://www.IN.gov/sos/elections/voters/genl{year % 100}.html":
                raise ValueError("Indiana early county continuation identity differs")
            footer = FOOT.fullmatch(lines.pop())
            if not footer or int(footer[1]) != i:
                raise ValueError("Indiana early county report footer differs")
            editions.add(datetime.strptime(footer[2], "%m/%d/%Y %I:%M %p").isoformat())
            for line in lines:
                if all(char == "=" for char in line) or FOOTER_STAT.fullmatch(line):
                    continue
                if not (match := ROW.fullmatch(line)):
                    raise ValueError("Invalid Indiana early county row")
                name, reg, n, pct, p, a, ap, missing = match.groups()
                if missing and not (year == 1994 and name == "Newton"):
                    raise ValueError("Unexpected missing Indiana mode data")
                facts.append(["" if name == "INDIANA" else name, reg, n, pct, p, a, ap])
    if len(editions) > 1:
        raise ValueError("Mixed Indiana early county report editions")
    query(facts, year)
    return {"year": year, "edition": next(iter(editions), None), "native_rows": facts,
            "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    year = FEEDS[feed]

    def checked(index, _):
        url = archive_link(index, INDEX, re.escape(URLS[year]))
        if url is None:
            raise IntakeError("report_not_linked", "Indiana does not link the reviewed county report")
        body, _ = collector.acquire(url)
        report = {"url": url, **pin(body)}
        previous = (collector.prior.get(feed) or {}).get("data")
        if previous and previous.get("report") == report:
            return previous
        data = parse(body, year)
        if previous and data["edition"] and previous["edition"] and previous["edition"] > data["edition"]:
            raise ValueError("Indiana early county report edition regressed")
        return {**data, "report": report}

    return collect_report(collector, feed, INDEX, checked,
                          reuse_checked_week=reuse_checked_week, shared_acquisition=True)


def exports(entries):
    result = []
    for feed, year in FEEDS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is None:
            continue
        report = data["report"]
        if (data["year"] != year or report["url"] != URLS[year]
                or entry["status"] not in ("reported", "retained_after_failure")):
            raise ValueError("Incompatible Indiana early county archive")
        result.extend({**row, "source_url": report["url"], "source_sha256": report["sha256"],
                       "report_edition": data["edition"], "source_status": entry["status"]}
                      for row in query(data["native_rows"], year))
    return result
