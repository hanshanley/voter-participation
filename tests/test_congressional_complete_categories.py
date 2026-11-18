import copy
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path

import pytest

from scripts import congressional_complete_categories as categories
from scripts import results_congress, results_intake
from scripts import results_official_congress as official
from scripts.participation_intake.contract import encoded, pin


def original():
    return json.loads((Path(__file__).parent / "fixtures/ri-official-congress.json").read_bytes())


def capture(tmp_path, native, previous=None, stopped=False):
    collector = results_intake.Collector(
        tmp_path, {categories.IDENTITY: previous} if previous else {},
        {"urls": [categories.URL] if stopped else [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 18, tzinfo=timezone.utc))
    calls = []

    def acquire(url):
        collector.guard(url)
        calls.append(url)
        if native is None:
            raise OSError("Official source unavailable")
        body = encoded(native)
        return body, {"origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    entries = official.collect_sources(collector, official.COMPLETE_CONFIG, selected={categories.IDENTITY})
    return entries[categories.IDENTITY], calls


def policy(entry):
    race = entry["data"]["races"][0]
    return {
        "identity": {"seat": "1"},
        "complete_official_categories": {
            "source_id": categories.IDENTITY, "source_url": categories.URL,
            "official_inventory": categories.signature(race),
            "accepted_source_updated_at": entry["data"]["source_updated_at"],
            "provider_aggregate_id": "other-40015",
            "official_omitted_candidate_ids": [row["candidate_id"] for row in race["candidates"]
                                               if row["party_group"] == "O"],
        },
    }


def provider(other=6440):
    return {"candidates": [{"candidate_id": "other-40015", "role": "provider_aggregate_other",
                             "votes": other, "party_group": "O"}]}


def revision(native, delta):
    result = copy.deepcopy(native)
    contest = result["ballotItems"][0]
    minor = contest["summaryResults"]["ballotOptions"][2]
    minor["voteCount"] += delta
    if minor["voteCount"] == 0:
        for mode in minor["groupResults"]:
            mode["voteCount"] = 0
    else:
        minor["groupResults"][0]["voteCount"] += delta
    contest["voteTotal"] += delta
    return result


def test_complete_actual_federal_inventory_preserves_modes_and_generic_affiliation():
    data = categories.parse(encoded(original()))
    assert [row["contest_total"] for row in data["races"]] == [163448, 195436]
    assert [len(row["candidates"]) for row in data["races"]] == [4, 3]
    assert [sum(candidate["votes"] for candidate in row["candidates"] if candidate["party_group"] == "O")
            for row in data["races"]] == [6440, 511]
    assert all(candidate["literal_party"] is None for race in data["races"]
               for candidate in race["candidates"] if candidate["role"] == "generic_write_in")
    assert not data["participation_observation_qualified"] and not data["conditional_model_eligible"]
    assert categories.parse(encoded(data["native_facts"])) == data
    assert json.loads(encoded(categories.signature(data["races"][0]))) == categories.signature(data["races"][0])


@pytest.mark.parametrize("change", ["primary", "production", "district", "missing", "duplicate",
                                   "total", "mode", "party", "write-in", "clock", "partial", "ranked",
                                   "native-id"])
def test_incompatible_complete_native_evidence_is_rejected(change):
    native = original()
    race = native["ballotItems"][0]
    candidate = race["summaryResults"]["ballotOptions"][0]
    if change == "primary":
        native["election"]["isPrimary"] = True
    elif change == "production":
        native["election"]["isProduction"] = False
    elif change == "district":
        race["name"][0]["text"] = "Representative in Congress District 3"
    elif change == "missing":
        native["ballotItems"].pop()
    elif change == "duplicate":
        native["ballotItems"].append(copy.deepcopy(race))
    elif change == "total":
        race["voteTotal"] += 1
    elif change == "mode":
        candidate["groupResults"][0]["voteCount"] += 1
    elif change == "party":
        candidate["party"]["abbreviation"] = "Other"
    elif change == "write-in":
        race["summaryResults"]["ballotOptions"][-1]["party"]["abbreviation"] = "REP"
    elif change == "clock":
        race["reportingStatus"]["asOf"] = "2026-11-11T00:00:00Z"
    elif change == "partial":
        race["reportingStatus"]["reportingUnits"] -= 1
    elif change == "ranked":
        race["rankedChoiceSummaryResults"] = {}
    elif change == "native-id":
        candidate["nativeId"] = {}
    with pytest.raises((ValueError, KeyError, TypeError)):
        categories.parse(encoded(native))


@pytest.mark.parametrize("delta", [7, -13, -6211])
def test_upward_downward_zero_other_revisions_require_official_agreement(tmp_path, delta):
    first, _ = capture(tmp_path / "first", original())
    changed, _ = capture(tmp_path / "changed", revision(original(), delta), first)
    assert changed["status"] == "reported"
    congress = official.attach({}, {categories.IDENTITY: changed})
    reviewed = policy(first)
    assert categories.current_hold(congress, "ri1", reviewed, provider(6440 + delta)) is None
    assert categories.current_hold(congress, "ri1", reviewed, provider()) == "official_category_Other_mass_differs"
    assert first["data"]["races"][0]["candidates"][2]["votes"] == 6211


def test_unchanged_outage_stop_and_latest_clock_preserve_last_good(tmp_path):
    native = original()
    first, _ = capture(tmp_path / "first", native)
    unchanged, calls = capture(tmp_path / "unchanged", native, first)
    assert unchanged == first and calls == [categories.URL]
    reviewed = policy(first)
    for label, document, stopped in (("outage", None, False), ("stop", native, True)):
        held, calls = capture(tmp_path / label, document, first, stopped)
        assert held["status"] == "retained_after_failure"
        assert held["data"] == first["data"] and held["source"] == first["source"]
        assert held["first_observed_at"] == first["first_observed_at"]
        assert categories.current_hold(official.attach({}, {categories.IDENTITY: held}),
                                       "ri1", reviewed, provider()) == "official_category_source_not_fresh"
        if stopped:
            assert calls == []
    newer = original()
    newer["election"]["asOf"] = "2026-11-17T00:00:00Z"
    for row in newer["ballotItems"]:
        row["reportingStatus"]["asOf"] = newer["election"]["asOf"]
    advanced, _ = capture(tmp_path / "newer", newer, first)
    assert advanced["status"] == "reported"
    regressed, _ = capture(tmp_path / "regressed", native, advanced)
    assert regressed["status"] == "retained_after_failure"
    assert regressed["data"] == advanced["data"]


def test_default_config_exports_and_category_identity_guard(tmp_path):
    from test_results_official_congress import original as nebraska_original

    collector = results_intake.Collector(
        tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 18, tzinfo=timezone.utc))
    calls = []

    def acquire(url):
        calls.append(url)
        body = nebraska_original() if url == official.URL else encoded(original())
        return body, {"origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    entries = official.collect_sources(collector, official.COMPLETE_CONFIG)
    assert set(entries) == set(official.COMPLETE_CONFIG["sources"]) and len(calls) == 2
    congress = official.attach({"races": {}}, entries)
    exported = results_congress.exports(congress)
    rows = list(csv.DictReader(io.StringIO(exported["congress-official-candidates.csv"].decode())))
    assert len(rows) == 16 and {row["evidence_id"] for row in rows} == set(official.COMPLETE_CONFIG["sources"])
    assert results_intake.numeric_observations({"index.json": encoded({"states": {}})}, entries) == []
    changed = copy.deepcopy(entries[categories.IDENTITY])
    changed["data"]["races"][0]["candidates"][0]["candidate_id"] = "changed"
    assert categories.current_hold(official.attach({}, {categories.IDENTITY: changed}), "ri1",
                                   policy(entries[categories.IDENTITY]), provider()) is not None


def test_senate_reuses_one_guarded_statewide_response_without_changing_house_tables(tmp_path):
    senate = json.loads((Path(__file__).parent / "fixtures/ri-official-senate.json").read_bytes())
    native = original()
    native["ballotItems"] += senate["native_facts"]["ballotItems"]
    body = encoded(native)
    collector = results_intake.Collector(
        tmp_path, {}, {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 18, tzinfo=timezone.utc))
    collector.bodies[categories.URL] = (body, {"origin": "supplied_original", **pin(body)})
    entries = official.collect_sources(collector, official.SENATE_CONFIG,
        selected={categories.IDENTITY, official.SENATE_IDENTITY})
    assert entries[categories.IDENTITY]["status"] == entries[official.SENATE_IDENTITY]["status"] == "reported"
    assert entries[categories.IDENTITY]["data"] == categories.parse(encoded(original()))
    assert entries[official.SENATE_IDENTITY]["data"] == categories.parse(encoded(native), "senate")
    race = entries[official.SENATE_IDENTITY]["data"]["races"][0]
    assert race["seat"] == "2" and not race["native_seat_declared"]
    assert sum(row["votes"] for row in race["candidates"]) == race["contest_total"]
    assert results_intake.numeric_observations({"index.json": encoded({"states": {}})}, entries) == []
    collector.stopped["urls"].append(categories.URL)
    refused = official.collect_sources(collector, official.SENATE_CONFIG,
        selected={official.SENATE_IDENTITY})[official.SENATE_IDENTITY]
    assert refused["status"] != "reported" and refused["data"] is None
