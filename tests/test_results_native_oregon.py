import copy
import gzip
import html
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
from scripts import results_native_oregon as adapter
from scripts.participation_intake.contract import encoded, pin
from scripts.results_granular import project


def page(rows, status="Unofficial"):
    counties = "".join(
        '<a id="MainContent_rptVoterTurnoutSW_lnkCountyName_' + str(ordinal)
        + '" href="ResultsSW.aspx?type=CTYALL&amp;cty=' + row["CountyID"] + '">'
        + html.escape(row["CountyName"]) + '</a><canvas id="Turnout' + row["CountyID"]
        + '"></canvas><span class="int">'
        + (f'{100 * row["calcVoterTurnout"] / row["Voters"]:.2f}' if row["Voters"] else "0.00").split(".")[0]
        + '</span><span class="dec">.'
        + (f'{100 * row["calcVoterTurnout"] / row["Voters"]:.2f}' if row["Voters"] else "0.00").split(".")[1]
        + '%</span>' for ordinal, row in enumerate(rows))
    return (
        '<title>Oregon Secretary of State</title>'
        '<input id="hidElectionDate" value="11/3/2026" />'
        '<input id="hidElectionType" value="General" />'
        '<div class="col header-box1"><h3>' + status
        + '</h3><h2>General Election<br/>November 3, 2026</h2></div>'
        '<span class="vt-text">Ballots Counted</span><span class="vt-number">'
        + str(sum(row["calcVoterTurnout"] for row in rows))
        + '</span><span class="vt-text">Active Registered Voters</span>'
        '<span class="vt-number">' + str(sum(row["Voters"] for row in rows))
        + '</span><div class="next-count">Results last updated: 11/15/2026 | 1:00 AM PT</div>'
        + counties).encode()


class OregonNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((HERE / "fixtures/oregon-accepted.json").read_bytes())

    def setUp(self):
        self.templates = copy.deepcopy(self.fixture["templates"])
        self.rows = copy.deepcopy(self.fixture["native_api_document"]["d"])
        self.body = encoded({"d": self.rows})
        self.page = page(self.rows)

    def parse(self, body=None, templates=None, source_page=None):
        def acquire(url):
            self.assertEqual(url, adapter.PAGE_URL)
            value = self.page if source_page is None else source_page
            return value, {"url": url, **pin(value)}
        return adapter.statistics(
            self.body if body is None else body,
            self.templates if templates is None else templates,
            adapter.API_URL, acquire=acquire)

    def baseline(self):
        frame = {"counties": [row["id"] for row in self.templates],
                 "precincts": [], "nongeographic": []}
        return {
            "index.json": encoded({"states": {"OR": {"file": "OR.json.gz"}}}),
            "OR.json.gz": gzip.compress(encoded({
                "records": self.templates, "views": {"available": frame}}), mtime=0),
        }

    def test_complete_real_county_facts_project_and_repeat(self):
        data = self.parse()
        self.assertEqual(len(data["updates"]), 36)
        self.assertEqual(sum(row["value"] for row in data["updates"]), 1992463)
        baseline = self.baseline()
        entry = {"status": "reported", "source": {"url": adapter.API_URL, **pin(self.body)},
                 "data": data}
        after, changes = project(baseline, {"OR-native": entry})
        self.assertEqual(len(changes), 36)
        self.assertEqual(sum(row["previous"] != row["current"] for row in changes), 27)
        rows = json.loads(gzip.decompress(after["OR.json.gz"]))["records"]
        for before, current in zip(self.templates, rows):
            for key in ("id", "geography", "election", "measure"):
                self.assertEqual(before[key], current[key])
            self.assertFalse(current["denominator"]["qualified"])
            self.assertIsNone(current["view"]["reported_pct"])
            self.assertFalse(current["view"]["maps_approved"])
            self.assertIsNone(current["source_clock"]["timezone"])
            self.assertIsNone(current["reporting_status"]["complete"])
        again = {**entry, "data": self.parse(templates=rows)}
        repeated, changes = project(after, {"OR-native": again})
        self.assertEqual(repeated, after)
        self.assertFalse(changes)

    def test_zero_is_a_reported_count_but_missing_or_boolean_is_not(self):
        self.rows[0]["calcVoterTurnout"] = 0
        data = self.parse(body=encoded({"d": self.rows}), source_page=page(self.rows))
        self.assertEqual(next(row["value"] for row in data["updates"]
                              if row["native"]["native_county_id"] == self.rows[0]["CountyID"]), 0)
        for value in (None, False, "0"):
            with self.subTest(value=value):
                self.rows[0]["calcVoterTurnout"] = value
                with self.assertRaises(ValueError):
                    self.parse(body=encoded({"d": self.rows}))

    def test_changed_election_measure_county_or_header_fails_closed(self):
        for bad in (
            self.page.replace(b"11/3/2026", b"11/3/2024"),
            self.page.replace(b"Ballots Counted", b"Candidate Votes"),
            self.page.replace(b">Baker</a>", b">Different County</a>"),
            self.page.replace(b">1992463</span>", b">1992464</span>"),
        ):
            with self.subTest(page=pin(bad)):
                with self.assertRaises(ValueError):
                    self.parse(source_page=bad)
        self.rows[1]["CountyID"] = self.rows[0]["CountyID"]
        with self.assertRaises(ValueError):
            self.parse(body=encoded({"d": self.rows}))

    def test_initial_frame_and_consistently_forged_identity_are_rejected(self):
        self.templates[0]["count"]["value"] += 1
        with self.assertRaises(ValueError):
            self.parse()
        self.templates = copy.deepcopy(self.fixture["templates"])
        self.templates[0]["geography"]["id"] += "-forged"
        with self.assertRaises(ValueError):
            self.parse()

    def test_source_status_transition_and_later_count_correction_keep_holds(self):
        first = self.parse()
        entry = {"status": "reported", "source": {"url": adapter.API_URL, **pin(self.body)},
                 "data": first}
        after, _ = project(self.baseline(), {"OR-native": entry})
        templates = json.loads(gzip.decompress(after["OR.json.gz"]))["records"]
        self.rows[0]["calcVoterTurnout"] += 1
        self.rows[0]["CurrentDateTime"] = "11/15/2026 1:00:00 AM"
        body = encoded({"d": self.rows})
        data = self.parse(body=body, templates=templates, source_page=page(self.rows, "Official"))
        projected, _ = project(after, {"OR-native": {
            "status": "reported", "source": {"url": adapter.API_URL, **pin(body)}, "data": data}})
        rows = json.loads(gzip.decompress(projected["OR.json.gz"]))["records"]
        self.assertTrue(all(not row["denominator"]["qualified"] for row in rows))
        self.assertTrue(all(row["view"]["source_status_literal"] == "Official" for row in rows))
        self.assertTrue(all(row["reporting_status"]["complete"] is None for row in rows))
        self.assertTrue(all(row["view"]["maps_approved"] is False for row in rows))

    def test_regressed_clock_and_mixed_projected_vector_are_rejected(self):
        self.rows[0]["CurrentDateTime"] = "11/3/2026 1:00:00 AM"
        with self.assertRaises(ValueError):
            self.parse(body=encoded({"d": self.rows}))
        entry = {"status": "reported", "source": {"url": adapter.API_URL, **pin(self.body)},
                 "data": self.parse()}
        after, _ = project(self.baseline(), {"OR-native": entry})
        templates = json.loads(gzip.decompress(after["OR.json.gz"]))["records"]
        templates[0]["view"]["native_record"]["record"]["calcVoterTurnout"] += 1
        with self.assertRaises(ValueError):
            self.parse(templates=templates)


if __name__ == "__main__":
    unittest.main()
