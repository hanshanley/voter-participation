"""Reconcile Alaska's reported ballot fields without using candidate votes."""
import csv
import io
import re
from decimal import Decimal, ROUND_HALF_UP

from scripts.participation_intake.contract import pin
from scripts.southeast_turnout import collect_report

FEED = "AK-2024-general-precinct-ballot-archive"
ROOT = "https://www.elections.alaska.gov/results/24GENR/"
URL = ROOT + "ENRbyPrecinct.csv"
REPORT = ROOT + "ElectionSummaryReport.pdf"
CSV = "participation-ak-2024-precinct-ballot-archive.csv"
OFFICES = ("U.S. President / Vice President", "U.S. Representative")
FIELDS = ("Reg_voters", "total_ballots", "Election Day_ballots", "Absentee_ballots",
          "Early Voting_ballots", "Question_ballots", "Remote_ballots")
MODE_NAMES = ("Absentee", "Early Voting", "Question")
PRECINCT = re.compile(r"(\d{2}-\d{3}) .+")
CENTRAL = re.compile(r"District ([1-9]\d?) +- (Absentee|Early Voting|Question)")
OVERSEAS = "HD99 Fed Overseas Absentee"
SOURCE_HEADER = re.compile(
    r"Precincts Reported: ([\d,]+) of ([\d,]+) \( 100\.00% \) "
    r"Voters Cast: ([\d,]+) of ([\d,]+) \( (\d+\.\d\d)% \) "
    r"State of Alaska 2024 GENERAL ELECTION Election Summary Report November 5 , 2024 OFFICIAL RESULTS$"
)


def parse_units(body):
    if not 0 < len(body) <= 8_000_000:
        raise ValueError("Alaska precinct CSV exceeds reviewed size limit")
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))
    columns = reader.fieldnames or []
    required = {"Pct_Id", "Precinct_name", "Aggregation_ID", "Contest_title", "Contest_Id", *FIELDS}
    if not required <= set(columns) or len(set(columns)) != len(columns):
        raise ValueError("Alaska precinct ballot fields changed")
    offices = {name: {} for name in OFFICES}
    identities = {name: set() for name in OFFICES}
    for row in reader:
        office = row["Contest_title"]
        if office not in offices:
            continue
        if (None in row or row["Aggregation_ID"] != ""
                or not all(re.fullmatch(r"[0-9]+", row.get(field) or "") for field in FIELDS)):
            raise ValueError("Alaska ballot row changed scope or contains a missing count")
        key = (row["Precinct_name"], row["Pct_Id"])
        values = tuple(int(row[field]) for field in FIELDS)
        if offices[office].setdefault(key, values) != values:
            raise ValueError("Duplicated Alaska ballot fields disagree within a contest")
        identities[office].add(row["Contest_Id"])
    if any(len(ids) != 1 for ids in identities.values()) or identities[OFFICES[0]] == identities[OFFICES[1]]:
        raise ValueError("Ambiguous Alaska federal contest identity")
    first, second = offices.values()
    if first != second:
        raise ValueError("Alaska federal ballot fields disagree between contests")
    return [[label, identity, *values] for (label, identity), values in sorted(first.items())]


def summary_control(body):
    from pypdf import PdfReader

    if not 0 < len(body) <= 4_000_000 or not body.startswith(b"%PDF-"):
        raise ValueError("Alaska statewide control is not a bounded PDF")
    pages = PdfReader(io.BytesIO(body), strict=True).pages
    if not 1 <= len(pages) <= 80:
        raise ValueError("Alaska statewide control page inventory changed")
    text = " ".join(pages[0].extract_text().split())
    matched = SOURCE_HEADER.search(text)
    if not matched:
        raise ValueError("Alaska official statewide Voters Cast control not found")
    clock = re.match(r"(\d\d/\d\d/2024 \d{1,2}:\d\d:\d\d [AP]M) Page: 1 of (\d+)", text)
    if not clock or int(clock[2]) != len(pages):
        raise ValueError("Alaska statewide control has no complete edition stamp")
    return [*matched.groups(), clock[1]]


def validate(rows, control):
    if (len(control) != 6 or not all(isinstance(s, str) and re.fullmatch(r"[\d,]+", s) for s in control[:4])
            or not re.fullmatch(r"\d+\.\d\d", control[4])
            or not re.fullmatch(r"\d\d/\d\d/2024 \d{1,2}:\d\d:\d\d [AP]M", control[5])):
        raise ValueError("Invalid Alaska statewide control literals")
    reported, total, voters, registered = (int(s.replace(",", "")) for s in control[:4])
    if not 0 < voters <= registered or reported != total or (
        Decimal(voters * 100) / registered
    ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(control[4]):
        raise ValueError("Alaska statewide control does not reconcile")
    names, codes, central = set(), set(), set()
    overseas = 0
    state_ballots = state_register = 0
    for label, identity, register, ballots, day, absentee, early, question, remote in rows:
        if (not isinstance(label, str) or not isinstance(identity, str) or label in names
                or any(type(n) is not int or n < 0 for n in (register, ballots, day, absentee, early, question, remote))
                or ballots != day + absentee + early + question + remote):
            raise ValueError("Alaska reporting row is duplicated or its ballot modes do not reconcile")
        names.add(label)
        state_ballots += ballots
        state_register += register
        if match := PRECINCT.fullmatch(label):
            if identity != match[1] or identity in codes or not 0 <= day <= register or not register or day != ballots:
                raise ValueError("Alaska physical precinct identity or Election Day scope differs")
            codes.add(identity)
        elif match := CENTRAL.fullmatch(label):
            key = (int(match[1]), match[2])
            mode = (absentee, early, question)[MODE_NAMES.index(match[2])]
            if key in central or register or mode + (day if match[2] == "Early Voting" else 0) != ballots:
                raise ValueError("Alaska central ballot mode differs")
            central.add(key)
        elif label == OVERSEAS and identity == "99-999" and 0 <= ballots <= register and absentee == ballots:
            overseas += 1
        else:
            raise ValueError("Unknown Alaska reporting-unit scope")
    if (central != {(i, mode) for i in range(1, 41) for mode in MODE_NAMES}
            or overseas != 1 or len(codes) + overseas != total
            or (state_ballots, state_register) != (voters, registered)):
        raise ValueError("Alaska reporting units do not match the complete official statewide controls")


def collect(collector, *, reuse_checked_week=False):
    def parse(body, _):
        report, _ = collector.acquire(REPORT)
        rows, control = parse_units(body), summary_control(report)
        validate(rows, control)
        return {"complete_native_query": rows, "control": control,
                "control_report": {"url": REPORT, **pin(report)}, "participation_observation_qualified": False}

    return collect_report(collector, FEED, URL, parse, reuse_checked_week=reuse_checked_week)


def exports(entries):
    entry = entries.get(FEED, {})
    data = entry.get("data")
    if data is None or entry.get("status") not in {"reported", "retained_after_failure"}:
        return []
    report = data["control_report"]
    if (entry["source"]["url"] != URL or report["url"] != REPORT
            or not re.fullmatch(r"[a-f0-9]{64}", report.get("sha256", ""))
            or type(report.get("bytes")) is not int or not 0 < report["bytes"] <= 4_000_000):
        raise ValueError("Alaska ballot or control source binding differs")
    validate(data["complete_native_query"], data["control"])
    return [
        {"state_code": "AK", "election_date": "2024-11-05", "reporting_unit": label,
         "source_unit_id": identity,
         "unit_scope": "precinct_election_day_only" if PRECINCT.fullmatch(label)
         else "central_unallocated_ballots",
         "reported_registration_cell": registered, "reported_ballots": ballots,
         "election_day_ballots": day, "absentee_ballots": absentee, "early_ballots": early,
         "question_ballots": question, "remote_ballots": remote,
         "source_status": entry["status"], "checked_week_utc": entry.get("archive_check_week_utc"),
         "source_url": URL, "source_sha256": entry["source"]["sha256"],
         "official_control_url": REPORT, "official_control_sha256": report["sha256"],
         "official_control_edition_local": data["control"][5]}
        for label, identity, registered, ballots, day, absentee, early, question, remote in data["complete_native_query"]
    ]
