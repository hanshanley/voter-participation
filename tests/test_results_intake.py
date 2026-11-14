import copy
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import subprocess
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
    assert intake.replay(packet, tmp_path / "reproduced")["complete_outputs"] == 7
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


def test_invalid_stop_seed_is_fail_closed_before_transport(tmp_path):
    with pytest.raises(ValueError, match="ledger"):
        intake.Collector(tmp_path, {}, {"urls": None, "prefixes": [], "hosts": []}, NOW)


def test_real_git_publication_keeps_main_and_persists_last_good_results(tmp_path, monkeypatch):
    registry = fixture(tmp_path)
    monkeypatch.setattr(intake.Collector, "acquire", unavailable)
    work = tmp_path / "run"
    report = intake.collect(registry, work, now=NOW)
    repo = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    def verify(self, commit, files):
        for name, expected in files.items():
            assert pin(subprocess.check_output(["git", "-C", str(repo), "show", commit + ":" + name])) == expected
    monkeypatch.setattr(GitPublisher, "verify_files", verify)
    intake.write(work / "publication-parent.json", {"parent": None})
    result = intake.publish(repo, "results-data", "fixture/results", work)
    assert result["status"] == "published"
    assert result["version"] == report["version"]
    assert subprocess.check_output(["git", "-C", str(repo), "symbolic-ref", "HEAD"]).strip() == b"refs/heads/main"
    intake.write(work / "publication-parent.json", {"parent": result["data_commit"]})
    assert intake.publish(repo, "results-data", "fixture/results", work)["status"] == "unchanged"
    failed = tmp_path / "failed"
    intake.write(failed / "publication-parent.json", {"parent": result["data_commit"]})
    intake.write(failed / "source-stops.json",
                 {"urls": ["https://example.test/stopped"], "prefixes": [], "hosts": []})
    with pytest.raises(ValueError, match="durable stops preserved"):
        intake.publish(repo, "results-data", "fixture/results", failed)
    head = GitPublisher(repo, ref="results-data").remote_head()
    assert json.loads(subprocess.check_output(["git", "-C", str(repo), "show", head + ":latest.json"]))["version"] == report["version"]
    assert "https://example.test/stopped" in json.loads(
        subprocess.check_output(["git", "-C", str(repo), "show", head + ":state.json"]))["source_stops"]["urls"]
