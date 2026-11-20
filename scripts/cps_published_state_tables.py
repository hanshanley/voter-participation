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
PUBLICATIONS = {2016: 580, 2018: 583, 2020: 585, 2022: 586, 2024: 587}
LEGACY_PUBLICATIONS = {
    2008: "562-rv/table-0{table}.xls",
    2010: "voting-registration-2010-election/table{table}_2010.xls",
    2012: "568/table0{table}.xls",
    2014: "577/table0{table}.xls",
}
YEARS = sorted(PUBLICATIONS.keys() | LEGACY_PUBLICATIONS.keys())
EXPECTED = {(year, table) for year in YEARS for table in ("4b", "4c")}
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


def early_workbook(body, table):
    sheet, rows = workbook_rows(body, True, 13)
    title_fragment = {"4a": "of the Citizen Voting-Age Population",
                      "4b": "by Sex, Race and Hispanic Origin", "4c": "by Age"}[table]
    normalize = lambda v: " ".join((v or "").lower().split())
    header = tuple("moe" if normalize(v) == "margin of error1"
                   else normalize(v).replace(" 18+)", ")") for v in rows[5][3:])
    if (sheet != f"Table {table}" or not all(v in rows[1][0] for v in (
            f"Table {table}. Reported Voting and Registration", title_fragment, "November 2008"))
            or normalize(rows[2][0]) != "(in thousands)"
            or tuple(map(normalize, rows[4][1:4])) != ("total population", "total citizen population", "registered")
            or header != COMMON_HEADER
            or not any(row[0] == CONFIDENCE.replace("1 This", "1This") for row in rows)):
        raise ValueError("2008 CPS workbook headers differ")
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
                    raise ValueError("Duplicate 2008 CPS geography heading")
                headings.add(state)
            elif isinstance(label, str) and label.strip():
                state = None
            continue
        if table == "4a":
            state, native = places.get(label), "Total"
        elif isinstance(label, str) and label.startswith("."):
            native = label
        else:
            raise ValueError(f"Unknown 2008 CPS label at row {row_number}")
        group = native.lstrip(".").strip()
        group = LABEL_ALIASES.get(group, group)
        if state not in rosters or group not in rosters[state] or (state, group) in seen:
            raise ValueError(f"Unknown or duplicate 2008 CPS geography/group at row {row_number}")
        seen.add((state, group))
        markers, values = {}, {}
        for field, cell in zip(FIELDS, cells, strict=True):
            if cell in ("(B)", "-"):
                markers[field], values[field] = cell, None
                continue
            if (table, state, group, field, cell) == (
                    "4b", "SD", "White alone or in combination", "cvap_registered_pct", 423):
                markers[field], values[field] = "invalid_published_rate", None
                continue
            count = field.endswith("_thousands")
            if (type(cell) not in (int, float) or not math.isfinite(cell) or cell < 0
                    or (not count and cell > 100) or (count and not float(cell).is_integer())):
                raise ValueError(f"Invalid 2008 CPS field {field} at row {row_number}")
            values[field] = int(cell) if count else cell
        for prefix in ("vap_registered", "vap_voted", "cvap_registered", "cvap_voted"):
            marker = markers.get(prefix + "_pct")
            if marker == "invalid_published_rate" or (marker == "(B)" and values[prefix + "_moe_pp"] is not None):
                values[prefix + "_moe_pp"] = None
                markers[prefix + "_moe_pp"] = "withheld_without_valid_point"
            if (values[prefix + "_pct"] is None) != (values[prefix + "_moe_pp"] is None):
                raise ValueError(f"2008 CPS point and margin do not share availability at row {row_number}")
        output.append({"year": 2008, "election_type": "presidential", "state_code": state, "group": group,
                       "native_group": native, "dimension": ("overall" if group == "Total" else "age"
                                     if table == "4c" else "sex" if group in SEX else "race_or_hispanic_origin"),
                       **values, "source_markers": markers, "confidence_level_pct": 90, "source_table": table,
                       "source_sheet": sheet, "source_row": row_number, "source_url": source_url(2008, table),
                       "source_sha256": checksum})
    expected_headings = set() if table == "4a" else set(STATES) if table == "4b" else set(places.values())
    if headings != expected_headings or seen != {(code, group) for code, groups in rosters.items() for group in groups}:
        raise ValueError("Incomplete 2008 CPS geographic or demographic roster")
    return output


def parse_workbook(body, year, table):
    if year == 2008:
        return early_workbook(body, table)
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
        expected = {filename(y, t) for y, t in inventory}
        if set(archive.namelist()) != {"sources.json", *expected} or len(archive.namelist()) != len(expected) + 1:
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
    for year in YEARS:
        def totals(table):
            return {r["state_code"]: tuple(r[field] for field in FIELDS)
                    for r in frames[year, table] if r["group"] == "Total"}
        if year == 2008:
            if totals("4a") != totals("4b"):
                raise ValueError("CPS 4a and 4b totals differ for 2008")
            controls = totals("4a")
            age = frames[year, "4c"]
            held = {state for state, total in totals("4c").items() if total != controls[state]}
            by_state = {r["state_code"]: r for r in age if r["dimension"] == "overall"}
            held.update(state for state, total in by_state.items() if not age_frame_compatible(
                total, [r for r in age if r["state_code"] == state and r["dimension"] == "age"]))
            frames[year, "4c"] = [r for r in age if r["state_code"] not in held]
            del frames[CONTROL]
        elif totals("4b") != totals("4c"):
            raise ValueError(f"CPS 4b and 4c totals differ for {year}")
    return [r for frame in frames.values() for r in frame]


def summary(rows):
    early = [r for r in rows if r["year"] == 2008]
    return {"years": sorted({r["year"] for r in rows}), "rows": len(rows),
            "states_and_dc": len({r["state_code"] for r in rows} - {"US"}),
            "cvap_voting_rates": sum(r["cvap_voted_pct"] is not None for r in rows),
            "cvap_voting_rates_by_year": {str(year): sum(
                r["year"] == year and r["cvap_voted_pct"] is not None for r in rows)
                for year in sorted({r["year"] for r in rows})},
            **({"held_2008_age_frames": sorted({r["state_code"] for r in early if r["source_table"] == "4b"}
                                             - {r["state_code"] for r in early if r["source_table"] == "4c"})}
               if early else {}),
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
