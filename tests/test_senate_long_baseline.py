from pathlib import Path

from scripts import senate_long_baseline as old


ROOT = Path(__file__).resolve().parents[1]


def test_archived_candidates_reconcile_and_louisiana_uses_only_decisive_runoff():
    frames = old.load_review(ROOT)["historical_frames"]
    assert frames["AR"]["candidate_votes"] == 847505
    assert len(frames["AR"]["candidates"]) == 5
    assert frames["LA"]["candidate_votes"] == 1273589
    assert {row["votes"] for row in frames["LA"]["candidates"]} == {712379, 561210}


def test_older_same_seat_comparison_never_replaces_primary_baseline():
    review = old.load_review(ROOT)
    row = {"id": "npr:senate:AR:2:regular:general:not_ranked", "state_code": "AR",
           "advertised": True, "qualified_comparison": False, "status": "reported",
           "ranked_choice": False, "native_runoff": None, "count_coverage_complete": True,
           "D": 377108, "R": 481495, "O": 29539, "U": 0, "stage": "general",
           "election_date": "2026-11-03"}
    candidates = [{"id": row["id"], "party_group": p, "role": "named_candidate"} for p in "DR"]
    comparison, = old.comparisons([row], candidates, review)
    assert comparison["margin_change_pp"] is not None
    assert not comparison["replaces_last_cycle"] and not row["qualified_comparison"]
    assert old.comparisons([dict(row, qualified_comparison=True)], candidates, review) == []
    assert old.comparisons([row], candidates[:1], review)[0]["margin_change_pp"] is None
    assert old.comparisons([dict(row, status="retained_after_failure")], candidates, review)[0]["margin_change_pp"] is None
