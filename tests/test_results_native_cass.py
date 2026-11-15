"""Portable source-plan, collector and projection tests for the Cass adapter."""

import copy
import gzip
import json

from scripts import results_granular as granular
from scripts import results_native as native
from scripts import results_pdf_cass as cass
from scripts.participation_intake.contract import (
    encoded,
    observation_id,
    pin,
    validate,
)

from test_results_pdf_cass import page


def row(state, name, geography_id, url, measure):
    source_id = "fixture-" + state.lower()
    election_id = "general-2026"
    item = {
        "contract": "participation.observation.v1",
        "id": "",
        "election": {
            "id": election_id,
            "year": 2026,
            "date": "2026-11-03",
            "type": "general",
            "qualification": "native",
        },
        "geography": {
            "id": geography_id,
            "name": name,
            "state_code": state,
            "level": "county",
            "parent_id": None,
            "join": {
                "status": "unreviewed",
                "reference_id": None,
                "feature_key": None,
                "evidence": "fixture",
            },
        },
        "measure": copy.deepcopy(measure),
        "count": {"value": 7, "literal": 7, "status": "reported"},
        "denominator": None,
        "source_clock": {
            "literal": "11/03/2026 7:59 PM",
            "timezone": None,
            "qualification": "native",
        },
        "reporting_status": {
            "literal": "Unofficial Results; OFFICIAL 2026 GENERAL",
            "reported_units": None,
            "total_units": None,
            "complete": None,
        },
        "source": {
            "id": source_id,
            "url": url,
            "input_sha256": "b" * 64,
            "selector": {},
            "classification": "public_aggregate",
            "fields": {},
        },
        "quality": {"conflicts": [], "notes": []},
        "view": {
            "source_url": url,
            "source_update_label": "11/03/2026 7:59 PM",
            "native_record": {},
            "ballots": 7,
            "denominator": None,
            "reported_pct": None,
        },
    }
    item["id"] = observation_id(
        source_id,
        election_id,
        geography_id,
        measure["id"],
        measure["mode"],
    )
    item["source"]["fields"] = copy.deepcopy(item["view"])
    return validate(item)


def cass_row():
    item = row(
        "IN",
        "Cass County",
        "IN|additional:IN:18017|",
        cass.URL,
        cass.MEASURE,
    )
    item["view"].update({
        "county": "Cass County",
        "county_id": "additional:IN:18017",
        "selected_source_kind": "native_turnout_numerator",
        "cast_ballot_count_qualified": False,
        "unique_voter_count_qualified": False,
        "native_record": {
            "county": "Cass",
            "measure_literal": "Registered Voters",
        },
        "reference_geometry": {"sha256": "c" * 64},
        "statewide_statistics_native_record": {
            "County": "Cass",
            "VotersVoting": 0,
            "REGISTERED_VOTERS": 31415,
        },
    })
    item["source"]["fields"] = copy.deepcopy(item["view"])
    return validate(item)


def baseline():
    cass_template = cass_row()
    tx = row(
        "TX",
        "Fixture County",
        "TX|fixture|",
        "https://tx.example.test/2026-general.pdf",
        {
            "id": "native-statistics",
            "kind": "participation_reported",
            "literal": "Native statistics",
            "mode": "source_defined",
            "unit": "source_units",
        },
    )
    shards = {
        "IN": {
            "records": [cass_template],
            "views": {
                "official": {"counties": [cass_template["id"]]},
                "available": {"counties": [cass_template["id"]]},
            },
        },
        "TX": {
            "records": [tx],
            "views": {"official": {"counties": [tx["id"]]}},
        },
    }
    bodies = {}
    states = {}
    for state, shard in shards.items():
        path = f"states/{state}.json.gz"
        bodies[path] = gzip.compress(encoded(shard), mtime=0)
        states[state] = {"file": path, **pin(bodies[path])}
    bodies["index.json"] = encoded({"states": states})
    return bodies, cass_template


class RetainedCollector:
    def __init__(self, body):
        self.body = body
        self.capture_count = 0

    def capture(self, identity, url, parse):
        if url != cass.URL:
            return {
                "status": "source_stopped",
                "data": None,
                "source": {"url": url, "origin": "offline_hold"},
            }
        self.capture_count += 1
        return {
            "status": "reported",
            "data": parse(self.body),
            "source": {"url": url, "origin": "retained_original", **pin(self.body)},
        }


def test_plan_collector_projection_preserve_scope_and_repeat(monkeypatch):
    before, accepted = baseline()
    profile = copy.deepcopy(cass.PROFILES[cass.URL])
    profile["target_id"] = accepted["id"]
    monkeypatch.setitem(cass.PROFILES, cass.URL, profile)
    parsed = cass.factual_query_from_pages(
        [page(1), page(2)],
        {"bytes": 123, "sha256": "a" * 64},
        profile,
    )
    monkeypatch.setattr(cass, "factual_query", lambda body, url=cass.URL: parsed)

    source = next(iter(native.source_plan(before)["IN"].values()))
    assert source["adapter"] == "reviewed_cass_turnout_pdf"
    assert [item["id"] for item in source["templates"]] == [accepted["id"]]

    collector = RetainedCollector(b"retained-cass-source")
    entries = native.collect_sources(collector, before)
    cass_entry = next(
        entry for entry in entries.values()
        if entry.get("adapter") == "reviewed_cass_turnout_pdf"
    )
    assert collector.capture_count == 1
    assert cass_entry["reviewed_record_count"] == 1

    after, changes = granular.project(before, entries)
    assert len(changes) == 1
    assert after["states/TX.json.gz"] == before["states/TX.json.gz"]
    old = json.loads(gzip.decompress(before["states/IN.json.gz"]))
    current = json.loads(gzip.decompress(after["states/IN.json.gz"]))
    assert current["views"] == old["views"]
    prior, refreshed = old["records"][0], current["records"][0]
    assert refreshed["id"] == prior["id"]
    assert refreshed["geography"] == prior["geography"]
    assert refreshed["source"]["id"] == prior["source"]["id"]
    assert refreshed["denominator"] is None
    assert refreshed["view"]["reported_pct"] is None
    assert refreshed["count"]["value"] == 18
    assert refreshed["reporting_status"]["reported_units"] == 2
    assert refreshed["reporting_status"]["total_units"] == 3
    assert refreshed["reporting_status"]["complete"] is None
    assert (refreshed["view"]["statewide_statistics_native_record"]
            == prior["view"]["statewide_statistics_native_record"])
    assert (refreshed["view"]["reference_geometry"]
            == prior["view"]["reference_geometry"])

    repeated = native.collect_sources(collector, after)
    assert granular.project(after, repeated) == (after, [])
