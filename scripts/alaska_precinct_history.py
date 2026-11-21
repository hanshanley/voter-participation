"""Reconcile Alaska's reported ballot fields without using candidate votes."""
import csv
import io
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from functools import partial

from scripts.participation_intake.contract import pin
from scripts import results_alaska_turnout as current
from scripts.southeast_turnout import collect_report

FEED = "AK-2024-general-precinct-ballot-archive"
ROOT = "https://www.elections.alaska.gov/results/24GENR/"
URL = ROOT + "ENRbyPrecinct.csv"
REPORT = ROOT + "ElectionSummaryReport.pdf"
CSV = "participation-ak-2024-precinct-ballot-archive.csv"
MIDTERM_FEED = "AK-2022-general-precinct-ballot-archive"
MIDTERM_ROOT = "https://elections.alaska.gov/results/22GENR/"
MIDTERM_REPORT = MIDTERM_ROOT + "ElectionSummaryReportRPT.pdf"
MIDTERM_CSV = "participation-ak-2022-precinct-ballot-archive.csv"
MIDTERM_DISTRICTS = (*range(1, 41), 99)
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
MIDTERM_IDENTITY = "State of Alaska 2022 GENERAL ELECTION"
MIDTERM_TABLE = "Precinct Registered Voters Cards Cast Voters Cast % Turnout "
MIDTERM_NUM = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
MIDTERM_VALUES = rf"({MIDTERM_NUM}) ({MIDTERM_NUM}) ({MIDTERM_NUM}) (\d+\.\d\d%|N/A)"
MIDTERM_TOTAL = "State of Alaska - Total "


def midterm_document(body):
    from pypdf import PdfReader

    if not 0 < len(body) <= 4_000_000 or not body.startswith(b"%PDF-"):
        raise ValueError("Alaska midterm source is not a bounded PDF")
    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("Alaska midterm source page inventory changed")
    return reader.pages


def midterm_summary(body):
    pages = midterm_document(body)
    text = " ".join(pages[0].extract_text().split())
    control = re.search(
        rf"Precincts Reported: ({MIDTERM_NUM}) of ({MIDTERM_NUM}) \( 100\.00% \) "
        rf"Registered Voters: ({MIDTERM_NUM}) of ({MIDTERM_NUM}) \( (\d+\.\d\d%) \) "
        rf"Ballots Cast: ({MIDTERM_NUM}) {MIDTERM_IDENTITY} Election Summary Report "
        rf"November 8 , 2022 OFFICIAL RESULTS (\d\d/\d\d/2022 \d{{1,2}}:\d\d:\d\d [AP]M) Page: 1 of {len(pages)}$", text)
    if not control:
        raise ValueError("Alaska official midterm statewide ballot control changed")
    reported, total, voters, registered, printed, ballots, stamp = control.groups()
    if reported != total or voters != ballots:
        raise ValueError("Alaska official midterm statewide controls disagree")
    values = midterm_values((registered, ballots, voters, printed))
    return {"precincts_reported": int(total.replace(",", "")), "registered": values[0],
            "ballots": values[1], "edition": stamp, "registered_turnout": printed}


def midterm_values(fields):
    register, cards, voters = (int(value.replace(",", "")) for value in fields[:3])
    rate = ("N/A" if not register else
            f'{(Decimal(voters * 100) / register).quantize(Decimal(".01"), rounding=ROUND_HALF_UP):.2f}%')
    if min(register, cards, voters) < 0 or cards != voters or rate != fields[3] or (register and voters > register):
        raise ValueError("Alaska midterm ballot fields do not reconcile")
    return [register, cards, voters, fields[3]]


def midterm_district(body, district):
    pages = midterm_document(body)
    text = " ".join(pages[0].extract_text().split())
    footer = re.search(
        rf" {MIDTERM_IDENTITY} Statement of Votes Cast November 8 , 2022 OFFICIAL RESULTS "
        rf"(\d\d/\d\d/2022 \d{{1,2}}:\d\d:\d\d [AP]M) Page: 1 of {len(pages)}$", text)
    header = MIDTERM_TABLE + "State State of Alaska "
    if not text.startswith(header) or not footer:
        raise ValueError("Alaska midterm district report has the wrong election or reporting stage")
    table = text[len(header):footer.start()]
    for number in range(2, min(len(pages), 5) + 1):
        if MIDTERM_TOTAL in table:
            break
        text = " ".join(pages[number - 1].extract_text().split())
        end = f" {footer[1]} Page: {number} of {len(pages)}"
        if not text.startswith(MIDTERM_TABLE) or not text.endswith(end):
            raise ValueError("Alaska midterm ballot table continuation differs")
        table += " " + text[len(MIDTERM_TABLE):-len(end)]
    controls = re.search(rf" {MIDTERM_TOTAL}{MIDTERM_VALUES} State - Total {MIDTERM_VALUES}$", table)
    if not controls or controls.groups()[:4] != controls.groups()[4:]:
        raise ValueError("Alaska midterm district totals disagree")
    remaining = table[:controls.start()]
    unit = re.compile(rf"((?:{district:02d}-\d{{3}} .+?|District {district} - (?:Absentee|Early Voting|Question)|"
                      rf"HD99 Fed Overseas Absentee)) {MIDTERM_VALUES}(?: |$)")
    rows = []
    while remaining:
        match = unit.match(remaining)
        if not match:
            raise ValueError("Unknown or incomplete Alaska midterm reporting row")
        rows.append([match[1], *midterm_values(match.groups()[1:])])
        remaining = remaining[match.end():]
    return {"rows": rows, "total": midterm_values(controls.groups()[:4]), "edition": footer[1]}


def reconcile_midterm(districts, control):
    if set(districts) != {str(n) for n in MIDTERM_DISTRICTS}:
        raise ValueError("Missing Alaska midterm district report")
    units, codes, registered, ballots = set(), set(), 0, 0
    for number, district in districts.items():
        rows = district["rows"]
        row_register, row_ballots, central = 0, 0, set()
        for label, register, cards, voters, rate in rows:
            if label in units or midterm_values((str(register), str(cards), str(voters), rate)) != [register, cards, voters, rate]:
                raise ValueError("Duplicate or incompatible Alaska midterm row")
            units.add(label)
            row_register += register
            row_ballots += cards
            if (match := PRECINCT.fullmatch(label)) and match[1][:2] == f"{int(number):02d}" and number != "99":
                if not register or match[1] in codes:
                    raise ValueError("Missing registration or repeated Alaska midterm precinct ID")
                codes.add(match[1])
            elif (match := CENTRAL.fullmatch(label)) and number == match[1] and not register:
                central.add(match[2])
            elif not (number == "99" and label == OVERSEAS and register):
                raise ValueError("Unrecognized Alaska midterm geography or mode")
        if (number == "99" and len(rows) != 1
                or number != "99" and central != set(MODE_NAMES)
                or district["total"][:3] != [row_register, row_ballots, row_ballots]):
            raise ValueError("Alaska midterm rows do not reconcile to the district control")
        registered += row_register
        ballots += row_ballots
    if (len(codes) + 1, registered, ballots) != (control["precincts_reported"], control["registered"], control["ballots"]):
        raise ValueError("Alaska midterm district reports do not match the official statewide control")


def collect_midterm(collector, *, reuse_checked_week=False):
    def parse(body, _):
        control = midterm_summary(body)
        districts = {}
        for district in MIDTERM_DISTRICTS:
            url = MIDTERM_ROOT + f"HD{district}.pdf"
            original, _ = collector.acquire(url)
            districts[str(district)] = {**midterm_district(original, district),
                                        "source": {"url": url, **pin(original)}}
        reconcile_midterm(districts, control)
        return {"control": control, "districts": districts, "participation_observation_qualified": False}
    return collect_report(collector, MIDTERM_FEED, MIDTERM_REPORT, parse, reuse_checked_week=reuse_checked_week)


def midterm_exports(entries):
    entry = entries.get(MIDTERM_FEED, {})
    if not entry.get("data"):
        return
    data = entry["data"]
    if entry["status"] not in ("reported", "retained_after_failure") or entry["source"]["url"] != MIDTERM_REPORT:
        raise ValueError("Unreviewed Alaska midterm source binding")
    reconcile_midterm(data["districts"], data["control"])
    for district, report in sorted(data["districts"].items(), key=lambda item: int(item[0])):
        source = report["source"]
        if source["url"] != MIDTERM_ROOT + f"HD{district}.pdf" or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"]):
            raise ValueError("Unreviewed Alaska midterm district binding")
        for label, register, cards, voters, rate in report["rows"]:
            match = PRECINCT.fullmatch(label)
            yield {"state_code": "AK", "election_date": "2022-11-08", "district": district,
                   "source_unit_id": match[1] if match else "", "reporting_unit": label,
                   "unit_scope": "precinct_election_day_only" if match else "central_unallocated_ballots",
                   "reported_registration_cell": register, "reported_ballots": cards,
                   "reported_voters_cast": voters, "printed_source_turnout": rate,
                   "all_mode_precinct_rate_qualified": False, "precinct_geometry_verified": False,
                   "official_state_ballot_control": data["control"]["ballots"],
                   "official_state_registration_control": data["control"]["registered"],
                   "source_status": entry["status"], "source_url": source["url"], "source_sha256": source["sha256"],
                   "archive_status": entry.get("archive_status"),
                   "latest_acquisition_status": entry.get("latest_acquisition_status"),
                   "official_control_url": MIDTERM_REPORT, "official_control_sha256": entry["source"]["sha256"],
                   "official_district_edition_local": report["edition"]}


def midterm_originals(entries):
    entry = entries.get(MIDTERM_FEED, {})
    if not entry.get("data"):
        return
    data, source = entry["data"], entry["source"]
    yield (MIDTERM_FEED + "-statewide", source, ".pdf", 4_000_000,
           source["url"] == MIDTERM_REPORT, midterm_summary, data["control"])
    for district, report in data["districts"].items():
        source = report["source"]
        yield (MIDTERM_FEED + "-" + district, source, ".pdf", 4_000_000,
               source["url"] == MIDTERM_ROOT + f"HD{district}.pdf",
               partial(midterm_district, district=int(district)),
               {key: value for key, value in report.items() if key != "source"})


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
