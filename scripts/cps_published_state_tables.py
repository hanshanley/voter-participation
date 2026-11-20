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
EXPECTED = {(year, table) for year in PUBLICATIONS for table in ("4b", "4c")}
SEX = ("Male", "Female")
RACE = ("White alone", "White non-Hispanic alone", "Black alone", "Asian alone",
        "Hispanic (any race)", "White alone or in combination", "Black alone or in combination",
        "Asian alone or in combination")
AGES = ("18 to 24", "25 to 34", "35 to 44", "45 to 64", "65+")
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
    return f"{year}-table{table}.xlsx"


def source_url(year, table):
    base = f"https://www2.census.gov/programs-surveys/cps/tables/p20/{PUBLICATIONS[year]}/"
    return base + (f"table0{table}.xlsx" if year < 2022 else f"vote0{table}_{year}.xlsx")


def parse_workbook(body, year, table):
    from openpyxl import load_workbook

    book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        if len(book.sheetnames) != 1:
            raise ValueError("CPS workbook has an unexpected sheet inventory")
        sheet = book.active
        rows = list(sheet.iter_rows(max_col=14, values_only=True))
    finally:
        book.close()
    title = rows[1][0]
    required = "by Age" if table == "4c" else "by Sex, Race and Hispanic Origin"
    clauses = (f"Table {table}.", "Reported Voting and Registration", required, f"November {year}")
    if not isinstance(title, str) or not all(clause in title for clause in clauses):
        raise ValueError("CPS table, dimension, or election year differs")
    if "in thousands" not in rows[2][0].lower():
        raise ValueError("CPS count units differ")
    upper = next(i for i, row in enumerate(rows[:5]) if row[0] in ("STATE", "Characteristics"))
    normalize = lambda value: " ".join((value or "").lower().split())
    if tuple(map(normalize, rows[upper][2:5])) != ("total population", "total citizen population", "registered"):
        raise ValueError("CPS population columns differ")
    header = tuple("moe" if normalize(v) in ("margin of error 1", "margin of error1",
                                            "margin of error (+/-)1") else normalize(v)
                   for v in rows[upper + 1][4:])
    if header != COMMON_HEADER or not any(row[0] == CONFIDENCE for row in rows):
        raise ValueError("CPS measure or published uncertainty columns differ")
    codes = {name.upper(): code for code, name in STATES.items()} | {"US": "US", "UNITED STATES": "US"}
    expected_groups = ("Total", *(AGES if table == "4c" else (*SEX, *RACE)))
    output, seen = [], set()
    state = None
    for row_number, row in enumerate(rows[upper + 2:], upper + 3):
        place, native_group, *cells = row
        if native_group is None and all(value is None for value in cells):
            continue
        if place:
            state = codes.get(place)
        group = LABEL_ALIASES.get(native_group, native_group)
        if state is None or group not in expected_groups or (state, group) in seen:
            raise ValueError(f"Unknown or duplicate CPS geographic/group identity at row {row_number}")
        seen.add((state, group))
        markers, values = {}, {}
        for field, cell in zip(FIELDS, cells, strict=True):
            if cell in ("B", "-"):
                markers[field] = cell
                cell = None
            elif (type(cell) not in (int, float) or not math.isfinite(cell) or cell < 0
                  or (not field.endswith("_thousands") and cell > 100)
                  or (field.endswith("_thousands") and type(cell) is not int)):
                raise ValueError(f"Invalid CPS field {field} at row {row_number}")
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
                       "source_table": table, "source_sheet": sheet.title, "source_row": row_number,
                       "source_url": source_url(year, table), "source_sha256": pin(body)["sha256"]})
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
    for year in PUBLICATIONS:
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
