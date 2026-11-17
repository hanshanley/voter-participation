import copy

import pytest

from scripts import congressional_analytical_bridge as bridge
from scripts import results_congress as congress
from test_results_congress import race, review


def fixture():
    native = race(state="AR")
    native["candidates"][-1]["votes"] = 7
    data = congress.normalize(native, "house")
    key = data["id"]
    snapshot = {
        "congress": {"contract": congress.CONTRACT, "election_date": congress.ELECTION,
                     "races": {key: {
                         "status": "reported", "advertised": True, "freshness": "source_verified",
                         "data": data, "source": {"url": "https://example.test/house"},
                     }}},
    }
    candidates = [
        {"state_code": "AR", "district": "AR-AL", "name": name, "party": party,
         "year": 2026, "votes": str(votes)}
        for name, party, votes in (
            ("D Candidate", "Democratic", 100), ("R Candidate", "Republican", 90),
            ("Minor Candidate", "Libertarian", 7))
    ]
    previous = {"D": 110, "R": 90, "O": 0}
    result = {"rows": [{
        "state_code": "AR", "source_comparison_available": True,
        "reported_comparison": {
            "previous": previous, "current": {"D": 100, "R": 90, "O": 7},
            "current_snapshot": "dated-science", "current_native_clock": ["original-clock"],
        },
        "source_aggregate_comparison": {"current_snapshot": "dated-science"},
        "point": {"switching": 1.25},
    }]}
    seed = {"accepted_candidates": candidates, "qualification": {"frozen": "mask"},
            "scenarios": {"original/accepted_ridge_multinomial": {"accepted_result": result}}}
    scientific = review()
    scientific["previous_district_queries"][0].update(district="AR-AL")
    policy = bridge.prepare_review(snapshot["congress"], seed, scientific, {"datasets": []})
    seed["congressional_analytical_review"] = policy
    return snapshot, seed, key


def revise(snapshot, key, votes=101, **changes):
    entry = snapshot["congress"]["races"][key]
    native = copy.deepcopy(entry["data"]["native_facts"])
    native["updated"] += 1
    native["candidates"][0]["votes"] = votes
    native.update(changes)
    entry["data"] = congress.normalize(native, "house")
    return native


@pytest.mark.parametrize("votes", [101, 83, 0])
def test_stable_ids_accept_increases_decreases_and_literal_zero(votes):
    snapshot, seed, key = fixture()
    # Keep a positive statewide D endpoint while testing a genuine zero candidate.
    native = revise(snapshot, key, votes)
    if votes == 0:
        native["candidates"][1]["votes"] = 0
        snapshot["congress"]["races"][key]["data"] = congress.normalize(native, "house")
    result = bridge.evaluate(snapshot, seed)
    assert result["races"][key]["compatible"]
    assert result["last_good"][key]["candidates"][0]["votes"] == votes
    assert result["states"]["AR"]["automatic_update_eligible"] is (votes != 0)
    assert seed["accepted_candidates"][-1]["votes"] == "7"
    crosswalk = result["candidate_crosswalk"]
    assert crosswalk[-1]["legacy"]["name"] == "Minor Candidate"
    assert crosswalk[-1]["provider_candidate_id"] is None
    assert not crosswalk[-1]["individual_count_allocated_from_Other"]


@pytest.mark.parametrize("change", ["rollback", "same_clock", "missing", "unknown", "party",
                                   "identity", "stage", "source", "not_fresh", "not_advertised"])
def test_incompatible_updates_hold_only_the_analytical_frame(change):
    snapshot, seed, key = fixture()
    original = copy.deepcopy(snapshot["congress"]["races"][key]["data"])
    native = revise(snapshot, key)
    entry = snapshot["congress"]["races"][key]
    if change == "rollback":
        native["updated"] -= 2
    elif change == "same_clock":
        native["updated"] -= 1
    elif change == "missing":
        native["candidates"].pop()
    elif change == "unknown":
        native["candidates"][0]["votes"] = None
    elif change == "party":
        native["candidates"][0]["party"] = "Ind"
    elif change == "identity":
        native["candidates"][0]["last"] = "Different"
    elif change == "stage":
        native["type"] = "General Runoff"
    elif change == "source":
        entry["source"]["url"] = "https://different.test/house"
    elif change == "not_fresh":
        entry["status"] = "retained_after_failure"
    else:
        entry["advertised"] = False
    entry["data"] = congress.normalize(native, "house")
    seed["congressional_analytical_last_good"] = {key: original}
    result = bridge.evaluate(snapshot, seed)
    assert not result["states"]["AR"]["automatic_update_eligible"]
    assert result["states"]["AR"]["last_good_model_counts"] == {"D": 100, "R": 90, "O": 7}
    assert result["last_good"][key] == original
    assert result["states"]["AR"]["recorded_results_available_separately"]


def test_missing_other_mass_is_inspectable_not_silently_discarded():
    snapshot, seed, key = fixture()
    next(candidate for candidate in snapshot["congress"]["races"][key]["data"]["candidates"]
         if candidate["role"] == "provider_aggregate_other")["votes"] = 3
    policy = bridge.prepare_review(snapshot["congress"], seed, {
        **review(), "previous_district_queries": [
            {**review()["previous_district_queries"][0], "district": "AR-AL"}]}, {"datasets": []})
    assert not policy["states"]["AR"]["automatic_update_reviewed"]
    assert policy["legacy_candidates_preserved"][-1]["votes"] == "7"
    assert "aggregate_other_not_reconciled" in ";".join(policy["states"]["AR"]["holds"])


def test_new_race_is_published_but_cannot_grant_scientific_eligibility():
    snapshot, seed, key = fixture()
    added = congress.normalize(race(state="AR", seat="2", identity="new"), "house")
    snapshot["congress"]["races"][added["id"]] = {
        **copy.deepcopy(snapshot["congress"]["races"][key]), "data": added}
    result = bridge.evaluate(snapshot, seed)
    assert not result["states"]["AR"]["automatic_update_eligible"]
    assert result["races"][added["id"]]["holds"] == [
        "new_provider_identity_requires_reviewed_scientific_successor"]


def test_qualified_current_frame_keeps_a_versioned_comparability_audit():
    snapshot, seed, key = fixture()
    handoff = bridge.evaluate(snapshot, seed)
    result = copy.deepcopy(seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"])
    result["rows"][0]["contest_comparability"] = {
        "state_code": "AR", "previous_counts": {"D": 110, "R": 90, "O": 0},
        "current_counts": {"D": 100, "R": 90, "O": 7},
    }
    bridge.annotate_result(result, handoff)
    row = result["rows"][0]
    assert row["congressional_analytical_status"]["conditioned_on_fresh_returns"]
    assert row["source_aggregate_comparison"] == row["reported_comparison"]


@pytest.mark.parametrize("votes", [101, 83])
def test_fresh_comparison_diagnostics_follow_increases_and_downward_corrections(votes):
    snapshot, seed, key = fixture()
    audit = {
        "state_code": "AR", "previous_counts": {"D": 110, "R": 90, "O": 0},
        "current_counts": {"D": 100, "R": 90, "O": 7},
        "common_reported_DR_district_ids": ["AR-AL"],
        "common_source_id_previous_counts": {"D": 110, "R": 90, "O": 0},
        "common_source_id_current_counts": {"D": 100, "R": 90, "O": 7},
        "common_source_id_margin_change_pp": -1,
        "raw_reported_aggregate_margin_change_pp": -1,
        "aggregate_minus_common_source_id_change_pp": 0,
        "common_source_id_boundary_stability_qualified": False,
    }
    seed["congressional_analytical_review"]["states"]["AR"]["reviewed_comparability"] = audit
    before = copy.deepcopy(audit)
    revise(snapshot, key, votes)
    handoff = bridge.evaluate(snapshot, seed)
    result = copy.deepcopy(seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"])
    change = 100 * (votes - 90) / (votes + 90) - 10
    result["rows"][0]["reported_comparison"].update(
        current={"D": votes, "R": 90, "O": 7}, reported_change_pp=change,
        contest_comparability=copy.deepcopy(audit))
    bridge.annotate_result(result, handoff)
    row = result["rows"][0]
    current = row["contest_comparability"]
    assert current["current_counts"] == {"D": votes, "R": 90, "O": 7}
    assert current["common_source_id_current_counts"] == current["current_counts"]
    assert current["raw_reported_aggregate_margin_change_pp"] == pytest.approx(change)
    assert current["common_source_id_margin_change_pp"] == pytest.approx(change)
    assert current["aggregate_minus_common_source_id_change_pp"] == pytest.approx(0)
    assert current["common_source_id_boundary_stability_qualified"] is False
    assert row["reported_comparison"]["contest_comparability"] == current
    assert row["source_aggregate_comparison"]["contest_comparability"] == current
    assert row["reported_comparison"]["current_stage"] == "general"
    assert row["reported_comparison"]["current_round"] == "not_ranked"
    assert audit == before


def test_frozen_labels_preserve_original_clocks_numerics_and_do_not_accumulate():
    snapshot, seed, key = fixture()
    snapshot["congress"]["races"][key]["status"] = "retained_after_failure"
    handoff = bridge.evaluate(snapshot, seed)
    result = copy.deepcopy(seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"])
    bridge.annotate_result(result, handoff)
    row = result["rows"][0]
    assert row["point"] == {"switching": 1.25}
    assert row["reported_comparison"]["current_native_clock"] == ["original-clock"]
    assert row["source_aggregate_comparison"]["current_snapshot"] == "FROZEN ANALYTICAL RESULT: dated-science"
    first = copy.deepcopy(result)
    assert bridge.annotate_result(result, handoff) == first


def test_display_labels_wrap_without_losing_source_identity_or_hold_codes():
    snapshot, seed, key = fixture()
    result = copy.deepcopy(seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"])
    handoff = bridge.evaluate(snapshot, seed)
    bridge.annotate_result(result, handoff)
    comparison = result["rows"][0]["reported_comparison"]
    assert len(comparison["current_snapshot_identity"].split()[-1]) == 64
    assert max(map(len, comparison["current_snapshot"].split())) <= 12

    identity = "native-query:" + "a" * 64
    row = result["rows"][0]
    row["congressional_analytical_status"]["last_good_snapshot"] = identity
    handoff["states"]["AR"].update(
        automatic_update_eligible=False, decision="frozen_dated_result",
        holds=[key + ":aggregate_other_not_reconciled"])
    bridge.annotate_result(result, handoff)
    assert row["point"] == {"switching": 1.25}
    assert row["congressional_analytical_status"]["last_good_snapshot"] == identity
    assert row["reported_comparison"]["current_snapshot_identity"] == identity
    assert row["congressional_analytical_status"]["holds"] == [
        key + ":aggregate_other_not_reconciled"]
    assert max(map(len, row["reported_comparison"][
        "current_native_control_scope_qualification"].split())) < 40
    assert identity not in row["reported_comparison"]["current_snapshot"]
    first = copy.deepcopy(result)
    assert bridge.annotate_result(result, handoff) == first


def test_unchanged_reviewed_inputs_are_exact_and_source_frames_cannot_change():
    snapshot, seed, key = fixture()
    first = bridge.evaluate(snapshot, seed)
    seed["congressional_analytical_last_good"] = first["last_good"]
    assert bridge.evaluate(snapshot, seed) == first
    seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"][
        "rows"][0]["reported_comparison"]["previous"]["D"] += 1
    result = bridge.evaluate(snapshot, seed)
    assert "reviewed_historical_model_endpoint_changed" in result["states"]["AR"]["holds"]


def test_missing_native_identity_is_a_hold_not_a_batch_abort():
    snapshot, seed, key = fixture()
    del snapshot["congress"]["races"][key]["data"]["native_facts"]["candidates"][0]["id"]
    result = bridge.evaluate(snapshot, seed)
    assert not result["states"]["AR"]["automatic_update_eligible"]
