"""Package all permitted native inputs, complete predecessor and every new query."""

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
    primary = module(root / "scripts/cps_1998_state_points.py")
    verifier = module(root / "scripts/verify_cps_1998_state_points.py")
    proof = verifier.verify(args.inputs, args.results)
    if args.output.exists() or len(args.commit) != 40:
        raise ValueError("Use a fresh output and complete source commit")
    native = json.loads((args.inputs / "manifest.json").read_bytes())
    members = {"inputs/" + name: (args.inputs / name).read_bytes()
        for name in ("manifest.json", *native["files"])}
    for name in ("scripts/cps_1998_state_points.py", "scripts/verify_cps_1998_state_points.py",
            "scripts/package_cps_1998_state_points.py", "scripts/reproduce_cps_1998_state_points.py",
            "tests/test_cps_1998_state_points.py"):
        members["code/" + name] = (root / name).read_bytes()
    result = json.loads((args.results / "complete-result.json").read_bytes())
    for name, body in primary.result_files(result).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed complete numerical/query export")
        members["results/" + name] = body
    members["checks/independent-verification.json"] = primary.encoded(proof)
    members["README.txt"] = (
        "COMPLETE 1998 NATIVE STATE DEMOGRAPHIC PARTICIPATION POINTS\n\n"
        "468 source rows / 4680 literal metric cells across all51states/DC plusUS,\n"
        "nine native groups and1404 metric decisions. 1060 reported points selected;\n"
        "343(B) measures and one invalid900. citizenship percentage remain withheld.\n"
        "NewMexico's printed0.8. standard error stays literal and uninterpreted.\n"
        "1059 printed source SEs are retained, including ten literal zeros. No newCIs.\n"
        "32 literal dot counts are not converted to zero;14 actual zero counts survive.\n\n"
        "Native counts are rounded thousands, NOT sampleN or exact persons. Registered\n"
        "and voted percentages use the source adult18+ population, NOT citizens.\n"
        "Citizenship percentage is a population share, not participation or eligibility.\n"
        "No suppressed measure is recovered from counts. Source defects are not repaired.\n"
        "Native groups overlap; N-H means Non-Hispanic, API includes Asian/PacificIslander,\n"
        "and Hispanic may be any race. Neither a modern race alias nor a group partition.\n\n"
        "All936 1998-to-2002 group/metric decisions (675 compatible source-label snapshots,\n"
        "104 non-HispanicAPI/allAPI holds plus native source holds); all104 original vs\n"
        "retrospective decisions (102 match, twoUS absences), and208 2018/2022 same-VAP\n"
        "overall decisions (204 descriptive comparisons/fourUS absences) are included.\n"
        "These are repeated source snapshots, NOT harmonized definitions, cohorts,\n"
        "individual retention, observed staying home or significant changes. 1998 SEs\n"
        "are not applied to2002 confidence scalars or converted to change intervals.\n\n"
        "The new Census native directory and separately declared TXT were acquired once;\n"
        "the denied HTML landing page remains stopped. No alternate client/cache/mirror\n"
        "recovered that page. Full TXT plus all permitted policy/provenance, ENTIRE accepted\n"
        "1241697-byte 2002 science ZIP (including original XLS/PDFs and older science),\n"
        "maintained code/tests and EVERY complete result/query are included. No publisher\n"
        "HTML/app code, session headers, private respondent identifiers or survey fine cells.\n\n"
        "Python3.9+ standard library only. Reproduce in a fresh extracted packet:\n"
        "python3 -Werror code/scripts/reproduce_cps_1998_state_points.py --package . "
        "--output /fresh/path\n"
        "Seven tests, all independent checks and every result/query byte run with network\n"
        "and external commands blocked. Earlier source acquisitions/reductions are not rerun.\n"
        "No new frontend activation, model refit, population validation or local allocation.\n"
    ).encode()
    manifest = dict(contract="participation.complete_cps_1998_state_points.v1",
        source_commit=args.commit, complete_query_download=True,
        accepted_original_acquisitions_or_reductions_repeated=False,
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
    receipt = dict(status="complete_cps_1998_state_points_packet_prepared",
        source_commit=args.commit, members=len(members),
        archive=primary.pin((args.output / "complete-analysis.zip").read_bytes()),
        summary=result["summary"], independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
