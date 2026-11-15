import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import results_native_broome as source
from scripts.results_intake import Collector


FIXTURE = Path(__file__).resolve().parent / "fixtures/broome-contest-2026.json"


def query():
    return json.loads(FIXTURE.read_bytes())


def factual_declarations(value=None):
    """Synthetic declarations and text, not copies of publisher HTML or clients."""
    value = copy.deepcopy(value or query())
    header = "\n".join((
        "** Protected", "Broome County", "2026 General Election", "November 03, 2026",
        "Results by Municipality, Ward, and District", source.CONTEXT, "Vote For 1",
        "Write-in Under Votes Over Votes Whole Number (Ballots Cast)Eligible Voters Turnout (%)",
    ))
    pages = []
    for page in range(1, 8):
        lines = [header]
        for row in value["rows"]:
            if row["page"] == page:
                line = "{} 0 0 0 0 0 0 0 0 {} {}".format(
                    row["native_label"], row["ballots_cast_literal"],
                    row["eligible_voters_literal"])
                if row["printed_pct"] is not None:
                    line += " " + row["printed_pct"] + " %"
                lines.append(line)
        pages.append("\n".join(lines))
    summary = "\n".join((
        "2026 General Election 1 Last Updated: "
        + value["summary_control"]["source_clock"]["literal"],
        "Broome County", "2026 General Election", "November 03, 2026",
        "Summary Results Report", source.CONTEXT, "Vote for 1",
        "Election Districts Reported 126 of 126",
        "Total Ballots Cast " + str(value["summary_control"]["total_ballots_cast"]),
        "Comptroller",
    ))
    election = copy.deepcopy(value["publisher_edition"])
    election.update(
        name=[{"languageId": "en", "text": "2026 General Election"}],
        dateText=[{"languageId": "en", "text": "November 3, 2026"}],
        isProduction=True, isPrimary=False, ballotsCast=0.0, totalVoters=0.0,
        publicReportCategories=[{"reports": [
            {"reportName": source.REPORT_NAME, "blobName": "Ballot_2026.PDF"},
            {"reportName": source.SUMMARY_NAME, "blobName": "Summary_2026.PDF"},
        ]}],
    )
    client_url = source.ORIGIN + "/results/public/main-FACTS.js"
    chunk_url = source.ORIGIN + "/results/public/chunk-FACTS.js"
    client = "\n".join((
        'api:{endpoint:"/results/public/api"',
        'getElection(a,p){return this.http.get(`${this.baseUrl}/elections/${a}/${p}`)',
        'g=a.paramMap.get("name"),p=a.paramMap.get("id")',
        "this.appService.loadElection(g,p)",
        "this.electionService.getElection(o.jurisdictionName,o.electionId)",
        'imageCdn:"/cdn/results/"',
        'path:"reports",loadComponent:()=>import("./chunk-FACTS.js")',
    )).encode()
    return {
        source.AUTHORITY_URL: (
            '<p>2026 General</p><a href="{0}">Unofficial</a>'
            '<a href="{0}">Results</a>'.format(source.DASHBOARD)).encode(),
        source.DASHBOARD: (
            '<base href="/results/public/"><script src="main-FACTS.js"></script>').encode(),
        client_url: client,
        chunk_url: (
            'this.toCategoryView(h,i.id,o,m)\nblobName:i+"/"+e.blobName\n'
            "o.baseImageCdn+o.report.blobName").encode(),
        source.API_URL: source.encoded(election),
        source.report_url(election, source.REPORT_NAME): source.encoded(pages),
        source.report_url(election, source.SUMMARY_NAME): source.encoded([summary]),
    }


class BroomeSourceTests(unittest.TestCase):
    def collect(self, bodies, prior=None, stopped=None):
        with tempfile.TemporaryDirectory() as work:
            collector = Collector(work, prior or {}, stopped if stopped is not None else
                                  {"urls": [], "hosts": [], "prefixes": []},
                                  datetime(2026, 11, 15, tzinfo=timezone.utc), offline=True)
            collector.bodies = {
                url: (body, {"origin": "synthetic_factual_fixture", **source.pin(body)})
                for url, body in bodies.items()
            }
            with patch.object(source, "pdf_pages", side_effect=lambda body, limit:
                              json.loads(body)[:limit]), patch(
                    "socket.socket", side_effect=AssertionError("Unexpected network")):
                result = source.collect_statistics(collector)
            return result

    def test_complete_scoped_query_preserves_zero_excess_and_unknown_clock(self):
        value = source.validate_query(query())
        self.assertEqual(value["rows"][-1]["ballots_cast"], 68955)
        units = [row for row in value["rows"] if row["kind"] == "reporting_unit"]
        self.assertEqual(sum(row["ballots_cast"] == 0 for row in units), 1)
        excess, = [row for row in units if row["ballots_cast"] > row["eligible_voters"]]
        self.assertEqual((excess["ballots_cast"], excess["eligible_voters"],
                          excess["printed_pct"]), (611, 122, "500.82"))
        self.assertEqual(value["source_clock"], {"literal": None, "timezone": None})
        self.assertFalse(any(value["qualification"].values()))

    def test_default_capture_ignores_backend_zero_and_retains_full_query(self):
        result = self.collect(factual_declarations())
        self.assertEqual(result["status"], "reported")
        self.assertEqual(len(result["data"]["complete_native_query"]["rows"]), 144)
        self.assertEqual(result["data"]["updates"], [])
        self.assertIs(result["data"]["numerical_data_qualified"], False)
        self.assertEqual(result["data"]["complete_native_query"]["rows"][-1]["ballots_cast"],
                         68955)

    def test_repeat_and_failure_keep_original_observation_metadata(self):
        bodies = factual_declarations()
        first = self.collect(bodies)
        prior = {source.IDENTITY: first}
        self.assertEqual(self.collect(bodies, prior), first)
        broken = dict(bodies)
        broken.pop(next(url for url in bodies if "/cdn/results/" in url))
        retained = self.collect(broken, prior)
        self.assertEqual(retained["status"], "retained_after_failure")
        for key in ("data", "source", "first_observed_at"):
            self.assertEqual(retained[key], first[key])

    def test_scheduled_intake_exports_full_query_and_carries_prior(self):
        from scripts import results_intake as intake
        from test_results_intake import fixture
        import zipfile

        bodies = factual_declarations()
        initialize = Collector.__init__

        def warm(collector, *args, **kwargs):
            initialize(collector, *args, **kwargs)
            collector.bodies.update({
                url: (body, {"origin": "synthetic_factual_fixture", **source.pin(body)})
                for url, body in bodies.items()
            })

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            registry = fixture(root)
            with patch.object(Collector, "__init__", warm), patch.object(
                    source, "pdf_pages", side_effect=lambda body, limit:
                    json.loads(body)[:limit]), patch(
                    "socket.socket", side_effect=AssertionError("Unexpected network")):
                first = root / "first"
                intake.collect(registry, first, offline=True)
                state = intake.read(first / "state.json")
                captured = state["feeds"][source.IDENTITY]
                self.assertEqual(captured["status"], "reported")
                self.assertEqual(captured["data"]["complete_native_query"]["rows"], query()["rows"])
                with zipfile.ZipFile(first / "complete-results.zip") as archive:
                    packaged = json.loads(archive.read("inputs/selected-source-facts.json"))
                    self.assertEqual(packaged["feeds"][source.IDENTITY], captured)
                    for name in ("scripts/results_native_broome.py",
                                 "tests/test_results_native_broome.py",
                                 "tests/fixtures/broome-contest-2026.json"):
                        self.assertEqual(archive.read("code/" + name),
                                         (intake.ROOT / name).read_bytes())
                    archive.extractall(root / "packet")
                intake.replay(root / "packet", root / "reproduced")
                observations = (first / "participation-observations.csv.gz").read_bytes()
                self.assertNotIn(source.IDENTITY.encode(), intake.gzip.decompress(observations))
                config = intake.read(registry)
                config["source_stops"]["urls"].append(source.API_URL)
                intake.write(registry, config)
                second = root / "second"
                intake.collect(registry, second, previous=state, offline=True)
                retained = intake.read(second / "state.json")["feeds"][source.IDENTITY]
                self.assertEqual(retained["status"], "retained_after_failure")
                for key in ("data", "source", "first_observed_at"):
                    self.assertEqual(retained[key], captured[key])
                self.assertEqual((second / "participation-observations.csv.gz").read_bytes(),
                                 observations)

    def test_access_stop_refuses_warmed_child_and_preserves_last_good(self):
        bodies = factual_declarations()
        first = self.collect(bodies)
        result = self.collect(bodies, {source.IDENTITY: first},
                              {"urls": [source.API_URL], "hosts": [], "prefixes": []})
        self.assertEqual(result["status"], "retained_after_failure")
        self.assertEqual(result["data"], first["data"])

    def test_missing_protected_or_duplicate_rows_do_not_become_zero(self):
        for mutation in ("missing", "protected", "duplicate"):
            with self.subTest(mutation=mutation):
                value = query()
                if mutation == "missing":
                    value["rows"].pop(0)
                elif mutation == "protected":
                    value["rows"][0]["ballots_cast_literal"] = "**"
                else:
                    value["rows"][0] = copy.deepcopy(value["rows"][1])
                with self.assertRaises((ValueError, KeyError)):
                    source.validate_query(value)

    def test_changed_statistical_columns_and_wrong_election_refuse(self):
        bodies = factual_declarations()
        report_url = next(url for url in bodies if "Ballot_2026.PDF" in url)
        for old, new in (("Whole Number (Ballots Cast)Eligible Voters",
                          "Eligible Voters Whole Number (Ballots Cast)"),
                         ("November 03, 2026", "November 03, 2025")):
            changed = dict(bodies)
            changed[report_url] = changed[report_url].replace(old.encode(), new.encode())
            self.assertNotEqual(self.collect(changed)["status"], "reported")

    def test_publication_rollback_including_seventh_fractional_digit_refuses(self):
        previous = query()
        current = copy.deepcopy(previous)
        for key in source.EDITION_FIELDS[:3]:
            with self.subTest(key=key):
                current = copy.deepcopy(previous)
                previous["publisher_edition"][key] = "2026-11-09T21:52:26.3919102Z"
                current["publisher_edition"][key] = "2026-11-09T21:52:26.3919101Z"
                with self.assertRaisesRegex(ValueError, "backwards"):
                    source.edition_guard(current, previous)

    def test_unchanged_edition_changed_report_and_summary_mismatch_refuse(self):
        old = query()
        changed = copy.deepcopy(old)
        changed["report_source"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "without a new"):
            source.edition_guard(changed, old)
        changed["summary_control"]["total_ballots_cast"] = 69086
        with self.assertRaisesRegex(ValueError, "summary control"):
            source.validate_query(changed)

    def test_successor_true_zero_updates_full_query_without_qualifying_turnout(self):
        old = query()
        updated = copy.deepcopy(old)
        unit = updated["rows"][0]
        decrement = unit["ballots_cast"]
        unit.update(ballots_cast=0, ballots_cast_literal="0", printed_pct="0.00")
        parent = next(row for row in updated["rows"] if row["kind"] == "control")
        for row in (parent, updated["rows"][-1]):
            row["ballots_cast"] -= decrement
            row["ballots_cast_literal"] = str(row["ballots_cast"])
            row["printed_pct"] = str((source.Decimal(row["ballots_cast"]) * 100
                / row["eligible_voters"]).quantize(source.Decimal(".01"),
                                                   rounding=source.ROUND_HALF_UP))
        updated["summary_control"]["total_ballots_cast"] -= decrement
        updated["publisher_edition"]["publishDate"] = "2026-11-10T00:00:00Z"
        source.edition_guard(updated, old)
        first = self.collect(factual_declarations(old))
        successor = self.collect(factual_declarations(updated), {source.IDENTITY: first})
        self.assertEqual(successor["status"], "reported")
        self.assertEqual(successor["data"]["complete_native_query"]["rows"][0]["ballots_cast"], 0)
        self.assertIs(successor["data"]["numerical_data_qualified"], False)
        self.assertEqual(successor["data"]["updates"], [])

    def test_guessed_report_path_and_missing_official_declaration_refuse(self):
        bodies = factual_declarations()
        changed = dict(bodies)
        changed[source.AUTHORITY_URL] = b"<p>2026 General, no declared dashboard</p>"
        self.assertNotEqual(self.collect(changed)["status"], "reported")
        election = json.loads(bodies[source.API_URL])
        election["publicReportCategories"][0]["reports"][0]["blobName"] = "../secret.PDF"
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            source.report_url(election, source.REPORT_NAME)


if __name__ == "__main__":
    unittest.main()
