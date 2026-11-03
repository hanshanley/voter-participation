"""Cache original public aggregate sources and an auditable download manifest."""

import concurrent.futures
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www2.census.gov/programs-surveys/cps/tables/time-series/voting-historical-time-series/"
NC = "https://s3.amazonaws.com/dl.ncsbe.gov/"
PAGES = {
    "nc_history": "https://www.ncsbe.gov/results-data/voter-history-data",
    "nc_registration": "https://www.ncsbe.gov/results-data/voter-registration-data",
    "nc_geometry": "https://www.ncsbe.gov/results-data/voting-maps-redistricting",
    "nc_turnout": "https://www.ncsbe.gov/results-data/voter-turnout",
}
CENSUS = [
    "hst_vote01.xlsx", "hst_vote02.xlsx", "hst_vote03a.xlsx",
    "hst_vote03b.xlsx", "hst_vote04.xlsx", "a5a.xlsx", "a5b.xlsx",
    "hst_vote06.xlsx", "hst_vote07.xlsx", "hst_vote08.xlsx",
    "hst_vote09.xlsx", "hst_vote10.xlsx",
]
ELECTION_DIRECTORIES = {
    2000: "542", 2002: "552", 2004: "556", 2006: "557", 2008: "562-rv",
    2010: "voting-registration-2010-election", 2012: "568", 2014: "577",
    2016: "580", 2018: "583", 2020: "585", 2022: "586", 2024: "587",
}


def atomic_json(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=None if compact else 2,
                                    separators=(",", ":") if compact else None,
                                    ensure_ascii=True) + "\n")
    temporary.replace(path)


def download(spec):
    path = ROOT / spec["path"]
    result = dict(spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if spec.get("sha256") == digest:
            result["status"] = "cached"
            print(f"cached {spec['path']}", flush=True)
            return result
    for attempt in range(3):
        try:
            response = requests.get(spec["url"], timeout=(15, 150))
            response.raise_for_status()
            content = response.content
            if path.suffix in {".zip", ".xlsx"} and not content.startswith(b"PK"):
                raise ValueError("Expected ZIP/XLSX, received a different format")
            if path.suffix == ".xls" and not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
                raise ValueError("Expected a legacy Excel workbook")
            if path.suffix == ".geojson":
                payload = response.json()
                if payload.get("type") != "FeatureCollection" or not payload.get("features"):
                    raise ValueError("Expected a nonempty GeoJSON FeatureCollection")
            temporary = path.with_suffix(path.suffix + ".part")
            temporary.write_bytes(content)
            temporary.replace(path)
            result.update(
                status="downloaded", bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )
            result.pop("error", None)
            print(f"saved {spec['path']} ({len(content):,} bytes)", flush=True)
            return result
        except (requests.RequestException, ValueError) as error:
            result.update(status="failed", error=str(error))
            if attempt < 2:
                time.sleep(2 ** attempt)
    print(f"FAILED {spec['url']}: {result['error']}", flush=True)
    return result


def main():
    manifest_path = ROOT / "data/sources.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    existing = {s["path"]: s for s in previous.get("sources", [])}
    specs = [
        {"url": BASE + name, "path": "data/raw/census/" + name, "kind": "census_workbook"}
        for name in CENSUS
    ]
    for name, url in PAGES.items():
        specs.append({"url": url, "path": f"data/raw/pages/{name}.html", "kind": "source_catalog"})
    for filename in ["layout_history_stats.txt", "layout_voter_stats.txt"]:
        specs.append({"url": NC + "ENRS/" + filename,
                      "path": "data/raw/layouts/" + filename, "kind": "nc_layout"})
    specs = [dict(existing.get(s["path"], {}), **s) for s in specs]
    results = dict(existing)

    def collect(jobs):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for result in executor.map(download, jobs):
                results[result["path"]] = result
                atomic_json(manifest_path, {"sources": sorted(results.values(), key=lambda s: s["path"])})

    collect(specs)
    catalogs = [
        {"url": f"https://www2.census.gov/programs-surveys/cps/tables/p20/{directory}/",
         "path": f"data/raw/pages/cps_{year}.html", "kind": "cps_election_catalog", "year": year}
        for year, directory in ELECTION_DIRECTORIES.items()
    ]
    collect([dict(existing.get(s["path"], {}), **s) for s in catalogs])
    election_tables = []
    for spec in catalogs:
        page = ROOT / spec["path"]
        if not page.exists():
            continue
        links = re.findall(r'href="([^"]+\.(?:xlsx|xls))"', page.read_text())
        for table in [1, 5]:
            candidates = []
            for link in links:
                name = link.rsplit("/", 1)[-1]
                numbers = [int(n) for n in re.findall(r"\d+", name) if int(n) < 1900]
                if numbers in ([table], [table, 1]) and re.fullmatch(r"(?:table|tab|vote)[\d_-]+\.(?:xlsx|xls)", name):
                    candidates.append(link)
            if len(candidates) != 1:
                raise ValueError(f"{spec['year']}: cannot uniquely identify Census table {table}: {candidates}")
            link = candidates[0]
            job = {"url": spec["url"] + link, "path": f"data/raw/census/elections/{spec['year']}/{link}",
                   "kind": "cps_election_table", "year": spec["year"], "table": table}
            election_tables.append(dict(existing.get(job["path"], {}), **job))
    collect(election_tables)
    nc_specs = []
    for name in ["nc_history", "nc_registration"]:
        page = ROOT / f"data/raw/pages/{name}.html"
        if not page.exists():
            continue
        pattern = r'https://s3\.amazonaws\.com/dl\.ncsbe\.gov/ENRS/(\d{4})_(\d{2})_(\d{2})/((?:history|voter)_stats_\d{8}\.zip)'
        for year, month, day, filename in sorted(set(re.findall(pattern, page.read_text()))):
            year_number = int(year)
            if month != "11" or int(day) > 8 or year_number % 2 or year_number > 2024:
                continue
            spec = {
                "url": NC + f"ENRS/{year}_{month}_{day}/{filename}",
                "path": "data/raw/nc/" + filename,
                "kind": "nc_history" if filename.startswith("history") else "nc_registration",
                "year": year_number, "election_date": f"{year}-{month}-{day}",
            }
            nc_specs.append(dict(existing.get(spec["path"], {}), **spec))
    collect(nc_specs)
    geometry_specs = [{
        "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2024/State_County/MapServer/9/query"
               "?where=1%3D1&outFields=NAME%2CSTATE%2CSTUSAB&outSR=4326&geometryPrecision=4&f=geojson",
        "path": "data/raw/geometry/states.geojson", "kind": "state_geometry",
    }, {
        "url": NC + "?list-type=2&prefix=ShapeFiles/Precinct/",
        "path": "data/raw/geometry/nc_catalog.xml", "kind": "boundary_catalog",
    }]
    geometry_jobs = []
    for spec in geometry_specs:
        old = existing.get(spec["path"], {})
        geometry_jobs.append(dict(old if old.get("url") == spec["url"] else {}, **spec))
    collect(geometry_jobs)
    catalog = ROOT / "data/raw/geometry/nc_catalog.xml"
    if catalog.exists():
        root = ET.fromstring(catalog.read_bytes())
        namespace = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys = {x.text for x in root.findall("s:Contents/s:Key", namespace)}
        selected = {
            2006: "Precincts2006Gen.zip",
            2012: "SBE_PRECINCTS_20120901.zip",
            2014: "SBE_PRECINCTS_20141016.zip",
            2016: "SBE_PRECINCTS_20161004.zip",
            2020: "SBE_PRECINCTS_20201018.zip",
            2022: "SBE_PRECINCTS_20220831.zip",
            2024: "SBE_PRECINCTS_20240723.zip",
        }
        jobs = []
        for year, filename in selected.items():
            key = "ShapeFiles/Precinct/" + filename
            if key not in keys:
                continue
            spec = {"url": NC + key, "path": "data/raw/geometry/" + filename,
                    "kind": "nc_geometry", "year": year,
                    "vintage": filename.removesuffix(".zip")}
            jobs.append(dict(existing.get(spec["path"], {}), **spec))
        collect(jobs)
    failures = [r for r in results.values() if r["status"] == "failed"]
    print(f"Sources: {len(results)}; failures: {len(failures)}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
