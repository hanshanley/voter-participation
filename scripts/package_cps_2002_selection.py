"""Package all 2002 CPS source facts, originals, code, tests and complete numerical queries."""

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
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    primary = module(root / "scripts/cps_2002_selection.py")
    verifier = module(root / "scripts/verify_cps_2002_selection.py")
    proof = verifier.verify(args.inputs, args.results)
    if args.output.exists() or len(args.source_commit) != 40:
        raise ValueError("Use a fresh output and the complete published source commit")
    members = {}
    input_manifest = json.loads((args.inputs / "manifest.json").read_bytes())
    for name in ["manifest.json", *input_manifest["files"]]:
        members["inputs/" + name] = (args.inputs / name).read_bytes()
    names = ("scripts/cps_2002_selection.py", "scripts/verify_cps_2002_selection.py",
        "scripts/package_cps_2002_selection.py", "scripts/reproduce_cps_2002_selection.py",
        "tests/test_cps_2002_selection.py")
    for name in names:
        members["code/" + name] = (root / name).read_bytes()
    for name, body in primary.result_files(json.loads((args.results / "complete-result.json").read_bytes())).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Full result/query export differs")
        members["results/" + name] = body
    members["checks/independent-verification.json"] = primary.encoded(proof)
    members["README.txt"] = (
        "COMPLETE REPORTED 2002 CPS POINT-SELECTION SCIENCE\n\n"
        "693 selected native table rows, 642 distinct geography/frame/category cells,\n"
        "including 540 non-total group rows. Duplicate total rows and overlapping groups\n"
        "are not independent or additive. All832rows/8320metric cells and every hold remain.\n"
        "Sex/race/age rates use ALL ADULTS; only the separate overall table uses citizens.\n"
        "Race labels are exact historical source labels, not harmonized modern categories.\n"
        "131 missing/suppressed rows, six defect rows and all3PA conflicting totals are held.\n"
        "The 75,000-person caution uses weighted population, NOT sample size or precision.\n"
        "Native confidence scalars are uninterpreted; no SEs or CIs are calculated.\n"
        "Only the directly printed national citizen interval is retained as a report fact.\n"
        "100 supported 2002-to-2018/2022 midterm citizen-overall snapshot differences,\n"
        "all104 snapshot decisions and832source reconciliation decisions are included.\n"
        "No significance, cohort transition, 2026 estimate, administrative staying home,\n"
        "population validation, repaired count, racial harmonization or local allocation.\n\n"
        "Includes all3original XLS files, both full official PDFs, complete accepted factual\n"
        "and methodological reductions, the ENTIRE accepted historical-frame science ZIP,\n"
        "all new inputs/code/tests/results/queries. No acquisition session headers or HTML apps.\n"
        "Requires only Python3.9+; no dependencies, original parsing, acquisition or installation.\n"
        "Reproduce: python3 code/scripts/reproduce_cps_2002_selection.py --package . --output /fresh/path\n"
        "The reproducer blocks network/external commands, runs10focused tests and the independent\n"
        "verifier, and compares every full result/query byte. No frontend or live data activation.\n"
    ).encode()
    manifest = dict(contract="participation.complete_cps_2002_points.v1",
        source_commit=args.source_commit, complete_query_download=True,
        accepted_original_reductions_repeated=False, original_html_or_session_headers_included=False,
        files={name: primary.pin(body) for name, body in sorted(members.items())})
    members["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name in ("manifest.json", "checks/independent-verification.json",
            *[key for key in members if key.startswith("results/")]):
        (args.output / Path(name).name).write_bytes(members[name])
    receipt = dict(status="complete_cps_2002_point_selection_packet",
        source_commit=args.source_commit, members=len(members),
        archive=primary.pin((args.output / "complete-analysis.zip").read_bytes()),
        summary=json.loads((args.results / "summary.json").read_bytes()), independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
