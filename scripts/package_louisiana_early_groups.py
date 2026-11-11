"""Package the entire new official aggregate source and every complete query."""

import argparse
import importlib.util
import json
from pathlib import Path
import zipfile


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "results", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    primary = module(root / "scripts/louisiana_early_groups.py")
    verifier = module(root / "scripts/verify_louisiana_early_groups.py")
    proof = verifier.verify(args.inputs, args.results)
    if args.output.exists() or len(args.commit) != 40:
        raise ValueError("Use a fresh output and complete source commit")
    inputs = json.loads((args.inputs / "manifest.json").read_bytes())
    members = {"inputs/" + name: (args.inputs / name).read_bytes() for name in ("manifest.json", *inputs["files"])}
    for name in ("scripts/freeze_louisiana_early_groups.py", "scripts/louisiana_early_groups.py",
            "scripts/verify_louisiana_early_groups.py", "scripts/package_louisiana_early_groups.py",
            "scripts/reproduce_louisiana_early_groups.py", "tests/test_louisiana_early_groups.py"):
        members["code/" + name] = (root / name).read_bytes()
    result = json.loads((args.results / "complete-result.json").read_bytes())
    for name, body in primary.result_files(result).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed complete numerical/query export")
        members["results/" + name] = body
    members["checks/independent-verification.json"] = primary.encoded(proof)
    members["README.txt"] = (
        "COMPLETE LOUISIANA SOURCE-DEFINED EARLY/ABSENTEE GROUP COMPOSITIONS\n\n"
        "The full157893-byte official two-page PDF, complete cached native text,\n"
        "1040 factual count cells,65 source rows (64parishes plus separate state\n"
        "parent), full independent pypdf coordinate evidence, policy/provenance/\n"
        "access holds, maintained code/tests and EVERY result/query are included.\n"
        "This is a standalone new source family, not a replacement/repackaging of\n"
        "any accepted earlier state controls or science. No HTML/apps/session headers,\n"
        "private voter/survey records, identifiers or private fine cells are included.\n\n"
        "NativeVOTES536190=INPER448588+ABS87602. All16 same-report parish-column sums\n"
        "match their printed state parents. State parent and children are NOT65\n"
        "independent populations or additional votes; never sum both together.\n"
        "Native WHITE/BLACK/OTHER totals are328590/184348/23252. Native MALE224376\n"
        "plus FEMALE311536 leaves278 source-vote accounting units, not an identified\n"
        "unknown-sex/nonvoter class. Preserve all37 parish sex residuals and21 zeros.\n\n"
        "All455 own-source race/sex/INPER-ABS composition rows,260 margin-accounting\n"
        "rows,130 opaque-subset decisions,16 state-parent column controls and all51\n"
        "state/DC coverage decisions (50not supplied by this state source) remain.\n"
        "Percentages use OWN nativeVOTES, not classified-sex totals or registrations.\n"
        "Registration-group turnout, full-election ballots, unique persons, samplingN,\n"
        "confidence intervals, individual stayinghome, eligibility/deaths/migration and\n"
        "race-sex-method joints remain null. Native racial labels are not CPS/SSRS/\n"
        "resident-group aliases. Party fields are registration accounting, not voting\n"
        "behavior; no partisan choice percentages are derived. UOCAVA IN/OUT andASST\n"
        "D/I remain literal; meanings and disjoint/any-person unions are unqualified.\n"
        "ABS is NOT relabelled mail-returned and source parish codes are NOT FIPS.\n\n"
        "Report election11/03/2026, printed query begin1/1/1900/end11/9/2026, printed\n"
        "clock11/10/20263:10:06AM; printed timezone unknown. The PDF creation offset\n"
        "is separate metadata, not a license to fill that clock's timezone. Filter\n"
        "begin1900 is not an observed voting period. No finality/certification claim.\n"
        "Newly denied Michigan PDF403 remains stopped; no alternate-client/cache/\n"
        "mirror or old index/dashboard retry, no snippet numerical substitution.\n\n"
        "Reproduce with Python3.9+ standard library only:\n"
        "python3 -Werror code/scripts/reproduce_louisiana_early_groups.py "
        "--package . --output /fresh/path\n"
        "Seven tests, independent integer verification and every full result/query\n"
        "byte run with network/external commands blocked. No acquisition/PDF extraction\n"
        "or earlier successful reduction is repeated. Optional original-audit refresh\n"
        "uses private already-held source and pypdf6.16.0; it is not required for\n"
        "offline query reproduction. No new UI/data activation or accepted-model refit.\n"
    ).encode()
    manifest = dict(contract="participation.complete_louisiana_early_groups.v1",
        source_commit=args.commit, complete_query_download=True, standalone_new_source=True,
        files={name: primary.pin(body) for name, body in sorted(members.items())})
    members["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name in ("manifest.json", "checks/independent-verification.json",
            *[name for name in members if name.startswith("results/")]):
        (args.output / Path(name).name).write_bytes(members[name])
    receipt = dict(status="complete_louisiana_early_group_packet_prepared",
        source_commit=args.commit, members=len(members),
        archive=primary.pin((args.output / "complete-analysis.zip").read_bytes()),
        summary=result["summary"], independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
