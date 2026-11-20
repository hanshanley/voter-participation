import copy
import csv
from datetime import datetime, timezone
import io
import json
import subprocess
import sys
import zipfile

import pytest

from scripts import results_congress, results_intake
from scripts import results_official_congress as official
from scripts.participation_intake.contract import encoded, pin


def original(count=100, status="Unofficial", reported=10):
    races = []
    for seat in range(1, 4):
        candidates = []
        for index, (name, party, votes) in enumerate((
            ("First  Candidate ", "Democratic", count),
            ("Second Candidate", "Republican", 90),
            ("Minor Candidate", "Legal Marijuana Now", 7),
        )):
            candidates.append(
                '<div class="col display-results-box-d"><h1>' + name
                + '</h1><h2 class="' + party + '">' + party + "</h2></div>"
                + '<div id="bar' + str(seat * 100 + index) + '"></div>'
                + '<div class="col display-results-box-f"><h1>' + str(votes)
                + "</h1></div>")
        races.append(
            '<div class="display-results-box-a"><h1>'
            + f"For Representative in Congress - 2  Year Term - District {seat:02d}"
            + '</h1><input raceid="' + str(seat) + '">'
            + f'<div class="precinct-fully">Precincts Fully: {reported} / 10</div>'
            + '<div class="precinct-partial">Partially: 0 / 10</div>'
            + "".join(candidates)
            + '<div class="col display-results-box-totalvotes"><h2>total votes</h2></div>'
            + '<div class="col display-results-box-total"><h2>'
            + str(count + 97) + "</h2></div>")
    return (
        "<title>Nebraska Secretary of State</title><h1>" + status + " Results</h1>"
        + "<h2>General Election November 3, 2026</h2>"
        + '<div class="last-updated"></div>' + "".join(races) + "</form>").encode()


def capture(tmp_path, body, prior=None, stopped=False):
    collector = results_intake.Collector(
        tmp_path, {official.IDENTITY: prior} if prior else {},
        {"urls": [official.URL] if stopped else [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 17, tzinfo=timezone.utc))
    calls = []

    def acquire(url):
        collector.guard(url)
        calls.append(url)
        if body is None:
            raise OSError("Unavailable original")
        return body, {"origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    return official.collect(collector, official.CONFIG), calls, collector


def test_complete_native_names_parties_controls_and_partial_status():
    for reported in (0, 7, 10):
        data = official.nebraska_house(original(reported=reported))
        assert len(data["races"]) == 3
        assert data["participation_observation_qualified"] is False
        assert data["conditional_model_eligible"] is False
        for race in data["races"]:
            assert race["contest_total"] == 197
            assert race["complete_reporting"] is (reported == 10)
            assert race["source_update_label"] is None
            assert race["candidates"][0]["name_literal"] == "First  Candidate "
            assert race["candidates"][0]["name"] == "First Candidate"
            assert race["candidates"][2]["literal_party"] == "Legal Marijuana Now"
            assert race["candidates"][2]["votes"] == 7
    assert official.nebraska_house(original(status="Official"))["races"][0][
        "native_status_literal"] == "Official Results"


@pytest.mark.parametrize("count", [107, 93, 0])
def test_upward_downward_zero_corrections_never_merge_national_counts(tmp_path, count):
    first, _, _ = capture(tmp_path / "first", original())
    revised, _, _ = capture(tmp_path / "revision", original(count), first)
    assert revised["status"] == "reported"
    assert [race["candidates"][0]["votes"] for race in revised["data"]["races"]] == [count] * 3
    national = {"chambers": {}, "national_counts": {"NE-01": 999}}
    before = copy.deepcopy(national)
    attached = official.attach(national, {official.IDENTITY: revised})
    assert national == before and attached["national_counts"] == national["national_counts"]
    assert all(row["conditional_model_eligible"] is False for row in official.rows(attached))
    assert all(row["provider_other_equivalence_qualified"] is False for row in official.rows(attached))


def test_unchanged_outage_unknown_and_stopped_original_preserve_last_good(tmp_path):
    first, _, _ = capture(tmp_path / "first", original())
    unchanged, calls, _ = capture(tmp_path / "same", original(), first)
    assert unchanged == first and calls == [official.URL]
    for name, body in (("outage", None), ("unknown", original().replace(b">100</h1>", b">--</h1>"))):
        held, _, _ = capture(tmp_path / name, body, first)
        assert held["status"] == "retained_after_failure"
        assert held["data"] == first["data"] and held["source"] == first["source"]
        assert held["first_observed_at"] == first["first_observed_at"]
    held, calls, collector = capture(tmp_path / "stopped", original(), first, stopped=True)
    assert calls == [] and held["status"] == "retained_after_failure"
    assert held["data"] == first["data"] and collector.stopped["urls"] == [official.URL]


@pytest.mark.parametrize("before,after", [
    (b"Nebraska Secretary of State", b"Another Publisher"),
    (b"General Election November 3, 2026", b"Primary Election May 12, 2026"),
    (b"District 03", b"District 04"),
    (b"District 03", b"District 02"),
    (b">197</h2>", b">198</h2>"),
    (b">100</h1>", b">1,00</h1>"),
    (b">100</h1>", b">-1</h1>"),
    (b"Fully: 10 / 10", b"Fully: 11 / 10"),
    (b"Partially: 0 / 10", b"Partially: 0 / 11"),
    (b'<div id="bar102">', b'<div id="bar101">'),
])
def test_wrong_identity_inventory_counts_and_controls_fail_closed(before, after):
    with pytest.raises(ValueError):
        official.nebraska_house(original().replace(before, after))


def test_candidate_queries_export_separately_and_never_become_participation(tmp_path):
    entry, _, _ = capture(tmp_path, original())
    national = official.attach({"races": {}}, {official.IDENTITY: entry})
    baseline = {"index.json": encoded({"states": {}})}
    assert results_intake.numeric_observations(baseline, {official.IDENTITY: entry}) == []
    exported = results_congress.exports(national)
    rows = list(csv.DictReader(io.StringIO(exported["congress-official-candidates.csv"].decode())))
    assert len(rows) == 9
    assert sum(row["literal_party"] == "Legal Marijuana Now" for row in rows) == 3
    assert all(row["conditional_model_eligible"] == "False" for row in rows)
    assert json.loads(rows[0]["source"]) == entry["source"]
    assert official.attach({}, {}) == {}
    with pytest.raises(ValueError):
        official.collect(None, dict(official.CONFIG, sources={official.IDENTITY: "https://wrong.test"}))


def test_provider_other_differences_are_explicit_not_reconciled_by_major_totals(tmp_path):
    entry, _, _ = capture(tmp_path, original())
    race = {
        "chamber": "house", "state_code": "NE", "seat": "1", "stage": "general",
        "election_kind": "regular", "election_date": "2026-11-03", "round": "not_ranked",
        "candidates": [
            {"role": "provider_aggregate_other", "votes": 6},
            {"role": "named_candidate", "party_group": "D", "votes": 0},
            {"role": "named_candidate", "party_group": "R", "votes": None},
        ],
    }
    national = official.attach({"races": {"native-race": {
        "status": "reported", "data": race}}}, {official.IDENTITY: entry})
    before = copy.deepcopy(national)
    compared = official.reconciliation(national)
    assert compared[0]["named_minor_minus_provider_other"] == 1
    assert compared[0]["official_generic_write_in_votes"] is None
    assert compared[0]["named_minor_plus_generic_write_in_minus_provider_other"] is None
    assert compared[0]["provider_d_named_votes"] == 0
    assert compared[0]["r_named_votes_difference"] is None
    assert compared[0]["provider_candidate_vote_sum"] is None
    assert compared[1]["provider_aggregate_other"] is None
    assert all(row["universe_equivalence_qualified"] is False for row in compared)
    assert national == before
    race["candidates"][0]["votes"] = 7
    national["races"]["native-race"]["data"] = race
    compared = official.reconciliation(national)
    assert compared[0]["named_minor_minus_provider_other"] == 0
    assert compared[0]["universe_equivalence_qualified"] is False
    assert compared[0]["official_contest_vote_total"] == entry["data"]["races"][0]["contest_total"]

    race["candidates"][2]["votes"] = 20
    native = national["official_candidate_evidence"][official.IDENTITY]["data"]["races"][0]
    native["candidates"].append({"role": "generic_write_in", "party_group": "O", "votes": 2})
    native["contest_total"] += 2
    rows = list(csv.DictReader(io.StringIO(results_congress.csv_bytes(
        official.reconciliation(national)).decode())))
    row = rows[0]
    assert row["provider_candidate_vote_sum"] == "27"
    assert row["named_minor_minus_provider_other"] == "0"
    assert row["named_minor_plus_generic_write_in_minus_provider_other"] == "2"
    assert row["counts_combined_or_replaced"] == "False"

    national["races"]["wrong-stage"] = {"status": "reported", "data": {**race, "stage": "runoff"}}
    assert official.reconciliation(national)[0]["provider_match_count"] == 1
    national["races"]["ambiguous"] = national["races"]["native-race"]
    ambiguous = official.reconciliation(national)[0]
    assert ambiguous["provider_match_count"] == 2
    assert ambiguous["provider_aggregate_other"] is None


def test_default_collector_and_complete_extracted_packet_keep_separate_queries(tmp_path, monkeypatch):
    from test_results_intake import fixture, unavailable

    registry = fixture(tmp_path)
    config = results_intake.read(registry)
    config["congressional"] = {"test_scope": "stub national inventory only"}
    results_intake.write(registry, config)
    results_intake.write(registry.with_name("official-congress.json"), official.CONFIG)
    monkeypatch.setattr(results_congress, "collect", lambda *args: {"races": {}})
    body = original()

    def acquire(collector, url):
        if url != official.URL:
            return unavailable(collector, url)
        collector.guard(url)
        return body, {"origin": "supplied_original", **pin(body)}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)
    work = tmp_path / "captured"
    first = results_intake.collect(registry, work)
    state = results_intake.read(work / "state.json")
    assert state["feeds"][official.IDENTITY]["status"] == "reported"
    second = results_intake.collect(registry, tmp_path / "unchanged", state)
    assert first["version"] == second["version"] and first["files"] == second["files"]
    with zipfile.ZipFile(work / "complete-results.zip") as archive:
        assert archive.read("code/scripts/results_official_congress.py") == (
            results_intake.ROOT / "scripts/results_official_congress.py").read_bytes()
        assert "code/tests/test_results_official_congress.py" in archive.namelist()
        assert "queries/congress-official-candidates.csv" in archive.namelist()
        assert "queries/congress-official-reconciliation.csv" in archive.namelist()
        archive.extractall(tmp_path / "extracted")
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".", "--output", "reproduced"],
        cwd=tmp_path / "extracted", capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["network_requests"] == 0
