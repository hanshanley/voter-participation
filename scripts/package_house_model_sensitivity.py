"""Package and replay the complete public-aggregate sensitivity projection."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest
import zipfile


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()


def package(code, inputs, queries, output):
    if output.exists():
        raise ValueError("Never overwrite a source-pinned scientific package")
    members = {}
    for folder, root, names in (
        ("code", code, ("scripts/house_model_sensitivity.py",
            "scripts/package_house_model_sensitivity.py", "tests/test_house_model_sensitivity.py")),
        ("inputs", inputs, ("inputs.json", "viewer-original.json", "viewer-attenuated.json", "viewer-full.json")),
        ("queries", queries, ("sensitivity.json", "sensitivity.json.gz",
            "complete-nine-variant-query.csv", "manifest.json")),
    ):
        for name in names:
            members[folder+"/"+name] = (root/name).read_bytes()
    members["REPRODUCE.txt"] = (
        "PUBLIC FITTED-AGGREGATE PROJECTION REPLAY ONLY; NOT SOURCE-MODEL FITTING.\n"
        "All three original immutable public aggregate profile bodies are included.\n"
        "No private respondents, weights, new fits, administrative counts or local allocations.\n"
        "Ranges cover nine existing family/profile combinations, not confidence intervals\n"
        "or all survey, transport, accounting-frame or endpoint uncertainty.\n"
        "Every state/group/metric/variant withholding decision is in the complete CSV.\n"
        "Extract this ZIP into a new directory, then run:\n"
        "python3 -I -S code/scripts/package_house_model_sensitivity.py --replay --directory .\n"
        "The replay verifies every member, blocks network/DNS/child processes,\n"
        "runs the focused tests and reproduces all four outputs byte-for-byte.\n"
    ).encode()
    members["checksums.json"] = encoded({name: pin(body) for name, body in sorted(members.items())})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
    return dict(archive=pin(output.read_bytes()), members=len(members))


def replay(directory):
    directory = directory.resolve()
    manifest = json.loads((directory/"checksums.json").read_bytes())
    actual = {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}
    if actual != set(manifest) | {"checksums.json"}:
        raise ValueError("Replay requires the exact complete package in a fresh directory")
    for name, expected in manifest.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or pin((directory/path).read_bytes()) != expected:
            raise ValueError("Package member differs: "+name)
    attempts = []

    def blocked(*unused, **kwargs):
        attempts.append("blocked")
        raise RuntimeError("External operation blocked")

    socket.socket = socket.create_connection = socket.getaddrinfo = subprocess.Popen = blocked
    for operation in (socket.socket, socket.getaddrinfo, subprocess.Popen):
        try:
            operation()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Offline gate failed")
    assert len(attempts) == 3
    attempts.clear()
    sys.path.insert(0, str(directory/"code"))
    suite = unittest.defaultTestLoader.discover(str(directory/"code/tests"),
        pattern="test_house_model_sensitivity.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful() and not result.skipped
    from scripts.house_model_sensitivity import build
    summary = build(directory/"inputs", directory/"reproduced")
    files = sorted(path.name for path in (directory/"queries").iterdir())
    for name in files:
        assert (directory/"queries"/name).read_bytes() == (directory/"reproduced"/name).read_bytes(), name
    assert not attempts
    proof = dict(passed=True, tests=result.testsRun, all_member_pins_verified=len(manifest),
        complete_output_files=len(files), all_output_bytes_exact=True,
        isolated_stdlib_only=sys.flags.isolated == sys.flags.no_site == 1,
        network_dns_and_children_blocked=True, three_gates_probed=True,
        unexpected_external_operations=0, source_fits_reproduced=False,
        private_respondents_included=False, summary=summary)
    (directory/"offline-verification.json").write_bytes(encoded(proof))
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--code", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.replay:
        replay(args.directory)
    else:
        print(json.dumps(package(args.code, args.inputs, args.queries, args.output), sort_keys=True))
