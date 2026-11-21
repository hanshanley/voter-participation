import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.louisiana_group_history import (
    ELECTION_DATES_URL, INDEXES, STATE_INDEX_URL, _Catalog, _group_vector, collect, collect_year, federal_events,
    precinct_rows,
)
from scripts.participation_intake.engine import IntakeError


class LouisianaGroupHistoryTest(unittest.TestCase):
    def test_selects_only_exact_november_federal_event_and_official_status(self):
        body = json.dumps({"Dates": {"Date": [
            {"ElectionDate": "12/07/2024", "PKElectionID": "332", "ResultsOfficial": "1",
             "PostElectionStatsAvailable": "1"},
            {"ElectionDate": "11/05/2024", "PKElectionID": "331", "ResultsOfficial": "1",
             "PostElectionStatsAvailable": "1"},
            {"ElectionDate": "11/03/2026", "PKElectionID": "344", "ResultsOfficial": "0",
             "PostElectionStatsAvailable": "1"},
        ]}}).encode()
        found = [(event, row["PKElectionID"], allowed) for event, row, allowed in federal_events(body, 2024, 2026)]
        self.assertEqual(found, [(date(2024, 11, 5), "331", True), (date(2026, 11, 3), "344", False)])

    def test_year_post_requires_report_for_selected_year_and_exact_scope(self):
        first = b'''<input name="__VIEWSTATE" type="hidden" value="x">
        <input name="__VIEWSTATEGENERATOR" type="hidden" value="y">
        <input name="__EVENTVALIDATION" type="hidden" value="z">
        <select name="cboYear"><option selected value="2026">2026</option>
        <option value="2024">2024</option></select>'''
        self.assertIn(b"cboYear=2024", _Catalog(STATE_INDEX_URL, first).selection(2024))
        with self.assertRaisesRegex(ValueError, "did not select 2024"):
            _Catalog(STATE_INDEX_URL, first).workbook("statewide", date(2024, 11, 5))
        body = b'''<select name="cboYear"><option selected value="2024">2024</option></select>
        <a href="/Data/Post_Election_Statistics/statewide/2024_1105_sta.xls">Excel</a>
        <a href="/Data/Post_Election_Statistics/statewide/2024_1105_sta.pdf">PDF</a>
        <a href="/Data/Post_Election_Statistics/statewide/2024_1207_sta.xls">Runoff</a>'''
        catalog = _Catalog(STATE_INDEX_URL, body)
        self.assertTrue(catalog.workbook("statewide", date(2024, 11, 5)).endswith("2024_1105_sta.xls"))
        self.assertIsNone(catalog.workbook("parish", date(2024, 11, 5)))

    def test_stopped_host_prevents_transport(self):
        with tempfile.TemporaryDirectory() as work, patch("scripts.louisiana_group_history.build_opener") as build:
            with self.assertRaisesRegex(ValueError, "already stopped"):
                collect(work, 2008, 2024, stopped={"urls": [], "prefixes": [], "hosts": ["voterportal.sos.la.gov"]})
            build.return_value.open.assert_not_called()
            self.assertEqual(json.loads((Path(work) / "inventory.json").read_text())["events"], {})

    def test_group_discrepancies_not_hidden_by_balanced_marginals(self):
        # Overall race and party totals balance, but one party's race counts were swapped.
        from scripts.results_native_louisiana import FIELDS
        counts = dict(zip(FIELDS, map(str, (4, 2, 1, 1, 2, 0, 1, 1, 2, 1, 1, 0, 0, 0, 0, 0))))
        rows = {10: counts, 11: {"B": "# VOTING", **dict.fromkeys(FIELDS, "0")},
                12: {"B": "% VOTING", **dict.fromkeys(FIELDS, "0.00")}}
        with self.assertRaisesRegex(ValueError, "party-by-race subtotals differ"):
            _group_vector(rows, 10, "PAR 01")

    def test_scoped_revisions_unchanged_source_and_last_good_retention(self):
        feed = "LA-2024-general-election-group-history"
        collector = Mock(prior={}, offline=False, attempts=[], now=datetime(2026, 11, 21, tzinfo=timezone.utc))
        record = {"ElectionDate": "11/05/2024", "PKElectionID": "331", "ResultsOfficial": "1",
                  "PostElectionStatsAvailable": "1"}
        bodies = {ELECTION_DATES_URL: json.dumps({"Dates": {"Date": [record]}}).encode()}
        workbook = {}
        for scope, (url, suffix) in INDEXES.items():
            path = f"/Data/Post_Election_Statistics/{scope}/2024_1105_{suffix}.xls"
            workbook[scope] = "https://electionstatistics.sos.la.gov" + path
            bodies[url] = f'''<select name="cboYear"><option selected value="2024">2024</option></select>
                <a href="{path}">Workbook</a>'''.encode()
            bodies[workbook[scope]] = b"10"

        def acquire(url):
            body = bodies[url]
            if isinstance(body, Exception):
                raise body
            return body, {}

        def check(statewide, parishes):
            if statewide != parishes:
                raise ValueError("Workbooks disagree")

        collector.acquire.side_effect = acquire
        with patch("scripts.louisiana_group_history.workbook_facts", side_effect=lambda body, *args: int(body)), \
                patch("scripts.louisiana_group_history.reconcile", side_effect=check):
            for value in (10, 11, 9):
                for url in workbook.values():
                    bodies[url] = str(value).encode()
                entry = collect_year(collector, feed)
                self.assertEqual(entry["data"]["workbooks"], dict.fromkeys(INDEXES, value))
                collector.prior[feed] = entry
            bodies[STATE_INDEX_URL] += b"<!-- volatile catalog text -->"
            self.assertEqual(collect_year(collector, feed), entry)
            bodies[workbook["parish"]] = b"8"
            retained = collect_year(collector, feed)
            self.assertEqual((retained["status"], retained["error_stage"]), ("retained_after_failure", "reconciliation"))
            self.assertEqual(retained["data"], entry["data"])
            bodies[workbook["parish"]] = IntakeError("source_stopped", "403")
            retained = collect_year(collector, feed)
            self.assertEqual((retained["status"], retained["error"]), ("retained_after_failure", "source_stopped"))
            self.assertEqual(retained["data"], entry["data"])
            collector.prior[feed] = retained
            collector.acquire.reset_mock()
            self.assertEqual(collect_year(collector, feed, reuse_checked_week=True), retained)
            collector.acquire.assert_not_called()

    def test_native_precinct_counts_keep_disagreeing_statewide_control_separate(self):
        election = date(2016, 11, 8)
        areas = [f"PAR {number:02}" for number in range(1, 65)]
        counts = lambda value: {"voters_participating": {"total": value}}
        books = {"statewide": {"STATE": ["Louisiana", "Sheet1", 11, counts(65)],
                               **{area: ["", "", 0, counts(2 if i == 0 else 1)]
                                  for i, area in enumerate(areas)}},
                 "parish": {area: [area, "Sheet1", 11, counts(1), [[area + " W 01 P 01", "", 15, 1]]]
                            for area in areas}}
        sources = {scope: {"url": scope, "sha256": ""} for scope in INDEXES}
        rows = list(precinct_rows(election, {"PKElectionID": "284"}, books, sources))
        self.assertEqual(len(rows), 64)
        self.assertEqual(rows[0]["control_status"], "parish_rows_reconcile_statewide_control_differs")
        self.assertEqual(rows[0]["voters_voting"], 1)
        self.assertEqual(rows[1]["control_status"], "parish_and_statewide_counts_agree")
        self.assertTrue(all(row["geometry_qualified"] == row["rate_qualified"] == "false" for row in rows))
        books["parish"][areas[0]][4][0][3] = 2
        with self.assertRaisesRegex(ValueError, "differ from the parish"):
            list(precinct_rows(election, {"PKElectionID": "284"}, books, sources))
