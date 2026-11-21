"""Refresh reviewed election feeds; preserve independent results and durable access holds."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from functools import partial
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import threading
import time
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
from scripts import results_state_statistics
from scripts import results_native_broome
from scripts import results_congress


OFFICIAL = {**OFFICIAL, **results_state_statistics.OFFICIAL}


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "participation.automatic_results_registry.v1"
STATE_CONTRACT = "participation.automatic_results_compressed_state.v1"
MAX_STATE_BYTES = 400_000_000
MAX_RECOVERY_NON_STATE_BYTES = 100_000_000
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


GRANULAR_ALIAS_CONTRACT = "participation.granular_state_alias.v1"
GRANULAR_ALIAS_QUALIFICATION = (
    "Lossless duplicate indexed to the complete granular state entry.")
GRANULAR_ALIAS_KEYS = {
    "contract", "granular_key", "data_pin", "qualification"}


def _is_granular_alias_candidate(value):
    return isinstance(value, dict) and (
        value.get("contract") == GRANULAR_ALIAS_CONTRACT
        or {"granular_key", "data_pin"} <= set(value))


def _validate_granular_alias(identity, alias, full_data):
    if full_data is None:
        raise ValueError("Collector granular alias has no full data")
    if not isinstance(alias, dict) or set(alias) != GRANULAR_ALIAS_KEYS:
        raise ValueError("Collector granular alias shape differs")
    if alias["contract"] != GRANULAR_ALIAS_CONTRACT:
        raise ValueError("Collector granular alias contract differs")
    if alias["granular_key"] != identity:
        raise ValueError("Collector granular alias key differs")
    if alias["qualification"] != GRANULAR_ALIAS_QUALIFICATION:
        raise ValueError("Collector granular alias qualification differs")
    if alias["data_pin"] != pin(encoded(full_data)):
        raise ValueError("Collector granular alias pin differs")


def compact_collector_state(state):
    result = copy.deepcopy(state)
    granular = result.get("granular", {})
    feeds = result.get("feeds", {})
    for identity, entry in feeds.items():
        feed_data = entry.get("data")
        if identity not in granular and _is_granular_alias_candidate(feed_data):
            raise ValueError("Collector granular alias target is missing")
    for identity, entry in granular.items():
        if identity not in feeds:
            continue
        feed_data = feeds[identity].get("data")
        full_data = entry.get("data")
        if _is_granular_alias_candidate(full_data):
            raise ValueError("Collector granular full data is an alias")
        if full_data is None:
            if _is_granular_alias_candidate(feed_data):
                raise ValueError("Collector granular alias has no full data")
            continue
        if feed_data != full_data:
            _validate_granular_alias(identity, feed_data, full_data)
            continue
        full_data = copy.deepcopy(full_data)
        granular[identity] = copy.deepcopy(entry)
        feeds[identity] = copy.deepcopy(feeds[identity])
        feeds[identity]["data"] = {
            "contract": GRANULAR_ALIAS_CONTRACT,
            "granular_key": identity,
            "data_pin": pin(encoded(full_data)),
            "qualification": GRANULAR_ALIAS_QUALIFICATION,
        }
    return result


def hydrate_collector_state(state):
    result = copy.deepcopy(state)
    granular = result.get("granular", {})
    for identity, entry in result.get("feeds", {}).items():
        feed_data = entry.get("data")
        if identity not in granular:
            if _is_granular_alias_candidate(feed_data):
                raise ValueError("Collector granular alias target is missing")
            continue
        full_data = granular[identity].get("data")
        if _is_granular_alias_candidate(full_data):
            raise ValueError("Collector granular full data is an alias")
        if feed_data == full_data:
            continue
        _validate_granular_alias(identity, feed_data, full_data)
        entry["data"] = copy.deepcopy(full_data)
    return result


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
        self.started_monotonic = time.monotonic()
        self.stopped, self.offline = stops(stopped), offline
        self.lock, self.context = threading.Lock(), threading.local()
        self.attempts, self.bodies = [], {}
        self.shared_acquisition_errors = {}
        write(self.work / "source-stops.json", self.stopped)

    def observation_time(self):
        return self.now + timedelta(seconds=max(0, time.monotonic() - self.started_monotonic))

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

    def public_edition(self, url):
        source = self.context.store.db.execute(
            "SELECT sha,etag,modified,stopped FROM inputs WHERE url=?", (url,)).fetchone()
        if not source or not source[0] or source[3]:
            raise ValueError("Source edition requires an accepted cached original")
        return {"body_sha256": source[0], "http_etag": source[1],
                "http_last_modified": source[2],
                "qualification": "HTTP representation edition, not a native count-update clock"}

    def capture(self, identity, url, parser, *, equivalent=None, shared_acquisition=False):
        old = self.prior.get(identity)
        stage, attempted_pin = "acquisition", None
        try:
            if shared_acquisition and url in self.shared_acquisition_errors:
                self.guard(url)
                raise IntakeError(*self.shared_acquisition_errors[url])
            try:
                body, receipt = self.acquire(url)
            except IntakeError as error:
                if shared_acquisition:
                    self.shared_acquisition_errors[url] = (source_error(error), str(error))
                raise
            stage, attempted_pin = "parsing", pin(body)
            data = parser(body)
            if (old and old.get("data") and data.get("date") and old["data"].get("date")
                    and data["date"] < old["data"]["date"]):
                raise ValueError("Source data date regressed")
            source = {"url": url, **pin(body)}
            same_facts = (equivalent is not None and old and old.get("data") is not None
                          and (old.get("source") or {}).get("url") == url
                          and equivalent(old["data"], data))
            if same_facts or (old and old.get("source") == source and old.get("data") == data):
                result = copy.deepcopy(old)
                result.update(status="reported", error=None)
            else:
                result = {"status": "reported", "data": data, "source": source, "error": None,
                          "first_observed_at": self.now.isoformat()}
            attempt = {"id": identity, "status": receipt["origin"], **source}
            if same_facts and old["source"] != source:
                # Volatile transport bytes do not replace the exact prior analytical input.
                attempt["accepted_equivalent_source"] = old["source"]
                attempted_pin = {key: old["source"][key] for key in ("bytes", "sha256")}
            result.update(error_detail=None, error_stage=None)
        except Exception as error:
            code = source_error(error)
            result = copy.deepcopy(old) if old and old.get("data") is not None else {
                "data": None, "source": None, "first_observed_at": None}
            result.update(status="retained_after_failure" if result["data"] is not None else code,
                          error=code, error_stage=stage,
                          error_detail=str(error) if isinstance(error, (ValueError, IntakeError)) else None)
            attempt = {"id": identity, "url": url, "status": code}
        result.update(attempted_source_url=url, attempted_source_pin=attempted_pin)
        with self.lock:
            self.attempts.append(attempt)
        return result


def numeric_observations(baseline, feeds, granular_reference=None, granular_keys=()):
    rows = []
    index = json.loads(baseline["index.json"])
    for state, item in sorted(index["states"].items()):
        shard = json.loads(gzip.decompress(baseline[item["file"]]))
        for row in shard["records"]:
            rows.append({"state_code": state, "channel": "accepted_canonical_observation",
                         "id": row["id"], "observation": row})
    for identity, entry in sorted(feeds.items()):
        if (entry.get("data") is not None and identity.split("-")[0] in STATES
                and not identity.endswith(("-capabilities", "-directory"))
                and entry["data"].get("participation_observation_qualified") is not False
                and entry["data"].get("numerical_data_qualified") is not False):
            observation = entry["data"]
            if identity in granular_keys:
                if not isinstance(granular_reference, dict):
                    raise ValueError("Granular observation externalization requires its full query")
                data = observation if isinstance(observation, dict) else {}
                updates = data.get("updates")
                summary = {
                    key: value for key, value in data.items()
                    if value is None or isinstance(value, (bool, int, float, str))
                }
                if isinstance(updates, list):
                    summary["projected_updates"] = {
                        "records": len(updates),
                        "reported": sum(item.get("value") is not None for item in updates),
                        "unknown": sum(item.get("value") is None for item in updates),
                        "observation_ids_pin": digest(encoded(sorted(
                            item["id"] for item in updates))),
                    }
                observation = {
                    "contract": "participation.externalized_native_query.v1",
                    "summary": summary,
                    "full_data": {
                        **granular_reference, "key": identity,
                        "qualification": (
                            "Lossless exact native data externalized from the bounded snapshot."),
                    },
                }
            rows.append({"state_code": identity.split("-")[0], "channel": identity,
                         "status": entry["status"], "source": entry["source"],
                         "observation": observation})
    return rows


def snapshot_granular_sources(granular, query_reference):
    """Reference exact replay data instead of duplicating it inside the bounded snapshot."""
    result = copy.deepcopy(granular)
    for identity, entry in result.items():
        data = entry.get("data")
        if data is None:
            continue
        if not isinstance(data, dict):
            continue
        updates = data.get("updates")
        summary = {
            key: value for key, value in data.items()
            if value is None or isinstance(value, (bool, int, float, str))
        }
        if isinstance(updates, list):
            summary["projected_updates"] = {
                "records": len(updates),
                "reported": sum(update.get("value") is not None for update in updates),
                "unknown": sum(update.get("value") is None for update in updates),
                "observation_ids_pin": digest(encoded(sorted(update["id"] for update in updates))),
            }
        bridge = data.get("reviewed_source_url_bridge")
        compact = {
            "summary": summary,
            "full_data": {
                **query_reference,
                "key": identity,
                "qualification": "Exact full native query and replay updates retained externally.",
            },
        }
        if isinstance(bridge, dict):
            compact["reviewed_source_url_bridge"] = bridge
        entry["data"] = compact
    return result


def project(inputs, baseline):
    feeds, house, declared = (inputs[key] for key in ("feeds", "house", "districts"))
    granular_query = compressed(encoded(inputs.get("granular", {})))
    granular_reference = {"file": "granular-source-queries.json.gz", **pin(granular_query)}
    observations = numeric_observations(
        baseline, feeds, granular_reference, set(inputs.get("granular", {})))
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
    status_entries = {**feeds, **inputs.get("granular", {}), **{"house-" + k: v for k, v in house.items()}}
    status_rows = [{"source": key, "status": entry["status"], "error": entry.get("error"),
                    "data_retained": entry.get("data") is not None,
                    "source_url": (entry.get("source") or {}).get("url")
                        or entry.get("attempted_source_url"),
                    "attempted_source_url": entry.get("attempted_source_url"),
                    "error_stage": entry.get("error_stage"),
                    "error_detail": entry.get("error_detail"),
                    **({"archive_check_week_utc": entry["archive_check_week_utc"]}
                       if "archive_check_week_utc" in entry else {})}
                   for key, entry in sorted(status_entries.items())]
    products_query = compressed(encoded(inputs.get("products", {})))
    products_reference = {"file": "declared-numerical-queries.json.gz", **pin(products_query)}
    products_index = {
        identity: {**{key: value for key, value in entry.items() if key != "data"},
                   "factual_data_available": entry.get("data") is not None,
                   "complete_factual_query": {**products_reference, "key": identity}}
        for identity, entry in inputs.get("products", {}).items()}
    snapshot = {
        "contract": "participation.automatic_results_snapshot.v1", "election_date": "2026-11-03",
        "jurisdictions": coverage, "participation_observations": observations,
        "house_candidates": candidates, "house_states": house_states,
        "source_status": status_rows, "declared_products": inputs["directories"],
        "behavioral_models_refitted": False, "geographic_joins_changed": False,
        "all_states_certified_or_precinct_complete": False,
        "source_clock_not_replaced_by_retrieval_time": True,
        "baseline_and_fresh_source_frames_are_separate_not_added": True,
        "granular_sources": snapshot_granular_sources(
            inputs.get("granular", {}), granular_reference),
        "declared_numerical_products": products_index,
    }
    if "collection_scope" in inputs:
        snapshot["collection_scope"] = inputs["collection_scope"]
    if "congress" in inputs:
        snapshot["congress"] = inputs["congress"]
    from scripts import results_uf_turnout
    uf = feeds.get(results_uf_turnout.IDENTITY)
    if uf is not None:
        snapshot["uf_turnout"] = copy.deepcopy(uf)
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
        snapshot["declared_numerical_products_query"] = products_reference
        outputs["snapshot.json.gz"] = compressed(encoded(snapshot))
        outputs["granular-source-queries.json.gz"] = granular_query
        outputs["declared-numerical-queries.json.gz"] = products_query
        outputs["canonical-local-changes.csv"] = csv_body(changes)
    if "congress" in inputs:
        outputs.update(results_congress.exports(inputs["congress"]))
        outputs["congress-queries.json.gz"] = compressed(encoded(inputs["congress"]))
        outputs["snapshot.json.gz"] = compressed(encoded(snapshot))
    if uf is not None and uf.get("data") is not None:
        outputs.update(results_uf_turnout.exports(uf))
    return outputs


def registry_config(registry_path):
    registry_path = Path(registry_path)
    config = read(registry_path)
    congressional = registry_path.with_name("congress.json")
    if congressional.exists():
        declaration = read(congressional)
        if (declaration.get("contract") != "participation.congressional_provider.v1"
                or declaration.get("election_date") != config["election_date"]
                or set(declaration.get("feeds", {})) != {"house", "senate"}):
            raise ValueError("Invalid reviewed congressional provider configuration")
        config["congressional"] = declaration
        config["source_stops"] = merge_stops(config["source_stops"], declaration["source_stops"])
    uf_path = registry_path.with_name("uf-turnout.json")
    if uf_path.exists():
        from scripts.results_uf_turnout import CONFIG
        declaration = read(uf_path)
        if declaration != CONFIG:
            raise ValueError("Invalid reviewed statewide UF provider configuration")
        config["uf_turnout"] = declaration
    official_path = registry_path.with_name("official-congress.json")
    if official_path.exists():
        from scripts.results_official_congress import source_ids
        declaration = read(official_path)
        source_ids(declaration)
        config["official_congress"] = declaration
    return config


def collect(registry_path, work, previous=None, now=None, offline=False):
    registry_path, work = Path(registry_path), Path(work)
    config = registry_config(registry_path)
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
    previous = hydrate_collector_state(previous)
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
    collector = Collector(work, {**previous.get("granular", {}), **prior}, stopped, now, offline)
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
            data = (results_state_statistics.statistics(body, state)
                    if state in results_state_statistics.OFFICIAL else parse_official(body, state))
            if state == "NC":
                data["complete_county_query"], data["county_reconciliation"] = reporting_counts(json.loads(body))
            return data
        key = state + "-official"
        feeds[key] = collector.capture(key, url, parse)
    feeds[results_native_broome.IDENTITY] = results_native_broome.collect_statistics(collector)
    if "uf_turnout" in config:
        from scripts import results_uf_turnout
        feeds[results_uf_turnout.IDENTITY] = results_uf_turnout.collect(collector, config["uf_turnout"])
    if "official_congress" in config:
        from scripts import results_official_congress
        feeds.update(results_official_congress.collect_sources(collector, config["official_congress"]))
    from scripts.louisiana_bootstrap import IDENTITY as LA_BOOTSTRAP_ID
    from scripts.louisiana_bootstrap import collect_bootstrap as collect_la_bootstrap
    la_bootstrap = collect_la_bootstrap(
        collector, baseline, config.get("louisiana_post_election_authority"))
    granular = results_granular.collect(collector, baseline)
    if la_bootstrap.get("status") == "reported":
        granular[LA_BOOTSTRAP_ID] = la_bootstrap
    else:
        feeds[LA_BOOTSTRAP_ID] = la_bootstrap
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
    from scripts.results_native_congress import derive as derive_native_congress
    feeds = derive_native_congress(feeds)
    inputs = {"feeds": feeds, "house": house, "districts": declared, "directories": directories,
              "granular": granular, "products": products}
    if "congressional" in config:
        inputs["congress"] = results_congress.collect(
            collector, previous.get("congress"), config["congressional"])
        if "official_congress" in config:
            inputs["congress"] = results_official_congress.attach(inputs["congress"], feeds)
    inputs["source_stops"] = collector.stopped
    return export_collection(
        work, config, baseline, inputs, extras, now,
        collector.attempts + house_collector.attempts)


def export_collection(work, config, baseline, inputs, extras, now, source_attempts):
    from scripts.bulk_participation_archives import original_inventory
    from scripts.results_turnout_history import county_archive_originals

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    write(work / "source-stops.json", inputs["source_stops"])
    stored_inputs = compact_collector_state(inputs)
    write(work / "state.json", stored_inputs)
    outputs = project(inputs, baseline)
    outputs.update(extras)
    package_members = {"inputs/selected-source-facts.json": encoded(stored_inputs),
                       "inputs/registry.json": encoded(config),
                       **{"inputs/accepted-counts/" + key: body for key, body in baseline.items()},
                       **{"queries/" + key: body for key, body in outputs.items()}}
    originals = county_archive_originals(stored_inputs.get("granular", {}))
    if originals:
        package_members["inputs/county-report-originals.json"] = encoded(originals)
    bulk_originals = original_inventory(stored_inputs.get("granular", {}))
    if bulk_originals:
        package_members["inputs/bulk-report-originals.json"] = encoded(bulk_originals)
    code = ("results_intake.py", "results_house.py", "results_congress.py", "results_granular.py", "results_native.py",
             "results_state_statistics.py", "results_uf_turnout.py", "results_official_congress.py",
             "results_aspx_congress.py", "results_native_congress.py", "results_json_congress.py",
             "results_clarity_congress.py", "results_connecticut_congress.py",
             "congressional_complete_categories.py", "protected_official_house.py",
             "protected_official_wyoming.py",
             "results_native_delaware.py", "results_native_dc.py",
             "results_native_state_family.py", "results_native_oregon.py",
             "results_native_north_carolina.py",
             "results_native_rhode_island.py",
             "results_native_utah.py",
             "results_native_idaho.py",
             "results_native_virginia.py", "results_native_north_dakota.py",
             "results_native_louisiana.py", "results_native_louisiana_runtime.py",
             "louisiana_onboarding.py", "louisiana_bootstrap.py", "louisiana_group_history.py",
             "results_native_broome.py", "results_native_kansas.py",
             "participation_count_additions.py",
             "results_pdf_ocr.py", "results_pdf_archive_ocr.py", "results_pdf_tables.py", "results_pdf_boston.py",
             "results_pdf_grids.json",
             "results_json_statistics.py", "automatic_native_refresh.py",
             "results_pdf_periodic.py", "results_pdf_periodic_grids.json",
             "results_pdf_periodic_ocr.py", "results_pdf_periodic_sussex.json",
             "results_pdf_affiliations.py", "results_pdf_jefferson.py",
             "results_pdf_cass.py", "results_pdf_dunn.py", "results_pdf_cole.py",
             "results_pdf_platte.py", "results_pdf_county_parent.py", "results_minnesota_turnout.py",
             "philadelphia_divisions.py",
             "results_turnout_history.py", "national_turnout_release_watch.py", "washington_participation.py",
             "oregon_turnout_history.py", "retained_bulk_turnout.py", "southeast_turnout.py", "alabama_precinct_history.py",
             "alaska_precinct_history.py", "alaska_cards_history.py", "alaska_age_history.py", "connecticut_turnout_history.py",
             "bulk_participation_archives.py", "connecticut_2018_verified_scan.json", "kansas_turnout_history.py",
             "virginia_precinct_turnout.py", "virginia_bulk_turnout.py", "virginia_absentee_history.py",
             "hawaii_turnout_history.py", "hawaii_precinct_turnout.py", "dakota_turnout_history.py",
             "new_jersey_periodic_counties.py",
             "north_carolina_participation.py", "california_media.py", "california_turnout_history.py",
             "indiana_early_state_turnout.py", "indiana_early_county_turnout.py", "pa_audit_ballots.py",
             "south_carolina_voter_statistics.py",
             "wyoming_participation_statistics.py", "nebraska_canvass.py",
             "nebraska_county_reports.py",
             "colorado_voting_statistics.py", "maryland_precinct_history.py", "minnesota_precinct_history.py",
             "results_indiana_turnout.py", "results_nc_vote_history.py",
             "results_ca_county_scan_transcriptions.json",
             "results_pa_vote_history.py", "results_alaska_turnout.py",
             "native_pdf.py", "pdf_group_queries.py", "native_tabular.py", "native_products.py",
            "nationwide.py", "current.py", "download.py",
            "precinct_source_batch.py", "house_clerk_endpoints.py",
            "participation_intake/__init__.py", "participation_intake/engine.py",
            "participation_intake/contract.py", "participation_intake/adapters.py",
            "participation_intake/publisher.py")
    for name in code:
        package_members["code/scripts/" + name] = (ROOT / "scripts" / name).read_bytes()
    for name in ("test_results_intake.py", "test_california_turnout_history.py", "test_results_congress.py",
                 "test_results_granular.py", "test_results_native.py",
                 "test_results_state_statistics.py", "test_results_uf_turnout.py",
                 "test_results_official_congress.py", "test_results_aspx_congress.py",
                 "test_results_native_congress.py",
                 "test_results_json_congress.py",
                 "test_results_clarity_congress.py",
                 "test_congressional_complete_categories.py",
                 "test_protected_official_house.py",
                 "test_protected_official_wyoming.py",
                 "test_results_native_delaware.py", "test_results_native_dc.py",
                 "test_results_native_broome.py", "test_results_native_kansas.py",
                 "test_results_native_workbooks.py",
                 "test_results_pdf_tables.py", "test_results_pdf_boston.py",
                 "test_results_json_statistics.py", "test_results_pdf_periodic.py",
                 "test_results_pdf_affiliations.py", "test_results_pdf_jefferson.py",
                 "test_results_pdf_cass.py", "test_results_native_cass.py",
                 "test_results_pdf_dunn.py", "test_results_pdf_cole.py",
                 "test_results_pdf_platte.py",
                 "test_results_native_state_family.py", "test_results_native_oregon.py",
                 "test_results_native_north_carolina.py",
                 "test_results_native_rhode_island.py",
                 "test_results_native_utah.py",
                 "test_results_native_idaho.py",
                 "test_results_native_virginia.py",
                 "test_results_native_virginia_repair.py",
                 "test_results_native_north_dakota.py",
                 "test_results_native_north_dakota_repair.py",
                 "test_results_intake_north_dakota_package.py",
                 "test_louisiana_onboarding.py",
                 "test_automatic_native_refresh.py",
                 "test_nationwide.py", "test_current.py", "test_wyoming_participation_statistics.py"):
        package_members["code/tests/" + name] = (ROOT / "tests" / name).read_bytes()
    name = "tests/nd_native_fixture_support.py"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    for name in ("accepted-templates.json.gz", "nd-complete-facts.json.gz"):
        relative_name = "tests/fixtures/nd-native-automatic/" + name
        package_members["code/" + relative_name] = (ROOT / relative_name).read_bytes()
    for name in ("accepted-reporting.json.gz", "accepted-templates.json.gz",
                 "fixture-manifest.json"):
        relative_name = "tests/fixtures/north-carolina-native/" + name
        package_members["code/" + relative_name] = (ROOT / relative_name).read_bytes()
    for name in ("complete-products.json.gz", "sussex-ocr-views.json.gz"):
        package_members["code/tests/fixtures/results_pdf_periodic/" + name] = (
            ROOT / "tests/fixtures/results_pdf_periodic" / name).read_bytes()
    name = "tests/fixtures/results_pdf_jefferson/complete-pages.json.gz"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/dunn-accepted.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/oregon-accepted.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/virginia-federal-candidates.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/oregon-federal-candidates.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/utah-federal-candidates.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/iowa-clarity-federal-facts.json.gz"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/rhode-island-native-accepted.json.gz"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/ri-official-congress.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    name = "tests/fixtures/ri-official-senate.json"
    package_members["code/" + name] = (ROOT / name).read_bytes()
    from scripts.protected_official_wyoming import FACTS_PATH as WY_FACTS_PATH
    package_members["code/" + WY_FACTS_PATH] = (ROOT / WY_FACTS_PATH).read_bytes()
    fixture_root = ROOT / "tests/fixtures/utah-native"
    for path in sorted(fixture_root.rglob("*")):
        if path.is_file():
            package_members["code/" + str(path.relative_to(ROOT))] = path.read_bytes()
    name = "tests/fixtures/dc-native-accepted.json"
    broome_fixture = "tests/fixtures/broome-contest-2026.json"
    package_members["code/" + broome_fixture] = (ROOT / broome_fixture).read_bytes()
    fixture_root = ROOT / "tests/fixtures/idaho-native"
    for path in sorted(fixture_root.rglob("*")):
        if path.is_file():
            package_members["code/" + str(path.relative_to(ROOT))] = path.read_bytes()
    package_members["code/" + name] = (ROOT / name).read_bytes()
    for name in ("accepted-de-shard.json", "complete-turnout.json"):
        relative_name = "tests/fixtures/delaware-native/" + name
        package_members["code/" + relative_name] = (ROOT / relative_name).read_bytes()
    for fixture in ("authority-resolution.json", "route-authority.json",
            "election-dates.json", "state-source-declaration.json",
            "parish-source-declaration.json", "2026_1103_sta.xlsx",
            "2026_1103_par.xlsx"):
        name = "tests/fixtures/louisiana-native/" + fixture
        package_members["code/" + name] = (ROOT / name).read_bytes()
    fixture_root = ROOT / "tests/fixtures/louisiana-native/source-baseline"
    for path in sorted(fixture_root.rglob("*")):
        if path.is_file():
            name = "tests/fixtures/louisiana-native/source-baseline/" + str(
                path.relative_to(fixture_root))
            package_members["code/" + name] = path.read_bytes()
    name = "tests/LOUISIANA_ONBOARDING_TESTS.txt"
    package_members["code/" + name] = (ROOT / name).read_bytes()
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
    if originals:
        package_members["REPRODUCE.txt"] += (
            "\nOptional: independently re-extract the retained county reports.\n"
            "Place the exact publisher PDFs and CSVs in a local directory using the filenames and SHA-256\n"
            "checksums in inputs/county-report-originals.json. Use pypdf==6.16.0 and, for early scanned\n"
            "Nebraska reports, PyMuPDF==1.26.5 and rapidocr-onnxruntime==1.4.4. Then run:\n"
            "python3 code/reproduce.py replay --package . --output reproduced-from-originals"
            " --county-report-dir /path/to/originals\n"
            "This check makes no requests and never substitutes a newer edition for a missing original.\n"
        ).encode()
    if bulk_originals:
        package_members["REPRODUCE.txt"] += (
            "\nOptional: independently re-extract the Alaska age and Connecticut town reports.\n"
            "Use CPython 3.12 with pypdf==6.16.0, PyMuPDF==1.26.5 and rapidocr-onnxruntime==1.4.4.\n"
            "Place the exact publisher files in a local directory with the filenames and SHA-256\n"
            "checksums listed in inputs/bulk-report-originals.json. Then run:\n"
            "python3.12 code/reproduce.py replay --package . --output reproduced-from-bulk-originals"
            " --bulk-report-dir /path/to/originals\n"
            "The verification is offline; a newer edition does not replace a missing original.\n"
        ).encode()
    package_members["checksums.json"] = encoded({key: pin(body) for key, body in package_members.items()})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for name, body in sorted(package_members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
            archive.writestr(info, body)
    for name, body in {**outputs, "complete-results.zip": buffer.getvalue()}.items():
        (work / name).write_bytes(body)
    write(work / "state.json", stored_inputs)
    report = {"passed": True, "version": version, "checked_at": now.isoformat(),
              "jurisdictions": 51, "house_districts_declared": len(inputs["districts"]),
              "house_districts_available": sum(
                  item.get("data") is not None for item in inputs["house"].values()),
              "source_attempts": source_attempts,
              "files": {name: pin((work / name).read_bytes()) for name in (*outputs, "complete-results.zip")}}
    if "UF-national-turnout" in inputs["feeds"]:
        entry = inputs["feeds"]["UF-national-turnout"]
        rows = (entry.get("data") or {}).get("rows", [])
        report["uf_turnout"] = {
            "status": entry["status"], "version": (entry.get("data") or {}).get("version"),
            "jurisdiction_rows": sum(row["state_code"] != "US" for row in rows),
            "separate_us_rows": sum(row["state_code"] == "US" for row in rows),
            "ballot_status": dict(sorted(Counter(row["ballots_status"] for row in rows).items())),
            "error": entry.get("error"),
            "not_independently_certified_or_locally_allocated": True,
        }
    if "collection_scope" in inputs:
        report["collection_scope"] = inputs["collection_scope"]
    if "congress" in inputs:
        report["congressional"] = results_congress.summary(inputs["congress"])
    write(work / "report.json", report)
    return report


def refresh_congress(registry_path, work, previous, now=None, offline=False):
    registry_path, work = Path(registry_path), Path(work)
    config, now = registry_config(registry_path), now or datetime.now(timezone.utc)
    previous = hydrate_collector_state(previous)
    if ("congressional" not in config or len(previous.get("districts", {})) != 435
            or not all(key in previous for key in ("feeds", "house", "granular", "directories", "source_stops"))
            or set(previous["house"]) != set(previous["districts"])
            or set(previous["directories"]) != set(STATES)):
        raise ValueError("Congressional refresh requires the complete accepted collector state")
    baseline = baseline_inputs(registry_path.parent / config["baseline"]["root"], config["baseline"])
    extras = {}
    for name, declaration in config.get("accepted_queries", {}).items():
        body = (registry_path.parent / str(relative(declaration["file"]))).read_bytes()
        if pin(body) != {key: declaration[key] for key in ("bytes", "sha256")}:
            raise ValueError("Accepted query changed")
        extras[str(relative(name))] = body
    stopped = merge_stops(previous["source_stops"], config["source_stops"],
                         read(work / "source-stops.json") if (work / "source-stops.json").exists()
                         else config["source_stops"])
    collector = Collector(work, {}, stopped, now, offline=offline)
    inputs = copy.deepcopy(previous)
    inputs["congress"] = results_congress.collect(
        collector, previous.get("congress"), config["congressional"])
    if "official_congress" in config:
        from scripts import results_official_congress
        inputs["congress"] = results_official_congress.attach(inputs["congress"], previous["feeds"])
    inputs["source_stops"] = collector.stopped
    inputs["collection_scope"] = {
        "kind": "congressional_bulk_refresh", "chambers": ["house", "senate"],
        "all_noncongressional_inputs_retained_not_reacquired": True}
    return export_collection(work, config, baseline, inputs, extras, now, collector.attempts)


def late_archive_sources():
    from scripts import bulk_participation_archives, nebraska_county_reports
    from scripts import (
        results_indiana_turnout, results_minnesota_turnout, results_nc_vote_history,
        results_official_congress, results_pa_vote_history, results_uf_turnout,
    )
    from scripts import results_turnout_history as history

    return (
        history.KS_FEED, history.NJ_FEED, results_nc_vote_history.FEED, results_pa_vote_history.FEEDS[history.CURRENT_YEAR],
        history.TX_FEED, history.VA_FEED, history.WA_FEED, history.NC_HISTORY_FEED,
        history.WY_HISTORY_FEED, history.WY_CANVASS_FEED,
        results_uf_turnout.IDENTITY,
        *results_official_congress.source_ids(results_official_congress.CONNECTICUT_CONFIG),
        *results_minnesota_turnout.SOURCE_IDS,
        *results_indiana_turnout.FEEDS.values(),
        history.CA_CURRENT_FEED,
        nebraska_county_reports.FEED,
        *history.COUNTY_ARCHIVES,
        *bulk_participation_archives.collectors(),
        *sorted(history.municipal_feeds()),
    )


def selected_collection_scope(source_ids, *, congressional=False):
    return {
        "mode": "selected_registered_source_refresh",
        "source_ids": sorted(source_ids),
        "all_other_acquisitions_and_native_count_clocks_reused_not_retrieved_again": True,
        **({"congressional_provider_feeds_checked": ["house", "senate"]} if congressional else {}),
    }


def refresh_selected(registry_path, work, previous, source_ids, now=None, *, late_archives=False):
    from scripts import bulk_participation_archives, nebraska_county_reports
    from scripts import philadelphia_divisions, results_pa_vote_history, results_pdf_county_parent, results_turnout_history
    from scripts import results_indiana_turnout, results_minnesota_turnout, results_native, results_nc_vote_history
    from scripts import results_uf_turnout
    from scripts import results_official_congress

    administrative = {
        results_turnout_history.OH_FEED: results_turnout_history.collect_ohio,
        results_turnout_history.MT_FEED: results_turnout_history.collect_montana,
        results_turnout_history.WV_FEED: results_turnout_history.collect_west_virginia,
        results_turnout_history.ND_CANVASS_FEED: results_turnout_history.collect_north_dakota_canvass,
        results_turnout_history.GA_FEED: results_turnout_history.collect_georgia,
        results_turnout_history.KS_FEED: results_turnout_history.collect_kansas,
        results_turnout_history.NJ_FEED: results_turnout_history.collect_new_jersey,
        results_turnout_history.TX_FEED: results_turnout_history.collect_texas,
        results_turnout_history.VA_FEED: results_turnout_history.collect_virginia,
        results_turnout_history.WA_FEED: results_turnout_history.collect_washington,
        results_turnout_history.NC_HISTORY_FEED: results_turnout_history.collect_north_carolina_history,
        results_turnout_history.WY_HISTORY_FEED: results_turnout_history.collect_wyoming_history,
        results_turnout_history.WY_CANVASS_FEED: results_turnout_history.collect_wyoming_precinct_canvass,
        results_nc_vote_history.FEED: results_nc_vote_history.collect,
        results_pdf_county_parent.PHILADELPHIA_FEED: results_pdf_county_parent.collect_philadelphia,
        results_pdf_county_parent.SUMMIT_FEED: results_pdf_county_parent.collect_summit,
        results_pdf_county_parent.SUSSEX_FEED: results_pdf_county_parent.collect_sussex,
        results_pdf_county_parent.DOUGLAS_FEED: results_pdf_county_parent.collect_douglas,
        results_pdf_county_parent.OKTIBBEHA_FEED: results_pdf_county_parent.collect_oktibbeha,
        results_pdf_county_parent.WOODFORD_FEED: results_pdf_county_parent.collect_woodford,
        results_pdf_county_parent.LAWRENCE_FEED: results_pdf_county_parent.collect_lawrence,
        philadelphia_divisions.FEED: philadelphia_divisions.collect,
    }
    administrative.update({feed: partial(results_pa_vote_history.collect, year=year)
                           for year, feed in results_pa_vote_history.FEEDS.items()})
    administrative.update({feed: partial(results_indiana_turnout.collect, year=year)
                           for year, feed in results_indiana_turnout.FEEDS.items()})
    administrative.update({feed: partial(results_turnout_history.collect_county_archive, feed=feed)
                           for feed in (*results_turnout_history.COUNTY_ARCHIVES, results_turnout_history.CA_CURRENT_FEED)})
    administrative[nebraska_county_reports.FEED] = nebraska_county_reports.collect
    administrative.update(bulk_participation_archives.collectors())
    administrative.update({feed: capture for feed, (_, capture)
                           in results_turnout_history.municipal_feeds().items()})
    registry_path, work = Path(registry_path), Path(work)
    if late_archives and set(source_ids) != set(late_archive_sources()):
        raise ValueError("Weekly refresh requires the complete late archive scope")
    paired = set(results_minnesota_turnout.SOURCE_IDS)
    minnesota_ids = paired.intersection(source_ids)
    if minnesota_ids and minnesota_ids != paired:
        raise ValueError("Minnesota selected refresh requires both linked source IDs")
    config = registry_config(registry_path)
    now = now or datetime.now(timezone.utc)
    previous = hydrate_collector_state(previous)
    if (not source_ids or len(source_ids) != len(set(source_ids))
            or not all(item in administrative or item in paired
                or item in (results_uf_turnout.IDENTITY,) + results_official_congress.IDENTITIES or re.fullmatch(
                r"[A-Z]{2}-registered-[a-f0-9]{16}", item) for item in source_ids)
            or not {"feeds", "granular", "house", "districts", "directories", "source_stops"} <= set(previous)
            or config.get("contract") != CONTRACT or config.get("election_date") != "2026-11-03"
            or set(config["jurisdictions"]) != set(STATES)
            or len(previous["districts"]) != 435 or set(previous["house"]) != set(previous["districts"])):
        raise ValueError("Selected refresh requires complete accepted inputs and exact registered source IDs")
    baseline = baseline_inputs(registry_path.parent / config["baseline"]["root"], config["baseline"])
    plan = {key: value for sources in results_native.source_plan(baseline).values()
            for key, value in sources.items()}
    plan.update({key: {"adapter": "reviewed_administrative_participation"} for key in administrative})
    plan.update({key: {"adapter": "reviewed_administrative_participation"} for key in paired})
    if "uf_turnout" in config:
        plan[results_uf_turnout.IDENTITY] = {"adapter": "reviewed_statewide_uf_turnout"}
    if "official_congress" in config:
        plan.update({identity: {"adapter": "reviewed_official_candidate_evidence"}
                     for identity in results_official_congress.source_ids(config["official_congress"])})
    if not set(source_ids) <= set(plan):
        raise ValueError("Selected refresh source is not in the actual registered dispatch plan")
    if any(plan[identity]["adapter"] == "unadapted_primary_product" for identity in source_ids):
        raise ValueError("Selected numerical refresh requires a reviewed source adapter")
    stopped = merge_stops(config["source_stops"], previous["source_stops"],
                         read(work / "source-stops.json") if (work / "source-stops.json").exists()
                         else config["source_stops"])
    native_ids = set(source_ids) - {results_uf_turnout.IDENTITY, *results_official_congress.IDENTITIES}
    administrative_ids = native_ids & (administrative.keys() | paired)
    native_ids -= administrative_ids
    collector = Collector(work, {**previous["granular"], **previous["feeds"]}, stopped, now)
    entries = results_native.collect_sources(collector, baseline, source_ids=native_ids) if native_ids else {}
    entries.update((key, administrative[key](collector)) for key in source_ids if key in administrative)
    if minnesota_ids:
        entries.update(results_minnesota_turnout.collect_pair(collector, baseline))
    if results_uf_turnout.IDENTITY in source_ids:
        entries[results_uf_turnout.IDENTITY] = results_uf_turnout.collect(collector, config["uf_turnout"])
    official_ids = set(source_ids) & set(results_official_congress.IDENTITIES)
    if official_ids:
        entries.update(results_official_congress.collect_sources(
            collector, config["official_congress"], selected=official_ids))
    independent_holds = administrative_ids | (
        {results_uf_turnout.IDENTITY} | official_ids if late_archives else set())
    requested = set(source_ids)
    failures = {key: {"status": entries[key]["status"], "stage": entries[key].get("error_stage"),
                      "error": entries[key].get("error")}
                for key in entries.keys() - independent_holds if entries[key]["status"] != "reported"}
    if set(entries) != requested or failures:
        detail = json.dumps({"missing": sorted(requested - entries.keys()),
                             "unexpected": sorted(entries.keys() - requested), "failed": failures},
                            sort_keys=True)
        raise ValueError("Selected numerical refresh did not succeed; no replacement publication: " + detail)
    inputs = copy.deepcopy(previous)
    inputs["granular"].update({key: value for key, value in entries.items()
                               if key in native_ids or key in administrative_ids})
    # Full collections mirror granular entries in feeds; keep any existing mirror in sync.
    inputs["feeds"].update({key: value for key, value in entries.items()
                            if key not in administrative_ids or key in previous["feeds"]})
    from scripts.results_native_congress import PARENT_ID, derive as derive_native_congress
    if PARENT_ID in entries:
        inputs["feeds"] = derive_native_congress(inputs["feeds"])
    congressional = late_archives and "congressional" in config
    if congressional:
        inputs["congress"] = results_congress.collect(
            collector, previous.get("congress"), config["congressional"])
    if "congress" in inputs and "official_congress" in config:
        inputs["congress"] = results_official_congress.attach(inputs["congress"], inputs["feeds"])
    inputs["source_stops"] = collector.stopped
    inputs["collection_scope"] = selected_collection_scope(source_ids, congressional=congressional)
    extras = {}
    for name, declaration in config.get("accepted_queries", {}).items():
        body = (registry_path.parent / str(relative(declaration["file"]))).read_bytes()
        if pin(body) != {key: declaration[key] for key in ("bytes", "sha256")}:
            raise ValueError("Accepted query changed during selected refresh")
        extras[str(relative(name))] = body
    return export_collection(work, config, baseline, inputs, extras, now, collector.attempts)


def replay(package, output, *, county_report_dir=None, bulk_report_dir=None):
    from scripts.bulk_participation_archives import original_inventory, verify_original_reports
    from scripts.results_turnout_history import county_archive_originals, verify_county_archive_originals

    package, output = Path(package), Path(output)
    if output.exists():
        raise ValueError("Reproduction needs a fresh output directory")
    manifest = read(package / "checksums.json")
    for name, expected in manifest.items():
        if pin((package / str(relative(name))).read_bytes()) != expected:
            raise ValueError("Changed complete packet member: " + name)
    config = read(package / "inputs/registry.json")
    baseline = baseline_inputs(package / "inputs/accepted-counts", config["baseline"])
    state = hydrate_collector_state(read(package / "inputs/selected-source-facts.json"))
    entries = state.get("granular", {})
    original_manifest = "inputs/county-report-originals.json"
    if original_manifest in manifest and read(package / original_manifest) != county_archive_originals(entries):
        raise ValueError("County report original inventory differs from the accepted checkpoint")
    original_count = (verify_county_archive_originals(entries, Path(county_report_dir))
                      if county_report_dir is not None else None)
    bulk_manifest = "inputs/bulk-report-originals.json"
    if bulk_manifest in manifest and read(package / bulk_manifest) != original_inventory(entries):
        raise ValueError("Bulk report original inventory differs from the accepted checkpoint")
    bulk_count = (verify_original_reports(entries, Path(bulk_report_dir))
                  if bulk_report_dir is not None else None)
    outputs = project(state, baseline)
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
    result = {"passed": True, "complete_outputs": len(outputs), "network_requests": 0}
    if original_count is not None:
        result["county_report_originals_verified"] = original_count
    if bulk_count is not None:
        result["bulk_report_originals_verified"] = bulk_count
    return result


def pack_state(state):
    state = compact_collector_state(state)
    body = encoded(state)
    if len(body) > MAX_STATE_BYTES:
        raise ValueError("Complete collector state exceeds the size guard")
    return encoded({"contract": STATE_CONTRACT, "source_stops": stops(state["source_stops"]),
                    "decoded": pin(body),
                    "gzip_base64": base64.b64encode(compressed(body)).decode("ascii")})


def unpack_state(value):
    if not isinstance(value, dict):
        raise ValueError("Malformed complete collector state")
    if "contract" not in value:
        stops(value["source_stops"])
        return value
    if (value.get("contract") != STATE_CONTRACT
            or set(value) != {"contract", "source_stops", "decoded", "gzip_base64"}):
        raise ValueError("Unknown compressed collector state contract")
    expected = value["decoded"]
    if (not isinstance(expected, dict) or set(expected) != {"bytes", "sha256"}
            or type(expected["bytes"]) is not int
            or not 0 < expected["bytes"] <= MAX_STATE_BYTES):
        raise ValueError("Invalid complete collector state size")
    body = base64.b64decode(value["gzip_base64"], validate=True)
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
        decoded = stream.read(expected["bytes"] + 1)
    if pin(decoded) != expected:
        raise ValueError("Changed complete collector state")
    state = json.loads(decoded)
    if (not isinstance(state, dict)
            or stops(state["source_stops"]) != stops(value["source_stops"])):
        raise ValueError("Changed durable stops in complete collector state")
    return state


def restore(package, report_path, work, previous=None, latest=None, *, require_late_archive_scope=False):
    package, report_path, work = Path(package), Path(report_path), Path(work)
    if any((work / name).exists() for name in ("report.json", "state.json", "complete-results.zip")):
        raise ValueError("Recovery needs fresh publication outputs")
    report_body = report_path.read_bytes()
    report = json.loads(report_body)
    if (report.get("passed") is not True or report.get("jurisdictions") != 51
            or pin(package.read_bytes()) != report["files"]["complete-results.zip"]):
        raise ValueError("Changed or unvalidated completed collection")
    if latest and datetime.fromisoformat(latest["checked_at"]) > datetime.fromisoformat(report["checked_at"]):
        raise ValueError("A newer collection is already published; refusing recovery rollback")
    with tempfile.TemporaryDirectory(prefix="election-results-recovery-") as directory:
        root = Path(directory)
        state_member = "inputs/selected-source-facts.json"
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            if (len(names) != len(set(names)) or state_member not in names
                    or not 0 < archive.getinfo(state_member).file_size <= MAX_STATE_BYTES
                    or sum(item.file_size for item in archive.infolist()
                           if item.filename != state_member) > MAX_RECOVERY_NON_STATE_BYTES):
                raise ValueError("Invalid complete recovery packet inventory or size")
            manifest = json.loads(archive.read("checksums.json"))
            if set(names) != set(manifest) | {"checksums.json"}:
                raise ValueError("Incomplete recovery packet inventory")
            for name in names:
                path = root / str(relative(name))
                body = archive.read(name)
                if name != "checksums.json" and pin(body) != manifest[name]:
                    raise ValueError("Changed recovery packet member: " + name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
        state = read(root / state_member)
        config = read(root / "inputs/registry.json")
        if require_late_archive_scope:
            scope = state.get("collection_scope")
            if scope != report.get("collection_scope"):
                raise ValueError("Completed archive checkpoint report disagrees with its packet scope")
            if scope != selected_collection_scope(
                    late_archive_sources(), congressional="congressional" in config):
                return {"status": "superseded"}
        result = replay(root, root / "reproduced")
        query_names = {name.removeprefix("queries/") for name in manifest if name.startswith("queries/")}
        if set(report["files"]) != query_names | {"complete-results.zip"}:
            raise ValueError("Incomplete completed collection report")
        for name in query_names:
            if pin((root / "queries" / name).read_bytes()) != report["files"][name]:
                raise ValueError("Changed completed collection query")
        version = digest(encoded({
            "inputs": hydrate_collector_state(state), "baseline": config["baseline"],
            "outputs": {name: report["files"][name] for name in query_names},
            "code": {name: value for name, value in manifest.items()
                     if name.startswith("code/") and name != "code/reproduce.py"}}))
        if version != report["version"]:
            raise ValueError("Changed completed collection version")
        stopped = stops(state["source_stops"])
        if previous and merge_stops(stopped, previous["source_stops"]) != stopped:
            raise ValueError("Completed packet would drop current durable access stops")
        work.mkdir(parents=True, exist_ok=True)
        for name in query_names:
            shutil.copyfile(root / "queries" / name, work / name)
        shutil.copyfile(package, work / "complete-results.zip")
        shutil.copyfile(root / state_member, work / "state.json")
        (work / "report.json").write_bytes(report_body)
        write(work / "source-stops.json", stopped)
    return {**result, "version": version, "original_report": pin(report_body),
            "complete_packet": report["files"]["complete-results.zip"],
            "original_packet_and_queries_unchanged": True}


def publisher_state(repository, ref, github_repository, work):
    publisher = GitPublisher(repository, ref=ref, github_repository=github_repository)
    parent = publisher.remote_head()
    if parent:
        publisher.git("fetch", "--no-tags", "--depth=1", "--filter=blob:none",
                      publisher.remote, publisher.ref_path)
        if pending_publication(publisher, parent) is not None:
            raise ValueError("A staged collection must be activated before starting another collection")
        prior = unpack_state(json.loads(publisher.git("show", parent + ":state.json")))
    else:
        prior = {}
    write(Path(work) / "publication-parent.json", {"parent": parent})
    return publisher, prior


PENDING_PUBLICATION = "pending-results-publication.json"


def pending_publication(publisher, head):
    body = publisher.git("show", head + ":" + PENDING_PUBLICATION, check=False) if head else ""
    return json.loads(body) if body else None


def activate_staged_results(publisher, staged, pending):
    if publisher.remote_head() != staged or pending["parent"] != publisher.parent_of(staged):
        raise ValueError("Staged source receipt was superseded or does not belong to this commit")
    version = pending["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[a-f0-9]{64}", version):
        raise ValueError("Invalid staged collection version")
    prefix = "snapshots/" + version + "/"
    latest_body = publisher.git("show", staged + ":latest.json", check=False)
    latest_before = json.loads(latest_body) if latest_body else None
    if pin(encoded(latest_before)) != pending["previous_pointer"]:
        raise ValueError("Staged source snapshot does not match the previous active pointer")
    prior_body = publisher.git("show", staged + ":state.json", check=False)
    if pin(encoded(json.loads(prior_body) if prior_body else None)) != pending["previous_state"]:
        raise ValueError("Staged source snapshot does not match the previous collector state")
    checked_at = datetime.fromisoformat(pending["checked_at"])
    if (checked_at.utcoffset() is None or latest_before
            and checked_at < datetime.fromisoformat(latest_before["checked_at"])):
        raise ValueError("Staged source snapshot has an invalid or older check time")
    files = pending["files"]
    if not {"snapshot.json.gz", "complete-results.zip"} <= files.keys():
        raise ValueError("Incomplete staged collection")
    state = encoded(json.loads(publisher.git("show", staged + ":" + prefix + "collector-state.json")))
    stop_body = encoded(json.loads(publisher.git("show", staged + ":source-stops.json")))
    if pin(state) != pending["collector_state"] or pin(stop_body) != pending["stops"]:
        raise ValueError("Changed staged source state or access stops")
    stopped = stops(json.loads(stop_body))
    if (unpack_state(json.loads(state))["source_stops"] != stopped
            or prior_body and merge_stops(stopped, unpack_state(json.loads(prior_body))["source_stops"]) != stopped):
        raise ValueError("Staged source state would alter or drop durable access stops")
    publisher.verify_files(staged, {
        **{prefix + str(relative(name)): expected for name, expected in files.items()},
        prefix + "collector-state.json": pending["collector_state"],
        "source-stops.json": pending["stops"],
    })
    latest = {"contract": "participation.automatic_results_latest.v1", "version": version,
              "checked_at": pending["checked_at"], "results_commit": staged,
              "base_url": f"https://raw.githubusercontent.com/{publisher.github_repository}/{staged}/{prefix}",
              "files": files, "all_states_certified": False}
    bodies = {"latest.json": encoded(latest), "state.json": state, PENDING_PUBLICATION: encoded(None)}
    promoted = publisher.commit(publisher.tree(staged, bodies), staged,
                                "Activate current validated election results and persistent source states")
    publisher.promote(promoted, staged)
    publisher.verify_files(promoted, {name: pin(body) for name, body in bodies.items()})
    return {"status": "published", "data_commit": promoted, "results_commit": staged, **latest}


def resume_publication(repository, ref, github_repository):
    publisher = GitPublisher(repository, ref=ref, github_repository=github_repository)
    head = publisher.remote_head()
    if head:
        publisher.git("fetch", "--no-tags", "--depth=1", "--filter=blob:none",
                      publisher.remote, publisher.ref_path)
    pending = pending_publication(publisher, head)
    if pending is None:
        return {"status": "no_pending_publication", "data_commit": head}
    return activate_staged_results(publisher, head, pending)


def publish_source_stops(publisher, parent, stopped):
    if publisher.remote_head() != parent:
        raise ValueError("Source access ledger parent has changed; refusing publication")
    if pending_publication(publisher, parent) is not None:
        raise ValueError("Resume the staged collection before publishing another")
    prior, ledger = {}, None
    if parent:
        prior = unpack_state(json.loads(publisher.git("show", parent + ":state.json")))
        if publisher.git("ls-tree", parent, "--", "source-stops.json"):
            ledger = stops(json.loads(publisher.git("show", parent + ":source-stops.json")))
        stopped = merge_stops(prior["source_stops"], stopped)
        if ledger is not None:
            stopped = merge_stops(ledger, stopped)
        if prior["source_stops"] == ledger == stopped:
            return {"status": "unchanged", "data_commit": parent}
    bodies = {"source-stops.json": encoded(stopped),
              "state.json": pack_state({**prior, "source_stops": stopped})}
    commit = publisher.commit(publisher.tree(parent, bodies), parent,
                              "Preserve election source access holds")
    publisher.promote(commit, parent)
    return {"status": "published_source_stops", "data_commit": commit}


def merge_saved_source_stops(repository, expected_head, ledgers):
    if not re.fullmatch(r"[a-f0-9]{40}", expected_head) or not ledgers:
        raise ValueError("An exact results-data head and at least one saved ledger are required")
    stopped = merge_stops(*(read(path) for path in ledgers))
    publisher = GitPublisher(repository, ref="results-data", github_repository="hanshanley/voter-participation")
    if publisher.remote_head() != expected_head:
        raise ValueError("Source access ledger parent has changed; refusing publication")
    publisher.git("fetch", "--no-tags", "--depth=1", "--filter=blob:none",
                  publisher.remote, publisher.ref_path)
    return publish_source_stops(publisher, expected_head, stopped)


def require_idle_collector():
    endpoint = "repos/hanshanley/voter-participation/actions/concurrency_groups?per_page=100"
    try:
        page = json.loads(subprocess.check_output(["gh", "api", endpoint], timeout=30))
        groups, total = page["concurrency_groups"], page["total_count"]
        if (not isinstance(groups, list) or type(total) is not int or len(groups) != total
                or any(not isinstance(group["group_name"], str) or not group["group_name"] for group in groups)):
            raise ValueError("Incomplete or invalid active concurrency inventory")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise ValueError("Could not verify the hosted collector is idle; source stops not published") from error
    if any(group["group_name"].casefold() == "election-night-participation" for group in groups):
        raise ValueError("Hosted collector is active or queued; keep the saved ledgers and merge when idle")


def publish(repository, ref, github_repository, work):
    work = Path(work)
    publisher = GitPublisher(repository, ref=ref, github_repository=github_repository)
    parent = read(work / "publication-parent.json")["parent"]
    stopped = stops(read(work / "source-stops.json"))
    report_path = work / "report.json"
    if not report_path.exists():
        publish_source_stops(publisher, parent, stopped)
        raise ValueError("Intake failed; durable stops preserved and last valid results retained")
    if pending_publication(publisher, parent) is not None:
        raise ValueError("Resume the staged collection before publishing another")
    report = read(report_path)
    if not report["passed"] or report["jurisdictions"] != 51:
        raise ValueError("Unvalidated current results")
    latest = None
    if parent:
        latest = json.loads(publisher.git("show", parent + ":latest.json", check=False) or "{}")
        if latest.get("version") == report["version"]:
            return {"status": "unchanged", "data_commit": parent}
        if latest and datetime.fromisoformat(latest["checked_at"]) > datetime.fromisoformat(report["checked_at"]):
            raise ValueError("Source snapshot predates the accepted collection; refusing rollback")
    bodies = {}
    prefix = "snapshots/" + report["version"] + "/"
    for name, expected in report["files"].items():
        body = (work / str(relative(name))).read_bytes()
        if pin(body) != expected:
            raise ValueError("Changed validated publication output")
        bodies[prefix + name] = body
    state_body = pack_state(read(work / "state.json"))
    stop_body = encoded(stopped)
    prior_body = publisher.git("show", parent + ":state.json", check=False) if parent else ""
    pending = {"version": report["version"], "checked_at": report["checked_at"], "parent": parent,
               "files": report["files"], "previous_pointer": pin(encoded(latest or None)),
               "previous_state": pin(encoded(json.loads(prior_body) if prior_body else None)),
               "collector_state": pin(state_body), "stops": pin(stop_body)}
    bodies.update({prefix + "collector-state.json": state_body,
                   "source-stops.json": stop_body, PENDING_PUBLICATION: encoded(pending)})
    staged = publisher.commit(publisher.tree(parent, bodies), parent,
                              "Preserve validated complete election results " + report["version"][:12])
    publisher.promote(staged, parent)
    return activate_staged_results(publisher, staged, pending)


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
    congress = commands.add_parser("refresh-congress")
    congress.add_argument("--registry", type=Path, required=True)
    congress.add_argument("--work-dir", type=Path, required=True)
    congress.add_argument("--repository", type=Path, default=ROOT)
    congress.add_argument("--ref", default="results-data")
    congress.add_argument("--github-repository", default="hanshanley/voter-participation")
    congress.add_argument("--offline", action="store_true")
    selected = commands.add_parser("refresh-selected")
    selected.add_argument("--registry", type=Path, required=True)
    selected.add_argument("--work-dir", type=Path, required=True)
    selection = selected.add_mutually_exclusive_group(required=True)
    selection.add_argument("--sources", help="Comma-separated registered source IDs")
    selection.add_argument("--late-archives", action="store_true",
                           help="Select the reviewed statewide and municipal archive feeds")
    selected.add_argument("--repository", type=Path, default=ROOT)
    selected.add_argument("--ref", default="results-data")
    selected.add_argument("--github-repository", default="hanshanley/voter-participation")
    upload = commands.add_parser("publish")
    for action in (upload,):
        action.add_argument("--work-dir", type=Path, required=True)
        action.add_argument("--repository", type=Path, default=ROOT)
        action.add_argument("--ref", default="results-data")
        action.add_argument("--github-repository", default="hanshanley/voter-participation")
    resume = commands.add_parser("resume-publication")
    resume.add_argument("--repository", type=Path, default=ROOT)
    resume.add_argument("--ref", default="results-data")
    resume.add_argument("--github-repository", default="hanshanley/voter-participation")
    merge_policy = commands.add_parser("merge-source-stops")
    merge_policy.add_argument("--repository", type=Path, default=ROOT)
    merge_policy.add_argument("--expected-head", required=True)
    merge_policy.add_argument("ledgers", type=Path, nargs="+")
    reproduce = commands.add_parser("replay")
    reproduce.add_argument("--package", type=Path, required=True)
    reproduce.add_argument("--output", type=Path, required=True)
    reproduce.add_argument("--county-report-dir", type=Path,
                           help="Also verify and re-extract the exact local Wyoming and West Virginia PDFs")
    reproduce.add_argument("--bulk-report-dir", type=Path,
                           help="Also verify and re-extract the exact local Alaska and Connecticut reports")
    recover = commands.add_parser("restore")
    recover.add_argument("--package", type=Path, required=True)
    recover.add_argument("--report", type=Path, required=True)
    recover.add_argument("--require-predecessor", type=Path,
                         help="Automatically restore only against the checkpoint's original data ref")
    recover.add_argument("--require-late-archive-scope", action="store_true",
                         help="Require a complete checkpoint for the current weekly archive registry")
    recover.add_argument("--work-dir", type=Path, required=True)
    recover.add_argument("--repository", type=Path, default=ROOT)
    recover.add_argument("--ref", default="results-data")
    recover.add_argument("--github-repository", default="hanshanley/voter-participation")
    args = parser.parse_args()
    if args.command == "collect":
        _, previous = publisher_state(args.repository, args.ref, args.github_repository, args.work_dir)
        result = collect(args.registry, args.work_dir, previous, offline=args.offline)
    elif args.command == "refresh-congress":
        _, previous = publisher_state(args.repository, args.ref, args.github_repository, args.work_dir)
        result = refresh_congress(args.registry, args.work_dir, previous, offline=args.offline)
    elif args.command == "refresh-selected":
        _, previous = publisher_state(args.repository, args.ref, args.github_repository, args.work_dir)
        source_ids = list(late_archive_sources()) if args.late_archives else args.sources.split(",")
        result = refresh_selected(args.registry, args.work_dir, previous, source_ids,
                                  late_archives=args.late_archives)
    elif args.command == "publish":
        result = publish(args.repository, args.ref, args.github_repository, args.work_dir)
    elif args.command == "resume-publication":
        result = resume_publication(args.repository, args.ref, args.github_repository)
    elif args.command == "merge-source-stops":
        require_idle_collector()
        result = merge_saved_source_stops(args.repository, args.expected_head, args.ledgers)
    elif args.command == "restore":
        if args.require_late_archive_scope and not args.require_predecessor:
            parser.error("--require-late-archive-scope requires --require-predecessor")
        publisher, previous = publisher_state(args.repository, args.ref, args.github_repository, args.work_dir)
        parent = read(args.work_dir / "publication-parent.json")["parent"]
        if args.require_predecessor and read(args.require_predecessor) != {"parent": parent}:
            result = {"status": "superseded"}
        else:
            latest = json.loads(publisher.git("show", parent + ":latest.json", check=False) or "{}") if parent else {}
            result = restore(args.package, args.report, args.work_dir, previous, latest,
                             require_late_archive_scope=args.require_late_archive_scope)
    else:
        result = replay(args.package, args.output, county_report_dir=args.county_report_dir,
                        bulk_report_dir=args.bulk_report_dir)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
