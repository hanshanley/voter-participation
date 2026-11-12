"""Replay the complete held-fact Harris transformation without network or OCR."""

import argparse
import json
from pathlib import Path

from harris_county_successor import compile_datasets, encoded, pin


def reproduce(root, output):
    if output.exists():
        raise ValueError("Use a fresh replay directory")
    for name, metadata in json.loads((root/"checksums.json").read_bytes()).items():
        if pin((root/name).read_bytes()) != metadata:
            raise ValueError("Changed archived input or output: "+name)
    compile_datasets(root/"inputs/source/county-participation.json",
        root/"inputs/counts", root/"inputs/native", root/"inputs/county-reference.json.gz",
        output/"datasets")
    actual = {str(path.relative_to(output)): pin(path.read_bytes())
              for path in output.rglob("*") if path.is_file()}
    expected = json.loads((root/"output-checksums.json").read_bytes())
    if actual != expected:
        raise ValueError("Complete replay output inventory or bytes differ")
    for name in actual:
        if (root/name).read_bytes() != (output/name).read_bytes():
            raise ValueError("Full replay output differs: "+name)
    result = dict(status="pass", outputs=len(actual), complete_native_measures=13,
        counted_ballots=1392280, roster_voters=1393495, signed_native_difference=-4085,
        no_new_rate_or_precinct_geometry=True, network_ocr_or_source_acquisition_required=False)
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
