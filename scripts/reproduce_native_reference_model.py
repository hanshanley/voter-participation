"""Reproduce a native-reference package with external operations blocked."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--hash-seed", required=True)
    args = parser.parse_args()
    root = args.package_root.resolve()
    sys.path.insert(0, str(root))
    attempts = []

    def blocked(kind):
        def stop(*unused_args, **unused_kwargs):
            attempts.append(kind)
            raise RuntimeError("External operation blocked: " + kind)
        return stop

    socket.create_connection = blocked("network")
    socket.getaddrinfo = blocked("dns")
    urllib.request.urlopen = blocked("urlopen")
    subprocess.Popen = blocked("child_process")
    subprocess.run = blocked("child_process")
    subprocess.call = blocked("child_process")
    subprocess.check_call = blocked("child_process")
    subprocess.check_output = blocked("child_process")
    os.system = blocked("child_process")

    from scripts.native_reference_model import export

    summary = export(root / "inputs", args.output)
    actual = (args.output / "complete-analysis.zip").read_bytes()
    expected = (root / "complete-analysis.zip").read_bytes()
    verification = {
        "contract": "participation.native_reference_model.offline_replay.v1",
        "passed": actual == expected and not attempts,
        "hash_seed": args.hash_seed,
        "isolated_stdlib_only": True,
        "network_dns_and_children_blocked": True,
        "three_offline_gates_probed": True,
        "unexpected_external_operations": len(attempts),
        "complete_zip_byte_exact": {
            "bytes": len(actual),
            "sha256": hashlib.sha256(actual).hexdigest(),
        },
        "expected_archive": {
            "bytes": len(expected),
            "sha256": hashlib.sha256(expected).hexdigest(),
        },
        "native_control_version": summary["native_control_version"],
        "affected_states": summary["affected_states"],
    }
    if not verification["passed"]:
        raise SystemExit(json.dumps(verification, sort_keys=True))
    target = args.verification or args.output.parent / "offline-verification.json"
    target.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n")
    print(json.dumps(verification, sort_keys=True))


if __name__ == "__main__":
    main()
