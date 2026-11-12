"""Package every permitted sufficient input, source query, hold and House diagnostic."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from house_panel_public import json_bytes, replay


SCRIPTS = ("house_panel_validation.py", "verify_house_panel_validation.py", "house_panel_public.py",
           "reproduce_house_panel_validation.py", "package_house_panel_validation.py")
TESTS = ("test_house_panel_validation.py", "test_house_panel_public.py")


def digest(body):
    return hashlib.sha256(body).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("private-results", "policy", "verification", "coding-dir", "output", "dataset"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.dataset.exists():
        raise ValueError("Use fresh scientific and dataset directories")
    source = Path(__file__).resolve().parents[1]
    policy = json.loads(args.policy.read_bytes())
    verification = json.loads(args.verification.read_bytes())
    if (verification["status"] != "pass" or verification["policy_sha256"] != digest(args.policy.read_bytes()) or
            verification["reviewer_sha256"] != digest((source / "scripts/house_panel_validation.py").read_bytes()) or
            policy["tests_sha256"] != digest((source / "tests/test_house_panel_validation.py").read_bytes())):
        raise ValueError("Missing or stale native scientific acceptance")
    candidate = json.loads((args.private_results / "public-candidate.json").read_bytes())
    for name, expected in verification["private_result_sha256"].items():
        if digest((args.private_results / name).read_bytes()) != expected:
            raise ValueError("Native verification preimage changed")
    sufficient = dict(contract="participation.house_panel_coarse_sufficient_input.v1",
        decisions=[{key: value for key, value in row.items() if key != "statistics"}
                   for row in candidate["decisions"]])
    outputs = replay(sufficient)
    if outputs["source-concordance.json"] != (args.private_results / "public-candidate.json").read_bytes():
        raise ValueError("Coarse public replay differs from verified native extraction")
    members = {
        "inputs/policy.json": args.policy.read_bytes(),
        "inputs/sufficient-coarse-inputs.json": json_bytes(sufficient)
    }
    members.update({"outputs/" + name: body for name, body in outputs.items()})
    for name, key in (("choice-bridge-03.json", "bridge_sha256"),
                      ("participation-qualification-02.json", "history_qualification_sha256")):
        body = (args.coding_dir / name).read_bytes()
        if digest(body) != policy[key]:
            raise ValueError("Changed source coding qualification record")
        members["inputs/" + name] = body
    for name in SCRIPTS:
        members["code/scripts/" + name] = (source / "scripts" / name).read_bytes()
    for name in TESTS:
        members["code/tests/" + name] = (source / "tests" / name).read_bytes()
    members["records/independent-native-verification.json"] = args.verification.read_bytes()
    members["README.txt"] = (
        "Conditional same-office House source concordance, 2022 to 2024\n\n"
        "This full packet contains all permitted sufficient inputs, all 319 public query\n"
        "decisions (2 available tables and 317 whole-table holds), 8 coarse source cells,\n"
        "five complete numerical outputs, exact source/code/test pins and native checks.\n"
        "No raw respondents, identifiers, native fine cells or trained models are included.\n"
        "The two coding records are code/citation evidence only: inherited native-release\n"
        "and population-validation holds are not overridden by including those records.\n\n"
        "CES: retained 2020-adult panel, 2022 and 2024 post-election House reports;\n"
        "positive administrative participation histories at both waves, known D/R choices,\n"
        "positive commonpostweight_24. Choices require conditional shared-item code transport,\n"
        "not panel-native numeric labels. Missing/contradictory histories remain separate.\n"
        "AP: positive POLLCLOSE_STATE_WEIGHT, modeled current voter, known actual recalled\n"
        "House22/current House24 source responses. Recalled22 codes1R/2D are reversed;\n"
        "QVOTE2022S is forbidden. This is not the final-vote weight frame of the fitted bridge.\n"
        "Pooled state-weight cases are not a national population-weighted estimate.\n"
        "Different recruitment, retention, recall, answer timing, state and administrative\n"
        "frames prevent interpreting differences as recall bias or population/model error.\n"
        "Each source rate is conditional on both choices being D/R, not all prior voters.\n"
        "This does not validate entry, staying home, first-ever voting, 2026 state behavior\n"
        "or precinct allocations, change the accepted three models, or provide design CIs.\n\n"
        "Standard-library-only offline public numerical replay (no private extraction):\n"
        "python -S -W error code/scripts/reproduce_house_panel_validation.py "
        "--archive COMPLETE_ZIP --output NEW_DIRECTORY\n"
        "Native extraction can be audited separately with the pinned original sources,\n"
        "the two exact coding records and code/scripts/house_panel_validation.py --help.\n"
        "Private-source arithmetic was independently checked with SQL and exact fractions.\n"
        "Source code commit: " + args.source_commit + "\n"
    ).encode()
    manifest = dict(contract="participation.house_panel_complete_packet.v1", source_code_commit=args.source_commit,
        output_files=sorted(outputs),
        files={name: dict(bytes=len(body), sha256=digest(body)) for name, body in sorted(members.items())},
        original_native_sources_included=False, only_permitted_coarse_sufficient_inputs=True)
    members["manifest.json"] = json_bytes(manifest)
    args.output.mkdir(parents=True)
    args.dataset.mkdir(parents=True)
    archive_path = args.output / "complete-analysis.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
            if not name.startswith("code/"):
                path = args.dataset / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
    assets = {name: body for name, body in outputs.items()}
    assets.update({"policy.json": members["inputs/policy.json"],
                  "sufficient-coarse-inputs.json": members["inputs/sufficient-coarse-inputs.json"],
                  "manifest.json": members["manifest.json"],
                  "independent-native-verification.json": args.verification.read_bytes(),
                  "README.txt": members["README.txt"]})
    for name, body in assets.items():
        (args.output / name).write_bytes(body)
    all_files = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
                 for p in sorted(args.output.iterdir()) if p.is_file()}
    (args.output / "SHA256SUMS.txt").write_text(
        "".join(f"{metadata['sha256']}  {name}\n" for name, metadata in all_files.items()))
    print(json.dumps(dict(status="full_public_scientific_packet_created", members=len(members),
                          zip_bytes=archive_path.stat().st_size, zip_sha256=digest(archive_path.read_bytes()),
                          complete_outputs=len(outputs), source_code_commit=args.source_commit)))


if __name__ == "__main__":
    main()
