"""Package every spatial query, offline map, input and both entire predecessor packets."""

import argparse
import importlib.util
import json
from pathlib import Path
import zipfile


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "results", "native-science", "runtime-science", "browser-proof", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    primary = module(root / "scripts/louisiana_early_spatial.py")
    verifier = module(root / "scripts/verify_louisiana_early_spatial.py")
    data = primary.load_inputs(args.inputs)
    result, geometry = primary.build(data)
    proof = verifier.verify(args.inputs, args.results)
    if args.output.exists() or len(args.commit) != 40:
        raise ValueError("Use a fresh output and full source commit")
    inputs = json.loads((args.inputs / "manifest.json").read_bytes())
    members = {"inputs/" + name: args.inputs / name for name in ("manifest.json", *inputs["files"])}
    for name, path in (("complete-native-science.zip", args.native_science),
            ("complete-runtime-science.zip", args.runtime_science)):
        if primary.file_pin(path) != inputs["complete_predecessors"][name]:
            raise ValueError("Missing or changed entire accepted predecessor")
        members["predecessors/" + name] = path
    code = ("scripts/freeze_louisiana_early_spatial.py", "scripts/louisiana_early_spatial.py",
        "scripts/verify_louisiana_early_spatial.py", "scripts/package_louisiana_early_spatial.py",
        "scripts/reproduce_louisiana_early_spatial.py", "scripts/check_louisiana_early_spatial_browser.py",
        "scripts/templates/louisiana-early-group-map.html", "tests/test_louisiana_early_spatial.py")
    for name in code:
        members["code/" + name] = root / name
    for name, body in primary.result_files(result, geometry).items():
        if body != (args.results / name).read_bytes():
            raise ValueError("Changed complete spatial query/map")
        members["results/" + name] = args.results / name
    browser = json.loads(args.browser_proof.read_bytes())
    if (browser["status"] != "passed_offline_louisiana_group_map" or browser["screens"] != ["desktop", "phone"]
            or browser["map_pin"] != primary.file_pin(args.results / "louisiana-early-group-map.html")):
        raise ValueError("Missing real offline browser acceptance")
    additions = {
        "checks/independent-verification.json": primary.encoded(proof),
        "checks/browser-acceptance.json": args.browser_proof.read_bytes(),
        "README.txt": (
            "COMPLETE LOUISIANA EARLY-REPORT PARISH GROUP MAPS\n\n"
            "Open results/louisiana-early-group-map.html locally: 64 clickable/keyboard\n"
            "parishes, seven native race/sex/method choices and count/share views,\n"
            "with no network dependency. Full GeoJSON and gzip, 64 name bindings,\n"
            "flat numeric count/report-share fields usable directly in GIS (binary\n"
            "float shares for plotting; original exact decimal strings retained),\n"
            "128 native/provider comparisons, 448 COPIED accepted compositions,\n"
            "256 COPIED margin accounts and all reference/state decisions are included.\n\n"
            "Both ENTIRE accepted predecessor scientific archives are included, not\n"
            "manifests or selected rows: full official two-page PDF/text/1040cells/\n"
            "all455source compositions and the 232295601-byte count/reference archive\n"
            "with its entire predecessors. New sufficient full LA shard, both full\n"
            "runtime indexes/descriptors, unchanged 1288586-byte reference, maintained\n"
            "code/tests/template, browser and independent evidence, ALL results are here.\n\n"
            "124 numeric pairs agree; four official-minus-provider differences remain:\n"
            "Bossier ABS -1; East Feliciana INPER +1; Jefferson ABS +4; Lafayette ABS +1.\n"
            "Existing provider early/returned frames were already64/64. This supplies\n"
            "no new count coverage or live-source replacement. Numeric matches do NOT\n"
            "establish independent validation, common lineage or equal population,\n"
            "method/processing semantics or clocks. ABS is NOT relabelled mail-returned.\n"
            "Official print Nov10 2026 03:10:06AM, timezone unknown, filter Jan1 1900\n"
            "to Nov9 2026; provider Nov3 label separately unqualified. Source filter\n"
            "is not observed voting period. Reasons for differences stay unknown.\n\n"
            "Native report VOTES536190, INPER448588, ABS87602. Shares use OWN report\n"
            "VOTES, not registrations or classified-sex totals. Sex residual278 and\n"
            "all original zeros preserved. Race/sex/method are separate margins, not\n"
            "joints or harmonized CPS/resident groups. No group turnout, full-election\n"
            "ballots, unique people, staying-home histories, new CIs, private records,\n"
            "repaired geometry or certified election precinct boundaries. Source\n"
            "codes01-64 are NOT FIPS; unique native names bind to the existing\n"
            "unsimplified2026Census parish context. State parent is not a65th feature.\n\n"
            "Python3.9+ standard-library offline reproduction (fresh path):\n"
            "python3 -Werror code/scripts/reproduce_louisiana_early_spatial.py "
            "--package . --output /fresh/path\n"
            "Runs eight focused tests, independent NEW spatial/comparison verification\n"
            "and all eleven full query/map bytes with network/external commands blocked.\n"
            "Does NOT reacquire originals, re-extract PDFs, rerun old reductions or\n"
            "rebuild/promote live website/catalog/models. Browser QA additionally uses\n"
            "already-installed Playwright/Chromium; no browser dependency for reproduction.\n"
        ).encode(),
    }
    manifest = dict(contract="participation.complete_louisiana_early_spatial.v1",
        source_commit=args.commit, complete_query_download=True,
        whole_predecessor_archives=True, files={
            **{name: primary.file_pin(path) for name, path in sorted(members.items())},
            **{name: primary.pin(body) for name, body in sorted(additions.items())}})
    additions["manifest.json"] = primary.encoded(manifest)
    args.output.mkdir(parents=True)
    with zipfile.ZipFile(args.output / "complete-analysis.zip", "x", zipfile.ZIP_DEFLATED,
            compresslevel=9, allowZip64=True) as archive:
        for name in sorted(set(members) | set(additions)):
            info = zipfile.ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            with archive.open(info, "w", force_zip64=True) as destination:
                if name in additions:
                    destination.write(additions[name])
                else:
                    with members[name].open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            destination.write(chunk)
    for name, body in additions.items():
        (args.output / Path(name).name).write_bytes(body)
    for name in primary.result_files(result, geometry):
        (args.output / name).write_bytes((args.results / name).read_bytes())
    receipt = dict(status="complete_louisiana_spatial_packet_prepared", source_commit=args.commit,
        members=len(manifest["files"]) + 1, archive=primary.file_pin(args.output / "complete-analysis.zip"),
        summary=result["summary"], independent=proof, whole_predecessors=inputs["complete_predecessors"])
    (args.output / "package-receipt.json").write_bytes(primary.encoded(receipt))
    print(json.dumps(receipt, sort_keys=True))
