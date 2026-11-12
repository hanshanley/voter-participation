"""Reproduce the complete new 1996 experiment without network or external commands."""

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
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def offline(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.sendto", "subprocess.Popen", "os.system"):
        raise PermissionError("Reproduction forbids network/external commands")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.package.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Use a fresh output directory")
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe member path")
        body = (root / name).read_bytes()
        if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != expected:
            raise ValueError("Changed scientific member")
    sys.addaudithook(offline)
    for probe in (lambda: socket.getaddrinfo("example.invalid", 443),
                  lambda: subprocess.run([sys.executable, "-c", "pass"], check=True)):
        try:
            probe()
        except PermissionError:
            pass
        else:
            raise ValueError("Offline guard failed")
    os.environ["CPS_1996_STATE_INPUTS"] = str(root / "inputs")
    sys.path.insert(0, str(root / "code"))
    suite = unittest.defaultTestLoader.discover(str(root / "code/tests"), pattern="test_cps_1996_state_points.py")
    tests = unittest.TextTestRunner(verbosity=1).run(suite)
    if not tests.wasSuccessful() or tests.testsRun != 8:
        raise ValueError("Focused native tests failed")
    primary = module(root / "code/scripts/cps_1996_state_points.py")
    independent = module(root / "code/scripts/verify_cps_1996_state_points.py")
    result = primary.build(*primary.load_inputs(root / "inputs"))
    output.mkdir(parents=True)
    for name, body in primary.result_files(result).items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Complete query/result byte differs")
        (output / name).write_bytes(body)
    proof = independent.verify(root / "inputs", output)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent receipt differs")
    receipt = dict(status="passed_fresh_offline_cps_1996_state_points", tests_passed=tests.testsRun,
        source_commit=manifest["source_commit"], all_full_result_query_bytes_identical=True,
        network_and_external_commands_blocked=True, independent=proof,
        whole_accepted_predecessor_included=True, older_acquisitions_or_reductions_repeated=False,
        stopped_maine_routes_retried=False, frontend_activation=False)
    (output / "reproduction.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
