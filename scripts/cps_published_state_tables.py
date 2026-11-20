"""Published Census CPS Table 4b/4c rows, not estimates from respondent records."""

import argparse
import csv
import io
import json
import math
import zipfile
from pathlib import Path

from scripts.nationwide import STATES
from scripts.participation_intake.contract import encoded, pin

INPUT = "cps-published-state-workbooks.zip"
INPUT_PATH = "data/results-intake/" + INPUT
CSV = "participation-cps-published-state-tables.csv"
OVERALL_CSV = "participation-cps-state-overall-history.csv"
OVERALL_BASE = "https://www2.census.gov/programs-surveys/cps/tables/time-series/voting-historical-time-series/"
OVERALL_TABLES = {
    "hst_vote03a.xlsx": ("A-3a", "midterm", "voted"),
    "hst_vote03b.xlsx": ("A-3b", "midterm", "registered"),
    "a5a.xlsx": ("A-5a", "presidential", "voted"),
    "a5b.xlsx": ("A-5b", "presidential", "registered"),
}
OVERALL_MANIFEST = "overall-sources.json"
PUBLICATIONS = {2016: 580, 2018: 583, 2020: 585, 2022: 586, 2024: 587}
LEGACY_PUBLICATIONS = {
    2002: "552/tab0{table}.xls",
    2004: "556/tab0{table}.xls",
    2006: "557/tab0{table}.xls",
    2008: "562-rv/table-0{table}.xls",
    2010: "voting-registration-2010-election/table{table}_2010.xls",
    2012: "568/table0{table}.xls",
    2014: "577/table0{table}.xls",
}
VAP_YEARS = {2002, 2004}
YEARS = sorted((PUBLICATIONS.keys() | LEGACY_PUBLICATIONS.keys()) - VAP_YEARS - {2006})
EXPECTED = {(year, table) for year in YEARS for table in ("4b", "4c")}
MIDTERM_2006 = {(2006, "4a"), (2006, "4b")}
CONTROL = (2008, "4a")
SEX = ("Male", "Female")
RACE = ("White alone", "White non-Hispanic alone", "Black alone", "Asian alone",
        "Hispanic (any race)", "White alone or in combination", "Black alone or in combination",
        "Asian alone or in combination")
AGES = ("18 to 24", "25 to 34", "35 to 44", "45 to 64", "65+")
AGES_2010 = ("18 to 24", "25 to 44", "45 to 64", "65 to 74", "75+")
AGES_2008_US = ("18 to 24", "25 to 34", "35 to 44", "45 to 54", "55 to 64", "65 to 74", "75+")
AGES_2008_COLLAPSED = ("18 to 44", "45 to 64", "65+")
COLLAPSED_2008 = {"AK", "DE", "DC", "ID", "MT", "ND", "RI", "SD", "VT", "WY"}
LABEL_ALIASES = {"Hispanic (of any race)": "Hispanic (any race)", "65 years and over": "65+",
                 **{f"{age} years": age for age in AGES[:-1]}}
FIELDS = ("voting_age_population_thousands", "citizen_voting_age_population_thousands",
          "reported_registered_thousands", "vap_registered_pct", "vap_registered_moe_pp",
          "cvap_registered_pct", "cvap_registered_moe_pp", "reported_voted_thousands",
          "vap_voted_pct", "vap_voted_moe_pp", "cvap_voted_pct", "cvap_voted_moe_pp")
COMMON_HEADER = ("total registered", "percent registered (total)", "moe",
                 "percent registered (citizen)", "moe", "total voted",
                 "percent voted (total)", "moe", "percent voted (citizen)", "moe")
CONFIDENCE = "1 This figure added to or subtracted from the estimate provides the 90-percent confidence interval."
VAP_RACE_2002 = ("Non-Hispanic White", "Non-Hispanic Black", "Asian and Pacific Islander",
                 "Hispanic (any race)", "White", "Black")


def filename(year, table):
    extension = "xls" if year in LEGACY_PUBLICATIONS else "xlsx"
    return f"{year}-table{table}.{extension}"


def source_url(year, table):
    if year in LEGACY_PUBLICATIONS:
        return ("https://www2.census.gov/programs-surveys/cps/tables/p20/"
                + LEGACY_PUBLICATIONS[year].format(table=table))
    base = f"https://www2.census.gov/programs-surveys/cps/tables/p20/{PUBLICATIONS[year]}/"
    return base + (f"table0{table}.xlsx" if year < 2022 else f"vote0{table}_{year}.xlsx")


def workbook_rows(body, legacy, columns=14):
    if legacy:
        import xlrd

        with xlrd.open_workbook(file_contents=body, on_demand=True) as book:
            if book.nsheets != 1:
                raise ValueError("CPS workbook has an unexpected sheet inventory")
            sheet = book.sheet_by_index(0)
            if sheet.ncols != columns:
                raise ValueError("CPS legacy workbook columns differ")
            return sheet.name, [tuple(v if v != "" else None for v in sheet.row_values(i))
                                for i in range(sheet.nrows)]
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        if len(book.sheetnames) != 1:
            raise ValueError("CPS workbook has an unexpected sheet inventory")
        sheet = book.active
        return sheet.title, list(sheet.iter_rows(max_col=14, values_only=True))
    finally:
        book.close()


def early_workbook(body, year, table):
    sheet, rows = workbook_rows(body, True, 13)
    title_fragment = {"4a": "of the Citizen Voting-Age Population",
                      "4b": "by Sex, Race and Hispanic Origin", "4c": "by Age"}[table]
    normalize = lambda v: " ".join((v or "").lower().split())
    header = tuple("moe" if normalize(v) == "margin of error1"
                   else normalize(v).replace(" 18+)", ")") for v in rows[5][3:])
    if (sheet != f"Table {table}" or not all(v in rows[1][0] for v in (
            f"Table {table}. Reported Voting and Registration", title_fragment, f"November {year}"))
            or normalize(rows[2][0]) != "(in thousands)"
            or tuple(map(normalize, rows[4][1:4])) != ("total population", "total citizen population", "registered")
            or header != COMMON_HEADER
            or not any(row[0] == CONFIDENCE.replace("1 This", "1This") for row in rows)):
        raise ValueError(f"{year} CPS workbook headers differ")
    places = {name.upper(): code for code, name in STATES.items()} | {"UNITED STATES": "US"}
    rosters = {
        code: {"Total", *(() if table == "4a" else (*SEX, *RACE) if table == "4b"
                         else AGES_2008_US if code == "US" else AGES_2008_COLLAPSED
                         if code in COLLAPSED_2008 else AGES_2010)}
        for code in places.values()
    }
    state = "US" if table == "4b" else None
    seen, headings, output = set(), set(), []
    checksum = pin(body)["sha256"]
    for row_number, (label, *cells) in enumerate(rows[6:], 7):
        if all(v is None for v in cells):
            if table == "4c" and isinstance(label, str) and label.endswith(" 2") and (
                    places.get(label[:-2]) in COLLAPSED_2008):
                label = label[:-2]
            if label in places and table != "4a":
                state = places[label]
                if state in headings:
                    raise ValueError(f"Duplicate {year} CPS geography heading")
                headings.add(state)
            elif isinstance(label, str) and label.strip():
                state = None
            continue
        if table == "4a":
            state, native = places.get(label), "Total"
        elif isinstance(label, str) and label.startswith("."):
            native = label
        else:
            raise ValueError(f"Unknown {year} CPS label at row {row_number}")
        group = native.lstrip(".").strip()
        group = LABEL_ALIASES.get(group, group)
        if state not in rosters or group not in rosters[state] or (state, group) in seen:
            raise ValueError(f"Unknown or duplicate {year} CPS geography/group at row {row_number}")
        seen.add((state, group))
        markers, values = {}, {}
        for field, cell in zip(FIELDS, cells, strict=True):
            if cell in ("(B)", "-"):
                markers[field], values[field] = cell, None
                continue
            if (year, table, state, group, field, cell) == (
                    2008, "4b", "SD", "White alone or in combination", "cvap_registered_pct", 423):
                markers[field], values[field] = "invalid_published_rate", None
                continue
            count = field.endswith("_thousands")
            if (type(cell) not in (int, float) or not math.isfinite(cell) or cell < 0
                    or (not count and cell > 100) or (count and not float(cell).is_integer())):
                raise ValueError(f"Invalid {year} CPS field {field} at row {row_number}")
            values[field] = int(cell) if count else cell
        for prefix in ("vap_registered", "vap_voted", "cvap_registered", "cvap_voted"):
            marker = markers.get(prefix + "_pct")
            if marker == "invalid_published_rate" or (marker == "(B)" and values[prefix + "_moe_pp"] is not None):
                values[prefix + "_moe_pp"] = None
                markers[prefix + "_moe_pp"] = "withheld_without_valid_point"
            if (values[prefix + "_pct"] is None) != (values[prefix + "_moe_pp"] is None):
                raise ValueError(f"{year} CPS point and margin do not share availability at row {row_number}")
        output.append({"year": year, "election_type": "presidential" if year % 4 == 0 else "midterm",
                       "state_code": state, "group": group,
                       "native_group": native, "dimension": ("overall" if group == "Total" else "age"
                                     if table == "4c" else "sex" if group in SEX else "race_or_hispanic_origin"),
                       **values, "source_markers": markers, "confidence_level_pct": 90, "source_table": table,
                       "source_sheet": sheet, "source_row": row_number, "source_url": source_url(year, table),
                       "source_sha256": checksum})
    expected_headings = set() if table == "4a" else set(STATES) if table == "4b" else set(places.values())
    if headings != expected_headings or seen != {(code, group) for code, groups in rosters.items() for group in groups}:
        raise ValueError(f"Incomplete {year} CPS geographic or demographic roster")
    return output


def legacy_vap_workbook(body, year, table):
    citizen = table == "4c"
    has_vap_count = not (citizen and year == 2004)
    sheet, rows = workbook_rows(body, True, 11 if has_vap_count else 10)
    description = {"4a": "by Sex, Race and Hispanic Origin",
                   "4b": "by Age", "4c": "of the Citizen Voting-Age Population"}[table]
    normalize = lambda label: " ".join((label or "").lower().split())
    header_kind = "citizen" if citizen else "18+"
    error = "confidence interval" if year == 2002 else "margin of error1"
    measure_header = ("total", f"percent registered ({header_kind})", error,
                      "total", f"percent voted ({header_kind})", error)
    count_index = 2 if has_vap_count else 1
    measures_index = count_index + 3
    if (sheet != (f"Table {table}" if year == 2002 else "Sheet1")
            or not all(v in rows[1][0] for v in (f"Table {table}. Reported Voting and Registration",
                                                description, f"November {year}"))
            or normalize(rows[2][0]) != "(in thousands)"
            or (not citizen and "of the Total Voting-Age Population" not in rows[1][0])
            or (has_vap_count and normalize(rows[4][1]) != "population 18 and over")
            or normalize(rows[4][count_index]) != "total citizen"
            or tuple(map(normalize, rows[5][measures_index:])) != measure_header
            or (year == 2004 and not any(r[0] == CONFIDENCE.replace("1 This", "1This") for r in rows))):
        raise ValueError(f"{year} CPS Table {table} header differs")
    places = {name.upper(): code for code, name in STATES.items()} | {"UNITED STATES": "US"}
    expected_groups = {"Total", *(() if citizen else AGES_2010 if table == "4b" else
                        (*SEX, *(VAP_RACE_2002 if year == 2002 else (*RACE,
                            "White non-Hispanic alone or in combination"))))}
    seen, headings, output = set(), set(), []
    checksum = pin(body)["sha256"]
    state = None
    for row_number, row in enumerate(rows[6:], 7):
        label = (row[0] or "").strip()
        has_values = any(v is not None and v != " " for v in row[1:])
        if not has_values:
            if label in places and not citizen:
                state = places[label]
                if state in headings:
                    raise ValueError("Duplicate historical CPS geography")
                headings.add(state)
            elif label:
                state = None
            continue
        if citizen:
            state, native = places.get(label), "Total"
        elif label.startswith("."):
            native = row[0]
        else:
            raise ValueError(f"Unknown historical CPS row {year}/{table}/{row_number}")
        name = label.lstrip(".").strip()
        group = "Total" if citizen else LABEL_ALIASES.get(name, name)
        if (year, table, state, row_number, group) == (2004, "4a", "AZ", 50, "Non-Hispanic White"):
            if rows[row_number][0] != ".White alone" or row[1:] != rows[row_number][1:]:
                raise ValueError("Unreviewed Arizona CPS label conflict")
            continue
        if state is None or group not in expected_groups or (state, group) in seen:
            raise ValueError(f"Unknown or duplicate historical CPS identity {year}/{table}/{row_number}")
        seen.add((state, group))
        markers, values = {}, dict.fromkeys(FIELDS)
        basis = "cvap" if citizen else "vap"
        cells = {"citizen_voting_age_population_thousands": row[count_index]}
        if has_vap_count:
            cells["voting_age_population_thousands"] = row[1]
        for i, measure in enumerate(("registered", "voted")):
            index = measures_index + i * 3
            cells.update(zip((f"reported_{measure}_thousands", f"{basis}_{measure}_pct",
                              f"{basis}_{measure}_moe_pp"), row[index:index + 3], strict=True))
        for field in values:
            if field not in cells:
                markers[field] = "not_in_table"
                continue
            cell = cells[field]
            if isinstance(cell, str) and cell.strip() in ("(B)", "-"):
                markers[field] = cell.strip()
                continue
            count = field.endswith("_thousands")
            if (type(cell) not in (int, float) or not math.isfinite(cell) or cell < 0
                    or (not count and cell > 100) or (count and not float(cell).is_integer())):
                raise ValueError(f"Invalid historical CPS field {year}/{table}/{row_number}/{field}")
            values[field] = int(cell) if count else cell
        for measure in ("registered", "voted"):
            if (values[f"{basis}_{measure}_pct"] is None) != (values[f"{basis}_{measure}_moe_pp"] is None):
                raise ValueError("Historical CPS point and uncertainty availability differs")
        # The source originals keep the anomalous values. Do not repair them from rounded cells.
        if (year, table, state, group) == (2002, "4a", "US", "Non-Hispanic White"):
            if row[1:3] != (105499, 147171):
                raise ValueError("Unreviewed national estimate in the 2002 CPS workbook")
            for key, value in values.items():
                if value is not None:
                    values[key], markers[key] = None, "invalid_published_rate"
        if (year, table, state, group) == (2002, "4a", "WI", "Non-Hispanic White"):
            if row[5:8] != (2650, 70.7, 1.9):
                raise ValueError("Unreviewed Wisconsin estimate in the 2002 CPS workbook")
            for key in ("reported_registered_thousands", "vap_registered_pct", "vap_registered_moe_pp"):
                values[key], markers[key] = None, "invalid_published_rate"
        output.append({"year": year, "election_type": "presidential" if year % 4 == 0 else "midterm",
                       "state_code": state, "group": group, "native_group": native,
                       "dimension": ("overall" if group == "Total" else "age" if table == "4b"
                                     else "sex" if group in SEX else "race_or_hispanic_origin"),
                       **values, "source_markers": markers, "confidence_level_pct": 90,
                       "source_table": table, "source_sheet": sheet, "source_row": row_number,
                       "source_url": source_url(year, table), "source_sha256": checksum})
    if seen != {(code, group) for code in places.values() for group in expected_groups}:
        raise ValueError("Incomplete historical CPS geographic or demographic roster")
    return output


def parse_workbook(body, year, table):
    if year in VAP_YEARS:
        return legacy_vap_workbook(body, year, table)
    if year == 2008 or (year, table) in MIDTERM_2006:
        return early_workbook(body, year, table)
    legacy = year in LEGACY_PUBLICATIONS
    sheet_name, rows = workbook_rows(body, legacy)
    title_index = 0 if year == 2010 else 1
    title = rows[title_index][0]
    required = "by Age" if table == "4c" else "by Sex, Race and Hispanic Origin"
    clauses = (f"Table {table}.", "Reported Voting and Registration", required, f"November {year}")
    if not isinstance(title, str) or not all(clause in title for clause in clauses):
        raise ValueError("CPS table, dimension, or election year differs")
    if "in thousands" not in rows[title_index + 1][0].lower():
        raise ValueError("CPS count units differ")
    normalize = lambda value: " ".join((value or "").lower().split())
    upper = next((i for i, row in enumerate(rows[:5])
                  if normalize(row[0]) in ("state", "characteristics")), None)
    if upper is None or tuple(map(normalize, rows[upper][2:5])) != (
            "total population", "total citizen population", "total registered" if legacy else "registered"):
        raise ValueError("CPS population columns differ")
    header_row = upper if legacy else upper + 1
    header = tuple("moe" if normalize(v) in ("margin of error", "margin of error 1",
                                            "margin of error1", "margin of error (+/-)1") else normalize(v)
                   for v in rows[header_row][4:])
    confidence_notes = {CONFIDENCE, CONFIDENCE.replace("1 This", "1This")}
    if header != COMMON_HEADER or not any(row[0] in confidence_notes for row in rows):
        raise ValueError("CPS measure or published uncertainty columns differ")
    codes = {name.upper(): code for code, name in STATES.items()} | {"US": "US", "UNITED STATES": "US"}
    if year == 2012:
        codes["All"] = "US"
    age_groups = AGES_2010 if year == 2010 else AGES
    expected_groups = ("Total", *(age_groups if table == "4c" else (*SEX, *RACE)))
    output, seen = [], set()
    state = None
    checksum = pin(body)["sha256"]
    for row_number, row in enumerate(rows[header_row + 1:], header_row + 2):
        place, native_group, *cells = row
        if native_group is None and all(value is None for value in cells):
            continue
        if place:
            state = codes.get(place)
        label = native_group.lstrip(".").strip() if legacy and isinstance(native_group, str) else native_group
        group = LABEL_ALIASES.get(label, label)
        if state is None or group not in expected_groups or (state, group) in seen:
            raise ValueError(f"Unknown or duplicate CPS geographic/group identity at row {row_number}")
        seen.add((state, group))
        markers, values = {}, {}
        for field, cell in zip(FIELDS, cells, strict=True):
            if cell in ("B", "(B)", "-"):
                markers[field] = cell
                cell = None
            elif (type(cell) not in (int, float) or not math.isfinite(cell) or cell < 0
                  or (not field.endswith("_thousands") and cell > 100)
                  or (field.endswith("_thousands") and (
                      not float(cell).is_integer() if legacy else type(cell) is not int))):
                raise ValueError(f"Invalid CPS field {field} at row {row_number}")
            elif legacy and field.endswith("_thousands"):
                cell = int(cell)
            values[field] = cell
        for population in ("vap", "cvap"):
            for measure in ("registered", "voted"):
                if (values[f"{population}_{measure}_pct"] is None) != (
                        values[f"{population}_{measure}_moe_pp"] is None):
                    raise ValueError("CPS point and margin do not share availability")
        output.append({"year": year, "election_type": "presidential" if year % 4 == 0 else "midterm",
                       "state_code": state, "group": group, "native_group": native_group,
                       "dimension": ("overall" if group == "Total" else "age" if table == "4c"
                                     else "sex" if group in SEX else "race_or_hispanic_origin"),
                       **values, "source_markers": markers, "confidence_level_pct": 90,
                       "source_table": table, "source_sheet": sheet_name, "source_row": row_number,
                       "source_url": source_url(year, table), "source_sha256": checksum})
    if seen != {(code, group) for code in {*STATES, "US"} for group in expected_groups}:
        raise ValueError("Incomplete CPS state/age/sex/race roster")
    return output


def age_frame_compatible(total, age_rows):
    for field in (field for field in FIELDS if field.endswith("_thousands")):
        values = [row[field] for row in age_rows]
        if total[field] is None or any(value is None for value in values):
            return False
        if abs(sum(values) - total[field]) > (len(values) + 1) / 2:
            return False
    for row in age_rows:
        for basis, population in (("cvap", "citizen_voting_age_population_thousands"),
                                  ("vap", "voting_age_population_thousands")):
            for measure in ("registered", "voted"):
                top, bottom = row[f"reported_{measure}_thousands"], row[population]
                point = row[f"{basis}_{measure}_pct"]
                if point is None:
                    continue
                if bottom == 0 or not (100 * (top - .5) / (bottom + .5) - .050001 <= point
                                       <= 100 * (top + .5) / (bottom - .5) + .050001):
                    return False
    return True


def build(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        inventory = EXPECTED | {CONTROL}
        if any(filename(year, table) in archive.namelist() for year, table in MIDTERM_2006):
            inventory |= MIDTERM_2006
        for year in VAP_YEARS:
            trio = {(year, table) for table in ("4a", "4b", "4c")}
            if any(filename(y, table) in archive.namelist() for y, table in trio):
                inventory |= trio
        expected = {filename(y, t) for y, t in inventory}
        members = {"sources.json", *expected}
        if OVERALL_MANIFEST in archive.namelist():
            members |= {OVERALL_MANIFEST, *OVERALL_TABLES}
        from scripts import cps_archived_state_tables as archived
        if archived.MANIFEST in archive.namelist():
            members |= {archived.MANIFEST, *(archived.filename(*key) for key in archived.SOURCES)}
        if set(archive.namelist()) != members or len(archive.namelist()) != len(members):
            raise ValueError("Incomplete or duplicate CPS workbook bundle")
        sources = json.loads(archive.read("sources.json"))
        if set(sources) != expected:
            raise ValueError("CPS manifest differs from workbook bundle")
        frames = {}
        for year, table in sorted(inventory):
            name = filename(year, table)
            body = archive.read(name)
            receipt = sources[name]
            if (receipt["year"], receipt["table"], receipt["url"],
                {k: receipt[k] for k in ("bytes", "sha256")}) != (
                    year, table, source_url(year, table), pin(body)):
                raise ValueError(f"CPS source identity or checksum differs: {name}")
            frames[year, table] = parse_workbook(body, year, table)
    def totals(year, table):
        return {r["state_code"]: tuple(r[field] for field in FIELDS)
                for r in frames[year, table] if r["group"] == "Total"}

    for year in VAP_YEARS:
        if (year, "4a") not in frames:
            continue
        controls = {r["state_code"]: r for r in frames[year, "4a"] if r["group"] == "Total"}
        count_fields = tuple(f for f in FIELDS if f.endswith("_thousands")
                             and not (year == 2004 and f == "voting_age_population_thousands"))
        for row in frames[year, "4c"]:
            if any(row[key] != controls[row["state_code"]][key] for key in count_fields):
                raise ValueError(f"Historical CPS citizen controls differ for {year}")
        age_rows = frames[year, "4b"]
        age_totals = totals(year, "4b")
        held = {code for code, total in totals(year, "4a").items() if age_totals[code] != total
                or not age_frame_compatible(controls[code], [r for r in age_rows
                    if r["state_code"] == code and r["dimension"] == "age"])}
        frames[year, "4b"] = [r for r in age_rows if r["state_code"] not in held]
    if MIDTERM_2006 <= frames.keys():
        if totals(2006, "4a") != totals(2006, "4b"):
            raise ValueError("CPS 4a and 4b totals differ for 2006")
        del frames[2006, "4a"]
    for year in YEARS:
        if year == 2008:
            if totals(year, "4a") != totals(year, "4b"):
                raise ValueError("CPS 4a and 4b totals differ for 2008")
            controls = totals(year, "4a")
            age = frames[year, "4c"]
            held = {state for state, total in totals(year, "4c").items() if total != controls[state]}
            by_state = {r["state_code"]: r for r in age if r["dimension"] == "overall"}
            held.update(state for state, total in by_state.items() if not age_frame_compatible(
                total, [r for r in age if r["state_code"] == state and r["dimension"] == "age"]))
            frames[year, "4c"] = [r for r in age if r["state_code"] not in held]
            del frames[CONTROL]
        elif totals(year, "4b") != totals(year, "4c"):
            raise ValueError(f"CPS 4b and 4c totals differ for {year}")
    return [r for frame in frames.values() for r in frame]


def parse_overall_workbook(body, table, election, measure):
    states = {name: code for code, name in STATES.items()}
    start, stop, first_citizen = (1974, 2022, 1978) if election == "midterm" else (1972, 2024, 1980)
    roster = [(year, basis) for year in range(stop, start - 1, -4)
              for basis in ("vap", "cvap") if basis == "vap" or year >= first_citizen]
    from openpyxl import load_workbook

    with io.BytesIO(body) as stream:
        book = load_workbook(stream, read_only=True, data_only=True)
        try:
            if len(book.sheetnames) != 1 or book.active.max_column != len(roster) + 1:
                raise ValueError("CPS overall workbook inventory differs")
            sheet, rows = book.active.title, list(book.active.values)
        finally:
            book.close()
    topic = "Voting" if measure == "voted" else "Registration"
    cycle = "Congressional" if election == "midterm" else "Presidential"
    if (rows[1][0] != f"Table {table}. Reported {topic} for Total and Citizen Voting-Age Populations, "
            f"by State for {cycle} Elections: {start} to {stop}"
            or rows[2][0] != "(Percent, Population 18 Years and Over)" or rows[3][0] != "State"
            or tuple(rows[3][1:]) != tuple(y if b == "vap" else None for y, b in roster)
            or tuple(rows[4][1:]) != tuple("Total" if b == "vap" else "Citizen" for _, b in roster)
            or not any(isinstance(r[0], str) and "prior to 1996" in r[0] and "not directly comparable" in r[0]
                       for r in rows)):
        raise ValueError("CPS overall workbook definition or years differ")
    numbers, seen = {}, set()
    for row_number, (place, *cells) in enumerate(rows[5:], 6):
        if place not in states:
            if any(cell is not None for cell in cells):
                raise ValueError(f"Unknown CPS overall geography at row {row_number}")
            continue
        code = states[place]
        if code in seen:
            raise ValueError(f"Duplicate CPS overall geography at row {row_number}")
        seen.add(code)
        for (year, basis), point in zip(roster, cells, strict=True):
            if point != "N" and (type(point) not in (int, float) or not math.isfinite(point) or not 0 <= point <= 100):
                raise ValueError(f"Invalid CPS overall percentage at row {row_number}")
            numbers[year, code, basis] = (None if point == "N" else point, "N" if point == "N" else "",
                                          sheet, row_number)
        for year in range(start, first_citizen, 4):
            numbers[year, code, "cvap"] = (None, "not_in_table", sheet, row_number)
    if seen != set(STATES):
        raise ValueError("Incomplete CPS overall state roster")
    return numbers


def build_overall(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        if OVERALL_MANIFEST not in archive.namelist():
            return []
        receipts = json.loads(archive.read(OVERALL_MANIFEST))
        if set(receipts) != set(OVERALL_TABLES):
            raise ValueError("CPS overall manifest differs from workbook bundle")
        series = {}
        for name, (table, election, measure) in OVERALL_TABLES.items():
            body, url = archive.read(name), OVERALL_BASE + name
            checksum = pin(body)
            if receipts[name] != {"table": table, "url": url, **checksum}:
                raise ValueError(f"CPS overall source identity or checksum differs: {name}")
            series[election, measure] = (parse_overall_workbook(body, table, election, measure), url, checksum["sha256"])
    out = []
    for election in ("midterm", "presidential"):
        voting, vu, vh = series[election, "voted"]
        registration, ru, rh = series[election, "registered"]
        if voting.keys() != registration.keys():
            raise ValueError("CPS overall voting and registration rosters differ")
        for (year, code, basis), (vp, vm, vs, vr) in voting.items():
            rp, rm, rs, rr = registration[year, code, basis]
            out.append({"year": year, "election_type": election, "state_code": code, "denominator_basis": basis,
                        "reported_voted_pct": vp, "voted_source_marker": vm,
                        "reported_registered_pct": rp, "registered_source_marker": rm,
                        "citizenship_measurement_caution": basis == "cvap" and year < 1996,
                        "voted_source_url": vu, "voted_source_sha256": vh, "voted_source_sheet": vs,
                        "voted_source_row": vr, "registered_source_url": ru, "registered_source_sha256": rh,
                        "registered_source_sheet": rs, "registered_source_row": rr})
    return sorted(out, key=lambda r: (r["state_code"], r["denominator_basis"], r["year"]))


def overall_summary(rows):
    return {"years": sorted({r["year"] for r in rows}), "rows": len(rows),
            "states_and_dc": len({r["state_code"] for r in rows}),
            "reported_voting_rates": sum(r["reported_voted_pct"] is not None for r in rows),
            "reported_registration_rates": sum(r["reported_registered_pct"] is not None for r in rows),
            "administratively_observed_turnout": False, "published_margins_of_error": False}


def overall_csv(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def summary(rows):
    early = [r for r in rows if r["year"] == 2008]
    legacy = {str(year): sorted({r["state_code"] for r in rows if r["year"] == year and r["source_table"] == "4a"}
                                - {r["state_code"] for r in rows if r["year"] == year and r["source_table"] == "4b"})
              for year in sorted(VAP_YEARS & {r["year"] for r in rows})}
    return {"years": sorted({r["year"] for r in rows}), "rows": len(rows),
            "states_and_dc": len({r["state_code"] for r in rows} - {"US"}),
            "cvap_voting_rates": sum(r["cvap_voted_pct"] is not None for r in rows),
            "cvap_voting_rates_by_year": {str(year): sum(
                r["year"] == year and r["cvap_voted_pct"] is not None for r in rows)
                for year in sorted({r["year"] for r in rows})},
            **({"held_2008_age_frames": sorted({r["state_code"] for r in early if r["source_table"] == "4b"}
                                             - {r["state_code"] for r in early if r["source_table"] == "4c"})}
               if early else {}),
            **({"held_vap_age_frames": legacy} if legacy else {}),
            "separate_from_other_survey_series": True, "administratively_observed_turnout": False}


def csv_body(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows({**row, "source_markers": encoded(row["source_markers"]).decode().strip()} for row in rows)
    return out.getvalue().encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbooks", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = build(args.workbooks.read_bytes())
    with args.output.open("xb") as target:
        target.write(csv_body(rows))
    print(json.dumps(summary(rows), sort_keys=True))


if __name__ == "__main__":
    main()
