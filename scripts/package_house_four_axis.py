"""Package all permitted four-axis inputs, queries, simulations and predecessor science."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from house_four_axis_public import replay

SCRIPTS = ("house_four_axis.py", "fit_house_four_axis.py", "house_four_axis_public.py",
    "verify_house_four_axis.py", "package_house_four_axis.py", "reproduce_house_four_axis.py",
    "house_pair_oof.py", "house_panel_validation.py", "house_fixed_copula.py", "house_pair_public.py")
TESTS = ("test_house_four_axis.py", "test_house_four_axis_public.py")


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("experiment", "private", "predecessor", "dataset"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    experiment = args.experiment
    policy_body = (experiment/"policy.json").read_bytes()
    policy = json.loads(policy_body)
    sufficient_body = (args.private/"public-sufficient-candidate.json").read_bytes()
    proof_body = (experiment/"independent-native-verification.json").read_bytes()
    proof = json.loads(proof_body)
    if (proof["status"] != "pass" or proof["new_conditional_heads_verified"] != 30
            or proof["accepted_paired_heads_verified_without_refit"] != 60
            or proof["policy_sha256"] != pin(policy_body)["sha256"]
            or proof["sufficient_sha256"] != pin(sufficient_body)["sha256"]
            or proof["verifier_sha256"] != pin((root/"scripts/verify_house_four_axis.py").read_bytes())["sha256"]):
        raise ValueError("Incomplete independent source acceptance or changed code")
    for key, path in (("driver_sha256", "scripts/fit_house_four_axis.py"),
                      ("core_sha256", "scripts/house_four_axis.py"), ("tests_sha256", "tests/test_house_four_axis.py"),
                      ("parent_fitter_sha256", "scripts/house_pair_oof.py"),
                      ("projector_sha256", "scripts/house_fixed_copula.py")):
        if policy[key] != pin((root/path).read_bytes())["sha256"]:
            raise ValueError("Frozen experiment implementation differs")
    outputs = replay(json.loads(sufficient_body))
    dataset = {"inputs/policy.json": policy_body, "inputs/sufficient-scores.json": sufficient_body,
        "records/independent-native-verification.json": proof_body,
        "records/fitting-receipt.json": (args.private/"fitting-receipt.json").read_bytes()}
    for name, body in outputs.items():
        if body != (experiment/"results"/name).read_bytes():
            raise ValueError("Accepted complete public output differs")
        dataset["outputs/"+name] = body
    for name, body in dataset.items():
        target = args.dataset/name
        if target.exists() and target.read_bytes() != body:
            raise ValueError("Versioned data path already contains different bytes")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    if args.stage_only:
        print(json.dumps(dict(status="verified_four_axis_public_data_staged", files=len(dataset))))
        return
    if not args.output or args.output.exists() or not args.source_commit or len(args.source_commit) != 40:
        raise ValueError("Provide exact implementation commit and fresh science directory")
    predecessor = args.predecessor.read_bytes()
    if pin(predecessor)["sha256"] != policy["delivery"]["full_predecessor_sha256"]:
        raise ValueError("Whole accepted predecessor differs")
    members = dict(dataset)
    members["inputs/accepted-fixed-copula-science.zip"] = predecessor
    members["records/numerical-environment.json"] = (experiment/"numerical-environment.json").read_bytes()
    for name in SCRIPTS:
        members["code/scripts/"+name] = (root/"scripts"/name).read_bytes()
    for name in TESTS:
        members["code/tests/"+name] = (root/"tests"/name).read_bytes()
    members["README.txt"] = (
        "Four-axis administrative participation / reported House dependence\n\n"
        "New30conditional House30 heads reuse60accepted paired administrative9/House30 heads.\n"
        "Same6175retained cases,5prior-only folds,2feature levels,3nativeweightframes; no oldfits\n"
        "repeated. Jointforecast enumeratesALL9hypothetical administrative pairs for each held-out\n"
        "case; observed future test histories never enter forecast features. Administrative pairs\n"
        "condition a likelihood factor during TRAINING, not known future covariates at prediction.\n"
        "Conditioning on2022 histories is a retrospective source diagnostic: pre2024availability\n"
        "of the later-released matched administrative record is NOT established. No archived\n"
        "prospective validation or contemporaneous election-day residence is claimed.\n"
        "Three hypotheses: independent pairs, conditionalHousegivenadmin, and positive KL projection\n"
        "preserving both accepted per-case pair margins. Complete270-state joint predictions remain\n"
        "private; broad loss sums reproduce all public results. Unknowns/conflicts stay unrepaired.\n\n"
        "Prior2022positive-history/major-House cohort evaluates15future outcomes. Separate2022\n"
        "explicit-nonvoter cohort evaluates entry/return. FutureknownP/N binary scores are explicitly\n"
        "outcome-selected diagnostics. All540score queries,216pooled scores,60predictive queries,\n"
        "54coarse estimates,270predictive-simulation rows and18144fold-stress rows included.\n"
        "Simulations:600000synthetic mixture draws, NOT real persons or survey/design confidence\n"
        "intervals. Overlapping-training fold compositions are stresses, not independent samples.\n\n"
        "Primaryhistory joint logloss2.371022->2.280635 under fixed pair margins. Prior-nonvoter\n"
        "future15logloss1.551515->1.483908 and knownP/N.490998->.460688 improve. Prior-voter\n"
        "major-cohort future15.661000->.664968 and knownP/N.069624->.070773 WORSEN. Added\n"
        "demographic/geographic predictors still do not beat simpler history. Coarse aggregate\n"
        "entry calibration need not improve when individual proper scores improve; errors retained.\n"
        "Every raw cell must reach30 before publishing a pooled primary coarse reference. The\n"
        "six-cell prior-major-voter table is heldWHOLE; the three-cell prior-nonvoter table qualifies.\n"
        "No threshold was relaxed after seeing counts. No native fine/source-state tables disclosed.\n\n"
        "Whole63651646-byte accepted predecessor included. Source2020-adult retention, conditional\n"
        "House-code bridge and postwave weights remain. Original source administration is NOT\n"
        "2026NORC voting likelihood; no parameter/default/map change, population or2026validation,\n"
        "candidate-administrative truth, firstever/eligibility/death/migration or local allocation.\n"
        "Native persons/features/per-case predictions/losses/coefficients/fine cells stay private.\n\n"
        "Offline stdlib replay (no private fitting):\n"
        "python -S -W error code/scripts/reproduce_house_four_axis.py --archive COMPLETE_ZIP --output NEW_DIRECTORY\n"
        "Source tests run from repository data or extracted packet; private numerical tests require\n"
        "the pinned optional scientific stack, while pure feature/public arithmetic tests need stdlib.\n"
        "Scientific implementation commit: "+args.source_commit+"\n").encode()
    manifest = dict(contract="participation.house_four_axis_packet.v1", source_code_commit=args.source_commit,
        output_files=sorted(outputs), files={name: pin(body) for name, body in sorted(members.items())},
        original_persons_predictions_or_fine_cells_included=False, only_permitted_complete_inputs=True,
        population_or2026_transport_validated=False, current_models_or_website_changed=False)
    members["manifest.json"] = encoded(manifest)
    args.output.mkdir(parents=True)
    archive_path = args.output/"complete-analysis.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
    for name, body in outputs.items():
        (args.output/name).write_bytes(body)
    for name in ("manifest.json", "README.txt"):
        (args.output/name).write_bytes(members[name])
    for name, body in (("policy.json", policy_body), ("sufficient-scores.json", sufficient_body)):
        (args.output/name).write_bytes(body)
    receipt = dict(status="complete_four_axis_public_packet_created", members=len(members),
        archive=pin(archive_path.read_bytes()), source_code_commit=args.source_commit,
        complete_public_outputs=9, entire_predecessor_bytes=len(predecessor), native_persons_or_predictions_exported=False)
    (args.output/"package-receipt.json").write_bytes(encoded(receipt))
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
