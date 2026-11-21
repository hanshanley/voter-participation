"""Reproduce the statewide counts in Indiana's early participation summary."""

from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re

from scripts.california_turnout_history import federal_general
from scripts.participation_intake.contract import IntakeError, pin
from scripts.results_indiana_turnout import INDEX, NUMBER
from scripts.results_turnout_history import archive_link
from scripts.southeast_turnout import collect_report


FEED = "IN-early-statewide-turnout-history"
CSV = "participation-in-early-statewide-turnout-history.csv"
URL = "https://www.in.gov/dA/4371f6fa9f/particip.pdf?language_id=1"
MAX_BYTES = 500_000
HEAD = [
    "HISTORY OF VOTER PARTICIPATION IN INDIANA",
    "Year # Reg. Voters Turnout % of RV Voting Age % of VAP % of VAP",
    "Turnout Population Turnout Registered",
]
NOTE = "NOTE: Numbers ending in 00 are estimates"
PCT = r"(?:[0-9]{1,3}\.[0-9]%|unknown)"
ROW = re.compile(rf"(\d{{4}}) ({NUMBER}|unknown) ({NUMBER}) ({PCT}) ({NUMBER}) ({PCT}) ({PCT})")
FOOT = re.compile(r"([12]) ?of ?2 (\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2} [AP]M)")
PRESIDENTIAL, MIDTERM = "Presidential Elections", "Mid-Term Elections"


def fraction(n, r, printed, *, estimated):
    if not r or printed == "unknown":
        return None, "not_reported"
    if estimated:
        return None, "source_estimate"
    if not 0 <= n <= r:
        return None, "invalid_denominator"
    native = Decimal(printed[:-1])
    half_unit = Decimal(".5").scaleb(native.as_tuple().exponent)
    if abs(Decimal(n) * 100 / r - native) > half_unit:
        return None, "printed_percentage_disagrees"
    return 100 * n / r, None


def query(lines):
    if not lines or lines[0] != PRESIDENTIAL or lines.count(MIDTERM) != 1:
        raise ValueError("Indiana statewide election categories differ")
    middle = lines.index(MIDTERM)
    result = []
    for data, years, category in ((lines[1:middle], range(1996, 1947, -4), "presidential"),
                                  (lines[middle + 1:], range(1994, 1953, -4), "midterm")):
        for line, year in zip(data, years, strict=True):
            if not (row := ROW.fullmatch(line)) or int(row[1]) != year:
                raise ValueError("Indiana statewide election roster or row differs")
            _, registered, voters, printed_reg, vap, printed_vap, printed_reg_vap = row.groups()
            r, n, v = (None if x == "unknown" else int(x.replace(",", "")) for x in (registered, voters, vap))
            estimated_voters, estimated_reg = voters.endswith("00"), registered.endswith("00")
            pct, hold = fraction(n, r, printed_reg, estimated=estimated_voters or estimated_reg)
            result.append({
                "state_code": "IN", "election_date": federal_general(year).isoformat(), "election_type": category,
                "reported_participants": n, "reported_registrations": r, "reported_voting_age_population": v,
                "participants_flagged_as_source_estimate": estimated_voters,
                "registrations_flagged_as_source_estimate": estimated_reg,
                "vap_flagged_as_source_estimate": vap.endswith("00"),
                "printed_registered_pct": printed_reg, "printed_vap_turnout_pct": printed_vap,
                "printed_vap_registered_pct": printed_reg_vap,
                "qualified_registered_fraction_pct": pct, "registration_fraction_hold": hold,
            })
    return sorted(result, key=lambda row: row["election_date"])


def parse(original):
    from pypdf import PdfReader

    if not original.startswith(b"%PDF-") or len(original) > MAX_BYTES:
        raise ValueError("Expected bounded Indiana statewide turnout PDF")
    pages = PdfReader(BytesIO(original)).pages
    if len(pages) != 2:
        raise ValueError("Unexpected Indiana statewide turnout page count")
    dates, body = set(), []
    for index, page in enumerate(pages, 1):
        lines = [" ".join(s.split()) for s in page.extract_text(extraction_mode="layout").splitlines() if s.strip()]
        if (len(lines) < 4 or index == 1 and lines[:3] != HEAD
                or index == 2 and (lines[0] != "http://www.IN.gov/sos/elections/voters/particip.html" or lines[-2] != NOTE)
                or not (foot := FOOT.fullmatch(lines[-1])) or int(foot[1]) != index):
            raise ValueError("Indiana statewide title, page numbering or estimate note differs")
        dates.add(datetime.strptime(foot[2], "%m/%d/%Y %I:%M %p").isoformat())
        body.extend(line for line in (lines[3:-1] if index == 1 else lines[1:-2])
                    if not line.startswith("Average ") and not all(char == "_" for char in line))
    if len(dates) != 1:
        raise ValueError("Mixed Indiana statewide summary editions")
    query(body)
    return {"edition": dates.pop(), "native_lines": body, "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    def checked(index, _):
        url = archive_link(index, INDEX, re.escape(URL))
        if url is None:
            raise IntakeError("report_not_linked", "Indiana does not link the reviewed statewide history")
        body, _ = collector.acquire(url)
        report = {"url": url, **pin(body)}
        previous = (collector.prior.get(feed) or {}).get("data")
        if previous and previous.get("report") == report:
            return previous
        data = parse(body)
        if previous and previous["edition"] > data["edition"]:
            raise ValueError("Indiana statewide history edition regressed")
        return {**data, "report": report}

    return collect_report(collector, feed, INDEX, checked,
                          reuse_checked_week=reuse_checked_week, shared_acquisition=True)


def exports(entries):
    entry = entries.get(FEED) or {}
    if (data := entry.get("data")) is None:
        return []
    report = data["report"]
    if report["url"] != URL or entry["status"] not in ("reported", "retained_after_failure"):
        raise ValueError("Incompatible Indiana statewide history source")
    return [{
        **row, "source_url": URL, "source_sha256": report["sha256"],
        "report_edition": data["edition"], "source_status": entry["status"],
    } for row in query(data["native_lines"])]
