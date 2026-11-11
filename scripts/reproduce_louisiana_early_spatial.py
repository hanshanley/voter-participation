"""Reproduce the new complete spatial/map query without repeating predecessor science."""

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
        raise PermissionError("Offline reproduction forbids network/external commands")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.package.resolve(), args.output.resolve()
    if output.exists():
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
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe member path")
        path, digest = root / name, hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if dict(bytes=path.stat().st_size, sha256=digest.hexdigest()) != expected:
            raise ValueError("Changed complete scientific member")
    os.environ["LOUISIANA_SPATIAL_INPUTS"] = str(root / "inputs")
    sys.path.insert(0, str(root / "code"))
    suite = unittest.defaultTestLoader.discover(str(root / "code/tests"), pattern="test_louisiana_early_spatial.py")
    tests = unittest.TextTestRunner(verbosity=1).run(suite)
    if not tests.wasSuccessful() or tests.testsRun != 8:
        raise ValueError("Spatial regression tests failed")
    primary = module(root / "code/scripts/louisiana_early_spatial.py")
    verifier = module(root / "code/scripts/verify_louisiana_early_spatial.py")
    result, geojson = primary.build(primary.load_inputs(root / "inputs"))
    output.mkdir(parents=True)
    files = primary.result_files(result, geojson)
    for name, body in files.items():
        if body != (root / "results" / name).read_bytes():
            raise ValueError("Full spatial query/map output byte differs")
        (output / name).write_bytes(body)
    proof = verifier.verify(root / "inputs", output)
    if proof != json.loads((root / "checks/independent-verification.json").read_bytes()):
        raise ValueError("Independent numerical receipt differs")
    receipt = dict(status="passed_fresh_offline_louisiana_spatial", tests_passed=tests.testsRun,
        complete_result_query_map_files=len(files), all_full_output_bytes_identical=True,
        network_and_external_commands_blocked=True, independent=proof,
        source_commit=manifest["source_commit"], original_acquisitions_or_reductions_repeated=False)
    (output / "reproduction.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))
