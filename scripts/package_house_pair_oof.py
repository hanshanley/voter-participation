"""Package all permitted paired-source inputs, models, queries, negative results and replay."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from house_pair_public import replay


SCRIPTS = ("house_pair_oof.py", "house_pair_public.py", "adopt_house_pair_cache.py",
           "verify_house_pair_oof.py", "reproduce_house_pair_oof.py", "package_house_pair_oof.py",
           "house_panel_validation.py")
TESTS = ("test_house_pair_oof.py", "test_house_pair_public.py")


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("experiment", "private", "reference", "predecessor", "output", "dataset"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.dataset.exists():
        raise ValueError("Use fresh scientific packet and dataset paths")
    root = Path(__file__).resolve().parents[1]
    experiment = args.experiment
    policy = json.loads((experiment/"policy-score02.json").read_bytes())
    verification = json.loads((experiment/"independent-native-verification.json").read_bytes())
    sufficient_body = (args.private/"public-sufficient-candidate.json").read_bytes()
    sufficient = json.loads(sufficient_body)
    if (verification["status"] != "pass" or verification["cached_component_fits_verified"] != 180 or
            verification["sufficient_sha256"] != pin(sufficient_body)["sha256"] or
            verification["policy_sha256"] != pin((experiment/"policy-score02.json").read_bytes())["sha256"] or
            verification["verifier_sha256"] != pin((root/"scripts/verify_house_pair_oof.py").read_bytes())["sha256"] or
            policy["fitter_sha256"] != pin((root/"scripts/house_pair_oof.py").read_bytes())["sha256"] or
            policy["tests_sha256"] != pin((root/"tests/test_house_pair_oof.py").read_bytes())["sha256"] or
            policy["reference_sha256"] != pin(args.reference.read_bytes())["sha256"]):
        raise ValueError("Changed source/design/numerical acceptance preimage")
    if pin(args.predecessor.read_bytes())["sha256"] != "25d0dfe7a6b7332dd6f26620b36b96f277e57e8f319f38bc70b83757d9c3e2d3":
        raise ValueError("Accepted full predecessor differs")
    outputs = replay(sufficient, json.loads(args.reference.read_bytes()))
    for name, body in outputs.items():
        if body != (experiment/"results"/name).read_bytes():
            raise ValueError("Current complete public output differs")
    members = {
        "inputs/policy-original.json": (experiment/"policy.json").read_bytes(),
        "inputs/policy-score02.json": (experiment/"policy-score02.json").read_bytes(),
        "inputs/sufficient-fold-scores.json": sufficient_body,
        "inputs/reference-concordance.json": args.reference.read_bytes(),
        "inputs/accepted-house-panel-science.zip": args.predecessor.read_bytes(),
        "inputs/original-fitter.py": subprocess.check_output([
            "git", "-C", str(root), "show", "1e9ee689873252a50c6806bed0b63a46018684c9:scripts/house_pair_oof.py"])}
    for name in ("independent-native-verification.json", "cache-adoption.json", "reduction-diagnostic.json"):
        members["records/"+name] = (experiment/name).read_bytes()
    members["records/fitting-receipt.json"] = (args.private/"fitting-receipt.json").read_bytes()
    environment = dict(python=sys.version, numpy=importlib.metadata.version("numpy"),
        scikit_learn=importlib.metadata.version("scikit-learn"), native_fits_local_only=True,
        public_replay_standard_library_only=True)
    members["records/numerical-environment.json"] = (json.dumps(environment, indent=2, sort_keys=True)+"\n").encode()
    for name, body in outputs.items():
        members["outputs/"+name] = body
    for name in SCRIPTS:
        members["code/scripts/"+name] = (root/"scripts"/name).read_bytes()
    for name in TESTS:
        members["code/tests/"+name] = (root/"tests"/name).read_bytes()
    members["README.txt"] = (
        "Held-out historical participation/House pairing experiment\n\n"
        "Five structural hypotheses, not five new statistical families: pooled2020president\n"
        "paired frequencies; independent/paired ridge with2020president; independent/paired\n"
        "ridge adding native2020calendar-age, education-code and survey-state predictors.\n"
        "No2022/24outcomes enter predictors and no2026partisan returns train/select a model.\n"
        "Same5prior-only folds/3nativeweightframes; primary2024postweight, older2022weights\n"
        "are only frame sensitivities, not recommended2024population weights.\n\n"
        "All75fold/model/frame score-sufficient rows,100pooled scores,40synthetic2x2cells,\n"
        "10matching stages,15decisions and5040exact fold-composition stress rows included.\n"
        "Full9-class administrative and30-class House-response pairs retain unknowns and\n"
        "contradictions separately. They do NOT learn all administrative/choice dependence.\n"
        "Known-history and selected both-positive/both-major slices are conditional tests.\n"
        "Margin matching preserves forecast odds, not observed switching. Published source\n"
        "2x2reference reused exactly; no new native fine/source-state tables are disclosed.\n\n"
        "Original frozen design preceded fits, but source/reference already explored.\n"
        "After72successful component fits, finite matmul reductions raised numerical flags\n"
        "despite agreement with product-sum/math.fsum. Only score/forecast reductions changed.\n"
        "AST-bound cache adoption preserved every successful probability array;108remaining\n"
        "fits completed, none repeated. Both policies/original source/diagnostic are retained.\n"
        "Independent native row/predictor/weight checks, math.fsum scoring, cache checks and\n"
        "separate iterative IPF verify the outputs. Native persons/features/predictions/\n"
        "coefficients/fine cells stay private. Entire35562-byte accepted predecessor included.\n\n"
        "This is retained2020-adult source evidence, with conditional shared-item House codes,\n"
        "not panel-native numeric labels, population identification, an external post-selection\n"
        "test or a2026correction. Predictors/window differ from accepted2026models. Cross-time\n"
        "pairing and added demographic/geographic features are separate comparisons; negative\n"
        "results stay. Fold-composition stress uses overlapping fitted folds: NOT design CIs.\n"
        "No precinct allocation or accepted model/map replacement.\n\n"
        "Offline full public replay, without private fits or external dependencies:\n"
        "python -S -W error code/scripts/reproduce_house_pair_oof.py "
        "--archive COMPLETE_ZIP --output NEW_DIRECTORY\n"
        "Authorized native fitting separately requires pinned original source/private stack.\n"
        "Scientific implementation commit: "+args.source_commit+"\n").encode()
    manifest = dict(contract="participation.house_pair_oof_complete_packet.v1",
        source_code_commit=args.source_commit, output_files=sorted(outputs),
        files={name: pin(body) for name, body in sorted(members.items())},
        original_persons_and_prediction_caches_included=False, only_permitted_sufficient_inputs=True)
    members["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True)+"\n").encode()
    args.output.mkdir(parents=True)
    args.dataset.mkdir(parents=True)
    archive_path = args.output/"complete-analysis.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
            if not name.startswith("code/") and name != "inputs/original-fitter.py":
                path = args.dataset/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
    assets = dict(outputs)
    assets.update({"policy-original.json": members["inputs/policy-original.json"],
                  "policy-score02.json": members["inputs/policy-score02.json"],
                  "sufficient-fold-scores.json": sufficient_body,
                  "manifest.json": members["manifest.json"], "README.txt": members["README.txt"]})
    for name, body in assets.items():
        (args.output/name).write_bytes(body)
    receipt = dict(status="complete_public_pair_OOF_packet_created", members=len(members),
        archive=pin(archive_path.read_bytes()), source_code_commit=args.source_commit,
        complete_public_outputs=7, accepted_full_predecessor_bytes=35562,
        native_respondents_and_fine_cells_exported=False)
    (args.output/"package-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
