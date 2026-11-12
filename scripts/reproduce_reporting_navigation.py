"""Reproduce the full held-row adapter from complete sufficient inputs offline."""

import argparse
import json
from pathlib import Path

from connect_reporting_navigation import compile_datasets
from harris_county_successor import encoded, pin


def reproduce(root, output):
    if output.exists():
        raise ValueError("Use a fresh replay directory")
    for name, metadata in json.loads((root/"checksums.json").read_bytes()).items():
        if pin((root/name).read_bytes()) != metadata:
            raise ValueError("Changed archived member: "+name)
    summary = compile_datasets(root/"inputs", output/"datasets")
    actual = {str(path.relative_to(output)): pin(path.read_bytes())
              for path in output.rglob("*") if path.is_file()}
    if actual != json.loads((root/"output-checksums.json").read_bytes()):
        raise ValueError("Full replay output inventory or bytes differ")
    for name in actual:
        if (root/name).read_bytes() != (output/name).read_bytes():
            raise ValueError("Full replay bytes differ: "+name)
    result = dict(status="pass", outputs=len(actual), reporting_rows=summary["reporting_rows"],
        county_parents=summary["county_parents"], network_or_source_acquisition_required=False)
    (output/"reproduction.json").write_bytes(encoded(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.root, args.output)))
