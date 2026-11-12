"""Verify and replay complete permitted four-axis score/forecast/simulation outputs."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import sys
import zipfile

OUTPUTS = {"fold-scores.csv", "scores.csv", "synthetic-forecasts.csv", "source-outcomes.csv",
    "source-predictive-simulations.csv", "fold-composition-stress.csv", "pair-margin-diagnostics.csv",
    "coarse-reference-decisions.json", "summary.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete replay directory")
    args.output.mkdir(parents=True)
    packet = args.output/"packet"
    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        if (len(names) != len(set(names)) or len(names) > 80
                or sum(item.file_size for item in archive.infolist()) > 128*1024*1024
                or any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names)):
            raise ValueError("Unexpected archive members")
        manifest = json.loads(archive.read("manifest.json"))
        if (manifest["contract"] != "participation.house_four_axis_packet.v1"
                or set(names) != set(manifest["files"]) | {"manifest.json"} or set(manifest["output_files"]) != OUTPUTS
                or manifest["original_persons_predictions_or_fine_cells_included"]
                or manifest["population_or2026_transport_validated"] or manifest["current_models_or_website_changed"]):
            raise ValueError("Incomplete or unqualified scientific packet")
        for name, metadata in manifest["files"].items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Archive member checksum mismatch")
        for name in names:
            target = packet/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))

    def offline(event, arguments):
        if event.startswith("socket.") or event in {
                "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
            raise RuntimeError("Network and external commands prohibited during replay")

    sys.addaudithook(offline)
    sys.path.insert(0, str(packet/"code/scripts"))
    sys.argv = ["house_four_axis_public.py", "--sufficient", str(packet/"inputs/sufficient-scores.json"),
                "--output", str(args.output/"reproduced")]
    runpy.run_path(str(packet/"code/scripts/house_four_axis_public.py"), run_name="__main__")
    verified = {}
    for name in sorted(OUTPUTS):
        body = (args.output/"reproduced"/name).read_bytes()
        if body != (packet/"outputs"/name).read_bytes():
            raise ValueError("Complete public replay differs: "+name)
        verified[name] = hashlib.sha256(body).hexdigest()
    proof = dict(status="pass", output_files_matched=len(verified), outputs=verified,
        archive_sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(), archive_members=len(names),
        network_and_external_commands_blocked=True, successful_source_fits_repeated=False,
        baseline_or_current2026_simulations_repeated=False, source_predictive_draws_reproduced=600000,
        private_fits_replayed=False)
    (args.output/"reproduction.json").write_text(json.dumps(proof, indent=2, sort_keys=True)+"\n")
    print(json.dumps({key: value for key, value in proof.items() if key != "outputs"}), flush=True)


if __name__ == "__main__":
    main()
