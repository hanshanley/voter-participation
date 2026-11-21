import copy
import csv
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

import pytest

from scripts import results_intake as intake
from scripts.participation_intake.contract import IntakeError, encoded, pin
from scripts.participation_intake.engine import AllowedRedirect, Store
from scripts.participation_intake.publisher import GitPublisher
from scripts.results_house import candidate_results, districts, state_totals


NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def declaration():
    regions, count = {}, 0
    for index, state in enumerate(code for code in intake.STATES if code != "DC"):
        for number in range(1, (9 if index < 35 else 8) + 1):
            count += 1
            regions[state.lower() + "-" + str(number).zfill(2)] = {
                "type": "Congressional District", "election_id": count}
    return {"test_data": False, "country": "US", "province": "US",
            "election_date": "2026-11-03", "election_type": "House of Representatives",
            "election_scope": "General", "region_results": regions}


def candidate(declared, votes=0):
    return {"test_data": False, "country": "US", "province": declared["state_code"],
            "district": declared["district"], "election_date": "2026-11-03",
            "election_type": "House of Representatives", "election_scope": "General",
            "last_updated": "2026-11-14T01:00:00Z", "percent_reporting": 100,
            "candidates": [{"name": "A", "party": "D", "votes": votes},
                           {"name": "B", "party": "R", "votes": 3}]}


def fixture(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    baseline = root / "accepted"
    (baseline / "states").mkdir(parents=True)
    index = {"states": {}}
    files = {}
    for state in intake.STATES:
        name = "states/" + state + ".json.gz"
        body = intake.compressed(encoded({"records": [{"id": state, "count": {"value": None}}]}))
        (baseline / name).write_bytes(body)
        files[name] = pin(body)
        index["states"][state] = {"file": name, **pin(body)}
    body = encoded(index)
    (baseline / "index.json").write_bytes(body)
    files["index.json"] = pin(body)
    config = {"contract": intake.CONTRACT, "election_date": "2026-11-03",
              "baseline": {"root": "accepted", "files": files},
              "jurisdictions": {code: {"url": None, "status": "not_listed_in_directory"}
                                for code in intake.STATES}, "source_stops": EMPTY_STOPS}
    (root / "registry.json").write_bytes(encoded(config))
    return root / "registry.json"


def unavailable(self, url):
    self.guard(url)
    raise IntakeError("source_unavailable", "Fixture transport unavailable")


def test_district_identity_and_missing_counts_are_not_completion_or_zero():
    native = declaration()
    declared = districts(native)
    assert len(declared) == 435
    row = next(iter(declared.values()))
    parsed = candidate_results(candidate(row), row)
    assert parsed["candidates"][0]["votes"] == 0
    assert parsed["certification_qualified"] is False
    assert parsed["candidate_votes_are_ballots"] is False
    for change in (None, True, -1):
        body = candidate(row)
        body["candidates"][0]["votes"] = change
        with pytest.raises(ValueError):
            candidate_results(body, row)
    body = candidate(row)
    body["election_scope"] = "Primary"
    with pytest.raises(ValueError):
        candidate_results(body, row)
    native["region_results"].pop(next(iter(native["region_results"])))
    with pytest.raises(ValueError):
        districts(native)
    aggregate = state_totals({row["district"]: {"status": "reported", "data": parsed}}, declared)
    assert next(item for item in aggregate if item["state_code"] == row["state_code"])["party_votes"] is None


@pytest.mark.parametrize("http_status", [403, 429])
def test_new_denial_survives_fresh_store_and_429_stops_host(tmp_path, monkeypatch, http_status):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise HTTPError(request.full_url, http_status, "Denied", {}, io.BytesIO(b""))
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    first = intake.Collector(tmp_path / "first", {}, EMPTY_STOPS, NOW)
    result = first.capture("source", "https://example.test/one", lambda body: {})
    assert result["data"] is None and len(calls) == 1
    second = intake.Collector(tmp_path / "new-cache", {}, intake.read(tmp_path / "first/source-stops.json"), NOW)
    second.capture("source", "https://example.test/one", lambda body: {})
    assert len(calls) == 1
    if http_status == 429:
        second.capture("other", "https://example.test/two", lambda body: {})
        assert len(calls) == 1


def test_redirect_target_is_checked_before_following_it(tmp_path):
    collector = intake.Collector(tmp_path, {},
                                {"urls": ["https://example.test/held"], "prefixes": [], "hosts": []}, NOW)
    handler = AllowedRedirect(["example.test"], collector.guard)
    with pytest.raises(IntakeError, match="Persisted"):
        handler.redirect_request(Request("https://example.test/allowed"), None, 302, "",
                                 {}, "https://example.test/held")


def test_source_failure_keeps_prior_counts_and_clocks(tmp_path, monkeypatch):
    prior = {"source": {"status": "reported", "data": {"total": 12, "date": "2026-11-12"},
                        "source": {"url": "https://example.test/data", "bytes": 1, "sha256": "a" * 64},
                        "first_observed_at": "old", "error": None}}
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
    result = collector.capture("source", "https://example.test/data", lambda body: {})
    assert result["data"] == prior["source"]["data"]
    assert result["source"] == prior["source"]["source"]
    assert result["status"] == "retained_after_failure"


def test_failed_capture_preserves_attempt_url_input_pin_and_specific_parser_reason(tmp_path, monkeypatch):
    body = b"permitted public aggregate fixture"
    monkeypatch.setattr(intake.Collector, "acquire", lambda self, url: (
        body, {"origin": "retained_fixture", **pin(body)}))
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    def parse(body):
        raise ValueError("Native precinct/county totals disagree")
    result = collector.capture("WI-registered-fixture", "https://official.test/report", parse)
    assert result["source"] is None
    assert result["attempted_source_url"] == "https://official.test/report"
    assert result["attempted_source_pin"] == pin(body)
    assert result["error_stage"] == "parsing"
    assert result["error_detail"] == "Native precinct/county totals disagree"
    assert result["error"] == "schema_or_source_semantics_changed"
    collector.prior["WI-registered-fixture"] = result
    recovered = collector.capture(
        "WI-registered-fixture", "https://official.test/report", lambda body: {"total": 0})
    assert recovered["status"] == "reported" and recovered["data"]["total"] == 0
    assert recovered["error_detail"] is None and recovered["error_stage"] is None


def test_selected_refresh_reuses_every_other_capture_and_rejects_unknown_sources(tmp_path, monkeypatch):
    from scripts import results_native
    registry = fixture(tmp_path)
    identity = "WI-registered-87e0d6c3aa94b8a6"
    previous = {
        "feeds": {"unchanged-feed": {"status": "reported", "data": {"total": 12}}},
        "granular": {"unchanged": {"status": "reported", "data": {"updates": []}}},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {"status": "reported", "data": {"count": index}} for index in range(435)},
        "directories": {state: {} for state in intake.STATES}, "source_stops": EMPTY_STOPS,
    }
    original = copy.deepcopy(previous)
    calls = []
    monkeypatch.setattr(results_native, "source_plan", lambda baseline: {
        "WI": {identity: {"adapter": "reviewed_pdf_county_parent"}}})
    def selected(collector, baseline, source_ids=None):
        calls.append(source_ids)
        return {identity: {"status": "reported", "data": {"updates": []}}}
    monkeypatch.setattr(results_native, "collect_sources", selected)
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)
    result = intake.refresh_selected(registry, tmp_path / "scoped", previous, [identity], NOW)
    assert calls == [{identity}] and previous == original
    assert result["house"] == original["house"]
    assert result["feeds"]["unchanged-feed"] == original["feeds"]["unchanged-feed"]
    assert result["granular"]["unchanged"] == original["granular"]["unchanged"]
    assert result["collection_scope"]["source_ids"] == [identity]
    with pytest.raises(ValueError, match="dispatch plan"):
        intake.refresh_selected(registry, tmp_path / "wrong", previous, ["WI-registered-" + "0" * 16], NOW)
    assert len(calls) == 1
    monkeypatch.setattr(results_native, "collect_sources", lambda *args, **kwargs: {
        identity: {"status": "schema_or_source_semantics_changed", "data": None}})
    monkeypatch.setattr(intake, "export_collection",
                        lambda *args: pytest.fail("A failed selected capture must not be published"))
    with pytest.raises(ValueError, match="no replacement publication"):
        intake.refresh_selected(registry, tmp_path / "failed", previous, [identity], NOW)
    assert previous == original


def test_selected_retry_preserves_new_denial_before_publication(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    from scripts import results_native

    registry = fixture(tmp_path)
    work = tmp_path / "scoped-retry"
    identity = "WI-registered-87e0d6c3aa94b8a6"
    url = "https://official.test/report"
    previous = {
        "feeds": {}, "granular": {},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {} for index in range(435)},
        "directories": {state: {} for state in intake.STATES},
        "source_stops": {**EMPTY_STOPS, "hosts": ["previously-stopped.test"]},
    }
    monkeypatch.setattr(results_native, "source_plan", lambda baseline: {
        "WI": {identity: {"adapter": "reviewed_pdf_county_parent"}}})
    captures = []

    def selected(collector, baseline, source_ids=None):
        assert source_ids == {identity}
        entry = collector.capture(identity, url, lambda _: pytest.fail("No source body expected"))
        captures.append(entry)
        return {identity: entry}

    requests = []

    def denied(self, spec, *, access_guard):
        access_guard(spec["url"])
        requests.append(spec["url"])
        if len(requests) > 1:
            pytest.fail("Retried a persisted denial")
        raise intake.IntakeError("source_access", "Forbidden") from HTTPError(
            url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(results_native, "collect_sources", selected)
    monkeypatch.setattr(intake.Store, "acquire", denied)
    monkeypatch.setattr(intake, "export_collection",
                        lambda *args: pytest.fail("A failed selected capture must not be published"))
    for _ in range(2):
        with pytest.raises(ValueError, match="no replacement publication"):
            intake.refresh_selected(registry, work, previous, [identity], NOW)
        assert intake.read(work / "source-stops.json") == {
            "hosts": ["previously-stopped.test"], "prefixes": [], "urls": [url]}
    assert [entry["status"] for entry in captures] == ["source_stopped", "source_stopped"]
    assert requests == [url]
    assert previous["source_stops"]["urls"] == []


def test_uf_only_dispatch_preserves_congress_counties_and_every_other_source(tmp_path, monkeypatch):
    from scripts import results_native, results_turnout_history as history, results_uf_turnout as uf
    registry = fixture(tmp_path)
    intake.write(registry.parent / "uf-turnout.json", uf.CONFIG)
    previous = {
        "feeds": {"unchanged-feed": {"status": "reported", "data": {"total": 12}}},
        "granular": {"unchanged": {"status": "reported", "data": {"updates": []}}},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {"status": "reported", "data": {"count": index}} for index in range(435)},
        "congress": {"native_clock": "must stay unchanged"},
        "directories": {state: {} for state in intake.STATES}, "source_stops": EMPTY_STOPS,
    }
    original, calls = copy.deepcopy(previous), []
    monkeypatch.setattr(results_native, "source_plan", lambda baseline: {})
    monkeypatch.setattr(results_native, "collect_sources",
                        lambda *args, **kwargs: pytest.fail("UF refresh must not acquire local sources"))
    def collect(collector, config):
        calls.append(config)
        return {"status": "reported", "data": {"rows": []}}
    monkeypatch.setattr(uf, "collect", collect)
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)
    result = intake.refresh_selected(registry, tmp_path / "selected", previous, [uf.IDENTITY], NOW)
    assert calls == [uf.CONFIG] and previous == original
    for key in ("granular", "districts", "house", "congress", "directories", "source_stops"):
        assert result[key] == original[key]
    assert result["feeds"]["unchanged-feed"] == original["feeds"]["unchanged-feed"]
    assert result["collection_scope"]["source_ids"] == [uf.IDENTITY]

    prior = {"status": "reported", "data": {"rows": [500]}, "first_observed_at": "old"}
    previous["feeds"][uf.IDENTITY] = prior
    held = {**prior, "status": "retained_after_failure", "error": "source_unavailable"}
    monkeypatch.setattr(uf, "collect", lambda *_: held)
    with pytest.raises(ValueError, match="no replacement publication"):
        intake.refresh_selected(registry, tmp_path / "strict", previous, [uf.IDENTITY], NOW)

    weekly_sources = [uf.IDENTITY, history.WA_FEED]
    monkeypatch.setattr(intake, "late_archive_sources", lambda: tuple(weekly_sources))
    with pytest.raises(ValueError, match="complete late archive scope"):
        intake.refresh_selected(registry, tmp_path / "partial", previous, [uf.IDENTITY], NOW, late_archives=True)
    revised_wa = {"status": "reported", "data": {"total": 42}}
    monkeypatch.setattr(history, "collect_washington", lambda _: revised_wa)
    weekly = intake.refresh_selected(registry, tmp_path / "weekly", previous, weekly_sources, NOW,
                                     late_archives=True)
    assert weekly["feeds"][uf.IDENTITY] == held
    assert weekly["granular"][history.WA_FEED] == revised_wa
    assert uf.IDENTITY not in weekly["granular"]
    for key in ("districts", "house", "congress", "directories", "source_stops"):
        assert weekly[key] == previous[key]
    assert intake.refresh_selected(registry, tmp_path / "weekly", weekly, weekly_sources, NOW,
                                   late_archives=True) == weekly


def test_weekly_official_correction_survives_an_independent_source_stop(tmp_path, monkeypatch):
    from scripts import results_official_congress as official

    registry = fixture(tmp_path)
    intake.write(registry.with_name("official-congress.json"), official.CLARITY_CONFIG)
    national = {"native_race": {"status": "reported", "data": {"native_clock": 100}}}
    old = {"status": "reported", "data": {"count": 10}}
    previous = {"feeds": {official.CLARITY_IDENTITY: old}, "granular": {},
                "districts": {str(i): {} for i in range(435)},
                "house": {str(i): {} for i in range(435)},
                "directories": {key: {} for key in intake.STATES}, "source_stops": EMPTY_STOPS,
                "congress": {"races": national}}
    ids = [official.CLARITY_IDENTITY, official.JSON_IDENTITY]
    monkeypatch.setattr(intake, "late_archive_sources", lambda: tuple(ids))
    monkeypatch.setattr(intake, "export_collection", lambda *args: args[3])
    revised = {"status": "reported", "data": {"count": 9}}
    held = {**old, "status": "retained_after_failure", "error": "source_stopped"}
    entries = {official.CLARITY_IDENTITY: held, official.JSON_IDENTITY: revised}

    def collect(collector, config, selected):
        assert config == official.CLARITY_CONFIG and selected == set(ids)
        assert collector.prior[official.CLARITY_IDENTITY] == old
        return entries

    monkeypatch.setattr(official, "collect_sources", collect)
    with pytest.raises(ValueError, match="no replacement publication"):
        intake.refresh_selected(registry, tmp_path / "strict", previous, ids, NOW)
    accepted = intake.refresh_selected(registry, tmp_path / "weekly", previous, ids, NOW, late_archives=True)
    assert accepted["congress"]["races"] == national
    assert accepted["congress"]["official_candidate_evidence"] == entries
    assert accepted["granular"] == {}


@pytest.mark.parametrize("ohio_status", ["reported", "source_stopped", "retained_after_failure"])
def test_selected_administrative_refresh_does_not_reacquire_congress(tmp_path, monkeypatch, ohio_status):
    from scripts import alaska_age_history, alaska_cards_history, alaska_precinct_history
    from scripts import (
        alabama_precinct_history, national_turnout_release_watch, nebraska_county_reports, oregon_turnout_history,
        philadelphia_divisions, results_indiana_turnout,
        results_minnesota_turnout as mn, results_native,
        results_nc_vote_history, results_official_congress,
        results_pa_vote_history, results_pdf_county_parent, results_uf_turnout,
        results_turnout_history, southeast_turnout, washington_participation,
    )

    registry = fixture(tmp_path)
    previous = {
        "feeds": {"unchanged": {"status": "reported", "data": {"total": 12}}},
        "granular": {},
        "districts": {str(index): {} for index in range(435)},
        "house": {str(index): {"status": "reported", "data": {"count": index}} for index in range(435)},
        "congress": {"native_clock": "must stay unchanged"},
        "directories": {state: {} for state in intake.STATES}, "source_stops": EMPTY_STOPS,
    }
    calls = []

    def adapter(identity):
        def capture(_):
            calls.append(identity)
            status = ohio_status if identity == selected[0] else "reported"
            return {"status": status, "data": None if status == "source_stopped" else {"identity": identity}}
        return capture

    selected = [results_turnout_history.OH_FEED, results_pdf_county_parent.PHILADELPHIA_FEED,
                philadelphia_divisions.FEED]
    prior_ohio = {"status": "reported", "data": {"total": 42}, "first_observed_at": "old"}
    previous["feeds"][selected[0]] = previous["granular"][selected[0]] = prior_ohio
    previous = intake.compact_collector_state(previous)
    monkeypatch.setattr(results_turnout_history, "collect_ohio", adapter(selected[0]))
    monkeypatch.setattr(results_pdf_county_parent, "collect_philadelphia", adapter(selected[1]))
    monkeypatch.setattr(philadelphia_divisions, "collect", adapter(selected[2]))
    for code, name in (("KS", "kansas"), ("NJ", "new_jersey"), ("TX", "texas"),
                       ("VA", "virginia"), ("WA", "washington")):
        identity = getattr(results_turnout_history, code + "_FEED")
        selected.append(identity)
        monkeypatch.setattr(results_turnout_history, "collect_" + name, adapter(identity))
    selected.append(results_pa_vote_history.FEEDS[2026])
    monkeypatch.setattr(results_pa_vote_history, "collect",
                        lambda collector, year: adapter(results_pa_vote_history.FEEDS[year])(collector))
    selected.append(results_nc_vote_history.FEED)
    monkeypatch.setattr(results_nc_vote_history, "collect", adapter(results_nc_vote_history.FEED))
    selected.append(results_turnout_history.NC_HISTORY_FEED)
    monkeypatch.setattr(results_turnout_history, "collect_north_carolina_history",
                        adapter(results_turnout_history.NC_HISTORY_FEED))
    selected.append(results_turnout_history.WY_HISTORY_FEED)
    monkeypatch.setattr(results_turnout_history, "collect_wyoming_history",
                        adapter(results_turnout_history.WY_HISTORY_FEED))
    selected.append(results_turnout_history.WY_CANVASS_FEED)
    monkeypatch.setattr(results_turnout_history, "collect_wyoming_precinct_canvass",
                        adapter(results_turnout_history.WY_CANVASS_FEED))
    selected.extend(results_indiana_turnout.FEEDS.values())
    monkeypatch.setattr(results_indiana_turnout, "collect",
                        lambda collector, year: adapter(results_indiana_turnout.FEEDS[year])(collector))
    monkeypatch.setattr(results_turnout_history, "collect_county_archive",
                        lambda collector, feed: adapter(feed)(collector))
    monkeypatch.setattr(nebraska_county_reports, "collect", adapter(nebraska_county_reports.FEED))
    monkeypatch.setattr(national_turnout_release_watch, "collect",
                        lambda collector, feed: adapter(feed)(collector))
    monkeypatch.setattr(washington_participation, "collect", adapter(washington_participation.FEED))
    monkeypatch.setattr(oregon_turnout_history, "collect",
                        lambda collector, feed: adapter(feed)(collector))
    monkeypatch.setattr(southeast_turnout, "collect",
                        lambda collector, feed: adapter(feed)(collector))
    monkeypatch.setattr(alabama_precinct_history, "collect",
                        lambda collector, feed: adapter(feed)(collector))
    monkeypatch.setattr(alaska_precinct_history, "collect", adapter(alaska_precinct_history.FEED))
    monkeypatch.setattr(alaska_cards_history, "collect",
                        lambda collector, feed: adapter(feed)(collector))
    monkeypatch.setattr(alaska_age_history, "collect",
                        lambda collector, feed: adapter(feed)(collector))
    for feed, name in ((results_turnout_history.BUXTON_FEED, "buxton"),
                       (results_turnout_history.BATH_FEED, "bath")):
        monkeypatch.setattr(results_turnout_history, "collect_" + name, adapter(feed))
    monkeypatch.setattr(results_turnout_history, "collect_votingworks_town",
                        lambda collector, profile: adapter(profile.feed)(collector))
    assert set(mn.SOURCE_IDS) <= set(intake.late_archive_sources())
    with pytest.raises(ValueError, match="both linked source IDs"):
        intake.refresh_selected(registry, tmp_path / "scoped", previous, [mn.IDENTITY], NOW)
    assert not calls
    pair_status = ohio_status

    def collect_pair(collector, baseline):
        assert baseline
        calls.extend(mn.SOURCE_IDS)
        return {key: {"status": pair_status,
                      "data": None if pair_status == "source_stopped" else {"identity": key}}
                for key in mn.SOURCE_IDS}

    monkeypatch.setattr(mn, "collect_pair", collect_pair)
    selected.extend(key for key in intake.late_archive_sources()
                    if key not in selected and key not in (results_uf_turnout.IDENTITY, *results_official_congress.IDENTITIES))
    monkeypatch.setattr(results_native, "collect_sources",
                        lambda *args, **kwargs: pytest.fail("Scoped refresh must not acquire unrelated sources"))
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)

    result = intake.refresh_selected(registry, tmp_path / "scoped", previous, selected, NOW)
    persisted = intake.hydrate_collector_state(intake.unpack_state(json.loads(intake.pack_state(result))))
    assert calls == [key for key in selected if key not in mn.SOURCE_IDS] + list(mn.SOURCE_IDS)
    assert set(result["granular"]) == set(selected)
    assert result["granular"][selected[0]]["status"] == ohio_status
    assert all(result["granular"][identity]["status"] == pair_status for identity in mn.SOURCE_IDS)
    assert all(result["granular"][identity]["status"] == "reported"
               for identity in selected[1:] if identity not in mn.SOURCE_IDS)
    assert persisted["feeds"][selected[0]] == persisted["granular"][selected[0]]
    assert set(persisted["feeds"]) == set(previous["feeds"])
    assert persisted["feeds"]["unchanged"] == previous["feeds"]["unchanged"]
    for key in ("districts", "house", "congress", "directories", "source_stops"):
        assert result[key] == previous[key]
    assert intake.refresh_selected(registry, tmp_path / "scoped", persisted, selected, NOW) == result


def test_county_archive_revisions_keep_full_facts(tmp_path, monkeypatch):
    from scripts import results_turnout_history as history

    feed = "KS-2022-general-election-turnout-workbook"
    url = "https://www.sos.ks.gov/elections/22elec/2022-General-Election-Turnout-Information.xlsx"
    mock_source = {history.KS_URL: b"<a href='/elections/22elec/2022-General-Election-Turnout-Information.xlsx'>Turnout</a>",
                   url: b"42"}
    names = [f"county {i:03d}" for i in range(105)]
    monkeypatch.setattr(history, "KS_COUNTIES", pin(encoded(names)))

    def workbook(body):
        ballots = int(body)
        return {"counties": [[name, 0, ballots if i == 0 else 0, 100 if i == 1 else 40]
                             for i, name in enumerate(names)],
                "total": [0, ballots, 4260]}

    monkeypatch.setattr(history, "kansas_workbook", workbook)
    requested = []

    def acquire(_, target):
        requested.append(target)
        return mock_source[target], {"origin": "fixture"}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    first = history.collect_county_archive(collector, feed)
    rows = history.county_archive_rows({feed: first})
    assert len(rows) == 106
    assert rows[0]["reported_ballots_cast"] == 42
    assert rows[0]["rate_hold_reason"] == "ballots_exceed_registered"
    assert rows[1]["qualified_same_report_registration_fraction_pct"] == 0
    assert rows[-1]["rate_hold_reason"] == "county_conflict_included_in_statewide_total"
    collector.prior = {feed: first}
    mock_source[url] = b"37"
    requested.clear()
    assert history.collect_county_archive(collector, feed, reuse_checked_week=True) == first
    assert not requested
    revised = history.collect_county_archive(collector, feed)
    assert history.county_archive_rows({feed: revised})[-1]["qualified_same_report_registration_fraction_pct"] == 3700 / 4260
    collector.prior = {feed: revised}
    assert history.collect_county_archive(collector, feed) == revised
    mock_source[history.KS_URL] = b"<a href='/elections/26elec/2026-General-Election-Turnout-Information.xlsx'>Turnout</a>"
    requested.clear()
    retained = history.collect_county_archive(collector, feed)
    assert requested == [history.KS_URL]
    assert retained["data"] == revised["data"]
    assert retained["error"] == "report_not_linked"
    assert history.county_archive_rows({feed: retained})[0]["source_status"] == "retained_after_failure"
    mock_source[history.KS_URL] = b"<a href='/elections/22elec/2022-General-Election-Turnout-Information.xlsx'>Turnout</a>"
    mock_source[url] = b"38"
    collector.prior = {feed: retained}
    recovered = history.collect_county_archive(collector, feed, reuse_checked_week=True)
    assert recovered["status"] == "reported"
    assert recovered["data"]["complete_native_query"]["total"][1] == 38
    collector.prior = {feed: recovered}
    mock_source[url] = b"39"
    next_week = intake.Collector(tmp_path, collector.prior, EMPTY_STOPS, NOW + timedelta(days=2))
    following = history.collect_county_archive(next_week, feed, reuse_checked_week=True)
    assert following["archive_check_week_utc"] == "2026-11-16"
    assert following["data"]["complete_native_query"]["total"][1] == 39
    cached = intake.Collector(tmp_path, {feed: following}, EMPTY_STOPS, NOW + timedelta(days=9), offline=True)
    assert history.collect_county_archive(cached, feed)["archive_check_week_utc"] == "2026-11-16"


@pytest.mark.parametrize("election,header,measure", [
    ("2008-11-04", ["County Registered Voters Turnout Ballots Cast", "(based on voter history)"], "voter_history_credits"),
    ("2014-11-04", ["County Ballots Cast Registered Voters Turnout"], "ballots_cast"),
])
def test_west_virginia_archive_keeps_literal_basis_and_requires_reconciled_counties(election, header, measure):
    from scripts import results_turnout_history as history

    year = election[:4]
    lines = [f"{year} General", *header, *(f"{name} 2 4 50.0%" for name in history.WV_COUNTIES),
             "West Virginia 110 220 50.0%"]
    query = history.west_virginia_archive_query(lines, election)
    feed = f"WV-{year}-general-election-turnout-pdf"
    url = f"https://sos.wv.gov/media/{history.WV_ARCHIVES[election]}/download?inline"
    data = {"status": "reported", "source": {"url": history.WV_ARCHIVE_URL},
            "data": {"election_date": election, "report": {"url": url, "bytes": 1, "sha256": "a" * 64},
                     "complete_native_query": query, "participation_observation_qualified": False}}
    rows = history.county_archive_rows({feed: data})
    assert len(rows) == 56
    assert rows[-1]["participation_measure"] == measure
    assert rows[-1]["qualified_same_report_registration_fraction_pct"] == 50
    assert rows[-1]["reported_ballots_cast"] == (110 if measure == "ballots_cast" else None)
    assert rows[-1].get("reported_voter_history_credits") == (110 if measure == "voter_history_credits" else None)
    with pytest.raises(ValueError, match="state total"):
        history.west_virginia_archive_query([*lines[:-1], "West Virginia 111 220 50.0%"], election)
    held = history.west_virginia_archive_query([*lines[:-1], "West Virginia 110 220 49.9%"], election)
    data["data"]["complete_native_query"] = held
    assert history.county_archive_rows({feed: data})[-1]["rate_hold_reason"] == "printed_registration_fraction_disagrees"


@pytest.mark.parametrize(("date", "heading", "trailing"), [
    ("2006-11-07", ["Statewide Total Ballots Cast Official Summary",
                    "Wyoming General Election - November 7, 2006", "Total Ballots Cast"], []),
    ("2024-11-05", ["Statewide Total Ballots Cast",
                    "Wyoming General Election - November 5, 2024", "Total Ballots Cast"], ["Page 1 of 1"]),
])
def test_wyoming_county_archive_exports_ballots_without_registration(date, heading, trailing, tmp_path, monkeypatch):
    from scripts import results_turnout_history as history

    year = date[:4]
    feed = f"WY-{year}-general-election-ballots-pdf"
    county_lines = [f"{name} 2" for name in history.WY_COUNTIES]
    lines = [*heading, *county_lines, "Total 46", *trailing]
    query = history.wyoming_archive_query(lines, date)
    index, _ = history.county_archive_routes("WY", date)
    original = b"%PDF-1.7 fixture"
    report = {"url": history.WY_ARCHIVE_BASE + year + "/" + history.WY_ARCHIVES[date],
              **pin(original)}
    entry = {"status": "reported", "source": {"url": index}, "data": {
        "election_date": date, "report": report, "complete_native_query": query,
        "participation_observation_qualified": False}}
    rows = history.county_archive_rows({feed: entry})
    assert len(rows) == 24
    assert rows[-1]["reported_ballots_cast"] == 46
    assert any(row["geography_level"] == "state" for row in rows)
    assert all(row["reported_registered_voters"] is None
               and row["qualified_same_report_registration_fraction_pct"] is None
               and row["rate_hold_reason"] == "registration_not_in_report" for row in rows)
    with pytest.raises(ValueError, match="printed statewide total"):
        history.wyoming_archive_query([*heading, *county_lines, "Total 47", *trailing], date)

    entries = {feed: entry}
    receipt = history.county_archive_originals(entries)[feed]
    assert receipt == {"filename": feed + ".pdf", **report}
    file = tmp_path / receipt["filename"]
    with pytest.raises(FileNotFoundError):
        history.verify_county_archive_originals(entries, tmp_path)
    file.write_bytes(original.replace(b"1.7", b"1.6"))
    with pytest.raises(ValueError, match="Changed original"):
        history.verify_county_archive_originals(entries, tmp_path)
    file.write_bytes(original)
    monkeypatch.setattr(history, "wyoming_archive_report",
                        lambda body, election: query if (body, election) == (original, date) else None)
    assert history.verify_county_archive_originals(entries, tmp_path) == 1
    entry["data"]["complete_native_query"] = {**query, "counties": []}
    with pytest.raises(ValueError, match="extraction differs"):
        history.verify_county_archive_originals(entries, tmp_path)


def test_nebraska_canvass_discovers_current_book_and_rejects_bad_totals(tmp_path, monkeypatch):
    from scripts import nebraska_canvass as ne, results_turnout_history as history

    url = ne.BASE + "2026/General%20Canvass.pdf"
    index = f'<a href="{url}">General Election Official Results</a>'.encode()
    past = b'<a href="2024.pdf">General Election Official Results</a>'
    feed = ne.CURRENT_FEED
    phase = iter((past, index, index, past))
    prior = {}

    def pages(votes):
        counties = ne.COUNTIES
        return [
            ["OFFICIAL REPORT OF THE NEBRASKA BOARD OF STATE CANVASSERS", "GENERAL ELECTION NOVEMBER 3, 2026"],
            ["Number of Registered Voters", ne.REGISTRATION[2018][0], "Statewide Total 93 93 93 0 0 186",
             *(f"{name} 1 1 1 0 0 2" for name in counties[:45])],
            [f"{name} 1 1 1 0 0 2" for name in counties[45:]],
            ["Total Voting by Method", ne.VOTING[2022][0], f"Statewide Total {votes} 0 0 0 0 {votes}",
             *(f"{name} 0 0 0 0 0 0" for name in counties[:45])],
            [*(f"{name} 0 0 0 0 0 0" for name in counties[45:-1]),
             f"York {votes} 0 0 0 0 {votes}"],
        ]

    monkeypatch.setattr(ne, "parse", lambda body, date: ne.query(json.loads(body), date))

    def run():
        collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
        document = next(phase)
        monkeypatch.setattr(collector, "acquire", lambda link: (
            document if link == ne.INDEX else encoded(pages(1)), {"origin": "test"}))
        value = history.collect_county_archive(collector, feed)
        prior[feed] = value
        return value

    assert run()["status"] == "report_not_linked"
    accepted = run()
    assert run() == accepted
    held = run()
    assert held["status"] == "retained_after_failure" and held["data"] == accepted["data"]
    assert not history.county_archive_rows(prior)
    rows = history.county_archive_rows(prior, current_nebraska=True)
    assert len(rows) == 94 and rows[-2]["reported_total_voters"] == 1
    assert rows[-2]["qualified_same_report_registration_fraction_pct"] == 50
    assert all(row["reported_ballots_cast"] is None for row in rows)
    wrong = pages(1)
    wrong[-1][-1] = "York 0 0 0 0 0 0"
    with pytest.raises(ValueError, match="state total"):
        ne.query(wrong, ne.CURRENT)


def test_nebraska_scan_agreement_retention_and_no_reprocessing(tmp_path, monkeypatch):
    from scripts import nebraska_canvass as ne, results_turnout_history as history

    date = "2006-11-07"
    profile = ne.SCANS[date]
    feed = "NE-2006-general-election-canvass"
    report = ne.BOOKS[date]
    index = f'<a href="{report}">Official Results</a>'.encode()
    evidence = {"cover": [{"text": " ".join(profile["cover_headings"]),
                           "receipt": {"page": profile["cover_page"] + 1, "dpi": dpi}}
                          for dpi in ne.scan.DPI], "tables": {
        table: [[{"receipt": {"page": page + 1, "dpi": dpi}, "rows": [
            {"name": ne.scan.label(name), "literal_name": name,
             "literal_total": str(value * (len(ne.COUNTIES) if name == "TOTAL" else 1)),
             "total": value * (len(ne.COUNTIES) if name == "TOTAL" else 1),
             "high_confidence": True, "row": i}
            for i, name in enumerate(names, 1)]}
                 for dpi in ne.scan.DPI] for page, _, names, _, _ in panels]
        for value, (table, panels) in enumerate(profile["tables"].items(), 1)
    }}
    disputed = copy.deepcopy(evidence)
    row = disputed["tables"]["voted"][0][1]["rows"][1]
    row.update(total=3, literal_total="3")
    bad_control = copy.deepcopy(evidence)
    for view in bad_control["tables"]["voted"][0]:
        row = view["rows"][0]
        row.update(total=187, literal_total="187")
    bad_identity = copy.deepcopy(evidence)
    bad_identity["tables"]["voted"][0][0]["rows"][1]["literal_name"] = "Antelope"
    bad_date = copy.deepcopy(evidence)
    for view in bad_date["cover"]:
        view["text"] = view["text"].replace("2006", "2008")
    for bad, reason in ((disputed, "disagree between renders"), (bad_control, "printed state total"),
                        (bad_identity, "identities disagree"), (bad_date, "election date differs")):
        with pytest.raises(IntakeError, match=reason):
            ne.scan_query(bad, date)
    retained = ne.scan_query(evidence, date)
    reextracted = copy.deepcopy(evidence)
    views = reextracted["tables"]["voted"][0]
    views[1]["rows"][1]["high_confidence"] = False
    for row in views[1]["rows"][1:]:
        row["row"] += 1
    assert history.nebraska_canvass_original_matches(ne.scan_query(reextracted, date), retained, date)
    reordered = copy.deepcopy(reextracted)
    broken = reordered["tables"]["voted"][0][1]["rows"]
    broken[1]["row"] = broken[0]["row"]
    with pytest.raises(IntakeError, match="physical row order"):
        history.nebraska_canvass_original_matches({**retained, "scan_evidence": reordered}, retained, date)
    views[1]["rows"][1]["literal_name"] = views[1]["rows"][1]["literal_name"].upper()
    assert not history.nebraska_canvass_original_matches(ne.scan_query(reextracted, date), retained, date)
    views[0]["rows"][1]["high_confidence"] = False
    with pytest.raises(IntakeError, match="confidence floor"):
        history.nebraska_canvass_original_matches({**retained, "scan_evidence": reextracted}, retained, date)

    calls = []

    def parse(body, election):
        calls.append(body)
        return ne.scan_query(evidence if body == b"first edition" else disputed, election)

    monkeypatch.setattr(ne, "parse", parse)
    monkeypatch.setattr(ne, "scan_policy", lambda date: "original-policy")
    prior = {}

    def refresh(body):
        collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
        monkeypatch.setattr(collector, "acquire", lambda url: (
            index if url == ne.INDEX else body, {"origin": "test"}))
        value = history.collect_county_archive(collector, feed)
        prior[feed] = value
        return value

    first = refresh(b"first edition")
    assert first["status"] == "reported"
    assert refresh(b"first edition") == first
    held = refresh(b"changed edition")
    assert refresh(b"changed edition") == held
    assert calls == [b"first edition", b"changed edition"]
    assert held["status"] == "retained_after_failure" and held["error"] == "scan_reconciliation_failed"
    assert held["data"] == first["data"] and held["source"] == first["source"]
    assert history.county_archive_rows(prior)[-1]["reported_total_voters"] == 186
    monkeypatch.setattr(ne, "scan_policy", lambda date: "new-policy")
    assert refresh(b"changed edition")["error"] == "scan_reconciliation_failed"
    assert calls.count(b"changed edition") == 2
    assert "rejected_scan" not in refresh(b"first edition")


def test_scanned_panels_handle_wrapped_names_and_check_repeated_printed_controls():
    from scripts import results_pdf_archive_ocr as scan

    def cell(text, left=2, right=16):
        return {"text": text, "left": left, "right": right, "confidence": 1}

    first = (0, ("County total",), ("TOTAL", "Red Willow"), (0, 10), (28, 35))
    repeated = (1, ("County total",), ("TOTAL",), (0, 10), (28, 35))

    def views(page, rows):
        return [{"receipt": {"page": page, "dpi": dpi}, "text": "County total",
                 "role_cells": [[{**c, "left": c["left"] * dpi / 72, "right": c["right"] * dpi / 72}
                                 for c in row] for row in rows]} for dpi in scan.DPI]

    total = [cell("TOTAL"), cell("15", 24, 32)]
    raw = {0: views(1, [total, [cell("Red"), cell("15", 24, 32)], [cell("Willow")]]),
           1: views(2, [total])}
    profile = {"cover_page": 0, "cover_headings": ("County total",), "aliases": {},
               "tables": {"voted": (first, repeated)}}
    evidence = {"cover": [{"receipt": v["receipt"], "text": v["text"]} for v in raw[0]],
                "tables": {"voted": [[{"receipt": v["receipt"], "rows": scan.panel(v, panel, {})}
                                      for v in raw[panel[0]]] for panel in (first, repeated)]}}
    assert scan.verify(evidence, profile) == {"voted": {"TOTAL": 15, "Red Willow": 15}}
    for view in evidence["tables"]["voted"][1]:
        view["rows"][0].update(total=16, literal_total="16")
    with pytest.raises(IntakeError, match="disagree"):
        scan.verify(evidence, profile)


def test_scanned_native_control_requires_unique_exact_name_and_component_sum():
    from scripts import results_pdf_archive_ocr as scan

    line = "Red Willow 15 9 6"
    assert scan.native_control((line, "Willow 20 10 10"), "Red Willow", 3) == (line, 15)
    for lines in ((line, line), ("Red Willow 15 9 5",), ("Willow 15 9 6",)):
        assert scan.native_control(lines, "Red Willow", 3) == (None, None)


def test_colorado_statistics_revisions_reconcile_and_preserve_held_precinct(tmp_path, monkeypatch):
    from scripts import colorado_voting_statistics as co, results_turnout_history as history

    date, feed = "2024-11-05", "CO-2024-general-voting-statistics"
    index, report = co.routes(date)
    title = "<title>2024 Nov 5 • General • Voting Statistics • State of Colorado | State of Colorado</title>"
    authority = (title + f'<a href="{report.replace("co.elstats3.", "co.elstats.")}">Download</a>').encode()
    with pytest.raises(ValueError, match="election identity"):
        co.discover(authority.replace(b"Nov 5", b"Jun 5"), date)

    def edition(first):
        body = [",,Active Voters,Inactive Voters,Total Voters,Total Ballots Cast", ",,,,,",
                f"State,Colorado,1280,0,1280,{63 + first}"]
        for i, name in enumerate(co.COUNTIES):
            ballots = first if i == 0 else 1
            body.extend([f"County,{name},20,0,20,{ballots}",
                         f"Precinct,{i:010d},10,0,10,{ballots}",
                         f"Precinct,{i + 100:010d},10,0,10,0"])
        return ("\n".join(body) + "\n").encode()

    prior = {}

    def refresh(body):
        collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
        monkeypatch.setattr(collector, "acquire", lambda url: (authority if url == index else body, {"origin": "test"}))
        prior[feed] = history.collect_county_archive(collector, feed)
        return prior[feed]

    first = refresh(edition(9))
    assert refresh(edition(9)) == first
    assert refresh(edition(8))["data"]["complete_native_query"]["total"]["ballots_cast"] == 71
    higher = refresh(edition(11))
    for bad in (edition(11).replace(b"1280,74", b"1280,75"),
                edition(11).replace(b"10,0,10,11", b"10,0,10,12")):
        retained = refresh(bad)
        assert retained["status"] == "retained_after_failure" and retained["data"] == higher["data"]
    county = history.county_archive_rows(prior)
    units = history.county_archive_rows(prior, colorado_precincts=True)
    assert len(county) == 65 and len(units) == 128
    assert units[0]["ballots_cast"] == 11 and units[0]["rate_hold_reason"] == "ballots_exceed_registered"
    assert units[0]["qualified_same_report_registration_fraction_pct"] is None
    assert units[1]["qualified_same_report_registration_fraction_pct"] == 0
    original = history.county_archive_originals(prior)[feed]
    assert original["filename"].endswith(".csv")
    (tmp_path / original["filename"]).write_bytes(edition(11))
    assert history.verify_county_archive_originals(prior, tmp_path) == 1
    party_labeled = edition(11).replace(
        b",,Active Voters,Inactive Voters,Total Voters,Total Ballots Cast\n,,,,,\n",
        b",,Registered Voters,Active Voters,Inactive Voters,Total Ballots Cast\n,,Republican,,,\n"
    ).replace(b",1280,0,1280,", b",1280,1280,0,").replace(
        b",20,0,20,", b",20,20,0,").replace(b",10,0,10,", b",10,10,0,")
    with pytest.raises(ValueError, match="schema"):
        co.parse(party_labeled, date)
    date, feed = "2020-11-03", "CO-2020-general-voting-statistics"
    index, report = co.routes(date)
    authority = (title.replace("2024 Nov 5", "2020 Nov 3") + f'<a href="{report}">Download</a>').encode()
    accepted = refresh(party_labeled)
    assert accepted["data"]["complete_native_query"]["native_rows"][1] == co.PARTY_SUBHEADER
    for rows in (history.county_archive_rows({feed: accepted}),
                 history.county_archive_rows({feed: accepted}, colorado_precincts=True)):
        assert all(row["rate_hold_reason"] == co.REGISTRATION_HOLD
                   and row["qualified_same_report_registration_fraction_pct"] is None for row in rows)
        assert sum(row["reported_ballots_cast"] if "reported_ballots_cast" in row else row["ballots_cast"]
                   for row in rows if row.get("geography_level") != "state") == 74


def test_colorado_retains_reviewed_ballot_shortfalls_but_rejects_new_ones(tmp_path, monkeypatch):
    from scripts import colorado_voting_statistics as co, results_turnout_history as history

    date, feed = "2014-11-04", "CO-2014-general-voting-statistics"
    index, report = co.routes(date)
    authority = (f"<title>2014 Nov 4 • General • Voting Statistics • State of Colorado | State of Colorado</title>"
                 f'<a href="{report}">Download</a>').encode()
    rows = [",,Active Voters,Inactive Voters,Total Voters,Total Ballots Cast", ",,,,,",
            "State,Colorado,12800,0,12800,6436"]
    for i, name in enumerate(co.COUNTIES):
        gap = co.COUNTY_BALLOT_GAPS[date].get(name, 0)
        rows.extend([f"County,{name},200,0,200,100", f"Precinct,{i:010d},200,0,200,{100 - gap}"])
    body = "\n".join(rows).encode()
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    monkeypatch.setattr(collector, "acquire", lambda url: (authority if url == index else body, {"origin": "test"}))
    accepted = {feed: history.collect_county_archive(collector, feed)}
    county = history.county_archive_rows(accepted)
    statewide = next(row for row in county if row["geography_level"] == "state")
    assert statewide["reported_ballots_cast"] == 6436
    assert statewide["rate_hold_reason"] == "state_ballot_control_disagrees"
    assert statewide["state_ballot_shortfall"] == 36
    assert statewide["qualified_same_report_registration_fraction_pct"] is None
    assert "by 36" in statewide["report_note"]
    units = history.county_archive_rows(accepted, colorado_precincts=True)
    assert {row["county"]: row["county_ballot_shortfall"] for row in units
            if row["rate_hold_reason"] == "county_ballot_control_disagrees"} == {
                "Larimer": 43, "Rio Grande": 48, "Summit": 78}
    assert sum(row["qualified_same_report_registration_fraction_pct"] is None for row in units) == 3
    with pytest.raises(ValueError, match="state control"):
        co.parse(body.replace(b",6436\n", b",6437\n"), date)
    with pytest.raises(ValueError, match="Larimer precincts"):
        co.parse(body.replace(b",200,0,200,57\n", b",200,0,200,56\n"), date)
    corrected = body.replace(b",6436\n", b",6400\n").replace(b",200,0,200,57\n", b",200,0,200,100\n")
    query = co.parse(corrected, date)
    assert "state_ballot_shortfall" not in query and "Larimer" not in query["county_ballot_shortfalls"]


def test_virginia_locality_report_replays_and_keeps_curbside_out_of_the_sum(tmp_path, monkeypatch):
    from scripts import results_turnout_history as history

    names = sorted([f"TEST {i} COUNTY" for i in range(95)] + [f"TEST {i} CITY" for i in range(38)])
    monkeypatch.setattr(history, "VA_LOCALITY_ROSTER", pin(encoded(names))["sha256"])
    rows = [history.VA_LOCALITY_HEADER, *[(name, "1", "3", "2", "0", "6", "", "1") for name in names],
            ("Total", "133", "399", "266", "0", "798", "", "133")]

    def report(rows):
        return ("<title>2022 November General</title><h2 class=\"entry-title\">Official Results</h2>"
                "<p>Curbside numbers are included in the Total.</p>"
                "<p class=\"asOf\">Page generated on 12/06/2022 02:16 AM</p><table>"
                + "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows)
                + "</table>").encode()

    feed = "VA-2022-general-election-locality-turnout"
    original = report(rows)
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    monkeypatch.setattr(collector, "acquire", lambda url: (original, {"origin": "fixture"}))
    result = history.collect_county_archive(collector, feed)
    entries = {feed: result}
    exported = history.county_archive_rows(entries)
    assert len(exported) == 134
    assert sum(row["geography_level"] == "county_equivalent" for row in exported) == 38
    assert all(row["rate_hold_reason"] == "registration_not_in_report" for row in exported)
    assert exported[-1]["reported_ballots_cast"] == 798
    assert exported[-1]["reported_curbside"] == 133
    (tmp_path / f"{feed}.html").write_bytes(original)
    assert history.verify_county_archive_originals(entries, tmp_path) == 1
    collector.prior = entries
    original = report([*rows[:-1], ("Total", "133", "399", "266", "0", "931", "", "133")])
    failure = history.collect_county_archive(collector, feed)
    assert failure["status"] == "retained_after_failure" and failure["data"] == result["data"]


def test_national_release_discovery_distinguishes_links_from_participation(tmp_path, monkeypatch):
    from scripts import national_turnout_release_watch as watch

    def census(year, url):
        return (f'<a title="Voting and Registration in the Election of November {year}" '
                f'href="{url}"><span>Detailed tables</span></a>').encode()

    path = "/data/tables/time-series/demo/voting-and-registration/"
    prior = census(2024, path + "p20-590.html")
    candidate = census(2026, path + "next.html")
    body = prior + census(2026, "https://example.test" + path + "unofficial.html")
    calls = []

    def acquire(url):
        calls.append(url)
        return body, {"origin": "fixture"}

    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    monkeypatch.setattr(collector, "acquire", acquire)
    initial = watch.collect(collector, watch.CENSUS)
    assert initial["data"]["complete_native_query"] == {"release_status": "not_yet_linked", "links": []}
    collector.prior = {watch.CENSUS: initial}
    assert watch.collect(collector, watch.CENSUS, reuse_checked_week=True) == initial
    assert calls == [watch.INDEXES[watch.CENSUS]]
    body = candidate
    linked = watch.collect(collector, watch.CENSUS)
    assert linked["data"]["participation_observation_qualified"] is False
    assert linked["data"]["complete_native_query"]["release_status"] == "candidate_links_require_admission"
    from scripts import results_granular
    baseline = {"index.json": b'{"states": {}}'}
    assert results_granular.project(baseline, {watch.CENSUS: linked}) == (baseline, [])
    invalid = {**linked, "data": {**linked["data"], "updates": [{"id": "not-an-observation"}]}}
    with pytest.raises(ValueError, match="cannot project participation"):
        results_granular.project(baseline, {watch.CENSUS: invalid})
    collector.prior = {watch.CENSUS: linked}
    body = prior
    retained = watch.collect(collector, watch.CENSUS)
    assert retained["status"] == "retained_after_failure"
    assert retained["error"] == "release_index_regressed" and retained["data"] == linked["data"]
    with pytest.raises(ValueError, match="series not found"):
        watch.discover(b"<html>Unrecognized page</html>", watch.CENSUS)

    eac = b'''<button aria-controls="a"><span>2026</span></button>
      <a href="/sites/default/files/2026-09/2026_EAVS_Instrument.pdf">2026 Survey</a>
      <a href="/sites/default/files/2027-06/2026_Policy_Dataset.zip">CSV</a>'''
    older = b'''<button aria-controls="b">2024</button>
      <a href="/sites/default/files/2026-02/2024_EAVS_for_Public_Release_V2_csv.zip">CSV</a>'''
    csv = b'<a href="/sites/default/files/2027-06/2026_EAVS_for_Public_Release_V1_csv.zip">CSV</a>'
    codebook = b'<a href="/sites/default/files/2027-06/2026_EAVS_Codebook.xlsx">EAVS Codebook</a>'
    for new, status in [(b"", "not_yet_linked"), (csv, "incomplete_release_links"),
                        (csv + codebook, "candidate_links_require_admission")]:
        data = watch.discover(eac + new + older, watch.EAC)
        assert data["complete_native_query"]["release_status"] == status
        assert data["participation_observation_qualified"] is False


def test_maryland_registration_groups_preserve_unlocated_activity_and_retain_valid_pair(tmp_path, monkeypatch):
    import gzip
    from scripts import maryland_precinct_history as md, results_turnout_history as history

    date, feed = "2024-11-05", "MD-2024-general-precinct-affiliation-turnout"
    edition = md.EDITIONS[date]
    parties = sorted(md.PARTIES | {edition[-1]})
    native = [[county, cd, ld, precinct, party, *values]
              for county in md.COUNTIES for party in parties
              for cd, ld, precinct, values in (
                  ("02", "02A", "001-001", ["2", "1", "3", "0", "10"]),
                  ("", "", "Unable to Determine", ["0", "0", "0", "1", ""]),
              )]
    monkeypatch.setitem(md.EDITIONS, date, (*edition[:4], len(native), edition[-1]))
    control = "\n".join([f"Election Date: {edition[1]}", f"Election: {edition[2]}", f"As of: {edition[3]}",
                         *[f"{county} 14 7 21 7 70 70.00%" for county in md.COUNTIES],
                         "TOTAL 336 168 504 168 1,680 70.00%"])
    url, control_url = md.routes(date)
    bodies = {url: b"precinct query", control_url: b"control PDF"}
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    monkeypatch.setattr(collector, "acquire", lambda url: (bodies[url], {"origin": "fixture"}))
    monkeypatch.setattr(md, "parse", lambda body, pdf, election: md.query(native, control, election))
    accepted = history.collect_county_archive(collector, feed)
    assert accepted["status"] == "reported"
    entries = {feed: accepted}
    units, groups = md.exports(entries)
    assert len(units) == 336 and len(groups) == 175 and not history.county_archive_rows(entries)
    unknown = [row for row in units if not row["has_native_precinct_id"]]
    assert len(unknown) == 168 and all(row["eligible_registered"] is None for row in unknown)
    assert sum(r["reported_ballot_activity_without_precinct"] for r in groups if r["geography_level"] == "state") == 168
    assert all(r["participation_measure"] == md.NUMERATOR for r in groups)
    for spec in history.county_archive_originals(entries).values():
        (tmp_path / spec["filename"]).write_bytes(bodies[spec["url"]])
    assert history.verify_county_archive_originals(entries, tmp_path) == 2
    collector.prior = entries
    assert history.collect_county_archive(collector, feed)["data"] == accepted["data"]
    control = control.replace("Election Date: November 5, 2024", "Election Date: November 8, 2022")
    bodies[control_url] = b"changed control PDF"
    rejected = history.collect_county_archive(collector, feed)
    assert rejected["status"] == "retained_after_failure" and rejected["data"] == accepted["data"]
    monkeypatch.setattr(md, "EDITIONS", {date: md.EDITIONS[date]})
    archival = gzip.compress(encoded({feed: {key: accepted[key] for key in ("source", "data")}}), mtime=0)
    monkeypatch.setattr(md, "ARCHIVE_PIN", pin(archival))
    with pytest.raises(ValueError, match="archive checksum"):
        md.exports({}, archival[:-1])
    assert md.exports(entries, archival) == (units, groups)
    fallback = md.exports({feed: {"status": "source_stopped", "data": None}}, archival)
    assert all(row["source_status"] == "retained_after_failure"
               and row["latest_acquisition_status"] == "source_stopped"
               and row["archive_status"] == "reviewed_historical_archive"
               for frame in fallback for row in frame)
    assert tuple([[{k: v for k, v in row.items() if k not in ("archive_status", "latest_acquisition_status")}
                   | {"source_status": "reported"} for row in frame] for frame in fallback]) == (units, groups)


def test_maryland_2020_repeated_keys_require_independent_affiliation_totals(monkeypatch):
    from scripts import maryland_precinct_history as md

    date = "2020-11-03"
    edition = md.EDITIONS[date]
    parties = sorted((md.PARTIES - {"DEMOCRATIC"}) | {"DEMOCRAT", "BREAD AND ROSES", "WORKING CLASS PARTY"})
    native = [[county, cd, ld, precinct, party, *values]
              for county in md.COUNTIES for party in parties
              for cd, ld, precinct, values in (
                  ("02", "02A", "001-001", ["2", "1", "3", "0", "10"]),
                  ("", "", "Unable to Determine", ["0", "0", "0", "1", ""]),
                  ("", "", "Unable to Determine", ["0", "0", "0", "1", ""]),
              )]
    monkeypatch.setitem(md.EDITIONS, date, (*edition[:4], len(native), edition[-1]))
    control = "\n".join([f"Election Date: {edition[1]}", f"Election: {edition[2]}",
                         *[f"{county} 16 8 24 16 80 80.00%" for county in md.COUNTIES],
                         "TOTAL 384 192 576 384 1,920 80.00%",
                         *[line for party in parties for line in
                           [party.title(), *[f"{county} 2 1 3 2 10 80.00%" for county in md.COUNTIES],
                            "TOTAL 48 24 72 48 240 80.00%"]]])
    assert md.query(native, control, date)["native_rows"] == native
    native[1][8], native[4][8] = "2", "0"
    with pytest.raises(ValueError, match="no longer reconcile by affiliation"):
        md.query(native, control, date)


@pytest.mark.parametrize("date", ["2012-11-06", "2014-11-04", "2024-11-05"])
def test_minnesota_workbook_revisions_and_offline_original(tmp_path, monkeypatch, date):
    import io
    from openpyxl import Workbook
    from scripts import minnesota_precinct_history as mn, results_turnout_history as history

    year = date[:4]
    monkeypatch.setitem(mn.EDITIONS, date, (mn.EDITIONS[date][0], 87, 870, 87))

    def workbook(change=0, compensate=True):
        wb = Workbook()
        results = wb.active
        results.title = "Precinct-Results" if year == "2024" else "Results"
        aliases = {"REG7AM": "7AM", "AB_MB": "REGMILOVAB"} if year == "2012" else {}
        results.append([aliases.get(k, k) for k in mn.FIELDS])
        definitions = wb.create_sheet("Fields")
        definitions.append(("TOTVOTING", "Number of voters casting ballots"))
        definitions.append((aliases.get("REG7AM", "REG7AM"), "Registered at 7AM"))
        definitions.append(("EDR", "Voters registering when they vote" if year == "2024"
                            else "Voters registering in the polling place on election day"))
        counties = wb.create_sheet("Counties")
        counties.append(("County Code", "County Name", "County FIPS"))
        for i in range(1, 88):
            name, fips = f"COUNTY {i}", 27000 + 2 * i - 1
            counties.append((i, name, fips))
            voting = 10 + (change if i == 1 else -change if i == 2 and compensate else 0)
            precinct = f"{fips}0001"
            results.append((int(precinct) if year == "2014" else precinct, "Precinct", "0001", "Municipality",
                            name, i, 9, 1, 7, 3, 0, voting))
        if year == "2012":
            results.append((None, "TOTALS", None, None, None, None, 783, 87, 609, 261, 0,
                            870 + (change if not compensate else 0)))
        target = io.BytesIO()
        wb.save(target)
        return target.getvalue()

    feed = f"MN-{year}-general-precinct-turnout-workbook"
    original = workbook()
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    monkeypatch.setattr(collector, "acquire", lambda url: (original, {"origin": "fixture"}))
    accepted = history.collect_county_archive(collector, feed)
    collector.prior = {feed: accepted}
    repeat = history.collect_county_archive(collector, feed)
    assert repeat["data"] == accepted["data"]
    original = workbook(2)
    revised = history.collect_county_archive(collector, feed)
    entries = {feed: revised}
    rows = history.county_archive_rows(entries, minnesota_precincts=True)
    assert len(rows) == 87 and [r["reported_total_voters"] for r in rows[:2]] == [12, 8]
    assert rows[0]["precinct_id"] == "270010001"
    if year == "2012":
        assert rows[0]["reported_accepted_absentee_mail"] is None
        assert rows[0]["reported_accepted_regular_military_overseas_absentee"] == 3
    county_rows = history.county_archive_rows(entries)
    assert len(county_rows) == 88 and county_rows[-1]["reported_total_voters"] == 870
    assert county_rows[-1]["registered_at_7am"] == 783
    assert all(r["qualified_same_report_registration_fraction_pct"] is None for r in county_rows)
    (tmp_path / f"{feed}.xlsx").write_bytes(original)
    assert history.verify_county_archive_originals(entries, tmp_path) == 1
    original = workbook(2, compensate=False)
    collector.prior = entries
    rejected = history.collect_county_archive(collector, feed)
    assert rejected["status"] == "retained_after_failure" and rejected["data"] == revised["data"]


def test_colorado_legacy_mixed_reporting_labels_do_not_become_precincts():
    from scripts import colorado_voting_statistics as co

    def edition(election, mixed=False):
        labels = co.MODES if mixed else ["Active Voters"]
        rows = [["", "", *labels, co.BALLOTS], [""] * (len(labels) + 3)]
        for i, name in enumerate(co.COUNTIES):
            values = ["1", "2", "0", "0", "3"] if mixed else ["4", "3"]
            rows.extend([["County", name, *values],
                         ["Precinct", "Absentee" if mixed else f"{i:010d}", *values]])
        rows.insert(2, ["State", "Colorado", *[str(int(v) * 64) for v in rows[2][2:]]])
        return co.query(rows, election)

    mixed = edition("2004-11-02", mixed=True)
    assert mixed["precincts"] == {}
    assert mixed["registration_hold"] == co.REGISTRATION_NOT_REPORTED
    assert mixed["total"]["ballots_cast"] == 192
    assert len(mixed["native_rows"]) == 131
    regular = edition("2010-11-02")
    assert len(regular["precincts"]) == 64
    assert regular["registration_hold"] == co.ACTIVE_REGISTRATION_HOLD
    with pytest.raises(ValueError, match="voting modes"):
        changed = copy.deepcopy(mixed["native_rows"])
        changed[4][-1] = "2"
        co.query(changed, "2004-11-02")


def test_colorado_legacy_county_only_respects_historical_roster():
    from scripts import colorado_voting_statistics as co

    rows = [["", "", "Registered Voters", co.BALLOTS], [""] * 4,
            ["State", "Colorado", "630", "441"],
            *[["County", name, "10", "7"] for name in co.COUNTIES if name != "Broomfield"]]
    query = co.query(rows, "2000-11-07")
    assert len(query["counties"]) == 63 and query["total"]["registered"] == 630
    assert query["registration_basis"] == "Registered voters in the same report"
    with pytest.raises(ValueError, match="geography"):
        co.query([*rows, ["County", "Broomfield", "0", "0"]], "2000-11-07")


def test_full_refresh_preserves_scoped_county_archive_on_source_failure(tmp_path, monkeypatch):
    from scripts import colorado_voting_statistics as co, results_granular, results_turnout_history as history

    registry = fixture(tmp_path)
    election, feed = "2000-11-07", "CO-2000-general-voting-statistics"
    index, report = co.routes(election)
    authority = (f"<title>2000 Nov 7 • General • Voting Statistics • State of Colorado | State of Colorado</title>"
                 f'<a href="{report}">Download</a>').encode()
    body = "\n".join([",,Registered Voters,Total Ballots Cast", ",,,", "State,Colorado,630,441",
                      *[f"County,{name},10,7" for name in co.COUNTIES if name != "Broomfield"]]).encode()
    prior = {"feeds": {}, "granular": {},
             "directories": {state: {"status": "not_listed_in_directory"} for state in intake.STATES},
             "source_stops": EMPTY_STOPS,
             "districts": districts(declaration())}
    prior["house"] = dict.fromkeys(prior["districts"], {"status": "source_unavailable", "data": None})
    bodies = {index: authority, report: body}
    monkeypatch.setattr(intake.Collector, "acquire", lambda _, url: (bodies[url], {"origin": "test"}))
    intake.refresh_selected(registry, tmp_path / "scoped", prior, [feed], NOW)
    scoped = intake.hydrate_collector_state(intake.read(tmp_path / "scoped/state.json"))
    assert feed not in scoped["feeds"]

    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    monkeypatch.setattr(results_granular, "collect", lambda collector, _: {
        feed: history.collect_county_archive(collector, feed, reuse_checked_week=True)})
    reuse = tmp_path / "reuse"
    reused = intake.collect(registry, reuse, scoped, now=NOW)
    state = intake.hydrate_collector_state(intake.read(reuse / "state.json"))
    assert state["granular"][feed] == scoped["granular"][feed]
    assert not any(attempt["id"] == feed for attempt in reused["source_attempts"])
    with zipfile.ZipFile(reuse / "complete-results.zip") as archive:
        archive.extractall(tmp_path / "package")
    assert intake.replay(tmp_path / "package", tmp_path / "replayed")["passed"]
    status_rows = csv.DictReader(io.StringIO((tmp_path / "replayed/source-status.csv").read_text()))
    assert next(row for row in status_rows if row["source"] == feed)["archive_check_week_utc"] == "2026-11-09"

    intake.collect(registry, tmp_path / "full", scoped, now=NOW + timedelta(days=2))
    full = intake.hydrate_collector_state(intake.read(tmp_path / "full/state.json"))
    retained = full["granular"][feed]
    assert full["feeds"][feed] == retained
    assert retained["status"] == "retained_after_failure"
    assert retained["first_observed_at"] == scoped["granular"][feed]["first_observed_at"]
    assert retained["data"] == scoped["granular"][feed]["data"]
    rows = history.county_archive_rows(full["granular"])
    assert len(rows) == 64
    assert all(row["source_status"] == "retained_after_failure" for row in rows)
    assert next(row for row in rows if row["geography_level"] == "state")["reported_ballots_cast"] == 441


def test_nebraska_current_county_reports_keep_independent_last_good_editions(tmp_path, monkeypatch):
    from scripts import nebraska_county_reports as reports

    def index(*names):
        return ("2026 General Election<table>" + "".join(
            f"<tr><td>{name}</td><td><a href='election_files/{name}/2026_General_official_results.pdf'>"
            "Official Results</a></td><td>11/17/2026 10:00 AM</td></tr>" for name in names) + "</table>").encode()

    def lines(name, total, day):
        return ["Summary Results Report", f"NE {name} 261103 General Election_6110", "November 3, 2026",
                "Official Results", f"{name} County, Nebraska", "Statistics TOTAL Election Day Early Voting Provisional",
                f"Ballots Cast - Total {total} {day} 3 2", "Election Summary - 11/17/2026 11:00 AM 1 of 3"]

    def extract(body, county, status):
        total, day = map(int, body.split())
        native = lines(county, total, day)
        return {"native_lines": native, **reports.query(native, county, status)}

    monkeypatch.setattr(reports, "extract", extract)
    prior = {}

    def refresh(adams, box, names=("Adams", "Box Butte")):
        bodies = {reports.INDEX: index(*names), reports.report_url("Adams", "Official Results"): adams,
                  reports.report_url("Box Butte", "Official Results"): box}
        collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
        monkeypatch.setattr(collector, "acquire", lambda url: (bodies[url], {"origin": "test"}))
        prior[reports.FEED] = reports.collect(collector)
        return prior[reports.FEED]

    assert "Box%20Butte" in reports.discovery(index("Box Butte"))["Box Butte"]["url"]
    first = refresh(b"10 5", b"10 5")
    assert refresh(b"10 5", b"10 5") == first
    refresh(b"9 4", b"11 5")
    rows = {row["county"]: row for row in reports.rows(prior)}
    assert len(rows) == 93
    assert rows["Adams"]["ballots"] == 9
    assert rows["Box Butte"]["ballots"] == 10 and rows["Box Butte"]["disposition"] == "ballot_modes_disagree"
    assert rows["Blaine"]["disposition"] == "compatible_report_not_linked" and "ballots" not in rows["Blaine"]
    refresh(b"11 6", b"10 5", names=("Adams",))
    rows = {row["county"]: row for row in reports.rows(prior)}
    assert rows["Adams"]["ballots"] == 11
    assert rows["Box Butte"]["source_status"] == "retained_after_failure"


def test_nebraska_county_scan_requires_both_editions_and_does_not_accept_precinct_summary():
    from scripts import nebraska_county_reports as reports, results_turnout_history as history

    evidence = [{"receipt": {"page": 1, "dpi": dpi}, "high_confidence": [True] * 4, "cells": [
        ["Summary Results Report", "Official Results"], ["General Election"],
        ["November 3, 2026", "Adams County, Nebraska"], ["Statistics", "TOTAL", "Election", "Early", "Provisional"],
        ["Day", "Voting"], ["Ballots Cast - Total", "10", "5", "3", "2"],
        ["Election Summary - 11/17/2026 11:00 AM", "1 of 3"],
    ]} for dpi in reports.DPI]
    status = "Official Results"
    facts = reports.scan_query(evidence, "Adams", status)
    assert facts["ballots"] == 10
    spaced = copy.deepcopy(evidence)
    spaced[1]["cells"][2][1] = "AdamsCounty, Nebraska"
    spaced[1]["cells"][5][0] = "Ballots Cast- Total"
    spaced[1]["cells"][-1][0] = spaced[1]["cells"][-1][0].replace(" AM", "AM")
    spaced[1]["cells"][-1][1] = "1of3"
    spaced[1]["high_confidence"][0] = False
    assert history.nebraska_county_original_matches({"scan_evidence": spaced, **facts},
                                                    {"scan_evidence": evidence, **facts}, "Adams", status)
    spaced[1]["cells"][-1][1] = "1 of 4"
    assert not history.nebraska_county_original_matches({"scan_evidence": spaced, **facts},
                                                        {"scan_evidence": evidence, **facts}, "Adams", status)
    with pytest.raises(IntakeError, match="Unsupported county scan layout"):
        reports.scan_query(evidence, "Adams", "Unofficial Results")
    precinct = copy.deepcopy(evidence)
    for view in precinct:
        view["cells"].insert(3, ["Precinct 1"])
    with pytest.raises(IntakeError, match="countywide"):
        reports.scan_query(precinct, "Adams", "Official Results")
    evidence[1]["cells"][5][1:] = ["12", "7", "3", "2"]
    with pytest.raises(IntakeError, match="did not agree"):
        reports.scan_query(evidence, "Adams", "Official Results")


def test_nebraska_county_scan_corroborates_a_total_only_report():
    from scripts import nebraska_county_reports as reports

    evidence = [{"receipt": {"page": 1, "dpi": dpi}, "high_confidence": [True], "cells": [
        ["Summary Results Report", "Official Results"], ["General Election"],
        ["November 3, 2026", "Adams County, Nebraska"], ["Statistics"], ["TOTAL"],
        ["Registered Voters - Total", "30"], ["Ballots Cast - Total", "20"],
        ["Voter Turnout - Total", "66.67%"],
        ["1 of 3"], ["Election Summary - 11/17/2026 11:00 AM"],
    ]} for dpi in reports.DPI]
    query = reports.scan_query(evidence, "Adams", "Official Results")
    assert query["ballots"] == 20 and query["election_day"] is None
    assert query["control_percentage"] == "66.67%"
    for view in evidence:
        view["cells"][7][1] = "66.66%"
    with pytest.raises(IntakeError, match="registration-and-rate control"):
        reports.scan_query(evidence, "Adams", "Official Results")


def test_nebraska_paired_sources_preserve_blue_book_discrepancy_and_pin_both(tmp_path, monkeypatch):
    from scripts import nebraska_canvass as ne, results_turnout_history as history

    date, feed = ne.PAIRED_ELECTION, "NE-2002-general-election-canvass"
    url, _ = ne.routes(date)
    report = ne.BOOKS[date]
    header = ("Nebraska General Election Statistics November 5, 2002 Abstract of Votes "
              "Number of People Voting Number of Persons Voting Registered Voters")
    markers = {"Douglas": "1", "Johnson": "2", "Sarpy": "3"}
    county_rows = [f"{name}{markers.get(name, '')} ... 1 4 0 0 0 0 4 0 0 2 2" for name in ne.COUNTIES]
    native = [[header, *county_rows[:31]], [header, *county_rows[31:62]],
              [header, *county_rows[62:], "TOTAL ... 93 372 0 0 0 0 372 0 0 184 184"]]
    control = "-- November 5, 2002 186 372"
    facts = ne.blue_book_query(native, control)
    assert facts["blue_book_printed_statewide_voters"] == 184 and facts["total"]["ballots_cast"] == 186
    with pytest.raises(ValueError, match="disagree with the official canvass"):
        ne.blue_book_query(native, "-- November 5, 2002 184 372")

    calls = []

    def parse(companion, main):
        calls.append((companion, main))
        if companion != b"approved":
            raise ValueError("Revised report does not reconcile")
        return facts

    monkeypatch.setattr(ne, "parse_blue_book", parse)
    prior = {}

    def refresh(companion):
        bodies = {url: f'<a href="{report}">Official Results</a>'.encode(),
                  report: b"state control", ne.BLUE_BOOK: companion}
        collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
        monkeypatch.setattr(collector, "acquire", lambda url: (bodies[url], {"origin": "test"}))
        prior[feed] = history.collect_county_archive(collector, feed)
        return prior[feed]

    accepted = refresh(b"approved")
    assert accepted["status"] == "reported" and refresh(b"approved") == accepted
    held = refresh(b"revised")
    assert held["status"] == "retained_after_failure" and held["data"] == accepted["data"]
    assert calls == [(b"approved", b"state control"), (b"revised", b"state control")]
    originals = history.county_archive_originals(prior)
    assert set(originals) == {feed, feed + "-blue-book"}
    for key, body in ((feed, b"state control"), (feed + "-blue-book", b"approved")):
        (tmp_path / originals[key]["filename"]).write_bytes(body)
    assert history.verify_county_archive_originals(prior, tmp_path) == 2
    assert history.county_archive_rows(prior)[-1]["reported_total_voters"] == 186


def test_nebraska_old_canvass_preserves_printed_total_and_malformed_component():
    from scripts import nebraska_canvass as ne, results_turnout_history as history

    date = "2008-11-04"
    url = ne.BASE + "2008/" + ne.BOOKS[date]
    link = f'<a href="{url.replace("%20", " ")}">2008 General Election Official Results</a>'
    assert history.archive_link(link.encode(), *ne.routes(date)) == url
    names = ne.COUNTIES
    registration = [f"{name} 150000 0 0 0 0 0 150000" for name in names]
    voting = [f"{name} 0 0 0 0 0" if name != "Lancaster"
              else "Lancaster 98,900 2,9192 517 12 128,621" for name in names]
    pages = [
        ["Official Results of Nebraska General Election - November 4, 2008"],
        ["Number of Registered Voters", ne.REGISTRATION[2008][0], "Totals 13950000 0 0 0 0 0 13950000",
         *registration[:45]],
        registration[45:],
        ["Total Voting By Location", ne.VOTING[2008][0], "Totals 98900 29192 517 12 128621", *voting[:45]],
        voting[45:],
    ]
    query = ne.query(pages, date)
    lancaster = next(row for row in query["counties"] if row["county"] == "Lancaster")
    assert lancaster["ballots_cast"] == 128621
    assert lancaster["rate_hold_reason"] == "malformed_printed_voting_method"
    bad = [*pages[:4], [line.replace("128,621", "128,622") for line in pages[4]]]
    with pytest.raises(ValueError, match="county rows"):
        ne.query(bad, date)


def test_county_archive_outage_attempts_shared_index_once_per_collection(tmp_path, monkeypatch):
    from scripts import results_turnout_history as history

    feeds = [feed for feed, (state, _) in history.COUNTY_ARCHIVES.items() if state == "CA"]
    prior = {feed: {"status": "reported", "data": {"election_date": date},
                    "first_observed_at": "old"}
             for feed, (state, date) in history.COUNTY_ARCHIVES.items() if state == "CA"}
    calls = []

    def acquire(_, source, *, access_guard):
        url = source["url"]
        access_guard(url)
        calls.append(url)
        if len(calls) == 1:
            raise IntakeError("source_unavailable", "Fixture index timeout")
        return b"<html>No report links</html>", {"origin": "fixture"}

    monkeypatch.setattr(Store, "acquire", acquire)
    batch = [*feeds, history.CA_CURRENT_FEED]
    collector = intake.Collector(tmp_path, prior, EMPTY_STOPS, NOW)
    results = {feed: history.collect_county_archive(collector, feed) for feed in batch}
    assert calls == [history.CA_URL]
    assert all(result["error"] == "source_unavailable" and result["error_stage"] == "acquisition"
               for result in results.values())
    assert len(collector.attempts) == len(batch)
    for feed in feeds:
        assert results[feed]["status"] == "retained_after_failure"
        assert results[feed]["data"] == prior[feed]["data"]
        assert results[feed]["first_observed_at"] == "old"
    assert results[history.CA_CURRENT_FEED]["data"] is None
    assert collector.stopped == EMPTY_STOPS

    next_run = intake.Collector(tmp_path, results, EMPTY_STOPS, NOW)
    recovered = {feed: history.collect_county_archive(next_run, feed) for feed in batch}
    assert calls == [history.CA_URL, history.CA_URL]
    assert all(result["error"] == "report_not_linked" and result["error_stage"] == "parsing"
               for result in recovered.values())


def test_california_checked_scan_keeps_denominators_and_source_conflicts_separate():
    from scripts import results_turnout_history as history

    scans = json.loads(Path(history.__file__).with_name(history.CA_SCAN_FILE).read_bytes())["reports"]
    cases = {"1990-11-06": 7899131, "1992-11-03": 11374565, "1994-11-08": 8900632}
    for date, statewide in cases.items():
        feed = f"CA-{date[:4]}-general-election-turnout-pdf"
        report = {"url": history.california_report_url(date), **scans[date]["pdf"]}
        query = history.california_scan(report, date)
        rows = history.county_archive_rows({feed: {
            "status": "reported", "source": {"url": history.CA_URL}, "data": {
                "election_date": date, "report": report, "complete_native_query": query,
                "participation_observation_qualified": False,
            },
        }})
        assert len(rows) == 59 and rows[-1]["reported_total_voters"] == statewide
        if date == "1992-11-03":
            assert rows[-1]["reported_voting_age_population"] == 20863687
            assert rows[-1]["reported_eligible_to_register"] is None
            assert next(row for row in rows if row["geography"] == "Santa Cruz")["rate_hold_reason"] == (
                "printed_registration_fraction_disagrees")
        if date == "1994-11-08":
            assert "8,900,593" in rows[-1]["report_note"]
        with pytest.raises(intake.IntakeError, match="new checked transcription"):
            history.california_scan({**report, "sha256": "0" * 64}, date)


@pytest.mark.parametrize("current", [False, True])
def test_california_county_archive_uses_native_measure_and_rejects_bad_revision(tmp_path, monkeypatch, current):
    from types import SimpleNamespace

    import pypdf

    from scripts import results_turnout_history as history

    election = history.CA_CURRENT_ELECTION if current else "2024-11-05"
    year, day = int(election[:4]), int(election[-2:])
    feed = f"CA-{year}-general-election-turnout-pdf"
    url = (history.california_report_url("2024-11-05").replace("2024-general", "2026-general")
           if current else history.california_report_url(election))
    landing = f"<a href='{url}'>November {day}, {year} - General Election (PDF)</a>".encode()

    def report(count, total, report_day=day, note=True):
        footnote = ("1Registered Voters totals are based on the 15-day Report of Registration and do not "
                    "include voters registered after the 15-day close of registration." if note else "")
        return f"""NOVEMBER {report_day}, {year}, GENERAL ELECTION
VOTER PARTICIPATION STATISTICS BY COUNTY
County Number of Eligible to Registered Precinct Vote-By-Mail Total Percent of Turnout Turnout
Precincts Register Voters1 Voters* Voters Voters Vote-By-Mail Registered Eligible
Alameda 1 200 100 0* * {count} {count} 100.00% {count:.2f}% {count / 2:.2f}%
State Total 1 200 100 0 {total} {total}
Percent 50.00% 0.00% 100.00% 100.00% {total:.2f}% {total / 2:.2f}%
{footnote}
""".encode()

    monkeypatch.setattr(history, "CA_COUNTIES", ["Alameda"])
    monkeypatch.setattr(pypdf, "PdfReader", lambda buf: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda **_: buf.read().decode())]))
    bodies = {history.CA_URL: landing, url: b"%PDF-1.6\n" + report(70, 70)}
    requested = []

    def acquire(_, target):
        requested.append(target)
        return bodies[target], {"origin": "fixture"}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    if current:
        for invalid in (landing.replace(b"General Election", b"Primary Election"),
                        landing.replace(b"admin.cdn.sos.ca.gov", b"outside.test")):
            bodies[history.CA_URL] = invalid
            requested.clear()
            absent = history.collect_county_archive(collector, feed)
            assert absent["error"] == "report_not_linked" and absent["data"] is None
            assert requested == [history.CA_URL]
        bodies[history.CA_URL] = landing

    def rows_for(entry):
        return history.county_archive_rows({feed: entry}, current_california=current)

    first = history.collect_county_archive(collector, feed)
    rows = rows_for(first)
    assert len(rows) == 2
    assert rows[0]["reported_ballots_cast"] is None
    assert rows[0]["reported_total_voters"] == 70
    assert rows[0]["reported_eligible_to_register"] == 200
    assert rows[0]["reported_turnout_eligible_pct"] == "35.00%"
    assert rows[0]["qualified_same_report_registration_fraction_pct"] == 70
    if current:
        from scripts.supported_analytical_release import selected_local_observation_ids

        assert history.county_archive_rows({feed: first}) == []
        assert selected_local_observation_ids({
            "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": [feed]},
            "granular_sources": {feed: first},
        }) == set()
        bodies[url] = b"%PDF-1.6\n" + report(70, 70, note=False)
        unqualified = rows_for(history.collect_county_archive(collector, feed))
        assert unqualified[0]["reported_total_voters"] == 70
        assert unqualified[0]["rate_hold_reason"] == "registration_timing_unqualified"
        bodies[url] = b"%PDF-1.6\n" + report(70, 70).replace(b"Registered Eligible", b"Eligible Registered")
        wrong_headers = history.collect_county_archive(collector, feed)
        assert wrong_headers["data"] is None and "columns differ" in wrong_headers["error_detail"]
    collector.prior = {feed: first}
    for bad in (report(72, 71), report(70, 70, report_day=6)):
        bodies[url] = b"%PDF-1.6\n" + bad
        retained = history.collect_county_archive(collector, feed)
        assert retained["status"] == "retained_after_failure"
        assert retained["data"] == first["data"]
    bodies[url] = b"%PDF-1.6\n" + report(68, 68)
    revised = history.collect_county_archive(collector, feed)
    assert rows_for(revised)[-1]["reported_total_voters"] == 68
    collector.prior = {feed: revised}
    assert history.collect_county_archive(collector, feed) == revised
    if current:
        assert "archive_check_week_utc" not in revised
        bodies[url] = b"%PDF-1.6\n" + report(67, 67)
        next_report = history.collect_county_archive(collector, feed, reuse_checked_week=True)
        assert rows_for(next_report)[-1]["reported_total_voters"] == 67


def test_indiana_archive_uses_only_declared_general_report_and_keeps_count_conflicts(monkeypatch):
    from scripts import results_indiana_turnout as indiana

    url = "https://www.in.gov/dA/0123456789/turnout.pdf?language_id=1"
    assert indiana.report_link(f'<a href="{url}">2026 Primary Election Registration and Turnout Data</a>'.encode(),
                               2026) is None
    assert indiana.report_link(f'<a href="{url}"><strong>2026 General Election</strong> '
                               'Registration and Turnout Data</a>'.encode(), 2026) == url
    with pytest.raises(ValueError, match="outside the reviewed archive"):
        indiana.report_link(b'<a href="https://outside.test/2026.pdf">'
                            b'2026 General Election Registration and Turnout Data</a>', 2026)
    counties = ["County " + chr(65 + i // 26) + chr(65 + i % 26) for i in range(92)]
    monkeypatch.setattr(indiana, "COUNTIES_SHA", indiana.digest(("\n".join(counties) + "\n").encode()))
    lines = ["2026 General Election", "Tuesday, November 3, 2026  General Election Turnout and Registration",
             indiana.HEADER, *(f"{county}  100  40  40 %  25  15  38 %" for county in counties)]
    lines[3] = f"{counties[0]}  100  40  40 %  30  15  38 %"
    lines += ["9,200 3,680 40 % 2,305 1,380 38 %", "Page 1 of 1  Monday, November 16, 2026"]
    parsed = indiana.parse_pages(["\n".join(lines)], 2026)
    data = {**parsed, "report": {"url": url, "sha256": "a" * 64, "bytes": 42}}
    rows = indiana.rows({indiana.FEEDS[2026]: {"status": "reported", "data": data}})
    assert len(rows) == 93
    assert rows[-1]["voters_voting"] == 3680 and rows[-1]["mode_count_minus_voters_voting"] == 5
    assert rows[-1]["qualified_registered_fraction_pct"] is rows[0]["qualified_registered_fraction_pct"] is None
    assert rows[1]["qualified_registered_fraction_pct"] == 40
    data["complete_native_query"][-1][1] += 1
    with pytest.raises(ValueError, match="column totals do not reconcile"):
        indiana.rows({indiana.FEEDS[2026]: {"status": "reported", "data": data}})


def test_nc_age_archive_waits_for_both_links_and_preserves_last_good(tmp_path, monkeypatch):
    import io
    from zipfile import ZipFile

    from scripts import results_nc_vote_history as nc

    counties = [f"COUNTY{i:03}" for i in range(100)]
    monkeypatch.setattr(nc, "COUNTY_PIN", nc.digest(("\n".join(counties) + "\n").encode()))

    def report(kind, updated, value):
        fields = nc.HEADERS[kind].split()
        lines = ["\t".join(fields)]
        for county in counties:
            ages = (*nc.AGES, nc.REGISTRATION_ONLY_AGE) if kind == "voter" else nc.AGES
            for age in ages:
                row = dict(county_desc=county, election_date="11/03/2026", stats_type=kind,
                           update_date=updated, age=age, total_voters=str(value))
                lines.append("\t".join(row.get(key, "") for key in fields))
        out = io.BytesIO()
        with ZipFile(out, "w") as archive:
            archive.writestr(f"{kind}_stats_20261103.txt", "\n".join(lines))
        return out.getvalue()

    reports = {kind: nc.report_url(kind, nc.ELECTION) for kind in nc.CATALOGS}
    bodies = {
        nc.CATALOGS["history"]: f'<a href="{reports["history"]}">History</a>'.encode(),
        nc.CATALOGS["voter"]: b"<p>Not yet published</p>",
        reports["history"]: report("history", "12/01/2026", 4),
        reports["voter"]: report("voter", "11/03/2026", 10),
    }
    calls = []

    def acquire(self, url):
        calls.append(url)
        return bodies[url], {"origin": "fixture"}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    work = tmp_path / "nc"
    initial = nc.collect(intake.Collector(work, {}, EMPTY_STOPS, NOW))
    assert initial["status"] == "report_not_linked" and initial["data"] is None
    assert calls == list(nc.CATALOGS.values())

    bodies[nc.CATALOGS["voter"]] = f'<a href="{reports["voter"]}">Registration</a>'.encode()
    accepted = nc.collect(intake.Collector(work, {}, EMPTY_STOPS, NOW))
    assert accepted["status"] == "reported"
    prior = {nc.FEED: accepted}
    rows = nc.rows(prior)
    assert [(r["voters_with_history"], r["active_and_inactive_registered_voters"],
             r["source_defined_rate_pct"]) for r in rows] == [(400, 1000, 40)] * 4
    assert all(r["geography_level"] == "state" and not r["reporting_completeness_or_certification_established"]
               for r in rows)
    assert all(r["registrations_outside_the_four_paired_age_groups"] == 1000 for r in rows)
    assert nc.collect(intake.Collector(work, prior, EMPTY_STOPS, NOW)) == accepted

    bodies[reports["history"]] = report("history", "11/30/2026", 5)
    retained = nc.collect(intake.Collector(work, prior, EMPTY_STOPS, NOW))
    assert retained["status"] == "retained_after_failure" and retained["data"] == accepted["data"]
    bodies[reports["history"]] = report("history", "12/02/2026", 11)
    revised = nc.collect(intake.Collector(work, prior, EMPTY_STOPS, NOW))
    assert revised["status"] == "reported"
    assert all(r["voters_with_history"] == 1100 and r["source_defined_rate_pct"] is None
               for r in nc.rows({nc.FEED: revised}))


def test_accepted_candidate_strings_survive_a_blocked_live_declaration(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    rows = [{"state_code": row["state_code"], "district": row["district"],
             "name": "A", "party": "D", "votes": "12", "source_updated_at": "old",
             "source_url": row["url"]} for row in districts(declaration()).values()]
    body = encoded(rows)
    (registry.parent / "candidates.json").write_bytes(body)
    config = intake.read(registry)
    config["accepted_queries"] = {
        "accepted-current-candidate-queries.json": {"file": "candidates.json", **pin(body)}}
    intake.write(registry, config)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    report = intake.collect(registry, tmp_path / "run", now=NOW)
    assert report["house_districts_available"] == 435
    state = intake.read(tmp_path / "run/state.json")
    assert all(row["data"]["candidates"][0]["votes"] == 12 for row in state["house"].values())
    assert all(row["url"] is None for row in state["districts"].values())
    assert all(row["retained_districts"] == row["available_districts"]
               for row in state_totals(state["house"], state["districts"]))
    rows[0]["votes"] = None
    with pytest.raises(ValueError, match="accepted candidate"):
        intake.house_baseline(rows)


def test_cached_resume_keeps_new_stops_and_never_opens_transport(tmp_path, monkeypatch):
    work = tmp_path / "run"
    store = Store(work / "cache")
    body = b'{"value":12}'
    sha = intake.digest(body)
    store.object(body)
    store.db.execute("INSERT INTO inputs VALUES(?,?,?,?,?)",
                     ("https://example.test/allowed", sha, None, None, None))
    store.db.commit()
    monkeypatch.setattr("urllib.request.build_opener",
                        lambda *args: pytest.fail("Offline resume opened transport"))
    collector = intake.Collector(work, {}, EMPTY_STOPS, NOW, offline=True)
    assert collector.acquire("https://example.test/allowed")[0] == body
    registry = fixture(tmp_path)
    intake.write(work / "source-stops.json",
                 {"urls": [intake.API + "/AL/capabilities"], "prefixes": [], "hosts": []})
    intake.collect(registry, work, now=NOW, offline=True)
    assert intake.API + "/AL/capabilities" in intake.read(work / "source-stops.json")["urls"]


def test_all51_full_queries_and_extracted_packet_replay_without_network(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    report = intake.collect(registry, tmp_path / "run", now=NOW)
    assert report["jurisdictions"] == 51 and report["house_districts_available"] == 0
    snapshot = json.loads(gzip.decompress((tmp_path / "run/snapshot.json.gz").read_bytes()))
    assert len(snapshot["jurisdictions"]) == 51
    assert len(snapshot["participation_observations"]) == 51
    assert all(row["observation"]["count"]["value"] is None
               for row in snapshot["participation_observations"])
    packet = tmp_path / "packet"
    with zipfile.ZipFile(tmp_path / "run/complete-results.zip") as archive:
        assert archive.testzip() is None
        archive.extractall(packet)
    replayed = intake.replay(packet, tmp_path / "reproduced")
    assert replayed["complete_outputs"] == 10
    subprocess.run([sys.executable, "-c",
        "import sys; sys.path[:0]=['code']; "
        "from scripts import results_pdf_tables as pdf; "
        "from scripts import results_pdf_boston, results_json_statistics, results_pdf_periodic; "
        "from scripts import results_pdf_periodic_ocr, automatic_native_refresh; "
        "from scripts import results_pdf_affiliations, results_pdf_jefferson, results_pdf_cass, results_pdf_dunn; "
        "from scripts import results_native_state_family, results_native_virginia; "
        "from scripts import results_native_delaware, results_native_dc, results_native_idaho; "
        "from scripts import results_native_north_carolina; "
        "from scripts import results_native_utah; "
        "from scripts import results_state_statistics; "
        "from scripts import native_pdf, pdf_group_queries; "
        "import json; "
        "assert pdf.Path('code/scripts/results_pdf_cass.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_pdf_cass.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_cass.py').is_file(); "
        "assert pdf.Path('code/scripts/results_pdf_dunn.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_pdf_dunn.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_state_family.py').is_file(); "
        "assert pdf.Path('code/scripts/results_native_virginia.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_virginia.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_virginia_repair.py').is_file(); "
        "assert pdf.Path('code/scripts/results_native_delaware.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_delaware.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/delaware-native/accepted-de-shard.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/delaware-native/complete-turnout.json').is_file(); "
        "assert pdf.Path('code/scripts/results_native_dc.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_dc.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/dc-native-accepted.json').is_file(); "
        "assert pdf.Path('code/scripts/results_native_idaho.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_idaho.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/idaho-native/accepted-data.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/idaho-native/accepted-ballots.xlsx.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/idaho-native/accepted-templates.json.gz').is_file(); "
        "assert pdf.Path('code/scripts/results_native_north_carolina.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_north_carolina.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/north-carolina-native/accepted-reporting.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/north-carolina-native/accepted-templates.json.gz').is_file(); "
        "assert pdf.Path('code/scripts/results_native_utah.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_native_utah.py').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/api-data.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/frozen-ut.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/rolling7416-ut.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/utah-native/summaries/cache-summary.pdf.gz').is_file(); "
        "assert pdf.Path('code/scripts/results_state_statistics.py').is_file(); "
        "assert pdf.Path('code/tests/test_results_state_statistics.py').is_file(); "
        "assert pdf.Path('code/scripts/results_native_louisiana_runtime.py').is_file(); "
        "assert pdf.Path('code/scripts/louisiana_bootstrap.py').is_file(); "
        "assert pdf.Path('code/tests/test_louisiana_onboarding.py').is_file(); "
        "assert pdf.Path('code/tests/LOUISIANA_ONBOARDING_TESTS.txt').is_file(); "
        "assert pdf.Path('code/tests/fixtures/louisiana-native/authority-resolution.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/louisiana-native/route-authority.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/louisiana-native/source-baseline/index.json').is_file(); "
        "assert pdf.Path('code/tests/fixtures/dunn-accepted.json').is_file(); "
        "assert (pdf.Path('code/tests/fixtures/results_pdf_periodic') / "
        "'complete-products.json.gz').is_file(); "
        "assert (pdf.Path('code/tests/fixtures/results_pdf_periodic') / "
        "'sussex-ocr-views.json.gz').is_file(); "
        "assert pdf.Path('code/tests/fixtures/results_pdf_jefferson/"
        "complete-pages.json.gz').is_file(); "
        "p=json.loads(pdf.Path(pdf.__file__).with_name('results_pdf_grids.json').read_bytes()); "
        "assert len(p['source']['grids']) == 14; "
        "import pytest; "
        "assert pytest.main(['-q', '-p', 'no:cacheprovider', "
        "'code/tests/test_results_pdf_cass.py', "
        "'code/tests/test_results_native_cass.py', "
        "'code/tests/test_results_pdf_dunn.py', "
        "'code/tests/test_results_native_state_family.py', "
        "'code/tests/test_results_native_virginia.py', "
        "'code/tests/test_results_native_virginia_repair.py', "
        "'code/tests/test_results_native_delaware.py', "
        "'code/tests/test_results_native_dc.py', "
        "'code/tests/test_results_native_idaho.py', "
        "'code/tests/test_results_native_north_carolina.py', "
        "'code/tests/test_results_native_utah.py', "
        "'code/tests/test_results_state_statistics.py']) == 0"],
        cwd=packet, check=True, capture_output=True)
    assert (tmp_path / "reproduced/granular-source-queries.json.gz").is_file()
    assert (tmp_path / "reproduced/declared-numerical-queries.json.gz").is_file()
    (packet / "queries/coverage.csv").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed"):
        intake.replay(packet, tmp_path / "second")


def test_same_data_is_a_numerical_noop_despite_new_check_time(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    def fetch(self, url):
        self.guard(url)
        if url.endswith("/capabilities"):
            state = url.split("/")[-2]
            body = encoded({"state": state, "categories": {"inperson": {"race": False}}})
        elif url == intake.NATIONAL_URL:
            body = encoded(declaration())
        else:
            raise IntakeError("source_unavailable", "Fixture unavailable")
        return body, {"origin": "new_source_response", **pin(body)}
    monkeypatch.setattr(intake.Collector, "acquire", fetch)
    first = intake.collect(registry, tmp_path / "first", now=NOW)
    second = intake.collect(registry, tmp_path / "second", intake.read(tmp_path / "first/state.json"),
                            now=NOW.replace(hour=1))
    assert first["version"] == second["version"]
    assert first["files"] == second["files"]


def test_complete_factual_products_are_not_duplicated_as_participation_observations(tmp_path):
    registry = fixture(tmp_path)
    config = intake.read(registry)
    baseline = intake.baseline_inputs(registry.parent / "accepted", config["baseline"])
    facts = {"status": "reported", "source": {"url": "https://example.test/workbook"},
             "data": {"numerical_data_qualified": False,
                      "tables": [{"rows": [["label", "count"], ["native", 0], ["missing", None]]}]},
             "error": None, "first_observed_at": NOW.isoformat()}
    native = {"status": "reported", "source": {"url": "https://example.test/statistics"},
              "data": {"ballots": 0, "source_update_label": None}}
    inputs = {"feeds": {"CA-product": facts, "CA-official": native},
              "house": {}, "districts": {},
              "directories": {state: {"status": "not_listed"} for state in intake.STATES},
              "granular": {}, "products": {"CA-product": facts}}
    before = copy.deepcopy(inputs)
    outputs = intake.project(inputs, baseline)
    snapshot = json.loads(gzip.decompress(outputs["snapshot.json.gz"]))
    observations = snapshot["participation_observations"]
    assert len(observations) == 52
    assert observations[-1]["observation"] == native["data"]
    assert all(row["channel"] != "CA-product" for row in observations)
    query = outputs["declared-numerical-queries.json.gz"]
    assert json.loads(gzip.decompress(query)) == inputs["products"]
    reference = snapshot["declared_numerical_products_query"]
    assert reference == {"file": "declared-numerical-queries.json.gz", **pin(query)}
    indexed = snapshot["declared_numerical_products"]["CA-product"]
    assert indexed["complete_factual_query"] == {**reference, "key": "CA-product"}
    assert indexed["factual_data_available"] is True and "data" not in indexed
    assert inputs == before


def test_source_status_export_includes_current_native_holds(tmp_path):
    import csv
    import io

    registry = fixture(tmp_path)
    config = intake.read(registry)
    baseline = intake.baseline_inputs(registry.parent / "accepted", config["baseline"])
    url = "https://example.test/turnout"
    held = {"status": "source_stopped", "data": None, "source": None,
            "attempted_source_url": url, "error": "source_stopped",
            "error_stage": "acquisition", "error_detail": "HTTP 403"}
    inputs = {"feeds": {"GA-native-test": {"status": "reported"},
                        "GA-official": {"status": "not_reported"}},
              "house": {}, "districts": {},
              "directories": {state: {"status": "not_listed"} for state in intake.STATES},
              "granular": {"GA-native-test": held}}
    outputs = intake.project(inputs, baseline)
    snapshot = json.loads(gzip.decompress(outputs["snapshot.json.gz"]))
    csv_rows = list(csv.DictReader(io.StringIO(outputs["source-status.csv"].decode())))
    assert [row["source"] for row in csv_rows] == ["GA-native-test", "GA-official"]
    row = csv_rows[0]
    assert (row["status"], row["source_url"], row["error_stage"], row["error_detail"]) == (
        "source_stopped", url, "acquisition", "HTTP 403")
    assert snapshot["source_status"][0]["data_retained"] is False


def test_invalid_stop_seed_is_fail_closed_before_transport(tmp_path):
    with pytest.raises(ValueError, match="ledger"):
        intake.Collector(tmp_path, {}, {"urls": None, "prefixes": [], "hosts": []}, NOW)


def test_partial_clone_publisher_does_not_fetch_unchanged_blobs(tmp_path):
    remote = tmp_path / "remote"
    local = tmp_path / "publisher"
    subprocess.run(["git", "init", str(remote)], check=True, capture_output=True)
    original = GitPublisher(remote, ref="results-data")
    original.git("config", "uploadpack.allowFilter", "true")
    parent = original.commit(original.tree(None, {"archive.txt": b"unchanged"}), None, "Original")
    original.git("update-ref", original.ref_path, parent)
    old_blob = original.git("rev-parse", parent + ":archive.txt")
    subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none", remote.as_uri(), str(local)],
                   check=True, capture_output=True)
    publisher = GitPublisher(local, ref="results-data")
    assert "?" + old_blob in publisher.git("rev-list", "--objects", "--missing=print", parent)
    staged = publisher.commit(publisher.tree(parent, {"latest.json": b"new"}), parent, "Successor")
    assert "?" + old_blob in publisher.git("rev-list", "--objects", "--missing=print", staged)
    publisher.promote(staged, parent)
    assert original.git("rev-parse", staged + ":archive.txt") == old_blob
    assert original.git("show", staged + ":latest.json") == "new"


@pytest.mark.parametrize("interrupt_staging", [False, True, "successor"])
def test_real_git_publication_keeps_main_and_persists_last_good_results(
        tmp_path, monkeypatch, interrupt_staging):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    work = tmp_path / "run"
    report = intake.collect(registry, work, now=NOW)
    collected = intake.read(work / "state.json")
    full_entry = {
        "status": "reported",
        "source": {"url": "https://official.example/native"},
        "data": {"updates": [{"id": "one", "value": 0}],
                 "complete_native_query": [0, None, 7]},
    }
    collected.setdefault("feeds", {})["LA-native"] = copy.deepcopy(full_entry)
    collected.setdefault("granular", {})["LA-native"] = copy.deepcopy(full_entry)
    collected = intake.compact_collector_state(collected)
    intake.write(work / "state.json", collected)
    repo = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    interrupted_once = False

    def verify(self, commit, files):
        nonlocal interrupted_once
        if interrupt_staging and not interrupted_once and any(
                name.startswith("snapshots/" + report["version"]) for name in files):
            interrupted_once = True
            raise OSError("Temporary verification outage")
        for name, expected in files.items():
            assert pin(subprocess.check_output(
                ["git", "-C", str(self.repository), "show", commit + ":" + name])) == expected
    monkeypatch.setattr(GitPublisher, "verify_files", verify)
    intake.write(work / "publication-parent.json", {"parent": None})
    git = GitPublisher(repo, ref="results-data")
    previous_head = None
    before_latest = before_state = ""
    if interrupt_staging == "successor":
        prior = tmp_path / "prior"
        shutil.copytree(work, prior)
        intake.write(prior / "report.json", {**report, "version": "a" * 64})
        previous_head = intake.publish(repo, "results-data", "fixture/results", prior)["data_commit"]
        before_latest = git.git("show", previous_head + ":latest.json")
        before_state = git.git("show", previous_head + ":state.json")
        intake.write(work / "publication-parent.json", {"parent": previous_head})
        collected["source_stops"]["urls"].append("https://example.test/newly-stopped")
        intake.write(work / "state.json", collected)
        intake.write(work / "source-stops.json", collected["source_stops"])
    if interrupt_staging:
        with pytest.raises(OSError, match="Temporary verification outage"):
            intake.publish(repo, "results-data", "fixture/results", work)
        stage = git.remote_head()
        assert git.git("show", stage + ":latest.json", check=False) == before_latest
        assert git.git("show", stage + ":state.json", check=False) == before_state
        if previous_head is not None:
            assert "https://example.test/newly-stopped" in json.loads(
                git.git("show", stage + ":source-stops.json"))["urls"]
        with pytest.raises(ValueError, match="staged collection must be activated"):
            intake.publisher_state(repo, "results-data", "fixture/results", tmp_path / "next")
        intake_checkout = tmp_path / "next-runner"
        subprocess.run(["git", "init", "-b", "main", str(intake_checkout)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(intake_checkout), "remote", "add", "origin", str(remote)], check=True)
        monkeypatch.setattr(intake.Collector, "acquire", lambda *args: pytest.fail("Recollected after staging"))
        result = intake.resume_publication(intake_checkout, "results-data", "fixture/results")
        assert result["results_commit"] == stage
        assert intake.resume_publication(intake_checkout, "results-data", "fixture/results")["status"] == (
            "no_pending_publication")
        git.fetch_parent(result["data_commit"])
    else:
        result = intake.publish(repo, "results-data", "fixture/results", work)
    assert result["status"] == "published"
    assert result["version"] == report["version"]
    published = json.loads(subprocess.check_output(
        ["git", "-C", str(repo), "show", result["data_commit"] + ":state.json"]))
    assert published["contract"] == intake.STATE_CONTRACT
    assert intake.unpack_state(published) == intake.read(work / "state.json")
    _, restored = intake.publisher_state(repo, "results-data", "fixture/results", tmp_path / "next")
    assert restored == intake.read(work / "state.json")
    hydrated = intake.hydrate_collector_state(restored)
    assert hydrated["feeds"]["LA-native"]["data"] == full_entry["data"]
    assert subprocess.check_output(["git", "-C", str(repo), "symbolic-ref", "HEAD"]).strip() == b"refs/heads/main"
    intake.write(work / "publication-parent.json", {"parent": result["data_commit"]})
    assert intake.publish(repo, "results-data", "fixture/results", work)["status"] == "unchanged"
    head = result["data_commit"]
    assert subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "--heads", "origin"]) == b""
    assert subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "--tags", "origin", "refs/tags/results-data"]
    ).decode().split()[0] == head


@pytest.mark.parametrize("separate_ledger_only_stop", [False, True])
def test_interrupted_publication_merges_stops_without_changing_results(
        tmp_path, separate_ledger_only_stop):
    repo, remote = tmp_path / "repository", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    publisher = GitPublisher(repo, ref="results-data")
    publisher.git("remote", "add", "origin", str(remote))
    old = {**EMPTY_STOPS, "hosts": ["previously-stopped.test"]}
    ledger = {**old, "prefixes": ["https://separately-stopped.test/"]} if separate_ledger_only_stop else old
    new = {**EMPTY_STOPS, "urls": ["https://example.test/stopped"]}
    state = {"source_stops": old, "feeds": {"retained": {"status": "reported"}}}
    latest = b'{"version":"last-good"}\n'
    parent = publisher.commit(publisher.tree(None, {
        "state.json": intake.pack_state(state),
        "source-stops.json": intake.encoded(ledger),
        "latest.json": latest,
        "snapshots/last-good/complete-results.zip": b"immutable original packet",
    }), None, "Original")
    publisher.promote(parent, None)

    failed = tmp_path / "failed"
    intake.write(failed / "publication-parent.json", {"parent": parent})
    intake.write(failed / "source-stops.json", new)
    with pytest.raises(ValueError, match="durable stops preserved"):
        intake.publish(repo, "results-data", "fixture/results", failed)
    successor = publisher.remote_head()
    expected = intake.merge_stops(old, ledger, new)
    assert json.loads(publisher.git("show", successor + ":source-stops.json")) == expected
    assert intake.unpack_state(json.loads(publisher.git("show", successor + ":state.json"))) == {
        **state, "source_stops": expected,
    }
    assert set(publisher.git("diff", "--name-only", parent, successor).splitlines()) == {
        "source-stops.json", "state.json",
    }
    intake.write(failed / "publication-parent.json", {"parent": successor})
    with pytest.raises(ValueError, match="durable stops preserved"):
        intake.publish(repo, "results-data", "fixture/results", failed)
    assert publisher.remote_head() == successor


def test_saved_source_stops_batch_keeps_latest_and_refuses_stale_or_pending_parent(tmp_path):
    repo, remote = tmp_path / "repository", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    publisher = GitPublisher(repo, ref="results-data")
    publisher.git("remote", "add", "origin", str(remote))
    state = {"source_stops": EMPTY_STOPS, "feeds": {"retained": {"status": "reported"}}}
    latest = b'{"version":"last-good"}\n'
    parent = publisher.commit(publisher.tree(None, {
        "state.json": intake.pack_state(state),
        "source-stops.json": intake.encoded(EMPTY_STOPS),
        "latest.json": latest,
    }), None, "Original")
    publisher.promote(parent, None)
    paths = [tmp_path / "first.json", tmp_path / "second.json"]
    for i, path in enumerate(paths):
        intake.write(path, {**EMPTY_STOPS, "urls": [f"https://official.example/{i}"]})
    result = intake.merge_saved_source_stops(repo, parent, paths)
    successor = result["data_commit"]
    assert result["status"] == "published_source_stops"
    assert publisher.git("show", successor + ":latest.json") == latest.decode().strip()
    expected = intake.merge_stops(*(intake.read(path) for path in paths))
    assert json.loads(publisher.git("show", successor + ":source-stops.json")) == expected
    assert intake.unpack_state(json.loads(publisher.git("show", successor + ":state.json"))) == {
        **state, "source_stops": expected,
    }
    assert intake.merge_saved_source_stops(repo, successor, paths) == {
        "status": "unchanged", "data_commit": successor,
    }
    with pytest.raises(ValueError, match="parent has changed"):
        intake.merge_saved_source_stops(repo, parent, paths)
    staged = publisher.commit(publisher.tree(successor, {
        intake.PENDING_PUBLICATION: b'{"version":"staged"}\n',
    }), successor, "Staged collection")
    publisher.promote(staged, successor)
    with pytest.raises(ValueError, match="Resume the staged collection"):
        intake.merge_saved_source_stops(repo, staged, paths)
    assert publisher.remote_head() == staged


def test_data_tag_updates_preserve_main_and_reject_stale_or_backward_publication(tmp_path):
    repo, remote = tmp_path / "repository", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    code = GitPublisher(repo, ref="main")
    main = code.commit(code.tree(None, {"README": b"Retained website source\n"}), None, "Source")
    code.promote(main, None)
    data = GitPublisher(repo)
    first = data.commit(data.tree(None, {"catalog.json": b'{"value":0}\n'}), None, "First data")
    data.promote(first, None)
    data.fetch_parent(first)
    second = data.commit(
        data.tree(first, {"catalog.json": b'{"value":1}\n'}), first, "Next data")
    data.promote(second, first)
    assert data.remote_head() == second
    with pytest.raises(IntakeError, match="advanced"):
        data.promote(first, first)
    with pytest.raises(IntakeError, match="discarding history"):
        data.promote(first, second)
    assert data.remote_head() == second
    assert code.remote_head() == main
    assert subprocess.check_output(
        ["git", "-C", str(repo), "ls-remote", "--heads", "origin"]
    ).decode().splitlines() == [main + "\trefs/heads/main"]



def test_granular_alias_compaction_is_idempotent_strict_and_publishable():
    full_entry = {
        "status": "reported",
        "source": {"url": "https://official.example/native"},
        "data": {"updates": [{"id": "one", "value": 0}],
                 "complete_native_query": [0, None, 7]},
    }
    state = {
        "source_stops": copy.deepcopy(EMPTY_STOPS),
        "feeds": {"LA-native": copy.deepcopy(full_entry)},
        "granular": {"LA-native": copy.deepcopy(full_entry)},
        "house": {}, "districts": {}, "directories": {}, "products": {},
    }
    compact = intake.compact_collector_state(state)
    assert intake.compact_collector_state(compact) == compact
    assert intake.pack_state(state) == intake.pack_state(compact)
    unpacked = intake.unpack_state(json.loads(intake.pack_state(compact)))
    assert unpacked == compact
    assert intake.hydrate_collector_state(unpacked) == state
    legacy = {"source_stops": copy.deepcopy(EMPTY_STOPS),
              "feeds": {"old": {"data": 0}}}
    assert intake.hydrate_collector_state(
        intake.compact_collector_state(legacy)) == legacy
    for mutation in ("contract", "key", "pin", "missing_pin", "extra"):
        broken = copy.deepcopy(compact)
        alias = broken["feeds"]["LA-native"]["data"]
        if mutation == "contract":
            alias["contract"] = "changed"
        elif mutation == "key":
            alias["granular_key"] = "different"
        elif mutation == "pin":
            alias["data_pin"]["sha256"] = "0" * 64
        elif mutation == "missing_pin":
            alias.pop("data_pin")
        else:
            alias["extra"] = True
        with pytest.raises(ValueError):
            intake.compact_collector_state(broken)
        with pytest.raises(ValueError):
            intake.hydrate_collector_state(broken)
        with pytest.raises(ValueError):
            intake.pack_state(broken)
    missing = copy.deepcopy(compact)
    del missing["granular"]["LA-native"]
    with pytest.raises(ValueError, match="target is missing"):
        intake.pack_state(missing)
    null_full = copy.deepcopy(compact)
    null_full["granular"]["LA-native"]["data"] = None
    with pytest.raises(ValueError, match="no full data"):
        intake.pack_state(null_full)
    alias_full = copy.deepcopy(compact)
    alias_full["granular"]["LA-native"]["data"] = copy.deepcopy(
        alias_full["feeds"]["LA-native"]["data"])
    with pytest.raises(ValueError, match="full data is an alias"):
        intake.pack_state(alias_full)


def test_complete_state_storage_preserves_legacy_unknown_zero_and_full_native_facts(monkeypatch):
    state = {"source_stops": EMPTY_STOPS,
             "feeds": {"zero": {"data": {"count": 0, "native": ["literal", None, 17]}},
                       "unknown": {"data": {"count": None, "clock": None}}},
             "facts": "complete numerical cells " * 1000}
    envelope = json.loads(intake.pack_state(state))
    assert len(intake.pack_state(state)) < len(encoded(state))
    assert intake.unpack_state(envelope) == state
    assert intake.unpack_state(copy.deepcopy(state)) == state
    mutations = [
        {**envelope, "contract": "unrecognized"},
        {**envelope, "decoded": {**envelope["decoded"], "sha256": "0" * 64}},
        {**envelope, "decoded": {**envelope["decoded"], "bytes": 1}},
        {**envelope, "gzip_base64": "!invalid"},
        {**envelope, "source_stops": {**EMPTY_STOPS, "hosts": ["stopped.test"]}},
    ]
    for changed in mutations:
        with pytest.raises((ValueError, EOFError, OSError)):
            intake.unpack_state(changed)
    monkeypatch.setattr(intake, "MAX_STATE_BYTES", 10)
    with pytest.raises(ValueError, match="size"):
        intake.unpack_state(envelope)


def test_completed_collection_restores_without_transport_and_rejects_lost_stops(tmp_path, monkeypatch):
    from scripts import results_granular

    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    feed = "WY-test-county-product"
    monkeypatch.setattr(results_granular, "collect", lambda *_: {
        feed: {"status": "reported", "source": {"url": "https://example.test/aggregate"},
               "data": {"participation_observation_qualified": False, "complete_native_query": [7]}}})
    original = tmp_path / "original"
    report = intake.collect(registry, original, now=NOW)
    compact = intake.read(original / "state.json")
    assert compact["feeds"][feed]["data"]["contract"] == intake.GRANULAR_ALIAS_CONTRACT
    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must never acquire a source")
    monkeypatch.setattr(intake.Collector, "acquire", forbidden)
    packet, report_path = original / "complete-results.zip", original / "report.json"
    with pytest.raises(ValueError, match="refusing recovery rollback"):
        intake.restore(packet, report_path, tmp_path / "older",
                       latest={"checked_at": NOW.replace(hour=1).isoformat()})
    assert not (tmp_path / "older").exists()
    lost_stop = {"source_stops": {**EMPTY_STOPS, "hosts": ["new-stop.test"]}}
    with pytest.raises(ValueError, match="drop current durable"):
        intake.restore(packet, report_path, tmp_path / "rejected", lost_stop)
    assert not (tmp_path / "rejected").exists()
    with zipfile.ZipFile(packet) as archive:
        state_bytes = archive.getinfo("inputs/selected-source-facts.json").file_size
        overhead = sum(item.file_size for item in archive.infolist()) - state_bytes
    with monkeypatch.context() as limits:
        limits.setattr(intake, "MAX_STATE_BYTES", state_bytes - 1)
        with pytest.raises(ValueError, match="inventory or size"):
            intake.restore(packet, report_path, tmp_path / "state-too-large")
    with monkeypatch.context() as limits:
        limits.setattr(intake, "MAX_RECOVERY_NON_STATE_BYTES", overhead - 1)
        with pytest.raises(ValueError, match="inventory or size"):
            intake.restore(packet, report_path, tmp_path / "archive-too-large")
    destination = tmp_path / "restored"
    with monkeypatch.context() as limits:
        limits.setattr(intake, "MAX_STATE_BYTES", state_bytes)
        limits.setattr(intake, "MAX_RECOVERY_NON_STATE_BYTES", overhead)
        result = intake.restore(packet, report_path, destination)
    assert result["network_requests"] == 0 and result["original_packet_and_queries_unchanged"]
    assert result["version"] == report["version"]
    for name in (*report["files"], "state.json", "report.json", "source-stops.json"):
        assert (destination / name).read_bytes() == (original / name).read_bytes()
    with pytest.raises(ValueError, match="fresh publication"):
        intake.restore(packet, report_path, destination)
    changed = {**report, "files": {**report["files"],
               "complete-results.zip": {**report["files"]["complete-results.zip"], "sha256": "0" * 64}}}
    intake.write(tmp_path / "changed-report.json", changed)
    with pytest.raises(ValueError, match="Changed or unvalidated"):
        intake.restore(packet, tmp_path / "changed-report.json", tmp_path / "changed")
    assert not (tmp_path / "changed").exists()


def test_weekly_checkpoint_requires_the_full_current_registry(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    original = tmp_path / "original"
    intake.collect(registry, original, now=NOW)
    config = intake.registry_config(registry)
    baseline = intake.baseline_inputs(registry.parent / config["baseline"]["root"], config["baseline"])
    inputs = intake.hydrate_collector_state(intake.read(original / "state.json"))
    feeds = intake.late_archive_sources()
    weekly = tmp_path / "weekly"
    inputs["collection_scope"] = {
        "mode": "selected_registered_source_refresh",
        "source_ids": sorted(feeds),
        "all_other_acquisitions_and_native_count_clocks_reused_not_retrieved_again": True,
    }
    report = intake.export_collection(weekly, config, baseline, inputs, {}, NOW, [])
    monkeypatch.setattr(intake.Collector, "acquire", lambda *_: pytest.fail("Recovery attempted transport"))
    packet, report_path = weekly / "complete-results.zip", weekly / "report.json"
    restored = tmp_path / "restored-weekly"
    result = intake.restore(packet, report_path, restored, require_late_archive_scope=True)
    assert result["version"] == report["version"] and result["network_requests"] == 0
    assert all((weekly / name).read_bytes() == (restored / name).read_bytes() for name in report["files"])

    forged = tmp_path / "mislabelled.json"
    intake.write(forged, {**report, "collection_scope": {"source_ids": []}})
    with pytest.raises(ValueError, match="disagrees with its packet scope"):
        intake.restore(packet, forged, tmp_path / "mislabelled", require_late_archive_scope=True)
    monkeypatch.setattr(intake, "late_archive_sources", lambda: (*feeds, "new-reviewed-feed"))
    for candidate in (weekly, original):
        output = tmp_path / "superseded"
        assert intake.restore(candidate / "complete-results.zip", candidate / "report.json", output,
                              require_late_archive_scope=True) == {"status": "superseded"}
        assert not output.exists()
