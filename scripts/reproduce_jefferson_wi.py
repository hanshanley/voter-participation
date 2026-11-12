"""Reproduce the complete new factual query and datasets from held inputs offline."""

import argparse
import html
import json
from pathlib import Path
import re

from build_jefferson_wi_datasets import build, encoded, pin
from review_jefferson_wi_participation import outputs


def verify_native(body, query):
    text = body.decode("utf-8-sig")
    tables = re.findall(r"<table\b[^>]*>(.*?)</table\s*>", text, re.S | re.I)
    candidates = []
    for table in tables:
        rows = [[html.unescape(re.sub(r"<[^>]*>", "", cell)).strip()
                 for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", row, re.S | re.I)]
                for row in re.findall(r"<tr\b[^>]*>(.*?)</tr\s*>", table, re.S | re.I)]
        if rows and rows[0] == ["", "Registered Voters", "Ballots Cast", "Ballots Cast %"]:
            candidates.append(rows[1:])
    if len(candidates) != 1:
        raise ValueError("Independent literal table is not unique")
    rows = candidates[0]
    actual = [[r["reporting_unit"], str(r["registered"]), str(r["ballots"]), r["native_printed_percent"]]
              for r in query["reporting_units"]]
    normalized = [[row[0], row[1].replace(",", ""), row[2].replace(",", ""), row[3]] for row in rows]
    if normalized != actual or len(rows) != 32:
        raise ValueError("Independent complete native rows differ")
    if (sum(int(row[1].replace(",", "")) for row in rows) != 52428
            or sum(int(row[2].replace(",", "")) for row in rows) != 38414
            or sum(row[1:3] == ["0", "0"] for row in normalized) != 1):
        raise ValueError("Independent county totals or genuine zero differ")
    if not any(row[0] == "Town of Aztalan (W1,3)" for row in rows):
        raise ValueError("Literal noncontiguous ward group missing")
    return 32 * 4 + 4


def reproduce(root, output):
    if output.exists():
        raise ValueError("Use a fresh replay directory")
    source = (root/"inputs/originals/jefferson.html").read_bytes()
    facts = outputs(source)
    query = json.loads(facts["complete-native-query.json"])
    checks = verify_native(source, query)
    changes, flat = build(query, root/"inputs/counts", root/"inputs/native",
                          (root/"inputs/county-reference.json.gz").read_bytes())
    generated = {"query/"+name: body for name, body in facts.items()}
    for family in ("counts", "native"):
        previous = json.loads((root/f"inputs/{family}/dataset.json").read_bytes())
        bodies = {name: (root/f"inputs/{family}"/name).read_bytes() for name in previous["files"]}
        for name, body in bodies.items():
            if pin(body) != previous["files"][name]:
                raise ValueError("Changed accepted baseline input")
            checks += 1
        bodies.update(changes[family])
        files = {name: pin(body) for name, body in bodies.items()}
        previous.update(files=files, index=dict(file="index.json", **files["index.json"]),
            version=pin(encoded(dict(files=files, contract=previous["record_contract"])))["sha256"],
            complete_download=None)
        bodies["dataset.json"] = encoded(previous)
        generated.update({f"datasets/{family}/"+name: body for name, body in bodies.items()})
    generated["datasets/reporting-unit-participation.json.gz"] = flat
    expected = json.loads((root/"output-checksums.json").read_bytes())
    if set(expected) != set(generated):
        raise ValueError("Complete output inventory differs")
    for name, body in generated.items():
        if pin(body) != expected[name] or body != (root/name).read_bytes():
            raise ValueError("Replayed full output differs: "+name)
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        checks += 1
    result = dict(status="pass", outputs=len(generated), checks=checks,
        complete_literal_native_rows=32, ballots=38414, registered=52428,
        original_grouping_and_zero_preserved=True, network_or_source_acquisition_required=False)
    (output/"reproduction.json").write_bytes(encoded(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.root, args.output)))


if __name__ == "__main__":
    main()
