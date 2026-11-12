"""Verify and numerically replay the complete public House diagnostic without private cases."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import sys
import zipfile


OUTPUTS = {"source-concordance.json", "query-decisions.csv", "pooled-joints.csv",
           "source-comparison.csv", "summary.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh offline replay directory")
    args.output.mkdir(parents=True)
    packet = args.output / "packet"
    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        if (len(names) != len(set(names)) or len(names) > 100 or
                sum(item.file_size for item in archive.infolist()) > 32 * 1024 * 1024 or
                any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names)):
            raise ValueError("Unexpected archive members")
        manifest = json.loads(archive.read("manifest.json"))
        if set(names) != set(manifest["files"]) | {"manifest.json"} or set(manifest["output_files"]) != OUTPUTS:
            raise ValueError("Incomplete full packet manifest")
        for name, metadata in manifest["files"].items():
            body = archive.read(name)
            if hashlib.sha256(body).hexdigest() != metadata["sha256"] or len(body) != metadata["bytes"]:
                raise ValueError("Packet member checksum mismatch")
        for name in names:
            path = packet / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))

    def offline(event, arguments):
        if event.startswith("socket.") or event in {
                "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
            raise RuntimeError("Network and external commands prohibited during public replay")

    sys.addaudithook(offline)
    sys.argv = ["house_panel_public.py", "--inputs", str(packet / "inputs/sufficient-coarse-inputs.json"),
                "--output", str(args.output / "reproduced")]
    runpy.run_path(str(packet / "code/scripts/house_panel_public.py"), run_name="__main__")
    matched = {}
    for name in sorted(OUTPUTS):
        actual = (args.output / "reproduced" / name).read_bytes()
        if actual != (packet / "outputs" / name).read_bytes():
            raise ValueError("Public numerical replay differs")
        matched[name] = hashlib.sha256(actual).hexdigest()
    report = dict(status="pass", output_files_matched=len(matched), outputs=matched,
                  archive_sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                  archive_members=len(names), network_and_external_commands_blocked=True,
                  private_extraction_or_model_fits_repeated=False)
    (args.output / "reproduction.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in
                      ("status", "output_files_matched", "archive_members", "network_and_external_commands_blocked")}))


if __name__ == "__main__":
    main()
