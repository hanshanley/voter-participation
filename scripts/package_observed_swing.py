#!/usr/bin/env python3
"""Package full return references, both complete predecessor analyses and exact reproduction."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from observed_swing import VERSION, build, encoded

ROOT = Path(__file__).resolve().parents[1]


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--model-archive", type=Path, required=True)
    parser.add_argument("--house-archive", type=Path, required=True)
    parser.add_argument("--assets-directory", type=Path, required=True)
    args = parser.parse_args()
    if args.assets_directory.exists() or (args.data_directory / "download.json").exists():
        raise ValueError("Refuse to replace an immutable numerical package")
    viewer = encoded(build(args.data_directory / "inputs"))
    assert viewer == (args.data_directory / "viewer-data.json").read_bytes()
    with zipfile.ZipFile(args.model_archive) as archive:
        assert archive.read("results/viewer-data.json") == (args.data_directory / "inputs/original-viewer.json").read_bytes()
        assert archive.read("inputs/model-inputs.json") == (args.data_directory / "inputs/model-inputs.json").read_bytes()
    with zipfile.ZipFile(args.house_archive) as archive:
        assert archive.read("county-panel.csv") == (args.data_directory / "inputs/house-county-panel.csv").read_bytes()
    prefix = f"data/return-attribution/{VERSION}/"
    members = {prefix + "inputs/" + path.name: path.read_bytes()
               for path in sorted((args.data_directory / "inputs").iterdir())}
    members.update({
        prefix + "viewer-data.json": viewer,
        "original-analysis/complete-model-analysis.zip": args.model_archive.read_bytes(),
        "original-analysis/complete-house-analysis.zip": args.house_archive.read_bytes(),
        "requirements.txt": b"openpyxl==3.1.5\n",
    })
    for name in ("observed_swing.py", "package_observed_swing.py"):
        members["scripts/" + name] = (ROOT / "scripts" / name).read_bytes()
    members["tests/test_observed_swing.py"] = (ROOT / "tests/test_observed_swing.py").read_bytes()
    members["README.txt"] = (
        "REPORTED SAME-OFFICE SWING AND UNCHANGED CONDITIONAL MODEL CONTRIBUTIONS\n\n"
        "Reported total = switching + modeled nonparticipation + other/unallocated.\n"
        "All seven original model terms are unchanged. A separate baseline alignment\n"
        "bridges the recalled presidential survey baseline to qualified earlier returns.\n"
        "Neither this gap nor the grouped remainder is attributed to one mechanism.\n"
        "Margins are 100*(D-R)/(D+R), not vote shares or turnout. Reporting is not necessarily final.\n"
        "Unavailable comparisons stay unknown. House county identity/control conflicts,\n"
        "unresolved Senate seats/specials and ambiguous party affiliations are not fitted away.\n"
        "Governor comparisons remain their supplied matched county frames, not certified statewide.\n\n"
        "This packet includes the ENTIRE original 113-model/1017-scenario analysis ZIP,\n"
        "the ENTIRE House panel analysis ZIP with all six sufficient native aggregate inputs,\n"
        "the FULL FEC 2020 workbook, FULL Census Gazetteer ZIP, all comparison inputs,\n"
        "source pins, code, tests and checksums. No private respondents/fine cells or credentials.\n\n"
        "With Python and the declared openpyxl dependency already available:\n"
        "  python reproduce.py --output /path/to/new-directory\n"
        "This verifies every member, fully rebuilds both predecessor numerical analyses,\n"
        "byte-compares their reused inputs, rebuilds every comparison and runs all correction tests.\n"
        "It uses no network. Prior immutable releases and downloads are not replaced.\n"
    ).encode()
    members["reproduce.py"] = b'''import argparse,hashlib,json,pathlib,subprocess,sys,zipfile
root=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
if a.output.exists():raise ValueError("Output must be new")
for name,pin in json.loads((root/"manifest.json").read_bytes())["files"].items():
 body=(root/name).read_bytes()
 assert len(body)==pin["bytes"] and hashlib.sha256(body).hexdigest()==pin["sha256"],name
a.output.mkdir(parents=True)
for kind in ("model","house"):
 with zipfile.ZipFile(root/f"original-analysis/complete-{kind}-analysis.zip") as archive:
  archive.extractall(a.output/kind)
model=a.output/"model";house=a.output/"house"
subprocess.run([sys.executable,str(model/"reproduce.py"),"--output",str(a.output/"model-results")],check=True)
subprocess.run([sys.executable,"-m","scripts.house_panel","--inputs",".","--output","reproduced"],cwd=house,check=True)
inputs=root/"data/return-attribution/20261110-02/inputs"
assert (house/"reproduced/county-panel.csv").read_bytes()==(inputs/"house-county-panel.csv").read_bytes()
assert (model/"inputs/model-inputs.json").read_bytes()==(inputs/"model-inputs.json").read_bytes()
assert (a.output/"model-results/viewer-data.json").read_bytes()==(inputs/"original-viewer.json").read_bytes()
subprocess.run([sys.executable,str(root/"scripts/observed_swing.py"),"--inputs",str(inputs),
 "--output",str(a.output/"viewer-data.json")],check=True)
assert (a.output/"viewer-data.json").read_bytes()==(root/"data/return-attribution/20261110-02/viewer-data.json").read_bytes()
subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p","test_observed_swing.py"],cwd=root,check=True)
print("PASS_exact_113_unchanged_models_all_scenarios_full_house_panel_and_reported_comparisons")
'''
    members["manifest.json"] = encoded(dict(version=VERSION,
        files={name: pin(body) for name, body in sorted(members.items())}))
    args.assets_directory.mkdir(parents=True)
    destination = args.assets_directory / "complete-analysis.zip"
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    data = json.loads(viewer)
    receipt = dict(url=data["complete_download_url"], **pin(destination.read_bytes()),
        members=len(members), models=len(data["rows"]),
        qualified_reported_comparisons=sum(row["reported_comparison"]["status"] == "reported_source_comparison"
                                          for row in data["rows"]),
        full_original_model_and_house_packets=True, full_fec_workbook=True,
        full_gazetteer_original=True, metadata_only=False)
    (args.data_directory / "download.json").write_bytes(encoded(receipt))
    for name, body in (("viewer-data.json", viewer), ("download.json", encoded(receipt))):
        (args.assets_directory / name).write_bytes(body)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
