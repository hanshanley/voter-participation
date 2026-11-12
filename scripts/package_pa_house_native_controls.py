"""Package complete accepted inputs and the PA-only native-control scope correction."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input-directory", "results", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh scientific package")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from scripts import norc_house_model as model
    from scripts.reproduce_pa_house_native_controls import analyze
    result = json.loads((args.results / "complete-result.json").read_bytes())
    result, endpoints, proof, reuse, scope = analyze(args.input_directory, result)
    members = {"frozen-inputs.json": (args.input_directory / "frozen-inputs.json").read_bytes()}
    for name in json.loads(members["frozen-inputs.json"]):
        members["inputs/"+name] = (args.input_directory / "inputs" / name).read_bytes()
    for name, value in {"independent-verification.json": proof, "unchanged-state-reuse.json": reuse,
            "native-control-SQL-verification.json": scope,
            "complete-endpoint-decisions.json": endpoints}.items():
        members["checks/"+name] = model.encoded(value)
    names = ("scripts/house_native_controls.py", "scripts/house_clerk_endpoints.py",
        "scripts/norc_house_endpoint_successor.py", "scripts/norc_house_model.py",
        "scripts/verify_norc_house_model.py", "scripts/reproduce_norc_house_endpoints.py",
        "scripts/reproduce_pa_house_native_controls.py", "scripts/package_pa_house_native_controls.py",
        "tests/test_house_native_controls.py")
    for name in names:
        members["code/"+name] = (root / name).read_bytes()
    for path in (root / "data/pa-house-native-controls/20261112-01/inputs").iterdir():
        members["code/data/pa-house-native-controls/20261112-01/inputs/"+path.name] = path.read_bytes()
    for name, body in model.result_files(result).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed complete result: "+name)
        members["results/"+name] = body
    members["README.txt"] = (
        "PENNSYLVANIA NATIVE HOUSE CONTROL SCOPE CORRECTION\n\n"
        "No new counts or NORC refit. The complete accepted 47-comparison science\n"
        "is preserved byte-for-byte, with every earlier sufficient input/result.\n"
        "Reuses the complete accepted 1400-row/435-district/50-state candidate CSV\n"
        "and its full source audit, not a new acquisition or old parse campaign.\n\n"
        "Pennsylvania has 17 native districts and 34 reported native candidates.\n"
        "The 18 blank control rows were unmatched county-validation entries from\n"
        "a union table, not absent native district votes. Every native candidate\n"
        "matches its held reported control exactly without alias normalization.\n"
        "All 18 exceptions remain unchanged and downloadable. No county sum,\n"
        "candidate alias, partial-state promotion or missing-as-zero repair.\n\n"
        "Provider state/district totals remain separate from official county\n"
        "fragments. The provider omits known county-source write-ins; those are\n"
        "NOT added to Other. Reported candidate votes are not all Other ballots,\n"
        "certified final totals, turnout or administratively confirmed absence.\n"
        "Native source URLs and all 17 district clocks remain explicit. All\n"
        "current counts remain the frozen Nov 7 2026 source snapshot.\n\n"
        "48 qualified comparisons; AK nonpartisan and ME ranked-choice round\n"
        "holds remain. Only PA is recalculated; 49 states' numerical fields and\n"
        "complete assumption/seed cases are reused. All 438 assumption cases,\n"
        "250 state seeds, 1500 demographic partition seeds, 1600 group decisions,\n"
        "every flow and all eight complete output files are included.\n"
        "The 48-state before-conditioning margin MAE is 6.12699827pp: a changed\n"
        "comparison set, not evidence that the source fits improved. Error stays\n"
        "separate from behavioral contributions. Conditional reconstruction is\n"
        "not independent voter-history or administrative outcome validation.\n\n"
        "Six demographic dimensions separately partition a state, not each\n"
        "other. Entry is not proven first-ever voting; modeled N is not observed\n"
        "staying home. Eligibility/death/migration remain unidentified. No state\n"
        "model is allocated to counties/precincts; no new CI or fine source cells.\n\n"
        "Full permitted native inputs, complete predecessor, source/tests,\n"
        "SQL/native-scope checks and every query/result are included. No raw\n"
        "survey respondents, IDs, private fine cells, acquisition session headers\n"
        "or compiled publisher app code. Public simulations use the standard\n"
        "library; Python3.9 is the byte-reference toolchain. Reproduction blocks\n"
        "network/external commands and recomputes only PA:\n"
        "python3 -Werror code/scripts/reproduce_pa_house_native_controls.py "
        "--package . --output /fresh/path\n"
    ).encode()
    manifest = dict(contract="participation.complete_PA_native_house_scope_successor.v1",
        source_commit=args.commit, complete_query_download=True,
        reference_python="3.9", source_models_refitted=False, native_source_counts_changed=False,
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
    receipt = dict(status="complete_PA_native_House_scope_successor",
        source_commit=args.commit, archive_bytes=len(body),
        archive_sha256=hashlib.sha256(body).hexdigest(), members=len(members),
        summary=result["summary"], independent=proof, native_SQL=scope, reuse=reuse,
        private_raw_respondents_exported=False, source_models_refitted=False,
        native_source_counts_changed=False)
    (args.output / "package-receipt.json").write_bytes(model.encoded(receipt))
    print(json.dumps(receipt))
