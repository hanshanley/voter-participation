import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts import results_congress, results_intake, results_official_congress
from scripts import results_json_congress as source
from scripts.participation_intake.contract import IntakeError, encoded, pin
from scripts.participation_intake.engine import Store


NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def facts():
    return json.loads((Path(__file__).parent / "fixtures/utah-federal-candidates.json").read_bytes())


def revision(value, delta):
    value = copy.deepcopy(value)
    race = value["ballotItems"][0]
    race["summaryResults"]["ballotOptions"][-1]["voteCount"] += delta
    race["voteTotal"] += delta
    return value


def capture(tmp_path, value, prior=None):
    collector = results_intake.Collector(
        tmp_path, {source.IDENTITY: prior} if prior else {}, EMPTY_STOPS, NOW)

    def acquire(url):
        collector.guard(url)
        if value is None:
            raise OSError("Unavailable original")
        body = encoded(value)
        return body, {"origin": "retained_original", **pin(body)}

    collector.acquire = acquire
    result = results_official_congress.collect_sources(
        collector, results_official_congress.JSON_CONFIG, selected=(source.IDENTITY,))
    return result[source.IDENTITY]


@pytest.mark.parametrize("delta", [0, 7, -13, -76])
def test_literal_candidates_minor_parties_named_write_in_and_true_zero(delta):
    value = revision(facts(), delta)
    before = copy.deepcopy(value)
    result = source.parse(encoded(value))
    assert result == source.normalized(value) and value == before
    assert len(result["races"]) == 4 and sum(len(r["candidates"]) for r in result["races"]) == 20
    totals = {p: sum(c["votes"] for r in result["races"] for c in r["candidates"]
                     if c["party_group"] == p) for p in "DROU"}
    assert totals == {"D": 476701, "R": 479680, "O": 68751 + delta, "U": 0}
    named = result["races"][0]["candidates"][-1]
    assert named["name_literal"] == 'BABAK "BOBBY" DARVISH '
    assert named["name"] == 'BABAK "BOBBY" DARVISH'
    assert named["votes"] == 76 + delta and named["is_qualified_write_in"]
    assert named["role"] == "named_candidate" and named["is_write_in"]
    assert named["literal_party"] == "Unaffiliated" and named["native_party_abbreviation"] is None
    assert result["source_updated_at"] == "2026-11-11T03:03:24.6796079Z"
    assert all(r["reporting_unit_kind"] == "native_reporting_fragment_not_certified_precinct"
               for r in result["races"])
    assert all(result[key] is False for key in (
        "exhaustive_write_in_universe_qualified", "participation_observation_qualified",
        "provider_other_equivalence_qualified", "conditional_model_eligible"))


@pytest.mark.parametrize("change", [
    "primary", "production", "jurisdiction", "date", "official-type", "root-clock",
    "missing-seat", "duplicate-seat", "stage", "parent", "vote-for", "ranked-choice",
    "fragment-count", "race-clock", "missing-candidate", "duplicate-candidate", "negative",
    "boolean", "unsafe", "named-write-in", "qualified-write-in", "method-breakdown",
])
def test_incompatible_facts_refuse_without_repair_or_universe_promotion(change):
    value = facts()
    election, race = value["election"], value["ballotItems"][0]
    candidate = race["summaryResults"]["ballotOptions"][-1]
    if change == "primary":
        election["isPrimary"] = True
    elif change == "production":
        election["isProduction"] = False
    elif change == "jurisdiction":
        election["jurisdictionId"] = "00000000-0000-0000-0000-000000000000"
    elif change == "date":
        election["electionDate"] = "2024-11-05"
    elif change == "official-type":
        election["isOfficialResults"] = 1
    elif change == "root-clock":
        election["asOf"] = "2026-11-11"
    elif change == "missing-seat":
        value["ballotItems"].pop()
    elif change == "duplicate-seat":
        value["ballotItems"][-1] = copy.deepcopy(race)
    elif change == "stage":
        race["name"][0]["text"] += " Special Election"
    elif change == "parent":
        race["parentId"] = election["id"]
    elif change == "vote-for":
        race["voteFor"] = [{"text": "2"}]
    elif change == "ranked-choice":
        race["rankedChoiceSummaryResults"] = {}
    elif change == "fragment-count":
        race["reportingStatus"]["reportingUnits"] += 1
    elif change == "race-clock":
        race["reportingStatus"]["asOf"] = "2026-11-11T03:03:24"
    elif change == "missing-candidate":
        race["summaryResults"]["ballotOptions"].pop()
    elif change == "duplicate-candidate":
        candidate["id"] = race["summaryResults"]["ballotOptions"][0]["id"]
    elif change in ("negative", "boolean", "unsafe"):
        candidate["voteCount"] = {"negative": -1, "boolean": True, "unsafe": 2**53}[change]
    elif change == "named-write-in":
        candidate["isQualifiedWriteIn"] = False
    elif change == "qualified-write-in":
        candidate["isWriteIn"] = False
    else:
        candidate["groupResults"] = []
    with pytest.raises((ValueError, KeyError, TypeError)):
        source.parse(encoded(value))


def test_duplicate_json_fields_and_unreviewed_federal_seat_are_not_discarded():
    body = encoded(facts())
    with pytest.raises(ValueError, match="Duplicate native JSON property"):
        source.parse(body.replace(b'"voteTotal":249058', b'"voteTotal":249058,"voteTotal":249058', 1))
    value = facts()
    extra = copy.deepcopy(value["ballotItems"][0])
    extra["name"][0]["text"] = "U.S. House District 5"
    value["ballotItems"].append(extra)
    with pytest.raises(ValueError, match="seat or election stage"):
        source.parse(encoded(value))


def test_unknown_party_is_retained_and_generic_write_ins_are_not_deleted():
    value = facts()
    candidate = copy.deepcopy(value["ballotItems"][0]["summaryResults"]["ballotOptions"][-1])
    candidate.update(id="00000000-0000-0000-0000-000000000001",
                     nativeId="native-generic-write-in", voteCount=71,
                     name=[{"languageId": "en", "text": "Write-in"}],
                     isQualifiedWriteIn=False, party=None)
    race = value["ballotItems"][0]
    race["summaryResults"]["ballotOptions"].append(candidate)
    race["voteTotal"] += 71
    result = source.parse(encoded(value))
    assert len(result["races"][0]["candidates"]) == 6
    assert result["races"][0]["candidates"][-1]["party_group"] == "U"
    assert result["races"][0]["candidates"][-1]["votes"] == 71
    assert result["races"][0]["candidates"][-1]["role"] == "generic_write_in"
    assert result["races"][0]["candidates"][-2]["votes"] == 76
    assert result["provider_other_equivalence_qualified"] is False


def test_revisions_noop_failure_and_recovery_preserve_own_clocks(tmp_path):
    first = capture(tmp_path / "first", facts())
    assert first["status"] == "reported"
    same = capture(tmp_path / "same", facts(), first)
    assert same == first
    up = capture(tmp_path / "up", revision(facts(), 7), same)
    down = capture(tmp_path / "down", revision(facts(), -13), up)
    zero = capture(tmp_path / "zero", revision(facts(), -76), down)
    assert all(row["status"] == "reported" for row in (up, down, zero))
    held = capture(tmp_path / "outage", None, zero)
    assert held["status"] == "retained_after_failure"
    assert held["data"] == zero["data"] and held["source"] == zero["source"]
    assert held["first_observed_at"] == zero["first_observed_at"]
    assert capture(tmp_path / "recovered", facts(), held)["data"] == first["data"]


@pytest.mark.parametrize("change", [
    "root-rollback", "last-updated-rollback", "race-rollback", "future",
    "lost", "renamed", "party", "native-id", "contest", "official-rollback", "corrupt-prior",
])
def test_prior_identity_clock_and_finality_failures_retain_last_good(tmp_path, change):
    previous_facts = facts()
    if change == "official-rollback":
        previous_facts["election"]["isOfficialResults"] = True
    first = capture(tmp_path / "first", previous_facts)
    value = facts()
    race = value["ballotItems"][0]
    if change == "root-rollback":
        value["election"]["asOf"] = "2026-11-10T03:03:24Z"
    elif change == "last-updated-rollback":
        value["election"]["lastUpdated"] = "2026-11-10T03:03:24Z"
    elif change == "race-rollback":
        race["reportingStatus"]["asOf"] = "2026-11-10T03:03:24Z"
    elif change == "future":
        value["election"]["asOf"] = "2026-11-20T03:03:24Z"
    elif change == "lost":
        lost = race["summaryResults"]["ballotOptions"].pop()
        race["voteTotal"] -= lost["voteCount"]
    elif change == "renamed":
        race["summaryResults"]["ballotOptions"][-1]["name"][0]["text"] = "Another Person"
    elif change == "party":
        race["summaryResults"]["ballotOptions"][-1]["party"]["name"][0]["text"] = "Republican"
    elif change == "native-id":
        race["summaryResults"]["ballotOptions"][-1]["nativeId"] = "different-native-id"
    elif change == "contest":
        race["id"] = "00000000-0000-0000-0000-000000000001"
    elif change == "corrupt-prior":
        first["data"]["races"][0]["contest_total"] += 1
    held = capture(tmp_path / "held", value, first)
    assert held["status"] == "retained_after_failure"
    assert held["data"] == first["data"] and held["source"] == first["source"]
    assert held["first_observed_at"] == first["first_observed_at"]


@pytest.mark.parametrize("target", ["asOf", "lastUpdated", "race"])
def test_full_native_clock_precision_refuses_submicrosecond_rollback(tmp_path, target):
    value = facts()
    container, key = (value["ballotItems"][0]["reportingStatus"], "asOf") if target == "race" else (
        value["election"], target)
    container[key] = "2026-11-11T03:03:24.6796079Z"
    first = capture(tmp_path / "first", value)
    assert first["status"] == "reported"
    container[key] = "2026-11-11T03:03:24.6796078Z"
    held = capture(tmp_path / "rollback", value, first)
    assert held["status"] == "retained_after_failure"
    assert held["data"] == first["data"] and held["source"] == first["source"]
    container[key] = "2026-11-11T03:03:24.6796080Z"
    assert capture(tmp_path / "successor", value, held)["status"] == "reported"


def test_full_native_clock_precision_refuses_future_fraction(tmp_path, monkeypatch):
    monkeypatch.setattr(results_intake.Collector, "observation_time", lambda self: NOW)
    value = facts()
    value["election"]["asOf"] = "2026-11-19T00:00:00.0000001Z"
    result = capture(tmp_path, value)
    assert result["data"] is None
    assert result["status"] == "schema_or_source_semantics_changed"
    assert "future" in result["error_detail"]


def county_document():
    from test_results_native_utah import source_document

    result = source_document()
    result["ballotItems"] = facts()["ballotItems"]
    return result


@pytest.mark.parametrize("pdf_available", [True, False])
def test_one_actual_root_acquisition_county_independence_and_stopped_warmed_body(
        tmp_path, monkeypatch, pdf_available):
    from test_results_native_utah import declared_bodies, full_baseline, utah_entry
    from scripts import results_native
    from scripts import results_native_utah

    document = county_document()
    body, calls = encoded(document), []
    pdfs = declared_bodies(document)

    def acquire(store, item, **kwargs):
        calls.append(item["url"])
        if item["url"] != source.URL:
            if not pdf_available:
                raise IntakeError("source_unavailable", "County PDF unavailable")
            original = pdfs[item["url"]]
        else:
            original = body
        return original, {"origin": "supplied_original", **pin(original)}

    monkeypatch.setattr(Store, "acquire", acquire)
    collector = results_intake.Collector(tmp_path, {}, EMPTY_STOPS, NOW)
    official = results_official_congress.collect_sources(
        collector, results_official_congress.JSON_CONFIG, selected=(source.IDENTITY,))
    county = results_native.collect_sources(collector, full_baseline(selected_only=True))
    assert official[source.IDENTITY]["status"] == "reported"
    county_result = utah_entry(county)
    if pdf_available:
        assert county_result["status"] == "reported"
        assert len(county_result["data"]["updates"]) == 4
        assert len(calls) == 5
    else:
        assert county_result["data"] is None
    assert calls.count(source.URL) == 1 and len(calls) > 1
    assert source.URL == results_native_utah.API_URL
    collector.stopped["urls"].append(source.URL)
    collector.prior[source.IDENTITY] = official[source.IDENTITY]
    stopped = source.collect(collector)
    assert stopped["status"] == "retained_after_failure"
    assert stopped["data"] == official[source.IDENTITY]["data"]
    assert calls.count(source.URL) == 1


def test_actual_default_collection_and_extracted_complete_packet(tmp_path, monkeypatch):
    from test_results_intake import fixture

    registry = fixture(tmp_path)
    config = results_intake.read(registry)
    config["congressional"] = {"test_scope": "stub national inventory only"}
    results_intake.write(registry, config)
    results_intake.write(registry.with_name("official-congress.json"),
                         results_official_congress.JSON_CONFIG)
    monkeypatch.setattr(results_congress, "collect", lambda *args: {"races": {}})
    body, calls = encoded(facts()), []

    def acquire(store, item, **kwargs):
        calls.append(item["url"])
        if item["url"] != source.URL:
            raise IntakeError("source_unavailable", "Fixture transport unavailable")
        return body, {"origin": "supplied_original", **pin(body)}

    monkeypatch.setattr(Store, "acquire", acquire)
    work = tmp_path / "captured"
    first = results_intake.collect(registry, work, now=NOW)
    state = results_intake.read(work / "state.json")
    entry = state["feeds"][source.IDENTITY]
    assert entry["status"] == "reported" and calls.count(source.URL) == 1
    exported = results_official_congress.rows(state["congress"])
    assert len(exported) == 20 and all(r["conditional_model_eligible"] is False for r in exported)
    assert results_intake.numeric_observations(
        {"index.json": encoded({"states": {}})}, {source.IDENTITY: entry}) == []
    second = results_intake.collect(registry, tmp_path / "unchanged", state, now=NOW)
    assert first["version"] == second["version"] and first["files"] == second["files"]
    with zipfile.ZipFile(work / "complete-results.zip") as packet:
        for name in ("scripts/results_json_congress.py", "tests/test_results_json_congress.py",
                     "tests/fixtures/utah-federal-candidates.json"):
            assert packet.read("code/" + name) == (results_intake.ROOT / name).read_bytes()
        csv_body = packet.read("queries/congress-official-candidates.csv")
        assert b"DARVISH" in csv_body
        assert b"Named write-ins do not resolve unmatched generic provider write-ins." in csv_body
        packet.extractall(tmp_path / "extracted")
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".", "--output", "reproduced"],
        cwd=tmp_path / "extracted", capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["network_requests"] == 0
    portable = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_results_json_congress.py",
         "-k", "not actual_default_collection"],
        cwd=tmp_path / "extracted/code", capture_output=True, text=True)
    assert portable.returncode == 0, portable.stdout + portable.stderr
