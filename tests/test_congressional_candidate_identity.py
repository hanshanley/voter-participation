import copy
import gzip
import json

import pytest

from scripts import congressional_analytical_bridge as bridge
from scripts import congressional_candidate_identity as identity
from test_congressional_analytical_bridge import fixture
from scripts.participation_intake.contract import encoded, pin


def evidence():
    return {
        "contract": identity.CONTRACT,
        "sources": [],
        "candidates": [{
            "candidate_id": "H6AR00001", "name": "DOE, JOSEPH 'JOE'", "literal_party": "DEM",
            "election_year": "2026", "office_state": "AR", "office": "H", "district": "00",
            "incumbent_challenger": "C", "candidate_status": "C",
        }],
        "committees": [{
            "committee_id": "C00000001", "name": "JOEY DOE FOR CONGRESS", "designation": "P",
            "committee_type": "H", "literal_party": "DEM", "candidate_id": "H6AR00001",
        }],
        "linkages": [{
            "candidate_id": "H6AR00001", "candidate_election_year": "2026",
            "fec_election_year": "2026", "committee_id": "C00000001",
            "committee_type": "H", "designation": "P", "linkage_id": "10001",
        }],
    }


def candidates():
    old = {"state_code": "AR", "district": "AR-AL", "name": "Joe Doe",
           "party": "Democratic", "year": "2026"}
    current = {"candidate_id": "provider-123", "name": "Joseph Doe",
               "party_group": "D", "role": "named_candidate"}
    race = {"district": "AR-AL", "identity": {
        "chamber": "house", "election_date": "2026-11-03", "election_kind": "regular",
        "stage": "general", "ranked_choice": False, "state_code": "AR",
    }}
    return old, current, race


@pytest.mark.parametrize("legacy,method", [
    ("Joe Doe", "explicit_FEC_quoted_given_name_and_full_surname"),
    ("Joey Doe", "authorized_committee_literal_full_name"),
    ("Joseph Doe", "literal_FEC_given_prefix_and_full_surname"),
])
def test_native_aliases_require_the_same_unique_stable_fec_identity(legacy, method):
    old, current, race = candidates()
    old["name"] = legacy
    result = identity.Evidence(evidence()).resolve(old, current, race)
    assert result["fec_candidate"]["candidate_id"] == "H6AR00001"
    assert result["legacy_support"]["method"] == method
    assert result["ballot_stage_and_counts_qualified_by_FEC"] is False


@pytest.mark.parametrize("field,value", [
    ("office_state", "CA"), ("district", "01"), ("office", "S"),
    ("election_year", "2024"), ("literal_party", "REP"),
])
def test_wrong_fec_frame_never_resolves(field, value):
    source = evidence()
    source["candidates"][0][field] = value
    assert identity.Evidence(source).resolve(*candidates()) is None


@pytest.mark.parametrize("field,value", [
    ("state_code", "CA"), ("election_kind", "special"), ("chamber", "senate"),
    ("election_date", "2026-12-01"), ("stage", "runoff"), ("ranked_choice", True),
])
def test_race_identity_and_stage_are_not_supplied_by_fec(field, value):
    old, current, race = candidates()
    race["identity"][field] = value
    assert identity.Evidence(evidence()).resolve(old, current, race) is None


def test_same_name_in_the_same_frame_is_ambiguous():
    source = evidence()
    source["candidates"].append({**source["candidates"][0], "candidate_id": "H6AR00002"})
    assert identity.Evidence(source).resolve(*candidates()) is None


@pytest.mark.parametrize("table,field,value", [
    ("committees", "candidate_id", "H6AR00002"),
    ("committees", "designation", "U"),
    ("committees", "committee_type", "Q"),
    ("linkages", "candidate_election_year", "2024"),
    ("linkages", "fec_election_year", "2024"),
    ("linkages", "designation", "U"),
    ("linkages", "candidate_id", "H6AR00002"),
])
def test_unauthorized_or_wrong_cycle_committee_cannot_supply_an_alias(table, field, value):
    source = evidence()
    source[table][0][field] = value
    old, current, race = candidates()
    old["name"] = "Joey Doe"
    assert identity.Evidence(source).resolve(old, current, race) is None


def test_initial_only_committee_alias_is_held():
    source = evidence()
    source["committees"][0]["name"] = "JOEY D FOR CONGRESS"
    old, current, race = candidates()
    old["name"] = "Joey Doe"
    assert identity.Evidence(source).resolve(old, current, race) is None


@pytest.mark.parametrize("field,value", [("state_code", "CA"), ("district", "AR-01"), ("year", 2024)])
def test_legacy_record_must_belong_to_its_actual_source_frame(field, value):
    old, current, race = candidates()
    old[field] = value
    assert identity.Evidence(evidence()).resolve(old, current, race) is None


def unresolved_review(extra_hold=None):
    snapshot, seed, key = fixture()
    seed["accepted_candidates"][0]["name"] = "Joe Doe"
    native = snapshot["congress"]["races"][key]["data"]["native_facts"]
    native["candidates"][0].update(first="Joseph", last="Doe")
    from scripts.results_congress import normalize
    snapshot["congress"]["races"][key]["data"] = normalize(native, "house")
    from test_results_congress import review
    scientific = review()
    scientific["previous_district_queries"][0]["district"] = "AR-AL"
    policy = bridge.prepare_review(snapshot["congress"], seed, scientific, {"datasets": []})
    if extra_hold:
        policy["races"][key]["initial_holds"].append(extra_hold)
        policy["states"]["AR"]["holds"].append(key + ":" + extra_hold)
    return policy, key


def test_successor_preserves_every_legacy_record_and_nonidentity_hold():
    previous, key = unresolved_review("aggregate_other_not_reconciled_to_retained_minor_candidate_mass")
    before = copy.deepcopy(previous)
    successor = identity.successor(previous, evidence(), {})
    assert previous == before
    assert successor["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
    assert successor["frozen_qualification"] == previous["frozen_qualification"]
    assert len(successor["candidate_crosswalk"]) == len(previous["candidate_crosswalk"])
    assert successor["races"][key]["unmatched_legacy_indices"] == [2]
    assert successor["states"]["AR"]["holds"] == [
        key + ":aggregate_other_not_reconciled_to_retained_minor_candidate_mass"]
    assert not successor["states"]["AR"]["automatic_update_reviewed"]
    assert successor["candidate_crosswalk"][2] == previous["candidate_crosswalk"][2]


def test_resolving_identity_does_not_remove_frozen_scientific_hold():
    previous, key = unresolved_review()
    previous["states"]["AR"]["holds"].append("frozen_scientific_hold:source_incompatibility")
    previous["states"]["AR"]["frozen_scientific_comparison_qualified"] = False
    successor = identity.successor(previous, evidence(), {})
    assert successor["states"]["AR"]["holds"] == ["frozen_scientific_hold:source_incompatibility"]
    assert not successor["states"]["AR"]["automatic_update_reviewed"]
    assert successor["races"][key]["unmatched_legacy_indices"] == [2]


def test_compatible_existing_scientific_frame_can_resolve_identity_only():
    previous, key = unresolved_review()
    successor = identity.successor(previous, evidence(), {})
    assert successor["states"]["AR"]["automatic_update_reviewed"]
    assert successor["states"]["AR"]["holds"] == []
    resolved = successor["candidate_identity_successor"]["resolved_identities"]
    assert len(resolved) == 1
    assert successor["races"][key]["named_crosswalk"][resolved[0]["provider_candidate_id"]] == 0


@pytest.mark.parametrize("year", [2026, "2026"])
def test_original_csv_year_and_normalized_integer_year_share_the_reviewed_election(year):
    old, current, race = candidates()
    old["year"] = year
    assert identity.Evidence(evidence()).resolve(old, current, race) is not None


def test_full_predecessor_and_safe_evidence_are_required_to_load_the_successor(tmp_path):
    previous, key = unresolved_review()
    bodies = {
        identity.DATA_PATHS[0]: bridge.compressed(previous),
        identity.DATA_PATHS[1]: bridge.compressed(evidence()),
        identity.DATA_PATHS[2]: encoded({"passed": True}),
    }
    files = {name: pin(body) for name, body in bodies.items()}
    result = identity.successor(previous, evidence(), files)
    for name, body in bodies.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    assert identity.load_successor(tmp_path, result) == result
    result["races"][key]["named_crosswalk"]["invented-provider-id"] = 0
    with pytest.raises(ValueError, match="do not reproduce"):
        identity.load_successor(tmp_path, result)
    result = identity.successor(previous, evidence(), files)
    path = tmp_path / identity.DATA_PATHS[1]
    changed = json.loads(gzip.decompress(path.read_bytes()))
    changed["candidates"][0]["office_state"] = "CA"
    path.write_bytes(bridge.compressed(changed))
    with pytest.raises(ValueError, match="Changed complete"):
        identity.load_successor(tmp_path, result)
    result["candidate_identity_successor"]["files"][identity.DATA_PATHS[1]] = pin(path.read_bytes())
    with pytest.raises(ValueError, match="do not reproduce"):
        identity.load_successor(tmp_path, result)


def test_successor_rejects_contact_fields_in_the_numerical_evidence():
    source = evidence()
    source["candidates"][0]["street_address"] = "not part of identity evidence"
    with pytest.raises(ValueError, match="Unexpected"):
        identity.Evidence(source)


def test_two_legacy_names_cannot_consume_the_same_provider_candidate():
    previous, key = unresolved_review()
    index = len(previous["legacy_candidates_preserved"])
    previous["legacy_candidates_preserved"].append({
        **previous["legacy_candidates_preserved"][0], "name": "Joey Doe"})
    previous["races"][key]["unmatched_legacy_indices"].append(index)
    previous["candidate_crosswalk"].append({
        **previous["candidate_crosswalk"][0], "legacy_index": index,
        "legacy": previous["legacy_candidates_preserved"][index]})
    result = identity.successor(previous, evidence(), {})
    assert result["candidate_identity_successor"]["resolved_identities"] == []
    assert result["races"][key]["named_crosswalk"] == previous["races"][key]["named_crosswalk"]
    assert result["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
