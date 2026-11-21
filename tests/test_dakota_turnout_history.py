import pytest

from scripts import dakota_turnout_history as dakota


def test_nd_separates_general_counts_and_estimated_rates():
    rows = [f"{year} G 400 30,000 - - - 100,000 60,000 - 50%" for year in range(1980, 2025, 2)]
    rows[1] = rows[1].removesuffix("50%") + "62%"
    rows.insert(0, "1980 P 400 15,000 - - - 100,000 60,000 - 25%")
    values = dakota.nd_rows(rows)
    assert len(values) == 23
    assert values[0]["reported_absentee_votes"] is None
    assert values[0]["qualified_eligible_turnout_pct"] == "50.000000"
    assert values[1]["reported_turnout"] == 30_000 and values[1]["qualified_eligible_turnout_pct"] is None
    with pytest.raises(ValueError, match="duplicate"):
        dakota.nd_rows([*rows, rows[-1]])
    with pytest.raises(ValueError, match="Incomplete"):
        dakota.nd_rows(rows[:-2] + rows[-1:])


def test_sd_keeps_registration_and_vap_separate():
    years = list(map(str, range(1988, 2025, 2)))
    columns = [
        ["YEAR", *years], ["TOTAL REGISTRATION", *(["800"] * len(years))],
        ["VOTING AGE POPUL.", *(["1000"] * len(years))],
        ["REG. % OF VAP", *(["80%"] * len(years))],
        ["TURNOUT", *(["400"] * len(years))], ["TURNOUT % OF VAP", *(["40%"] * len(years))],
        ["TURNOUT % OF REG.", *(["50%"] * len(years))], ["PRECINCTS", *(["10"] * len(years))],
    ]
    columns[5][1], columns[6][1] = columns[6][1], columns[5][1]
    head, *rest = dakota.sd_rows(columns)
    assert head["reported_turnout"] == 400
    assert head["qualified_registered_turnout_pct"] is head["qualified_vap_turnout_pct"] is None
    assert rest[0]["qualified_registered_turnout_pct"] == "50.000000"
    assert rest[0]["qualified_vap_turnout_pct"] == "40.000000"
    with pytest.raises(ValueError, match="labels differ"):
        dakota.sd_rows([row for row in columns if row[0] != "TURNOUT"])
