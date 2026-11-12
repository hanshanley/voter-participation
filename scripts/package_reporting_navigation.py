"""Package all sufficient runtime inputs, source matches, code, tests and outputs."""

import argparse
import io
import json
from pathlib import Path
import zipfile

from harris_county_successor import encoded, pin

CODE = ("harris_county_successor.py", "connect_reporting_navigation.py",
        "reproduce_reporting_navigation.py", "package_reporting_navigation.py",
        "verify_reporting_navigation.mjs")
METHODS = """# Held reporting rows: county-navigation repair

This packet connects 4,963 existing source reporting rows to 113 existing county
parents: Arkansas 2,768 / 75; Arizona 1,763 / 15; Wyoming 432 / 23. These are
already-held/deployed native-table observations, not newly acquired election data.
They were omitted from the canonical county-navigation frames and carried
incompatible native-label parent keys and incomplete selector metadata.

All native counts, identities, source fields, denominators, reporting statuses,
clocks, unknowns and source disagreements remain unchanged. The 83 unknown counts
remain unknown and 22 genuine zeros remain zero. Literal same-state county labels
must uniquely identify existing parents; only case/whitespace and the literal
County suffix are normalized. No fuzzy spelling, ordinal/FIPS invention or
allocation is used. Parent assignment is navigation identity, not a polygon join.
No new rates, precinct polygons, state totals or source acquisitions are created.
The source-native snapshots are not upgraded to final/certified or unique-person
counts, and source-specific missingness/reporting limits remain in each record.

Every old canonical record, all native tables/bindings/geometries, all other
48 state shards, and both separate early/mail frames are unchanged. Existing
four eligible contexts receive the held rows; no all-election row enters early
or mail mode. Imported rows gain only compatible county-parent/selector/source-
review/download metadata. The complete CSV and JSON match queries include every
source row and native count status, not merely an inventory or examples.

All sufficient complete accepted count/native runtimes and every compiled output
are included with maintained source/tests and the actual frontend reader. Original
source-native reductions are not repeated. The complete original source packets
remain at their retained immutable row-source links; this is a full sufficient-
input incremental transformation. No private voters/respondents, fine cells,
raw acquisition session headers or compiled publisher app code are included.

Standard-library offline replay:

    python3 -S code/reproduce_reporting_navigation.py --root . --output /new/replay

Exact optional Node reader test:

    node code/verify_reporting_navigation.mjs --datasets datasets --baseline inputs --reader code/frontend --proof /new/proof.json

The compiled dataset descriptor predates complete-download qualification. The
activated catalog separately pins the complete anonymously verified immutable ZIP.
Native tables and county binding inventories are unchanged, so the count entry
alone is compatible with the existing native entry; no binding update is needed.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("baseline", "datasets", "evidence", "reader", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh packet directory")
    bodies = {}
    for family in ("counts", "native"):
        root = args.baseline/family
        descriptor = json.loads((root/"dataset.json").read_bytes())
        bodies[f"inputs/{family}/dataset.json"] = (root/"dataset.json").read_bytes()
        for name, metadata in descriptor["files"].items():
            body = (root/name).read_bytes()
            if pin(body) != metadata:
                raise ValueError("Changed complete accepted runtime input")
            bodies[f"inputs/{family}/"+name] = body
    for name in CODE:
        bodies["code/"+name] = (Path(__file__).parent/name).read_bytes()
    bodies["code/test_connect_reporting_navigation.py"] = (
        Path(__file__).parent.parent/"tests/test_connect_reporting_navigation.py").read_bytes()
    for name in ("participation-counts.js", "participation-native-bindings.js",
                 "participation-dataset.js", "participation-explorer.js"):
        bodies["code/frontend/"+name] = (args.reader/name).read_bytes()
    bodies["code/frontend/package.json"] = encoded(dict(type="module"))
    for name in ("frontend-contract-proof.json", "local-renderer-fixture-proof.json", "local-map-pointer-proof.json"):
        bodies["verification/"+name] = (args.evidence/name).read_bytes()
    outputs = {"datasets/"+str(path.relative_to(args.datasets)): path.read_bytes()
               for path in sorted(args.datasets.rglob("*")) if path.is_file()}
    bodies.update(outputs)
    bodies["output-checksums.json"] = encoded({name: pin(body) for name, body in outputs.items()})
    bodies["METHODS.md"] = METHODS.encode()
    bodies["checksums.json"] = encoded({name: pin(body) for name, body in bodies.items()})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(bodies.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
    args.output.mkdir(parents=True)
    body = stream.getvalue()
    (args.output/"complete-analysis.zip").write_bytes(body)
    for name in ("complete-navigation-query.csv", "complete-navigation-query.json", "summary.json"):
        (args.output/name).write_bytes((args.datasets/name).read_bytes())
    proof = dict(status="complete_sufficient_input_output_packet", **pin(body),
        members=len(bodies), outputs=len(outputs), complete_baseline_runtime_inputs=True,
        reporting_rows=4963, county_parents=113, metadata_only=False)
    (args.output/"package-proof.json").write_bytes(encoded(proof))
    print(json.dumps(proof))
