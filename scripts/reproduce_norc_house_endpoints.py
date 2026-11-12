"""Reproduce the endpoint-only successor without source refits or network access."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
import zipfile


ANCESTOR_SHA256 = "8ec723e49df49af59b559d4835cf7846e70ac46e4e28bac7b5c2fe0a67bc7ae0"


def load_inputs(root):
    inputs = root / "inputs"
    for name, pin in json.loads((root / "frozen-inputs.json").read_bytes()).items():
        if Path(name).name != name:
            raise ValueError("Unsafe frozen input name")
        body = (inputs / name).read_bytes()
        if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != pin:
            raise ValueError("Changed frozen input: "+name)
    ancestor = (inputs / "complete-accepted-NORC-science.zip").read_bytes()
    if hashlib.sha256(ancestor).hexdigest() != ANCESTOR_SHA256:
        raise ValueError("Changed accepted complete NORC predecessor")
    with zipfile.ZipFile(io.BytesIO(ancestor)) as archive:
        priors = json.loads(archive.read("inputs/fitted-synthetic-NORC-priors.json"))
        previous = json.loads(archive.read("results/complete-result.json"))
        nested = archive.read("inputs/complete-return-source-science.zip")
    for member in ("inputs/complete-prior-science.zip", "inputs/bridge-analysis.zip"):
        with zipfile.ZipFile(io.BytesIO(nested)) as archive:
            nested = archive.read(member)
    with zipfile.ZipFile(io.BytesIO(nested)) as archive:
        original = json.loads(archive.read("inputs/model-inputs.json"))
    held = json.loads((inputs / "held-2026-House-controls.json").read_bytes())
    key = lambda row: row["state_code"]
    controls = [row for row in original["return_controls"] if row["office"] == "house"]
    if sorted(controls, key=key) != sorted(held["return_controls"], key=key):
        raise ValueError("Held current controls differ from the accepted complete source")
    return priors, previous, held


def verify_reuse(result, previous, endpoints):
    changed = set(result["endpoint_update"]["changed_states"])
    unchanged = []
    old = {row["state_code"]: row for row in previous["rows"]}
    for row in result["rows"]:
        if row["state_code"] not in changed:
            for name in old[row["state_code"]]:
                if name != "reported_comparison" and row[name] != old[row["state_code"]][name]:
                    raise ValueError("An unchanged state numerical field was mutated")
            unchanged.append(row["state_code"])
    counts = {}
    for name in ("complete_assumption_cases", "complete_seed_cases",
                 "complete_demographic_seed_cases"):
        before = [row for row in previous[name] if row["state_code"] not in changed]
        after = [row for row in result[name] if row["state_code"] not in changed]
        encoded = lambda row: json.dumps(row, sort_keys=True, allow_nan=False)
        if sorted(map(encoded, before)) != sorted(map(encoded, after)):
            raise ValueError("An unchanged state's complete simulation cases were mutated")
        counts[name] = len(after)
    revised = [row["state_code"] for row in endpoints["rows"]
               if row["old_previous_counts"] is not None
               and row["old_previous_counts"] != row["previous_candidate_counts"]]
    newly_anchored = [row["state_code"] for row in endpoints["rows"]
                      if not row["old_comparison_available"]
                      and row["status"] == "qualified_source_comparison"]
    return dict(status="passed_unchanged_state_numerics_and_full_simulation_reuse",
                unchanged_states=sorted(unchanged), preserved_cases=counts,
                revised_previously_anchored_baselines=sorted(revised),
                newly_anchored_states=sorted(newly_anchored),
                source_models_refitted=False, current_source_controls_changed=False)


def offline(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                 "socket.gethostbyname", "socket.sendto", "subprocess.Popen", "os.system"):
        raise PermissionError("Public reproduction forbids network/external commands")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    root = args.package.resolve()
    sys.addaudithook(offline)
    for probe in (lambda: socket.getaddrinfo("example.invalid", 443),
                  lambda: subprocess.run([sys.executable, "-c", "pass"], check=True)):
        try:
            probe()
        except PermissionError:
            pass
        else:
            raise ValueError("Offline guard failed")
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, pin in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe member path")
        body = (root / name).read_bytes()
        if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != pin:
            raise ValueError("Changed complete member: "+name)
    sys.path.insert(0, str(root / "code"))
    from scripts import norc_house_endpoint_successor as successor
    from scripts import norc_house_model as model, verify_norc_house_model as independent
    suite = unittest.TestSuite(unittest.defaultTestLoader.discover(
        str(root / "code/tests"), pattern=pattern)
        for pattern in ("test_norc_house_model.py", "test_house_clerk_endpoints.py"))
    tests = unittest.TextTestRunner().run(suite)
    if not tests.wasSuccessful():
        raise ValueError("Focused tests failed")
    priors, previous, held = load_inputs(root)
    endpoints = successor.comparisons(
        json.loads((root / "inputs/native-house-facts.json").read_bytes()),
        json.loads((root / "inputs/native-house-recap.json").read_bytes()), held, previous)
    if model.encoded(endpoints) != (root / "inputs/complete-endpoint-decisions.json").read_bytes():
        raise ValueError("Source endpoint decisions changed")
    result = successor.build(priors, previous, endpoints)
    proof = independent.verify(result, priors)
    reuse = verify_reuse(result, previous, endpoints)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent numerical proof changed")
    if reuse != json.loads((root / "checks/unchanged-state-reuse.json").read_bytes()):
        raise ValueError("Unchanged state proof changed")
    files = model.result_files(result)
    for name, body in files.items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Complete query byte mismatch: "+name)
    args.output.mkdir(parents=True)
    for name, body in files.items():
        (args.output / name).write_bytes(body)
    receipt = dict(status="passed_complete_offline_NORC_endpoint_successor",
        all_eight_complete_output_files_byte_identical=True, tests_passed=tests.testsRun,
        network_and_external_commands_blocked=True, original_survey_reduction_or_fit_repeated=False,
        only_changed_state_simulations_recomputed=True, independent=proof, reuse=reuse)
    (args.output / "reproduction.json").write_bytes(model.encoded(receipt))
    print(json.dumps(receipt))
