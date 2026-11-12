"""Package or reproduce the complete narrow Alaska experiment using saved inputs."""

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
import zipfile


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def offline(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname",
                 "socket.sendto", "subprocess.Popen", "os.system"):
        raise PermissionError("Offline reproduction forbids network/external commands")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("package", "reproduce"))
    for key in ("inputs", "results", "output", "package"):
        parser.add_argument("--" + key, type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    if args.output is None or args.output.exists():
        raise ValueError("Use a fresh output")
    if args.mode == "reproduce":
        root = args.package.resolve()
        manifest = json.loads((root / "manifest.json").read_bytes())
        for name, expected in manifest["files"].items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("Unsafe member")
            body = (root / name).read_bytes()
            if dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()) != expected:
                raise ValueError("Changed packet member")
        sys.addaudithook(offline)
        for probe in (lambda: socket.getaddrinfo("example.invalid", 443),
                      lambda: subprocess.run([sys.executable, "-c", "pass"])):
            try:
                probe()
            except PermissionError:
                pass
            else:
                raise ValueError("Offline guard failed")
        os.environ["AK_SENATE_INPUTS"] = str(root / "inputs")
        sys.path.insert(0, str(root / "code"))
        tests = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover(
            str(root / "code/tests"), pattern="test_ak_senate_controls.py"))
        if not tests.wasSuccessful() or tests.testsRun != 5:
            raise ValueError("New tests failed")
        primary = module(root / "code/scripts/ak_senate_controls.py")
        verifier = module(root / "code/scripts/verify_ak_senate_controls.py")
        inputs = primary.load(root / "inputs")
        result = primary.build(*inputs)
        args.output.mkdir(parents=True)
        for name, body in primary.files(result, inputs[3]).items():
            if body != (root / "results" / name).read_bytes():
                raise ValueError("Complete query/result differs")
            (args.output / name).write_bytes(body)
        proof = verifier.verify(root / "inputs", args.output)
        if proof != json.loads((root / "checks/independent.json").read_bytes()):
            raise ValueError("Independent receipt differs")
        receipt = dict(status="passed_fresh_offline_Alaska_scope_experiment", tests_passed=5,
            independent=proof, every_result_query_byte_identical=True,
            network_and_external_commands_blocked=True, earlier_reductions_repeated=False)
        (args.output / "reproduction.json").write_bytes(primary.encoded(receipt))
        print(json.dumps(receipt, sort_keys=True))
        return
    root = Path(__file__).resolve().parents[1]
    primary = module(root / "scripts/ak_senate_controls.py")
    verifier = module(root / "scripts/verify_ak_senate_controls.py")
    proof = verifier.verify(args.inputs, args.results)
    if not args.commit or len(args.commit) != 40:
        raise ValueError("A complete source commit is required")
    frozen = json.loads((args.inputs / "manifest.json").read_bytes())
    members = {"inputs/" + name: (args.inputs / name).read_bytes() for name in ("manifest.json", *frozen)}
    for name in ("scripts/ak_senate_controls.py", "scripts/verify_ak_senate_controls.py",
                 "scripts/ak_senate_packet.py", "tests/test_ak_senate_controls.py"):
        members["code/" + name] = (root / name).read_bytes()
    result = json.loads((args.results / "complete-result.json").read_bytes())
    for name, body in primary.files(result, (args.inputs / "complete-prior-crosschecks.csv").read_bytes()).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed query export")
        members["results/" + name] = body
    members["checks/independent.json"] = primary.encoded(proof)
    members["README.txt"] = (
        "COMPLETE ALASKA SENATE NATIVE ROLE ACCOUNTING EXPERIMENT\n\n"
        "The held Nov8 snapshot reports73.9%, native round1 and null registration.\n"
        "Its top candidate parent214246 differs from nested state213733 selections.\n"
        "30boroughs+explicitOverseas match all4top-parent candidates;40HouseDistricts\n"
        "+Overseas match the nested state instead. Both original parents survive.\n"
        "The normalized D-R margins are-2.039983099 vs-2.003017137 percentage points.\n"
        "This is internal source arithmetic, NOT independent outcome, legal geography,\n"
        "matched timing/round, finalRCV, ballots, turnout, eligibility or a model fit.\n"
        "Native district/borough roles are never mixed or allocated to counties.\n\n"
        "All234control decisions retain every old field;229old accepted controls are\n"
        "unchanged and4AK controls gain only an explicit noncounty accounting scope.\n"
        "ME882writeins vs0county remains held. All14742oldcrosschecks/215differences,\n"
        "entire accepted identifier science/all34492rows/six derived IDs/one additional\n"
        "difference, original AK factual JSON, safe receipts, policy, code and tests\n"
        "are included. No acquisition session headers or compiled publisher apps.\n"
        "The initial district-to-top-parent hypothesis was rejected, not repaired;\n"
        "the corrected policy enumerates both native parents and all six scopes.\n\n"
        "All288native AK rows,24candidate/scope checks,6margin diagnostics and every\n"
        "complete query/result are included. Five tests/4253independent SQL checks.\n"
        "Python3.9+ standard library only, from this extracted package:\n"
        "python3 -Werror code/scripts/ak_senate_packet.py reproduce --package . "
        "--output /fresh/path\n"
        "Network/external commands are blocked; every new byte is reproduced.\n"
        "No old acquisition/reduction/refit, source replacement or frontend activation.\n"
    ).encode()
    manifest = dict(contract="participation.complete_ak_senate_scope.v1", source_commit=args.commit,
        complete_query_download=True, files={name: primary.pin(body) for name, body in sorted(members.items())})
    members["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name in members:
        if name.startswith(("results/", "checks/")) or name == "manifest.json":
            (args.output / Path(name).name).write_bytes(members[name])
    receipt = dict(source_commit=args.commit, members=len(members),
        archive=primary.pin((args.output / "complete-analysis.zip").read_bytes()), independent=proof)
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
