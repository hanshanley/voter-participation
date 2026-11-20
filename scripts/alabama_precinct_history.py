"""Alabama's historical ballot counts, independently checked against county totals."""
import io
import re
from zipfile import ZipFile

from scripts.southeast_turnout import COUNTIES, NUMBER, collect_report

ROOT = "https://www.sos.alabama.gov/sites/default/files/election-data/"
FILES = {
    2022: ("2022-11/2022%20General%20Precinct%20Level%20Results.zip",
           "2023-05/General%20Election%202022%20Official%20Total%20Ballots%20Cast.pdf", "November 8, 2022"),
    2024: ("2024-12/2024-General%20Precinct%20Level%20Results.zip",
           "2025-01/2024GeneralElectionTotalBallotsCast.pdf", "November 5, 2024"),
}
FEEDS = {year: (f"AL-{year}-general-precinct-ballot-archive", f"AL-{year}-general-county-ballot-control")
         for year in FILES}
URLS = {feed: ROOT + path for year, paths in FILES.items() for feed, path in zip(FEEDS[year], paths[:2])}
CSV = "participation-al-precinct-ballot-archives.csv"
CONTROL_CSV = "participation-al-precinct-ballot-county-controls.csv"
COUNTY_KEYS = {county.replace("_", ""): county for county in COUNTIES}
MODE_LABELS = {
    "ABSENTEE", "PROVISIONAL", "PROVISIONAL ABSENTEE", "ABSENTEE PROVISIONAL",
    "BESSEMER ABSENTEE", "BIRMINGHAM ABSENTEE", "PROVISIONAL OFFICIAL",
}


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
            match = re.fullmatch(rf"{year}-General-([A-Za-z ._'-]+)\.xls", item.filename)
            county = COUNTY_KEYS.get(county_key(match[1])) if match else None
            if county is None or county in counties or not 0 < item.file_size <= 1_000_000:
                raise ValueError("Unknown, oversized or repeated Alabama county workbook")
            book = xlrd.open_workbook(file_contents=z.read(item))
            if book.sheet_names() != ["Precinct Results"]:
                raise ValueError("Alabama precinct results sheet changed")
            sheet = book.sheet_by_index(0)
            if [str(sheet.cell_value(i, 0)).strip() for i in range(4)] != [
                    "Contest Title", "REGISTERED VOTERS - TOTAL", "BALLOTS CAST - TOTAL", "BALLOTS CAST - BLANK"
            ] or [str(v).strip() for v in sheet.row_values(0)[:3]] != ["Contest Title", "Party", "Candidate"]:
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
    title = f"General Election {'–' if year == 2022 else '-'} {FILES[year][2]}"
    columns = ("County Registered Total Ballots Cast Party Republican Absentee Percentage Percentage"
               if year == 2022 else
               "County Voters Ballots Cast Ballots Ballots Ballots Registered Voters Total Ballots")
    if title not in lines or "Official Total Ballots Cast" not in lines or columns not in lines:
        raise ValueError("Alabama county ballot control election or measure changed")
    match_row = re.compile(rf"([A-Za-z. ]+) ((?:{NUMBER} ){{5}})\d{{1,3}}\.\d+% \d{{1,3}}\.\d+%")
    values = {}
    for line in lines:
        match = match_row.fullmatch(line)
        if not match:
            continue
        key = county_key(match[1])
        county = "TOTAL" if key == "TOTAL" else COUNTY_KEYS.get(key)
        if county is None or county in values:
            raise ValueError("Unexpected Alabama control county")
        registration, ballots, _, _, absentee = [int(value.replace(",", "")) for value in match[2].split()]
        if not 0 <= absentee <= ballots <= registration:
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
    return collect_report(collector, feed, URLS[feed], parse, reuse_checked_week=reuse_checked_week)


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
        archive_sums = {name: sum(row[1] for row in rows) for name, rows in workbooks.items()}
        if workbooks:
            archive_sums["TOTAL"] = sum(archive_sums.values())
        provenance = {"state_code": "AL", "year": year,
                      "archive_url": URLS[archive_feed], "control_url": URLS[control_feed],
                      "archive_status": archive.get("status"), "control_status": control.get("status"),
                      "archive_checked_week_utc": archive.get("archive_check_week_utc"),
                      "control_checked_week_utc": control.get("archive_check_week_utc"),
                      "archive_sha256": (archive.get("source") or {}).get("sha256"),
                      "control_sha256": (control.get("source") or {}).get("sha256")}
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
                          else "reporting_unit_no_boundary_binding",
                          "reported_ballots": ballots, "unqualified_registration_cell": registration,
                          "reconciliation": decision}
                         for index, (label, ballots, registration) in enumerate(workbooks.get(name, ()), 1))
    return units, county
