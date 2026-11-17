import copy

import pytest

from scripts import congressional_category_reconciliation as categories
from scripts.congressional_candidate_identity import DECLARATION_VERSION
from scripts.participation_intake.contract import pin


def fixture():
    previous = {"version": DECLARATION_VERSION, "races": {}, "states": {},
                "legacy_candidates_preserved": [], "candidate_crosswalk": []}
    lines, keys = [], []
    for seat in range(1, 9):
        key = f"npr:house:MN:{seat}:regular:general:not_ranked"
        keys.append(key)
        candidate_rows = [("0401", f"Dylan Democrat{seat}", "DFL", "D", 10),
                          ("0302", f"Robin Republican{seat}", "R", "R", 20)]
        if seat == 5:
            candidate_rows.append(("1003", "Pat Independent", "IND", "O", 7))
        total = sum(row[4] for row in candidate_rows) + 3
        mapped, provider = {}, []
        for candidate_id, name, party, group, votes in candidate_rows:
            mapped[candidate_id] = len(previous["legacy_candidates_preserved"])
            previous["legacy_candidates_preserved"].append(
                {"name": name, "party": group, "votes": str(votes)})
            provider.append({"candidate_id": candidate_id, "name": name,
                             "literal_party": party, "party_group": group,
                             "role": "named_candidate", "votes": votes})
            lines.append(f"MN;;;{103+seat:04d};U.S. Representative District {seat};"
                         f"{seat};{candidate_id};{name};;;{party};2;2;{votes};1.00;{total}")
        unmatched = len(previous["legacy_candidates_preserved"])
        previous["legacy_candidates_preserved"].append(
            {"name": "Write-in", "party": "Nonpartisan", "votes": "1" if seat == 2 else "3"})
        provider.append({"candidate_id": "other", "name": "Other", "literal_party": "Other",
                         "party_group": "O", "role": "provider_aggregate_other", "votes": 3})
        lines.append(f"MN;;;{103+seat:04d};U.S. Representative District {seat};"
                     f"{seat};9901;WRITE-IN;;;WI;2;2;3;1.00;{total}")
        previous["races"][key] = {
            "identity": {"state_code": "MN", "chamber": "house", "seat": str(seat),
                         "election_date": "2026-11-03", "stage": "general",
                         "election_kind": "regular", "ranked_choice": False, "round": "not_ranked"},
            "accepted_native": {"candidates": provider}, "named_crosswalk": mapped,
            "unmatched_legacy_indices": [unmatched],
            "initial_holds": [categories.MASS_HOLD] if seat == 2 else [],
        }
    previous["states"]["MN"] = {
        "expected_race_ids": keys, "frozen_scientific_comparison_qualified": True,
        "initial_recorded_comparison_qualified": True, "automatic_update_reviewed": False,
        "holds": [keys[1] + ":" + categories.MASS_HOLD],
    }
    body = ("\n".join(lines) + "\n").encode()
    value = {"contract": categories.CONTRACT, "sources": [{
        "family": "mn_house_statewide_semicolon_v1",
        "url": "https://electionresultsfiles.sos.mn.gov/20261103/ushouse.txt",
        "original_path": categories.DATA_PATHS[2], "original_pin": pin(body),
        "election_date": "2026-11-03", "stage": "general", "captured_at": None,
    }]}
    return previous, value, body


def test_complete_inventory_resolves_only_category_guard_and_keeps_original_counts():
    previous, value, body = fixture()
    saved = copy.deepcopy(previous)
    review = categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})
    assert previous == saved
    assert review["states"]["MN"]["automatic_update_reviewed"]
    assert review["legacy_candidates_preserved"] == previous["legacy_candidates_preserved"]
    assert len(review["official_category_successor"]["resolved_races"]) == 1
    district = review["races"][previous["states"]["MN"]["expected_race_ids"][4]]
    decision = district["official_category_reconciliation"]
    assert decision["provider_aggregate_other"]["votes"] == 3
    assert next(row for row in decision["named_candidates"]
                if row["official"]["name"] == "Pat Independent")["provider"]["votes"] == 7
    assert not decision["individual_count_allocated_from_Other"]


def test_equal_major_party_totals_cannot_hide_omitted_named_minor_candidate():
    previous, value, body = fixture()
    lines = [line for line in body.decode().splitlines() if ";Pat Independent;" not in line]
    lines = [line.rsplit(";", 1)[0] + ";33" if ";U.S. Representative District 5;" in line
             else line for line in lines]
    body = ("\n".join(lines) + "\n").encode()
    value["sources"][0]["original_pin"] = pin(body)
    with pytest.raises(ValueError, match="Provider named candidate absent"):
        categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})


def test_same_major_totals_do_not_qualify_different_other_mass():
    previous, value, body = fixture()
    previous["races"][previous["states"]["MN"]["expected_race_ids"][1]][
        "accepted_native"]["candidates"][-1]["votes"] = 4
    with pytest.raises(ValueError, match="Provider Other differs"):
        categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})


@pytest.mark.parametrize("old,new,reason", [
    (b";2;2;10;", b";1;2;10;", "Incomplete official"),
    (b";9901;WRITE-IN;", b";9901;Named Person;", "Ambiguous official write-in"),
    (b";DFL;2;2;10;", b";R;2;2;10;", "candidate inventory"),
    (b";2;2;10;", b";2;2;-10;", "noninteger official"),
])
def test_malformed_official_rows_fail_closed(old, new, reason):
    previous, value, body = fixture()
    body = body.replace(old, new, 1)
    value["sources"][0]["original_pin"] = pin(body)
    with pytest.raises(ValueError, match=reason):
        categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})


@pytest.mark.parametrize("field,new", [("election_date", "2024-11-05"), ("stage", "primary")])
def test_wrong_election_or_stage_is_never_reclassified(field, new):
    previous, value, body = fixture()
    value["sources"][0][field] = new
    with pytest.raises(ValueError, match="Unreviewed official"):
        categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})


def test_missing_district_and_changed_original_are_refused():
    previous, value, body = fixture()
    with pytest.raises(ValueError, match="original changed"):
        categories.successor(previous, value, {categories.DATA_PATHS[2]: body + b"\n"}, {})
    lines = [line for line in body.decode().splitlines()
             if ";U.S. Representative District 8;" not in line]
    body = ("\n".join(lines) + "\n").encode()
    value["sources"][0]["original_pin"] = pin(body)
    with pytest.raises(ValueError, match="district inventory incomplete"):
        categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})


def test_other_scientific_holds_cannot_be_removed_by_category_evidence():
    previous, value, body = fixture()
    previous["states"]["MN"]["holds"].append("different_historical_source_frame")
    review = categories.successor(previous, value, {categories.DATA_PATHS[2]: body}, {})
    assert review["states"]["MN"]["holds"] == ["different_historical_source_frame"]
    assert not review["states"]["MN"]["automatic_update_reviewed"]
