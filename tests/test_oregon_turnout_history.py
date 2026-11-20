import pytest

from scripts import oregon_turnout_history as ore
from scripts.supported_analytical_release import selected_local_observation_ids


def sources():
    history = ore.query([
        "Voter Turnout History for General Elections Oregon Secretary of State",
        "Year Total Registered Voters Total Votes Cast % of Turnout",
        *(f"{year} 1,000 600 60.00%" for year in range(2024, 1959, -2)),
        "Generated 09/12/2025",
    ], ore.HISTORY)
    control = ore.query([
        "May 19, 2026 Primary Election Official Voter Registration & Turnout Statistics",
        "Comparative Voter Registration and Participation Statistics General Elections Other Totals",
        "Year Active Ballots Percent Active Ballots Percent Voters Returned Returned Voters Returned Returned",
        *(f"{year} 10 N/A N/A 1,000 " + ("605 60.50%" if year == 2020 else "600 60.00%")
          for year in range(1960, 2025, 2)),
    ], ore.CONTROL)
    return {feed: {"source": {"url": ore.URLS[feed], "sha256": "a" * 64},
                   "status": "reported", "data": data}
            for feed, data in zip(ore.URLS, (history, control))}


def test_complete_comparison_holds_disagreement_and_accepts_partial_sources():
    entries = sources()
    rows = {r["year"]: r for r in ore.exports(entries)}
    assert len(rows) == 33 and rows[2024]["matched_returned_ballots_per_active_voter"] == .6
    assert rows[2020]["history_count"] == 600 and rows[2020]["control_count"] == 605
    assert rows[2020]["reconciliation"] == "counts_differ"
    assert rows[2020]["matched_returned_ballots_per_active_voter"] is None
    assert {r["reconciliation"] for r in ore.exports({ore.HISTORY: entries[ore.HISTORY]})} == {"one_source"}
    entries[ore.CONTROL]["status"] = "retained_after_failure"
    assert next(ore.exports(entries))["control_source_status"] == "retained_after_failure"
    entries[ore.HISTORY]["data"]["complete_native_query"][-1]["count"] += 1
    with pytest.raises(ValueError, match="retained source query"):
        list(ore.exports(entries))


def test_scoped_oregon_history_cannot_select_current_counts():
    assert selected_local_observation_ids({
        "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": list(ore.URLS)},
        "granular_sources": sources(),
    }) == set()
