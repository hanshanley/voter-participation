"""Reconcile literal Jefferson WI county/ward-group ballot statistics."""

import argparse
import csv
from decimal import Decimal
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re

URL = "https://apps.jeffersoncountywi.gov/jc/election/results/11032026"


class TableReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell, self.text = [], None, None, None, []

    def handle_starttag(self, tag, attributes):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, value):
        self.text.append(value)
        if self.cell is not None:
            self.cell.append(value)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse(body):
    reader = TableReader()
    reader.feed(body.decode("utf-8-sig"))
    text = " ".join(" ".join(reader.text).split())
    if "Jefferson County WI" not in text or "Fall General Election" not in text:
        raise ValueError("Wrong native county or election")
    total = re.search(r"REGISTERED VOTERS TOTAL ([\d,]+) BALLOTS CAST TOTAL ([\d,]+) "
                      r"Precincts Reporting (\d+) of (\d+) for (\d+)%", text)
    clock = re.search(r"AS OF (\d{2}-\d{2}-2026 \d{2}:\d{2} [ap]m)", text)
    if not total or not clock or "Number of votes reflect Jefferson County only" not in text:
        raise ValueError("Missing complete native statistical totals, clock or county scope")
    header = ["", "Registered Voters", "Ballots Cast", "Ballots Cast %"]
    tables = [t for t in reader.tables if t and t[0] == header]
    if len(tables) != 1:
        raise ValueError("Ambiguous native participation table")
    units = []
    for row in tables[0][1:]:
        if len(row) != 4 or not all(re.fullmatch(r"[\d,]+", x) for x in row[1:3]):
            raise ValueError("Unreported or malformed native row; never substitute zero")
        name, registered, ballots, percent = row
        registered, ballots = int(registered.replace(",", "")), int(ballots.replace(",", ""))
        if not re.fullmatch(r"\d+(?:\.\d+)?%", percent):
            raise ValueError("Missing literal registered percentage")
        if registered and abs(Decimal(percent[:-1])-Decimal(100)*ballots/registered) > Decimal(".011"):
            raise ValueError("Native percentage disagrees with literal counts")
        units.append(dict(reporting_unit=name, registered=registered, ballots=ballots,
                          native_printed_percent=percent,
                          zero_denominator=registered == 0,
                          unit_key="WI55055-"+hashlib.sha256(name.encode()).hexdigest()[:16]))
    registered, ballots, reported, expected, pct = [int(x.replace(",", "")) for x in total.groups()]
    if (len(units) != expected or len({r["reporting_unit"] for r in units}) != len(units)
            or sum(r["registered"] for r in units) != registered
            or sum(r["ballots"] for r in units) != ballots):
        raise ValueError("Entire native inventory and county totals do not reconcile")
    return dict(contract="participation.jefferson_wi_native.v1", year=2026, election_date="2026-11-03",
        state_code="WI", county="Jefferson County", county_reference_fips="55055", native_fips=None,
        source_url=URL, source_sha256=hashlib.sha256(body).hexdigest(),
        source_update_label=clock.group(1), source_update_timezone=None,
        native_header_official_results="Official Results" in text,
        native_unofficial_until_canvass_disclaimer="Results are unofficial until after the County Canvass is complete" in text,
        native_machine_completeness_disclaimer="may be only of one machine" in text,
        certification_verified=False, complete_all_machine_or_ballot_mode_counting_proved=False,
        ballots=ballots, registered=registered, reported_units=reported, total_units=expected,
        native_reporting_percent=pct, reporting_unit_rows=len(units),
        zero_count_units=sum(r["ballots"] == 0 for r in units), precinct_geometry_approved=False,
        reporting_units=units, unit_names_are_literal_groups_not_split_precincts=True,
        same_report_registration_fraction_percent=float(Decimal(100)*ballots/registered),
        registered_reference_date_established=False, voter_or_eligible_population_claim=False)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def outputs(body):
    result = parse(body)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(result["reporting_units"][0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(result["reporting_units"])
    return {"complete-native-query.json": encoded(result), "reporting-unit-participation.csv": stream.getvalue().encode(),
        "county-participation.json": encoded({key: value for key, value in result.items() if key != "reporting_units"})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete source query")
    args.output.mkdir(parents=True)
    for name, body in outputs(args.source.read_bytes()).items():
        (args.output/name).write_bytes(body)
    result = parse(args.source.read_bytes())
    print(json.dumps({key: result[key] for key in ("ballots", "registered", "reporting_unit_rows", "zero_count_units", "source_update_label")}))


if __name__ == "__main__":
    main()
