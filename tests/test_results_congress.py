import copy
from datetime import datetime, timezone
import gzip
import json

import pytest

from scripts import results_congress as congress
from scripts.results_intake import Collector


NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
CONFIG = {"feeds": {chamber: {"url": "https://example.test/" + chamber}
                    for chamber in ("house", "senate")}}
STOPS = {"urls": [], "hosts": [], "prefixes": []}


def race(chamber="house", state="AL", seat="1", special=False, identity="101"):
    return {
        "test": False, "id": identity, "office": "H" if chamber == "house" else "S",
        "officeName": "U.S. House" if chamber == "house" else "U.S. Senate",
        "resultsType": "live", "level": "state", "state": state,
        "seatNumber": seat,
        "seat": ("District " + seat if chamber == "house" else
                 {"1": "Class I", "2": "Class II", "3": "Class III"}[seat]
                 + (" Unexpired Term" if special else "")),
        "type": "Special General" if special else "General",
        "updated": 1794749345891,
        "candidates": [
            {"id": "d", "first": "D", "last": "Candidate", "party": "Dem", "votes": 100},
            {"id": "r", "first": "R", "last": "Candidate", "party": "GOP", "votes": 90},
            {"id": "other-" + identity, "first": "", "last": "Other", "party": "Other", "votes": 0},
        ]}


def collect(tmp_path, bodies, previous=None, stopped=None):
    collector = Collector(tmp_path, {}, stopped or STOPS, NOW)

    def acquire(url):
        collector.guard(url)
        chamber = url.rsplit("/", 1)[-1]
        value = bodies[chamber]
        if isinstance(value, Exception):
            raise value
        return json.dumps({"results": value}).encode(), {"origin": "new_source_response"}

    collector.acquire = acquire
    return congress.collect(collector, previous, CONFIG)


def sources():
    return {"house": [race()], "senate": [race("senate", seat="2")]}


def review():
    return {
        "previous_district_queries": [{
            "district": "AL-AL", "geographic_boundary_stability_independently_qualified": True, "previous": {
                "reported_counts": {"D": 110, "R": 90, "O": 0},
                "source_candidate_rows": [], "major_party_presence": {"D": True, "R": True},
                "multiple_same_party_nominees": False, "missing_major_party_counts": []}}],
        "frozen_inputs": {"existing_other_office_models": {"body": json.dumps({"rows": [{
            "state_code": "AL", "office": "senate", "reported_comparison": {
                "baseline_cycle_year": 2020, "baseline_year": 2020, "baseline_stage": "general",
                "scope": "Statewide regular-seat candidate counts; special/unexpired seat rows excluded",
                "previous": {"D": 100, "R": 100, "O": 0},
                "native_candidate_facts": [], "qualification": "reviewed 2020 regular seat cycle",
                "baseline_source_url": "https://example.test/fec2020",
            }}]})}}}


def test_bulk_discovery_new_races_seats_stages_and_rounds(tmp_path):
    bodies = sources()
    first = collect(tmp_path, bodies)
    bodies["senate"].extend([
        race("senate", seat="3", special=True, identity="102"),
        {**race("senate", seat="2", identity="103"), "type": "General Runoff"},
        {**race("senate", seat="2", identity="104"), "rankedChoice": True, "round": 2},
    ])
    updated = collect(tmp_path, bodies, first)
    assert congress.summary(updated)["senate"]["discovered"] == 4
    assert len({row["id"] for row in congress.tables(updated)[0]}) == 5


def test_unchanged_collection_is_exact_noop(tmp_path):
    first = collect(tmp_path, sources())
    assert collect(tmp_path, sources(), first) == first


@pytest.mark.parametrize("role", ["aggregate_other", "named_minor"])
@pytest.mark.parametrize("votes", [0, 26])
def test_newer_additions_preserve_candidates_without_approving_model_inventory(tmp_path, role, votes):
    bodies = sources()
    if role == "aggregate_other":
        bodies["house"][0]["candidates"].pop()
    first = collect(tmp_path, bodies)
    original = next(row["data"] for row in first["races"].values() if row["data"]["chamber"] == "house")
    added = ({"id": "other-101", "first": "", "last": "Other", "party": "Other", "votes": votes}
             if role == "aggregate_other" else
             {"id": "minor", "first": "New", "last": "Candidate", "party": "Lib", "votes": votes})
    bodies["house"][0]["updated"] += 1
    bodies["house"][0]["candidates"].append(added)
    updated = collect(tmp_path, bodies, first)
    current = updated["races"][original["id"]]
    assert current["status"] == "reported"
    by_id = {row["candidate_id"]: row for row in current["data"]["candidates"]}
    assert [by_id[row["candidate_id"]] for row in original["candidates"]] == original["candidates"]
    assert by_id[added["id"]]["votes"] == votes
    with pytest.raises(ValueError, match="Candidate inventory"):
        congress.check_revision(original, current["data"])
    assert collect(tmp_path, bodies, updated) == updated
    # A new source category is not permission to remove it on a later refresh.
    bodies["house"][0]["updated"] += 1
    bodies["house"][0]["candidates"].pop()
    refused = collect(tmp_path, bodies, updated)["races"][original["id"]]
    assert refused["status"] == "retained_after_failure"
    assert refused["data"] == current["data"]


def test_additive_inventory_still_requires_a_newer_native_clock(tmp_path):
    bodies = sources()
    bodies["house"][0]["candidates"].pop()
    first = collect(tmp_path, bodies)
    bodies["house"][0]["candidates"].append(
        {"id": "other-101", "first": "", "last": "Other", "party": "Other", "votes": 0})
    current = next(row for row in collect(tmp_path, bodies, first)["races"].values()
                   if row["data"]["chamber"] == "house")
    assert current["status"] == "retained_after_failure"
    assert "newer native version" in current["error"]


@pytest.mark.parametrize("future_minutes,accepted", [(10, True), (16, False)])
def test_future_guard_uses_elapsed_acquisition_time_not_collection_start(
        tmp_path, monkeypatch, future_minutes, accepted):
    from scripts import results_intake as intake

    elapsed = [0]
    monkeypatch.setattr(intake.time, "monotonic", lambda: elapsed[0])
    collector = Collector(tmp_path, {}, STOPS, NOW)
    bodies = sources()
    bodies["house"][0]["updated"] = int(NOW.timestamp() * 1000) + future_minutes * 60_000
    collector.acquire = lambda url: (
        json.dumps({"results": bodies[url.rsplit("/", 1)[-1]]}).encode(),
        {"origin": "new_source_response"})
    # Other source families can precede the national feed in a full collection.
    elapsed[0] = 600
    result = congress.collect(collector, None, CONFIG)
    current = next(row for row in result["races"].values()
                   if row.get("chamber") == "house" or (row.get("data") or {}).get("chamber") == "house")
    assert (current["status"] == "reported") is accepted
    if not accepted:
        assert current["error"] == "Native count clock is in the future"


@pytest.mark.parametrize("chamber", ["house", "senate"])
def test_tabulation_status_can_advance_without_changing_the_count_clock(tmp_path, chamber):
    bodies = sources()
    bodies[chamber][0]["tabulationStatus"] = "Active Tabulation"
    first = collect(tmp_path, bodies)
    bodies[chamber][0]["tabulationStatus"] = "Gathering Certified Results"
    updated = collect(tmp_path, bodies, first)
    old = next(row["data"] for row in first["races"].values() if row["data"]["chamber"] == chamber)
    current = next(row for row in updated["races"].values() if row["data"]["chamber"] == chamber)
    assert current["status"] == "reported"
    assert current["data"]["candidates"] == old["candidates"]
    assert current["data"]["source_updated_at"] == old["source_updated_at"]
    assert current["data"]["native_certified"] is None
    assert current["data"]["native_facts"] == bodies[chamber][0]
    assert collect(tmp_path, bodies, updated) == updated


@pytest.mark.parametrize("change", ["counts", "reporting", "round", "certified", "rollback",
                                   "results_type", "invalid_status"])
def test_status_update_cannot_authorize_unversioned_source_changes(tmp_path, change):
    bodies = sources()
    first = collect(tmp_path, bodies)
    row = bodies["house"][0]
    row["tabulationStatus"] = "Gathering Certified Results"
    if change == "counts":
        row["candidates"][0]["votes"] -= 1
    elif change == "reporting":
        row["reporting"] = 1
    elif change == "round":
        row["round"] = 2
        row["updated"] -= 1
    elif change == "certified":
        row["certified"] = True
    elif change == "rollback":
        row["updated"] -= 1
    elif change == "results_type":
        row["resultsType"] = "final"
    else:
        row["tabulationStatus"] = []
    updated = collect(tmp_path, bodies, first)
    retained = next(entry for entry in updated["races"].values()
                    if entry.get("data", {}).get("chamber") == "house")
    original = next(entry for entry in first["races"].values()
                    if entry["data"]["chamber"] == "house")
    assert retained["status"] == "retained_after_failure"
    assert retained["data"] == original["data"] and retained["source"] == original["source"]


def test_special_class_two_cannot_borrow_regular_same_class_baseline(tmp_path):
    bodies = sources()
    bodies["senate"] = [race("senate", seat="2", special=True)]
    row = next(row for row in congress.comparisons(collect(tmp_path, bodies), review())
               if row["chamber"] == "senate")
    assert row["previous"] is None and not row["qualified_comparison"]


@pytest.mark.parametrize("seat,compatible", [("1", False), ("3", True)])
def test_reviewed_boundary_gate_is_district_specific_and_keeps_other_holds(tmp_path, seat, compatible):
    from scripts.congressional_geography import load_review
    from pathlib import Path

    geography = load_review(Path(__file__).resolve().parents[1])
    scientific = review()
    template = scientific["previous_district_queries"][0]
    scientific["previous_district_queries"] = [
        {**copy.deepcopy(template), "district": "AL-" + str(number).zfill(2)}
        for number in range(1, 4)]
    bodies = sources()
    bodies["house"] = [race(seat=seat)]
    source = collect(tmp_path, bodies)
    compared = congress.comparisons(source, scientific, boundary_review=geography)
    row = next(row for row in compared if row["chamber"] == "house")
    assert row["qualified_comparison"] is compatible
    assert row["baseline"]["boundary_eligibility"]["boundary_compatible"] is compatible
    assert row["raw_recorded_margin_change_pp"] is not None
    source["races"][row["id"]].update(status="retained_after_failure", freshness="retained_last_good")
    retained = next(value for value in congress.comparisons(
        source, scientific, boundary_review=geography) if value["chamber"] == "house")
    assert not retained["qualified_comparison"]
    assert any("retained, not refreshed" in hold for hold in retained["comparison_holds"])
    assert retained["raw_recorded_margin_change_pp"] == row["raw_recorded_margin_change_pp"]


def test_reviewed_maine_final_pair_qualifies_district_and_state_without_waiving_revision_guards(tmp_path):
    from pathlib import Path

    from scripts.congressional_geography import load_review

    sources_by_chamber = sources()
    one = race(state="ME", seat="1")
    two = race(state="ME", seat="2", identity="102")
    two.update(rankedChoice=True, rcvResult="final")
    two["candidates"][0].update(first="Matthew", last="Dunlap", votes=165432, id="dd")
    two["candidates"][1].update(first="Paul", last="LePage", votes=170890, id="rr")
    sources_by_chamber["house"] = [one, two]
    source = collect(tmp_path, sources_by_chamber)
    review_data = review()
    template = review_data["previous_district_queries"][0]
    first = {**copy.deepcopy(template), "district": "ME-01"}
    final = {**copy.deepcopy(template), "district": "ME-02"}
    final["previous"].update(
        reported_counts={"D": 197151, "R": 194445, "O": 0},
        source_candidate_rows=[
            {"group": "D", "name": "Jared F. Golden", "votes": 197151, "named": True},
            {"group": "R", "name": "Austin Theriault", "votes": 194445, "named": True},
        ])
    review_data["previous_district_queries"] = [first, final]
    geography = load_review(Path(__file__).resolve().parents[1])

    def decisions(enabled):
        races = congress.comparisons(source, review_data, boundary_review=geography, final_rounds=enabled)
        district = next(r for r in races if r["id"] == "npr:house:ME:2:regular:general:rcv-final")
        state = congress.house_state_comparisons(source, review_data, races)[0]
        return district, state

    assert all(not row["qualified_comparison"] for row in decisions(False))
    district, state = decisions(True)
    assert district["qualified_margin_change_pp"] == pytest.approx(-2.313867230207)
    assert state["qualified_comparison"] and district["id"] in state["final_round_pairs"]
    frame = source["races"][district["id"]]
    frame["data"]["candidates"][0]["votes"] -= 1
    assert all(not row["qualified_comparison"] for row in decisions(True))
    frame["data"]["candidates"][0]["votes"] += 1
    frame.update(status="retained_after_failure", freshness="retained_last_good")
    assert all(not row["qualified_comparison"] for row in decisions(True))


def test_default_sidecar_and_bounded_refresh_preserve_other_sources(tmp_path, monkeypatch):
    from scripts import results_intake as intake
    from test_results_intake import fixture

    registry = fixture(tmp_path)
    intake.write(registry.with_name("congress.json"), {
        **CONFIG, "contract": "participation.congressional_provider.v1",
        "election_date": "2026-11-03", "source_stops": STOPS})
    previous = {
        "feeds": {"retained": {"status": "reported", "data": {"count": 12}}},
        "granular": {}, "house": {str(index): {} for index in range(435)},
        "districts": {str(index): {} for index in range(435)},
        "directories": {state: {} for state in intake.STATES}, "source_stops": STOPS}
    original = copy.deepcopy(previous)
    calls = []

    def acquire(self, url):
        calls.append(url)
        chamber = url.rsplit("/", 1)[-1]
        return json.dumps({"results": sources()[chamber]}).encode(), {"origin": "new_source_response"}

    monkeypatch.setattr(Collector, "acquire", acquire)
    monkeypatch.setattr(intake, "export_collection",
                        lambda work, config, baseline, inputs, extras, now, attempts: inputs)
    first = intake.refresh_congress(registry, tmp_path / "scoped", previous, NOW)
    assert set(calls) == {row["url"] for row in CONFIG["feeds"].values()}
    assert previous == original
    assert {key: first[key] for key in original} == original
    assert congress.summary(first["congress"])["senate"]["refreshed"] == 1
    second = intake.refresh_congress(registry, tmp_path / "scoped", first, NOW)
    assert second == first
    del previous["house"]["0"]
    with pytest.raises(ValueError, match="complete accepted"):
        intake.refresh_congress(registry, tmp_path / "invalid", previous, NOW)


@pytest.mark.parametrize("seat", ["7", "8"])
def test_split_block_successor_qualifies_recorded_revisions_not_retained_results(tmp_path, seat):
    from pathlib import Path
    from scripts.congressional_geography import load_review

    root = Path(__file__).resolve().parents[1]
    original = load_review(root, include_split_geometry=False)
    successor = load_review(root)
    scientific = review()
    template = scientific["previous_district_queries"][0]
    scientific["previous_district_queries"] = [
        {**copy.deepcopy(template), "district": f"CO-{number:02d}"}
        for number in range(1, 9)]
    source = collect(tmp_path, {
        "house": [race(state="CO", seat=seat)], "senate": []})
    old = congress.comparisons(source, scientific, boundary_review=original)[0]
    assert old["comparison_holds"] == ["House boundary hold: split_block_geometry_unresolved"]
    new = congress.comparisons(source, scientific, boundary_review=successor)[0]
    assert new["qualified_comparison"]
    assert new["raw_recorded_margin_change_pp"] == old["raw_recorded_margin_change_pp"]
    for delta in (7, -13):
        revised = race(state="CO", seat=seat)
        revised["updated"] += 60000
        revised["candidates"][0]["votes"] += delta
        updated = collect(tmp_path / str(delta), {"house": [revised], "senate": []}, source)
        compared = congress.comparisons(updated, scientific, boundary_review=successor)[0]
        assert compared["qualified_comparison"]
        assert compared["D"] == 100 + delta
        assert compared["raw_recorded_margin_change_pp"] != new["raw_recorded_margin_change_pp"]
        repeated = collect(tmp_path / (str(delta) + "-repeat"),
                           {"house": [revised], "senate": []}, updated)
        assert repeated == updated
        assert congress.comparisons(repeated, scientific, boundary_review=successor) == [
            compared]
    source["races"][new["id"]].update(
        status="retained_after_failure", freshness="retained_last_good")
    retained = congress.comparisons(source, scientific, boundary_review=successor)[0]
    assert not retained["qualified_comparison"]
    assert any("retained, not refreshed" in hold for hold in retained["comparison_holds"])
    assert retained["raw_recorded_margin_change_pp"] == old["raw_recorded_margin_change_pp"]


@pytest.mark.parametrize("votes", [101, 83, 0])
def test_newer_corrections_including_decrease_zero_unknown(tmp_path, votes):
    bodies = sources()
    first = collect(tmp_path, bodies)
    bodies["house"][0]["updated"] += 1
    bodies["house"][0]["candidates"][0]["votes"] = votes
    updated = collect(tmp_path, bodies, first)
    row = next(row for row in congress.tables(updated)[0] if row["chamber"] == "house")
    assert row["D"] == votes and row["freshness"] == "source_verified"


def test_unknown_is_not_zero_and_later_missing_count_retains_last_good(tmp_path):
    bodies = sources()
    bodies["senate"][0]["candidates"][0]["votes"] = None
    first = collect(tmp_path, bodies)
    senate = next(row for row in congress.tables(first)[0] if row["chamber"] == "senate")
    assert senate["D"] is None and senate["D_two_party_share_pct"] is None
    bodies["house"][0]["updated"] += 1
    bodies["house"][0]["candidates"][0]["votes"] = None
    second = collect(tmp_path, bodies, first)
    house = next(row for row in congress.tables(second)[0] if row["chamber"] == "house")
    assert house["D"] == 100 and house["freshness"] == "retained_last_good"


def test_malformed_race_is_isolated_and_missing_count_field_is_not_unknown(tmp_path):
    bodies = sources()
    bodies["house"].extend([None, {**race(identity="new", state="AK"), "id": ["invalid"]}])
    del bodies["house"][0]["candidates"][0]["votes"]
    result = collect(tmp_path, bodies)
    assert congress.summary(result)["house"]["held"] == 3
    assert congress.summary(result)["senate"]["refreshed"] == 1


def test_same_provider_rcv_rounds_are_separate_and_literal_unknown_party_is_retained(tmp_path):
    bodies = sources()
    row = bodies["senate"][0]
    row["rankedChoice"], row["round"] = True, 1
    bodies["senate"].append({**copy.deepcopy(row), "round": 2})
    row["candidates"][0]["party"] = None
    result = collect(tmp_path, bodies)
    assert congress.summary(result)["senate"]["refreshed"] == 2
    assert any(c["party_group"] == "U" and c["literal_party"] is None
               for c in congress.tables(result)[1])


@pytest.mark.parametrize("final_state", ["accepted", "equal_clock", "different_provider", "unknown", "still_advertised"])
def test_only_a_verified_later_same_contest_rcv_final_supersedes_a_withdrawn_pending_round(tmp_path, final_state):
    bodies = sources()
    before = bodies["house"][0]
    before.update(rankedChoice=True, rcvResult="pending")
    prior = collect(tmp_path, bodies)
    final = copy.deepcopy(before)
    final.update(rcvResult="final", updated=before["updated"] + (0 if final_state == "equal_clock" else 60000))
    if final_state == "different_provider":
        final["id"] = "303"
    if final_state == "unknown":
        final["candidates"][0]["votes"] = None
    bodies["house"] = [before, final] if final_state == "still_advertised" else [final]
    updated = collect(tmp_path, bodies, prior)
    races, candidates, coverage = congress.tables(updated)
    prior_id = next(key for key in prior["races"] if key.endswith("rcv-pending"))
    pending = next(r for r in races if r["id"] == prior_id)
    assert pending["D"] == congress.tables(prior)[0][0]["D"]
    expected = final_state == "accepted"
    assert ("superseded_by_race_id" in pending) is expected
    assert congress.summary(updated)["house"]["superseded_rcv_records"] == int(expected)
    if expected:
        target = next(r for r in races if r["id"].endswith("rcv-final"))
        assert target["status"] == "reported" and pending["status"] == "retained_after_failure"
        assert all(r["superseded_by_race_id"] == target["id"]
                   for r in (*candidates, *coverage) if r["id"] == prior_id)
        assert collect(tmp_path, bodies, updated) == updated
        bodies["house"] = ValueError("provider outage")
        failed = collect(tmp_path, bodies, updated)
        assert congress.summary(failed)["house"]["superseded_rcv_records"] == 0
        assert congress.summary(failed)["house"]["refreshed"] == 0


@pytest.mark.parametrize("change", ["rollback", "same_clock", "missing", "identity", "party",
                                   "boolean", "negative", "wrong_office", "test", "date"])
def test_rejected_race_retains_last_good_without_blocking_others(tmp_path, change):
    bodies = sources()
    first = collect(tmp_path, bodies)
    row = bodies["house"][0]
    row["updated"] += 10
    if change == "rollback":
        row["updated"] -= 20
    elif change == "same_clock":
        row["updated"] -= 10
        row["candidates"][0]["votes"] += 1
    elif change == "missing":
        row["candidates"].pop()
    elif change == "identity":
        row["candidates"][0]["last"] = "Different"
    elif change == "party":
        row["candidates"][0]["party"] = "GOP"
    elif change == "boolean":
        row["candidates"][0]["votes"] = True
    elif change == "negative":
        row["candidates"][0]["votes"] = -1
    elif change == "wrong_office":
        row["office"] = "S"
    elif change == "test":
        row["test"] = True
    else:
        row["electionDate"] = "2024-11-05"
    bodies["senate"][0]["updated"] += 10
    bodies["senate"][0]["candidates"][0]["votes"] = 103
    updated = collect(tmp_path, bodies, first)
    held = next(entry for entry in updated["races"].values() if entry.get("data", {}).get("chamber") == "house")
    original = next(entry for entry in first["races"].values() if entry["data"]["chamber"] == "house")
    assert held["data"] == original["data"] and held["source"] == original["source"]
    assert held["status"] == "retained_after_failure"
    assert congress.summary(updated)["senate"]["refreshed"] == 1


def test_partial_outage_and_missing_advertisement_retention(tmp_path):
    bodies = sources()
    first = collect(tmp_path, bodies)
    bodies["senate"] = ValueError("provider outage")
    updated = collect(tmp_path, bodies, first)
    assert congress.summary(updated)["house"]["refreshed"] == 1
    assert congress.summary(updated)["senate"]["retained"] == 1
    assert congress.summary(updated)["senate"]["refreshed"] == 0


def test_weekly_archive_refresh_applies_congress_revisions_and_retains_a_failed_chamber(tmp_path, monkeypatch):
    from scripts import results_intake as intake, results_turnout_history as history
    from test_results_intake import fixture

    registry = fixture(tmp_path)
    intake.write(registry.with_name("congress.json"), {
        **CONFIG, "contract": "participation.congressional_provider.v1",
        "election_date": "2026-11-03", "source_stops": STOPS})
    bodies = sources()
    previous = {
        "feeds": {}, "granular": {}, "house": {str(index): {} for index in range(435)},
        "districts": {str(index): {} for index in range(435)},
        "directories": {state: {} for state in intake.STATES}, "source_stops": STOPS,
        "congress": collect(tmp_path / "prior", bodies),
    }
    original = copy.deepcopy(previous)
    annual_row = {"status": "reported", "data": {"total": 42}}
    monkeypatch.setattr(history, "collect_washington", lambda _: annual_row)
    monkeypatch.setattr(intake, "late_archive_sources", lambda: (history.WA_FEED,))
    monkeypatch.setattr(intake, "export_collection", lambda *args: args[3])
    calls = []

    def acquire(self, url):
        calls.append(url)
        chamber = url.rsplit("/", 1)[-1]
        if chamber == "senate":
            raise OSError("Temporary provider outage")
        return json.dumps({"results": bodies[chamber]}).encode(), {"origin": "new_source_response"}

    monkeypatch.setattr(Collector, "acquire", acquire)
    scoped = intake.refresh_selected(registry, tmp_path / "scoped", previous, [history.WA_FEED], NOW)
    assert calls == [] and scoped["congress"] == original["congress"]
    for revised_count in (105, 97):
        bodies["house"][0]["updated"] += 1
        bodies["house"][0]["candidates"][0]["votes"] = revised_count
        weekly = intake.refresh_selected(registry, tmp_path / "weekly", previous,
                                         [history.WA_FEED], NOW, late_archives=True)
        assert weekly["collection_scope"]["congressional_provider_feeds_checked"] == ["house", "senate"]
        assert weekly["house"] == original["house"]
        assert weekly["granular"][history.WA_FEED] == annual_row
        races = list(weekly["congress"]["races"].values())
        fresh = next(row for row in races if row["data"]["chamber"] == "house")
        retained = next(row for row in races if row["data"]["chamber"] == "senate")
        assert fresh["status"] == "reported" and congress.totals(fresh["data"])["D"] == revised_count
        assert retained["status"] == "retained_after_failure"
        assert congress.totals(retained["data"])["D"] == 100
        previous = weekly
    assert len(calls) == 4 and set(calls) == {row["url"] for row in CONFIG["feeds"].values()}


def test_unavailable_first_result_remains_a_hold_during_feed_outage(tmp_path):
    bodies = sources()
    bodies["senate"][0]["candidates"] = []
    first = collect(tmp_path, bodies)
    bodies["senate"] = ValueError("provider outage")
    updated = collect(tmp_path, bodies, first)
    assert congress.summary(updated)["senate"]["held"] == 1
    assert congress.summary(updated)["senate"]["retained"] == 0


def test_reused_provider_id_cannot_move_to_another_state(tmp_path):
    bodies = sources()
    first = collect(tmp_path, bodies)
    bodies["senate"][0]["state"] = "CA"
    bodies["senate"][0]["updated"] += 1
    updated = collect(tmp_path, bodies, first)
    old = next(entry for entry in first["races"].values() if entry["data"]["chamber"] == "senate")
    retained = next(entry for entry in updated["races"].values() if entry.get("data", {}).get("chamber") == "senate")
    assert retained["data"] == old["data"]
    assert retained["status"] == "retained_after_failure"
    assert "identity changed" in retained["error"]


def test_native_literals_aggregates_independents_and_nonvoting(tmp_path):
    bodies = sources()
    bodies["house"].append(race(state="DC", identity="delegate"))
    bodies["senate"][0]["candidates"].append({
        "id": "ind", "first": "", "last": "Write-ins", "party": "Ind", "votes": 0})
    result = collect(tmp_path, bodies)
    assert congress.summary(result)["house"]["nonvoting_house_seats"] == 1
    candidates = congress.tables(result)[1]
    assert any(row["literal_party"] == "Ind" and row["votes"] == 0 for row in candidates)
    assert any(row["role"] == "provider_aggregate_other" for row in candidates)


def test_duplicate_declaration_cannot_pass_as_a_fresh_race(tmp_path):
    bodies = sources()
    bodies["house"].append(copy.deepcopy(bodies["house"][0]))
    result = collect(tmp_path, bodies)
    assert congress.summary(result)["house"]["refreshed"] == 0


def test_stopped_catalog_is_not_requested_and_other_chamber_updates(tmp_path):
    result = collect(tmp_path, sources(), stopped={
        **STOPS, "urls": [CONFIG["feeds"]["senate"]["url"]]})
    assert result["feeds"]["senate"]["error"] == "source_stopped"
    assert congress.summary(result)["house"]["refreshed"] == 1


def test_comparison_revision_exports_and_raw_held_changes(tmp_path):
    bodies = sources()
    original = collect(tmp_path, bodies)
    before_files, _ = congress.runtime(original, review())
    bodies["house"][0]["updated"] += 1
    bodies["house"][0]["candidates"][0]["votes"] = 70
    revised = collect(tmp_path, bodies, original)
    files, descriptor = congress.runtime(revised, review())
    decoded = json.loads(gzip.decompress(files[descriptor["path"]]))
    house = next(row for row in decoded["races"] if row["chamber"] == "house")
    assert house["D"] == 70 and house["qualified_comparison"]
    assert house["raw_recorded_margin_change_pp"] == pytest.approx(100 * (70 - 90) / 160 - 10)
    assert files["congressional/congress-candidates.csv"] != before_files["congressional/congress-candidates.csv"]
    bodies["senate"][0]["rankedChoice"] = True
    held = congress.comparisons(collect(tmp_path, bodies), review())
    senate = next(row for row in held if row["chamber"] == "senate")
    assert senate["raw_recorded_margin_change_pp"] is not None
    assert not senate["qualified_comparison"] and senate["qualified_margin_change_pp"] is None
    assert not senate["behavioral_estimate_updated"]


def test_special_senate_cannot_borrow_regular_seat_baseline(tmp_path):
    bodies = sources()
    bodies["senate"] = [race("senate", seat="3", special=True)]
    row = next(row for row in congress.comparisons(collect(tmp_path, bodies), review())
               if row["chamber"] == "senate")
    assert row["previous"] is None and not row["qualified_comparison"]


def test_class_ii_does_not_match_class_iii_prefix():
    source = race("senate", seat="2")
    source["seat"] = "Class III"
    with pytest.raises(ValueError, match="class and seat"):
        congress.normalize(source, "senate")


def test_unknown_district_boundaries_hold_district_but_not_complete_state_accounting(tmp_path):
    data = collect(tmp_path, sources())
    reviewed = review()
    reviewed["previous_district_queries"][0]["geographic_boundary_stability_independently_qualified"] = False
    district = next(row for row in congress.comparisons(data, reviewed) if row["chamber"] == "house")
    assert not district["qualified_comparison"] and district["raw_recorded_margin_change_pp"] is not None
    state = congress.house_state_comparisons(data, reviewed)[0]
    assert state["qualified_comparison"] and state["current"]["D"] == 100
    data["races"][district["id"]]["data"]["candidates"][0]["party_group"] = "O"
    assert not congress.house_state_comparisons(data, reviewed)[0]["qualified_comparison"]


def test_unopposed_previous_race_keeps_defined_raw_arithmetic(tmp_path):
    reviewed = review()
    reviewed["previous_district_queries"][0]["previous"]["reported_counts"]["D"] = 0
    row = next(row for row in congress.comparisons(collect(tmp_path, sources()), reviewed)
               if row["chamber"] == "house")
    assert not row["qualified_comparison"]
    assert row["previous"]["D"] == 0 and row["raw_recorded_margin_change_pp"] is not None


def test_matched_district_subtotal_pools_votes_and_excludes_held_or_unverified_rows():
    def row(seat, previous, current, qualified=True, boundary=True):
        return {"id": f"race-{seat}", "seat": seat, "advertised": True,
                "qualified_comparison": qualified, "previous": dict(zip("DR", previous)),
                **dict(zip("DR", current)),
                "baseline": {"boundary_eligibility": {"boundary_compatible": boundary}}}

    races = [row("2", (60, 40), (50, 50)), row("1", (450, 450), (540, 360)),
             row("3", (800, 200), (200, 800), qualified=False),
             row("4", (200, 800), (800, 200), boundary=False)]
    selected = {race["id"] for race in races}
    subtotal = congress.matched_district_subset(races, selected, 4)
    assert subtotal["race_ids"] == ["race-1", "race-2"]
    assert subtotal["previous"] == {"D": 510, "R": 490}
    assert subtotal["current"] == {"D": 590, "R": 410}
    assert subtotal["margin_change_pp"] == 16
    assert subtotal["D_two_party_share_change_pp"] == 8
    assert congress.matched_district_subset(races, {"race-3", "race-4"}, 4) is None


@pytest.mark.parametrize("state,seat,name,party,status", [
    ("FL", "20", "Sheila Cherfilus-McCormick", "D", "elected_unopposed_no_reported_general_vote"),
    ("OK", "3", "Frank D. Lucas", "R", "decided_in_primary_no_general_contest"),
])
def test_official_no_general_vote_explains_hold_without_inventing_counts(tmp_path, state, seat, name, party, status):
    bodies = sources()
    bodies["house"] = [race(state=state, seat=seat), race(state=state, seat="1", identity="102")]
    source = collect(tmp_path, bodies)
    reviewed = review()
    district = f"{state}-{seat.zfill(2)}"
    template = reviewed["previous_district_queries"][0]
    previous = {**template["previous"], "reported_counts": dict.fromkeys("DRO", 0),
                "missing_major_party_counts": [name],
                "source_candidate_rows": [{"name": name, "group": party, "named": True, "votes": None}]}
    reviewed["previous_district_queries"] = [
        {**template, "district": f"{state}-01"}, {**template, "district": district, "previous": previous}]
    row = next(r for r in congress.comparisons(source, reviewed) if r["baseline"].get("district") == district)
    assert row["baseline"]["previous_no_general_vote"]["status"] == status
    assert row["previous"] is row["qualified_margin_change_pp"] is None
    assert not row["qualified_comparison"]
    state_row, = congress.house_state_comparisons(source, reviewed)
    assert not state_row["qualified_comparison"]
    assert any("no general" in hold for hold in state_row["comparison_holds"])
    previous["source_candidate_rows"][0]["name"] = "Different nominee"
    assert congress.historical_house_no_vote(district, previous) is None
