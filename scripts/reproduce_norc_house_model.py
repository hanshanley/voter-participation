"""Reproduce the complete new NORC simulations offline from permitted fitted inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
import zipfile


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
        if len(body) != pin["bytes"] or hashlib.sha256(body).hexdigest() != pin["sha256"]:
            raise ValueError("Changed complete member")
    sys.path.insert(0, str(root / "code"))
    from scripts import norc_house_model as model
    from scripts import verify_norc_house_model as independent
    tests = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover(
        str(root / "code/tests"), pattern="test_norc_house_model.py"))
    if not tests.wasSuccessful():
        raise ValueError("Focused tests failed")
    priors = json.loads((root / "inputs/fitted-synthetic-NORC-priors.json").read_bytes())
    with zipfile.ZipFile(root / "inputs/complete-return-source-science.zip") as archive:
        accepted = json.loads(archive.read("results/complete-result.json"))
    result = model.build(priors, accepted)
    args.output.mkdir(parents=True)
    for name, body in model.result_files(result).items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Complete query byte mismatch: "+name)
        (args.output / name).write_bytes(body)
    proof = independent.verify(result, priors)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent numerical proof changed")
    receipt = dict(status="passed_complete_offline_NORC_demographic_simulations",
        all_eight_complete_output_files_byte_identical=True, tests_passed=tests.testsRun,
        network_and_external_commands_blocked=True, original_survey_reduction_or_fit_repeated=False,
        independent=proof)
    (args.output / "reproduction.json").write_bytes(model.encoded(receipt))
    print(json.dumps(receipt))
