"""Freeze a full independent pandas CSV view without inferring numeric values."""

import argparse
import hashlib
import json
from pathlib import Path


def extract(originals, output):
    import pandas

    if output.exists():
        raise ValueError("Do not overwrite a completed extraction")
    tables, sources = {}, {}
    for view in ("County", "Legislative", "Congressional"):
        path = originals / (view + ".csv")
        body = path.read_bytes()
        frame = pandas.read_csv(path, header=None, dtype=str, keep_default_na=False,
                                na_filter=False, skip_blank_lines=False, encoding="utf-8-sig")
        tables[view] = frame.values.tolist()
        if any(not isinstance(value, str) for row in tables[view] for value in row):
            raise ValueError("Independent reader altered a raw CSV cell")
        sources[view] = dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    output.mkdir()
    raw = (json.dumps(tables, indent=2) + "\n").encode()
    (output / "pandas-tables.json").write_bytes(raw)
    receipt = dict(pandas_version=pandas.__version__, sources=sources,
                   raw_whitespace_headers_and_cells_preserved=True,
                   no_numeric_or_missing_to_zero_inference=True,
                   snapshot_bytes=len(raw), snapshot_sha256=hashlib.sha256(raw).hexdigest())
    (output / "extraction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.originals, args.output)
