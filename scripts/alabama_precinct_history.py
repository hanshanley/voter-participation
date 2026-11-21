"""Alabama's reporting-unit ballot counts and compatible county controls."""
import io
import re
from zipfile import ZipFile
from xml.etree import ElementTree

from scripts.participation_intake.contract import pin
from scripts.southeast_turnout import COUNTIES, NUMBER, collect_report

ROOT = "https://www.sos.alabama.gov/sites/default/files/election-data/"
INDEX = "https://www.sos.alabama.gov/alabama-votes/voter/election-data"
CURRENT_CONTROL = "AL-2026-general-county-ballot-control"
CURRENT_CONTROL_ROUTE = (re.escape(ROOT) + r"20(?:26|27)-(?:0[1-9]|1[0-2])/"
                         r"(?=[^/]*2026)[A-Za-z0-9_%.-]+\.pdf")
FILES = {
    2010: ("2017-06/2010-general-precinctLevel.zip", None, "November 2, 2010"),
    2012: ("2017-06/2012General-PrecinctLevel.zip", None, "November 6, 2012"),
    2016: ("2017-06/2016-General-PrecinctLevel.zip", None, "November 8, 2016"),
    2018: ("2018-11/2018-Official-General-Precinct-Results.zip",
           "2019-01/2018GeneralVoterTurnoutStats.xlsx", "November 6, 2018"),
    2020: ("2020-12/2020%20General%20Precinct%20Results.zip",
           "2020-11/2020_General_Total_Ballots_Cast_Report.pdf", "November 3, 2020"),
    2022: ("2022-11/2022%20General%20Precinct%20Level%20Results.zip",
           "2023-05/General%20Election%202022%20Official%20Total%20Ballots%20Cast.pdf", "November 8, 2022"),
    2024: ("2024-12/2024-General%20Precinct%20Level%20Results.zip",
           "2025-01/2024GeneralElectionTotalBallotsCast.pdf", "November 5, 2024"),
    2026: ("2026-11/2026GeneralElectionPrecinctResults.zip", None, "November 3, 2026"),
}
FEEDS = {year: (f"AL-{year}-general-precinct-ballot-archive",
                f"AL-{year}-general-county-ballot-control")
         for year, paths in FILES.items()}
URLS = {feed: ROOT + path for year, paths in FILES.items() for feed, path in zip(FEEDS[year], paths[:2]) if path}
URLS[CURRENT_CONTROL] = INDEX
CSV = "participation-al-precinct-ballot-archives.csv"
CONTROL_CSV = "participation-al-precinct-ballot-county-controls.csv"
WORKBOOK_AUDIT_CSV = "participation-al-legacy-workbook-controls.csv"
COUNTY_KEYS = {county.replace("_", ""): county for county in COUNTIES}
EARLY_MISSING = {"BULLOCK", "BUTLER", "HALE", "WILCOX"}
EARLY_HEADER = ("Registered Voters", "Ballots Cast", "Voter Turnout")
MODE_LABELS = {
    "ABSENTEE", "PROVISIONAL", "PROVISIONAL ABSENTEE", "ABSENTEE PROVISIONAL",
    "BESSEMER ABSENTEE", "BIRMINGHAM ABSENTEE", "PROVISIONAL OFFICIAL",
}
LEGACY_MODE_LABELS = {
    "PROVISONAL", "BIRMINGHAM ABSENTEE 1", "BIRMINGHAM ABSENTEE 2",
    "PROVISIONAL 1", "PROVISIONAL 2", "ABSENTEE BS 1-20", "ABSENTEE BS 21-45",
    "PROVISIONAL BS 1-20", "PROVISIONAL BS 21-45", "ABSENTEE #1", "ABSENTEE #2",
    "PROVISIONAL #1", "PROVISIONAL #2", "ABSENTEE 1", "ABSENTEE 2",
}
CONTROL_2018_HEADER = (
    "County", "Total Registered Voters", "Total Ballots Cast", "Straight Party Democrat Ballots Cast",
    "Straight Party Republican Ballots Cast", "Total Absentee Ballots Cast",
    "Turnout as a Percentage of Registered Voters", "Absentee Ballots Cast as Percentage of Total Ballots Cast",
)


def county_key(name):
    return re.sub(r"[^A-Z]", "", name.upper())


def validate_units(data, year=None):
    if set(data) != set(COUNTY_KEYS.values()):
        raise ValueError("Alabama precinct workbook county roster changed")
    for county, rows in data.items():
        if (not rows and not (year == 2012 and county in EARLY_MISSING)) or len(rows) > 400:
            raise ValueError(f"Alabama reporting-unit inventory out of bounds: {county}")
        seen = set()
        for label, ballots, register in rows:
            if (not isinstance(label, str) or not label or len(label) > 200
                    or any(ord(char) < 32 for char in label)
                    or (label.upper() in seen and not
                        (year == 2012 and county == "MORGAN" and label.upper() == "DECATUR FIRE & RESCUE"
                         and sum(row[0].upper() == label.upper() for row in rows) == 2))
                    or re.match(r"^(?:TOTAL|GRAND TOTAL)\b", label, re.I)
                    or type(ballots) is not int or ballots < 0
                    or register is not None and (type(register) is not int or register < 0)):
                raise ValueError(f"Invalid Alabama reporting unit: {county}")
            seen.add(label.upper())
    return data


def early_integer(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,7}", value):
        value = int(value)
    if type(value) is float and value.is_integer():
        value = int(value)
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError("Invalid early Alabama turnout cell")
    return value


def early_tall_sheet(rows):
    active = [tuple(row) for row in rows if any(v not in (None, "") for v in row)]
    if (len(active) < 3 or len(active) > 402
            or any(len(row) < 4 or any(v not in (None, "") for v in row[4:]) for row in active)
            or active[0][0] not in ("Precinct", "Voting Center", "Voting Centers")
            or active[0][1:4] != EARLY_HEADER or active[-1][0] != "Total:"
            or any(not isinstance(row[0], str) for row in active[1:-1])):
        raise ValueError("Early Alabama turnout worksheet schema changed")
    return ([[row[0].strip(), early_integer(row[2]), early_integer(row[1])] for row in active[1:-1]],
            early_integer(active[-1][2]))


def early_xml_sheet(body):
    text = body.decode("utf-8-sig")
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        raise ValueError("Unexpected XML declarations in Alabama turnout workbook")
    ns = "{urn:schemas-microsoft-com:office:spreadsheet}"
    root = ElementTree.fromstring(text)
    sheets = [sh for sh in root.findall(f"{ns}Worksheet") if sh.get(f"{ns}Name") == "Registered Voters"]
    if len(sheets) != 1:
        raise ValueError("Missing or repeated Alabama turnout worksheet")
    rows = []
    for row in sheets[0].findall(f"{ns}Table/{ns}Row"):
        cells = row.findall(f"{ns}Cell")
        if any(f"{ns}{attr}" in cell.attrib for cell in cells for attr in ("Index", "MergeAcross", "MergeDown")):
            raise ValueError("Unexpected positional cells in Alabama turnout worksheet")
        rows.append([cell.findtext(f"{ns}Data") for cell in cells])
    return early_tall_sheet(rows)


def early_xlsx_sheet(body, county, *, misspelled_randolph=False):
    from openpyxl import load_workbook

    with ZipFile(io.BytesIO(body)) as nested:
        if sum(item.file_size for item in nested.infolist()) > 10_000_000:
            raise ValueError("Alabama workbook exceeds expanded size limit")
    book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        if misspelled_randolph and (
                "Table of Contents" not in book.sheetnames or not any(
                    row[0] == "FOR CIRCUIT CLERK, RANDOLPH COUNTY (Vote For 1)"
                    for row in book["Table of Contents"].iter_rows(max_row=100, min_col=2, max_col=2, values_only=True))):
            raise ValueError("Misspelled Alabama county workbook lacks Randolph identity")
        if "Registered Voters" in book.sheetnames:
            return early_tall_sheet(book["Registered Voters"].values)
        if county in EARLY_MISSING and book.sheetnames == ["Sheet1", "Sheet2", "Sheet3"]:
            cells = [cell for sh in book for row in sh.values for cell in row if cell not in (None, "")]
            if cells == ["Precinct Results Unavailable"]:
                return [], None
        if county == "MONTGOMERY" and book.sheetnames == ["Precinct Results"]:
            head, ballots = book.worksheets[0].iter_rows(max_row=2, values_only=True)
            if (head[:3] == ("Contest Title", "Party", "Candidate") and ballots[0] == "BALLOTS CAST - TOTAL"
                    and not ballots[1] and ballots[2] == "Ballots Cast - Total" and len(head) == len(ballots)
                    and all(isinstance(label, str) for label in head[3:])):
                return [[label.strip(), early_integer(n), None]
                        for label, n in zip(head[3:], ballots[3:], strict=True)], None
        raise ValueError("Unknown Alabama turnout worksheet")
    finally:
        book.close()


def parse_early_units(body, year):
    import xlrd

    units, printed = {}, {}
    with ZipFile(io.BytesIO(body)) as archive:
        members = archive.infolist()
        if len(members) != 67 or sum(item.file_size for item in members) > 64_000_000:
            raise ValueError("Early Alabama archive inventory changed")
        for item in members:
            name = re.fullmatch(r"([A-Za-z ._'-]+?)\.(xls(?:\.xls)?|xlsx)", item.filename)
            misspelled_randolph = year == 2012 and item.filename == "Radolph.xlsx"
            county = "RANDOLPH" if misspelled_randolph else COUNTY_KEYS.get(county_key(name[1])) if name else None
            if county is None or county in units or not 0 < item.file_size <= 10_000_000:
                raise ValueError("Unknown, oversized or repeated early Alabama county workbook")
            binary = archive.read(item)
            if name[2] == "xlsx" and year == 2012:
                rows, footer = early_xlsx_sheet(binary, county, misspelled_randolph=misspelled_randolph)
            elif name[2] != "xlsx" and binary.startswith((b"\xef\xbb\xbf<?xml", b"<?xml")):
                rows, footer = early_xml_sheet(binary)
            elif name[2] == "xls" and year == 2010:
                sheet = xlrd.open_workbook(file_contents=binary).sheet_by_name("Registered Voters")
                rows, footer = early_tall_sheet(sheet.row_values(i) for i in range(sheet.nrows))
            else:
                raise ValueError("Early Alabama workbook format changed")
            units[county], printed[county] = rows, footer
    return validate_units(units, year), printed


def parse_units(body, year):
    import xlrd

    def integer(value):
        if type(value) is not float or not value.is_integer() or not 0 <= value <= 1_000_000:
            raise ValueError("Missing or invalid Alabama reporting-unit count")
        return int(value)

    counties = {}
    with ZipFile(io.BytesIO(body)) as z:
        items = z.infolist()
        if len(items) != len(COUNTY_KEYS) or sum(item.file_size for item in items) > 20_000_000:
            raise ValueError("Alabama precinct archive inventory changed")
        for item in items:
            prefix = "2026_GENERAL_ELECTION" if year == 2026 else f"{year}-General"
            match = re.fullmatch(rf"{prefix}-([A-Za-z ._'-]+)\.xls", item.filename)
            county = COUNTY_KEYS.get(county_key(match[1])) if match else None
            if county is None or county in counties or not 0 < item.file_size <= 1_000_000:
                raise ValueError("Unknown, oversized or repeated Alabama county workbook")
            book = xlrd.open_workbook(file_contents=z.read(item))
            if book.sheet_names() != ["Precinct Results"]:
                raise ValueError("Alabama precinct results sheet changed")
            sheet = book.sheet_by_index(0)
            headings = [str(sheet.cell_value(i, 0)).strip() for i in range(4)]
            following = {"BALLOTS CAST - BLANK", "STRAIGHT PARTY"} if year <= 2020 else {"BALLOTS CAST - BLANK"}
            if year == 2016 and county == "COLBERT":
                following.add("PRESIDENT AND VICE PRESIDENT OF THE UNITED STATES")
            if (headings[:3] != ["Contest Title", "REGISTERED VOTERS - TOTAL", "BALLOTS CAST - TOTAL"]
                    or headings[3] not in following
                    or [str(v).strip() for v in sheet.row_values(0)[:3]] != ["Contest Title", "Party", "Candidate"]):
                raise ValueError("Alabama workbook no longer identifies ballots and registration")
            rows = []
            for col in range(3, sheet.ncols):
                label, register, ballots = (sheet.cell_value(row, col) for row in (0, 1, 2))
                if not isinstance(label, str):
                    raise ValueError("Alabama reporting-unit label is not text")
                rows.append([label.strip(), integer(ballots), None if register == "" else integer(register)])
            counties[county] = rows
    return validate_units(counties)


def control_rows(lines, year):
    if year == 2018:
        if not lines or tuple(lines[0]) != CONTROL_2018_HEADER or any(len(row) != 8 for row in lines[1:]):
            raise ValueError("Alabama county control workbook columns changed")
        return validate_controls((row[0], row[1], row[2], row[5]) for row in lines[1:])
    titles = {f"General Election {dash} {FILES[year][2]}" for dash in ("-", "–")}
    columns_2022 = "County Registered Total Ballots Cast Party Republican Absentee Percentage Percentage"
    columns_2024 = "County Voters Ballots Cast Ballots Ballots Ballots Registered Voters Total Ballots"
    columns = {columns_2022} if year == 2022 else {columns_2024} if year == 2024 else {columns_2022, columns_2024}
    if year == 2020:
        titles = {f"Total Ballots Cast ‐ General Election ‐ {FILES[year][2]}"}
        columns = {"County Voters Ballots Cast Democrat Republican Ballots Registered Voters Total Ballots"}
    if (not titles.intersection(lines) or not columns.intersection(lines)
            or year != 2020 and "Official Total Ballots Cast" not in lines):
        raise ValueError("Alabama county ballot control election or measure changed")
    match_row = re.compile(rf"([A-Za-z. ]+) ((?:{NUMBER} ){{5}})\d{{1,3}}\.\d+% \d{{1,3}}\.\d+%")
    values = []
    for line in lines:
        match = match_row.fullmatch(line)
        if not match:
            continue
        registration, ballots, _, _, absentee = [int(value.replace(",", "")) for value in match[2].split()]
        values.append((match[1], registration, ballots, absentee))
    return validate_controls(values)


def validate_controls(rows):
    values = {}
    for name, registration, ballots, absentee in rows:
        key = county_key(name) if isinstance(name, str) else None
        county = "TOTAL" if key == "TOTAL" else COUNTY_KEYS.get(key)
        if county is None or county in values:
            raise ValueError("Unexpected Alabama control county")
        if (not all(type(v) is int for v in (registration, ballots, absentee))
                or not 0 <= absentee <= ballots <= registration):
            raise ValueError("Incompatible Alabama county control counts")
        values[county] = [registration, ballots, absentee]
    if set(values) != {*COUNTIES, "TOTAL"} or any(
        sum(values[c][i] for c in COUNTIES) != values["TOTAL"][i] for i in range(3)
    ):
        raise ValueError("Alabama county controls do not reconcile to the printed state total")
    return values


def parse(body, feed):
    if not 0 < len(body) <= 6_000_000:
        raise ValueError("Alabama archive source exceeds reviewed bounds")
    year = next(year for year, pair in FEEDS.items() if feed in pair)
    if year in (2010, 2012) and feed == FEEDS[year][0]:
        data, footer = parse_early_units(body, year)
        return {"complete_native_query": data, "native_lines": None, "workbook_printed_totals": footer,
                "participation_observation_qualified": False}
    if feed == FEEDS[year][0]:
        data, lines = parse_units(body, year), None
    elif year == 2018:
        from openpyxl import load_workbook

        with ZipFile(io.BytesIO(body)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 10_000_000:
                raise ValueError("Alabama county control workbook exceeds expanded size limit")
        book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        try:
            if (book.sheetnames != ["Sheet1", "Sheet2", "Sheet3"]
                    or any(any(value is not None for row in book[name].values for value in row)
                           for name in book.sheetnames[1:])):
                raise ValueError("Alabama county control worksheets changed")
            lines = [[" ".join(v.split()) if isinstance(v, str) else v for v in row]
                     for row in book["Sheet1"].values]
            data = control_rows(lines, year)
        finally:
            book.close()
    else:
        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(body), strict=True).pages
        if len(pages) != 2:
            raise ValueError("Alabama county report layout changed")
        lines = [" ".join(line.split()) for page in pages
                 for line in page.extract_text(extraction_mode="layout").splitlines() if line.strip()]
        data = control_rows(lines, year)
    return {"complete_native_query": data, "native_lines": lines, "participation_observation_qualified": False}


def collect(collector, feed, *, reuse_checked_week=False):
    if feed == CURRENT_CONTROL:
        def discovery(index, _):
            from scripts.results_intake import IntakeError

            url = discover_control(index)
            if url is None:
                raise IntakeError("report_not_linked", "Alabama does not yet link a 2026 general-election county control")
            report, _ = collector.acquire(url)
            return {**parse(report, feed), "control_report": {"url": url, **pin(report)}}

        return collect_report(collector, feed, INDEX, discovery, reuse_checked_week=reuse_checked_week)
    return collect_report(collector, feed, URLS[feed], parse, reuse_checked_week=reuse_checked_week)


def discover_control(index):
    from scripts.results_turnout_history import archive_link

    return archive_link(index, INDEX, CURRENT_CONTROL_ROUTE, label="Total Ballots Cast - General Election")


def exports(entries):
    units, county = [], []
    for year, (archive_feed, control_feed) in FEEDS.items():
        archive, control = (entries.get(feed) or {} for feed in (archive_feed, control_feed))
        usable = {"reported", "retained_after_failure"}
        csv_entry = archive.get("data") if archive.get("status") in usable else None
        control_entry = control.get("data") if control.get("status") in usable else None
        if csv_entry is None and control_entry is None:
            continue
        workbooks = {} if csv_entry is None else validate_units(csv_entry["complete_native_query"], year)
        controls = {} if control_entry is None else control_rows(control_entry["native_lines"], year)
        if ((csv_entry is not None and archive["source"]["url"] != URLS[archive_feed])
                or (control_entry is not None and (control["source"]["url"] != URLS[control_feed]
                    or controls != control_entry["complete_native_query"]))):
            raise ValueError("Unbound Alabama original or changed county control query")
        control_source = control.get("source") or {}
        if control_feed == CURRENT_CONTROL and control_entry is not None:
            control_source = control_entry.get("control_report") or {}
            if not (re.fullmatch(CURRENT_CONTROL_ROUTE, control_source.get("url", ""))
                    and re.fullmatch(r"[a-f0-9]{64}", control_source.get("sha256", ""))
                    and type(control_source.get("bytes")) is int and 0 < control_source["bytes"] <= 6_000_000):
                raise ValueError("Alabama 2026 control is not bound to the discovered report")
        archive_sums = {name: sum(row[1] for row in rows) for name, rows in workbooks.items() if rows}
        if len(archive_sums) == len(COUNTIES):
            archive_sums["TOTAL"] = sum(archive_sums.values())
        provenance = {"state_code": "AL", "year": year,
                      "archive_url": URLS[archive_feed],
                      "control_url": control_source.get("url", URLS.get(control_feed)),
                      "archive_status": archive.get("status"), "control_status": control.get("status"),
                      "archive_checked_week_utc": archive.get("archive_check_week_utc"),
                      "control_checked_week_utc": control.get("archive_check_week_utc"),
                      "archive_sha256": (archive.get("source") or {}).get("sha256"),
                      "control_sha256": control_source.get("sha256")}
        for name in (*COUNTIES, "TOTAL"):
            comparison = controls.get(name)
            total = archive_sums.get(name)
            delta = total - comparison[1] if comparison is not None and total is not None else None
            decision = "not_reconciled_without_both_sources" if delta is None else (
                "reconciled" if delta == 0 else "county_control_disagrees")
            county.append({**provenance, "county": name, "county_archive_ballots": total,
                           "county_control_ballots": comparison[1] if comparison is not None else None,
                           "county_control_registered": comparison[0] if comparison is not None else None,
                           "county_control_absentee": comparison[2] if comparison is not None else None,
                           "archive_minus_control": delta, "reconciliation": decision})
            units.extend({**provenance, "county": name, "source_unit_ordinal": index,
                          "reporting_unit": label,
                          "unit_type": "central_mode_or_provisional" if label.upper() in MODE_LABELS
                          or year <= 2020 and label.upper() in LEGACY_MODE_LABELS
                          else "reporting_unit_no_boundary_binding",
                          "reported_ballots": ballots, "unqualified_registration_cell": registration,
                          "reconciliation": decision}
                         for index, (label, ballots, registration) in enumerate(workbooks.get(name, ()), 1))
    return units, county


def export_tables(entries):
    units, controls = exports(entries)
    audit = []
    for year in (2010, 2012):
        feed = FEEDS[year][0]
        archive = entries.get(feed) or {}
        if archive.get("status") not in {"reported", "retained_after_failure"} or archive.get("data") is None:
            continue
        footer = archive["data"]["workbook_printed_totals"]
        if footer.keys() != set(COUNTIES):
            raise ValueError("Early Alabama workbook-control roster changed")
        for row in controls:
            if row["year"] != year or row["county"] == "TOTAL":
                continue
            name, computed = row["county"], row["county_archive_ballots"]
            native = footer[name]
            if native is not None:
                native = early_integer(native)
                if computed is None:
                    raise ValueError("Early Alabama workbook total without reporting units")
            delta = computed - native if native is not None else None
            audit.append({**row, "workbook_printed_ballots": native, "unit_sum_minus_workbook_printed": delta,
                          "workbook_decision": "reporting_units_unavailable" if computed is None else
                          "workbook_total_not_printed" if delta is None else
                          "workbook_internal_agreement" if delta == 0 else "workbook_internal_discrepancy"})
    return units, controls, audit
