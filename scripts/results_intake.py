"""Refresh reviewed election feeds; preserve independent results and durable access holds."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import re
import threading
from urllib.parse import unquote, urlsplit, urlunsplit
import zipfile

from scripts.nationwide import (
    API, DIMENSIONS, MODES, OFFICIAL, STATES, NoData,
    parse_capabilities, parse_demographics, parse_mode, parse_official,
)
from scripts.current import reporting_counts
from scripts.participation_intake.contract import IntakeError, digest, encoded, pin
from scripts.participation_intake.engine import Store
from scripts.participation_intake.publisher import GitPublisher
from scripts.precinct_source_batch import discover_links, is_general_precinct_product
from scripts.results_house import NATIONAL_URL, candidate_results, districts, state_totals
from scripts import results_granular


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "participation.automatic_results_registry.v1"
CHALLENGES = [r"verify (?:that )?you are human", r"cf-chl-",
              r"incapsula incident id", r"captcha challenge"]


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name:
        raise ValueError("Unsafe registered relative path")
    return path


def normalized(url):
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                       unquote(parsed.path), parsed.query, ""))


def stops(value):
    if (not isinstance(value, dict) or set(value) != {"urls", "prefixes", "hosts"}
            or any(not isinstance(value[key], list)
                   or any(not isinstance(item, str) or not item for item in value[key])
                   for key in value)):
        raise ValueError("Unreadable/malformed durable access-stop ledger; refusing transport")
    if any(not item.startswith(("http://", "https://"))
           for key in ("urls", "prefixes") for item in value[key]):
        raise ValueError("Invalid stop URL/prefix")
    return {key: sorted(set(items)) for key, items in value.items()}


def merge_stops(*values):
    return {key: sorted({item for value in values for item in stops(value)[key]})
            for key in ("urls", "prefixes", "hosts")}


def source_error(error):
    status = getattr(error.__cause__, "code", None)
    if status in (401, 403, 429):
        return "source_stopped"
    if status == 404:
        return "not_reported"
    if isinstance(error, IntakeError):
        return error.code
    return "not_reported" if isinstance(error, NoData) else "schema_or_source_semantics_changed"


def csv_body(rows):
    stream = io.StringIO(newline="")
    columns = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, sort_keys=True, ensure_ascii=True)
                         if isinstance(value, (dict, list)) else value
                         for key, value in row.items()})
    return stream.getvalue().encode()


def compressed(body):
    result = bytearray(gzip.compress(body, compresslevel=6, mtime=0))
    result[9] = 3
    return bytes(result)


def baseline_inputs(folder, declaration):
    result = {}
    for name, expected in declaration["files"].items():
        body = (folder / str(relative(name))).read_bytes()
        if pin(body) != expected:
            raise ValueError("Accepted baseline body changed: " + name)
        result[name] = body
    index = json.loads(result["index.json"])
    if set(index["states"]) != set(STATES):
        raise ValueError("Accepted baseline must cover all 50 states and DC")
    for item in index["states"].values():
        if pin(result[item["file"]]) != {key: item[key] for key in ("bytes", "sha256")}:
            raise ValueError("Accepted state/index pins disagree")
    return result


def house_baseline(rows):
    entries, inventory = {}, {}
    for row in rows:
        district = row["district"]
        value = row["votes"]
        if not (type(value) is int and value >= 0 or
                isinstance(value, str) and re.fullmatch(r"[0-9]+", value)):
            raise ValueError("Invalid accepted candidate count")
        if district not in entries:
            data = {
                "state_code": row["state_code"], "district": district, "candidates": [],
                "source_update_label": row["source_updated_at"], "native_reporting": {},
                "certification_qualified": False, "candidate_votes_are_ballots": False,
                "county_reconciliation_or_map_join_claimed": False,
            }
            entries[district] = {
                "status": "accepted_snapshot_not_refreshed", "data": data,
                "source": {"url": row["source_url"], "role": "accepted_source_baseline"},
                "error": None, "first_observed_at": None,
            }
            inventory[district] = {"district": district, "state_code": row["state_code"],
                                   "url": None, "source_id": None}
        entries[district]["data"]["candidates"].append(
            {"name": row["name"], "party": row["party"], "votes": int(value)})
    if len(inventory) != 435 or {r["state_code"] for r in inventory.values()} != set(STATES) - {"DC"}:
        raise ValueError("Accepted House baseline is incomplete")
    return entries, inventory


class Collector:
    def __init__(self, work, prior, stopped, now, offline=False):
        self.work, self.prior, self.now = Path(work), prior, now
        self.stopped, self.offline = stops(stopped), offline
        self.lock, self.context = threading.Lock(), threading.local()
        self.attempts, self.bodies = [], {}
        write(self.work / "source-stops.json", self.stopped)

    def guard(self, url):
        target = normalized(url)
        with self.lock:
            held = (target in {normalized(item) for item in self.stopped["urls"]}
                    or any(target.startswith(normalized(item)) for item in self.stopped["prefixes"])
                    or urlsplit(url).hostname in self.stopped["hosts"])
        if held:
            raise IntakeError("source_stopped", "Persisted source/product/host access hold")

    def remember_stop(self, url, error):
        status = getattr(error.__cause__, "code", None)
        if status not in (401, 403, 429) and not (
                isinstance(error, IntakeError) and error.code == "source_stopped"):
            return
        actual = getattr(error.__cause__, "filename", None)
        with self.lock:
            for item in (url, actual):
                if isinstance(item, str) and item.startswith(("https://", "http://")):
                    self.stopped["urls"].append(item)
            if status == 429:
                self.stopped["hosts"].append(urlsplit(actual or url).hostname)
            self.stopped = stops(self.stopped)
            write(self.work / "source-stops.json", self.stopped)

    def acquire(self, url, *, refresh=False):
        self.guard(url)
        with self.lock:
            cached_in_run = self.bodies.get(url)
        if cached_in_run is not None and not refresh:
            body, receipt = cached_in_run
            return body, {**receipt, "origin": "same_run_verified_body"}
        if not hasattr(self.context, "store"):
            self.context.store = Store(self.work / "cache")
        if self.offline:
            cached = self.context.store.db.execute(
                "SELECT sha, stopped FROM inputs WHERE url=?", (url,)).fetchone()
            if not cached or not cached[0] or cached[1]:
                raise IntakeError("offline", "No permitted cached numerical source")
            body = (self.work / "cache/objects" / cached[0]).read_bytes()
            if digest(body) != cached[0]:
                raise IntakeError("source_integrity", "Cached source changed")
            return body, {"origin": "cached_offline", **pin(body)}
        try:
            body, receipt = self.context.store.acquire(
                {"url": url, "reject_body_patterns": CHALLENGES}, access_guard=self.guard)
        except Exception as error:
            self.remember_stop(url, error)
            raise
        with self.lock:
            self.bodies[url] = body, receipt
        return body, receipt

    def capture(self, identity, url, parser):
        old = self.prior.get(identity)
        try:
            body, receipt = self.acquire(url)
            data = parser(body)
            if (old and old.get("data") and data.get("date") and old["data"].get("date")
                    and data["date"] < old["data"]["date"]):
                raise ValueError("Source data date regressed")
            source = {"url": url, **pin(body)}
            if old and old.get("source") == source and old.get("data") == data:
                result = copy.deepcopy(old)
                result.update(status="reported", error=None)
            else:
                result = {"status": "reported", "data": data, "source": source, "error": None,
                          "first_observed_at": self.now.isoformat()}
            attempt = {"id": identity, "status": receipt["origin"], **source}
        except Exception as error:
            code = source_error(error)
            result = copy.deepcopy(old) if old and old.get("data") is not None else {
                "data": None, "source": None, "first_observed_at": None}
            result.update(status="retained_after_failure" if result["data"] is not None else code,
                          error=code)
            attempt = {"id": identity, "url": url, "status": code}
        with self.lock:
            self.attempts.append(attempt)
        return result


def numeric_observations(baseline, feeds):
    rows = []
    index = json.loads(baseline["index.json"])
    for state, item in sorted(index["states"].items()):
        shard = json.loads(gzip.decompress(baseline[item["file"]]))
        for row in shard["records"]:
            rows.append({"state_code": state, "channel": "accepted_canonical_observation",
                         "id": row["id"], "observation": row})
    for identity, entry in sorted(feeds.items()):
        if (entry.get("data") is not None and identity.split("-")[0] in STATES
                and not identity.endswith(("-capabilities", "-directory"))):
            rows.append({"state_code": identity.split("-")[0], "channel": identity,
                         "status": entry["status"], "source": entry["source"],
                         "observation": entry["data"]})
    return rows


def project(inputs, baseline):
    feeds, house, declared = (inputs[key] for key in ("feeds", "house", "districts"))
    observations = numeric_observations(baseline, feeds)
    house_states = state_totals(house, declared)
    coverage = []
    for state, name in STATES.items():
        official = feeds.get(state + "-official", {})
        local = [entry for key, entry in inputs.get("granular", {}).items()
                 if key.startswith(state + "-")]
        products = [entry for key, entry in inputs.get("products", {}).items()
                    if key.startswith(state + "-")]
        fresh_local = [entry for entry in local if entry["status"] == "reported"]
        fresh_products = [entry for entry in products
                          if entry["status"] == "reported" and entry.get("data")]
        refreshed = sum(len((entry.get("data") or {}).get("updates", [])) for entry in fresh_local)
        review_required = sum(bool((entry.get("data") or {}).get(
            "semantic_review_required_before_projection")) for entry in fresh_local)
        review_required += len(fresh_products)
        coverage.append({
            "state_code": state, "state": name,
            "statewide_administrative_status": official.get("status", "no_registered_statewide_parser"),
            "statewide_administrative_observation": official.get("data"),
            "provider_early_status": feeds.get(state + "-inperson", {}).get("status", "not_reported"),
            "provider_mail_status": feeds.get(state + "-returned", {}).get("status", "not_reported"),
            "accepted_local_observations_retained": True,
            "official_directory_status": inputs["directories"][state]["status"],
            "registered_native_products": len(local),
            "fresh_native_products": sum(bool((entry.get("data") or {}).get("updates"))
                                         for entry in fresh_local),
            "native_record_refreshes": refreshed,
            "native_source_failures": sum(entry["status"] != "reported" for entry in local),
            "primary_products_requiring_measure_review": review_required,
            "directory_products_attempted": len(products),
            "directory_numerical_products": len(fresh_products),
            "local_intake_status": ("reviewed_native_refresh" if refreshed else
                "source_facts_require_measure_review" if review_required else
                "reviewed_source_without_qualified_updates" if fresh_local else
                "native_source_unavailable" if local else "no_reviewed_native_product_registered"),
            "house": next(row for row in house_states if row["state_code"] == state),
            "complete_reporting_is_not_certification": True,
        })
    candidates = []
    for district, entry in sorted(house.items()):
        if entry.get("data") is None:
            continue
        data = entry["data"]
        for row in data["candidates"]:
            candidates.append({"year": 2026, "state_code": data["state_code"], "district": district,
                               **row, "status": entry["status"], "source": entry["source"],
                               "source_update_label": data["source_update_label"]})
    status_rows = [{"source": key, "status": entry["status"], "error": entry.get("error"),
                    "data_retained": entry.get("data") is not None,
                    "source_url": (entry.get("source") or {}).get("url")}
                   for key, entry in sorted({**feeds, **{"house-" + k: v for k, v in house.items()}}.items())]
    snapshot = {
        "contract": "participation.automatic_results_snapshot.v1", "election_date": "2026-11-03",
        "jurisdictions": coverage, "participation_observations": observations,
        "house_candidates": candidates, "house_states": house_states,
        "source_status": status_rows, "declared_products": inputs["directories"],
        "behavioral_models_refitted": False, "geographic_joins_changed": False,
        "all_states_certified_or_precinct_complete": False,
        "source_clock_not_replaced_by_retrieval_time": True,
        "baseline_and_fresh_source_frames_are_separate_not_added": True,
        "granular_sources": inputs.get("granular", {}),
        "declared_numerical_products": inputs.get("products", {}),
    }
    outputs = {
        "snapshot.json.gz": compressed(encoded(snapshot)), "coverage.csv": csv_body(coverage),
        "participation-observations.csv.gz": compressed(csv_body(observations)),
        "house-candidates.csv": csv_body(candidates), "house-state-results.csv": csv_body(house_states),
        "source-status.csv": csv_body(status_rows),
        "declared-products.json": encoded(inputs["directories"]),
    }
    if "granular" in inputs:
        _, changes = results_granular.project(baseline, inputs["granular"])
        snapshot["canonical_local_changes"] = changes
        outputs["snapshot.json.gz"] = compressed(encoded(snapshot))
        outputs["granular-source-queries.json.gz"] = compressed(encoded(inputs["granular"]))
        outputs["declared-numerical-queries.json.gz"] = compressed(encoded(inputs.get("products", {})))
        outputs["canonical-local-changes.csv"] = csv_body(changes)
    return outputs


def collect(registry_path, work, previous=None, now=None, offline=False):
    registry_path, work = Path(registry_path), Path(work)
    config = read(registry_path)
    now = now or datetime.now(timezone.utc)
    if (config["contract"] != CONTRACT or config["election_date"] != "2026-11-03"
            or set(config["jurisdictions"]) != set(STATES)):
        raise ValueError("Wrong election or incomplete all-state registry")
    baseline = baseline_inputs(registry_path.parent / config["baseline"]["root"], config["baseline"])
    previous = previous or {}
    if "initial_state" in config:
        seed_body = (registry_path.parent / str(relative(config["initial_state"]["file"]))).read_bytes()
        if pin(seed_body) != {key: config["initial_state"][key] for key in ("bytes", "sha256")}:
            raise ValueError("Initial complete numerical source state changed")
        seed = json.loads(seed_body)
        previous = {**seed, **previous}
    extras = {}
    for name, declaration in config.get("accepted_queries", {}).items():
        body = (registry_path.parent / str(relative(declaration["file"]))).read_bytes()
        if pin(body) != {key: declaration[key] for key in ("bytes", "sha256")}:
            raise ValueError("Accepted candidate query changed")
        extras[str(relative(name))] = body
    baseline_house, baseline_districts = {}, {}
    if "accepted-current-candidate-queries.json" in extras:
        baseline_house, baseline_districts = house_baseline(
            json.loads(extras["accepted-current-candidate-queries.json"]))
    stopped = merge_stops(config["source_stops"], previous.get("source_stops", config["source_stops"]),
                          read(work / "source-stops.json") if (work / "source-stops.json").exists()
                          else {"urls": [], "prefixes": [], "hosts": []})
    prior = previous.get("feeds", {})
    collector = Collector(work, prior, stopped, now, offline)
    feeds, directories, house = {}, {}, {}

    def provider(state):
        result = {}
        identity = state + "-capabilities"
        caps = collector.capture(identity, API + "/" + state + "/capabilities",
                                 lambda body: parse_capabilities(json.loads(body), state))
        result[identity] = caps
        categories = (caps.get("data") or {}).get("categories", {}) if caps["status"] == "reported" else {}
        for mode, flags in categories.items():
            if mode not in MODES:
                continue
            key = state + "-" + mode
            url = API + "/" + state + "/" + mode
            result[key] = collector.capture(
                key, url, lambda body, mode=mode: parse_mode(json.loads(body), state, mode, now.date()))
            for dimension, capability in DIMENSIONS.items():
                if flags.get(capability) is not True:
                    continue
                key = state + "-" + mode + "-" + dimension
                result[key] = collector.capture(
                    key, url + "/demographics?by=" + dimension,
                    lambda body, mode=mode, dimension=dimension:
                    parse_demographics(json.loads(body), state, mode, dimension, now.date()))
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        for group in pool.map(provider, STATES):
            feeds.update(group)
    for state, url in OFFICIAL.items():
        def parse(body, state=state):
            data = parse_official(body, state)
            if state == "NC":
                data["complete_county_query"], data["county_reconciliation"] = reporting_counts(json.loads(body))
            return data
        key = state + "-official"
        feeds[key] = collector.capture(key, url, parse)
    granular = results_granular.collect(collector, baseline)
    for key, entry in prior.items():
        if key not in feeds:
            feeds[key] = {**copy.deepcopy(entry), "status": "retained_after_failure",
                          "error": "not_advertised_by_current_capabilities"}

    national = collector.capture("house-national", NATIONAL_URL,
                                lambda body: {"districts": districts(json.loads(body))})
    declared = (national.get("data") or {}).get("districts", previous.get("districts") or baseline_districts)
    house_prior = {**baseline_house, **previous.get("house", {})}
    house_collector = Collector(work, house_prior, collector.stopped, now, offline)
    house_collector.lock = collector.lock
    house_collector.stopped = collector.stopped
    # One shared guard/stop object prevents later requests after a host-level throttle.
    house_collector.guard = collector.guard
    house_collector.acquire = collector.acquire
    def capture_district(item):
        key, declaration = item
        if declaration["url"] is None:
            return key, copy.deepcopy(house_prior[key])
        return key, house_collector.capture(
            key, declaration["url"],
            lambda body: candidate_results(json.loads(body), declaration))
    with ThreadPoolExecutor(max_workers=4) as pool:
        house.update(pool.map(capture_district, sorted(declared.items())))
    feeds["house-national"] = national
    products = {}
    for state, declaration in config["jurisdictions"].items():
        url = declaration["url"]
        if declaration["status"] != "directory_link_unverified" or not url:
            directories[state] = {"status": declaration["status"], "url": url, "products": []}
            continue
        key = state + "-directory"
        result = collector.capture(key, url, lambda body: {"products": [
            {**link, "url": results_granular.transport_url(link["url"]),
             "requires_scope_or_parser_review": True}
            for link in discover_links(body, url, 2026) if results_granular.eligible_product(link)]})
        feeds[key] = result
        directories[state] = {"status": result["status"], "url": url,
                              "products": (result.get("data") or {}).get("products", [])}
        if result["status"] != "reported":
            continue
        for link in directories[state]["products"][:30]:
            if link["role"] != "download_candidate":
                continue
            identity = state + "-product-" + digest(link["url"].encode())[:16]
            products[identity] = collector.capture(identity, link["url"],
                lambda body, url=link["url"]: results_granular.factual_tables(body, url))
            feeds[identity] = products[identity]
    feeds.update(granular)
    inputs = {"feeds": feeds, "house": house, "districts": declared, "directories": directories,
              "granular": granular, "products": products}
    inputs["source_stops"] = collector.stopped
    write(work / "state.json", inputs)
    outputs = project(inputs, baseline)
    outputs.update(extras)
    package_members = {"inputs/selected-source-facts.json": encoded(inputs),
                       "inputs/registry.json": encoded(config),
                       **{"inputs/accepted-counts/" + key: body for key, body in baseline.items()},
                       **{"queries/" + key: body for key, body in outputs.items()}}
    code = ("results_intake.py", "results_house.py", "results_granular.py", "results_native.py",
             "results_pdf_ocr.py", "native_tabular.py",
            "nationwide.py", "current.py", "download.py",
            "precinct_source_batch.py", "house_clerk_endpoints.py",
            "participation_intake/__init__.py", "participation_intake/engine.py",
            "participation_intake/contract.py", "participation_intake/adapters.py",
            "participation_intake/publisher.py")
    for name in code:
        package_members["code/scripts/" + name] = (ROOT / "scripts" / name).read_bytes()
    for name in ("test_results_intake.py", "test_results_granular.py", "test_results_native.py",
                 "test_nationwide.py", "test_current.py"):
        package_members["code/tests/" + name] = (ROOT / "tests" / name).read_bytes()
    version = digest(encoded({"inputs": inputs, "baseline": config["baseline"],
                              "outputs": {name: pin(body) for name, body in outputs.items()},
                              "code": {name: pin(body) for name, body in package_members.items()
                                       if name.startswith("code/")}}))
    package_members["code/reproduce.py"] = (
        "from pathlib import Path\nimport sys\n"
        "sys.path.insert(0,str(Path(__file__).resolve().parent))\n"
        "from scripts.results_intake import main\nmain()\n").encode()
    package_members["REPRODUCE.txt"] = (
        "Requires Python >=3.9 and requests>=2.31 (the project's existing dependency).\n"
        "python3 code/reproduce.py replay --package . --output reproduced\n"
        "Replays all complete numerical queries from selected facts and the full accepted baseline.\n"
        "Does not reacquire sources, extract excluded publisher HTML, fit models or certify results.\n").encode()
    package_members["checksums.json"] = encoded({key: pin(body) for key, body in package_members.items()})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for name, body in sorted(package_members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name, body in {**outputs, "complete-results.zip": buffer.getvalue()}.items():
        (work / name).write_bytes(body)
    write(work / "state.json", inputs)
    report = {"passed": True, "version": version, "checked_at": now.isoformat(),
              "jurisdictions": 51, "house_districts_declared": len(declared),
              "house_districts_available": sum(item.get("data") is not None for item in house.values()),
              "source_attempts": collector.attempts + house_collector.attempts,
              "files": {name: pin((work / name).read_bytes()) for name in (*outputs, "complete-results.zip")}}
    write(work / "report.json", report)
    return report


def replay(package, output):
    package, output = Path(package), Path(output)
    if output.exists():
        raise ValueError("Reproduction needs a fresh output directory")
    manifest = read(package / "checksums.json")
    for name, expected in manifest.items():
        if pin((package / str(relative(name))).read_bytes()) != expected:
            raise ValueError("Changed complete packet member: " + name)
    config = read(package / "inputs/registry.json")
    baseline = baseline_inputs(package / "inputs/accepted-counts", config["baseline"])
    outputs = project(read(package / "inputs/selected-source-facts.json"), baseline)
    for name in config.get("accepted_queries", {}):
        body = (package / "queries" / str(relative(name))).read_bytes()
        expected = config["accepted_queries"][name]
        if pin(body) != {key: expected[key] for key in ("bytes", "sha256")}:
            raise ValueError("Accepted numerical query changed")
        outputs[name] = body
    if set("queries/" + name for name in outputs) != {name for name in manifest if name.startswith("queries/")}:
        raise ValueError("Incomplete numerical query inventory")
    for name, body in outputs.items():
        if body != (package / "queries" / name).read_bytes():
            raise ValueError("Numerical reproduction differs: " + name)
    output.mkdir()
    for name, body in outputs.items():
        (output / name).write_bytes(body)
    return {"passed": True, "complete_outputs": len(outputs), "network_requests": 0}


def publisher_state(repository, ref, github_repository, work):
    publisher = GitPublisher(repository, ref=ref, github_repository=github_repository)
    parent = publisher.remote_head()
    if parent:
        publisher.git("fetch", "--no-tags", "--depth=1", "--filter=blob:none",
                      publisher.remote, "refs/heads/" + ref)
        prior = json.loads(publisher.git("show", parent + ":state.json"))
    else:
        prior = {}
    write(Path(work) / "publication-parent.json", {"parent": parent})
    return publisher, prior


def publish(repository, ref, github_repository, work):
    work = Path(work)
    publisher = GitPublisher(repository, ref=ref, github_repository=github_repository)
    parent = read(work / "publication-parent.json")["parent"]
    stopped = stops(read(work / "source-stops.json"))
    report_path = work / "report.json"
    if not report_path.exists():
        bodies = {"source-stops.json": encoded(stopped)}
        if parent:
            prior = json.loads(publisher.git("show", parent + ":state.json"))
            prior["source_stops"] = merge_stops(prior["source_stops"], stopped)
            bodies["state.json"] = encoded(prior)
        else:
            bodies["state.json"] = encoded({"source_stops": stopped})
        commit = publisher.commit(publisher.tree(parent, bodies), parent,
                                  "Preserve election source access holds after interrupted intake")
        publisher.promote(commit, parent)
        raise ValueError("Intake failed; durable stops preserved and last valid results retained")
    report = read(report_path)
    if not report["passed"] or report["jurisdictions"] != 51:
        raise ValueError("Unvalidated current results")
    if parent:
        latest = json.loads(publisher.git("show", parent + ":latest.json", check=False) or "{}")
        if latest.get("version") == report["version"]:
            return {"status": "unchanged", "data_commit": parent}
    bodies = {}
    prefix = "snapshots/" + report["version"] + "/"
    for name, expected in report["files"].items():
        body = (work / str(relative(name))).read_bytes()
        if pin(body) != expected:
            raise ValueError("Changed validated publication output")
        bodies[prefix + name] = body
    bodies.update({"state.json": (work / "state.json").read_bytes(),
                   "source-stops.json": encoded(stopped)})
    staged = publisher.commit(publisher.tree(parent, bodies), parent,
                              "Preserve validated complete election results " + report["version"][:12])
    publisher.promote(staged, parent)
    publisher.verify_files(staged, {name: pin(body) for name, body in bodies.items()})
    latest = {"contract": "participation.automatic_results_latest.v1", "version": report["version"],
              "checked_at": report["checked_at"], "results_commit": staged,
              "base_url": f"https://raw.githubusercontent.com/{github_repository}/{staged}/{prefix}",
              "files": report["files"], "all_states_certified": False}
    promoted_bodies = {"latest.json": encoded(latest), "state.json": (work / "state.json").read_bytes(),
                       "source-stops.json": encoded(stopped)}
    promoted = publisher.commit(publisher.tree(staged, promoted_bodies), staged,
                                "Activate current validated election results and persistent source states")
    publisher.promote(promoted, staged)
    publisher.verify_files(promoted, {name: pin(body) for name, body in promoted_bodies.items()})
    return {"status": "published", "data_commit": promoted, "results_commit": staged, **latest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("collect")
    capture.add_argument("--registry", type=Path, required=True)
    capture.add_argument("--work-dir", type=Path, required=True)
    capture.add_argument("--repository", type=Path, default=ROOT)
    capture.add_argument("--ref", default="results-data")
    capture.add_argument("--github-repository", default="hanshanley/voter-participation")
    capture.add_argument("--offline", action="store_true")
    upload = commands.add_parser("publish")
    for action in (upload,):
        action.add_argument("--work-dir", type=Path, required=True)
        action.add_argument("--repository", type=Path, default=ROOT)
        action.add_argument("--ref", default="results-data")
        action.add_argument("--github-repository", default="hanshanley/voter-participation")
    reproduce = commands.add_parser("replay")
    reproduce.add_argument("--package", type=Path, required=True)
    reproduce.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "collect":
        _, previous = publisher_state(args.repository, args.ref, args.github_repository, args.work_dir)
        result = collect(args.registry, args.work_dir, previous, offline=args.offline)
    elif args.command == "publish":
        result = publish(args.repository, args.ref, args.github_repository, args.work_dir)
    else:
        result = replay(args.package, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
