import copy
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts import results_aspx_congress as source
from scripts import results_intake, results_official_congress
from scripts.participation_intake.contract import encoded, pin


def facts():
    return json.loads((Path(__file__).parent / "fixtures/oregon-federal-candidates.json").read_bytes())


def html(value):
    parts = [
        "<title>Oregon Secretary of State</title><form>",
        "<h3>" + value["status_literal"] + "</h3>",
        "<h2>General Election<br/>November 3, 2026</h2>",
        '<div class="next-count">Results last updated: ' + value["source_update_label"] + "</div>",
        '<div class="disclaimer">' + value["write_in_scope_notice"] + "</div>",
    ]
    for race in value["races"]:
        parts.extend([
            '<div class="display-results-box-a"><h1>' + race["office_label"] + "</h1></div>",
            '<input raceid="' + race["contest_id"] + '">',
            '<div class="precinct-fully">' + race["reported_literal"] + " out of "
            + race["total_units_literal"] + " Precincts Reported</div>",
        ])
        for candidate in race["candidates"]:
            parts.extend([
                '<div class="col display-results-box-d"><h1>'
                + escape(candidate["name_literal"]) + "</h1><h2>"
                + escape(candidate["party_literal"]) + "</h2></div>",
                '<div id="' + candidate["candidate_id"] + '">\n</div>',
                '<div class="col display-results-box-f"><div>'
                + candidate["votes_literal"] + "</div></div>",
                '<div id="writeins_' + race["contest_id"] + '_NON" style="display:none"></div>',
            ])
        parts.extend([
            '<div class="col display-results-box-totalvotes"><div>total votes</div></div>',
            '<div class="col display-results-box-total"><div id="' + race["contest_id"]
            + 'totals">' + race["contest_total_literal"] + "</div></div>",
        ])
    return ("".join(parts) + "</form>").encode()


def revision(value, delta):
    changed = copy.deepcopy(value)
    row = changed["races"][3]
    candidate = next(c for c in row["candidates"] if c["name_literal"] == "Justin Filip")
    candidate["votes_literal"] = str(int(candidate["votes_literal"].replace(",", "")) + delta)
    row["contest_total_literal"] = str(int(row["contest_total_literal"].replace(",", "")) + delta)
    return changed


@pytest.mark.parametrize("delta", [0, 7, -13, -11857])
def test_complete_printed_tables_preserve_minors_fusion_write_ins_and_revisions(delta):
    value = revision(facts(), delta)
    before = copy.deepcopy(value)
    result = source.parse(html(value))
    assert result == source.normalized(value)
    assert value == before
    assert len(result["races"]) == 6
    assert sum(len(r["candidates"]) for r in result["races"]) == 20
    assert result["source_updated_at"] == "2026-11-18T12:15:00-08:00"
    assert sum(c["votes"] for r in result["races"] for c in r["candidates"]
               if c["name"] == "Justin Filip") == 11857 + delta
    assert all(not r["complete_reporting"] and r["reported_units"] == 0 for r in result["races"])
    assert [c["votes"] for r in result["races"] for c in r["candidates"]
            if c["role"] == "generic_write_in"] == [535, 402, 681, 328, 296, 355]
    assert result["complete_printed_candidate_tables"]
    assert not result["exhaustive_write_in_universe_qualified"]
    assert not result["participation_observation_qualified"]
    assert not result["provider_other_equivalence_qualified"]
    assert not result["conditional_model_eligible"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "party", "write-in-party",
                                   "total", "negative", "boolean", "counter", "stage",
                                   "clock", "notice", "district", "identity"])
def test_changed_or_incomplete_facts_refuse_instead_of_approving_models(change):
    value = facts()
    first = value["races"][0]
    if change == "missing":
        value["races"].pop()
    elif change == "duplicate":
        value["races"][-1] = copy.deepcopy(first)
    elif change == "party":
        first["candidates"][0]["party_literal"] = "Unreviewed endorsement"
    elif change == "write-in-party":
        first["candidates"][-1]["party_literal"] = "Republican"
    elif change == "total":
        first["contest_total_literal"] = "1"
    elif change == "negative":
        first["candidates"][0]["votes_literal"] = "-1"
    elif change == "boolean":
        first["candidates"][0]["votes_literal"] = True
    elif change == "counter":
        first["reported_literal"] = "9999"
    elif change == "stage":
        value["election_label"] = "Primary Election May 19, 2026"
    elif change == "clock":
        value["source_update_label"] = "11/18/2026 | 12:15 PM"
    elif change == "notice":
        value["write_in_scope_notice"] = ""
    elif change == "district":
        first["office_label"] = "US Representative, 7th District"
    else:
        first["candidates"][0]["candidate_id"] = first["candidates"][1]["candidate_id"]
    with pytest.raises((ValueError, TypeError)):
        source.normalized(value)


def test_new_named_write_in_details_are_not_silently_discarded():
    body = html(facts()).replace(b'style="display:none"></div>',
                                b'style="display:none">New named write-in 17</div>', 1)
    with pytest.raises(ValueError, match="write-in detail"):
        source.parse(body)


def test_primary_heading_and_removed_notice_are_not_accepted_from_html():
    body = html(facts())
    for changed in (body.replace(b"General Election", b"Primary Election"),
                    body.replace(source.WRITE_IN_NOTICE.encode(), b"")):
        with pytest.raises(ValueError, match="publisher, election or stage"):
            source.parse(changed)


def capture(tmp_path, value, prior=None, stopped=False):
    collector = results_intake.Collector(
        tmp_path, {source.IDENTITY: prior} if prior else {},
        {"urls": [source.URL] if stopped else [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 19, tzinfo=timezone.utc))
    calls = []

    def acquire(url):
        collector.guard(url)
        calls.append(url)
        if value is None:
            raise OSError("Unavailable original")
        body = html(value)
        return body, {"origin": "supplied_original", **pin(body)}

    collector.acquire = acquire
    result = results_official_congress.collect_sources(
        collector, results_official_congress.ASPX_CONFIG, selected=(source.IDENTITY,))
    return result[source.IDENTITY], calls


def test_default_registered_source_exports_complete_partial_evidence(tmp_path):
    from scripts import results_congress

    declaration_path = results_intake.ROOT / "data/results-intake/official-congress.json"
    declaration = (results_intake.read(declaration_path) if declaration_path.exists() else
                   results_intake.read(results_intake.ROOT.parent / "inputs/registry.json")[
                       "official_congress"])
    assert declaration == results_official_congress.ASPX_CONFIG
    entry, calls = capture(tmp_path, facts())
    assert entry["status"] == "reported" and calls == [source.URL]
    attached = results_official_congress.attach({"races": {}}, {source.IDENTITY: entry})
    exports = results_congress.exports(attached)
    assert len(results_official_congress.rows(attached)) == 20
    assert b"Pacific Green, Progressive" in exports["congress-official-candidates.csv"]
    assert b"Democrat, Working Families" in exports["congress-official-candidates.csv"]
    assert source.WRITE_IN_NOTICE.encode() in exports["congress-official-candidates.csv"]
    assert results_intake.numeric_observations(
        {"index.json": encoded({"states": {}})}, {source.IDENTITY: entry}) == []
    assert all(not row["universe_equivalence_qualified"]
               for row in results_official_congress.reconciliation(attached))


def test_repeated_revised_failed_stopped_and_recovered_captures(tmp_path):
    first, _ = capture(tmp_path / "first", facts())
    same, _ = capture(tmp_path / "same", facts(), first)
    assert same == first
    up, _ = capture(tmp_path / "up", revision(facts(), 7), same)
    down, _ = capture(tmp_path / "down", revision(facts(), -13), up)
    assert up["status"] == down["status"] == "reported"
    assert sum(r["contest_total"] for r in up["data"]["races"]) == 1948516
    assert sum(r["contest_total"] for r in down["data"]["races"]) == 1948496
    for label, stopped in (("outage", False), ("stopped", True)):
        held, calls = capture(tmp_path / label, None, down, stopped=stopped)
        assert held["status"] == "retained_after_failure"
        assert held["data"] == down["data"] and held["source"] == down["source"]
        assert held["first_observed_at"] == down["first_observed_at"]
        assert calls == ([] if stopped else [source.URL])
        recovered, _ = capture(tmp_path / (label + "-recovered"), facts(), held)
        assert recovered["status"] == "reported" and recovered["data"] == first["data"]


@pytest.mark.parametrize("change", ["rollback", "future", "lost", "renamed", "universe", "contest"])
def test_incompatible_native_revisions_keep_last_good_evidence(tmp_path, change):
    first, _ = capture(tmp_path / "first", facts())
    value = facts()
    if change == "rollback":
        value["source_update_label"] = "11/17/2026 | 12:15 PM PT"
    elif change == "future":
        value["source_update_label"] = "11/19/2026 | 12:15 PM PT"
    elif change == "lost":
        row = value["races"][3]
        removed = row["candidates"].pop(2)
        row["contest_total_literal"] = str(
            int(row["contest_total_literal"].replace(",", ""))
            - int(removed["votes_literal"].replace(",", "")))
    elif change == "renamed":
        value["races"][0]["candidates"][0]["name_literal"] = "Different Person"
    elif change == "universe":
        value["races"][0]["total_units_literal"] = "219"
    else:
        value["races"][0]["contest_id"] = "999999"
        for candidate in value["races"][0]["candidates"]:
            candidate["candidate_id"] = candidate["candidate_id"].replace("300038696", "999999")
    held, _ = capture(tmp_path / "rejected", value, first)
    assert held["status"] == "retained_after_failure"
    assert held["data"] == first["data"] and held["source"] == first["source"]


def test_cross_contest_candidate_and_total_ids_refuse():
    body = html(facts())
    for before, after in ((b"bar300038696300060170", b"bar300038697300060170"),
                          (b'id="300038696totals"', b'id="300038697totals"')):
        assert before in body
        with pytest.raises(ValueError):
            source.parse(body.replace(before, after, 1))


def test_literal_whitespace_is_retained_separately_from_identity_matching():
    value = facts()
    value["races"][0]["candidates"][0]["name_literal"] = " Barbara  J Kahl "
    value["races"][0]["candidates"][0]["party_literal"] = " Republican "
    candidate = source.parse(html(value))["races"][0]["candidates"][0]
    assert candidate["name"] == "Barbara J Kahl" and candidate["literal_party"] == "Republican"
    assert candidate["name_literal"] == " Barbara  J Kahl "
    assert candidate["party_literal"] == " Republican "


def test_actual_default_collection_and_extracted_complete_packet(tmp_path, monkeypatch):
    from test_results_intake import fixture, unavailable
    from scripts import results_congress

    registry = fixture(tmp_path)
    config = results_intake.read(registry)
    config["congressional"] = {"test_scope": "stub national inventory only"}
    results_intake.write(registry, config)
    results_intake.write(registry.with_name("official-congress.json"),
                         results_official_congress.ASPX_CONFIG)
    monkeypatch.setattr(results_congress, "collect", lambda *args: {"races": {}})
    body = html(facts())

    def acquire(collector, url):
        if url != source.URL:
            return unavailable(collector, url)
        collector.guard(url)
        return body, {"origin": "supplied_original", **pin(body)}

    monkeypatch.setattr(results_intake.Collector, "acquire", acquire)
    work = tmp_path / "captured"
    first = results_intake.collect(registry, work, now=datetime(2026, 11, 19, tzinfo=timezone.utc))
    state = results_intake.read(work / "state.json")
    assert state["feeds"][source.IDENTITY]["status"] == "reported"
    second = results_intake.collect(
        registry, tmp_path / "unchanged", state, now=datetime(2026, 11, 19, tzinfo=timezone.utc))
    assert first["version"] == second["version"] and first["files"] == second["files"]
    with zipfile.ZipFile(work / "complete-results.zip") as packet:
        for name in ("scripts/results_aspx_congress.py", "tests/test_results_aspx_congress.py",
                     "tests/fixtures/oregon-federal-candidates.json"):
            assert packet.read("code/" + name) == (results_intake.ROOT / name).read_bytes()
        assert source.WRITE_IN_NOTICE.encode() in packet.read(
            "queries/congress-official-candidates.csv")
        packet.extractall(tmp_path / "extracted")
    replay = subprocess.run(
        [sys.executable, "code/reproduce.py", "replay", "--package", ".", "--output", "reproduced"],
        cwd=tmp_path / "extracted", capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)["network_requests"] == 0
    portable = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_results_aspx_congress.py",
         "-k", "not actual_default_collection"],
        cwd=tmp_path / "extracted/code", capture_output=True, text=True)
    assert portable.returncode == 0, portable.stdout + portable.stderr
