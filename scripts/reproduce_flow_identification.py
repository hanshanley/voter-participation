"""Reproduce the complete new gross-flow bounds offline, without old model fits."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest


def offline(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo",
            "socket.gethostbyname", "socket.sendto", "subprocess.Popen", "os.system"):
        raise PermissionError("Network and external commands are blocked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh reproduction output")
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
            raise ValueError("Changed complete scientific member")
    sys.path.insert(0, str(root / "code"))
    from scripts import flow_identification as primary
    from scripts import verify_flow_identification as independent
    tests = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover(
        str(root / "code/tests"), pattern="test_flow_identification.py"))
    if not tests.wasSuccessful():
        raise ValueError("Focused tests failed")
    archive = root / "inputs/complete-return-constrained-science.zip"
    accepted = primary.read_accepted(archive)
    result = primary.build(accepted)
    result["accepted_science_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    args.output.mkdir(parents=True)
    for name, body in primary.result_files(result).items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Full new output differs: "+name)
        (args.output / name).write_bytes(body)
    proof = independent.verify(result, accepted)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent proof differs")
    receipt = dict(status="passed_offline_exact_gross_flow_bounds",
        tests_passed=tests.testsRun, all_six_query_outputs_byte_identical=True,
        network_and_external_commands_blocked=True, original_fits_or_source_reductions_rerun=False,
        independent=proof)
    (args.output / "reproduction.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt))
