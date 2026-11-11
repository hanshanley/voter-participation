"""Package all fitted cells/queries and both entire accepted source science archives."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "returns", "prior-archive", "observed-archive", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from scripts import calibrated_swing as primary
    from scripts import verify_calibrated_swing as independent
    if args.output.exists():
        raise ValueError("Use a fresh output")
    result = json.loads((args.results / "complete-result.json").read_bytes())
    original = json.loads(args.returns.read_bytes())
    proof = independent.verify(result, original)
    members = {
        "inputs/complete-prior-science.zip": args.prior_archive.read_bytes(),
        "inputs/complete-observed-science.zip": args.observed_archive.read_bytes(),
        "inputs/complete-return-comparisons.json": args.returns.read_bytes(),
        "checks/independent-verification.json": primary.encoded(proof),
    }
    for name in ("scripts/calibrated_swing.py", "scripts/verify_calibrated_swing.py",
            "scripts/package_calibrated_swing.py", "scripts/reproduce_calibrated_swing.py",
            "tests/test_calibrated_swing.py"):
        members["code/" + name] = (root / name).read_bytes()
    for name, body in primary.result_files(result).items():
        if (args.results / name).read_bytes() != body:
            raise ValueError("Changed complete result/query")
        members["results/" + name] = body
    members["README.txt"] = (
        "COMPLETE RETURN-CONSTRAINED TRANSITION SCENARIOS\n\n"
        "113state/office decisions;89 compatible reported comparisons;24unavailable.\n"
        "All801fitted scenarios,12816synthetic transition cells,678endpoint decisions,\n"
        "113selection decisions, all native D/R counts and available Other counts,\n"
        "full viewer/results/code/tests and BOTH ENTIRE previous science archives.\n"
        "No metadata-only download, private respondents or reconstructed source joints.\n\n"
        "This is NEW endpoint calibration, NOT proof of individual voter histories.\n"
        "The old survey-recall baseline is a transition PRIOR, not the observed\n"
        "same-office baseline. Both D/R endpoint counts constrain nonnegative cells.\n"
        "A relative-entropy matrix projection chooses one table, not a unique truth.\n"
        "Four Shapley mechanisms include denominator effects and sum exactly to the\n"
        "observed normalized margin. Independent24ordering verification covers all801.\n"
        "There is no ad-hoc Other/unallocated balancing term.\n\n"
        "Common frame size is ASSUMED from the source prior's current known-party\n"
        "weight, not measured population. Vary it0.8/1/1.25 and prior persistence\n"
        "0.5/1/2 for nine cases. Lower frame bounds are explicit. Original synthetic\n"
        "N/U are pooled only in the prior. No counted candidate vote does NOT\n"
        "establish no ballot, new eligibility, deaths, migration or first-ever voting.\n"
        "Other totals absent from governor frames stay absent in NATIVE inputs;\n"
        "their synthetic split uses the prior and is labeled assumed, not observed0.\n"
        "Reported source snapshots/footprints/competition caveats remain. No state\n"
        "model is allocated to counties/precincts. No confidence/identification interval\n"
        "or independent behavioral validation is claimed. Old estimates are archived.\n\n"
        "Reproduce NEW fits without network/external commands or old source refits:\n"
        "python3 -Werror code/scripts/reproduce_calibrated_swing.py --package . "
        "--output /fresh/path\n"
        "Reference byte-identical toolchain Python3.9; later Python versions may differ\n"
        "in floating summation/serialization. The model and independent endpoint/\n"
        "permutation verifier use only the standard library.\n"
    ).encode()
    manifest = dict(contract="participation.complete_return_constrained_scenarios.v1",
        source_commit=args.commit, complete_query_download=True, reference_python="3.9",
        files={name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            for name, body in sorted(members.items())})
    members["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name, body in members.items():
        if name.startswith(("results/", "checks/")) or name == "manifest.json":
            (args.output / Path(name).name).write_bytes(body)
    body = (args.output / "complete-analysis.zip").read_bytes()
    receipt = dict(status="complete_return_constrained_package", source_commit=args.commit,
        archive=dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()),
        members=len(members), summary=result["summary"], independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt))
