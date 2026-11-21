"""Refresh the complete Massachusetts historical atlas independently of current returns."""

import argparse
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from scripts import massachusetts_ballot_canvass as canvass
from scripts import massachusetts_municipality_map as municipalities
from scripts import massachusetts_precinct_reference as precincts
from scripts.automatic_runtime import CODE_PATHS, ROOT, archive_bytes, offline, read, relative
from scripts.participation_intake.contract import digest, encoded, pin, utc_now
from scripts.participation_intake.publisher import GitPublisher
from scripts.supported_analytical_release import csv_bytes


REPOSITORY = "hanshanley/voter-participation"
REF = "ma-historical-data"
CONTRACT = "participation.massachusetts_historical_atlas.v1"
PENDING = "pending.json"
YEARS = (2020, 2022, 2024)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}
CROSSWALK = "2022_gaz_cousubs_25.txt"
TIGER = "tl_2022_25_cousub.zip"
REFERENCE = ROOT / "data/results-intake/massachusetts-historical-reference"
MODULES = {*CODE_PATHS, "massachusetts_historical_release.py", "massachusetts_municipality_map.py",
           "massachusetts_precinct_reference.py"}


def collect(primary, acquire):
    primary.mkdir()
    controls = {}
    for year in YEARS:
        for contest in canvass.PAIRS[year]:
            page_url = canvass.BASE + f"view/{contest}/"
            body, _ = acquire(page_url)
            facts = canvass.page(body, year=year, contest=contest)
            original, _ = acquire(facts["csv_url"])
            (primary / f"{year}-{contest}.csv").write_bytes(original)
            controls[contest] = {"facts": facts, "page_pin": pin(body), "csv_pin": pin(original)}
    for file in (CROSSWALK, TIGER):
        (primary / file).write_bytes((REFERENCE / file).read_bytes())
    (primary / "county-page-controls.json").write_bytes(encoded(controls))


def count_tables(primary):
    controls, entries = read(primary / "county-page-controls.json"), {}
    for year in YEARS:
        reports = {}
        for contest in canvass.PAIRS[year]:
            control = controls[contest]
            body = (primary / f"{year}-{contest}.csv").read_bytes()
            if pin(body) != control["csv_pin"]:
                raise ValueError(f"Changed original Massachusetts export: {contest}")
            reports[contest] = {
                "page": control["facts"], "csv": canvass.precincts(body, year=year, contest=contest),
                "page_source": {"url": canvass.BASE + f"view/{contest}/", **control["page_pin"]},
                "csv_source": {"url": canvass.BASE + f"download/{contest}/precincts_include:1/", **control["csv_pin"]},
            }
        entries[canvass.FEEDS[year]] = {"status": "reported", "data": {"reports": reports}}
    body = (primary / CROSSWALK).read_bytes()
    entries[canvass.CROSSWALK_FEED] = {
        "status": "reported", "source": {"url": canvass.CROSSWALK_URL, **pin(body)},
        "data": canvass.parse_crosswalk(body),
    }
    historical, rollup = list(canvass.history_exports(entries)), list(canvass.rollup_exports(entries))
    if not historical or len(rollup) != 366:
        raise ValueError("Incomplete Massachusetts historical canvasses or municipality reconciliation")
    return csv_bytes(historical), csv_bytes(rollup)


def outputs(primary, geometry, target):
    history, rollup = count_tables(primary)
    target.mkdir()
    (target / canvass.HISTORY_CSV).write_bytes(history)
    (target / canvass.CROSSWALK_CSV).write_bytes(rollup)
    layer, projected, total = municipalities.join((primary / TIGER).read_bytes(), rollup)
    (target / "municipality-MA-2022.geojson").write_text(
        json.dumps(layer, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    (target / "massachusetts-2022-municipality-map.html").write_text(
        municipalities.render(layer, projected, total), encoding="utf-8")
    precincts.build(geometry, history, target / "precinct-reference")
    return history, rollup


def semantic_version(target):
    # Page wrappers can change without revising any count. The package preserves
    # their pins, while the no-op check ignores only those wrapper hashes.
    result = {}
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        body = path.read_bytes()
        if path.name == canvass.HISTORY_CSV:
            rows = csv.DictReader(io.StringIO(body.decode()))
            body = csv_bytes([{k: v for k, v in row.items() if not k.endswith("_page_sha256")} for row in rows])
        result[path.relative_to(target).as_posix()] = pin(body)
    return digest(encoded(result))


def package(primary, geometry, work):
    target = work / "outputs"
    outputs(primary, geometry, target)
    members = {f"{folder}/{path.relative_to(root).as_posix()}": path.read_bytes()
               for folder, root in (("primary", primary), ("geometry", geometry), ("outputs", target))
               for path in root.rglob("*") if path.is_file()}
    members.update({f"scripts/{name}": (ROOT / "scripts" / name).read_bytes() for name in MODULES})
    members["REPRODUCE.txt"] = (
        "Install CPython 3.12 and pyshp==3.1.8 pyproj==3.8.0 shapely==2.2.0.\n"
        "From the extracted archive: PROJ_NETWORK=OFF python3.12 -m scripts.massachusetts_historical_release"
        " --replay . --work reproduced\n"
        "All nine complete outputs reproduce offline. These are counts including blanks, not rates. "
        "See precinct-reference-coverage.csv for every geometry hold.\n"
    ).encode()
    archive = work / "complete-analysis.zip"
    archive.write_bytes(archive_bytes(members))
    # Verify the packaged code, not just the working copy.
    with tempfile.TemporaryDirectory(prefix="ma-historical-replay-") as directory, zipfile.ZipFile(archive) as source:
        source.extractall(directory)
        subprocess.run([sys.executable, "-I", "-c",
                        "import sys,runpy; sys.path.insert(0,'.'); "
                        "runpy.run_module('scripts.massachusetts_historical_release',run_name='__main__')",
                        "--replay", ".", "--work", "reproduced"], cwd=directory, check=True)
    return archive, semantic_version(target)


def replay(root, work):
    manifest = read(root / "checksums.json")
    for name, expected in manifest.items():
        if pin((root / relative(name)).read_bytes()) != expected:
            raise ValueError("Changed Massachusetts historical package member: " + name)
    with offline() as attempts:
        outputs(root / "primary", root / "geometry", work)
    produced = {"outputs/" + path.relative_to(work).as_posix(): pin(path.read_bytes())
                for path in work.rglob("*") if path.is_file()}
    if attempts or len(produced) != 9 or produced != {k: v for k, v in manifest.items() if k.startswith("outputs/")}:
        raise ValueError("Incomplete Massachusetts historical numerical replay")
    return {"complete_outputs": len(produced), "network_requests": 0}


def activate_staged(publisher, staged, receipt):
    if publisher.remote_head() != staged or publisher.parent_of(staged) != receipt["parent"]:
        raise ValueError("Massachusetts staged output no longer has the expected predecessor")
    file, file_pin = receipt["path"], receipt["file"]
    if (file != f"versions/{file_pin['sha256']}/complete-analysis.zip"
            or not re.fullmatch(r"[a-f0-9]{64}", file_pin["sha256"])
            or not re.fullmatch(r"[a-f0-9]{64}", receipt["numerical_version"])
            or not 1 <= file_pin["bytes"] <= 90_000_000):
        raise ValueError("Invalid Massachusetts historical ZIP receipt")
    publisher.verify_files(staged, {file: file_pin})
    manifest = {
        "contract": CONTRACT, "version": file_pin["sha256"], "numerical_version": receipt["numerical_version"],
        "years": list(YEARS), "complete_download": {
            "url": f"https://raw.githubusercontent.com/{REPOSITORY}/{staged}/{file}",
            **file_pin, "media_type": "application/zip", "verified_anonymously": True,
        },
    }
    files = {"latest.json": encoded(manifest), PENDING: encoded(None)}
    commit = publisher.commit(publisher.tree(staged, files), staged, "Activate verified Massachusetts historical atlas")
    publisher.promote(commit, staged)
    publisher.verify_files(commit, {name: pin(data) for name, data in files.items()})


def publish(publisher, parent, prior, ledger, archive, version):
    if prior and prior["numerical_version"] == version:
        return "unchanged"
    body = archive.read_bytes()
    if not 1 <= len(body) <= 90_000_000:
        raise ValueError("Massachusetts historical ZIP exceeds the Git-hosted download bound")
    file = f"versions/{digest(body)}/complete-analysis.zip"
    receipt = {"parent": parent, "path": file, "file": pin(body), "numerical_version": version}
    files = {file: body, PENDING: encoded(receipt), "source-stops.json": encoded(ledger)}
    commit = publisher.commit(publisher.tree(parent, files), parent, "Stage complete Massachusetts historical atlas")
    publisher.promote(commit, parent)
    activate_staged(publisher, commit, receipt)
    return "published"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", type=Path)
    mode.add_argument("--retained", type=Path, help="Build and validate without acquisition/publication")
    mode.add_argument("--refresh", action="store_true")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish and not args.refresh:
        parser.error("--publish requires --refresh")
    if args.replay:
        print(json.dumps(replay(args.replay, args.work)), flush=True)
        return
    args.work.mkdir()
    primary, geometry = args.work / "primary", args.work / "geometry"
    if args.retained:
        archive, version = package(args.retained / "primary", args.retained / "geometry", args.work)
    else:
        from scripts.results_intake import Collector, merge_stops, stops

        publisher = GitPublisher(ROOT, ref=REF, github_repository=REPOSITORY)
        parent = publisher.remote_head()
        publisher.fetch_parent(parent)
        ledger, prior = EMPTY_STOPS, None
        if parent:
            read_previous = lambda name: publisher.git("show", parent + ":" + name, check=False)
            ledger = stops(json.loads(read_previous("source-stops.json") or encoded(EMPTY_STOPS)))
            prior = json.loads(read_previous("latest.json") or "null")
            if prior and (prior.get("contract") != CONTRACT or
                          not re.fullmatch(r"[a-f0-9]{64}", prior.get("numerical_version", ""))):
                raise ValueError("Unknown Massachusetts historical atlas pointer")
            pending = json.loads(read_previous(PENDING) or "null")
            if pending and args.publish:
                activate_staged(publisher, parent, pending)
                print(json.dumps({"status": "resumed", "numerical_version": pending["numerical_version"]}), flush=True)
                return
        # Honor stops from both this writer and the existing national collector.
        national = GitPublisher(ROOT, ref="results-data", github_repository=REPOSITORY)
        head = national.remote_head()
        national.fetch_parent(head)
        body = national.git("show", head + ":source-stops.json", check=False) if head else ""
        collector = Collector(args.work, {}, merge_stops(ledger, json.loads(body) if body else EMPTY_STOPS), utc_now())
        try:
            collect(primary, collector.acquire)
            history, _ = count_tables(primary)
            precincts.collect(geometry, history, collector.acquire)
            archive, version = package(primary, geometry, args.work)
            if args.publish:
                status = publish(publisher, parent, prior, collector.stopped, archive, version)
                print(json.dumps({"status": status, "numerical_version": version}), flush=True)
                return
        except Exception:
            if args.publish and collector.stopped != ledger and publisher.remote_head() == parent:
                files = {"source-stops.json": encoded(collector.stopped)}
                commit = publisher.commit(publisher.tree(parent, files), parent, "Retain Massachusetts source access holds")
                publisher.promote(commit, parent)
            raise
    print(json.dumps({"status": "validated", "numerical_version": version, "complete_download": pin(archive.read_bytes())}))


if __name__ == "__main__":
    main()
