"""Reproduce every new fitted query offline; do not rerun prior survey simulations."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
import zipfile


def offline(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo",
            "socket.gethostbyname", "socket.sendto", "subprocess.Popen", "os.system"):
        raise PermissionError("Offline reproduction forbids network/external commands")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.package.resolve()
    if args.output.exists():
        raise ValueError("Use a fresh output")
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
        if len(body) != pin["bytes"] or hashlib.sha256(body).hexdigest() != pin["sha256"]:
            raise ValueError("Changed complete scientific member")
    sys.path.insert(0, str(root / "code"))
    from scripts import calibrated_swing as primary
    from scripts import verify_calibrated_swing as independent
    tests = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover(
        str(root / "code/tests"), pattern="test_calibrated_swing.py"))
    if not tests.wasSuccessful():
        raise ValueError("Regression tests failed")
    archive = root / "inputs/complete-prior-science.zip"
    returns = root / "inputs/complete-return-comparisons.json"
    with zipfile.ZipFile(archive) as source:
        prior = json.loads(source.read("complete-scenarios.json"))
    original = json.loads(returns.read_bytes())
    result = primary.build(original, prior)
    result["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in (("complete_prior_science", archive), ("complete_return_comparisons", returns))}
    args.output.mkdir(parents=True)
    for name, body in primary.result_files(result).items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("New full query bytes differ; reference toolchain is Python3.9")
        (args.output / name).write_bytes(body)
    proof = independent.verify(result, original)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent numerical receipt differs")
    receipt = dict(status="passed_offline_return_constrained_queries", tests_passed=tests.testsRun,
        all_six_full_output_bytes_identical=True, network_and_external_commands_blocked=True,
        complete_fits=801, original_source_reductions_repeated=False, independent=proof)
    (args.output / "reproduction.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt))
