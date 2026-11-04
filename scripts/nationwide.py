"""Preserve source-aware 2026 participation updates across all states and DC."""

import argparse
import copy
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from html.parser import HTMLParser

import requests

from scripts.current import digest, integer, reporting_counts, update_downloads, write_csv
from scripts.download import ROOT, atomic_json

ELECTION = "2026-11-03"
API = "https://civicapi.org/api/v2/early-vote"
STATES = dict(line.split("|") for line in """
AL|Alabama
AK|Alaska
AZ|Arizona
AR|Arkansas
CA|California
CO|Colorado
CT|Connecticut
DE|Delaware
DC|District of Columbia
FL|Florida
GA|Georgia
HI|Hawaii
ID|Idaho
IL|Illinois
IN|Indiana
IA|Iowa
KS|Kansas
KY|Kentucky
LA|Louisiana
ME|Maine
MD|Maryland
MA|Massachusetts
MI|Michigan
MN|Minnesota
MS|Mississippi
MO|Missouri
MT|Montana
NE|Nebraska
NV|Nevada
NH|New Hampshire
NJ|New Jersey
NM|New Mexico
NY|New York
NC|North Carolina
ND|North Dakota
OH|Ohio
OK|Oklahoma
OR|Oregon
PA|Pennsylvania
RI|Rhode Island
SC|South Carolina
SD|South Dakota
TN|Tennessee
TX|Texas
UT|Utah
VT|Vermont
VA|Virginia
WA|Washington
WV|West Virginia
WI|Wisconsin
WY|Wyoming
""".strip().splitlines())
MODES = {"inperson": "in_person_early", "returned": "mail_returned"}
DIMENSIONS = {"race": "race", "ethnicity": "ethnicity", "gender": "gender", "age_range": "age"}
OFFICIAL = {
    "AL": "https://www2.alabamavotes.gov/electionNight/statewideResultsByContest.aspx?ecode=1001305",
    "NC": "https://er.ncsbe.gov/enr/20261103/data/county.txt",
    "ND": "https://www.sos.nd.gov/news/398-voter-turnout-north-dakota-general-election",
    "OR": "https://results.oregonvotes.gov/?ID=39",
}


class NoData(ValueError):
    pass


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def match(pattern, text):
    found = re.search(pattern, text, re.I)
    if not found:
        raise ValueError(f"Missing administrative field: {pattern}")
    return found


def count(text):
    return integer(text.replace(",", ""))


def source_date(value, today):
    if not value:
        raise NoData("No dated observations in this source")
    parsed = date.fromisoformat(value)
    if not date(2026, 9, 1) <= parsed <= today:
        raise ValueError("Wrong election season or future source date")
    return value


def validate_identity(payload, state, mode=None):
    if payload.get("state") != state or (mode and payload.get("category") != mode):
        raise ValueError("Source state or voting mode disagrees with requested endpoint")


def party_sum(groups):
    if not isinstance(groups, dict) or not groups:
        raise ValueError("Missing aggregate count cells")
    return sum(integer(cell["votes"]) for cell in groups.values())


def parse_mode(payload, state, mode, today):
    validate_identity(payload, state, mode)
    dated = source_date(payload.get("snapshot_date"), today)
    total = party_sum(payload["statewide_total"])
    if not isinstance(payload.get("regions"), dict):
        raise ValueError("Missing source-region schema")
    regions = [{"name": name, "ballots": party_sum(groups)}
               for name, groups in payload["regions"].items()]
    quality = ["source_regions_not_reported"] if not regions else (
        [] if sum(row["ballots"] for row in regions) == total else ["region_state_totals_disagree"])
    return {"date": dated, "total": total, "regions": regions, "quality": quality}


def parse_demographics(payload, state, mode, dimension, today):
    validate_identity(payload, state, mode)
    if payload.get("breakdown_by") != dimension or payload.get("region") is not None:
        raise ValueError("Wrong demographic dimension or geography")
    dated = source_date(payload.get("snapshot_date"), today)
    groups = [{"group": label, "ballots": integer(value)}
              for label, value in payload["values"].items()]
    total = integer(payload["total"])
    if not groups or sum(row["ballots"] for row in groups) != total:
        raise ValueError("Demographic cells do not reconcile to their source total")
    return {"date": dated, "total": total, "groups": groups, "quality": []}


def parse_official(content, state):
    if state == "NC":
        rows, _ = reporting_counts(json.loads(content))
        row = next(item for item in rows if item["county_id"] == "0")
        return {
            "ballots": row["ballots_cast"], "denominator": row["registered_voters"],
            "denominator_basis": "active_and_inactive_registered_voters",
            "published_pct": row["source_published_pct"],
            "validated_pct": row["reported_ballot_fraction_pct"],
            "source_update_label": row["source_update_label"],
            "reported_units": row["precincts_reporting"], "total_units": row["precincts_total"],
            "reporting_unit": "precincts", "quality": row["quality"],
        }
    html = content.decode("utf-8", errors="replace")
    parser = PageText()
    parser.feed(html)
    text = " ".join(" ".join(parser.parts).split())
    record = {"reported_units": None, "total_units": None, "reporting_unit": None, "quality": []}
    if state == "AL":
        match(r"2026 GENERAL ELECTION", text)
        record.update(
            ballots=count(match(r"Total Ballots Cast:\s*([\d,]+)", text)[1]),
            denominator=count(match(r"Total Registered Voters:\s*([\d,]+)", text)[1]),
            denominator_basis="registered_voters_source_definition",
            published_pct=float(match(r"Voter Turnout:\s*([\d.]+)\s*%", text)[1]),
            source_update_label=match(r"Last Updated:\s*([0-9/: APMapm]+)", text)[1].strip(),
        )
        units = match(r"Counties Reported:\s*(\d+)\s*of\s*(\d+)", text)
        record.update(reported_units=integer(units[1]), total_units=integer(units[2]),
                      reporting_unit="counties")
    elif state == "OR":
        match(r'id="hidElectionDate"\s+value="11/3/2026"', html)
        record.update(
            ballots=count(match(r"Ballots Counted\s*([\d,]+)", text)[1]),
            denominator=count(match(r"Active Registered Voters\s*([\d,]+)", text)[1]),
            denominator_basis="active_registered_voters",
            published_pct=float(match(
                r"Statewide Voter Turnout\s*\(details\)\s*(\d+\s*(?:\.\d+)?)\s*%", text)[1].replace(" ", "")),
            source_update_label=match(r"Results last updated:\s*([0-9/: |APMTapmt]+)", text)[1].strip(),
        )
    elif state == "ND":
        result = match(r"([\d.]+) percent of eligible North Dakota voters cast ([\d,]+) "
                       r"ballots during the 2026 General Election", text)
        components = [
            count(match(r"([\d,]+) votes cast on election day", text)[1]),
            count(match(r"([\d,]+) ballots by early vote", text)[1]),
            count(match(r"([\d,]+) absentee/vote-by-mail ballots", text)[1]),
        ]
        if sum(components) != count(result[2]):
            raise ValueError("Official voting-mode components disagree with ballots")
        record.update(
            ballots=count(result[2]), denominator=None, denominator_basis="eligible_voters_source_estimate",
            published_pct=float(result[1]),
            source_update_label=match(r"Tuesday, November 3, 2026\s*-\s*11:30pm", text)[0],
        )
    else:
        raise ValueError("No verified administrative parser for this state")
    record["validated_pct"] = None
    denominator = record["denominator"]
    if denominator and 0 < record["ballots"] <= denominator:
        calculated = 100 * record["ballots"] / denominator
        if abs(calculated - record["published_pct"]) <= .015:
            record["validated_pct"] = round(calculated, 3)
        else:
            record["quality"].append("published_percentage_disagrees_with_counts")
    elif denominator is not None:
        record["quality"].append("invalid_or_unreported_denominator_or_ballots")
    if record["total_units"] is not None:
        if record["reported_units"] > record["total_units"]:
            raise ValueError("Reported administrative units exceed source total")
        if record["reported_units"] < record["total_units"]:
            record["quality"].append("incomplete_reporting")
    return record


def refresh(root=ROOT, fetch=requests.get, now=None):
    now = now or datetime.now(timezone.utc)
    snapshot_id, today = now.strftime("%Y%m%dT%H%M%SZ"), now.date()
    raw_root = root / "data/raw/nationwide"
    raw_dir = raw_root / snapshot_id
    raw_dir.mkdir(parents=True, exist_ok=False)
    public = root / "public/data/nationwide"
    previous = {}
    if (public / "latest.json").exists():
        prior_id = json.loads((public / "latest.json").read_text())["snapshot_id"]
        previous = json.loads((public / prior_id / "snapshot.json").read_text())["datasets"]
    sources = []

    def capture(state, kind, url, parser):
        key = f"{state}-{kind}"
        source = None
        try:
            response = fetch(url, timeout=(15, 45))
            content = response.content
            name = key + (".json" if "/api/" in url or state == "NC" else ".html")
            (raw_dir / name).write_bytes(content)
            source = {
                "file": name, "snapshot_id": snapshot_id, "url": url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "bytes": len(content), "sha256": digest(content), "http_status": response.status_code,
                "last_modified": response.headers.get("Last-Modified"), "etag": response.headers.get("ETag"),
            }
            sources.append(source)
            if response.status_code == 404:
                raise NoData("Not reported by this assessed provider (HTTP 404)")
            if response.status_code != 200:
                raise ValueError(f"Source returned HTTP {response.status_code}")
            data = parser(content)
            return {"state": state, "kind": kind, "status": "reported", "data": data,
                    "source": source, "error": None, "attempt_url": url}
        except Exception as error:
            prior = previous.get(key)
            if prior and prior.get("data") is not None:
                entry = copy.deepcopy(prior)
                entry.update(status="retained_after_failure", error=str(error), attempt_url=url)
                return entry
            return {"state": state, "kind": kind,
                    "status": "not_reported" if isinstance(error, NoData) else "failed",
                    "data": None, "source": source, "error": str(error), "attempt_url": url}

    def state_datasets(state):
        entries = {}
        caps = capture(state, "capabilities", f"{API}/{state}/capabilities",
                       lambda body: parse_capabilities(json.loads(body), state))
        entries[f"{state}-capabilities"] = caps
        capabilities = caps.get("data")
        if capabilities:
            for mode in MODES:
                if mode not in capabilities["categories"]:
                    continue
                entries[f"{state}-{mode}"] = capture(
                    state, mode, f"{API}/{state}/{mode}",
                    lambda body, mode=mode: parse_mode(json.loads(body), state, mode, today))
                for dimension, capability in DIMENSIONS.items():
                    if capabilities["categories"][mode].get(capability) is not True:
                        continue
                    kind = f"{mode}-{dimension}"
                    entries[f"{state}-{kind}"] = capture(
                        state, kind, f"{API}/{state}/{mode}/demographics?by={dimension}",
                        lambda body, mode=mode, dimension=dimension: parse_demographics(
                            json.loads(body), state, mode, dimension, today))
        if state in OFFICIAL:
            entries[f"{state}-official"] = capture(
                state, "official", OFFICIAL[state], lambda body: parse_official(body, state))
        # A failed capability probe must not silently erase previously saved observations.
        if caps["status"] == "retained_after_failure":
            for key, entry in previous.items():
                if entry["state"] == state and key not in entries and entry.get("data") is not None:
                    entries[key] = {**copy.deepcopy(entry), "status": "retained_after_failure",
                                    "error": "Capability probe failed; retained previous source"}
        return entries

    datasets = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for entries in executor.map(state_datasets, STATES):
            datasets.update(entries)
    snapshot = assemble(datasets, snapshot_id, now.isoformat())
    snapshot["sources"] = sorted(sources, key=lambda source: source["file"])
    if not snapshot["early_voting"] and not snapshot["reporting"]:
        atomic_json(raw_dir / "manifest.json", {**snapshot, "status": "rejected"})
        raise ValueError("No valid current or previously saved participation observations")
    atomic_json(raw_dir / "manifest.json", {
        "status": "validated_with_explicit_coverage", "sources": snapshot["sources"],
        "coverage": snapshot["coverage"], "audit": snapshot["audit"],
    })
    output = public / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "snapshot.json", snapshot)
    for name in ["early_voting", "demographics", "reporting", "coverage"]:
        if snapshot[name]:
            write_csv(output / f"{name}.csv", snapshot[name])
    with zipfile.ZipFile(output / "complete-snapshot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        originals = set(raw_dir.iterdir())
        for entry in datasets.values():
            if entry.get("data") is not None:
                source = entry["source"]
                originals.add(raw_root / source["snapshot_id"] / source["file"])
        for path in sorted(originals):
            archive.write(path, "sources/" + str(path.relative_to(raw_root)))
        for path in sorted(output.iterdir()):
            if path.name != "complete-snapshot.zip":
                archive.write(path, path.name)
    atomic_json(public / "latest.json", {
        "snapshot_id": snapshot_id, "election_date": ELECTION,
        "retrieved_at": snapshot["retrieved_at"], "status": "preliminary",
        "audit": snapshot["audit"],
        "files": [{"path": f"nationwide/{snapshot_id}/{path.name}", "bytes": path.stat().st_size,
                   "sha256": digest(path.read_bytes())} for path in sorted(output.iterdir())],
    })
    print(json.dumps({"snapshot_id": snapshot_id, **snapshot["audit"]}, indent=2))
    return snapshot


def parse_capabilities(payload, state):
    validate_identity(payload, state)
    if not isinstance(payload.get("categories"), dict) or not payload["categories"]:
        raise ValueError("Missing provider capability schema")
    for category in payload["categories"].values():
        if not isinstance(category, dict) or any(type(value) is not bool for value in category.values()):
            raise ValueError("Unexpected category capabilities")
    return payload


def assemble(datasets, snapshot_id, retrieved_at):
    early, demographics, reporting, coverage = [], [], [], []
    for state, name in STATES.items():
        entries = [entry for entry in datasets.values() if entry["state"] == state]
        available = {entry["kind"]: entry for entry in entries if entry.get("data") is not None}
        dimensions = set()
        for kind, entry in available.items():
            data = entry["data"]
            if kind == "capabilities":
                continue
            source = entry["source"]
            common = {
                "state_code": state, "state": name, "source_date": data.get("date"),
                "source_update_label": data.get("source_update_label"),
                "source_retrieved_at": source["retrieved_at"], "status": entry["status"],
                "source_url": source["url"], "source_snapshot": source["snapshot_id"],
                "quality": list(data["quality"]),
            }
            if kind == "official":
                reporting.append({**common, **{key: value for key, value in data.items() if key != "quality"}})
            elif kind in MODES:
                for region, ballots in [("STATEWIDE", data["total"])] + [
                        (row["name"], row["ballots"]) for row in data["regions"]]:
                    early.append({**common, "mode": MODES[kind], "geography": region,
                                  "geography_level": "state" if region == "STATEWIDE" else "source_region",
                                  "ballots": ballots})
            else:
                mode, dimension = kind.split("-", 1)
                if mode not in MODES or dimension not in DIMENSIONS:
                    raise ValueError("Unexpected dataset kind")
                mode_entry = available.get(mode)
                if not mode_entry:
                    common["quality"].append("mode_total_unavailable")
                else:
                    mode_data = mode_entry["data"]
                    if data["date"] != mode_data["date"]:
                        common["quality"].append("different_date_from_mode_total")
                    if data["total"] != mode_data["total"]:
                        common["quality"].append("demographic_total_differs_from_mode_total")
                if data["total"] == 0:
                    common["quality"].append("no_demographic_counts_reported")
                if data["total"] > 0:
                    dimensions.add(dimension)
                for row in data["groups"]:
                    demographics.append({**common, "mode": MODES[mode], "dimension": dimension,
                                         **row, "demographic_source_total": data["total"],
                                         "turnout_pct": None})
        has_early = any(mode in available for mode in MODES)
        coverage.append({
            "state_code": state, "state": name,
            "status": "official_and_early_data" if "official" in available and has_early else
                      "official_data_only" if "official" in available else
                      "early_data_only" if has_early else "not_reported_by_assessed_sources",
            "official_status": available["official"]["status"] if "official" in available else
                               "not_yet_ingested" if state not in OFFICIAL else
                               datasets[f"{state}-official"]["status"],
            "inperson_status": available["inperson"]["status"] if "inperson" in available else "not_reported",
            "returned_status": available["returned"]["status"] if "returned" in available else "not_reported",
            "demographic_dimensions": sorted(dimensions),
            "failed_sources": sum(entry["status"] == "failed" for entry in entries),
            "retained_sources": sum(entry["status"] == "retained_after_failure" for entry in entries),
            "assessment_url": f"{API}/{state}/capabilities",
        })
    return {
        "snapshot_id": snapshot_id, "retrieved_at": retrieved_at,
        "election_date": ELECTION, "status": "preliminary", "datasets": datasets,
        "early_voting": early, "demographics": demographics, "reporting": reporting, "coverage": coverage,
        "audit": {
            "jurisdictions_assessed": len(coverage),
            "jurisdictions_with_data": sum(row["status"] != "not_reported_by_assessed_sources" for row in coverage),
            "jurisdictions_with_early_data": len({row["state_code"] for row in early}),
            "jurisdictions_with_demographic_counts": sum(bool(row["demographic_dimensions"]) for row in coverage),
            "jurisdictions_with_official_ballots": len(reporting),
            "failed_sources": sum(row["failed_sources"] for row in coverage),
            "retained_sources": sum(row["retained_sources"] for row in coverage),
        },
        "providers": [{"name": "civicAPI", "url": "https://www.civicapi.org/early-vote",
                       "terms": "https://www.civicapi.org/api-documentation",
                       "role": "Public aggregate early-voting provider; not a certified government turnout series."},
                      {"name": "State election offices", "urls": OFFICIAL,
                       "role": "Administrative ballots and explicitly labeled denominators, where verified."}],
        "reference_not_ingested": {
            "url": "https://www.nytimes.com/interactive/2026/elections/voter-trends-national.html",
            "reason": "Automated access denied; no NYT figures or methodology have been extracted."},
        "limitations": [
            "This is a saved snapshot, not a live feed. Retrieval time is not the source's data date.",
            "All 50 states and DC are assessed against the public provider; missing there does not mean unavailable everywhere.",
            "Early-voting and returned-mail counts exclude other voting and are not full-election turnout.",
            "Never add official ballots to early-voting counts, or demographic dimensions to one another.",
            "Party registration is summed out; no candidate votes or preferences are normalized.",
            "Demographic counts have no matched population denominator; no demographic turnout rates are estimated.",
            "Group bins and source dates differ by state; no pooled national demographic percentage is constructed.",
            "A zero or undated demographic response is not evidence that no members of that group voted.",
            "Official registered, active-registered, and estimated-eligible voter percentages are different measures.",
            "Source-region names are not assumed to be precincts or certified election-year boundaries.",
            "No 2026 education or national precinct turnout is inferred. Historical series remain separate.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-downloads", action="store_true")
    args = parser.parse_args()
    refresh()
    if args.update_downloads:
        update_downloads()
