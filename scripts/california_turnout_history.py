"""Batch intake for California's statewide general and special election history."""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import re

from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_turnout_history import archive_link
from scripts.southeast_turnout import collect_report


FEED = "CA-statewide-general-special-turnout-history"
CSV = "participation-ca-statewide-general-special-turnout-history.csv"
INDEX = "https://www.sos.ca.gov/elections/statistics"
ROUTE = (
    r"https://(?:elections\.cdn\.sos\.ca\.gov|admin\.cdn\.sos\.ca\.gov/elections)"
    r"/sov/(\d{4})-(general|special)/sov/04-historical-voter-reg-general\.pdf"
)
TITLE = "PARTICIPATION IN STATEWIDE GENERAL AND SPECIAL ELECTIONS 1910-"
LABEL = r"Historical Voter Registration and Participation in Statewide General and Special Elections 1910-\d{4}\s*\(PDF\)"
HEADER = ("HISTORICAL VOTER REGISTRATION AND", "Registration Turnout", "Turnout Turnout",
          "Election Date Eligible Democratic Republican Other Total Total Voters Registered Eligible")
MAX_BYTES = 500_000
INTEGER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+|\*)"
PERCENT = r"(?:[0-9]{1,3}\.[0-9]{2}%|\*)"
ROW = re.compile(rf"([A-Z][a-z]{{2}}\.? \d{{1,2}}, \d{{4}})(?: ([PS]))? "
                 rf"((?:{INTEGER} ){{6}}{PERCENT} {PERCENT})")


def federal_general(year):
    nov = date(year, 11, 1)
    return nov + timedelta(days=(7 - nov.weekday()) % 7 + 1)


def percentage(voted, denominator, printed):
    if not denominator or printed == "*":
        return "denominator_or_percentage_not_reported"
    if voted > denominator:
        return "voters_exceed_denominator"
    calculated = (Decimal(voted) * 100 / denominator).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return None if calculated == Decimal(printed[:-1]) else "printed_percentage_disagrees"


def query(lines, *, url):
    edition = re.fullmatch(ROUTE, url)
    if not edition:
        raise ValueError("Unreviewed California statewide history route")
    year, kind = int(edition[1]), edition[2]
    rows = []
    for line in lines:
        match = ROW.fullmatch(line)
        if not match:
            raise ValueError("Invalid native California statewide history row")
        election = datetime.strptime(match[1].replace(".", ""), "%b %d, %Y").date()
        marker = match[2] or ""
        if marker != "S" and (election != federal_general(election.year)
                              or marker != ("P" if election.year % 4 == 0 else "")):
            raise ValueError("California federal general election date or marker differs")
        *counts, printed_registered, printed_eligible = match[3].split()
        eligible, democrats, republicans, other, registered, voted = (
            int(x.replace(",", "")) if x != "*" else None for x in counts
        )
        if not voted or not eligible or (registered is None) != (election.year == 1910):
            raise ValueError("California statewide turnout count or denominator inventory differs")
        components = (democrats, republicans, other)
        if (all(x is None for x in components) if election.year >= 1922
                else any(x is not None for x in components)):
            raise ValueError("California historical registration columns differ")
        if election.year >= 1922 and any(x is None for x in components):
            raise ValueError("Incomplete California registration components")
        registration_difference = (sum(components) - registered if democrats is not None else None)
        registration_hold = ("registration_components_disagree" if registration_difference
                             else percentage(voted, registered, printed_registered))
        eligible_hold = percentage(voted, eligible, printed_eligible)
        rows.append({
            "election_date": election.isoformat(),
            "election_type": {"P": "presidential", "S": "statewide_special", "": "midterm"}[marker],
            "reported_total_voters": voted, "reported_registered_voters": registered,
            "reported_eligible": eligible, "printed_registered_pct": printed_registered,
            "printed_eligible_pct": printed_eligible, "registration_component_difference": registration_difference,
            "registered_hold_reason": registration_hold, "eligible_hold_reason": eligible_hold,
            "qualified_registered_pct": None if registration_hold else 100 * voted / registered,
            "qualified_eligible_pct": None if eligible_hold else 100 * voted / eligible,
        })
    dates = [row["election_date"] for row in rows]
    last_general = year - (year % 2)
    expected = [federal_general(y).isoformat() for y in range(1910, last_general + 1, 2)]
    if (not dates or dates != sorted(set(dates)) or int(dates[-1][:4]) != year
            or (rows[-1]["election_type"] == "statewide_special") != (kind == "special")
            or [row["election_date"] for row in rows if row["election_type"] != "statewide_special"] != expected):
        raise ValueError("California statewide history election coverage differs")
    return rows


def parse(body, *, url):
    from pypdf import PdfReader

    edition = re.fullmatch(ROUTE, url)
    if not edition or not 0 < len(body) <= MAX_BYTES or not body.startswith(b"%PDF-"):
        raise ValueError("Not a bounded California statewide history PDF")
    pdf = PdfReader(BytesIO(body))
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 4:
        raise ValueError("Unexpected California statewide history page inventory")
    native_lines, notes = [], []
    for page_number, page in enumerate(pdf.pages):
        lines = [" ".join(line.split()) for line in page.extract_text(extraction_mode="layout").splitlines()
                 if line.strip()]
        title = TITLE + edition[1] + (" (continued)" if page_number else "")
        if lines[:5] != [HEADER[0], title, *HEADER[1:]]:
            raise ValueError("California statewide history title or column roles differ")
        table = lines[5:]
        if table and re.fullmatch(r"[0-9]{1,3}", table[-1]):
            table.pop()
        if "Notes" in table:
            before, after = table.index("Notes"), table[table.index("Notes") + 1:]
            if page_number != len(pdf.pages) - 1:
                raise ValueError("Notes precede the end of the California statewide table")
            notes, table = after, table[:before]
        native_lines.extend(table)
    if not {"P indicates a presidential election year.", "S indicates a statewide special election.",
            "* Indicates information not available."}.issubset(notes):
        raise ValueError("California statewide history marker definitions changed")
    rows = query(native_lines, url=url)
    return {"edition_year": int(edition[1]), "native_lines": native_lines, "notes": notes,
            "latest_election_date": rows[-1]["election_date"], "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    prior = (collector.prior.get(feed) or {}).get("data") or {}

    def checked(index, _):
        url = archive_link(index, INDEX, ROUTE, label=LABEL)
        if not url:
            raise IntakeError("report_not_linked", "California statewide general and special history not linked")
        original, _ = collector.acquire(url)
        report = {"url": url, **pin(original)}
        if prior.get("report") == report:
            return prior
        facts = parse(original, url=url)
        if (facts["latest_election_date"] > collector.observation_time().date().isoformat()
                or prior and facts["latest_election_date"] < prior["latest_election_date"]):
            raise ValueError("California statewide history election date is future-dated or regressed")
        if prior:
            old_dates = {row["election_date"] for row in query(prior["native_lines"], url=prior["report"]["url"])}
            new_dates = {row["election_date"] for row in query(facts["native_lines"], url=url)}
            if not old_dates <= new_dates:
                raise ValueError("California statewide history dropped published elections")
        return {"report": report, **facts}

    return collect_report(collector, feed, INDEX, checked, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return []
    report = data["report"]
    rows = query(data["native_lines"], url=report["url"])
    if (entry["status"] not in {"reported", "retained_after_failure"}
            or rows[-1]["election_date"] != data["latest_election_date"]
            or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])):
        raise ValueError("Unreviewed California statewide history evidence")
    return [{"state_code": "CA", "geography_level": "state", "participation_measure": "total_voters",
             "source_status": entry["status"], "report_edition_year": data["edition_year"],
             "source_url": report["url"], "source_sha256": report["sha256"], **row} for row in rows]
