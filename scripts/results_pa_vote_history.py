"""Reconcile Pennsylvania's public SURE vote-history and registration aggregates."""

import csv
import io
import math
import re
from urllib.parse import urlsplit

from scripts.participation_intake.contract import IntakeError, count, pin
from scripts.results_turnout_history import archive_link


INDEX = ("https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/"
         "voting-and-election-statistics/election-data")
YEARS = {2024: "2024-11-05", 2026: "2026-11-03"}
FEEDS = {year: f"PA-{year}-general-vote-history" for year in YEARS}
CONTRACT = "participation.pa_sure_general_vote_history.v1"
COUNTIES = (
    "ADAMS ALLEGHENY ARMSTRONG BEAVER BEDFORD BERKS BLAIR BRADFORD BUCKS BUTLER CAMBRIA CAMERON "
    "CARBON CENTRE CHESTER CLARION CLEARFIELD CLINTON COLUMBIA CRAWFORD CUMBERLAND DAUPHIN DELAWARE "
    "ELK ERIE FAYETTE FOREST FRANKLIN FULTON GREENE HUNTINGDON INDIANA JEFFERSON JUNIATA LACKAWANNA "
    "LANCASTER LAWRENCE LEBANON LEHIGH LUZERNE LYCOMING MCKEAN MERCER MIFFLIN MONROE MONTGOMERY MONTOUR "
    "NORTHAMPTON NORTHUMBERLAND PERRY PHILADELPHIA PIKE POTTER SCHUYLKILL SNYDER SOMERSET SULLIVAN "
    "SUSQUEHANNA TIOGA UNION VENANGO WARREN WASHINGTON WAYNE WESTMORELAND WYOMING YORK"
).split()
AGES = ("18 to 24", "25 to 34", "35 to 44", "45 to 54", "55 to 64", "65 to 74", "75+")
MODES = ("Absentee", "At Polls", "Mail-in", "Provisional")
AGE_RATE = " Percent Vote History/Registered Voters"
HEADERS = {
    "By county": ("County", "Vote History", "Registered voters", "Percent vote history/Registered voters"),
    "By vote method": ("County", *MODES),
    "By county & age": (
        "County", *(age + " Vote History" for age in AGES), *(age + " Voter Registration" for age in AGES),
        *(age + AGE_RATE for age in AGES),
    ),
}


def report_pattern(year):
    return (re.escape("https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/"
                      f"bulk-data/{year}-general-election/")
            + rf"voter(?:%20|-)+registration(?:%20|-)+(?:and(?:%20|-)+)?vote(?:%20|-)+history(?:%20|-)+"
              rf"summary(?:%20|-)+{year}(?:%20|-)+general\.xlsx")


def read_tables(body):
    from openpyxl import load_workbook

    if not body.startswith(b"PK\x03\x04") or len(body) > 8_000_000:
        raise ValueError("Invalid Pennsylvania public aggregate workbook")
    workbook = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        if not set(HEADERS) <= set(workbook.sheetnames):
            raise ValueError("Pennsylvania aggregate workbook is missing a required sheet")
        for sheet, header in HEADERS.items():
            native = workbook[sheet]
            if native.max_row != len(COUNTIES) + 2 or native.max_column != len(header):
                raise ValueError("Pennsylvania workbook query dimensions changed")
        return {sheet: [list(row) for row in workbook[sheet].values] for sheet in HEADERS}
    finally:
        workbook.close()


def queries(data):
    year, tables, report = data["year"], data["tables"], data["report"]
    if (year not in YEARS or data["election_date"] != YEARS[year]
            or not re.fullmatch(report_pattern(year), report["url"])
            or urlsplit(report["url"]).query or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])
            or type(report["bytes"]) is not int or not 0 < report["bytes"] <= 8_000_000
            or set(tables) != set(HEADERS)):
        raise ValueError("Incompatible Pennsylvania workbook scope or receipt")
    for sheet, header in HEADERS.items():
        rows = tables[sheet]
        native_header = tuple(rows[0])
        known_old_age_header = (*header[:15], "18 -24" + AGE_RATE, *header[16:])
        if (native_header != header and not (sheet == "By county & age" and year == 2024
                                             and native_header == known_old_age_header)
                or any(not isinstance(row, list) or len(row) != len(header) for row in rows)
                or [row[0].upper() for row in rows[1:]] != [*COUNTIES, "TOTAL"]):
            raise ValueError("Pennsylvania workbook county inventory or field definitions changed")

    def rate(voted, registered, printed):
        if (not 0 <= voted <= registered or registered <= 0 or type(printed) not in (int, float)
                or not math.isfinite(printed) or abs(100 * voted / registered - printed) > .00500001):
            raise ValueError("Pennsylvania vote-history counts and rate do not reconcile")
        return 100 * voted / registered

    result = []
    for total, modes, ages in zip(*(tables[name][1:] for name in HEADERS)):
        voted, registered = map(count, total[1:3])
        groups, populations = [list(map(count, ages[start:start + 7])) for start in (1, 8)]
        by_method = dict(zip(MODES, map(count, modes[1:])))
        if (sum(by_method.values()) != voted or sum(groups) > voted or sum(populations) > registered):
            raise ValueError("Pennsylvania method or age counts exceed or disagree with county totals")
        result.append({
            "county": total[0], "vote_history": voted, "registered": registered,
            "rate_pct": rate(voted, registered, total[3]), "vote_history_by_method": by_method,
            "ages": [{"age": age, "vote_history": x, "registered": n, "rate_pct": rate(x, n, pct)}
                     for age, x, n, pct in zip(AGES, groups, populations, ages[15:])],
            "age_not_tabulated": {"vote_history": voted - sum(groups), "registered": registered - sum(populations)},
        })
    for name, end in (("By county", 3), ("By vote method", 5), ("By county & age", 15)):
        cells = tables[name]
        if any(cells[-1][i] != sum(row[i] for row in cells[1:-1]) for i in range(1, end)):
            raise ValueError("Pennsylvania county rows do not reconcile to the statewide summary")
    return result


def collect(collector, year):
    def parse(body):
        url = archive_link(body, INDEX, report_pattern(year))
        if not url:
            raise IntakeError("report_not_linked", f"No public Pennsylvania {year} general vote-history workbook")
        workbook, _ = collector.acquire(url)
        data = {"year": year, "election_date": YEARS[year], "report": {"url": url, **pin(workbook)},
                "tables": read_tables(workbook), "participation_observation_qualified": False}
        queries(data)
        return data

    return collector.capture(FEEDS[year], INDEX, parse, equivalent=lambda old, new: old == new)


def exports(entries):
    by_edition, csv_rows = [], []
    for year, feed in FEEDS.items():
        entry = entries.get(feed, {})
        data = entry.get("data")
        if data is None:
            continue
        if data["year"] != year or entry["status"] not in ("reported", "retained_after_failure"):
            raise ValueError("Pennsylvania vote-history edition does not match the approved source")
        rows = queries(data)
        by_edition.append({
            "year": year, "election_date": data["election_date"], "status": entry["status"],
            "source": data["report"], "rows": rows,
        })
        for row in rows:
            for item in ({**row, "age": "All ages"}, *row["ages"]):
                csv_rows.append((year, data["election_date"], entry["status"], row["county"], item["age"],
                                 item["vote_history"], item["registered"], item["rate_pct"], data["report"]["url"]))
    if not csv_rows:
        return None, None
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("year", "election_date", "status", "county", "age", "vote_history", "registered",
                     "rate_pct", "source_url"))
    writer.writerows(csv_rows)
    return {
        "contract": CONTRACT, "state_code": "PA", "editions": by_edition,
        "measure": "Unique voters with vote history in SURE, a point-in-time administrative estimate",
        "denominator": "Registrations in the same source edition and geography and age group",
        "certified_ballots_cast": False, "geographic_allocation": False,
    }, stream.getvalue().encode()
