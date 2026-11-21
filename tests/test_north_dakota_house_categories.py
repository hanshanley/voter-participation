import copy

import pytest

from scripts import north_dakota_house_categories as nd


def test_official_slate_matches_current_counts_without_allocating_provider_other():
    frame = {"state_code": "ND", "chamber": "house", "seat": "1", "stage": "general",
             "election_date": nd.DATE, "election_kind": "regular"}
    official = [
        {"candidate_id": key, "name": name, "party_group": party, "votes": count,
         "role": "generic_write_in" if key == "9901" else "named_candidate"}
        for key, name, party, count in (
            ("37665", "Julie Fedorchak", "R", 134636), ("37763", "Trygve Hammer", "D", 86088),
            ("37935", "Charles Tuttle", "O", 9294), ("37939", "Helene Neville", "O", 4610),
            ("9901", "write-in", "O", 342),
        )
    ]
    provider = {"candidates": [*copy.deepcopy(official[:2]),
                               {"role": "provider_aggregate_other", "party_group": "O", "votes": 14246}]}
    reviewed = {"identity": frame, "named_crosswalk": {"37665": 3, "37763": 4},
                "unmatched_legacy_indices": [0, 1, 2]}
    review = {"legacy_candidates_preserved": [
        {"name": "Charles Tuttle", "party": "Independent"},
        {"name": "Helene Neville", "party": "Independent"},
        {"name": "Write-in", "party": "Nonpartisan"},
    ]}
    entry = {"status": "reported", "source": {"url": nd.URL},
             "data": {"races": [{**frame, "native_contest_id": "22055", "complete_reporting": True,
                                 "contest_total": 234970, "candidates": official}],
                      "metadata_source": {"url": nd.nd.ELECTION_URL}, "source_updated_at": "2026-11-18T00:00:00Z"}}
    congress = {"official_candidate_evidence": {nd.IDENTITY: entry}}
    proof = nd.reconcile(congress, review, reviewed, provider)
    assert [row["votes"] for row in proof["official_omitted_candidates"]] == [9294, 4610, 342]
    assert proof["individual_counts_allocated_from_Other"] is False
    for delta in (-1, 1):
        edited = copy.deepcopy(provider)
        edited["candidates"][-1]["votes"] += delta
        with pytest.raises(ValueError, match="Other"):
            nd.reconcile(congress, review, reviewed, edited)
    entry["status"] = "retained_after_failure"
    with pytest.raises(ValueError, match="freshly verified"):
        nd.reconcile(congress, review, reviewed, provider)
