"""Package all new exact bounds and the entire accepted predecessor, not metadata."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("results", "accepted-science", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from scripts import flow_identification as primary
    from scripts import verify_flow_identification as independent
    if args.output.exists():
        raise ValueError("Use a fresh complete package")
    result = json.loads((args.results / "complete-result.json").read_bytes())
    archive = args.accepted_science.read_bytes()
    if hashlib.sha256(archive).hexdigest() != result["accepted_science_sha256"]:
        raise ValueError("Changed accepted complete predecessor")
    proof = independent.verify(result, primary.read_accepted(args.accepted_science))
    members = {"inputs/complete-return-constrained-science.zip": archive,
        "checks/independent-verification.json": primary.encoded(proof)}
    for name in ("scripts/flow_identification.py", "scripts/verify_flow_identification.py",
            "scripts/package_flow_identification.py", "scripts/reproduce_flow_identification.py",
            "tests/test_flow_identification.py"):
        members["code/"+name] = (root / name).read_bytes()
    for name, body in primary.result_files(result).items():
        if (args.results / name).read_bytes() != body:
            raise ValueError("Changed full query or viewer bytes")
        members["results/"+name] = body
    members["README.txt"] = (
        "COMPLETE CONDITIONAL GROSS-FLOW IDENTIFICATION ANALYSIS\n\n"
        "All113state/office decisions;89comparable,24unavailable. Three already\n"
        "declared accounting frames plus ONE separately labeled large-frame\n"
        "mathematical counterexample per comparable case. No new partisan fit.\n"
        "Every bound is sharp for its specified nonnegative transportation table:\n"
        "all3824extremal primal matrices, exact endpoints, dual cut certificates,\n"
        "all1912bounds and224explicit metric holds are included in full queries.\n"
        "The independent verifier enumerates ALL806912network cuts without\n"
        "importing the production optimizer, using exact Decimal arithmetic.\n\n"
        "Other supplied at both endpoints: DRON. Governor D/R-only: DRX, with X\n"
        "an OPAQUE outside-known-major-party category, not zero Other or no ballot.\n"
        "Separate Other and no-current-contest-vote bounds then remain unavailable.\n"
        "Native zeros, missing baselines and source definitions remain unchanged.\n"
        "D/R retention/switch/outside shares use prior D+R. Entry into D/R uses\n"
        "current D+R and includes possible previous Other choices, not first-ever\n"
        "voting or new eligibility. Individual interval endpoints are NOT jointly\n"
        "attainable categories or additive net-margin contribution bounds.\n\n"
        "Accounting-frame size is assumed, not an independently measured eligible\n"
        "population or people. The large frame is the sum of supplied candidate\n"
        "counts at both endpoints; a feasible disjoint-set construction, not a\n"
        "new fitted estimate. Its single matrix has BOTH zero retention and zero\n"
        "switching while reproducing every native endpoint exactly. All89central\n"
        "frames separately allow zero switching. These are mathematical limits,\n"
        "not observations, confidence intervals, no-ballot histories, migration,\n"
        "causal persuasion, national cohorts or local allocation.\n\n"
        "The FULL14943668-byte accepted predecessor archive is embedded, with its\n"
        "entire earlier science, inputs, code, tests and original assumptions.\n"
        "Only NEW bound outputs are reproduced; no old survey reductions or fits.\n"
        "Python standard library only. Offline reproduction:\n"
        "python3 -Werror code/scripts/reproduce_flow_identification.py "
        "--package . --output /fresh/path\n\n"
        "Method reference (not a numerical input or copied implementation):\n"
        "https://developers.google.com/optimization/flow/maxflow?hl=en\n"
        "For selected-edge set E, max selected mass is its bipartite maximum\n"
        "flow. Complete remaining row/column mass on the complement. The minimum\n"
        "equals total mass minus maximum complement flow. The cut certificate\n"
        "minimizes r(not S)+c(neighbors(S)) over all subsets S of row vertices.\n"
        "A feasible full witness plus matching cut proves each extremum exact.\n"
    ).encode()
    manifest = dict(contract="participation.complete_gross_flow_identification.v1",
        source_commit=args.commit, complete_query_download=True,
        files={name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            for name, body in sorted(members.items())})
    members["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED) as package:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            package.writestr(info, body)
    for name, body in members.items():
        if name.startswith(("results/", "checks/")) or name == "manifest.json":
            (args.output / Path(name).name).write_bytes(body)
    body = (args.output / "complete-analysis.zip").read_bytes()
    receipt = dict(status="complete_conditional_gross_flow_bounds_package", source_commit=args.commit,
        archive=dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()),
        members=len(members), summary=result["summary"], independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt))
