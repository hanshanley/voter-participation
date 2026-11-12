"""Package all 1996 factual originals, complete predecessor, code and full queries."""

import argparse
import importlib.util
import json
from pathlib import Path
import zipfile


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "results", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    primary = module(root / "scripts/cps_1996_state_points.py")
    independent = module(root / "scripts/verify_cps_1996_state_points.py")
    proof = independent.verify(args.inputs, args.results)
    if args.output.exists() or len(args.commit) != 40:
        raise ValueError("Use a fresh destination and complete source commit")
    inputs = json.loads((args.inputs / "manifest.json").read_bytes())
    members = {"inputs/" + name: (args.inputs / name).read_bytes() for name in ("manifest.json", *inputs)}
    for name in ("scripts/cps_1996_state_points.py", "scripts/verify_cps_1996_state_points.py",
                 "scripts/package_cps_1996_state_points.py", "scripts/reproduce_cps_1996_state_points.py",
                 "tests/test_cps_1996_state_points.py"):
        members["code/" + name] = (root / name).read_bytes()
    result = json.loads((args.results / "complete-result.json").read_bytes())
    for name, body in primary.result_files(result).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed complete query/result bytes")
        members["results/" + name] = body
    members["checks/independent-verification.json"] = primary.encoded(proof)
    members["README.txt"] = (
        "COMPLETE 1996 NATIVE STATE DEMOGRAPHIC PARTICIPATION\n\n"
        "1923 native rows / 19539 literal cells across 50 states, DC and US.\n"
        "Race/origin-by-age A:1040 rows; sex-by-age B:780; citizen-gender C:103.\n"
        "All 4576 metric decisions are included:4142 selected source percentages,\n"
        "96 suppressed (B),20 rounded-zero-base holds and318 absent C-cell decisions.\n"
        "The 4142 selections include520 repeated A/B totals and618 C-category rates;\n"
        "they are not4142 independent turnout observations. All2600 repeated total\n"
        "cells match. All1313 literal integer-zero cells survive without reconstruction.\n\n"
        "A/B use ALL ADULTS18+; C uses CITIZEN ADULTS18+. National reported voting\n"
        "is54.2% vs58.4%, respectively. Neither measures administrative turnout or\n"
        "voter eligibility. All native counts are rounded THOUSANDS, NOT sampleN or\n"
        "exact persons. No sampleN, SE or CI is invented. White/Black include Hispanic\n"
        "origin; Hispanic overlaps races. No API or non-Hispanic race alias is created.\n"
        "Joint age/race and age/sex cells remain complete in the download, not allocated\n"
        "to precincts. 51 state citizen-overall and two national citizen-gender cells\n"
        "are not printed; no sex summation fabricates them. DC's wrapped label is read.\n\n"
        "C distinguishes reported no from voting/registration nonresponse. All206\n"
        "rounded-count all-unknown-no/yes allocation scenarios are assumptions, not\n"
        "confidence intervals. All source rounding residuals stay separate; the US\n"
        "voting count residual is1thousand, not assigned to nonvoters or respondents.\n"
        "A/B source nonvote totals are not confirmed individual staying-home counts.\n"
        "All309 cross-frame COUNT references preserve differences without rate mixing.\n\n"
        "All624 native-label1996-to1998 group decisions explicitly compare PRESIDENTIAL\n"
        "with MIDTERM and are descriptive only. All104 same-year original/retrospective\n"
        "reconciliations and728 same-frame PRESIDENTIAL overall decisions to2000,2004,\n"
        "2008,2012,2016,2020,2024 are included, including every hold and US absence.\n"
        "No significance claims, harmonized cohorts, retention or observed staying home.\n\n"
        "Three complete Census TXT originals, acquisition receipts/policy, ENTIRE\n"
        "accepted1998 science (including earlier originals/science), maintained code,\n"
        "eight tests and EVERY complete result/query are included. No publisher HTML,\n"
        "private fine cells, respondent identifiers or session headers. Three new Maine\n"
        "403 routes remain stopped; unknown denied-body lengths/hashes remain null.\n"
        "No Census acquisition, older source reduction or NORC model fit is repeated.\n\n"
        "Python3.9+ standard library only. In a fresh extracted packet:\n"
        "python3 -Werror code/scripts/reproduce_cps_1996_state_points.py --package . "
        "--output /fresh/path\n"
        "This runs eight tests, independent fixed-column/CSV checks and every new\n"
        "query/result byte with network and external commands blocked. No frontend\n"
        "activation, website build, current-count change or48-state House model change.\n"
    ).encode()
    manifest = dict(contract="participation.complete_cps_1996_state_points.v1", source_commit=args.commit,
        complete_query_download=True, older_acquisitions_or_reductions_repeated=False,
        files={name: primary.pin(body) for name, body in sorted(members.items())})
    members["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name in ("manifest.json", "checks/independent-verification.json",
                 *[name for name in members if name.startswith("results/")]):
        (args.output / Path(name).name).write_bytes(members[name])
    receipt = dict(status="complete_1996_native_science_packet_prepared", source_commit=args.commit,
        members=len(members), archive=primary.pin((args.output / "complete-analysis.zip").read_bytes()),
        summary=result["summary"], independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
