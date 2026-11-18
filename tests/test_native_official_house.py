import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts import congressional_analytical_bridge as bridge
from scripts import native_official_house as policy
from scripts import results_native_congress as native
from scripts.participation_intake.contract import encoded


ROOT = Path(__file__).resolve().parents[1]


def sources():
    return ROOT if (ROOT / bridge.REVIEW_PATH).is_file() else (
        ROOT.parent / "inputs/reviewed-congressional-sources")


def inputs():
    review = bridge.load_review(sources())
    facts = json.loads((ROOT / "tests/fixtures/virginia-federal-candidates.json").read_bytes())
    fec = json.loads(gzip.decompress((sources() /
        "data/results-intake/analytical-handoff/fec-identity/evidence.json.gz").read_bytes()))
    return review, facts, fec


def fixture(delta=0):
    review, facts, fec = inputs()
    value = policy.prepare_review(review, facts, fec)
    value["accepted_native"] = native.normalized(facts)
    review["native_official_house"] = value
    race = facts["root"]["ballotItems"][0]
    candidate = race["summaryResults"]["ballotOptions"][0]
    candidate["voteCount"] += delta
    candidate["groupResults"][0]["voteCount"] += delta
    race["voteTotal"] += delta
    piece = next(p for doc in facts["localities"].values() for p in doc["ballotItems"]
                 if p["parentId"] == race["id"])
    row = next(c for c in piece["summaryResults"]["ballotOptions"]
               if c["nativeId"] == candidate["nativeId"])
    row["voteCount"] += delta
    row["groupResults"][0]["voteCount"] += delta
    piece["voteTotal"] += delta
    data = native.normalized(facts)
    model = {"state_code": "VA", "source_comparison_available": True, "reported_comparison": {
        "previous": review["states"]["VA"]["reviewed_previous_counts"],
        "current": {"D": 2105772, "R": 1422580, "O": 58819}}}
    seed = {"congressional_analytical_review": review, "scenarios": {
        "original/accepted_ridge_multinomial": {"accepted_result": {"rows": [model]}}}}
    entry = {"status": "reported", "source": copy.deepcopy(facts["numerical_input_manifest"]["root"]),
             "data": data, "first_observed_at": "2026-11-18T23:00:00+00:00"}
    snapshot = {"congress": {"official_candidate_evidence": {native.IDENTITY: entry}, "races": {}}}
    handoff = {
        "states": {"VA": {"frozen_scientific_comparison_qualified": True,
                          "automatic_update_eligible": False, "holds": review["states"]["VA"]["holds"]},
                   "RI": {"preserved": True}},
        "races": {key: {"holds": review["races"][key]["initial_holds"]}
                  for key in review["states"]["VA"]["expected_race_ids"]}}
    return snapshot, seed, handoff


def test_complete_literal_universe_and_five_stable_fec_identity_chains():
    review, facts, fec = inputs()
    before = copy.deepcopy((review, facts, fec))
    result = policy.prepare_review(review, facts, fec)
    rows = result["candidate_crosswalk"]
    assert len(rows) == len({row["legacy_index"] for row in rows}) == 47
    assert sum(row["official_role"] == "generic_write_in" for row in rows) == 11
    mapped = {row["legacy_literal_name"]: row for row in rows if "fec_candidate" in row["evidence"]}
    assert set(mapped) == {"Edwin Rivera", "Robert Murray", "John McGuire", "Don Beyer", "Morgan Griffith"}
    for row in mapped.values():
        assert not row["evidence"]["FEC_establishes_ballot_presence_or_vote_counts"]
    assert mapped["Don Beyer"]["evidence"]["legacy_support"]["method"] == "authorized_committee_literal_full_name"
    assert mapped["Morgan Griffith"]["evidence"]["legacy_support"]["method"] == "authorized_committee_literal_full_name"
    assert not result["individual_count_allocation_from_Other_allowed"]
    assert not result["new_scientific_eligibility_allowed"] and not result["respondent_refitting_allowed"]
    assert (review, facts, fec) == before


@pytest.mark.parametrize("name,accepted", [
    ("John J. McGuire III", True), ("John McGuire", True),
    ("John J. McGuire, Jr.", False), ("John Q. McGuire III", False),
    ("J. McGuire III", False), ("Jonathan McGuire III", False),
    ("John J. McGuire Smith III", False),
])
def test_formal_fec_names_do_not_guess_nicknames_initials_or_conflicting_suffixes(name, accepted):
    candidate = {"name": "MCGUIRE, JOHN J. MR. III"}
    assert bool(policy.formal_support(name, candidate)) == accepted


@pytest.mark.parametrize("change", ["new_candidate", "wrong_party", "scientific", "stage",
                                   "historical", "ambiguous_fec", "independent_hold"])
def test_resealed_incompatible_reviews_cannot_waive_identity_or_scientific_guards(change):
    review, facts, fec = inputs()
    if change == "new_candidate":
        review["legacy_candidates_preserved"][1283]["name"] = "Different Person"
    elif change == "wrong_party":
        review["legacy_candidates_preserved"][1287]["party"] = "Libertarian"
    elif change == "scientific":
        review["states"]["VA"]["frozen_scientific_comparison_qualified"] = False
    elif change == "stage":
        review["races"][review["states"]["VA"]["expected_race_ids"][0]]["identity"]["stage"] = "primary"
    elif change == "historical":
        review["states"]["VA"]["initial_recorded_comparison_qualified"] = False
    elif change == "independent_hold":
        review["states"]["VA"]["holds"].append("different_scientific_problem")
    else:
        candidate = copy.deepcopy(next(row for row in fec["candidates"]
                                      if row["candidate_id"] == "H6VA03121"))
        candidate["candidate_id"] = "H6VA03999"
        fec["candidates"].append(candidate)
    with pytest.raises(ValueError):
        policy.prepare_review(review, facts, fec)


@pytest.mark.parametrize("delta", [0, 7, -13])
def test_whole_official_endpoints_without_provider_mixing(delta):
    snapshot, seed, handoff = fixture(delta)
    before = copy.deepcopy((snapshot, seed, handoff))
    result = policy.evaluate(snapshot, seed, handoff)
    row = result["states"]["VA"]
    data = snapshot["congress"]["official_candidate_evidence"][native.IDENTITY]["data"]
    assert row["counts"] == {p: sum(c["votes"] for r in data["races"] for c in r["candidates"]
                                    if c["party_group"] == p) for p in "DRO"}
    assert row["automatic_update_eligible"] and row["counts"]["O"] == 61053
    assert row["official_direct_source"] and len(row["current_district_counts"]) == 11
    assert result["races"] == handoff["races"] and result["states"]["RI"] == handoff["states"]["RI"]
    assert result["native_official_house_last_good"]["VA"] == data
    assert (snapshot, seed, handoff) == before


@pytest.mark.parametrize("change", ["outage", "URL", "local_rollback", "future", "name", "receipt"])
def test_own_last_good_retention_no_provider_fallback_and_recovery(change):
    snapshot, seed, handoff = fixture(7)
    first = policy.evaluate(snapshot, seed, handoff)
    seed["native_official_house_last_good"] = first["native_official_house_last_good"]
    seed["scenarios"]["original/accepted_ridge_multinomial"]["accepted_result"]["rows"][0][
        "reported_comparison"]["current"] = first["states"]["VA"]["counts"]
    stable = policy.evaluate(snapshot, seed, handoff)
    assert not stable["states"]["VA"]["changed"]
    assert policy.evaluate(snapshot, seed, handoff) == stable
    entry = snapshot["congress"]["official_candidate_evidence"][native.IDENTITY]
    before = copy.deepcopy(entry)
    if change == "outage":
        entry["status"] = "retained_after_failure"
    elif change == "URL":
        entry["source"]["url"] = "https://example.test/unreviewed"
    elif change == "future":
        entry["first_observed_at"] = "2026-11-03T00:00:00Z"
    elif change == "receipt":
        entry["source"]["sha256"] = "0" * 64
    else:
        facts = copy.deepcopy(entry["data"]["native_facts"])
        piece = next(r for doc in facts["localities"].values() for r in doc["ballotItems"])
        if change == "local_rollback":
            piece["reportingStatus"]["asOf"] = "2026-11-03T00:00:00Z"
            entry["data"] = native.normalized(facts)
        else:
            piece["summaryResults"]["ballotOptions"][0]["name"][0]["text"] = "Different Candidate"
            entry["data"]["native_facts"] = facts
    held = policy.evaluate(snapshot, seed, stable)
    assert not held["states"]["VA"]["automatic_update_eligible"]
    assert held["states"]["VA"]["counts"] is None and held["states"]["VA"]["holds"]
    assert held["native_official_house_last_good"] == seed["native_official_house_last_good"]
    assert not held["states"]["VA"]["provider_fallback_on_official_failure_allowed"]
    snapshot["congress"]["official_candidate_evidence"][native.IDENTITY] = before
    assert policy.evaluate(snapshot, seed, held) == stable


def test_prepared_review_and_full_evidence_reproduce_from_packaged_sources(tmp_path):
    review, facts, fec = inputs()
    value = policy.prepare_review(review, facts, fec)
    from scripts.congressional_candidate_identity import DATA_PATHS as FEC_PATHS
    for name, body in ((policy.REVIEW_PATH, encoded(value)),
                       (policy.FACTS_PATH, bridge.compressed(facts)),
                       (FEC_PATHS[1], bridge.compressed(fec))):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    loaded = policy.load_review(tmp_path, review)
    assert loaded["candidate_crosswalk"] == value["candidate_crosswalk"]
    loaded.pop("accepted_native")
    assert loaded == value
    value["respondent_refitting_allowed"] = True
    (tmp_path / policy.REVIEW_PATH).write_bytes(encoded(value))
    with pytest.raises(ValueError, match="does not reproduce"):
        policy.load_review(tmp_path, review)
