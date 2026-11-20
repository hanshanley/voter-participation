"""Published Census CPS Table 4b/4c rows, not estimates from respondent records."""

import argparse
import base64
import csv
import io
import json
import math
import re
import zipfile
from pathlib import Path

from scripts.nationwide import STATES
from scripts.participation_intake.contract import IntakeError, encoded, pin

INPUT = "cps-published-state-workbooks.zip"
INPUT_PATH = "data/results-intake/" + INPUT
CSV = "participation-cps-published-state-tables.csv"
INDEX_URL = "https://www.census.gov/topics/public-sector/voting/data/tables.html"
CURRENT_YEAR = 2026
CURRENT_FEED = "US-cps-2026-published-state-tables"
CURRENT_CONTRACT = "participation.cps_published_state_table_pair.v1"
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


def parse_workbook(body, year, table, url=None):
    from openpyxl import load_workbook

    if not 0 < len(body) <= 1_000_000:
        raise ValueError("CPS workbook exceeds the reviewed size bound")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 10_000_000:
            raise ValueError("CPS workbook exceeds the reviewed unpacked size bound")
    url = url or source_url(year, table)
    checksum = pin(body)["sha256"]
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
    clauses = (f"Table {table}.", "Reported Voting and Registration", required)
    if (not isinstance(title, str) or not title.strip().endswith(f"November {year}")
            or not all(clause in title for clause in clauses)):
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
                       "source_url": url, "source_sha256": checksum})
    if seen != {(code, group) for code in {*STATES, "US"} for group in expected_groups}:
        raise ValueError("Incomplete CPS state/age/sex/race roster")
    return output


def reconcile(frames, year):
    def totals(table):
        return {r["state_code"]: tuple((r[field], r["source_markers"].get(field)) for field in FIELDS)
                for r in frames[table] if r["group"] == "Total"}
    if totals("4b") != totals("4c"):
        raise ValueError(f"CPS 4b and 4c totals differ for {year}")
    return frames["4b"] + frames["4c"]


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
    return [row for year in sorted(PUBLICATIONS)
            for row in reconcile({t: frames[year, t] for t in ("4b", "4c")}, year)]


def release_link(index, year):
    from scripts.results_turnout_history import archive_link

    pattern = (r"https://www\.census\.gov/data/tables/time-series/demo/voting-and-registration/"
               r"p20-\d{3,4}\.html")
    label = (rf"(?:Table\s+)?Voting and Registration in the Election of November {year}"
             r"(?:\s+.*)?")
    return archive_link(index, INDEX_URL, pattern, label=label)


def table_links(page, release_url, year):
    from scripts.results_turnout_history import archive_link

    if f"Voting and Registration in the Election of November {year}".encode() not in page:
        raise ValueError("CPS release page does not identify the election")
    root = r"https://www2\.census\.gov/programs-surveys/cps/tables/p20/\d{3,4}/"
    links = {}
    for table in ("4b", "4c"):
        dimension = "Age" if table == "4c" else "Sex, Race and Hispanic Origin"
        pattern = root + rf"(?:vote0?{table}_{year}|table0?{table})\.xlsx"
        label = (rf"Reported Voting and Registration(?: of the Total Voting-Age Population)?,?"
                 rf" by {dimension},? for States: November {year}")
        links[table] = archive_link(page, release_url, pattern, label=label)
    if not all(links.values()):
        raise IntakeError("report_not_linked", "Census release does not yet link both state tables")
    if len({url.rsplit("/", 1)[0] for url in links.values()}) != 1:
        raise ValueError("CPS workbooks link to different publication directories")
    return links


def original(url, body):
    return {"url": url, **pin(body), "base64": base64.b64encode(body).decode("ascii")}


def original_body(item, url):
    if item["url"] != url or len(item["base64"]) > 1_400_000:
        raise ValueError("CPS original source identity or size differs")
    body = base64.b64decode(item["base64"], validate=True)
    if pin(body) != {key: item[key] for key in ("bytes", "sha256")}:
        raise ValueError("CPS original checksum differs")
    return body


def current_rows(entry):
    data = entry.get("data")
    if data is None:
        return []
    if (entry["status"] not in ("reported", "retained_after_failure")
            or data["contract"] != CURRENT_CONTRACT or data["year"] != CURRENT_YEAR
            or data["participation_observation_qualified"] is not False):
        raise ValueError("Unreviewed CPS source or turnout measure")
    index = original_body(data["index"], INDEX_URL)
    if entry["source"] != {"url": INDEX_URL, **pin(index)}:
        raise ValueError("CPS index does not match the collected observation")
    release_url = release_link(index, CURRENT_YEAR)
    if release_url is None:
        raise ValueError("CPS release is not linked by the official index")
    page = original_body(data["release"], release_url)
    urls = table_links(page, release_url, CURRENT_YEAR)
    if set(data["workbooks"]) != set(urls):
        raise ValueError("Incomplete collected CPS workbook pair")
    frames = {table: parse_workbook(original_body(data["workbooks"][table], url), CURRENT_YEAR, table, url)
              for table, url in urls.items()}
    return reconcile(frames, CURRENT_YEAR)


def collect_current(collector):
    def capture(url):
        body, _ = collector.acquire(url)
        if not 0 < len(body) <= 1_000_000:
            raise ValueError("CPS source file exceeds the reviewed size bound")
        return body

    def parse(index):
        if not 0 < len(index) <= 1_000_000:
            raise ValueError("CPS index exceeds the reviewed size bound")
        release_url = release_link(index, CURRENT_YEAR)
        if release_url is None:
            raise IntakeError("report_not_linked", "Census voting tables index has no November 2026 release")
        page = capture(release_url)
        urls = table_links(page, release_url, CURRENT_YEAR)
        data = {"contract": CURRENT_CONTRACT, "year": CURRENT_YEAR,
                "participation_observation_qualified": False,
                "index": original(INDEX_URL, index), "release": original(release_url, page),
                "workbooks": {table: original(url, capture(url)) for table, url in urls.items()}}
        current_rows({"status": "reported", "source": {"url": INDEX_URL, **pin(index)}, "data": data})
        return data

    def same_release(previous, current):
        return (previous.get("contract") == current["contract"]
                and previous["release"]["url"] == current["release"]["url"]
                and previous["workbooks"] == current["workbooks"])

    return collector.capture(CURRENT_FEED, INDEX_URL, parse, equivalent=same_release)


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
