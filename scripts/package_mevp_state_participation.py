"""Package complete permitted facts and all participant-profile queries, not source PDFs."""

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
    primary = module(root / "scripts/mevp_state_participation.py")
    verifier = module(root / "scripts/verify_mevp_state_participation.py")
    proof = verifier.verify(args.inputs, args.results)
    if args.output.exists() or len(args.commit) != 40:
        raise ValueError("Use a fresh output and full scientific source commit")
    inputs = json.loads((args.inputs / "manifest.json").read_bytes())
    members = {"inputs/" + name: (args.inputs / name).read_bytes()
        for name in ["manifest.json", *inputs["files"]]}
    for name in ("scripts/freeze_mevp_participation_facts.py", "scripts/mevp_state_participation.py",
            "scripts/verify_mevp_state_participation.py", "scripts/package_mevp_state_participation.py",
            "scripts/reproduce_mevp_state_participation.py", "tests/test_mevp_state_participation.py"):
        members["code/" + name] = (root / name).read_bytes()
    result = json.loads((args.results / "complete-result.json").read_bytes())
    for name, body in primary.result_files(result).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Complete numerical/query export differs")
        members["results/" + name] = body
    members["checks/independent-verification.json"] = primary.encoded(proof)
    members["README.txt"] = (
        "COMPLETE SOURCE-DEFINED PARTICIPANT HISTORY AND EXPERIENCE PROFILES\n\n"
        "Eleven direct state/group profiles across AZ/CA/FL/MI/TX, five national group profiles;\n"
        "all255 state/DC-by-five-group decisions (244 missing), all51 source-column decisions.\n"
        "All663 newly selected numerical facts are retained, independently checked against\n"
        "already-held originals using pdfplumber/pdfminer coordinates. Earlier national joint\n"
        "calculations, acquisitions and accepted original reductions are not repeated.\n\n"
        "These are percentages of a source frame containing reported early voters AND certain\n"
        "Election Day intenders, not all residents, registered/eligible voters or verified ballots.\n"
        "First-November-general history is not first-ever voting or eligibility. Prior-bin sums\n"
        "are not retention; signed residuals are preserved, not unknown/nonvoter counts.\n"
        "RawN is not weighted population. Do not recover counts by multiplyingN and percentages,\n"
        "pool oversamples, treat groups/states as independent replications, or apply whole-group\n"
        "margins to state columns. NativeQ2 experiences remain multiresponse, not a disjoint sum\n"
        "or derived union. No administrative turnout/absence, designCI, race harmonization,\n"
        "2026 model calibration or local allocation is qualified. Support100 is diagnostic only.\n\n"
        "Includes every permitted sufficient factual cell/method/policy/access decision, ENTIRE\n"
        "accepted predecessor science ZIP, maintained code/tests and full results/queries.\n"
        "Copyrighted originals, source prose, HTML/app code and session headers are not mirrored.\n"
        "The six newly denied UnidosUS routes stay stopped; no alternate-client/cache/mirror\n"
        "recovery is attempted. State values come ONLY from the distinct national originals\n"
        "successfully held on November7, not from blocked new state products or allocated marginals.\n\n"
        "Requires Python3.9+ only; no installation, external commands, source acquisition or PDF\n"
        "parsing. Reproduce: python3 code/scripts/reproduce_mevp_state_participation.py "
        "--package . --output /fresh/path\n"
        "Seven focused tests and independent verification run with network/commands blocked,\n"
        "then every full result/query byte is compared. Optional original-audit source requires\n"
        "private already-held PDFs/text/receipts and pdfplumber; it is not part of reproduction.\n"
    ).encode()
    manifest = dict(contract="participation.complete_mevp_participation.v1",
        source_commit=args.commit, complete_query_download=True,
        originals_redistributed=False, previous_source_reductions_repeated=False,
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
    receipt = dict(status="complete_mevp_participation_packet_prepared",
        members=len(members), source_commit=args.commit,
        archive=primary.pin((args.output / "complete-analysis.zip").read_bytes()),
        summary=result["summary"], independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
