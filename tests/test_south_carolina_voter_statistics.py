import csv
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

import pytest

from scripts import results_intake as intake, south_carolina_voter_statistics as sc


def csv_body(rows):
    buffer = StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode()


def native_tables(ballots=2, registration=3):
    return csv_body([
        ["", "", "Total Ballots Cast", "Registered Voters"], [""] * 4,
        ["State", "South Carolina", ballots * 46, registration * 46],
        *[row for county in sc.COUNTIES for row in [
            ["County", county, ballots, registration],
            ["Precinct", "Shared place label", ballots - 1, registration],
            ["Precinct", "Provisional", 1, 0],
        ]],
    ])


def test_catalog_does_not_promote_partial_statewide_alternatives(monkeypatch):
    monkeypatch.setattr(sc, "YEARS", (2024, 2026))
    monkeypatch.setattr(sc, "REVIEWED", {2024})
    def row(contest, county, stage="General"):
        return [contest, "58", "2024-11-05T00:00:00Z", stage, "", "", "", "568", "Voting Statistics",
                "", "1", "State", "South Carolina", "1", "Total Ballots Cast", "", "", "5",
                "County", county, "", "false", "1", "", "", "1"]
    body = csv_body([sc.CATALOG_COLUMNS, *[row("7075", county) for county in sc.COUNTIES],
                     row("7099", "York"), row("8000", "York", stage="Special")])
    results, audit = sc.decisions(sc.catalog(body), {})
    assert results[2024]["contest"] == "7075"
    assert audit[0]["native_candidate_contests"] == "7075;7099"
    assert audit[1]["status"] == "no_statewide_table"
    with pytest.raises(sc.IntakeError, match="no longer unique"):
        sc.decisions(sc.catalog(body) + [{**results[2024], "contest": "9000"}], {})


def test_table_checks_both_parent_sums_and_keeps_central_rows():
    rows = sc.table(native_tables())
    with pytest.raises(ValueError, match="county controls"):
        sc.table(native_tables().replace(b"Precinct,Provisional,1,0", b"Precinct,Provisional,0,0", 1))
    with pytest.raises(ValueError, match="statewide table control"):
        sc.table(native_tables().replace(b"State,South Carolina,92,138", b"State,South Carolina,93,138"))
    assert sc.rows_by_scope(rows)["York"][1][-1][1:] == ("Provisional", 1, 0)


def test_revisions_noop_and_last_good_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "YEARS", (2024,))
    monkeypatch.setattr(sc, "REVIEWED", {2024})
    source = sc.table_url("7075")
    control_url = sc.controls.URLS[sc.controls.SC]
    original = {sc.CATALOG: b"index", source: native_tables(), control_url: b"2"}
    monkeypatch.setattr(sc, "catalog", lambda _: [
        {"year": 2024, "event": "58", "contest": "7075", "counties": sc.COUNTIES}])
    monkeypatch.setattr(sc.controls, "parse", lambda body, _: {"complete_native_query": [
        {"year": 2024, "reported_participation": int(body) * 46, "reported_registered": 150,
         "numerator_basis": "ballots_cast"}]})

    def acquire(_, spec, *, access_guard):
        body = original[spec["url"]]
        return body, {"origin": "fixture", **intake.pin(body)}

    def collect(old, day, *, weekly=False):
        with patch.object(intake.Store, "acquire", acquire):
            collector = intake.Collector(tmp_path, {sc.FEED: old} if old else {},
                                         {"urls": [], "prefixes": [], "hosts": []},
                                         datetime(2026, 11, day, tzinfo=timezone.utc))
            return sc.collect(collector, sc.FEED, reuse_checked_week=weekly)

    before = collect(None, 16)
    assert before["status"] == "reported"
    assert collect(before, 17, weekly=True) == before
    assert collect(before, 17)["data"] == before["data"]
    for day, count in [(18, 4), (19, 1)]:
        original[source] = native_tables(ballots=count)
        original[control_url] = str(count).encode()
        before = collect(before, day)
        rows, audit = sc.exports({sc.FEED: before})
        assert before["status"] == "reported" and rows[0]["reported_ballots_cast"] == count * 46
        assert rows[0]["qualified_rate_pct"] is None and audit[0]["registration_difference"] == -12
    original[source] = native_tables(ballots=2)
    after = collect(before, 20)
    assert after["status"] == "retained_after_failure" and after["data"] == before["data"]
