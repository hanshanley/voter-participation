import pytest

from scripts import southeast_turnout as se
from scripts.supported_analytical_release import selected_local_observation_ids


def sc_lines():
    return [
        "Voter Participation History Total Overall Participation",
        "Registered",
        *(f"{year} General Election{'*' if year <= 2006 else ''} 1,000 600 "
          f"{'55.0%' if year == 2018 else '60.0%'}" for year in range(2026, 1997, -2)),
        "participation is calculated using Ballots Cast Method (BCM) uses actual ballots cast",
        "Denotes participation calculated using Voter History Method (VHM)",
    ]


def test_sc_keeps_both_rate_values_and_rejects_misdated_rows():
    lines = sc_lines()
    lines[3] = lines[3].removeprefix("2024 ")
    lines.insert(4, "2024 State Primaries")
    rows = {r["year"]: r for r in se.sc_query(lines)}
    assert rows[2006]["numerator_basis"] == "voter_history_credits"
    assert rows[2008]["numerator_basis"] == "ballots_cast"
    assert not rows[2018]["published_rate_matches_counts"]
    assert rows[2018]["participation_per_reported_registration"] == .6
    with pytest.raises(ValueError, match="year label"):
        se.sc_query([line for line in lines if line != "2024 State Primaries"])


def test_al_preserves_unreported_age_cells_and_checks_county_and_state_controls():
    rows = [[county, 8, *([1] * 8), None] for county in se.COUNTIES]
    rows.append(["TOTAL", 536, *([67] * 8), 0])
    feed = se.AL[2018]
    state = {"source": {"url": se.URLS[feed], "sha256": "a" * 64},
             "status": "retained_after_failure", "data": se.facts(rows, feed)}
    _, al = se.exports({feed: state})
    assert len(al) == 680
    assert al[9]["reported_ballots"] is None
    assert al[-1]["reported_ballots"] == 0
    assert all(r["source_status"] == "retained_after_failure" for r in al)
    rows[-1][1] += 1
    rows[-1][2] += 1
    with pytest.raises(ValueError, match="statewide control"):
        se.al_query(rows, 2018)


def test_historical_products_cannot_select_current_counts():
    assert selected_local_observation_ids({
        "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": list(se.URLS)},
        "granular_sources": {feed: {"status": "reported"} for feed in se.URLS},
    }) == set()
