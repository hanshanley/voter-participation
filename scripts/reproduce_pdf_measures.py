"""Replay complete numerical PDF queries and controls from full factual grids."""

import argparse
import gzip
import json
from pathlib import Path
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded, pin
from scripts.native_reconciliation import reconcile
from scripts.pdf_control_checks import build
from scripts.pdf_group_queries import build as group_queries
from scripts.pdf_measure_queries import csv_body, queries


def replay(grids, group_recipe=None):
    complete = queries(grids)
    controls = build(grids) if group_recipe is None else group_queries(grids, group_recipe)
    controls["reconciliation"] = reconcile(controls["queries"], controls["checks"])
    return {
        "complete-queries.json.gz": gzip.compress(encoded(complete), mtime=0),
        "complete-queries.csv.gz": gzip.compress(csv_body(complete), mtime=0),
        "complete-controls.json": encoded(controls),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--group-recipe", type=Path)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh offline replay output")
    attempts = []
    def denied(*unused, **keywords):
        attempts.append("network_dns_or_child")
        raise RuntimeError("Offline numerical replay forbids network, DNS and child commands")
    socket.socket = socket.create_connection = socket.getaddrinfo = subprocess.Popen = denied
    for action in (socket.socket, socket.getaddrinfo, subprocess.Popen):
        try:
            action()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Offline gate probe failed")
    if len(attempts) != 3:
        raise RuntimeError("Offline gate probes differ")
    attempts.clear()
    body = args.grids.read_bytes()
    if args.grids.suffix == ".gz":
        body = gzip.decompress(body)
    recipe = json.loads(args.group_recipe.read_bytes()) if args.group_recipe else None
    outputs = replay(json.loads(body), recipe)
    args.output.mkdir(parents=True)
    for name, body in outputs.items():
        expected = (args.expected / name).read_bytes()
        if body != expected:
            raise ValueError("Full numerical output differs: " + name)
        (args.output / name).write_bytes(body)
    if attempts:
        raise RuntimeError("Unexpected offline replay I/O attempt")
    proof = dict(passed=True, complete_outputs={name: pin(body) for name, body in outputs.items()},
        network_dns_and_child_gates_probed=3, unexpected_attempts=attempts,
        starts_from_complete_factual_grids_not_original_template_reextraction=True)
    (args.output / "verification.json").write_bytes(encoded(proof))
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
