"""Replay only new public simulations offline; never fit or expose respondents."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import unittest
import zipfile


def blocked(*args, **kwargs):
    raise RuntimeError("Network and external commands disabled for public reproduction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "code"))
    from scripts import compare_house_model_families as comparison
    from scripts.verify_house_model_families import verify
    socket.socket = socket.create_connection = socket.getaddrinfo = blocked
    subprocess.Popen = subprocess.run = subprocess.check_output = blocked
    for operation in (socket.socket, socket.getaddrinfo, subprocess.Popen):
        try:
            operation()
        except RuntimeError:
            pass
        else:
            raise ValueError("Offline block not active")
    if args.output.exists():
        raise ValueError("Use a fresh reproduction directory")
    args.output.mkdir(parents=True)
    inputs = root / "inputs"
    expected = json.loads((root / "manifest.json").read_bytes())
    for name, record in expected.items():
        body = (root / name).read_bytes()
        if len(body) != record["bytes"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise ValueError("Packet member differs: " + name)
    accepted = args.output / "accepted"
    accepted.mkdir()
    with zipfile.ZipFile(inputs / "accepted-48-state-science.zip") as archive:
        for name in archive.namelist():
            if name.startswith("results/") and not name.endswith("/"):
                (accepted / Path(name).name).write_bytes(archive.read(name))
    output = args.output / "results"
    sys.argv = ["compare_house_model_families",
        "--baseline-results", str(accepted),
        "--baseline-priors", str(inputs / (comparison.BASELINE + "-priors.json")),
        "--baseline-historical", str(inputs / "baseline-historical-validation.json"),
        "--hist-priors", str(inputs / "histogram_gradient_boosting-priors.json"),
        "--extra-priors", str(inputs / "extra_randomized_trees-priors.json"),
        "--policy", str(inputs / "policy.json"), "--output", str(output)]
    comparison.main()
    files = [p for p in (root / "results").rglob("*")
             if p.is_file() and p.name != "independent-verification.json"]
    for expected in files:
        relative = expected.relative_to(root / "results")
        if expected.read_bytes() != (output / relative).read_bytes():
            raise ValueError("Reproduction differs: " + str(relative))
    proof = verify(inputs, output)
    suite = unittest.TestSuite()
    for name in ("test_house_model_comparison.py", "test_house_model_families.py"):
        namespace = runpy.run_path(str(root / "code/tests" / name), run_name="public_tests")
        for value in namespace.values():
            if isinstance(value, type) and issubclass(value, unittest.TestCase):
                suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(value))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise ValueError("Packaged tests failed")
    proof.update(all_complete_output_files_byte_identical=len(files),
                 tests_run=result.testsRun, optional_private_stack_tests_skipped=len(result.skipped),
                 network_and_external_commands_blocked=True, private_fits_repeated=False,
                 baseline_simulations_repeated=False)
    (args.output / "reproduction.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
