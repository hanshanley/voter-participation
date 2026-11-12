"""Archive all sufficient inputs, thirteen source facts, code and complete outputs."""

import argparse
import io
import json
from pathlib import Path
import zipfile

from harris_county_successor import encoded, pin, qualify, SOURCE_SHA

CODE = ("harris_county_successor.py", "reproduce_harris_county.py",
        "package_harris_county.py", "verify_harris_county_datasets.mjs")
METHODS = """# Harris County: preliminary counted ballots

This incremental packet connects one already-held county report, not statewide
Texas completion. I. Total ballots counted (G+H) is 1,392,280 (1,345,094 in person
plus 47,186 mail); C. Total Voters (A+B), from rosters, is separately 1,393,495.
All thirteen factual query rows are supplied, including 5,300 rejected/pending
and the native signed C-F-I discrepancy of -4,085. The separate roster-minus-
counted difference is 1,215. Neither discrepancy is repaired or redistributed.
Possible additions and rejected/pending counts are not added to counted ballots.

The native Preliminary Election Reconciliation - Unofficial Totals report is
dated 11/4/2026, following the 11/3/2026 General and Special Elections. There is
no report time or timezone. HTTP Last-Modified is distinct. No certified/final,
unique-person, fully complete ballot-mode or demographic/history claim follows.
The source's 2,761,770 Registered Voters has undeclared status/cutoff scope;
no new rate is qualified. Original factual inputs retain earlier explicitly
derived diagnostic quotients; these do not become qualified mapped rates.

48201 is contextual Census identity, not a FIPS field printed in the report.
The unchanged full accepted 254-county 2026 Census reference is included; no
new precinct polygon, boundary simplification or allocation is performed.
The default best-available map now prioritizes the native counted snapshot;
all 254 prior early and 254 prior mail county rows remain in their separate
modes, with all old records, other states and native tables unchanged.

Inputs contain the complete previously verified 13-row JSON/CSV query, public
scope qualification, safe receipt, full accepted count/native runtimes and the
exact county reference. This is a complete sufficient-input incremental replay,
not a repeated source-acquisition/OCR campaign or a metadata-only download.
The held original PDF is identified by its exact bytes/hash and remains held;
raw HTTP session headers, private voters and respondents are not redistributed.

Offline replay requires only the Python standard library:

    python3 -S code/reproduce_harris_county.py --root . --output /new/replay

Optional exact frontend contract test with Node:

    node code/verify_harris_county_datasets.mjs --datasets datasets --baseline inputs --reader code/frontend --reference inputs/county-reference.json.gz --proof /new/proof.json

All compiled files and their pre-qualification descriptors are reproduced exactly.
The production catalog separately pins the complete anonymously verified immutable
ZIP. Count and native-binding entries must be activated together in one commit.
Local renderer fixtures are explicitly unpublished compatibility tests only;
actual live acceptance is a separate, no-override operation after activation.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "evidence", "datasets", "baseline", "reader", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh packet directory")
    source = json.loads((args.source/"output/county-participation.json").read_bytes())
    facts = qualify(source)
    native = (args.source/"native-source/harris-2026-general-preliminary-reconciliation.pdf").read_bytes()
    if pin(native) != dict(bytes=29813, sha256=SOURCE_SHA):
        raise ValueError("Changed already-held original")
    bodies = {}
    for family in ("counts", "native"):
        root = args.baseline/family
        descriptor = json.loads((root/"dataset.json").read_bytes())
        bodies[f"inputs/{family}/dataset.json"] = (root/"dataset.json").read_bytes()
        for name, metadata in descriptor["files"].items():
            body = (root/name).read_bytes()
            if pin(body) != metadata:
                raise ValueError("Changed baseline input")
            bodies[f"inputs/{family}/"+name] = body
    for name in ("county-participation.json", "county-participation.csv"):
        bodies["inputs/source/"+name] = (args.source/"output"/name).read_bytes()
    bodies["inputs/source/source-qualification.json"] = (args.source/"source-qualification.json").read_bytes()
    bodies["inputs/source/safe-receipt.json"] = encoded(dict(
        original_url=source["source"]["url"], held_original_verified=pin(native),
        native_report_date=facts["report_date"], report_time=None, timezone=None,
        http_last_modified_distinct=source["source"]["http_last_modified_utc"],
        complete_public_factual_rows=13, incremental_reuse_not_new_acquisition=True,
        contextual_fips_not_native=True, no_raw_http_headers_or_private_records=True))
    bodies["inputs/county-reference.json.gz"] = (args.evidence/"accepted-county-reference.json.gz").read_bytes()
    for name in CODE:
        bodies["code/"+name] = (Path(__file__).parent/name).read_bytes()
    bodies["code/test_harris_county_successor.py"] = (
        Path(__file__).parent.parent/"tests/test_harris_county_successor.py").read_bytes()
    for name in ("participation-counts.js", "participation-native-bindings.js", "participation-dataset.js"):
        bodies["code/frontend/"+name] = (args.reader/name).read_bytes()
    bodies["code/frontend/package.json"] = encoded(dict(type="module"))
    for name in ("frontend-contract-proof.json", "local-renderer-fixture-proof.json"):
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
    for name in ("county-participation.json", "county-participation.csv"):
        (args.output/name).write_bytes((args.source/"output"/name).read_bytes())
    (args.output/"complete-harris-query.json").write_bytes((args.datasets/"complete-harris-query.json").read_bytes())
    proof = dict(status="complete_sufficient_input_output_packet", **pin(body), members=len(bodies),
        complete_runtime_outputs=len(outputs), complete_baseline_runtime_inputs=True,
        complete_native_factual_rows=13, original_hash_verified=True, metadata_only=False,
        raw_http_headers_respondents_or_person_rows=False)
    (args.output/"package-proof.json").write_bytes(encoded(proof))
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
