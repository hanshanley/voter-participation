import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts import congressional_analytical_bridge as bridge
from scripts import congressional_candidate_identity as identity
from scripts import congressional_reference_identity as reference


ROOT = Path(__file__).resolve().parents[1]


def sources():
    return ROOT if (ROOT / bridge.REVIEW_PATH).is_file() else (
        ROOT.parent / "inputs/reviewed-congressional-sources")


def inputs():
    root = sources()
    previous = json.loads(gzip.decompress((root / bridge.REVIEW_PATH).read_bytes()))
    value = json.loads(gzip.decompress((root / reference.DATA_PATHS[1]).read_bytes()))
    fec = json.loads(gzip.decompress((root / identity.DATA_PATHS[1]).read_bytes()))
    return previous, value, fec


def test_actual_chain_resolves_only_one_identity_preserving_all_count_and_scientific_evidence():
    previous, value, fec = inputs()
    saved = copy.deepcopy((previous, value, fec))
    result = reference.successor(previous, value, fec, {})
    assert (previous, value, fec) == saved
    assert result["version"] == previous["version"]
    assert result["states"]["PA"]["automatic_update_reviewed"]
    assert not result["states"]["PA"]["holds"]
    changed = result["explicit_reference_names"]["resolved_identities"]
    assert len(changed) == 1 and changed[0]["race_id"] == (
        "npr:house:PA:5:regular:general:not_ranked")
    assert result["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
    for key, race in previous["races"].items():
        assert result["races"][key]["accepted_native"] == race["accepted_native"]
    for state, decision in previous["states"].items():
        if state != "PA":
            assert result["states"][state] == decision
    for field in ("frozen_scientific_comparison_qualified", "initial_recorded_comparison_qualified",
                  "reviewed_previous_counts", "reviewed_comparability"):
        assert result["states"]["PA"][field] == previous["states"]["PA"][field]


@pytest.mark.parametrize("change", ["candidate_id", "state", "district", "party", "election",
                                   "not_same_cell", "not_literal_quoted_name", "wrong_formal_name",
                                   "primary_seat", "missing_filing", "vote_count", "duplicate"])
def test_unqualified_reference_or_filing_evidence_cannot_create_aliases(change):
    _, value, fec = inputs()
    facts = value["sources"][0]["facts"]
    if change == "candidate_id":
        facts["fec_candidate_id"] = "H8PA07200"
    elif change == "state":
        facts["state_code"] = "NJ"
    elif change == "district":
        facts["district"] = "06"
    elif change == "party":
        facts["literal_party"] = "Democratic"
    elif change == "election":
        facts["election_date"] = "2024-11-05"
    elif change == "not_same_cell":
        facts["same_native_candidate_cell"] = False
    elif change == "not_literal_quoted_name":
        facts["candidate_label"] = "Nicholas Waln Morris Nick Manganaro"
    elif change == "wrong_formal_name":
        facts["candidate_label"] = 'Nicholas William Morris "Nick" Manganaro'
    elif change == "primary_seat":
        value["sources"][1]["facts"]["role_heading"] = "Candidate for US Congress, PA 6th District"
    elif change == "missing_filing":
        value["authorized_filings"]["filings"] = []
    elif change == "vote_count":
        facts["votes"] = 1
    else:
        value["declarations"].append(copy.deepcopy(value["declarations"][0]))
    with pytest.raises(ValueError):
        reference.ReferenceEvidence(fec, value)


def test_nickname_rule_remains_literal_and_ambiguous_FEC_frames_stay_unresolved():
    previous, value, fec = inputs()
    key = "npr:house:PA:5:regular:general:not_ranked"
    race = previous["races"][key]
    old = previous["legacy_candidates_preserved"][race["unmatched_legacy_indices"][0]]
    current = next(row for row in race["accepted_native"]["candidates"]
                   if row["candidate_id"] not in race["named_crosswalk"])
    evidence = reference.ReferenceEvidence(fec, value)
    assert evidence.resolve(old, current, race) is not None
    candidate = evidence.candidates["H6PA05216"]
    assert evidence.support("Nicky Manganaro", candidate) is None
    duplicate = copy.deepcopy(candidate)
    duplicate["candidate_id"] = "H6PA05999"
    fec["candidates"].append(duplicate)
    assert reference.ReferenceEvidence(fec, value).resolve(old, current, race) is None
    for field, replacement in (("stage", "primary"), ("election_kind", "special"),
                               ("ranked_choice", True)):
        changed = copy.deepcopy(race)
        changed["identity"][field] = replacement
        assert evidence.resolve(old, current, changed) is None


def test_literal_identity_cannot_erase_an_independent_Other_mass_hold():
    previous, value, fec = inputs()
    key = "npr:house:PA:5:regular:general:not_ranked"
    hold = "unmatched_or_changed_Other_source_universe"
    previous["races"][key]["initial_holds"].append(hold)
    previous["states"]["PA"]["holds"].append(key + ":" + hold)
    result = reference.successor(previous, value, fec, {})
    assert result["states"]["PA"]["holds"] == [key + ":" + hold]
    assert not result["states"]["PA"]["automatic_update_reviewed"]


def test_optional_policy_and_complete_evidence_roundtrip_through_actual_loader():
    root = sources()
    loaded = bridge.load_review(root, include_split_geometry=False)
    policy = json.loads((root / reference.REVIEW_PATH).read_bytes())
    assert loaded["explicit_reference_names"] == policy
    assert loaded["states"]["PA"]["automatic_update_reviewed"]
    assert loaded["official_house_precedence"]["states"]["RI"]
    assert set(reference.DATA_PATHS) <= set(bridge.data_paths(loaded))
