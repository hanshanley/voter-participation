"""Verify and reproduce the complete conditional scenario packet offline."""

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile


def blocked(*args, **kwargs):
    raise AssertionError("Offline reproduction attempted network or external commands")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive_path, output = args.archive.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Do not overwrite an existing acceptance receipt")
    with tempfile.TemporaryDirectory(prefix="transition-offline-") as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if set(archive.namelist()) != set(manifest) | {"manifest.json"} \
                    or len(archive.namelist()) != len(manifest) + 1:
                raise ValueError("Incomplete or duplicate packet members")
            for name, record in manifest.items():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe packet member")
                body = archive.read(name)
                if len(body) != record["bytes"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
                    raise ValueError("Pinned packet member differs")
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
        socket.socket = socket.create_connection = blocked
        subprocess.Popen = subprocess.run = blocked
        os.system = os.popen = blocked
        for name in dir(os):
            if name.startswith(("exec", "spawn")):
                setattr(os, name, blocked)
        warnings.simplefilter("error", RuntimeWarning)
        sys.path.insert(0, str(root))
        sys.path.insert(0, str(root / "scripts"))
        with contextlib.redirect_stdout(io.StringIO()):
            suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_transition_*.py")
            tests = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            if not tests.wasSuccessful():
                raise AssertionError("Packaged focused tests failed: " + repr(tests.errors + tests.failures))
            inputs = ["--bridge-archive", str(root / "inputs/bridge-analysis.zip"),
                "--demographics", str(root / "inputs/disclosed-demographics.json"),
                "--same-office-comparisons", str(root / "inputs/same-office-comparisons.json"),
                "--historical-cps-archive", str(root / "inputs/historical-cps-analysis.zip")]
            reproduced = root / "reproduced.json"
            sys.argv = ["transition_simulation.py", *inputs, "--output", str(reproduced)]
            runpy.run_path(str(root / "scripts/transition_simulation.py"), run_name="__main__")
            if reproduced.read_bytes() != (root / "complete-scenarios.json").read_bytes():
                raise AssertionError("Full scenario/seed/query bytes differ")
            namespace = runpy.run_path(str(root / "scripts/package_transition_simulation.py"))
            viewer = namespace["json_bytes"](namespace["viewer_for"](json.loads(reproduced.read_bytes())))
            if viewer != (root / "viewer-data.json").read_bytes():
                raise AssertionError("Compact viewer bytes differ")
            proof_path = root / "reproduced-verification.json"
            sys.argv = ["verify_transition_simulation.py", "--result", str(reproduced),
                *inputs, "--output", str(proof_path)]
            runpy.run_path(str(root / "scripts/verify_transition_simulation.py"), run_name="__main__")
            proof = json.loads(proof_path.read_bytes())
            if proof != json.loads((root / "independent-verification.json").read_bytes()):
                raise AssertionError("Independent numerical acceptance differs")
        receipt = dict(status="passed_complete_offline_reproduction", focused_tests=tests.testsRun,
            pinned_members=len(manifest), full_result_and_viewer_bytes_identical=True,
            independent_scalar_checks=proof["checks"], numerical_warnings_fatal=True,
            network_and_external_commands_blocked=True,
            archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
