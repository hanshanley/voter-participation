"""Offline complete public calibration/projection/simulation replay; no private refits."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import sys
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh offline replay directory")
    args.output.mkdir(parents=True)
    packet = args.output/"packet"
    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        if (len(names) != len(set(names)) or len(names) > 200 or
                sum(item.file_size for item in archive.infolist()) > 300*1024*1024 or
                any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names)):
            raise ValueError("Unexpected archive members")
        manifest = json.loads(archive.read("manifest.json"))
        if (manifest["contract"] != "participation.house_fixed_copula_complete_packet.v1"
                or set(names) != set(manifest["files"]) | {"manifest.json"} or len(manifest["output_files"]) != 60
                or manifest["original_persons_or_predictions_included"] is not False
                or manifest["historical_transport_validated"] is not False):
            raise ValueError("Incomplete or unqualified scientific packet")
        for name, metadata in manifest["files"].items():
            body = archive.read(name)
            if hashlib.sha256(body).hexdigest() != metadata["sha256"] or len(body) != metadata["bytes"]:
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
    sys.path.insert(0, str(packet/"code"))
    sys.argv = ["house_fixed_copula_public.py", "--sufficient", str(packet/"inputs/sufficient-scores.json"),
                "--reference", str(packet/"inputs/reference-concordance.json"),
                "--output", str(args.output/"source")]
    runpy.run_path(str(packet/"code/scripts/house_fixed_copula_public.py"), run_name="__main__")
    sys.argv = ["build_house_copula_profiles.py", "--source-summary", str(args.output/"source/summary.json"),
        "--priors", str(packet/"inputs/original-priors"), "--baseline-results", str(packet/"inputs/original-results"),
        "--baseline-viewer", str(packet/"inputs/original-viewer.json"), "--output", str(args.output/"current"),
        "--prepared-projections", str(packet/"inputs/current-profiles")]
    runpy.run_path(str(packet/"code/scripts/build_house_copula_profiles.py"), run_name="__main__")
    sys.argv = ["verify_house_copula_profiles.py", "--profiles", str(args.output/"current"),
        "--original-priors", str(packet/"inputs/original-priors"), "--baseline-results", str(packet/"inputs/original-results"),
        "--output", str(args.output/"independent-replay-verification.json")]
    runpy.run_path(str(packet/"code/scripts/verify_house_copula_profiles.py"), run_name="__main__")
    matched = {}
    for name in manifest["output_files"]:
        body = (args.output/name).read_bytes()
        if body != (packet/"outputs"/name).read_bytes():
            raise ValueError("Complete public replay differs: "+name)
        matched[name] = hashlib.sha256(body).hexdigest()
    projected = 0
    for name in names:
        if name.startswith("inputs/current-profiles/"):
            target = args.output/"current"/name.removeprefix("inputs/current-profiles/")
            if target.read_bytes() != (packet/name).read_bytes():
                raise ValueError("Source-only projection/decision differs")
            projected += 1
    report = dict(status="pass", output_files_matched=len(matched), outputs=matched,
        transformed_priors_and_decisions_matched=projected,
        archive_sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(), archive_members=len(names),
        network_and_external_commands_blocked=True, successful_private_fits_repeated=False,
        original_baseline_simulations_repeated=False, new_current_profile_simulations_reproduced=6,
        published_projections_consumed_not_recomputed=True,
        source_and_group_year_marginal_constraints_independently_rechecked=True,
        public_scores_replayed_from_permitted_sums_not_private_refits=True)
    (args.output/"reproduction.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({key: value for key, value in report.items() if key != "outputs"}), flush=True)


if __name__ == "__main__":
    main()
