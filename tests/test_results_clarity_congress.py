import copy
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import pytest

from scripts import results_clarity_congress as source
from scripts import results_congress, results_intake, results_official_congress
from scripts.participation_intake.contract import IntakeError, encoded, pin
from scripts.participation_intake.engine import Store


NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)
EMPTY_STOPS = {"urls": [], "prefixes": [], "hosts": []}


def facts():
    return json.loads(gzip.decompress(
        (Path(__file__).parent / "fixtures/iowa-clarity-federal-facts.json.gz").read_bytes()))


def bodies(value):
    settings = {
        "settings": {"electiondetails": value["election"]},
        "entityname": value["entityname"], "parententityname": value["parententityname"],
        "websiteupdatedat": value["publication_label"], **value["state_precincts"],
    }
    products = {key: encoded(settings if key == "settings" else value[key])
                for key in source.PRODUCTS}
    packet = io.BytesIO()
    with zipfile.ZipFile(packet, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo("detail.txt", (2026, 11, 3, 0, 0, 0)),
                         value["text_report"].encode("utf-8-sig"))
    products["text"] = packet.getvalue()
    return {
        source.URL: value["version"].encode(),
        **{f"{source.ROOT}/{value['version']}/json/{path}": products[key]
           for key, path in source.PRODUCTS.items()},
        source.report_url(value["version"]): products["text"],
    }


def revision(value, delta):
    value = copy.deepcopy(value)
    value["version"] = str(int(value["version"]) + 1)
    current = next(r for r in value["sum"]["Contests"] if r["K"] == "1100")
    descriptor = next(r for r in value["summary"] if r["K"] == "1100")
    children = next(r for r in value["details"]["Contests"] if r["K"] == "1100")
    index = current["CH"].index("Write-in")
    if delta == "zero":
        changes = {name: -v[index] for name, v in zip(children["P"], children["V"])}
    else:
        target = max(range(len(children["P"])), key=lambda i: children["V"][i][index])
        changes = {children["P"][target]: delta}
    for i, name in enumerate(children["P"]):
        children["V"][i][index] += changes.get(name, 0)
        children["T"][i] += changes.get(name, 0)
    total_delta = sum(changes.values())
    for row in (current, descriptor):
        row["V"][index] += total_delta
        row["T"][0] += total_delta
    lines = value["text_report"].splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.strip() == "United States Representative District 1 ( 1)")
    method_deltas = [0, 0]
    for i in range(start + 3, len(lines)):
        if not lines[i].strip():
            continue
        cells = re.split(r"\s{2,}", lines[i].strip())
        county = cells[0]
        offset = 2 + index * 3
        if county == "Totals:":
            for j in (0, 1):
                cells[offset + j] = str(int(cells[offset + j]) + method_deltas[j])
            cells[offset + 2] = str(int(cells[offset + 2]) + total_delta)
            cells[-1] = str(int(cells[-1]) + total_delta)
            lines[i] = "  ".join(cells)
            break
        change = changes.get(county, 0)
        old_ed, old_abs, old_total = map(int, cells[offset:offset + 3])
        new_total = old_total + change
        new_ed = old_ed + change if change >= 0 else min(old_ed, new_total)
        new_abs = new_total - new_ed
        method_deltas[0] += new_ed - old_ed
        method_deltas[1] += new_abs - old_abs
        cells[offset:offset + 3] = map(str, (new_ed, new_abs, new_total))
        cells[-1] = str(int(cells[-1]) + change)
        lines[i] = "  ".join(cells)
    value["text_report"] = "\n".join(lines)
    return value


def capture(tmp_path, value, prior=None, stopped=None):
    collector = results_intake.Collector(
        tmp_path, {source.IDENTITY: prior} if prior else {}, stopped or EMPTY_STOPS, NOW)
    originals = bodies(value) if value is not None else {}
    calls = []

    def acquire(url):
        collector.guard(url)
        calls.append(url)
        if url not in originals:
            raise OSError("Original unavailable")
        body = originals[url]
        return body, {"origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    return results_official_congress.collect_sources(
        collector, results_official_congress.CLARITY_CONFIG,
        selected=(source.IDENTITY,))[source.IDENTITY], calls


def test_complete_native_controls_keep_blank_parties_child_strings_and_separate_ballots():
    value = facts()
    result = source.normalized(value)
    stats = result["administrative_statistics"]
    assert len(stats["counties"]) == 99
    assert (stats["state_ballots"], stats["state_registered_stock"]) == (1382511, 2178374)
    assert stats["native_state_scalar_ballots"] == stats["native_state_scalar_registered"] == "0"
    assert result["source_updated_at"] is None
    assert result["source_publication_label"] == "11/18/2026 4:16:53 PM CST"
    assert len(result["races"]) == 5 and sum(len(r["candidates"]) for r in result["races"]) == 19
    unknown = {c["name"] for r in result["races"] for c in r["candidates"] if c["party_group"] == "U"}
    assert unknown == {"Write-in", "Michael Bridgford", "Dave Bushaw"}
    assert all(r["source_update_label"] is None for r in result["races"])
    assert any("0004" in r["Cid"] for r in value["details"]["Contests"])
    assert result["conditional_model_eligible"] is False
    assert result["provider_other_equivalence_qualified"] is False
    assert result["participation_observation_qualified"] is False
    assert sum(r["contest_total"] for r in result["races"]) != stats["state_ballots"]
    assert source.normalized(value) == result


@pytest.mark.parametrize("change", [
    "test", "primary", "override", "timezone", "missing-ballots", "boolean-ballots",
    "unsafe-ballots", "duplicate-county", "missing-contest", "duplicate-contest",
    "missing-writein", "candidate-party", "candidate-boolean", "county-text",
    "text-method-header", "text-parent", "child-id-number", "candidate-sum",
])
def test_partial_or_incompatible_editions_refuse_without_repair(change):
    value = facts()
    row = next(r for r in value["sum"]["Contests"] if r["K"] == "1100")
    if change == "test":
        value["election"]["istestmode"] = True
    elif change == "primary":
        value["election"]["internalname"] = "2026 Primary Election"
    elif change == "override":
        value["election"]["chkoverrideballotscastonreport"] = True
    elif change == "timezone":
        value["publication_label"] = "11/18/2026 4:16:53 PM"
    elif change in ("missing-ballots", "boolean-ballots", "unsafe-ballots"):
        value["status"]["B"][0] = {
            "missing-ballots": None, "boolean-ballots": True, "unsafe-ballots": 2**53}[change]
    elif change == "duplicate-county":
        value["status"]["P"][1] = value["status"]["P"][0]
    elif change == "missing-contest":
        value["summary"] = [r for r in value["summary"] if r["K"] != "1100"]
    elif change == "duplicate-contest":
        value["summary"].append(copy.deepcopy(value["summary"][0]))
    elif change == "missing-writein":
        row["CH"].pop()
    elif change == "candidate-party":
        row["P"][0] = "DEM"
    elif change == "candidate-boolean":
        row["V"][0] = True
    elif change == "county-text":
        value["text_report"] = value["text_report"].replace("3227", "3228", 1)
    elif change == "text-method-header":
        value["text_report"] = value["text_report"].replace("Election Day", "Provisional", 1)
    elif change == "text-parent":
        value["text_report"] = value["text_report"].replace("1382511", "1382512", 1)
    elif change == "child-id-number":
        value["details"]["Contests"][0]["Cid"][0] = 4
    else:
        row["V"][-1] += 1
    with pytest.raises((ValueError, KeyError, TypeError)):
        source.normalized(value)


def test_revised_counts_downward_true_zero_unchanged_outage_and_recovery(tmp_path):
    value = facts()
    first, calls = capture(tmp_path / "first", value)
    assert first["status"] == "reported"
    assert len(calls) == len(set(calls)) == 8
    assert source.report_url(value["version"]) in calls
    same, _ = capture(tmp_path / "same", value, first)
    assert same == first
    up_value = revision(value, 7)
    up, _ = capture(tmp_path / "up", up_value, first)
    down_value = revision(up_value, -13)
    down, _ = capture(tmp_path / "down", down_value, up)
    zero_value = revision(down_value, "zero")
    zero, _ = capture(tmp_path / "zero", zero_value, down)
    assert all(r["status"] == "reported" for r in (up, down, zero))
    candidate = next(r for r in zero["data"]["races"] if r["district"] == "IA-01")["candidates"][-1]
    assert candidate["votes"] == 0 and candidate["role"] == "generic_write_in"
    assert zero["data"]["administrative_statistics"] == first["data"]["administrative_statistics"]
    held, _ = capture(tmp_path / "outage", None, zero)
    assert held["status"] == "retained_after_failure"
    assert held["data"] == zero["data"] and held["source"] == zero["source"]
    recovered, _ = capture(tmp_path / "recovery", zero_value, held)
    assert recovered["status"] == "reported" and recovered["data"] == zero["data"]


@pytest.mark.parametrize("change", ["version", "publication", "future", "rewrite", "child-id", "corrupt-prior"])
def test_edition_lineage_and_missing_count_clock_do_not_allow_rollback(tmp_path, change):
    original = facts()
    first, _ = capture(tmp_path / "first", original)
    value = revision(original, 7)
    if change == "version":
        value["version"] = str(int(original["version"]) - 1)
    elif change == "publication":
        value["publication_label"] = "11/17/2026 4:16:53 PM CST"
    elif change == "future":
        value["publication_label"] = "11/20/2026 4:16:53 PM CST"
    elif change == "rewrite":
        value["version"] = original["version"]
    elif change == "child-id":
        value["details"]["Contests"][0]["Cid"][0] = "different"
    else:
        first["data"]["races"][0]["contest_total"] += 1
    held, _ = capture(tmp_path / "held", value, first)
    assert held["status"] == "retained_after_failure"
    assert held["data"] == first["data"] and held["source"] == first["source"]


def test_stopped_versioned_child_refuses_even_when_originals_are_supplied(tmp_path):
    value = facts()
    first, _ = capture(tmp_path / "first", value)
    stopped = {**EMPTY_STOPS, "urls": [source.report_url(value["version"])]}
    held, calls = capture(tmp_path / "held", value, first, stopped)
    assert held["status"] == "retained_after_failure" and held["data"] == first["data"]
    assert source.report_url(value["version"]) not in calls


def test_actual_default_collection_and_extracted_complete_packet(tmp_path, monkeypatch):
    from test_results_intake import fixture

    registry = fixture(tmp_path)
    config = results_intake.read(registry)
    config["congressional"] = {"test_scope": "stub national inventory only"}
    results_intake.write(registry, config)
    results_intake.write(registry.with_name("official-congress.json"),
                         results_official_congress.CLARITY_CONFIG)
    national = {
        f"npr:{chamber}:IA:{seat}:regular:general:not_ranked": {
            "data": {"chamber": chamber, "state_code": "IA", "seat": seat,
                     "election_date": "2026-11-03", "election_kind": "regular",
                     "stage": "general", "round": "not_ranked", "candidates": []}}
        for chamber, seat, _ in source.OFFICES.values()
    }
    monkeypatch.setattr(results_congress, "collect", lambda *args: {"races": {}})
    originals, calls = bodies(facts()), []

    def acquire(store, item, **kwargs):
        calls.append(item["url"])
        if item["url"] not in originals:
            raise IntakeError("source_unavailable", "Fixture transport unavailable")
        body = originals[item["url"]]
        return body, {"origin": "supplied_original", **pin(body)}

    monkeypatch.setattr(Store, "acquire", acquire)
    work = tmp_path / "captured"
    first = results_intake.collect(registry, work, now=NOW)
    state = results_intake.read(work / "state.json")
    assert state["feeds"][source.IDENTITY]["status"] == "reported"
    assert calls.count(source.URL) == 1
    comparison = copy.deepcopy(state["congress"])
    comparison["races"] = national
    rows = results_official_congress.rows(comparison)
    assert len(rows) == 19
    assert {r["provider_reconciliation"]["provider_race_id"] for r in rows} == set(national)
    assert results_intake.numeric_observations(
        {"index.json": encoded({"states": {}})}, {source.IDENTITY: state["feeds"][source.IDENTITY]}) == []
    second = results_intake.collect(registry, tmp_path / "same", state, now=NOW)
    assert first["version"] == second["version"] and first["files"] == second["files"]
    with zipfile.ZipFile(work / "complete-results.zip") as packet:
        for name in ("scripts/results_clarity_congress.py", "tests/test_results_clarity_congress.py",
                     "tests/fixtures/iowa-clarity-federal-facts.json.gz"):
            assert packet.read("code/" + name) == (results_intake.ROOT / name).read_bytes()
        assert b"Michael Bridgford" in packet.read("queries/congress-official-candidates.csv")
        packet.extractall(tmp_path / "extracted")
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".", "--output", "reproduced"],
        cwd=tmp_path / "extracted", capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["network_requests"] == 0
    portable = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_results_clarity_congress.py",
         "-k", "not actual_default_collection"],
        cwd=tmp_path / "extracted/code", capture_output=True, text=True)
    assert portable.returncode == 0, portable.stdout + portable.stderr
