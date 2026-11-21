import csv
import io

import pytest

from scripts import norc_senate_routing as routing


HEADER = "P_STATE,RACE1_RACEID,RACE1_OFFICEID,SENVOTE,WVA,WVB,CHEP_WEIGHT\n"
RACE = {"provider_race_id": "84979", "seat": "3", "election_kind": "special", "stage": "general",
        "round": "not_ranked"}


def test_counts_keep_observed_by_interview_and_intended_routes_separate():
    rows = "FL,84979,S,1,1,,1\nFL,84979,S,2,2,,3\nFL,84979,S,3,,3,2\nFL,84979,S,1,,,2\n"
    result = routing.audit(csv.DictReader(io.StringIO(HEADER + rows)), {"FL": RACE})
    assert [row["respondents_with_senate_answer"] for row in result] == [2, 1, 1]
    assert result[0]["weight_only_effective_n"] == "1.60"
    assert all(not row["participation_rate_qualified"] and not row["senate_transition_model_qualified"]
               for row in result)


@pytest.mark.parametrize("record,reason", [
    ("FL,84978,S,1,1,,1", "respondent routing"),
    ("FL,84979,S,1,1,3,1", "voting-timing routes"),
    ("FL,84979,S,1,1,,NaN", "population weight"),
])
def test_mismatched_race_or_unusable_weight_and_route_stop_the_audit(record, reason):
    with pytest.raises(ValueError, match=reason):
        routing.audit(csv.DictReader(io.StringIO(HEADER + record)), {"FL": RACE})


def test_special_senate_seat_cannot_be_substituted():
    bad = {**RACE, "seat": "2", "chamber": "senate", "advertised": "True",
           "state_code": "FL", "election_date": routing.ELECTION}
    with pytest.raises(ValueError, match="seat or stage"):
        routing.contests([bad])
