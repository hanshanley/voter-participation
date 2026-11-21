import json

from scripts import ces_senate_routing as routing


def race(stage="general", year=2020):
    return {
        "state_code": "CO", "seat": "2", "stage": "general", "qualified_comparison": "True",
        "baseline": json.dumps({"cycle_year": year, "stage": stage, "seat": "2", "election_kind": "regular"}),
        "previous_candidates": json.dumps([
            dict(candidate=name, party_group=party, fec_candidate_id=f"S0CO0000{i}",
                 state_code="CO", native_office="S", seat="2", stage="general", year=2020)
            for i, (name, party) in enumerate([("Hickenlooper, John W.", "D"), ("Gardner, Cory", "R")])
        ]),
    }


def test_historical_sample_requires_validated_state_and_same_candidate_slate():
    labels = {code: state for code, state in routing.FIPS.items()}
    good = {
        "inputstate_post": "8", "CL_state": "8", "CL_2020gvm": "4", "CC20_411": "1",
        "SenCand1Name_post": "John Hickenlooper", "SenCand1Party_post": "Democratic",
        "SenCand2Name_post": "Cory Gardner", "SenCand2Party_post": "Republican", "vvweight_post": "0.7",
    }
    data = [good, {**good, "CL_state": "1"}, {**good, "SenCand1Name_post": "Other Hickenlooper"},
            {**good, "CC20_411": "5"}, {**good, "vvweight_post": "NA"}]
    row, = routing.evaluate(data, {"CO": race()}, labels)
    assert (row["answered"], row["matched_state_validated_voter"], row["slate_unverified"],
            row["matched_slate"], row["reported_major_choice"]) == (5, 3, 1, 2, 1)
    assert not row["transition_model_qualified"]


def test_runoff_preferences_and_wrong_election_year_cannot_supply_the_baseline():
    assert routing.frame(race(stage="general_runoff")) == ("historical_stage_or_seat_not_covered", None)
    assert routing.frame(race(year=2022)) == ("different_baseline_year", None)
