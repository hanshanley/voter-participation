"""Package sufficient complete baseline inputs, native facts, code and every output."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from build_jefferson_wi_datasets import encoded, pin

CODE = ("review_jefferson_wi_participation.py", "build_jefferson_wi_datasets.py",
        "reproduce_jefferson_wi.py", "package_jefferson_wi.py", "verify_jefferson_wi_datasets.mjs")
METHODS = """# Jefferson County, Wisconsin: native participation snapshot

This packet supplies one additional county observation and all 32 literal native
ward-group observations, not statewide Wisconsin completion or new precinct polygons.
The native Ballots Cast total is 38,414 and Registered Voters total is 52,428.
Both independently printed totals reconcile to every reporting-unit row.
The 0-ballot/0-registration row is an observed zero, not a 0/0 turnout rate.
Noncontiguous and combined ward labels remain intact.

The source clock is 11-06-2026 01:13 pm; no timezone is supplied. The Official
Results heading coexists with unofficial-until-canvass and single-machine reporting
disclaimers. No certification, final/all-machine or complete ballot-mode status is
inferred. County fractions use a conditional same-report registration snapshot;
registrations have no separately established reference date. Unit fractions stay
withheld; native printed percentages remain literal metadata.

55055 is the contextual Census county identity, not a native supplied FIPS code.
The full accepted 72-county 2026 Census reference is unchanged. County mapping is
contextual, not a certification of election-day precinct geography. Old Rock County
records, all other states, early/mail modes and native geometry are unchanged.
Native county and count datasets must be activated together in one catalog commit.

All sufficient complete accepted runtime inputs and every new runtime/query output
are included, not metadata-only links. The predecessor's full scientific archive
remains immutable separately; its source-native acquisition/reductions are not rerun
by this incremental transformation. Denied Brown, Milwaukee and Dane sources are
holds, not numerical inputs: safe receipts are included, private challenge bodies
are not redistributed or recovered through alternate clients/caches/mirrors.

Offline reproduction (standard library only):

    python3 -S code/reproduce_jefferson_wi.py --root . --output /new/replay/path

Optional exact frontend contract verification with Node:

    node code/verify_jefferson_wi_datasets.mjs --datasets datasets --old-counts inputs/counts --old-native inputs/native --reader code/frontend --reference inputs/county-reference.json.gz --proof /new/proof.json

The replay reproduces complete original query values and both full compiled datasets.
Output dataset descriptors intentionally precede complete-download qualification;
the activated catalog separately pins the anonymously verified immutable ZIP itself.
No private respondents, demographic predictions or voter records are included.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("evidence", "datasets", "accepted-counts", "accepted-native", "reader", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete packet directory")
    bodies = {}
    for family, root in (("counts", args.accepted_counts), ("native", args.accepted_native)):
        descriptor = json.loads((root/"dataset.json").read_bytes())
        bodies[f"inputs/{family}/dataset.json"] = (root/"dataset.json").read_bytes()
        for name, metadata in descriptor["files"].items():
            body = (root/name).read_bytes()
            if pin(body) != metadata:
                raise ValueError("Changed complete accepted runtime input")
            bodies[f"inputs/{family}/"+name] = body
    for name in ("jefferson.html", "jefferson.html.safe-receipt.json", "brown.pdf.safe-receipt.json",
                 "milwaukee.html.safe-receipt.json", "dane.html.safe-receipt.json", "manifest.json"):
        bodies["inputs/originals/"+name] = (args.evidence/"originals"/name).read_bytes()
    bodies["inputs/county-reference.json.gz"] = (args.evidence/"accepted-county-reference.json.gz").read_bytes()
    bodies["inputs/accepted-catalog.json"] = (args.evidence/"accepted-catalog.json").read_bytes()
    for name in CODE:
        bodies["code/"+name] = (Path(__file__).parent/name).read_bytes()
    bodies["code/test_jefferson_wi_participation.py"] = (
        Path(__file__).parent.parent/"tests/test_jefferson_wi_participation.py").read_bytes()
    for name in ("participation-counts.js", "participation-native-bindings.js", "participation-dataset.js"):
        bodies["code/frontend/"+name] = (args.reader/name).read_bytes()
    bodies["code/frontend/package.json"] = encoded(dict(type="module"))
    outputs = {}
    for path in sorted(args.datasets.rglob("*")):
        if path.is_file():
            outputs["datasets/"+str(path.relative_to(args.datasets))] = path.read_bytes()
    for path in sorted((args.evidence/"results").iterdir()):
        if path.is_file():
            outputs["query/"+path.name] = path.read_bytes()
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
    archive = stream.getvalue()
    (args.output/"complete-analysis.zip").write_bytes(archive)
    for name in ("reporting-unit-participation.csv", "complete-native-query.json", "county-participation.json"):
        (args.output/name).write_bytes((args.evidence/"results"/name).read_bytes())
    (args.output/"reporting-unit-participation.json.gz").write_bytes(
        (args.datasets/"reporting-unit-participation.json.gz").read_bytes())
    result = dict(status="complete_sufficient_input_output_packet", **pin(archive), members=len(bodies),
        complete_runtime_outputs=len(outputs), complete_baseline_runtime_inputs=True,
        metadata_only=False, private_denial_bodies_or_respondents_included=False)
    (args.output/"package-proof.json").write_bytes(encoded(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
