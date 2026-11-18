import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts import congressional_analytical_bridge as bridge
from scripts import congressional_complete_categories as categories
from scripts import official_house_precedence as precedence
from scripts.participation_intake.contract import encoded
from test_congressional_complete_categories import original, revision


ROOT = Path(__file__).resolve().parents[1]


def sources():
    if (ROOT / bridge.REVIEW_PATH).is_file():
        return ROOT
    return ROOT.parent / "inputs/reviewed-congressional-sources"


def fixture(delta=0):
    root = sources()
    analytical = bridge.load_review(root)
    evidence = json.loads(gzip.decompress((root / categories.DATA_PATHS[1]).read_bytes()))
    policy = precedence.prepare_review(analytical, evidence)
    analytical["official_house_precedence"] = policy
    expected = analytical["states"]["RI"]["expected_race_ids"]
    races = {key: {"status": "reported", "source": {"url": analytical["races"][key]["source_url"]},
                   "data": copy.deepcopy(analytical["races"][key]["accepted_native"])}
             for key in expected}
    old = {party: sum(row["votes"] for entry in races.values() for row in entry["data"]["candidates"]
                      if row["party_group"] == party) for party in "DRO"}
    model = {
        "state_code": "RI", "source_comparison_available": True,
        "reported_comparison": {
            "previous": analytical["states"]["RI"]["reviewed_previous_counts"],
            "current": old, "current_snapshot": "retained model",
        },
    }
    seed = {"congressional_analytical_review": analytical,
            "scenarios": {"original/accepted_ridge_multinomial": {"accepted_result": {"rows": [model]}}}}
    data = categories.parse(encoded(revision(original(), delta)))
    entry = {"status": "reported", "source": {"url": categories.URL}, "data": data,
             "first_observed_at": "2026-11-18T04:49:10.700627+00:00"}
    snapshot = {"congress": {"races": races, "official_candidate_evidence": {categories.IDENTITY: entry}}}
    handoff = {
        "review_version": analytical["version"],
        "races": {key: {"holds": ["official_category_Other_mass_differs"]} for key in expected},
        "states": {"RI": {
            "frozen_scientific_comparison_qualified": True,
            "automatic_update_eligible": False, "decision": "frozen_dated_result",
            "holds": ["official_category_Other_mass_differs"], "counts": None,
            "reviewed_comparability": copy.deepcopy(analytical["states"]["RI"]["reviewed_comparability"]),
            "last_good_model_counts": old,
        }},
    }
    return snapshot, seed, handoff


@pytest.mark.parametrize("delta", [7, -13, -6211])
def test_whole_official_revisions_preserve_provider_disagreement_and_minor_mass(delta):
    snapshot, seed, handoff = fixture(delta)
    before = copy.deepcopy((snapshot, seed, handoff))
    result = precedence.evaluate(snapshot, seed, handoff)
    row = result["states"]["RI"]
    data = snapshot["congress"]["official_candidate_evidence"][categories.IDENTITY]["data"]
    expected = {party: sum(candidate["votes"] for race in data["races"]
                           for candidate in race["candidates"] if candidate["party_group"] == party)
                for party in "DRO"}
    assert row["automatic_update_eligible"] and row["counts"] == expected
    assert row["counts"]["O"] == 6951 + delta
    assert row["source_urls"] == [categories.URL]
    assert row["source_update_labels"] == [data["source_updated_at"]]
    assert row["official_direct_source"] and row["official_source_clock_supplied"]
    assert row["national_provider_frames"]
    assert all(value["compatibility_holds"] == ["official_category_Other_mass_differs"]
               for value in row["national_provider_frames"].values())
    assert result["races"] == handoff["races"]
    assert result["official_house_precedence_last_good"]["RI"] == data
    assert (snapshot, seed, handoff) == before
    key = seed["congressional_analytical_review"]["states"]["RI"]["expected_race_ids"][0]
    assert categories.current_hold(snapshot["congress"], key,
                                   seed["congressional_analytical_review"]["races"][key],
                                   snapshot["congress"]["races"][key]["data"]) is not None


def test_selected_official_endpoint_clocks_and_review_reach_existing_model_annotations():
    snapshot, seed, handoff = fixture(7)
    result = precedence.evaluate(snapshot, seed, handoff)
    recorded = [copy.deepcopy(seed["scenarios"]["original/accepted_ridge_multinomial"][
        "accepted_result"]["rows"][0]["reported_comparison"])]
    decisions, endpoints = [{"state_code": "RI"}], {"RI": {}}
    bridge.apply_decisions(decisions, endpoints, recorded, result)
    assert endpoints["RI"]["counts"] == result["states"]["RI"]["counts"]
    assert not endpoints["RI"]["provider_bridge"]
    model = copy.deepcopy(seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"])
    model["rows"][0]["reported_comparison"] = recorded[0]
    model["rows"][0]["reported_comparison"]["reported_change_pp"] = recorded[0]["recorded_margin_change_pp"]
    bridge.annotate_result(model, result)
    comparison = model["rows"][0]["reported_comparison"]
    assert comparison["current"] == result["states"]["RI"]["counts"]
    assert comparison["current_native_clock"] == result["states"]["RI"]["source_update_labels"]
    assert precedence.VERSION in comparison["current_native_control_scope_qualification"]
    assert "NPR/AP endpoint" not in comparison["current_snapshot"]


@pytest.mark.parametrize("change", ["outage", "URL", "missing_clock", "future", "rollback",
                                   "candidate", "partial", "primary"])
def test_invalid_official_successors_hold_without_provider_fallback(change):
    snapshot, seed, handoff = fixture(7)
    first = precedence.evaluate(snapshot, seed, handoff)
    seed["official_house_precedence_last_good"] = first["official_house_precedence_last_good"]
    entry = snapshot["congress"]["official_candidate_evidence"][categories.IDENTITY]
    if change == "outage":
        entry["status"] = "retained_after_failure"
    elif change == "URL":
        entry["source"]["url"] = "https://example.test/unreviewed"
    elif change == "missing_clock":
        entry.pop("first_observed_at")
    elif change == "future":
        entry["first_observed_at"] = "2026-11-01T00:00:00Z"
    else:
        native = copy.deepcopy(entry["data"]["native_facts"])
        if change == "rollback":
            native["election"]["asOf"] = "2026-11-01T00:00:00Z"
            for race in native["ballotItems"]:
                race["reportingStatus"]["asOf"] = native["election"]["asOf"]
        elif change == "candidate":
            name = native["ballotItems"][0]["summaryResults"]["ballotOptions"][0]["name"][0]
            name["text"] = "Changed " + name["text"]
        elif change == "partial":
            native["ballotItems"][0]["reportingStatus"]["reportingUnits"] -= 1
        elif change == "primary":
            native["election"]["isPrimary"] = True
        entry["data"]["native_facts"] = native
        if change in ("rollback", "candidate"):
            entry["data"] = categories.parse(encoded(native))
    held = precedence.evaluate(snapshot, seed, first)
    row = held["states"]["RI"]
    assert not row["automatic_update_eligible"] and row["counts"] is None and row["holds"]
    assert row["last_good_model_counts"] == handoff["states"]["RI"]["last_good_model_counts"]
    assert held["official_house_precedence_last_good"] == seed["official_house_precedence_last_good"]
    assert not row["provider_fallback_on_official_failure_allowed"]


def test_unchanged_official_frame_is_deterministic_and_recovers_after_failure():
    snapshot, seed, handoff = fixture(7)
    first = precedence.evaluate(snapshot, seed, handoff)
    seed["official_house_precedence_last_good"] = first["official_house_precedence_last_good"]
    seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"]["rows"][0][
        "reported_comparison"]["current"] = first["states"]["RI"]["counts"]
    same = precedence.evaluate(snapshot, seed, handoff)
    assert same["states"]["RI"]["automatic_update_eligible"]
    assert not same["states"]["RI"]["changed"]
    assert same == precedence.evaluate(snapshot, seed, handoff)
    entry = snapshot["congress"]["official_candidate_evidence"][categories.IDENTITY]
    entry["status"] = "retained_after_failure"
    failed = precedence.evaluate(snapshot, seed, same)
    entry["status"] = "reported"
    assert precedence.evaluate(snapshot, seed, failed) == same
    seed["congressional_analytical_review"].pop("official_house_precedence")
    assert precedence.evaluate(snapshot, seed, handoff) is handoff


def test_review_reproduces_and_rejects_rechecksummed_policy_waivers(tmp_path):
    snapshot, seed, _ = fixture()
    analytical = seed["congressional_analytical_review"]
    expected = analytical["official_house_precedence"]
    target = tmp_path / precedence.REVIEW_PATH
    target.parent.mkdir(parents=True)
    evidence_target = tmp_path / categories.DATA_PATHS[1]
    evidence_target.parent.mkdir(parents=True)
    evidence_target.write_bytes((sources() / categories.DATA_PATHS[1]).read_bytes())
    target.write_bytes(encoded(expected))
    assert precedence.load_review(tmp_path, analytical) == expected
    changed = copy.deepcopy(expected)
    changed["new_scientific_eligibility_allowed"] = True
    target.write_bytes(encoded(changed))
    with pytest.raises(ValueError, match="does not reproduce"):
        precedence.load_review(tmp_path, analytical)
    altered = copy.deepcopy(analytical)
    altered["states"]["RI"]["holds"] = ["substantive_scientific_hold"]
    with pytest.raises(ValueError, match="scientific"):
        precedence.prepare_review(altered, json.loads(gzip.decompress(evidence_target.read_bytes())))


def test_official_endpoint_does_not_overwrite_the_separate_national_candidate_seed():
    from scripts import automatic_estimates as estimates

    snapshot, _, handoff = fixture(7)
    _, policy_seed, _ = fixture(7)
    result = precedence.evaluate(snapshot, policy_seed, handoff)
    seed_root = sources() / "data/results-intake/model-seed"
    if not seed_root.is_dir():
        seed_root = ROOT.parent / "inputs/model-seed"
    if (seed_root / "manifest.json").is_file():
        seed = estimates.load_seed(seed_root)
    else:
        seed = estimates.load_rolling_seed_bytes(
            (seed_root / "rolling-seed.json.gz").read_bytes(),
            json.loads((seed_root / "rolling-seed-descriptor.json").read_bytes()))
    artifacts = {
        "house/viewer-" + profile + ".json.gz": {"content": viewer}
        for profile, viewer in seed["profile_viewers"].items()
    }
    artifacts.update({
        "house/" + key + "/complete-result.json.gz": {"content": scenario["accepted_result"]}
        for key, scenario in seed["scenarios"].items()
    })
    recorded = [copy.deepcopy(policy_seed["scenarios"]["original/accepted_ridge_multinomial"][
        "accepted_result"]["rows"][0]["reported_comparison"])]
    decisions, endpoints = [{"state_code": "RI"}], {"RI": {}}
    bridge.apply_decisions(decisions, endpoints, recorded, result)
    artifacts["house/recorded-states.json.gz"] = {"content": {
        "states": [{"state_code": "RI", "current": result["states"]["RI"]["counts"]}]}}
    advanced = estimates._advanced_seed(
        snapshot, seed, decisions, artifacts, seed["participation_state_controls"])
    assert advanced["accepted_candidates"] == seed["accepted_candidates"]
    assert advanced["accepted_controls"] == seed["accepted_controls"]


def test_official_precedence_does_not_activate_undeployed_split_geometry_reader():
    from scripts import automatic_runtime as runtime

    root = sources()
    legacy = runtime.analytical_policy(root)
    successor = runtime.analytical_policy(root, split_block_geometry=True)
    assert legacy["official_house_precedence"] == successor["official_house_precedence"]
    for district in ("CO-07", "CO-08"):
        assert legacy["house_boundaries"]["decisions"][district]["holds"] == [
            "split_block_geometry_unresolved"]
        assert successor["house_boundaries"]["decisions"][district]["boundary_compatible"]
    assert "split_geometry_review" not in legacy["house_boundaries"]
    assert "split_geometry_review" in successor["house_boundaries"]

