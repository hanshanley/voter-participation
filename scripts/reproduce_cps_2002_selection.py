"""Reproduce the complete new point selection offline without repeating native parsing."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def offline(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo",
            "socket.gethostbyname", "socket.sendto", "subprocess.Popen", "os.system"):
        raise PermissionError("CPS reproduction forbids network and external commands")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.package.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Use a fresh reproduction directory")
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe scientific member")
        body = (root / name).read_bytes()
        if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != expected:
            raise ValueError("Changed complete scientific member")
    sys.addaudithook(offline)
    for probe in (lambda: socket.getaddrinfo("example.invalid", 443),
            lambda: subprocess.run([sys.executable, "-c", "pass"], check=True)):
        try:
            probe()
        except PermissionError:
            pass
        else:
            raise ValueError("Offline/external-command guard failed")
    os.environ["CPS_2002_INPUTS"] = str(root / "inputs")
    sys.path.insert(0, str(root / "code"))
    suite = unittest.defaultTestLoader.discover(str(root / "code/tests"), pattern="test_cps_2002_selection.py")
    tests = unittest.TextTestRunner(verbosity=1).run(suite)
    if not tests.wasSuccessful() or tests.testsRun != 10:
        raise ValueError("Focused selection regression failed")
    primary = module(root / "code/scripts/cps_2002_selection.py")
    verifier = module(root / "code/scripts/verify_cps_2002_selection.py")
    result = primary.build(*primary.load_inputs(root / "inputs"))
    output.mkdir(parents=True)
    members = primary.result_files(result)
    for name, body in members.items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Full result/query byte mismatch")
        (output / name).write_bytes(body)
    proof = verifier.verify(root / "inputs", output)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent numerical receipt differs")
    receipt = dict(status="passed_fresh_offline_cps_2002_point_selection",
        tests_passed=tests.testsRun, all_full_result_query_bytes_identical=True,
        network_and_external_commands_blocked=True, previous_native_reductions_repeated=False,
        whole_predecessor_packet_included=True, source_commit=manifest["source_commit"],
        independent=proof)
    (output / "reproduction.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
