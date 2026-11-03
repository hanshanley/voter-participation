"""Cache original public aggregate sources and an auditable download manifest."""

import concurrent.futures
import hashlib
import json
import re
import time
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
}
CENSUS = [
    "hst_vote01.xlsx", "hst_vote02.xlsx", "hst_vote03a.xlsx",
    "hst_vote03b.xlsx", "hst_vote04.xlsx", "a5a.xlsx", "a5b.xlsx",
    "hst_vote06.xlsx", "hst_vote07.xlsx", "hst_vote08.xlsx",
    "hst_vote09.xlsx", "hst_vote10.xlsx",
]


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
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
    results = {}

    def collect(jobs):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for result in executor.map(download, jobs):
                results[result["path"]] = result
                atomic_json(manifest_path, {"sources": sorted(results.values(), key=lambda s: s["path"])})

    collect(specs)
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
    failures = [r for r in results.values() if r["status"] == "failed"]
    print(f"Sources: {len(results)}; failures: {len(failures)}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
