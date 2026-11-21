import pytest

from scripts.virginia_precinct_reference import DATE, LOCALITY, join


def precinct(code, name, count):
    return {
        "locality": LOCALITY, "election_date": DATE, "ballots": str(count),
        "locality_ballots_control": "15", "unit_kind": "physical_precinct",
        "ballot_component": "election_day", "precinct_code": code, "reporting_unit": f"{code} - {name}",
    }


def feature(code, name, x):
    return {
        "properties": {"id": code, "name": name},
        "geometry": {"type": "Polygon", "coordinates": [[(x, 0), (x + 1, 0), (x + 1, 1), (x, 1), (x, 0)]]},
    }


def test_reference_join_leaves_both_unmatched_sides_in_the_audit():
    rows = [precinct("001", "Fork", 4), precinct("002", "West / East", 3)]
    rows.append({**rows[0], "unit_kind": "central_reporting_unit", "ballot_component": "mail",
                 "precinct_code": "", "ballots": "8"})
    shapes = [feature("P1", "FORK", 0), feature("P2", "West", 1)]
    _, decisions, central, control = join(rows, shapes, LOCALITY, "id", "name")
    assert [r["decision"] for r in decisions] == ["matched_reference_name", "geometry_only", "count_only"]
    assert [r["election_day_ballots"] for r in decisions] == [4, None, 3]
    assert (central, control) == (8, 15)
    with pytest.raises(ValueError, match="overlapping"):
        join(rows, [shapes[0], feature("P2", "West", 0.5)], LOCALITY, "id", "name")
    with pytest.raises(ValueError, match="do not reconcile"):
        join(rows[:-1], shapes, LOCALITY, "id", "name")
