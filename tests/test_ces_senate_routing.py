import json

import pytest

from scripts import ces_senate_routing as routing
from scripts import ces_2022_senate_routing as midterm


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


def test_2022_special_uses_only_the_special_slate_and_validated_voter_state():
    races = {}
    for state, (seat, kind, _, _, _) in midterm.FRAMES.items():
        office = "S-Unexpired Term" if kind == "special" else "S"
        baseline = dict(cycle_year=2022, seat=seat, stage="general", election_kind=kind)
        candidates = [
            dict(candidate=name, party_group=party, fec_candidate_id=f"S2{state}{i:05d}",
                 state_code=state, native_office=office, seat=seat, stage="general",
                 year=2022, election_kind=kind)
            for i, (name, party) in enumerate([("Horn, Kendra", "D"), ("Mullin, Markwayne", "R")])
        ]
        races[state] = dict(seat=seat, qualified_comparison="True", baseline=json.dumps(baseline),
                            previous_candidates=json.dumps(candidates))
    labels = dict(routing.FIPS)
    sample = dict(
        inputstate_post="40", TS_state="40", TS_g2022="4", vvweight_post="1",
        CC22_411="1", CC22_411b="2", SenCand1Name2_post="Kendra Horn",
        SenCand1Party2_post="Democratic", SenCand2Name2_post="Markwayne Mullin",
        SenCand2Party2_post="Republican")
    _, _, ok = midterm.evaluate([sample, {**sample, "CC22_411b": ""},
                                 {**sample, "TS_state": "39"},
                                 {**sample, "CC22_411b": "8"}], races, labels)
    assert (ok["answered"], ok["matched_slate"], ok["reported_major_choice"]) == (3, 2, 1)
    assert not ok["transition_model_qualified"]
    races["OK"]["previous_candidates"] = races["OK"]["previous_candidates"].replace("S-Unexpired Term", "S")
    with pytest.raises(ValueError, match="invalid reviewed candidate frame"):
        midterm.evaluate([sample], races, labels)
