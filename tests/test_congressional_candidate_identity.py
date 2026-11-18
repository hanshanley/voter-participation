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


def declaration_fixture():
    fec = evidence()
    fec["candidates"][0]["name"] = "DOE, JOSEPH"
    fec["committees"] = []
    fec["linkages"] = []
    previous, key = unresolved_review()
    previous = identity.successor(previous, fec, {})
    value = {
        "contract": identity.DECLARATION_CONTRACT,
        "sources": [{
            "id": "party-bios", "url": "https://example.org/candidates",
            "bytes": 1000, "sha256": "a" * 64, "checked_at": "2026-11-17T17:00:00Z",
            "kind": "nominating_party",
            "facts": {"name": 'Joseph "Joe" Doe', "role": "Us Representative - District 0"},
        }],
        "declarations": [{
            "fec_candidate_id": "H6AR00001", "state_code": "AR", "district": "00",
            "literal_party": "DEM", "election_year": "2026", "source_id": "party-bios",
            "name_facts": ["name"], "role_fact": "role", "relationship": "same_candidate_biography",
        }],
    }
    return fec, previous, value, key


def test_primary_declaration_resolves_only_the_explicit_full_name_pair():
    fec, previous, value, key = declaration_fixture()
    before = copy.deepcopy(previous)
    assert previous["states"]["AR"]["holds"]
    result = identity.declaration_successor(previous, value, fec, {})
    assert previous == before
    assert result["states"]["AR"]["automatic_update_reviewed"]
    assert result["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
    assert result["candidate_crosswalk"][2] == previous["candidate_crosswalk"][2]
    assert identity.DeclaredEvidence(fec, value).resolve(*candidates()) is not None
    old, current, race = candidates()
    old["name"] = "Joey Doe"
    assert identity.DeclaredEvidence(fec, value).resolve(old, current, race) is None


def test_two_literal_names_in_one_reviewed_biography_allow_only_optional_middle_initials():
    fec, _, value, _ = declaration_fixture()
    fec["candidates"][0]["name"] = "DOE, JOE"
    value["sources"][0]["facts"].update(name="Joseph C. Doe", short="Joe Doe")
    value["declarations"][0]["name_facts"].append("short")
    old, current, race = candidates()
    assert identity.DeclaredEvidence(fec, value).resolve(old, current, race) is not None
    current["name"] = "Joseph Charles Doe"
    assert identity.DeclaredEvidence(fec, value).resolve(old, current, race) is None


def test_smart_quoted_declaration_preserves_literal_middle_initial_without_requiring_it_in_feed():
    fec, _, value, _ = declaration_fixture()
    value["sources"][0]["facts"]["name"] = "Joseph \u201cJoe\u201d C. Doe"
    result = identity.DeclaredEvidence(fec, value).resolve(*candidates())
    assert result["legacy_support"]["declarations"][0]["name_facts"] == {
        "name": "Joseph \u201cJoe\u201d C. Doe"}


@pytest.mark.parametrize("target,field,value", [
    ("declarations", "state_code", "CA"), ("declarations", "district", "01"),
    ("declarations", "election_year", "2024"), ("declarations", "literal_party", "REP"),
    ("declarations", "relationship", "similar_names"),
    ("sources", "kind", "search_snippet"), ("sources", "url", "http://example.org/candidates"),
    ("sources", "sha256", "not-a-hash"),
])
def test_unqualified_declaration_context_cannot_resolve_identity(target, field, value):
    fec, _, declarations, _ = declaration_fixture()
    declarations[target][0][field] = value
    with pytest.raises(ValueError):
        identity.DeclaredEvidence(fec, declarations)


@pytest.mark.parametrize("literal", ["State Representative - District 0",
                                    "Us Representative - District 1", "Senate"])
def test_other_office_or_district_declaration_stays_held(literal):
    fec, _, value, _ = declaration_fixture()
    value["sources"][0]["facts"]["role"] = literal
    with pytest.raises(ValueError, match="congressional district"):
        identity.DeclaredEvidence(fec, value)


def test_primary_identity_bridge_preserves_overlapping_other_and_source_holds():
    fec, previous, value, key = declaration_fixture()
    reason = "aggregate_other_not_reconciled_to_retained_minor_candidate_mass"
    previous["races"][key]["initial_holds"].append(reason)
    previous["states"]["AR"]["holds"].append(key + ":" + reason)
    result = identity.declaration_successor(previous, value, fec, {})
    assert result["states"]["AR"]["holds"] == [key + ":" + reason]
    assert result["states"]["AR"]["automatic_update_reviewed"] is False
    assert result["races"][key]["accepted_native"] == previous["races"][key]["accepted_native"]


def test_complete_primary_evidence_and_full_fec_predecessor_chain_are_packaged(tmp_path):
    fec, previous, value, _ = declaration_fixture()
    base = unresolved_review()[0]
    fec_bodies = {
        identity.DATA_PATHS[0]: bridge.compressed(base),
        identity.DATA_PATHS[1]: bridge.compressed(fec),
        identity.DATA_PATHS[2]: encoded({"passed": True}),
    }
    previous = identity.successor(base, fec, {name: pin(body) for name, body in fec_bodies.items()})
    bodies = {
        identity.DECLARATION_PATHS[0]: bridge.compressed(previous),
        identity.DECLARATION_PATHS[1]: bridge.compressed(value),
        identity.DECLARATION_PATHS[2]: encoded({"passed": True}),
    }
    result = identity.declaration_successor(previous, value, fec,
                                            {name: pin(body) for name, body in bodies.items()})
    for name, body in {**fec_bodies, **bodies}.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    assert set(identity.DATA_PATHS + identity.DECLARATION_PATHS) <= set(bridge.data_paths(result))
    assert identity.load_declaration_successor(tmp_path, result) == result
    result["states"]["AR"]["automatic_update_reviewed"] = False
    with pytest.raises(ValueError, match="do not reproduce"):
        identity.load_declaration_successor(tmp_path, result)
    path = tmp_path / identity.DATA_PATHS[1]
    path.write_bytes(bridge.compressed({**fec, "sources": ["changed"]}))
    with pytest.raises(ValueError, match="Changed complete"):
        identity.load_declaration_successor(tmp_path, result)


def official_declaration_fixture():
    from scripts.congressional_category_reconciliation import VERSION as CATEGORY_VERSION

    fec, previous, value, key = declaration_fixture()
    previous["version"] = CATEGORY_VERSION
    source = value["sources"][0]
    source.update(kind="official_election_report", url="https://elections.example.gov/precinct.pdf")
    source["facts"].update(role="United States Representative", state="Arkansas",
                           election_date="11/03/2026", election_stage="State General")
    value["declarations"][0]["relationship"] = "same_native_candidate_row"
    return fec, previous, value, key


def test_official_literal_alias_updates_identity_without_importing_local_counts():
    fec, previous, value, key = official_declaration_fixture()
    saved = copy.deepcopy(previous)
    result = identity.official_declaration_successor(previous, value, fec, {})
    assert previous == saved
    assert result["states"]["AR"]["automatic_update_reviewed"]
    assert result["races"][key]["accepted_native"] == previous["races"][key]["accepted_native"]
    assert result["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
    assert result["frozen_qualification"] == previous["frozen_qualification"]
    assert result["candidate_identity_successor"] == previous["candidate_identity_successor"]
    assert len(result["official_name_declarations"]["resolved_identities"]) == 1
    assert set(identity.OFFICIAL_DECLARATION_PATHS) <= set(bridge.data_paths(result))
    with pytest.raises(ValueError, match="primary source receipt"):
        identity.DeclaredEvidence(fec, value)


@pytest.mark.parametrize("field,value", [
    ("role", "United States Senator"), ("state", "South Dakota"),
    ("election_date", "11/05/2024"), ("election_stage", "State Primary"),
])
def test_official_report_wrong_office_state_year_or_stage_refuses(field, value):
    fec, _, source, _ = official_declaration_fixture()
    source["sources"][0]["facts"][field] = value
    with pytest.raises(ValueError, match="exact at-large"):
        identity.OfficialDeclaredEvidence(fec, source)


def test_unqualified_authority_or_non_at_large_office_cannot_supply_official_alias():
    fec, _, value, _ = official_declaration_fixture()
    value["sources"][0]["url"] = "https://elections.example.org/precinct.pdf"
    with pytest.raises(ValueError, match="exact at-large"):
        identity.OfficialDeclaredEvidence(fec, value)
    value["sources"][0]["url"] = "https://elections.example.gov/precinct.pdf"
    fec["candidates"][0]["district"] = value["declarations"][0]["district"] = "01"
    with pytest.raises(ValueError, match="exact at-large"):
        identity.OfficialDeclaredEvidence(fec, value)


def test_official_alias_keeps_independent_other_source_and_scientific_holds():
    fec, previous, value, key = official_declaration_fixture()
    reason = "aggregate_other_not_reconciled_to_retained_minor_candidate_mass"
    previous["races"][key]["initial_holds"].append(reason)
    previous["states"]["AR"]["holds"].extend([key + ":" + reason, "frozen_scientific_hold"])
    previous["states"]["AR"]["frozen_scientific_comparison_qualified"] = False
    result = identity.official_declaration_successor(previous, value, fec, {})
    assert result["states"]["AR"]["holds"] == ["frozen_scientific_hold", key + ":" + reason]
    assert not result["states"]["AR"]["automatic_update_reviewed"]


def test_official_declaration_needs_existing_fec_chain_and_a_resolved_guard():
    fec, previous, value, _ = official_declaration_fixture()
    with pytest.raises(ValueError, match="same complete FEC"):
        identity.official_declaration_successor(previous, value, {**fec, "sources": ["changed"]}, {})
    value["sources"][0]["facts"]["name"] = 'Joseph "Joey" Doe'
    with pytest.raises(ValueError, match="resolve no existing"):
        identity.official_declaration_successor(previous, value, fec, {})


def filing_fixture(party=False):
    from scripts import congressional_filing_identity as filing

    fec = evidence()
    fec["candidates"][0]["name"] = "DOE, JOSEPH"
    fec["committees"][0]["name"] = "DOE FOR CONGRESS"
    previous, key = unresolved_review()
    previous = identity.successor(previous, fec, {})
    previous["version"] = identity.OFFICIAL_DECLARATION_VERSION
    urls = [
        "https://www.fec.gov/data/candidate/H6AR00001/?cycle=2026&tab=about-candidate",
        "https://www.fec.gov/data/committee/C00000001/?cycle=2026",
        "https://www.fec.gov/data/committee/C00000001/?cycle=2026&tab=about-committee#section-2",
        "https://docquery.fec.gov/pdf/123/202601010000000123/202601010000000123.pdf",
    ]
    sources = []
    for index, kind in enumerate(("fec_candidate", "fec_committee", "fec_committee_about", "fec_form1")):
        facts = ({("committee_url", "about_url", "filing_url")[index]: urls[index + 1]}
                 if index < 3 else {
                     "committee_id": "C00000001", "committee_id_page": 1,
                     "candidate_name": "DOE, JOSEPH, , ," if party else "DOE, JOE, R, ,",
                     "state": "AR", "district": "00", "literal_party": "DEM", "office": "H",
                     "designation": "P", "physical_page": 2, "section": "5",
                     "field_role": "Name of Candidate", "campaign_website": "DOEFORCONGRESS.EXAMPLE",
                 })
        sources.append({
            "id": kind, "kind": kind, "url": urls[index], "facts": facts,
            "bytes": 1000, "sha256": "a" * 64, "checked_at": "2026-11-17T17:00:00Z",
        })
    if party:
        sources.append({
            **sources[0], "id": "party", "kind": "nominating_party",
            "url": "https://party.example/candidates",
            "facts": {"anchor_label": "Joe Doe | CD0", "candidate_anchor_labels": ["Joe Doe | CD0"],
                      "href": "https://doeforcongress.example", "election_year": "2026"},
        })
    value = {"contract": filing.CONTRACT, "sources": sources, "filings": [{
        "fec_candidate_id": "H6AR00001", "committee_id": "C00000001",
        "candidate_source": "fec_candidate", "committee_source": "fec_committee",
        "committee_about_source": "fec_committee_about", "filing_source": "fec_form1",
        "party_source": "party" if party else None,
    }]}
    return fec, previous, value, key


@pytest.mark.parametrize("party", [False, True])
def test_authorized_filing_or_named_party_campaign_link_resolves_only_pinned_identity(party):
    from scripts import congressional_filing_identity as filing

    fec, previous, value, key = filing_fixture(party)
    saved = copy.deepcopy(previous)
    assert identity.Evidence(fec).resolve(*candidates()) is None
    resolved = filing.FilingEvidence(fec, value).resolve(*candidates())
    assert resolved["fec_candidate"]["candidate_id"] == "H6AR00001"
    result = filing.successor(previous, value, fec, {})
    assert previous == saved
    assert result["states"]["AR"]["automatic_update_reviewed"]
    assert result["races"][key]["accepted_native"] == previous["races"][key]["accepted_native"]
    assert result["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
    assert result["frozen_qualification"] == previous["frozen_qualification"]
    assert set(filing.DATA_PATHS) <= set(bridge.data_paths(result))


@pytest.mark.parametrize("field,value", [
    ("field_role", "Name of Treasurer"), ("designation", "U"), ("office", "S"),
    ("state", "GA"), ("district", "01"), ("literal_party", "REP"),
    ("committee_id", "C00000002"), ("candidate_name", "DOE, J, R, ,"),
    ("candidate_name", "OTHER, JOE, , ,"),
])
def test_filing_rejects_officer_names_and_wrong_candidate_designation(field, value):
    from scripts import congressional_filing_identity as filing

    fec, _, source, _ = filing_fixture()
    source["sources"][3]["facts"][field] = value
    with pytest.raises(ValueError):
        filing.FilingEvidence(fec, source)


@pytest.mark.parametrize("table,field,value", [
    ("committees", "candidate_id", "H6AR00002"), ("committees", "literal_party", "REP"),
    ("linkages", "candidate_election_year", "2024"), ("linkages", "fec_election_year", "2024"),
    ("linkages", "designation", "U"),
])
def test_filing_cannot_supply_its_own_authorization_or_cycle(table, field, value):
    from scripts import congressional_filing_identity as filing

    fec, _, source, _ = filing_fixture()
    fec[table][0][field] = value
    with pytest.raises(ValueError, match="authorized FEC linkage"):
        filing.FilingEvidence(fec, source)


@pytest.mark.parametrize("field,value", [
    ("href", "https://www.doeforcongress.example"), ("href", "https://other.example"),
    ("anchor_label", "Joe Doe | CD1"), ("election_year", "2024"),
    ("candidate_anchor_labels", ["Joe Doe | CD0", "Other Doe | CD0"]),
])
def test_party_nickname_requires_exact_unique_candidate_link_and_district(field, value):
    from scripts import congressional_filing_identity as filing

    fec, _, source, _ = filing_fixture(True)
    source["sources"][4]["facts"][field] = value
    with pytest.raises(ValueError, match="Party anchor"):
        filing.FilingEvidence(fec, source)


def test_filing_chain_and_both_unique_fec_anchors_are_required():
    from scripts import congressional_filing_identity as filing

    fec, _, source, _ = filing_fixture()
    source["sources"][2]["facts"]["filing_url"] += "?unlinked"
    with pytest.raises(ValueError, match="declaration chain"):
        filing.FilingEvidence(fec, source)
    fec, _, source, _ = filing_fixture()
    fec["candidates"].append({**fec["candidates"][0], "candidate_id": "H6AR00002"})
    assert filing.FilingEvidence(fec, source).resolve(*candidates()) is None


def test_filing_successor_preserves_other_and_scientific_holds_and_checks_evidence():
    from scripts import congressional_filing_identity as filing

    fec, previous, source, key = filing_fixture()
    reason = "aggregate_other_not_reconciled_to_retained_minor_candidate_mass"
    previous["races"][key]["initial_holds"].append(reason)
    previous["states"]["AR"]["holds"].extend([key + ":" + reason, "frozen_scientific_hold"])
    previous["states"]["AR"]["frozen_scientific_comparison_qualified"] = False
    result = filing.successor(previous, source, fec, {})
    assert set(result["states"]["AR"]["holds"]) == {"frozen_scientific_hold", key + ":" + reason}
    assert not result["states"]["AR"]["automatic_update_reviewed"]
    with pytest.raises(ValueError, match="same complete FEC"):
        filing.successor(previous, source, {**fec, "sources": ["changed"]}, {})


def test_filing_loader_pins_full_evidence_and_recursively_validates_predecessor(tmp_path, monkeypatch):
    from scripts import congressional_filing_identity as filing

    fec, previous, source, _ = filing_fixture()
    bodies = {
        filing.DATA_PATHS[0]: bridge.compressed(previous),
        filing.DATA_PATHS[1]: bridge.compressed(source),
        filing.DATA_PATHS[2]: encoded({"passed": True}),
        identity.DATA_PATHS[1]: bridge.compressed(fec),
    }
    files = {name: pin(bodies[name]) for name in filing.DATA_PATHS}
    result = filing.successor(previous, source, fec, files)
    for name, body in bodies.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    calls = []
    monkeypatch.setattr(filing, "load_official_declaration_successor",
                        lambda root, value: calls.append((root, value)))
    assert filing.load_successor(tmp_path, result) == result
    assert calls == [(tmp_path, previous)]
    changed = copy.deepcopy(result)
    changed["states"]["AR"]["automatic_update_reviewed"] = False
    with pytest.raises(ValueError, match="do not reproduce"):
        filing.load_successor(tmp_path, changed)
    (tmp_path / filing.DATA_PATHS[1]).write_bytes(bridge.compressed({**source, "filings": []}))
    with pytest.raises(ValueError, match="Changed complete"):
        filing.load_successor(tmp_path, result)
