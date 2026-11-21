"""Reproduce the 2022 Alaska ballot-count archive and accessible reporting table."""

import argparse
from collections import Counter
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

from scripts import alaska_precinct_history as ak, bulk_participation_archives as bulk
from scripts.automatic_runtime import offline, relative
from scripts.participation_intake.contract import pin
from scripts.supported_analytical_release import csv_bytes


TABLE = "alaska-2022-reporting-table.html"


def report(rows):
    modes = Counter()
    table = []
    for row in rows:
        label = row["reporting_unit"]
        ballots = row["reported_ballots"]
        mode = ("Election Day precinct" if row["source_unit_id"] else
                "Federal overseas" if label == ak.OVERSEAS else label.split(" - ", 1)[1])
        modes[mode] += ballots
        table.append(f'<tr><th scope="row">{html.escape(label)}</th><td>{html.escape(mode)}</td><td>{ballots:,}</td></tr>')
    total = sum(modes.values())
    mode_rows = "".join(
        f'<li><span>{html.escape(mode)}</span> <meter max="{total}" value="{count}" aria-hidden="true"></meter> {count:,}</li>'
        for mode, count in sorted(modes.items(), key=lambda item: (-item[1], item[0])))
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alaska 2022 midterm ballot counts</title>
<style>
body{{font:1rem/1.5 system-ui,sans-serif;color:#142c39;margin:auto;padding:1.2rem;max-width:54rem}}
h1{{font-size:clamp(1.6rem,4vw,2.4rem);line-height:1.2}}
ul{{padding:0;list-style:none}}li{{display:flex;align-items:center;gap:.45rem;margin:.5rem 0}}
li span{{flex:1}}meter{{width:35%;accent-color:#22719e}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
caption{{text-align:left;font-weight:bold}}th,td{{border-bottom:1px solid #ccd7db;padding:.25rem;text-align:left}}
td:last-child,thead th:last-child{{text-align:right}}
</style><main><h1>Alaska 2022 midterm ballot counts</h1>
<p>November 8, 2022 &middot; {total:,} ballots across {len(rows):,} reporting units.</p>
<h2>Ballots by reporting method</h2><ul>{mode_rows}</ul>
<p>Central and overseas ballots are not assigned to a home precinct. This is a count table, not a map or an
all-mode precinct turnout rate. The statewide control reports {rows[0]['official_state_registration_control']:,}
registrations. <a href="{ak.MIDTERM_REPORT}">Official statewide ballot control</a>.</p>
<table><caption>Official ballots by reporting unit</caption>
<thead><tr><th scope="col">Reporting unit</th><th scope="col">Method</th><th scope="col">Ballots</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></main></html>
"""


def outputs(entries, inventory, originals=None):
    if bulk.original_inventory(entries) != inventory:
        raise ValueError("Alaska original inventory differs")
    if originals:
        for name, _, _, _, _, parse, expected in bulk.original_reports(entries):
            receipt = inventory[name]
            body = (originals / Path(urlsplit(receipt["url"]).path).name).read_bytes()
            if pin(body) != {key: receipt[key] for key in ("bytes", "sha256")} or parse(body) != expected:
                raise ValueError("Alaska original differs: " + name)
    rows = list(ak.midterm_exports(entries))
    if not rows:
        raise ValueError("Missing complete Alaska midterm query")
    return {ak.MIDTERM_CSV: csv_bytes(rows), TABLE: report(rows).encode("utf-8")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--originals", type=Path)
    args = parser.parse_args()
    pins = json.loads((args.package / "checksums.json").read_bytes())
    for name, expected in pins.items():
        if pin((args.package / relative(name)).read_bytes()) != expected:
            raise ValueError("Changed Alaska archive member: " + name)
    facts = json.loads((args.package / "inputs/accepted-facts.json").read_bytes())
    inventory = json.loads((args.package / "inputs/originals-inventory.json").read_bytes())
    with offline() as requests:
        rebuilt = outputs(facts, inventory, args.originals)
    if requests or {f"outputs/{name}": pin(body) for name, body in rebuilt.items()} != {
            name: expected for name, expected in pins.items() if name.startswith("outputs/")}:
        raise ValueError("Alaska archive replay differs")
    args.output.mkdir()
    for name, body in rebuilt.items():
        (args.output / name).write_bytes(body)
    print(json.dumps({"complete_outputs": len(rebuilt), "network_requests": 0,
                      "originals_verified": len(inventory) if args.originals else 0}))


if __name__ == "__main__":
    main()
