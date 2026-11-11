"""Package all permitted sufficient inputs, code, queries and scenario results."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def viewer_for(result):
    factor = result["persistence_calibration"]["selected_factor"]
    polls = [row for row in result["persistence_calibration"]["complete_poll_decisions"]
        if row["target_fraction"] is not None]
    groups = []
    for row in result["complete_demographic_decisions"]:
        data = {key: row[key] for key in ("state_code", "dimension", "group", "label", "disposition")}
        cases = row["conditional_simulation"]
        if cases is None:
            data.update(point=None, envelope=None)
        else:
            selected = [case for case in cases if case["persistence_factor"] in
                (factor * .5, factor, factor * 2)]
            point = next(case["analytic"] for case in selected if case["persistence_factor"] == factor)
            data.update(point=point, envelope={name: dict(
                minimum=min(case["analytic"][name] for case in selected),
                maximum=max(case["analytic"][name] for case in selected))
                for name in point if name.startswith("synthetic_")})
        groups.append(data)
    return dict(schema_version=1, status=result["status"],
        state_scenarios={code: dict(point=result["coupling_assumptions"][code + "|" + str(factor)]["analytic"],
            envelope=result["calibrated_half_double_assumption_envelopes"][code])
            for code in sorted(result["allocations"])},
        complete_demographic_decisions=groups,
        unfitted_return_checks=result["unfitted_return_checks"],
        validation=dict(heldout_mean_absolute_error_pp=result["persistence_calibration"][
            "heldout_mean_absolute_error_pp"], current_voter_poll_tables=len(polls),
            current_voter_poll_states=len({row["state_code"] for row in polls}),
            house_poll_validation_available=False,
            population_transport_validated=False, historical_joint_holdout_passed=False),
        uncertainty=result["uncertainty"], source_units_are_people=False,
        local_allocation=False, source_nonvoter_is_administrative_staying_home=False,
        private_joint_cells_reconstructed=False, design_confidence_intervals=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("result", "bridge-archive", "demographics", "same-office-comparisons",
            "historical-cps-archive", "verification", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = json.loads(args.result.read_bytes())
    proof = json.loads(args.verification.read_bytes())
    if proof["status"] != "passed_independent_scalar_verification":
        raise ValueError("An independent acceptance receipt is required")
    inputs = {"bridge_archive": ("inputs/bridge-analysis.zip", args.bridge_archive),
        "disclosed_demographics": ("inputs/disclosed-demographics.json", args.demographics),
        "same_office_comparisons": ("inputs/same-office-comparisons.json", args.same_office_comparisons),
        "historical_cps_archive": ("inputs/historical-cps-analysis.zip", args.historical_cps_archive)}
    members = {}
    for key, (name, path) in inputs.items():
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != result["input_sha256"][key]:
            raise ValueError("Do not package different sufficient inputs")
        members[name] = body
    names = ["pyproject.toml", "docs/TRANSITION_SIMULATION.md",
        "scripts/civic_estimates.py", "scripts/transition_simulation.py",
        "scripts/transition_validation.py", "scripts/verify_transition_simulation.py",
        "scripts/package_transition_simulation.py", "scripts/reproduce_transition_simulation.py",
        "tests/test_transition_simulation.py", "tests/test_transition_validation.py"]
    for name in names:
        members[name] = (root / name).read_bytes()
    members["complete-scenarios.json"] = args.result.read_bytes()
    members["independent-verification.json"] = args.verification.read_bytes()
    members["viewer-data.json"] = json_bytes(viewer_for(result))
    members["README.txt"] = (
        "Conditional source-frame scenarios, not validated population histories.\n"
        "See docs/TRANSITION_SIMULATION.md. All sufficient permitted inputs, code,\n"
        "queries, scenarios, seeds, disclosure holds and validation decisions included.\n"
        "Run: python scripts/reproduce_transition_simulation.py --archive complete-analysis.zip "
        "--output reproduction.json\n"
    ).encode()
    members["requirements-simulation.txt"] = (
        "numpy==" + result["numerical_library_version"] + "\n").encode()
    manifest = {name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        for name, body in sorted(members.items())}
    members["manifest.json"] = json_bytes(manifest)
    args.output.mkdir(parents=True, exist_ok=False)
    path = args.output / "complete-analysis.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    for name in ("complete-scenarios.json", "viewer-data.json", "independent-verification.json"):
        (args.output / name).write_bytes(members[name])
    assets = {path.name: dict(bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())}
    for name in ("complete-scenarios.json", "viewer-data.json", "independent-verification.json"):
        assets[name] = manifest[name]
    (args.output / "checksums.json").write_bytes(json_bytes(assets))
    print(json.dumps(dict(status="complete_conditional_scientific_packet",
        archive_members=len(members), assets=assets), sort_keys=True))


if __name__ == "__main__":
    main()
