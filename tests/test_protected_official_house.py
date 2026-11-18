import copy
import csv
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts import protected_official_house as official
from scripts import results_congress, results_intake
from scripts.participation_intake.contract import encoded, pin


ROOT = Path(__file__).resolve().parents[1]


def original(delta=0, reported=112):
    buffer = io.StringIO(newline="")
    buffer.write("#FormatVersion 1" + "\t" * 20 + "\n")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(official.HEADERS)
    for contest, title, sequence, total, counted, candidates in (
        (30, "U.S. Representative, Dist I", 1, 223, reported, (
            (4, "(D) CASE, Ed", 2, 123331 + delta, 3006),
            (3, "(R) LAM, Adriel C.", 4, 37235, 3073),
            (1, "(G) CONLEY, Jordan S.", 3, 6623, 388),
            (2, "(N) BERNING, Nathan M.", 1, 2183, 165))),
        (5, "U.S. Representative, Dist II", 2, 273, 137, (
            (1, "(D) TOKUDA, Jill N.", 2, 125562, 4369),
            (2, "(R) AWA, Brenton", 1, 59531, 5910))),
    ):
        for candidate, name, order, mail, in_person in candidates:
            writer.writerow((contest, title, sequence, "OF", "", 9351, 189, 383, 13,
                             0, 0, 853399, total, counted, candidate, name, order, "",
                             mail, in_person, mail + in_person))
    return buffer.getvalue().encode()


def seed():
    from scripts.automatic_estimates import load_seed
    from scripts.congressional_analytical_bridge import load_review
    if not (ROOT / "data/results-intake/model-seed/manifest.json").is_file():
        pytest.skip("Model priors are in the separate complete analytical archive.")
    value = load_seed(ROOT / "data/results-intake/model-seed")
    value["congressional_analytical_review"] = load_review(ROOT)
    value["protected_official_house_review"] = official.prepare_review(value, original())
    return value


def entry(body=None):
    body = body if body is not None else original()
    return {"status": "reported", "data": official.parse(body),
            "source": {"url": official.URL, **pin(body)},
            "first_observed_at": "2026-11-18T00:00:00Z"}


def snapshot(value, native=None):
    return {
        "contract": "participation.automatic_results_snapshot.v1", "election_date": "2026-11-03",
        "house_candidates": [dict(row, status="accepted_snapshot_not_refreshed", source=None,
                                  source_update_label=None) for row in value["accepted_candidates"]],
        "house_states": [], "source_status": [], "participation_observations": [],
        "congress": {"races": {}, "official_candidate_evidence": {official.IDENTITY: native or entry()}},
    }


def capture(tmp_path, body, previous=None, stopped=False):
    collector = results_intake.Collector(
        tmp_path, {official.IDENTITY: previous} if previous else {},
        {"urls": [official.URL] if stopped else [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 18, tzinfo=timezone.utc))
    calls = []

    def acquire(url):
        collector.guard(url)
        calls.append(url)
        if body is None:
            raise OSError("Official file unavailable")
        return body, {"url": url, "origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    return official.collect(collector), calls


def test_full_native_inventory_minor_mass_and_missing_clocks_remain_explicit():
    data = official.parse(original())
    assert official.from_facts(data["native_facts"]) == data
    assert len(data["races"]) == 2
    assert sum(len(row["candidates"]) for row in data["races"]) == 6
    assert sum(candidate["votes"] for race in data["races"] for candidate in race["candidates"]
               if candidate["party_group"] == "O") == 9359
    assert data["source_clock_supplied"] is False
    assert data["source_updated_at"] is None and data["conditional_model_eligible"] is False
    assert all(race["source_update_label"] is None and race["source_update_timezone"] is None
               and race["native_status_literal"] is None for race in data["races"])
    assert all(candidate["party_literal"] == "" for race in data["races"] for candidate in race["candidates"])
    assert data["races"][0]["native_contest_controls"]["Mail Blank Votes"] == "9351"


@pytest.mark.parametrize("old,new", [
    (b"#FormatVersion 1", b"#FormatVersion 2"),
    (b"Total Votes\n", b"Total Vote\n"),
    (b"Dist II", b"Dist III"),
    (b"(G) CONLEY", b"(?) CONLEY"),
    (b"(G) CONLEY, Jordan S.", b"Write-in"),
    (b"\t123331\t3006\t126337", b"\t123331\t3006\t126338"),
    (b"\t123331\t3006\t126337", b"\t-1\t3006\t3005"),
    (b"\t223\t112\t", b"\t111\t112\t"),
])
def test_changed_format_scope_unknown_party_and_inconsistent_counts_refuse(old, new):
    with pytest.raises(ValueError):
        official.parse(original().replace(old, new))


def test_outage_stops_unknown_and_progress_rollback_keep_own_last_good(tmp_path):
    first, _ = capture(tmp_path / "first", original())
    same, calls = capture(tmp_path / "same", original(), first)
    assert same == first and calls == [official.URL]
    for label, body in (("outage", None), ("regression", original(reported=111)),
                        ("unknown", original().replace(b"126337", b"--"))):
        held, _ = capture(tmp_path / label, body, first)
        assert held["status"] == "retained_after_failure"
        assert held["data"] == first["data"] and held["source"] == first["source"]
        assert held["first_observed_at"] == first["first_observed_at"]
    held, calls = capture(tmp_path / "stopped", original(), first, stopped=True)
    assert held["status"] == "retained_after_failure" and calls == []


@pytest.mark.parametrize("delta", [7, -13])
def test_count_revisions_do_not_invent_a_native_clock(tmp_path, delta):
    first, _ = capture(tmp_path / "first", original())
    revised, _ = capture(tmp_path / "revision", original(delta), first)
    assert revised["status"] == "reported"
    assert revised["data"]["races"][0]["candidates"][0]["votes"] == 126337 + delta
    assert revised["data"]["races"][0]["source_update_label"] is None


def test_direct_projection_never_changes_broad_intake_or_protected_wyoming():
    value = seed()
    observed = snapshot(value, entry(original(7)))
    before = copy.deepcopy(observed)
    projected = official.project_snapshot(observed, value)
    assert observed == before
    assert projected["congress"] == observed["congress"]
    assert [row for row in projected["house_candidates"] if row["state_code"] != "HI"] == [
        row for row in observed["house_candidates"] if row["state_code"] != "HI"]
    hi = [row for row in projected["house_candidates"] if row["state_code"] == "HI"]
    assert len(hi) == 6 and all(row["source_update_label"] is None for row in hi)
    assert all(row["source"]["automatic_estimates_official_scope"] ==
               value["official_source_guards"]["HI"]["guard_sha256"] for row in hi)


def test_native_inventory_change_or_failed_official_source_cannot_use_provider():
    from scripts.congressional_analytical_bridge import evaluate
    value = seed()
    for mutation in ("candidate", "outage", "url"):
        observed = snapshot(value)
        supplied = observed["congress"]["official_candidate_evidence"][official.IDENTITY]
        if mutation == "candidate":
            supplied["data"]["races"][0]["candidates"][0]["name"] = "Different candidate"
        elif mutation == "outage":
            supplied["status"] = "retained_after_failure"
        else:
            supplied["source"]["url"] = "https://wrong.test"
        assert official.project_snapshot(observed, value) == observed
        outcome = official.evaluate(observed, value, evaluate(observed, value))
        assert outcome["states"]["HI"]["automatic_update_eligible"] is False
        assert outcome["states"]["HI"]["counts"] is None


def test_all_nine_models_recondition_and_rolling_seed_retains_direct_source():
    from scripts.automatic_estimates import build
    value = seed()
    before = copy.deepcopy(value)
    result = build(snapshot(value, entry(original(7))), value)
    assert value == before
    decision = next(row for row in result["decisions"]["states"] if row["state_code"] == "HI")
    assert decision["decision"] == "changed_recompute_behavioral"
    assert decision["provider_bridge"] is False and decision["accepted_official_scope_preserved"]
    assert decision["congressional_analytical_status"]["chronological_count_order_qualified"] is False
    for path, artifact in result["artifacts"].items():
        if path.startswith("house/") and path.endswith("/complete-result.json.gz"):
            row = next(row for row in artifact["content"]["rows"] if row["state_code"] == "HI")
            assert row["reported_comparison"]["current"] == {"D": 256275, "R": 105749, "O": 9359}
            assert row["reported_comparison"]["current_native_clock"] is None
            assert "direct official" in row["reported_comparison"]["current_snapshot"]
            assert "NPR/AP" not in row["reported_comparison"]["current_native_control_scope_qualification"]
    advanced = result["artifacts"]["rolling/next-seed.json.gz"]["content"]
    assert advanced["protected_official_house_last_good"]["HI"] == entry(original(7))["data"]
    assert next(row for row in advanced["accepted_candidates"] if row["state_code"] == "HI"
                and row["name"] == "(D) CASE, Ed")["votes"] == "126344"
    repeat = build(snapshot(advanced, entry(original(7))), advanced)
    assert next(row for row in repeat["decisions"]["states"] if row["state_code"] == "HI")[
        "decision"] == "retained_fresh_unchanged"
    failed = entry(original(7))
    failed["status"] = "retained_after_failure"
    retained = build(snapshot(advanced, failed), advanced)
    for path, artifact in retained["artifacts"].items():
        if path.startswith("house/") and path.endswith("/complete-result.json.gz"):
            left = next(row for row in artifact["content"]["rows"] if row["state_code"] == "HI")
            right = next(row for row in repeat["artifacts"][path]["content"]["rows"]
                         if row["state_code"] == "HI")
            for key in ("current", "previous", "current_native_clock", "current_source_scope"):
                assert left["reported_comparison"][key] == right["reported_comparison"][key]
            assert left["point"] == right["point"]


def test_full_candidate_exports_keep_native_context_without_participation():
    observed = {"races": {}, "official_candidate_evidence": {official.IDENTITY: entry()}}
    exported = results_congress.exports(observed)
    rows = list(csv.DictReader(io.StringIO(exported["congress-official-candidates.csv"].decode())))
    assert len(rows) == 6 and all(row["evidence_id"] == official.IDENTITY for row in rows)
    assert all(row["conditional_model_eligible"] == "False" for row in rows)
    baseline = {"index.json": encoded({"states": {}})}
    assert results_intake.numeric_observations(baseline, {official.IDENTITY: entry()}) == []


@pytest.mark.parametrize("review", [{}, [], {"states": {"WY": {}}}, None])
def test_malformed_review_refuses_before_projection(review):
    value = seed()
    value["protected_official_house_review"] = review
    observed = snapshot(value)
    if review is None:
        assert official.project_snapshot(observed, value) is observed
    else:
        with pytest.raises(ValueError):
            official.project_snapshot(observed, value)


def test_review_original_and_accepted_scientific_frame_are_both_bound(tmp_path):
    value = seed()
    review = value["protected_official_house_review"]
    for path, body in (
            (official.ORIGINAL_PATH, original()),
            (official.REVIEW_PATH, gzip.compress(encoded(review), mtime=0))):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    assert official.load_review(tmp_path, value) == review
    (tmp_path / official.ORIGINAL_PATH).write_bytes(original(7))
    with pytest.raises(ValueError):
        official.load_review(tmp_path, value)
    (tmp_path / official.ORIGINAL_PATH).write_bytes(original())
    altered = copy.deepcopy(value)
    altered["official_source_guards"]["HI"]["guard_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        official.load_review(tmp_path, altered)


def test_review_cannot_rebind_original_counts_or_allow_provider_substitution():
    for field in ("accepted_native", "provider_substitution_allowed"):
        value = seed()
        policy = value["protected_official_house_review"]["states"]["HI"]
        policy[field] = official.parse(original(7)) if field == "accepted_native" else True
        with pytest.raises(ValueError):
            official.project_snapshot(snapshot(value), value)


def test_default_selected_intake_and_complete_extracted_download(tmp_path, monkeypatch):
    from scripts import results_official_congress
    from test_results_intake import declaration, fixture, unavailable

    registry = fixture(tmp_path)
    config = results_intake.read(registry)
    config["congressional"] = {"test_scope": "stub national inventory only"}
    results_intake.write(registry, config)
    results_intake.write(registry.with_name("official-congress.json"),
                         results_official_congress.PROTECTED_CONFIG)
    monkeypatch.setattr(results_congress, "collect", lambda *args: {"races": {}})
    body = original()
    calls = []

    def acquire(collector, url):
        if url == results_intake.NATIONAL_URL:
            inventory = encoded(declaration())
            return inventory, {"origin": "synthetic_national_inventory", **pin(inventory)}
        if url != official.URL:
            return unavailable(collector, url)
        collector.guard(url)
        calls.append(url)
        return body, {"origin": "supplied_original", **pin(body)}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)
    work = tmp_path / "captured"
    first = results_intake.collect(registry, work)
    state = results_intake.read(work / "state.json")
    assert state["feeds"][official.IDENTITY]["status"] == "reported"
    calls.clear()
    selected = results_intake.refresh_selected(
        registry, tmp_path / "selected", state, [official.IDENTITY])
    assert calls == [official.URL]
    first_snapshot = json.loads(gzip.decompress((work / "snapshot.json.gz").read_bytes()))
    selected_snapshot = json.loads(gzip.decompress(
        (tmp_path / "selected/snapshot.json.gz").read_bytes()))
    assert selected_snapshot.pop("collection_scope")["source_ids"] == [official.IDENTITY]
    assert selected_snapshot == first_snapshot
    selected_state = results_intake.read(tmp_path / "selected/state.json")
    for identity, value in state["feeds"].items():
        assert selected_state["feeds"][identity] == value
    repeated = results_intake.refresh_selected(
        registry, tmp_path / "repeated", selected_state, [official.IDENTITY])
    assert repeated["version"] == selected["version"] and repeated["files"] == selected["files"]
    with zipfile.ZipFile(work / "complete-results.zip") as packet:
        assert packet.read("code/scripts/protected_official_house.py") == (
            ROOT / "scripts/protected_official_house.py").read_bytes()
        assert packet.read("code/tests/test_protected_official_house.py") == Path(__file__).read_bytes()
        rows = list(csv.DictReader(io.StringIO(packet.read(
            "queries/congress-official-candidates.csv").decode())))
        assert len(rows) == 6 and all(row["evidence_id"] == official.IDENTITY for row in rows)
        packet.extractall(tmp_path / "extracted")
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".", "--output", "reproduced"],
        cwd=tmp_path / "extracted", capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["network_requests"] == 0
