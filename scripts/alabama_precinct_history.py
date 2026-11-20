"""Alabama's reporting-unit ballot counts and compatible county controls."""
import io
import re
from zipfile import ZipFile

from scripts.participation_intake.contract import pin
from scripts.southeast_turnout import COUNTIES, NUMBER, collect_report

ROOT = "https://www.sos.alabama.gov/sites/default/files/election-data/"
INDEX = "https://www.sos.alabama.gov/alabama-votes/voter/election-data"
CURRENT_CONTROL = "AL-2026-general-county-ballot-control"
CURRENT_CONTROL_ROUTE = (re.escape(ROOT) + r"20(?:26|27)-(?:0[1-9]|1[0-2])/"
                         r"(?=[^/]*2026)[A-Za-z0-9_%.-]+\.pdf")
FILES = {
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
COUNTY_KEYS = {county.replace("_", ""): county for county in COUNTIES}
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


def validate_units(data):
    if set(data) != set(COUNTY_KEYS.values()):
        raise ValueError("Alabama precinct workbook county roster changed")
    for county, rows in data.items():
        if not rows or len(rows) > 400:
            raise ValueError(f"Alabama reporting-unit inventory out of bounds: {county}")
        seen = set()
        for label, ballots, register in rows:
            if (not isinstance(label, str) or not label or len(label) > 200
                    or any(ord(char) < 32 for char in label)
                    or label.upper() in seen or re.match(r"^(?:TOTAL|GRAND TOTAL)\b", label, re.I)
                    or type(ballots) is not int or ballots < 0
                    or register is not None and (type(register) is not int or register < 0)):
                raise ValueError(f"Invalid Alabama reporting unit: {county}")
            seen.add(label.upper())
    return data


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
        workbooks = {} if csv_entry is None else validate_units(csv_entry["complete_native_query"])
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
        archive_sums = {name: sum(row[1] for row in rows) for name, rows in workbooks.items()}
        if workbooks:
            archive_sums["TOTAL"] = sum(archive_sums.values())
        provenance = {"state_code": "AL", "year": year,
                      "archive_url": URLS[archive_feed],
                      "control_url": control_source.get("url", URLS[control_feed]),
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
