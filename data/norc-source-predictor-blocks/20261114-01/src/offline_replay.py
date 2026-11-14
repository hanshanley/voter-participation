"""Replay repaired facts while probing selected blocked Python APIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess

import replay_repaired_facts as replay


def blocked(*_args, **_kwargs):
    raise RuntimeError("selected Python external-call API blocked by replay harness")


def probe(name, function):
    try:
        function()
    except RuntimeError as error:
        return {"probe": name, "python_api_blocked": True, "error": str(error)}
    raise ValueError(name + " unexpectedly succeeded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    socket.socket = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    subprocess.Popen = blocked
    subprocess.run = blocked
    subprocess.call = blocked
    subprocess.check_call = blocked
    subprocess.check_output = blocked
    probes = [
        probe("socket.socket", lambda: socket.socket()),
        probe("socket.getaddrinfo", lambda: socket.getaddrinfo("example.invalid", 443)),
        probe("subprocess.run", lambda: subprocess.run(["false"])),
    ]
    summary = replay.render(json.loads(args.facts.read_bytes()), args.output)
    receipt = {
        "scope": "selected_python_api_interposition_not_os_sandbox",
        "os_level_containment_claimed": False,
        "external_commands_required": False,
        "all_selected_python_api_probes_blocked": all(
            row["python_api_blocked"] for row in probes
        ),
        "probes": probes,
    }
    (args.output / "python-api-probes.json").write_bytes(replay.encoded(receipt))
    print(json.dumps({"summary": summary, "probe_receipt": receipt}, sort_keys=True))


if __name__ == "__main__":
    main()
