"""Reproduce the published overall county percentages from North Carolina's 2006 report."""

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader


SOURCE = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2006_11_07/voter_turnout_data_20061107.pdf"
PATTERN = re.compile(r"County\s*:\s*([A-Z .]+?)\s+((?:100|[0-9]{1,2})%)\s")


def county_rates(body, roster, expected_sha256):
    source_sha = hashlib.sha256(body).hexdigest()
    if source_sha != expected_sha256:
        raise ValueError("North Carolina PDF checksum differs")
    notes = PdfReader(io.BytesIO(body))
    if len(notes.pages) != 12:
        raise ValueError("North Carolina PDF page inventory differs")
    expected = {r["name"].upper(): r["fips"] for r in roster if r["state"] == "NC"}
    if len(expected) != 100 or len(set(expected.values())) != 100 or any(
            not re.fullmatch(r"37[0-9]{3}", fips) for fips in expected.values()):
        raise ValueError("North Carolina requires a complete dated county roster")
    copies = []
    for offset in range(0, 12, 3):
        found = {}
        for page, size in enumerate((35, 35, 30), offset):
            text = notes.pages[page].extract_text(extraction_mode="layout")
            if not all(token in text for token in ("2006 General Election", "Turnout %", "Total Voters")):
                raise ValueError(f"North Carolina PDF page {page + 1} has different headings")
            rows = [PATTERN.match(line) for line in text.splitlines() if line.startswith("County")]
            if len(rows) != size or any(row is None for row in rows):
                raise ValueError(f"North Carolina PDF page {page + 1} has unrecognized rows")
            for row in rows:
                name, rate = row.groups()
                if name in found:
                    raise ValueError(f"Duplicate North Carolina county: {name}")
                found[name] = (rate, page + 1)
        if found.keys() != expected.keys():
            raise ValueError("North Carolina report and dated county names disagree")
        copies.append(found)
    if any(any(copy[name][0] != rate for name, (rate, _) in copies[0].items()) for copy in copies[1:]):
        raise ValueError("Repeated overall rates in the North Carolina PDF disagree")
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(("election_date", "county_fips", "county", "published_turnout_pct", "measure",
                     "denominator_basis", "source_page", "source_url", "source_sha256"))
    for name in sorted(expected, key=expected.get):
        rate, page = copies[0][name]
        writer.writerow(("2006-11-07", expected[name], name, rate[:-1], "published_overall_turnout",
                         "not_specified_in_report", page, SOURCE, source_sha))
    return out.getvalue().encode()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pdf", type=Path)
    cli.add_argument("roster", type=Path)
    cli.add_argument("sha256")
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    result = county_rates(args.pdf.read_bytes(), json.loads(args.roster.read_bytes()), args.sha256)
    with args.output.open("xb") as target:
        target.write(result)
