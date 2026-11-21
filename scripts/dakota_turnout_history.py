"""Reconcile the Dakota election offices' statewide participation tables."""
from decimal import Decimal
import re

from scripts.kansas_turnout_history import rounded_percent
from scripts.participation_intake.contract import count
from scripts.southeast_turnout import collect_report


ND = "ND-statewide-general-turnout-history"
SD = "SD-statewide-general-turnout-history"
URLS = {
    ND: "https://www.sos.nd.gov/sites/www/files/documents/elections/election-results-pdfs/statistics-turnout.pdf",
    SD: "https://sdsos.gov/elections-voting/election-resources/election-history/registration_turnout.aspx",
}
EXTENSIONS = {ND: ".pdf", SD: ".html"}
MAX_BYTES = 2_000_000
CSV = "participation-dakota-statewide-turnout-history.csv"
ND_HEADER = (
    "Vote by In-Person",
    "No. of Total Votes Absentee Mail Votes Early No. of Vote by Turnout",
    "Year Type Precincts Cast Votes Cast Cast Votes Cast Population Eligible Voters Mail Counties Percentage",
)
ND_NOTES = (
    "Population and Eligible Voter estimates are provided by the U.S. Census Bureau. North Dakota Election Statistics",
    "All ballots were cast by mail in the 2020 Primary Election due to the Covid-19 pandemic. Page | ",
)
SD_REQUIRED = (
    "YEAR", "TOTAL REGISTRATION", "VOTING AGE POPUL.", "REG. % OF VAP",
    "TURNOUT", "TURNOUT % OF VAP", "TURNOUT % OF REG.", "PRECINCTS",
)
NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"


def election_roster(years, start):
    years = list(years)
    if not years or not 2024 <= years[-1] <= 2100 or years != list(range(start, years[-1] + 1, 2)):
        raise ValueError("Incomplete Dakota general-election roster")
    return years[-1]


def rate(numerator, denominator, printed):
    if not re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?%", printed) or not 0 < denominator:
        raise ValueError("Invalid Dakota participation percentage")
    shown = Decimal(printed[:-1])
    if not 0 <= shown <= 100:
        raise ValueError("Invalid Dakota participation percentage")
    if rounded_percent(numerator, denominator, -shown.as_tuple().exponent) != shown:
        return None, "published_percent_does_not_match_counts"
    return str(rounded_percent(numerator, denominator, 6)), ""


def nd_rows(native):
    rows = []
    seen = set()
    for line in native:
        columns = line.split()
        if (len(columns) != 11 or not re.fullmatch(r"\d{4}", columns[0])
                or columns[1] not in {"G", "P", "PP", "S"}
                or not all(re.fullmatch(NUMBER, columns[i]) for i in (2, 3, 7, 8))
                or not all(columns[i] == "-" or re.fullmatch(NUMBER, columns[i]) for i in (4, 5, 6, 9))):
            raise ValueError("North Dakota archive column roles differ")
        year, kind = int(columns[0]), columns[1]
        if (year, kind) in seen or not 1980 <= year <= 2100:
            raise ValueError("North Dakota archive contains duplicate or unexpected election")
        seen.add((year, kind))
        precincts, turnout, population, eligible = (count(columns[i]) for i in (2, 3, 7, 8))
        absentee, mail, early, mail_counties = (
            None if columns[i] == "-" else count(columns[i]) for i in (4, 5, 6, 9))
        if (not precincts or not 0 < turnout <= eligible <= population
                or sum(x or 0 for x in (absentee, mail, early)) > turnout or (mail_counties or 0) > 53):
            raise ValueError("North Dakota counts fail independent range or mode checks")
        qualified, hold = rate(turnout, eligible, columns[10])
        if kind == "G":
            rows.append({
                "state_code": "ND", "year": year, "reported_turnout": turnout,
                "turnout_measure": "total_votes_cast_state_election_statistics",
                "reported_precincts": precincts, "reported_absentee_votes": absentee, "reported_mail_votes": mail,
                "reported_early_in_person_votes": early, "reported_vote_by_mail_counties": mail_counties,
                "reported_population_estimate": population, "reported_eligible_voter_estimate": eligible,
                "printed_eligible_turnout_pct": columns[10], "qualified_eligible_turnout_pct": qualified,
                "eligible_turnout_hold": hold,
            })
    election_roster((row["year"] for row in rows), 1980)
    return rows


def sd_rows(native):
    if (not native or native[0][0] != "YEAR" or len({row[0] for row in native}) != len(native)
            or any(len(row) != len(native[0]) for row in native)):
        raise ValueError("South Dakota general-election table is incomplete")
    columns = {row[0]: row[1:] for row in native}
    if not set(SD_REQUIRED) <= columns.keys() or any(
            not re.fullmatch(r"\d{4}", year) for year in columns["YEAR"]):
        raise ValueError("South Dakota general-election labels differ")
    years = list(map(int, columns["YEAR"]))
    election_roster(years, 1988)
    rows = []
    for year, registered, vap, reg_printed, turnout, vap_printed, turnout_printed, precincts in zip(
            *(columns[key] for key in SD_REQUIRED), strict=True):
        registered, vap, turnout, precincts = map(count, (registered, vap, turnout, precincts))
        if not precincts or not 0 < turnout <= min(registered, vap):
            raise ValueError("South Dakota archive count roles do not reconcile")
        registered_rate, registered_hold = rate(turnout, registered, turnout_printed)
        vap_rate, vap_hold = rate(turnout, vap, vap_printed)
        _, registration_share_hold = rate(registered, vap, reg_printed)
        rows.append({
            "state_code": "SD", "year": int(year), "reported_turnout": turnout,
            "turnout_measure": "turnout_state_election_statistics", "reported_precincts": precincts,
            "reported_registered_voters": registered, "reported_voting_age_population": vap,
            "printed_registration_share_of_vap_pct": reg_printed,
            "registration_share_of_vap_hold": registration_share_hold,
            "printed_registered_turnout_pct": turnout_printed, "qualified_registered_turnout_pct": registered_rate,
            "registered_turnout_hold": registered_hold,
            "printed_vap_turnout_pct": vap_printed, "qualified_vap_turnout_pct": vap_rate, "vap_turnout_hold": vap_hold,
        })
    return rows


def parse(body, feed):
    if not 0 < len(body) <= MAX_BYTES:
        raise ValueError("Dakota statewide archive exceeds reviewed bounds")
    if feed == ND:
        import pymupdf

        if not body.startswith(b"%PDF-"):
            raise ValueError("North Dakota archive is not a PDF")
        with pymupdf.open(stream=body, filetype="pdf") as report:
            if report.needs_pass or not report.permissions & pymupdf.PDF_PERM_COPY or not 1 <= len(report) <= 6:
                raise ValueError("North Dakota archive permissions or page inventory differs")
            native = []
            for i, page in enumerate(report, 1):
                lines = [" ".join(line.split()) for line in page.get_text(sort=True).splitlines() if line.strip()]
                if i == 1:
                    if lines[:2] != ["NORTH DAKOTA ELECTION STATISTICS", "1980 – Present"]:
                        raise ValueError("North Dakota archive election range or title differs")
                    lines = lines[5:]
                if tuple(lines[:3]) != ND_HEADER or tuple(lines[-2:]) != (ND_NOTES[0], ND_NOTES[1] + str(i)):
                    raise ValueError("North Dakota archive headings or methodology notes differ")
                native.extend(lines[3:-2])
        rows = nd_rows(native)
    elif feed == SD:
        from scripts.results_turnout_history import html_tables

        html = body.decode("utf-8-sig")
        blocks = re.findall(r'<h2 class="blue_box_header">\s*GENERAL\s*</h2>\s*(<table>.*?</table>)', html, re.S)
        tables = html_tables(blocks[0].encode()) if len(blocks) == 1 else ()
        if len(tables) != 1:
            raise ValueError("South Dakota archive lacks its distinct general-election table")
        native = [list(row) for row in tables[0]]
        rows = sd_rows(native)
    else:
        raise ValueError("Unknown Dakota archive")
    return {"last_year": rows[-1]["year"], "complete_native_query": native,
            "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    def checked(body, identity):
        data = parse(body, identity)
        previous = (collector.prior.get(identity) or {}).get("data") or {}
        if data["last_year"] < previous.get("last_year", 2024):
            raise ValueError("Dakota archive election coverage regressed")
        return data

    return collect_report(collector, feed, URLS[feed], checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    from scripts.retained_bulk_turnout import disposition

    for feed, url in URLS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is None:
            continue
        source = entry["source"]
        if (entry["status"] not in {"reported", "retained_after_failure"} or source["url"] != url
                or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
                or type(source["bytes"]) is not int or not 0 < source["bytes"] <= MAX_BYTES):
            raise ValueError("Dakota statewide archive source lineage differs")
        rows = (nd_rows if feed == ND else sd_rows)(data["complete_native_query"])
        if rows[-1]["year"] != data["last_year"]:
            raise ValueError("Dakota statewide archive accepted year range differs")
        for row in rows:
            yield {**row, "geography_level": "state", "source_status": entry["status"], "source_url": url,
                   "source_sha256": source["sha256"], "source_bytes": source["bytes"], **disposition(entry),
                   "archive_checked_at": entry.get("first_observed_at")}
