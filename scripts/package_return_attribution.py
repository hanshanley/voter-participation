#!/usr/bin/env python3
"""Package all sufficient model inputs, all estimates/scenarios, code and exact reproduction."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "20261110-01"
RELEASE = "https://github.com/hanshanley/margin_of_error/releases/download/participation-return-attribution-20261110-01/"


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def table(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def viewer(results):
    rows = []
    for model in results["models"]:
        ref = model["reference"]
        rows.append(dict(id=model["id"], state_code=model["state_code"], office=model["office"],
            components_pp={key: float(value) for key, value in ref["contributions_pp"].items()},
            ranges_pp={key: {name: float(value) for name, value in bounds.items()}
                for key, bounds in model["assumption_ranges_pp"].items()},
            source_frame_change_pp=float(ref["source_frame_change_pp"]),
            current_return_margin_pp=float(ref["current_return_known_major_party_margin_pp"]),
            observed_same_office_change_pp=float(model["observed_same_office_change_pp"])
                if model["observed_same_office_change_pp"] is not None else None,
            previous_office_frame_gap_pp=float(model["prior_office_and_source_frame_gap_pp"])
                if model["prior_office_and_source_frame_gap_pp"] is not None else None,
            comparison=model["baseline"], support=model["source_support"],
            evidence=dict(switching=model["evidence"]["switching"],
                cross_office_transport=model["evidence"]["cross_office_transport"],
                return_scope=model["evidence"]["candidate_returns"]["source_scope"],
                native_clock=model["evidence"]["candidate_returns"].get("source_native_clock")),
            dominant_modeled_term=model["dominant_modeled_term"]))
    return dict(version=VERSION, status="experimental_NORC_returns_bridge_not_causal_population_attribution",
        rows=rows, complete_download_url=RELEASE+"complete-analysis.zip",
        model_baseline="Recalled 2024 President in the current study frame",
        source_population="Current NORC respondents; not original historical electorates",
        uncertainty="0.5x, 1x and 1.5x switching/nonparticipation moment-strength scenarios, not confidence intervals",
        other_uncertainty_not_exhausted=True, state_estimates_not_allocated_locally=True,
        eligibility_death_migration=None, design_confidence_intervals=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--assets-directory", type=Path, required=True)
    parser.add_argument("--data-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.assets_directory.exists() or args.data_directory.exists():
        raise ValueError("Refuse to replace an immutable numerical version")
    results = json.loads(args.results.read_bytes())
    verification = json.loads(args.verification.read_bytes())
    assert results["input_sha256"] == pin(args.inputs.read_bytes())["sha256"]
    assert verification["status"].startswith("PASS") and verification["models"] == len(results["models"]) == 113
    view = encoded(viewer(results))
    decisions, scenarios = [], []
    for model in results["models"]:
        base = dict(id=model["id"], state_code=model["state_code"], office=model["office"],
            model_prior_year=model["baseline"]["source_year"],
            model_prior_office=model["baseline"]["source_office"])
        decisions.append(dict(base, **model["reference"]["contributions_pp"],
            source_frame_change_pp=model["reference"]["source_frame_change_pp"],
            observed_same_office_change_pp=model["observed_same_office_change_pp"],
            previous_office_frame_gap_pp=model["prior_office_and_source_frame_gap_pp"]))
        for case in model["sensitivity_scenarios"]:
            scenarios.append(dict(base, switching_multiplier=case["switching_multiplier"],
                nonparticipation_multiplier=case["nonparticipation_multiplier"],
                **case["contributions_pp"], source_frame_change_pp=case["source_frame_change_pp"]))
    members = {
        "inputs/model-inputs.json": args.inputs.read_bytes(),
        "results/modeled-effects.json": args.results.read_bytes(),
        "results/viewer-data.json": view,
        "results/all-113-model-decisions.csv": table(decisions),
        "results/all-1017-sensitivity-scenarios.csv": table(scenarios),
        "verification/independent-verification.json": args.verification.read_bytes(),
    }
    for name in ("return_attribution.py", "select_return_attribution_inputs.py",
                 "verify_return_attribution.py", "package_return_attribution.py"):
        members["scripts/"+name] = (ROOT / "scripts" / name).read_bytes()
    members["tests/test_return_attribution.py"] = (ROOT / "tests/test_return_attribution.py").read_bytes()
    members["README.txt"] = (
        "EXPERIMENTAL NORC / RETURNS ATTRIBUTION BRIDGE\n\n"
        "113 conditional office/state estimates and all 1017 declared sensitivity scenarios.\n"
        "Inputs contain every whole-state signed survey moment used, all held House candidate controls,\n"
        "all selected native Senate candidate vectors, all 2014 governor factual county records,\n"
        "and all 55 qualified office-specific main poll tables. No respondent records, private\n"
        "fine joint/demographic cells, acquisition headers or publisher application code are included.\n\n"
        "The recalled baseline is 2024 President, not automatically the previous House/Senate election.\n"
        "Model-classified nonparticipation is not administrative evidence of staying home.\n"
        "House information and current-voter poll masses require explicit transport assumptions.\n"
        "The return/frame gap is not assigned to persuasion or nonparticipation.\n"
        "Strength-sensitivity ranges are not confidence/identification intervals or exhaustive uncertainty.\n"
        "No original-coalition population or causal certification; no state-to-local allocation.\n"
        "Original attributed numerical aggregate analysis; native privately supplied survey files\n"
        "and documents are not mirrored. State whole-frame moments are sufficient for this bridge,\n"
        "not for reconstructing the private survey or its fine transition tables.\n\n"
        "REPRODUCE: python reproduce.py --output /path/to/new-directory\n"
        "All packaged member hashes are checked, then every full estimate and the viewer is rerun\n"
        "and byte-compared without source acquisition. Tests: python -m unittest discover -s tests.\n"
    ).encode()
    members["reproduce.py"] = b'''import argparse,hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
if a.output.exists():raise ValueError("Output must be new")
manifest=json.loads((root/"manifest.json").read_bytes())
for name,pin in manifest["files"].items():
 body=(root/name).read_bytes()
 assert len(body)==pin["bytes"] and hashlib.sha256(body).hexdigest()==pin["sha256"],name
a.output.mkdir(parents=True)
subprocess.run([sys.executable,str(root/"scripts/return_attribution.py"),
 "--inputs",str(root/"inputs/model-inputs.json"),"--output",str(a.output/"modeled-effects.json")],check=True)
assert (a.output/"modeled-effects.json").read_bytes()==(root/"results/modeled-effects.json").read_bytes()
sys.path.insert(0,str(root/"scripts"))
from package_return_attribution import encoded,viewer
body=encoded(viewer(json.loads((a.output/"modeled-effects.json").read_bytes())))
assert body==(root/"results/viewer-data.json").read_bytes()
(a.output/"viewer-data.json").write_bytes(body)
print("PASS_exact_all113_models_all1017_scenarios_and_viewer")
'''
    members["manifest.json"] = encoded(dict(version=VERSION,
        files={name: pin(body) for name, body in sorted(members.items())}))
    args.assets_directory.mkdir(parents=True)
    archive_path = args.assets_directory / "complete-analysis.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    for name in ("modeled-effects.json", "viewer-data.json", "all-113-model-decisions.csv",
                 "all-1017-sensitivity-scenarios.csv"):
        (args.assets_directory / name).write_bytes(members["results/"+name])
    receipt = dict(url=RELEASE+"complete-analysis.zip", **pin(archive_path.read_bytes()),
        members=len(members), models=113, scenarios=1017, full_sufficient_numerical_inputs=True,
        raw_private_survey_data=False, metadata_only=False)
    (args.assets_directory / "download.json").write_bytes(encoded(receipt))
    args.data_directory.mkdir(parents=True)
    for name, body in (("model-inputs.json", args.inputs.read_bytes()), ("viewer-data.json", view),
                       ("download.json", encoded(receipt)), ("independent-verification.json", args.verification.read_bytes())):
        (args.data_directory / name).write_bytes(body)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
