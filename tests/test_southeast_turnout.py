from datetime import datetime, timezone

import pytest

from scripts import alabama_precinct_history as precinct, results_intake, southeast_turnout as se
from scripts.supported_analytical_release import selected_local_observation_ids
from scripts.participation_intake.contract import federal_general


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


def test_alabama_statewide_history_separates_vote_context_and_holds_date_or_rate_conflicts():
    lines = [*se.AL_HISTORY_HEADER]
    for year in range(1986, 2025, 2):
        day = 3 if year == 2014 else federal_general(year).day
        lines += [f"General Election November {day}, {year}",
                  "1,000 600 (60% turnout)" if year < 2014 else
                  f"1,000 Total Ballots Cast 600 ({'55' if year == 2020 else '60'}% turnout)"]
    lines.append("Office of the Secretary of State Last Revised July 13, 2026 Page 1 of 1")
    rows = {r["year"]: r for r in se.al_history_query(lines)}
    assert rows[2012]["decision"] == "contest_vote_context_only"
    assert rows[2012]["qualified_turnout_rate_pct"] is None
    assert rows[2014]["decision"] == "source_election_date_disagrees"
    assert rows[2020]["decision"] == "printed_rate_disagrees"
    assert rows[2024]["qualified_turnout_rate_pct"] == 60
    with pytest.raises(ValueError, match="page sequence"):
        se.al_history_query(lines[:-1])


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
    scope = [*se.URLS, *precinct.URLS]
    assert selected_local_observation_ids({
        "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": scope},
        "granular_sources": {feed: {"status": "reported"} for feed in scope},
    }) == set()


def test_precinct_controls_preserve_conflict_absentee_and_missing_register():
    archive_feed, control_feed = precinct.FEEDS[2024]
    rows = {name: [["Town hall", 15 if name == "AUTAUGA" else 8, 0],
                   ["ABSENTEE", 2, None]] for name in se.COUNTIES}
    lines = ["General Election - November 5, 2024", "Official Total Ballots Cast",
             "County Voters Ballots Cast Ballots Ballots Ballots Registered Voters Total Ballots",
             *(f"{name.replace('_', ' ')} 100 10 0 0 2 10.00% 20.00%" for name in se.COUNTIES),
             "Total 6700 670 0 0 134 10.00% 20.00%"]
    def entry(feed, data, native=None):
        return {"source": {"url": precinct.URLS[feed]}, "status": "reported",
                "data": {"complete_native_query": data, "native_lines": native}}

    archive = entry(archive_feed, rows)
    control = entry(control_feed, precinct.control_rows(lines, 2024), lines)
    units, counties = precinct.exports({archive_feed: archive, control_feed: control})
    assert counties[0]["archive_minus_control"] == 7
    assert units[0]["reconciliation"] == "county_control_disagrees"
    assert units[1]["unit_type"] == "central_mode_or_provisional"
    assert units[1]["unqualified_registration_cell"] is None
    assert units[2]["reconciliation"] == "reconciled"
    assert precinct.exports({archive_feed: archive})[0][0]["reconciliation"] == "not_reconciled_without_both_sources"
    current, _ = precinct.FEEDS[2026]
    current_units, current_counties = precinct.exports({current: entry(current, rows)})
    assert {row["reconciliation"] for row in current_units} == {"not_reconciled_without_both_sources"}
    assert all(row["county_control_ballots"] is None for row in current_counties)
    legacy, absent = precinct.FEEDS[2016]
    legacy_units, legacy_counties = precinct.exports({legacy: entry(legacy, rows)})
    assert absent not in precinct.URLS
    assert all(row["control_url"] is None for row in legacy_counties)
    assert legacy_counties[-1]["county_archive_ballots"] == 677
    assert {row["reconciliation"] for row in legacy_units} == {"not_reconciled_without_both_sources"}
    rows["AUTAUGA"].append(["TOWN HALL", 0, 0])
    with pytest.raises(ValueError, match="Invalid Alabama reporting unit"):
        precinct.exports({archive_feed: archive})


def test_current_alabama_control_discovery_requires_a_unique_general_report():
    path = "/sites/default/files/election-data/2026-12/2026%20General%20Total%20Ballots%20Cast.pdf"
    report = f'<a href="{path}">Total Ballots Cast - General Election</a>'
    others = (f'<a href="{path.replace("2026", "2024")}">Total Ballots Cast - General Election</a>'
              f'<a href="{path}">Total Ballots Cast - Primary Election</a>'
              '<a href="https://example.test/2026.pdf">Total Ballots Cast - General Election</a>')
    assert precinct.discover_control(others.encode()) is None
    assert precinct.discover_control((others + report).encode()) == "https://www.sos.alabama.gov" + path
    with pytest.raises(ValueError, match="Ambiguous"):
        precinct.discover_control((report + report.replace("2026-12", "2027-01")).encode())


def test_legacy_alabama_tall_sheet_keeps_printed_control_separate():
    rows = [
        ("Precinct", "Registered Voters", "Ballots Cast", "Voter Turnout"),
        ("Election day", 0, "25", "0.00 %"),
        ("Total:", 0, 0, "0.00 %"),
    ]
    assert precinct.early_tall_sheet(rows) == ([["Election day", 25, 0]], 0)
    with pytest.raises(ValueError, match="schema changed"):
        precinct.early_tall_sheet([rows[0], (*rows[1], 100), rows[2]])
    with pytest.raises(ValueError, match="Unexpected XML declarations"):
        precinct.early_xml_sheet(b'<!DOCTYPE test [<!ENTITY x "test">]><test>&x;</test>')


def test_legacy_alabama_unavailable_county_prevents_state_rollup():
    feed = precinct.FEEDS[2012][0]
    units = {name: [] if name == "HALE" else [["Town hall", 15, 0]] for name in se.COUNTIES}
    footer = {name: None if name == "HALE" else 0 if name == "FRANKLIN" else 15 for name in units}
    _, controls, audit = precinct.export_tables({feed: {
        "status": "reported", "source": {"url": precinct.URLS[feed]},
        "data": {"complete_native_query": units, "workbook_printed_totals": footer},
    }})
    assert controls[-1]["county"] == "TOTAL" and controls[-1]["county_archive_ballots"] is None
    by_county = {row["county"]: row for row in audit}
    assert by_county["HALE"]["workbook_decision"] == "reporting_units_unavailable"
    assert by_county["FRANKLIN"]["workbook_printed_ballots"] == 0
    assert by_county["FRANKLIN"]["workbook_decision"] == "workbook_internal_discrepancy"
    assert by_county["FRANKLIN"]["unit_sum_minus_workbook_printed"] == 15


def test_jefferson_crosstab_keeps_aggregate_out_of_reporting_units():
    rows = [
        ("Contest Title", "Party Code", "Candidate Name", "Total Of Registered Voters", "Town hall", "ABSENTEE"),
        ("REGISTERED VOTERS - TOTAL", "", "Registered Voters - Total", 35, 35, None),
        ("BALLOTS CAST - TOTAL", "", "Ballots Cast - Total", 25, 20, 5),
    ]
    assert precinct.mixed_crosstab(iter(rows), jefferson=True) == (
        [["Town hall", 20, 35], ["ABSENTEE", 5, None]], 25)
    with pytest.raises(ValueError, match="Ambiguous"):
        precinct.mixed_crosstab(iter([*rows, rows[-1]]), jefferson=True)


def test_alabama_mixed_csv_uses_native_measure_codes_not_column_name_or_candidate_votes():
    header = ",".join(precinct.MIXED_CSV_HEADER) + "\n"
    register = "Chambers,,0002,001,000263,,REGISTERED VOTERS - TOTAL,Registered Voters - Total,STROUD,\n"
    ballots = "Chambers,,0003,001,000132,,BALLOTS CAST - TOTAL,Ballots Cast - Total,STROUD,\n"
    central = ballots.replace("STROUD", "ABSENTEE").replace("000132", "000012")
    candidate = "Chambers,,0101,001,000100,DEM,GOVERNOR,Parker Griffith,STROUD,\n"
    body = header + register + ballots + central + candidate
    assert precinct.mixed_csv_units(body.encode(), "CHAMBERS") == [
        ["STROUD", 132, 263], ["ABSENTEE", 12, None],
    ]
    for changed in (
        body + ballots,
        body.replace("0003,001", "0013,001", 1),
        body.replace("Ballots Cast - Total", "Registered Voters - Total", 1),
    ):
        with pytest.raises(ValueError, match="Ambiguous"):
            precinct.mixed_csv_units(changed.encode(), "CHAMBERS")
    with pytest.raises(ValueError, match="county or election"):
        precinct.mixed_csv_units(body.replace("Chambers", "Winston", 1).encode(), "CHAMBERS")


def test_alabama_2014_rechecks_pre_csv_results_even_in_same_week(tmp_path, monkeypatch):
    feed = precinct.FEEDS[2014][0]
    legacy = {"status": "reported", "data": {"complete_native_query": {}},
              "archive_check_week_utc": "2026-11-16"}
    collector = results_intake.Collector(
        tmp_path, {feed: legacy}, {"urls": [], "prefixes": [], "hosts": []},
        datetime(2026, 11, 21, tzinfo=timezone.utc))
    calls = []

    def acquire(url):
        calls.append(url)
        return b"fixture", {"origin": "fixture"}

    monkeypatch.setattr(collector, "acquire", acquire)
    monkeypatch.setattr(precinct, "parse", lambda *_: {"mixed_csv_participation_rows_qualified": True})
    accepted = precinct.collect(collector, feed, reuse_checked_week=True)
    assert accepted["status"] == "reported" and calls == [precinct.URLS[feed]]
    collector.prior[feed] = accepted
    assert precinct.collect(collector, feed, reuse_checked_week=True) == accepted
    assert calls == [precinct.URLS[feed]]


def test_current_alabama_control_is_collected_only_after_discovery(tmp_path, monkeypatch):
    feed = precinct.CURRENT_CONTROL
    path = "/sites/default/files/election-data/2026-12/2026%20General%20Total%20Ballots%20Cast.pdf"
    url = "https://www.sos.alabama.gov" + path
    state = {"urls": [], "prefixes": [], "hosts": []}
    collector = results_intake.Collector(tmp_path, {}, state, datetime(2026, 12, 12, tzinfo=timezone.utc))
    calls = []
    bodies = {precinct.INDEX: b"<p>No report yet</p>"}

    def acquire(target):
        calls.append(target)
        if target not in bodies:
            raise results_intake.IntakeError("source_stopped", "test denial")
        return bodies[target], {"origin": "fixture"}

    monkeypatch.setattr(collector, "acquire", acquire)
    missing = precinct.collect(collector, feed)
    assert missing["status"] == "report_not_linked" and calls == [precinct.INDEX]

    lines = ["General Election - November 3, 2026", "Official Total Ballots Cast",
             "County Voters Ballots Cast Ballots Ballots Ballots Registered Voters Total Ballots",
             *(f"{name.replace('_', ' ')} 100 10 0 0 2 10.00% 20.00%" for name in se.COUNTIES),
             "Total 6700 670 0 0 134 10.00% 20.00%"]
    bodies[precinct.INDEX] = f'<a href="{path}">Total Ballots Cast - General Election</a>'.encode()
    bodies[url] = b"fixture PDF"

    def parse(body, identity):
        assert body == bodies[url] and identity == feed
        return {"native_lines": lines, "complete_native_query": precinct.control_rows(lines, 2026),
                "participation_observation_qualified": False}

    monkeypatch.setattr(precinct, "parse", parse)
    accepted = precinct.collect(collector, feed)
    assert accepted["status"] == "reported" and calls[-2:] == [precinct.INDEX, url]
    collector.prior[feed] = accepted
    del bodies[url]
    retained = precinct.collect(collector, feed)
    assert retained["status"] == "retained_after_failure"
    _, county = precinct.exports({feed: retained})
    assert county[-1]["county_control_ballots"] == 670 and county[-1]["control_url"] == url
