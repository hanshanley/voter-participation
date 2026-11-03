"""Restore immutable raw aggregate archives from this repository's data release."""

import hashlib
import json
import subprocess

from scripts.download import ROOT

TAG = "data-snapshot-2026-11-03"
REPO = "hanshanley/voter-participation"


def main():
    manifest = json.loads((ROOT / "data/sources.json").read_text())
    for source in manifest["sources"]:
        path = ROOT / source["path"]
        if source["kind"] not in {
            "nc_history", "nc_registration", "nc_geometry", "state_geometry", "boundary_catalog",
        }:
            continue
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["gh", "release", "download", TAG, "--repo", REPO,
                 "--pattern", path.name, "--dir", str(path.parent)],
                check=True,
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != source["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}. Existing file has not been overwritten.")
        print(f"verified {source['path']}", flush=True)


if __name__ == "__main__":
    main()
