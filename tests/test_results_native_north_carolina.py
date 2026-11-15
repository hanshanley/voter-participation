import copy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re

import pytest

from scripts import results_granular as granular
from scripts import results_intake as intake
from scripts import results_native
from scripts import results_native_north_carolina as nc
from scripts.participation_intake.contract import IntakeError, encoded, pin


FIXTURES = Path(__file__).parent / "fixtures/north-carolina-native"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def fixture_body():
    return gzip.decompress((FIXTURES / "accepted-reporting.json.gz").read_bytes())


def fixture_templates():
    return json.loads(gzip.decompress(
        (FIXTURES / "accepted-templates.json.gz").read_bytes()))


def baseline():
    templates = fixture_templates()
    counties = [row["id"] for row in templates if row["geography"]["level"] == "county"]
    state = [row["id"] for row in templates if row["geography"]["level"] == "state"]
    shard = {"records": templates, "views": {
        "official": {"counties": counties, "precincts": [], "nongeographic": state}}}
    body = intake.compressed(encoded(shard))
    empty = intake.compressed(encoded({"records": [], "views": {}}))
    index = {"states": {
        "MN": {"file": "states/MN.json.gz", **pin(empty)},
        "NC": {"file": "states/NC.json.gz", **pin(body)},
    }}
    return {
        "index.json": encoded(index),
        "states/MN.json.gz": empty,
        "states/NC.json.gz": body,
    }


def rows(body):
    return json.loads(body)


def revised(body, clock, *, county_delta=0, status_regression=False,
            partial_rollback=None, rate_unknown=False, state_clock=None,
            state_status=None):
    document = rows(body)
    for row in document:
        row["imp"] = clock
        row["sub"] = clock
    if county_delta:
        county = next(row for row in document if row["cid"] == "1")
        state = next(row for row in document if row["cid"] == "0")
        county["bct"] = str(int(county["bct"]) + county_delta)
        state["bct"] = str(int(state["bct"]) + county_delta)
        county["bpt"] = f"{100 * int(county['bct']) / int(county['rtl']):.2f}%"
        state["bpt"] = f"{100 * int(state['bct']) / int(state['rtl']):.2f}%"
    if status_regression:
        county = next(row for row in document if row["cid"] == "1")
        county["tle"] = county["tle"].replace(" OFFICIAL ", " UNOFFICIAL ")
    if partial_rollback is not None:
        county = next(row for row in document if row["cid"] == "1")
        county["imp"] = partial_rollback
        county["sub"] = partial_rollback
    if rate_unknown:
        next(row for row in document if row["cid"] == "1")["bpt"] = "0.00%"
    state = next(row for row in document if row["cid"] == "0")
    if state_clock is not None:
        state["imp"] = state_clock
        state["sub"] = state_clock
    if state_status is not None:
        state["tle"] = re.sub(
            r" (?:UNOFFICIAL|OFFICIAL) ", " " + state_status + " ", state["tle"])
    return encoded(document)


def captured(tmp_path, monkeypatch, body, prior=None, stopped=EMPTY_STOPS):
    calls = []

    def acquire(self, url, *, refresh=False):
        self.guard(url)
        calls.append(url)
        assert url == nc.URL and refresh is False
        return body, {"origin": "retained_fixture", **pin(body)}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    collector = intake.Collector(tmp_path, prior or {}, stopped, NOW)
    feeds = results_native.collect_sources(collector, baseline())
    entries = [entry for entry in feeds.values() if entry.get("adapter") == nc.ADAPTER]
    assert len(entries) == 1
    return entries[0], feeds, calls


def test_shared_export_id_does_not_route_nebraska_as_north_carolina():
    template = copy.deepcopy(fixture_templates()[0])
    template["geography"].update(state_code="NE", id="NE|14|", name="Adams")
    template["source"]["url"] = (
        "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
        "dc81c095cec959910c6dfb82da8c9184d7a993f9/"
        "public/participation-current/20261104T220424Z/local.json"
    )
    template["view"]["source_url"] = (
        "https://electionresults.nebraska.gov/VoterTurnoutDetails.aspx?map=PREC"
    )
    assert nc.route(template) is None


def test_default_source_plan_collector_projection_and_repeat_are_exact(tmp_path, monkeypatch):
    accepted = baseline()
    plan = results_native.source_plan(accepted)
    sources = [source for source in plan["NC"].values()
               if source["adapter"] == nc.ADAPTER]
    assert len(sources) == 1
    assert len(sources[0]["templates"]) == 100
    assert sources[0]["url"] == nc.URL

    first, feeds, calls = captured(tmp_path / "first", monkeypatch, fixture_body())
    assert calls == [nc.URL]
    assert first["status"] == "reported"
    assert len(first["data"]["updates"]) == 100
    updated, changes = granular.project(accepted, feeds)
    assert len(changes) == 100
    shard = json.loads(gzip.decompress(updated["states/NC.json.gz"]))
    assert sum(row["count"]["value"] for row in shard["records"]) == 4_242_662
    assert sum(row["denominator"]["value"] for row in shard["records"]) == 7_885_046
    assert all(row["source_clock"]["timezone"] is None for row in shard["records"])

    second, repeated_feeds, repeated_calls = captured(
        tmp_path / "repeat", monkeypatch, fixture_body(), prior=feeds)
    assert repeated_calls == [nc.URL]
    assert second["status"] == "reported"
    assert granular.project(updated, repeated_feeds) == (updated, [])


def test_ordinary_first_failure_without_data_can_recover_on_next_default_collection(
        tmp_path, monkeypatch):
    attempts = []

    def acquire(self, url, *, refresh=False):
        self.guard(url)
        attempts.append(url)
        if len(attempts) == 1:
            raise IntakeError("source_unavailable", "Ordinary transient fixture failure")
        body = fixture_body()
        return body, {"origin": "retained_fixture", **pin(body)}

    monkeypatch.setattr(intake.Collector, "acquire", acquire)
    first_collector = intake.Collector(tmp_path / "first", {}, EMPTY_STOPS, NOW)
    first_feeds = results_native.collect_sources(first_collector, baseline())
    first = next(entry for entry in first_feeds.values()
                 if entry.get("adapter") == nc.ADAPTER)
    assert first["status"] == "source_unavailable"
    assert first["source"] is None and first["data"] is None

    second_collector = intake.Collector(
        tmp_path / "second", first_feeds, EMPTY_STOPS, NOW)
    second_feeds = results_native.collect_sources(second_collector, baseline())
    second = next(entry for entry in second_feeds.values()
                  if entry.get("adapter") == nc.ADAPTER)
    assert attempts == [nc.URL, nc.URL]
    assert second["status"] == "reported"
    assert len(second["data"]["updates"]) == 100
    assert nc.statistics(
        fixture_body(), fixture_templates(), nc.URL,
        prior={"status": "source_unavailable", "source": None, "data": None},
    )["contract"] == nc.CONTRACT


def test_same_frozen_registration_rejects_full_and_partial_prior_clock_rollback(
        tmp_path, monkeypatch):
    first_body = revised(
        fixture_body(), "November 15, 2026 1:00 pm", county_delta=1)
    first, feeds, _ = captured(tmp_path / "first", monkeypatch, first_body)
    assert first["status"] == "reported"

    older = revised(
        fixture_body(), "November 14, 2026 1:00 pm", county_delta=2)
    rollback, _, _ = captured(
        tmp_path / "full-rollback", monkeypatch, older, prior=feeds)
    assert rollback["status"] == "retained_after_failure"
    assert rollback["data"] == first["data"]
    assert rollback["source"] == first["source"]

    partial = revised(
        fixture_body(), "November 16, 2026 1:00 pm", county_delta=3,
        partial_rollback="November 14, 2026 1:00 pm")
    rejected, _, _ = captured(
        tmp_path / "partial-rollback", monkeypatch, partial, prior=feeds)
    assert rejected["status"] == "retained_after_failure"
    assert rejected["data"] == first["data"]


def test_statewide_query_clock_status_and_forward_repeat_are_guarded(
        tmp_path, monkeypatch):
    first_body = revised(
        fixture_body(), "November 15, 2026 1:00 pm", county_delta=1)
    first, first_feeds, _ = captured(
        tmp_path / "first", monkeypatch, first_body)
    assert first["status"] == "reported"

    state_rollback = revised(
        fixture_body(), "November 16, 2026 1:00 pm", county_delta=2,
        state_clock="November 14, 2026 1:00 pm")
    rejected, _, _ = captured(
        tmp_path / "state-rollback", monkeypatch, state_rollback,
        prior=first_feeds)
    assert rejected["status"] == "retained_after_failure"
    assert rejected["data"] == first["data"]

    official_body = revised(
        fixture_body(), "November 15, 2026 1:00 pm", county_delta=1,
        state_status="OFFICIAL")
    official, official_feeds, _ = captured(
        tmp_path / "official", monkeypatch, official_body)
    assert official["status"] == "reported"
    state_status_regression = revised(
        fixture_body(), "November 16, 2026 1:00 pm", county_delta=2,
        state_status="UNOFFICIAL")
    rejected, _, _ = captured(
        tmp_path / "state-status", monkeypatch, state_status_regression,
        prior=official_feeds)
    assert rejected["status"] == "retained_after_failure"
    assert rejected["data"] == official["data"]

    forward_body = revised(
        fixture_body(), "November 16, 2026 1:00 pm", county_delta=2)
    forward, forward_feeds, _ = captured(
        tmp_path / "forward", monkeypatch, forward_body, prior=first_feeds)
    assert forward["status"] == "reported"
    repeated, _, _ = captured(
        tmp_path / "forward-repeat", monkeypatch, forward_body,
        prior=forward_feeds)
    assert repeated["status"] == "reported"
    assert repeated["data"] == forward["data"]
    assert repeated["source"] == forward["source"]


def test_status_malformed_duplicate_identity_and_prior_drift_retain_complete_prior(
        tmp_path, monkeypatch):
    first_body = revised(
        fixture_body(), "November 15, 2026 1:00 pm", county_delta=1)
    first, feeds, _ = captured(tmp_path / "first", monkeypatch, first_body)

    status = revised(
        fixture_body(), "November 16, 2026 1:00 pm",
        county_delta=2, status_regression=True)
    rejected, _, _ = captured(tmp_path / "status", monkeypatch, status, prior=feeds)
    assert rejected["status"] == "retained_after_failure"
    assert rejected["data"] == first["data"]

    duplicate = fixture_body().replace(b'"cid":"0"', b'"cid":"0","cid":"0"', 1)
    assert duplicate != fixture_body()
    rejected, _, _ = captured(tmp_path / "duplicate", monkeypatch, duplicate, prior=feeds)
    assert rejected["status"] == "retained_after_failure"

    identity = rows(revised(fixture_body(), "November 16, 2026 1:00 pm"))
    county = next(row for row in identity if row["cid"] == "1")
    county["cnm"] = "RENAMED"
    county["tle"] = county["tle"].replace("ALAMANCE", "RENAMED")
    rejected, _, _ = captured(
        tmp_path / "identity", monkeypatch, encoded(identity), prior=feeds)
    assert rejected["status"] == "retained_after_failure"

    corrupt_prior = copy.deepcopy(first)
    corrupt_prior["data"]["updates"][0]["value"] += 1
    with pytest.raises(ValueError, match="prior query/update/source coherence"):
        nc.statistics(fixture_body(), fixture_templates(), nc.URL, prior=corrupt_prior)


def test_source_stop_never_opens_transport_and_unknown_clock_rate_stay_held(
        tmp_path, monkeypatch):
    first_body = revised(
        fixture_body(), "November 15, 2026 1:00 pm", county_delta=1)
    first, feeds, _ = captured(tmp_path / "first", monkeypatch, first_body)

    opened = []

    def forbidden(self, url, *, refresh=False):
        self.guard(url)
        opened.append(url)
        pytest.fail("Stopped North Carolina URL reached transport")

    monkeypatch.setattr(intake.Collector, "acquire", forbidden)
    collector = intake.Collector(
        tmp_path / "stopped", feeds,
        {"urls": [nc.URL], "prefixes": [], "hosts": []}, NOW)
    stopped = results_native.collect_sources(collector, baseline())
    entry = next(value for value in stopped.values()
                 if value.get("adapter") == nc.ADAPTER)
    assert opened == []
    assert entry["status"] == "retained_after_failure"
    assert entry["error"] == "source_stopped"
    assert entry["data"] == first["data"]

    unknown_rate = revised(
        fixture_body(), "November 16, 2026 1:00 pm",
        county_delta=2, rate_unknown=True)
    parsed = nc.statistics(
        unknown_rate, fixture_templates(), nc.URL, prior=first)
    update = next(row for row in parsed["updates"]
                  if row["native"]["query"]["county_id"] == "1")
    assert update["rate_compatible"] is False
    assert update["clock"] == "November 16, 2026 1:00 pm"
    assert update["native"]["source_clock_timezone"] is None

    missing_clock = rows(unknown_rate)
    next(row for row in missing_clock if row["cid"] == "1")["imp"] = ""
    rejected, _, _ = captured(
        tmp_path / "missing-clock", monkeypatch, encoded(missing_clock), prior=feeds)
    assert rejected["status"] == "retained_after_failure"
