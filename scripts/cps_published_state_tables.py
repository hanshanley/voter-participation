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
    2010: "voting-registration-2010-election/table{table}_2010.xls",
    2012: "568/table0{table}.xls",
    2014: "577/table0{table}.xls",
}
YEARS = sorted(PUBLICATIONS.keys() | LEGACY_PUBLICATIONS.keys())
EXPECTED = {(year, table) for year in YEARS for table in ("4b", "4c")}
SEX = ("Male", "Female")
RACE = ("White alone", "White non-Hispanic alone", "Black alone", "Asian alone",
        "Hispanic (any race)", "White alone or in combination", "Black alone or in combination",
        "Asian alone or in combination")
AGES = ("18 to 24", "25 to 34", "35 to 44", "45 to 64", "65+")
AGES_2010 = ("18 to 24", "25 to 44", "45 to 64", "65 to 74", "75+")
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


def workbook_rows(body, legacy):
    if legacy:
        import xlrd

        with xlrd.open_workbook(file_contents=body, on_demand=True) as book:
            if book.nsheets != 1:
                raise ValueError("CPS workbook has an unexpected sheet inventory")
            sheet = book.sheet_by_index(0)
            if sheet.ncols != 14:
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


def parse_workbook(body, year, table):
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


def build(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        expected = {filename(y, t) for y, t in EXPECTED}
        if set(archive.namelist()) != {"sources.json", *expected} or len(archive.namelist()) != len(expected) + 1:
            raise ValueError("Incomplete or duplicate CPS workbook bundle")
        sources = json.loads(archive.read("sources.json"))
        if set(sources) != expected:
            raise ValueError("CPS manifest differs from workbook bundle")
        frames = {}
        for year, table in sorted(EXPECTED):
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
        if totals("4b") != totals("4c"):
            raise ValueError(f"CPS 4b and 4c totals differ for {year}")
    return [r for frame in frames.values() for r in frame]


def summary(rows):
    return {"years": sorted({r["year"] for r in rows}), "rows": len(rows),
            "states_and_dc": len({r["state_code"] for r in rows} - {"US"}),
            "cvap_voting_rates": sum(r["cvap_voted_pct"] is not None for r in rows),
            "cvap_voting_rates_by_year": {str(year): sum(
                r["year"] == year and r["cvap_voted_pct"] is not None for r in rows)
                for year in sorted({r["year"] for r in rows})},
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
