"""Reproduce the new experiment from complete cached inputs with networking blocked."""

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
        raise ValueError("Use a fresh offline reproduction receipt")
    with tempfile.TemporaryDirectory(prefix="adaptive-persistence-offline-") as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if len(archive.namelist()) != len(manifest) + 1 \
                    or set(archive.namelist()) != set(manifest) | {"manifest.json"}:
                raise ValueError("Incomplete or duplicate packet members")
            for name, pin in manifest.items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe packet member")
                body = archive.read(name)
                if len(body) != pin["bytes"] or hashlib.sha256(body).hexdigest() != pin["sha256"]:
                    raise ValueError("Pinned packet member differs")
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
        socket.socket = socket.create_connection = blocked
        subprocess.Popen = subprocess.run = blocked
        os.system = os.popen = blocked
        for name in dir(os):
            if name.startswith(("exec", "spawn")):
                setattr(os, name, blocked)
        warnings.simplefilter("error")
        sys.path.insert(0, str(root))
        sys.path.insert(0, str(root / "scripts"))
        with contextlib.redirect_stdout(io.StringIO()):
            suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_adaptive_persistence.py")
            tests = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            if not tests.wasSuccessful():
                raise AssertionError("Packaged focused tests failed: " + repr(tests.errors + tests.failures))
            namespace = runpy.run_path(str(root / "scripts/package_adaptive_persistence.py"))
            previous = root / "inputs/accepted-simulation-complete.zip"
            if hashlib.sha256(previous.read_bytes()).hexdigest() != namespace["PREDECESSOR_SHA256"]:
                raise ValueError("Accepted predecessor differs")
            with zipfile.ZipFile(previous) as archive:
                old_manifest = json.loads(archive.read("manifest.json"))
                if len(archive.namelist()) != len(old_manifest) + 1 \
                        or set(archive.namelist()) != set(old_manifest) | {"manifest.json"}:
                    raise ValueError("Incomplete predecessor packet")
                for name, pin in old_manifest.items():
                    body = archive.read(name)
                    if len(body) != pin["bytes"] or hashlib.sha256(body).hexdigest() != pin["sha256"]:
                        raise ValueError("A complete predecessor member differs")
                simulation = root / "accepted-scenarios.json"
                simulation.write_bytes(archive.read("complete-scenarios.json"))
            reproduced = root / "reproduced.json"
            spec = root / "inputs/spec.json"
            sys.argv = ["adaptive_persistence.py", "--simulation", str(simulation),
                "--spec", str(spec), "--output", str(reproduced)]
            runpy.run_path(str(root / "scripts/adaptive_persistence.py"), run_name="__main__")
            if reproduced.read_bytes() != (root / "complete-results.json").read_bytes():
                raise AssertionError("Complete new experiment bytes differ")
            tables = namespace["query_members"](json.loads(reproduced.read_bytes()))
            for name, body in tables.items():
                if body != (root / name).read_bytes():
                    raise AssertionError("Complete query export differs: " + name)
            proof_path = root / "reproduced-verification.json"
            sys.argv = ["verify_adaptive_persistence.py", "--simulation", str(simulation),
                "--spec", str(spec), "--result", str(reproduced), "--proof", str(proof_path)]
            runpy.run_path(str(root / "scripts/verify_adaptive_persistence.py"), run_name="__main__")
            proof = json.loads(proof_path.read_bytes())
            if proof != json.loads((root / "independent-verification.json").read_bytes()):
                raise AssertionError("Independent numerical verification differs")
        receipt = dict(status="passed_complete_adaptive_offline_reproduction",
            focused_tests=tests.testsRun, pinned_members=len(manifest),
            full_predecessor_members_verified=len(old_manifest) + 1,
            full_result_and_all_query_export_bytes_identical=True,
            independent_checks=proof["checks"], numerical_warnings_fatal=True,
            network_and_external_commands_blocked=True,
            original_entropy_fits_or_seed_draws_repeated=False,
            archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
