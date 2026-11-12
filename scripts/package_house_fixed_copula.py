"""Package complete permitted calibration and six current simulation runs."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from house_fixed_copula_public import replay

SCRIPTS = ("house_fixed_copula.py", "fit_house_fixed_copula.py", "house_fixed_copula_public.py",
    "transport_house_copula.py", "build_house_copula_profiles.py", "verify_house_fixed_copula.py",
    "verify_house_copula_profiles.py", "reproduce_house_fixed_copula.py", "package_house_fixed_copula.py",
    "house_pair_public.py", "house_pair_oof.py", "house_panel_validation.py",
    "norc_house_model.py", "compare_house_model_families.py", "verify_norc_house_model.py")
TESTS = ("test_house_fixed_copula.py", "test_transport_house_copula.py", "test_house_fixed_copula_public.py")
FAMILIES = ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees")
PRIOR_FILES = tuple(family+"-priors.json" for family in FAMILIES)
OUTPUT_FILES = ("complete-result.json", "viewer-data.json", "complete-state-mechanisms.csv",
    "complete-demographic-contributions.csv", "complete-modeled-flows.csv", "complete-assumption-cases.json",
    "complete-seed-cases.json", "complete-demographic-seed-cases.json")


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("experiment", "private", "family-experiment", "reference", "source-predecessor",
                "family-predecessor", "baseline-viewer", "dataset"):
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
    verification = json.loads((experiment/"independent-nested-verification.json").read_bytes())
    profiles_proof = json.loads((experiment/"independent-current-profiles.json").read_bytes())
    for proof, code in ((verification, "verify_house_fixed_copula.py"),
                        (profiles_proof, "verify_house_copula_profiles.py")):
        if proof["status"] != "pass" or proof["verifier_sha256"] != pin((root/"scripts"/code).read_bytes())["sha256"]:
            raise ValueError("Independent numerical acceptance or verifier differs")
    if (verification["policy_sha256"] != pin(policy_body)["sha256"] or
            verification["sufficient_sha256"] != pin(sufficient_body)["sha256"] or
            verification["new_inner_fits_verified"] != 180 or
            profiles_proof["source_model_profiles_verified"] != 6):
        raise ValueError("Incomplete new fits or profile verification")
    for key, path in (("driver_sha256", "scripts/fit_house_fixed_copula.py"),
                      ("copula_sha256", "scripts/house_fixed_copula.py"),
                      ("tests_sha256", "tests/test_house_fixed_copula.py")):
        if policy[key] != pin((root/path).read_bytes())["sha256"]:
            raise ValueError("Frozen experiment code differs")
    outputs = replay(json.loads(sufficient_body), json.loads(args.reference.read_bytes()))
    dataset = {"inputs/policy.json": policy_body, "inputs/sufficient-scores.json": sufficient_body,
               "inputs/reference-concordance.json": args.reference.read_bytes()}
    for name in ("independent-nested-verification.json", "independent-current-profiles.json"):
        dataset["records/"+name] = (experiment/name).read_bytes()
    dataset["records/fitting-receipt.json"] = (args.private/"fitting-receipt.json").read_bytes()
    for name, body in outputs.items():
        if body != (experiment/"results"/name).read_bytes():
            raise ValueError("Accepted source output differs")
        dataset["outputs/"+name] = body
    for name in ("viewer-attenuated.json", "viewer-full.json", "profile-summary.json",
                 "complete-profile-family-state-comparisons.csv"):
        dataset[name] = (experiment/"current-profiles"/name).read_bytes()
    for name, body in dataset.items():
        target = args.dataset/name
        if target.exists() and target.read_bytes() != body:
            raise ValueError("Versioned data path already contains different bytes")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    if args.stage_only:
        print(json.dumps(dict(status="verified_public_data_staged", files=len(dataset))))
        return
    if not args.output or args.output.exists() or not args.source_commit or len(args.source_commit) != 40:
        raise ValueError("Use a fresh scientific packet and exact implementation commit")
    members = {key: value for key, value in dataset.items() if not key.startswith("viewer-")}
    members["inputs/original-viewer.json"] = args.baseline_viewer.read_bytes()
    predecessors = (
        ("inputs/accepted-paired-source-science.zip", args.source_predecessor,
         "a48dcae4c99911cf8c3dc05ef39bde1617d4abb12589d99d47dec15649c97ed8"),
        ("inputs/accepted-three-family-science.zip", args.family_predecessor,
         "124c3702ea3d7218351f0105a571407804d48a2afa9c924b743fb5dc8dd214da"))
    for name, path, digest in predecessors:
        body = path.read_bytes()
        if pin(body)["sha256"] != digest:
            raise ValueError("Whole accepted scientific predecessor differs")
        members[name] = body
    for name in (*PRIOR_FILES, "manifest.json"):
        members["inputs/original-priors/"+name] = (args.family_experiment/"inputs"/name).read_bytes()
    for family in FAMILIES:
        members["inputs/original-results/"+family+"/complete-result.json"] = (
            args.family_experiment/"results"/family/"complete-result.json").read_bytes()
    all_outputs = {"source/"+name: body for name, body in outputs.items()}
    for profile in ("attenuated", "full"):
        for family in FAMILIES:
            directory = experiment/"current-profiles"/profile/family
            for name in ("synthetic-priors.json", "source-projection-decisions.json"):
                members["inputs/current-profiles/"+profile+"/"+family+"/"+name] = (directory/name).read_bytes()
            members["records/"+profile+"-"+family+"-accounting.json"] = (directory/"independent-accounting-proof.json").read_bytes()
            for name in OUTPUT_FILES:
                all_outputs["current/"+profile+"/"+family+"/"+name] = (directory/name).read_bytes()
    for name in ("viewer-attenuated.json", "viewer-full.json", "profile-summary.json",
                 "complete-profile-family-state-comparisons.csv"):
        all_outputs["current/"+name] = (experiment/"current-profiles"/name).read_bytes()
    for name, body in all_outputs.items():
        members["outputs/"+name] = body
    for name in SCRIPTS:
        members["code/scripts/"+name] = (root/"scripts"/name).read_bytes()
    for name in TESTS:
        members["code/tests/"+name] = (root/"tests"/name).read_bytes()
    members["README.txt"] = (
        "Fixed-marginal historical House calibration and conditional2026association stresses\n\n"
        "180 new inner marginal fits;60 accepted outer heads reused unchanged. Every inner fit\n"
        "and calibration excludes its outer holdout.270full curves/30decisions/60outer score\n"
        "rows; all categories, unknowns, negative results, earlier-weight and fold stresses stay.\n"
        "Full6x5per-case year margins fixed; DD/RR kernel only. No administrative-N persistence\n"
        "parameter is estimated. Primary retained-panel history logloss1.313660->1.263987;\n"
        "Brier.483039->.477228. Demographics are a separate feature comparison, not a new family.\n\n"
        "Conditional gate passed. Source history median theta8 supports sqrt8/8 STRESS profiles.\n"
        "State-level postaggregation transport is NOT validated per-case2026parameter transfer.\n"
        "Each state/group-year source margin and demographic partition is preserved; source-only\n"
        "feasibility backoff precedes return comparisons. Neither stress improved48-state\n"
        "before-conditioning MAE for ANY family. All errors are retained; original default stays.\n"
        "All6new profile-family runs, every state/group/assumption/seed simulation query, all\n"
        "transformed synthetic priors/feasibility decisions and450state comparisons included.\n"
        "Entire accepted paired-source and35332487-byte three-family predecessors included.\n"
        "No native respondents, features, per-case predictions, coefficients or fine cells.\n\n"
        "Reported nonvote, source likelihood and unknown are not observed staying home or\n"
        "first-ever voting. Conditional shared-item House codes/retained2020-adult recruitment\n"
        "and differing predictors/election direction remain. No population/2026validation, design\n"
        "confidence intervals, identified causes or allocation to counties/precincts.\n\n"
        "Offline standard-library replay checks all members, rebuilds8broad source outputs,\n"
        "reruns only6NEW profile simulations/projections, and byte-compares all60outputs plus\n"
        "12transformed-prior/decision inputs. It does NOT repeat baseline simulations or private\n"
        "fitting/calibration; broad sums reproduce public scoring, not withheld native fits.\n"
        "python -S -W error code/scripts/reproduce_house_fixed_copula.py --archive COMPLETE_ZIP --output NEW_DIRECTORY\n"
        "Scientific implementation commit: "+args.source_commit+"\n").encode()
    manifest = dict(contract="participation.house_fixed_copula_complete_packet.v1",
        source_code_commit=args.source_commit, output_files=sorted(all_outputs),
        files={name: pin(body) for name, body in sorted(members.items())},
        original_persons_or_predictions_included=False, only_permitted_complete_inputs=True,
        historical_transport_validated=False, original_default_changed=False)
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
    for name in ("policy.json",):
        (args.output/name).write_bytes(policy_body)
    (args.output/"sufficient-scores.json").write_bytes(sufficient_body)
    for name in ("profile-summary.json", "complete-profile-family-state-comparisons.csv"):
        (args.output/name).write_bytes((experiment/"current-profiles"/name).read_bytes())
    receipt = dict(status="complete_public_copula_packet_created", members=len(members),
        archive=pin(archive_path.read_bytes()), source_code_commit=args.source_commit,
        complete_public_outputs=len(all_outputs), new_profile_simulation_runs=6,
        accepted_full_source_predecessor_bytes=163404, accepted_full_family_predecessor_bytes=35332487,
        native_respondents_and_fine_cells_exported=False)
    (args.output/"package-receipt.json").write_bytes(encoded(receipt))
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
