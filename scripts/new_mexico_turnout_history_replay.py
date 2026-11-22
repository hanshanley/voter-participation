"""Reproduce the complete New Mexico historical turnout table offline."""

import argparse
import csv
import hashlib
import html
import io
import json
from pathlib import Path

from scripts import new_mexico_turnout_history as history


def build(entries, originals=None):
    if not entries or not entries.keys() <= history.FEEDS.keys() or any(
            not entry.get("data") for entry in entries.values()):
        raise ValueError("Incomplete or unrecognized New Mexico archive")
    if originals:
        for feed, source, suffix, limit, valid_url, parse, retained in history.original_reports(entries):
            with (originals / (feed + suffix)).open("rb") as stream:
                body = stream.read(limit + 1)
            if (not valid_url or len(body) != source["bytes"]
                    or hashlib.sha256(body).hexdigest() != source["sha256"] or parse(body) != retained):
                raise ValueError("Changed source original: " + feed)

    rows = list(history.exports(entries))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    def cells(row):
        rate = row["source_eligible_rate_pct"]
        place = row["county"] or "Statewide"
        if row["unit"]:
            place += " / " + row["unit"]
        values = [f'{row["source_reported_count"]:,}', f'{row["source_eligible_voters"]:,}',
                  f"{rate:.2f}%" if rate is not None else "Withheld",
                  row["rate_hold"].replace("_", " ")]
        return (f'<tr><th scope="row">{html.escape(place)}</th>'
                + "".join(f"<td>{html.escape(value)}</td>" for value in values) + "</tr>")

    def table(group):
        return ('<div class="table" tabindex="0" role="region" aria-label="Turnout counts"><table>'
                '<thead><tr><th scope="col">Reporting area</th><th scope="col">Ballots Cast</th>'
                '<th scope="col">Eligible Voters</th><th scope="col">Rate</th><th scope="col">Hold</th></tr></thead>'
                '<tbody>' + "".join(cells(row) for row in group) + "</tbody></table></div>")

    sections = []
    for state in (row for row in rows if row["geography_level"] == "state"):
        day = state["election_date"]
        children = [row for row in rows if row["election_date"] == day and row["geography_level"] != "state"]
        sections.append(f'<section><h2>{day}</h2><p><a href="{html.escape(state["source_url"])}">Official report</a>'
                        f' · {html.escape(state["source_clock"])}</p>{table([state])}'
                        f'<details><summary>All {len(children):,} county and reporting-unit rows</summary>'
                        f'{table(children)}</details></section>')
    document = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>New Mexico historical turnout</title>
<style>body{font:1rem/1.5 system-ui,sans-serif;max-width:60rem;margin:auto;padding:1rem;color:#1a1a1a}
.table{overflow:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:.35rem;border-bottom:1px solid #ccc}
td:nth-child(-n+4),thead th:nth-child(n+2):nth-child(-n+4){text-align:right}summary{cursor:pointer}</style>
<main><h1>New Mexico historical turnout</h1>
<p>Official general-election reports. Rates use the report's own Eligible Voters denominator, not VAP or VEP.
Unusable denominators remain in the table with the rate withheld. Reporting-unit locations are not inferred.</p>
<p><a href="participation-nm-historical-native-turnout.csv">Download all source rows and decisions (CSV)</a></p>
""" + "".join(sections) + "</main></html>\n"
    return {history.CSV: stream.getvalue().encode(), "new-mexico-turnout-history.html": document.encode()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--originals", type=Path)
    args = parser.parse_args()
    entries = json.loads((args.inputs / "source-facts.json").read_bytes())
    files = build(entries, args.originals)
    args.output.mkdir()
    for name, body in files.items():
        (args.output / name).write_bytes(body)
