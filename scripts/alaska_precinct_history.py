"""Reconcile Alaska's reported ballot fields without using candidate votes."""
import csv
import io
import json
import re
from decimal import Decimal, ROUND_HALF_UP

from scripts.participation_intake.contract import pin
from scripts import results_alaska_turnout as current
from scripts.southeast_turnout import collect_report

FEED = "AK-2024-general-precinct-ballot-archive"
ROOT = "https://www.elections.alaska.gov/results/24GENR/"
URL = ROOT + "ENRbyPrecinct.csv"
REPORT = ROOT + "ElectionSummaryReport.pdf"
CSV = "participation-ak-2024-precinct-ballot-archive.csv"
CURRENT_FEED = "AK-2026-general-precinct-ballot-archive"
CURRENT_JSON = current.ROOT + "precincts.js"
CURRENT_URL = current.ROOT + "GA_ENR_Precinct_State_of_Alaska.csv"
CURRENT_CSV = "participation-ak-2026-precinct-ballot-archive.csv"
GEOMETRY_URL = current.ROOT.removesuffix("results/") + "shapes/precincts.js"
GEOMETRY_PIN = {"bytes": 5364144, "sha256": "1e9d6b95b88c4ebeea3a1ec5bcd3d0a6052d0436e82dfee0fb62fbc4c25381eb"}
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


def parse_units(body, offices_for_election=OFFICES):
    if not 0 < len(body) <= 8_000_000:
        raise ValueError("Alaska precinct CSV exceeds reviewed size limit")
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))
    columns = reader.fieldnames or []
    required = {"Pct_Id", "Precinct_name", "Aggregation_ID", "Contest_title", "Contest_Id", *FIELDS}
    if not required <= set(columns) or len(set(columns)) != len(columns):
        raise ValueError("Alaska precinct ballot fields changed")
    offices = {name: {} for name in offices_for_election}
    identities = {name: set() for name in offices_for_election}
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
    if any(len(ids) != 1 for ids in identities.values()) or len(set.union(*identities.values())) != len(offices):
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
    validate_units(rows, total - 1, voters, registered)


def validate_units(rows, expected_precincts, voters, registered):
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
            or overseas != 1 or len(codes) != expected_precincts
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


def current_native(body):
    if not 0 < len(body) <= 8_000_000:
        raise ValueError("Alaska precinct JSON exceeds reviewed size limit")
    control = current.controls(body)
    document = json.loads(body)
    if document["precinctReportUrl"] != CURRENT_URL:
        raise ValueError("Alaska bulk precinct CSV is not linked by the matching feed")
    office_ids = [document["contestNames"].index(office) for office in current.OFFICES]
    precincts = []
    for precinct in document["precincts"]:
        values = []
        for office in office_ids:
            row, = (r for r in precinct["contests"] if r["n"] == office)
            values.append([row["b"], row["v"]])
        if values[0] != values[1] or any(type(value) is not int or value < 0 for value in values[0]):
            raise ValueError("Alaska native physical precinct ballot fields differ between offices")
        precincts.append([precinct["number"], precinct["name"], *values[0]])
    return control, sorted(precincts)


def current_reconcile(rows, pdf, native, precincts):
    control = current.reconcile(pdf, native)
    validate_units(rows, 402, control["voters"], control["registered"])
    declared = sorted([identity, label[len(identity) + 1:], ballots, registered]
                      for label, identity, registered, ballots, *_ in rows if PRECINCT.fullmatch(label))
    if declared != precincts or any(v != 403 for v in control["feed_total_precincts"].values()):
        raise ValueError("Alaska CSV precinct counts differ from the literal native roster")
    return control


def collect_current(collector):
    old = (collector.prior.get(CURRENT_FEED) or {}).get("data") or {}

    def parse(body):
        native_body, _ = collector.acquire(CURRENT_JSON)
        pdf_body, _ = collector.acquire(current.REPORT)
        if len(pdf_body) > 4_000_000:
            raise ValueError("Alaska precinct control PDF exceeds reviewed size limit")
        rows = parse_units(body, current.OFFICES)
        pdf = current.parse_report(pdf_body)
        native, precincts = current_native(native_body)
        control = current_reconcile(rows, pdf, native, precincts)
        if (old.get("reconciliation", {}).get("source_status") == current.STATUS[1]
                and control["source_status"] != current.STATUS[1]):
            raise ValueError("Alaska precinct certification regressed")
        # A geometry failure must not discard an independently reconciled count edition.
        geometry = collector.capture(CURRENT_FEED + "-display-geometry", GEOMETRY_URL, geometry_receipt)
        return {"date": control["date"], "complete_native_query": rows, "pdf_control": pdf,
                "native_control": native, "physical_native_units": precincts, "reconciliation": control,
                "control_report": {"url": current.REPORT, **pin(pdf_body)},
                "native_report": {"url": CURRENT_JSON, **pin(native_body)},
                "display_geometry_check": {"status": geometry["status"], "source": geometry["source"]},
                "participation_observation_qualified": False}

    return collector.capture(CURRENT_FEED, CURRENT_URL, parse)


def geometry_receipt(body):
    if not 0 < len(body) <= 8_000_000 or not body.startswith(b"["):
        raise ValueError("Alaska display geometry is not the expected bounded array")
    return {"matches_reviewed_display_geometry": pin(body) == GEOMETRY_PIN}


def geometry_export(data):
    check = data.get("display_geometry_check")
    if check is None:
        return {}  # Preserve byte-exact replay of releases made before the geometry check.
    receipt = check["source"]
    if check["status"] == "reported":
        if (receipt["url"] != GEOMETRY_URL or not re.fullmatch(r"[a-f0-9]{64}", receipt["sha256"])
                or type(receipt["bytes"]) is not int or not 0 < receipt["bytes"] <= 8_000_000):
            raise ValueError("Invalid Alaska geometry receipt")
        decision = "verified_display_subset" if receipt == {"url": GEOMETRY_URL, **GEOMETRY_PIN} else "geometry_changed"
    else:
        if receipt is not None:
            raise ValueError("Unaccepted Alaska geometry cannot supply a current receipt")
        decision = check["status"]
    return {"display_geometry_status": decision, "display_geometry_url": GEOMETRY_URL,
            "display_geometry_sha256": receipt["sha256"] if receipt else None}


def current_exports(entries):
    entry = entries.get(CURRENT_FEED, {})
    data = entry.get("data")
    if data is None or entry.get("status") not in {"reported", "retained_after_failure"}:
        return []
    if entry["source"]["url"] != CURRENT_URL or any(
        p.get("url") != url or not re.fullmatch(r"[a-f0-9]{64}", p.get("sha256", ""))
        or type(p.get("bytes")) is not int or not 0 < p["bytes"] <= limit
        for p, url, limit in ((data["control_report"], current.REPORT, 4_000_000),
                              (data["native_report"], CURRENT_JSON, 8_000_000))
    ):
        raise ValueError("Alaska current precinct data or control source binding differs")
    rows = data["complete_native_query"]
    control = current_reconcile(rows, data["pdf_control"], data["native_control"], data["physical_native_units"])
    if control != data["reconciliation"] or control["date"] != data["date"]:
        raise ValueError("Alaska current precinct control changed")
    geometry = geometry_export(data)
    return [
        {"state_code": "AK", "election_date": "2026-11-03", "reporting_unit": label,
         "source_unit_id": identity,
         "unit_scope": "precinct_election_day_only" if PRECINCT.fullmatch(label) else "central_unallocated_ballots",
         "reported_registration_cell": registered, "reported_ballots": ballots,
         "election_day_ballots": day, "absentee_ballots": absentee, "early_ballots": early,
         "question_ballots": question, "remote_ballots": remote,
         "source_status": entry["status"], "publication_status": control["source_status"],
         "source_url": CURRENT_URL, "source_sha256": entry["source"]["sha256"],
         "official_control_url": current.REPORT, "official_control_sha256": data["control_report"]["sha256"],
         "official_control_edition_local": control["date"], "native_control_url": CURRENT_JSON,
         "native_control_sha256": data["native_report"]["sha256"], **geometry}
        for label, identity, registered, ballots, day, absentee, early, question, remote in rows
    ]
