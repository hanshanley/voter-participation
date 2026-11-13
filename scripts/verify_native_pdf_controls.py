"""Verify pinned printed official county/total controls against full factual queries."""

import argparse
import io
import json
from pathlib import Path
import re
import sys

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded, pin

SOURCES = (
    ("wy-statewide-candidates", 130447,
     "2f65cdfd310ccefe5e3e17454bcf237c623906b06a244e72ee5e61c6028c55e8",
     "United States Representative", "wy-state-house",
     ("R", "D", "L", "C", "write_ins", "overvotes", "undervotes")),
    ("wy-ballots", 105379,
     "9c55c8e18d1b7a83c3819fa7672b559bc9544e7eddec9b33acb9f1c2c013dc11",
     "Statewide Total Ballots Cast", "wy-state-ballots", ("ballots",)),
)


def verify(queries, source_root):
    results = []
    for name, size, digest, title, query_id, fields in SOURCES:
        body = (source_root / name).read_bytes()
        if pin(body) != dict(bytes=size, sha256=digest):
            raise ValueError("Changed pinned printed original")
        pages = [page.extract_text(extraction_mode="layout")
            for page in PdfReader(io.BytesIO(body)).pages]
        selected = [(number + 1, text) for number, text in enumerate(pages) if title in text]
        if len(selected) != 1 or "November 3, 2026" not in selected[0][1]:
            raise ValueError("Printed contest/year selection is ambiguous")
        number, text = selected[0]
        count = 0
        for row in queries[query_id]["rows"]:
            matches = [line for line in text.splitlines() if re.match(
                r"^\s*" + re.escape(row["county"]) + r"\s{2,}", line)]
            if len(matches) != 1:
                raise ValueError("Missing or repeated printed parent")
            suffix = re.sub(r"^\s*" + re.escape(row["county"]) + r"\s+", "", matches[0])
            tokens = suffix.split()
            if len(tokens) != len(fields) or any(
                    not re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", token) for token in tokens):
                raise ValueError("Printed count layout changed")
            if [int(token.replace(",", "")) for token in tokens] != [row[field] for field in fields]:
                raise ValueError("Printed controls disagree with factual query")
            count += len(fields)
        results.append(dict(source=name, source_pin=pin(body), printed_page=number,
            control_rows=len(queries[query_id]["rows"]), independently_checked_counts=count))
    return dict(status="passed", reports=results, source_count_repairs=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh printed-control verification output")
    result = verify(json.loads(args.queries.read_bytes())["queries"], args.sources)
    args.output.write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
