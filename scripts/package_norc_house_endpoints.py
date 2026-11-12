"""Package all permitted native inputs and the complete endpoint-only NORC successor."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input-directory", "results", "output", "native-verifier", "footnotes"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh scientific package")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from scripts import norc_house_model as model, verify_norc_house_model as independent
    from scripts.reproduce_norc_house_endpoints import load_inputs, verify_reuse
    priors, previous, held = load_inputs(args.input_directory)
    result = json.loads((args.results / "complete-result.json").read_bytes())
    endpoints = json.loads((args.input_directory / "inputs/complete-endpoint-decisions.json").read_bytes())
    proof = independent.verify(result, priors)
    reuse = verify_reuse(result, previous, endpoints)
    members = {"frozen-inputs.json": (args.input_directory / "frozen-inputs.json").read_bytes(),
        "checks/independent-verification.json": model.encoded(proof),
        "checks/unchanged-state-reuse.json": model.encoded(reuse),
        "checks/source-no-ballot-footnotes.json": args.footnotes.read_bytes(),
        "code/scripts/verify_house_clerk_native.py": args.native_verifier.read_bytes()}
    for name in json.loads(members["frozen-inputs.json"]):
        members["inputs/"+name] = (args.input_directory / "inputs" / name).read_bytes()
    for name in ("scripts/norc_house_model.py", "scripts/house_clerk_endpoints.py",
                 "scripts/norc_house_endpoint_successor.py", "scripts/verify_norc_house_model.py",
                 "scripts/fit_norc_house_model.py", "scripts/package_norc_house_endpoints.py",
                 "scripts/reproduce_norc_house_endpoints.py",
                 "tests/test_norc_house_model.py", "tests/test_house_clerk_endpoints.py"):
        members["code/"+name] = (root / name).read_bytes()
    for name, body in model.result_files(result).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed complete query: "+name)
        members["results/"+name] = body
    members["README.txt"] = (
        "OFFICIAL HOUSE ENDPOINT SUCCESSOR TO THE LEARNED NORC MODEL\n\n"
        "No NORC refit. The entire accepted predecessor, including fitted synthetic\n"
        "priors, validation and source ancestry, remains included byte-for-byte.\n"
        "Current House controls remain the frozen Nov 7 2026 source snapshot;\n"
        "these are not new Nov 12 counts, certified final totals or ballots.\n\n"
        "The complete House Clerk 2024 PDF is included: all 50 states/435 districts,\n"
        "1279 candidate-party lines and 68 excluded accounting rows. Independent\n"
        "pypdf checks match 1347 lines/1345 numeric cells/two footnote-only counts\n"
        "in 8082 checks. Blank, overvote, continuing and exhausted accounting are\n"
        "not candidate votes. Explicit same-nominee fusion lines are combined;\n"
        "no caucus/coalition reassignment. FL-20/OK-03 structural (1) counts stay\n"
        "NULL, never zero; source notes explain unopposed names not on the ballot.\n\n"
        "47 qualified same-office comparisons; AK remains held for nonpartisan\n"
        "classification, ME for unresolved ranked-choice round compatibility,\n"
        "PA for missing current candidate controls. Every state decision, native\n"
        "line, count and exclusion is included. 21 previously anchored baselines\n"
        "change; 12 comparisons are newly anchored. Only 33 changed-state cases\n"
        "are recalculated. All other 17 states' numerics and full seeds are reused.\n"
        "432 assumption cases, 250 state seeds, 1500 demographic partition seeds.\n"
        "47-state preconditioning margin MAE is 6.21027852pp, not a component.\n\n"
        "Switching + entry/return + exit + Other + unresolved exactly reconciles\n"
        "each conditional modeled margin change. Net participation=entry+exit.\n"
        "Each demographic dimension separately partitions its state. Source\n"
        "response prediction is not independently validated completed voting.\n"
        "No individual histories, first-ever voting, eligibility/death/migration\n"
        "or local allocations are identified. Sensitivity is not confidence.\n\n"
        "Full permitted inputs, every query/result, code/tests and original PDF\n"
        "are included. No raw survey respondents, IDs, private fine source cells\n"
        "or compiled landing-page HTML. Private source fits require originals.\n"
        "Public simulation reproduction is standard-library-only; Python3.9 is\n"
        "the exact-byte reference. It blocks network/external commands, reuses\n"
        "unchanged states, and recomputes only changed endpoint cases:\n"
        "python3 -Werror code/scripts/reproduce_norc_house_endpoints.py "
        "--package . --output /fresh/path\n\n"
        "Optional native-source re-extraction requires PyMuPDF; independent PDF\n"
        "verification requires pypdf6.16.0, separate from the public simulations:\n"
        "python3 code/scripts/verify_house_clerk_native.py --root inputs "
        "--extraction inputs/native-house-facts.json --all-states "
        "--output /fresh/native-proof.json\n"
    ).encode()
    manifest = dict(contract="participation.complete_norc_house_endpoint_successor.v1",
        source_commit=args.commit, complete_query_download=True, reference_python="3.9",
        raw_private_inputs_redistributed=False, source_models_refitted=False,
        files={name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
               for name, body in sorted(members.items())})
    members["manifest.json"] = model.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name, body in members.items():
        if name.startswith(("results/", "checks/")) or name == "manifest.json":
            (args.output / Path(name).name).write_bytes(body)
    body = (args.output / "complete-analysis.zip").read_bytes()
    receipt = dict(status="complete_NORC_House_endpoint_successor_package",
        source_commit=args.commit, archive_bytes=len(body),
        archive_sha256=hashlib.sha256(body).hexdigest(), members=len(members),
        summary=result["summary"], independent=proof, reuse=reuse,
        private_raw_respondents_exported=False, source_models_refitted=False)
    (args.output / "package-receipt.json").write_bytes(model.encoded(receipt))
    print(json.dumps(receipt))
