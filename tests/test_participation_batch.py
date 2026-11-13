import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

from scripts.participation_batch import (
    compile_reporting, compressed, discover, display, execute, native_baseline_files,
)
from scripts.participation_intake.adapters import adapt
from scripts.participation_intake.contract import STATES, digest, encoded, pin
from scripts.participation_intake.engine import Store


class NativeResponseTraceTests(unittest.TestCase):
    def test_native_viewer_redirect_trace_is_private_for_success_and_conditional_cache(self):
        class Response(io.BytesIO):
            status = 200
            headers = {"ETag": "synthetic-etag", "Content-Type": "text/html"}

            def geturl(self):
                return "https://example.gov/viewer.html?file=%2Fnative.pdf"

        with tempfile.TemporaryDirectory() as temporary:
            store = Store(temporary)
            self.addCleanup(store.db.close)
            source = dict(url="https://example.gov/declared-result")
            trace = {"stale": "discard"}
            response = Response(b"native viewer")
            with patch("urllib.request.OpenerDirector.open", return_value=response):
                body, receipt = store.acquire(source, response_trace=trace)
            self.assertEqual(body, b"native viewer")
            self.assertEqual(trace, dict(final_url=response.geturl(), status=200, content_type="text/html"))
            self.assertNotIn("final_url", receipt)
            self.assertNotIn("content_type", receipt)
            unchanged = urllib.error.HTTPError(response.geturl(), 304, "Not Modified", {}, None)
            trace["stale"] = "discard"
            with patch("urllib.request.OpenerDirector.open", side_effect=unchanged):
                cached, cached_receipt = store.acquire(source, response_trace=trace)
            self.assertEqual(cached, body)
            self.assertEqual(trace, dict(final_url=response.geturl(), status=304, content_type=None))
            self.assertNotIn("final_url", cached_receipt)
            self.assertEqual(receipt["sha256"], cached_receipt["sha256"])

    def test_access_stop_clears_stale_trace_and_prevents_any_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(temporary)
            self.addCleanup(store.db.close)
            source = dict(url="https://example.gov/declared-result")
            store.db.execute("INSERT INTO inputs VALUES(?,?,?,?,?)",
                             (source["url"], None, None, None, "HTTP 403"))
            store.db.commit()
            trace = {"final_url": "https://example.gov/old-viewer?file=old.pdf"}
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
                with self.assertRaisesRegex(ValueError, "Recorded access hold"):
                    store.acquire(source, response_trace=trace)
            self.assertEqual(trace, {})
            response = io.BytesIO(b"security challenge")
            response.status, response.headers = 200, {}
            response.geturl = lambda: "https://example.gov/security-check"
            source = dict(url="https://example.gov/second-result",
                          reject_body_patterns=["security challenge"])
            with patch("urllib.request.OpenerDirector.open", return_value=response):
                with self.assertRaisesRegex(ValueError, "Security challenge"):
                    store.acquire(source, response_trace=trace)
            self.assertEqual(trace, {})


class RoutineBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline, self.supplied, self.work = (self.root / name for name in ("baseline", "supplied", "work"))
        self.baseline.mkdir()
        self.supplied.mkdir()
        self.registry = self.root / "registry.json"
        self.native = encoded([dict(unit="one", label="One", ballots=0),
            dict(unit="two", label="Two", ballots="")])
        self.spec = dict(id="native-counts", classification="public_aggregate", adapter="json",
            review_evidence="Synthetic fixture: explicit reviewed native count and scope",
            primary_input="data", inputs=dict(data=dict(url="https://example.gov/counts.json")),
            election=dict(id="general-2026", year=2026, date="2026-11-03", type="general", qualification="native"),
            geography=dict(state_code="AR", level="reporting_unit"),
            measure=dict(id="native-ballots", kind="ballots_cast", mode="all_methods",
                literal="Native ballots", unit="source_reported_count"),
            columns=dict(geography_id="unit", geography_name="label", count="ballots"),
            expected_rows=2, source_clock=dict(literal="native clock", timezone=None),
            view=dict(identities={name: dict(county_id="parent", county="Native county",
                unit_key=name, unit=label, precinct=label, unit_kind="source_reporting_unit",
                geography_level="reporting_unit", maps_approved=False)
                for name, label in (("one", "One"), ("two", "Two"))}))
        rows = [display(row, self.spec) for row in adapt(self.spec, {"data": self.native},
            {"data": pin(self.native)}, {"literal": "native clock", "timezone": None}, {})]
        self.original_rows = rows
        files, states, coverage = {}, {}, {}
        for state in STATES:
            selected = rows if state == "AR" else []
            frame = dict(counties=[], precincts=[row["id"] for row in selected], nongeographic=[], qualified=True, holds=[])
            views = {name: copy.deepcopy(frame) for name in ("available", "official", "uf_vep", "uf_vap")}
            shard = dict(contract="participation.count_snapshot.v1", year=2026, state_code=state,
                records=selected, views=views)
            name = "states/" + state + ".json.gz"
            files[name] = compressed(shard)
            disposition = dict(reported=1 if selected else 0, unknown=1 if selected else 0,
                withheld=0, qualified_fractions=0, geography_levels=["reporting_unit"] if selected else [])
            declarations = {mode: dict(counties=0, precincts=len(selected), nongeographic=0, holds=0,
                qualified=True, dispositions={key: copy.deepcopy(disposition) if key == "precincts"
                    else dict(reported=0, unknown=0, withheld=0, qualified_fractions=0, geography_levels=[])
                    for key in ("counties", "precincts", "nongeographic")}) for mode in views}
            states[state] = dict(file=name, **pin(files[name]), records=len(selected), views=declarations)
            coverage[state] = dict(records=len(selected), reported=bool(selected), unknown=bool(selected),
                zeros=bool(selected), withheld=0, qualified_fractions=0)
        files["index.json"] = encoded(dict(contract="participation.count_index.v1", year=2026,
            states=states, coverage=coverage))
        pins = {name: pin(body) for name, body in sorted(files.items())}
        self.description = dict(contract="participation.dataset.v1", id="participation-counts-2026",
            record_contract="participation.count_snapshot.v1",
            version=digest(encoded(dict(files=pins, contract="participation.count_snapshot.v1"))),
            files=pins, index=dict(file="index.json", **pins["index.json"]),
            complete_download=dict(url="https://github.com/example/repo/releases/download/frozen/complete-analysis.zip",
                bytes=100, sha256="d" * 64, verified_anonymously=True, immutable=True))
        for name, body in dict(files, **{"dataset.json": encoded(self.description)}).items():
            path = self.baseline / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        self.plan = dict(contract="participation.routine_batch.v1", baseline_version=self.description["version"],
            sources=[dict(id="native", spec=self.spec, baseline_source_ids=["native-counts"])])
        self.write_input(self.native)
        self.save_plan()

    def save_plan(self):
        self.registry.write_bytes(encoded(self.plan))

    def write_input(self, body):
        path = self.supplied / "native/data"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(body)

    def execute(self, **kwargs):
        return execute(self.registry, self.baseline, self.work, self.supplied, offline=True, **kwargs)

    def test_noop_preserves_all_fifty_one_shards_and_never_reparses_or_rewrites(self):
        first = self.execute()
        self.assertEqual((first["status"], first["compiled_rows"], first["source_requests"]), ("unchanged", 2, 0))
        before = {str(path): (pin(path.read_bytes()), path.stat().st_mtime_ns)
            for path in self.work.rglob("*") if path.is_file()}
        with patch("scripts.participation_batch.run", side_effect=AssertionError("reparse")), \
                patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            second = self.execute()
        self.assertTrue(second["no_op"])
        self.assertEqual(second["compiled_rows"], 0)
        self.assertEqual(before, {str(path): (pin(path.read_bytes()), path.stat().st_mtime_ns)
            for path in self.work.rglob("*") if path.is_file()})
        output = Path(first["directory"])
        for name in self.description["files"]:
            self.assertEqual((output / "counts" / name).read_bytes(), (self.baseline / name).read_bytes())
        self.assertEqual(len(json.loads((output / "all-51-jurisdictions.json").read_bytes())), 51)

    def test_native_json_change_preserves_other_fifty_states_unknown_and_zero(self):
        self.write_input(encoded([dict(unit="one", label="One", ballots=7), dict(unit="two", label="Two", ballots="")]))
        result = self.execute()
        self.assertEqual((result["status"], result["changed_rows"]), ("changed", 2))
        output = Path(result["directory"]) / "counts"
        for state in set(STATES) - {"AR"}:
            name = "states/" + state + ".json.gz"
            self.assertEqual((output / name).read_bytes(), (self.baseline / name).read_bytes())
        rows = json.loads(gzip.decompress((output / "states/AR.json.gz").read_bytes()))["records"]
        self.assertEqual([row["count"]["value"] for row in rows], [7, None])
        retained = copy.deepcopy(rows[1])
        retained["source"]["input_sha256"] = self.original_rows[1]["source"]["input_sha256"]
        self.assertEqual(retained, self.original_rows[1])

    def test_corrupted_output_is_not_accepted_as_valid_noop(self):
        result = self.execute()
        (Path(result["directory"]) / "counts/states/AR.json.gz").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "Previously verified batch"):
            self.execute()

    def test_held_originals_are_reused_without_supplied_files_or_network(self):
        first = self.execute()
        with patch("scripts.participation_batch.run", side_effect=AssertionError("reparse")), \
                patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            result = execute(self.registry, self.baseline, self.work, offline=True)
        self.assertTrue(result["no_op"])
        self.assertEqual(result["directory"], first["directory"])

    def test_native_json_election_control_and_private_classification_rejected(self):
        self.spec["format"] = dict(items_path="rows", assert_fields={"election": "2026-general"})
        self.write_input(encoded(dict(election="2024-general", rows=json.loads(self.native))))
        self.save_plan()
        self.assertEqual(self.execute()["status"], "held")
        self.spec["classification"] = "private_records"
        self.save_plan()
        with patch("scripts.participation_batch.Store.acquire", side_effect=AssertionError("acquisition")):
            with self.assertRaisesRegex(ValueError, "public aggregate"):
                self.execute()

    def test_canonical_refresh_can_require_an_independent_native_statistical_cell(self):
        row = copy.deepcopy(self.original_rows[0])
        spec = copy.deepcopy(self.spec)
        spec.update(adapter="canonical_json", expected_rows=1)
        spec["inputs"]["facts"] = dict(url="https://example.gov/reviewed-facts.json")
        spec["format"] = dict(fact_bindings=[dict(input="facts",
            record={"geography.id": row["geography"]["id"]}, path="count.value",
            source_id="native-source", table_id="statistics",
            native_unit="Native ballots", measure="total", parse="count")])
        facts = dict(contract="participation.reviewed_pdf_factual_grids.v1",
            products=[dict(source=dict(id="native-source"), tables=[dict(id="statistics",
                source_annotations=dict(native_clock="native clock"),
                source_role="unofficial_registration_ballot_reported_turnout_statistics",
                rows=[dict(cells=dict(native_unit=dict(value="Native ballots"),
                    total=dict(value="0", native_status="literal")))])])])
        def run():
            return adapt(spec, dict(data=encoded([row]), facts=encoded(facts)),
                {}, {"literal": None, "timezone": None}, {})
        self.assertEqual(run()[0]["count"]["value"], 0)
        clock_binding = dict(spec["format"]["fact_bindings"][0], path="source_clock.literal",
            value_scope="annotations", value_path="native_clock", parse="literal")
        spec["format"]["fact_bindings"].append(clock_binding)
        self.assertEqual(run()[0]["source_clock"]["literal"], "native clock")
        facts["products"][0]["tables"][0]["source_annotations"]["native_clock"] = "different clock"
        with self.assertRaisesRegex(ValueError, "differs from its reviewed native fact"):
            run()
        facts["products"][0]["tables"][0]["source_annotations"]["native_clock"] = "native clock"
        row["count"].update(value=1, literal=1)
        with self.assertRaisesRegex(ValueError, "differs from its reviewed native fact"):
            run()
        row["count"].update(value=0, literal=0)
        facts["products"][0]["tables"][0]["rows"][0]["cells"]["total"].update(
            value=None, native_status="blank")
        with self.assertRaisesRegex(ValueError, "Unknown factual cell"):
            run()

    def test_contest_choice_cells_cannot_authorize_participation_refresh(self):
        row = copy.deepcopy(self.original_rows[0])
        spec = copy.deepcopy(self.spec)
        spec.update(adapter="canonical_json", expected_rows=1)
        spec["inputs"]["facts"] = dict(url="https://example.gov/reviewed-facts.json")
        spec["format"] = dict(fact_bindings=[dict(input="facts",
            record={"geography.id": row["geography"]["id"]}, path="count.value",
            source_id="source", table_id="contest",
            native_unit="Native ballots", measure="total", parse="count")])
        facts = dict(contract="participation.reviewed_pdf_factual_grids.v1",
            products=[dict(source=dict(id="source"), tables=[dict(id="contest",
                source_role="unofficial_contest_choices_and_vote_accounting", rows=[])])])
        with self.assertRaisesRegex(ValueError, "not choices"):
            adapt(spec, dict(data=encoded([row]), facts=encoded(facts)), {}, {}, {})

    def wide_statistical_fixture(self):
        row = copy.deepcopy(self.original_rows[0])
        row["count"].update(value=18, literal=18)
        row["view"]["ballots"] = 18
        spec = copy.deepcopy(self.spec)
        spec.update(adapter="canonical_json", expected_rows=1)
        spec["inputs"]["facts"] = dict(url="https://example.gov/reviewed-facts.json")
        binding = dict(input="facts", record={"geography.id": row["geography"]["id"]},
            path="count.value", source_id="source", table_ids=["first", "second"],
            native_unit="One Town", reading_whitespace_normalized=True,
            where_nonempty=["district"], measure="total", parse="count", operation="sum",
            sum_review_evidence="Synthetic disjoint parts reconcile to printed parent controls",
            native_measure_header="Total votes cast", accepted_measure_literal="Native ballots",
            same_measure_review_evidence="Synthetic reviewed same-quantity label equivalence")
        spec["format"] = dict(fact_bindings=[binding])
        tables = []
        for name, value in (("first", 6), ("second", 12)):
            tables.append(dict(id=name, source_role="native_registration_ballot_reported_turnout_statistics",
                source_annotations=dict(native_column_headers=dict(total="Total votes\ncast")),
                rows=[dict(row=1, cells=dict(native_unit=dict(value="One\nTown"),
                    district=dict(value="A" if name == "first" else "B"),
                    total=dict(value=value, native_status="reported")))]))
        tables[0]["rows"].insert(0, dict(row=0, cells=dict(native_unit=dict(value="One Town"),
            district=dict(value=""), total=dict(value=None, native_status="blank"))))
        facts = dict(contract="participation.reviewed_pdf_factual_grids.v1",
            products=[dict(source=dict(id="source"), tables=tables)])
        return row, spec, binding, facts

    def run_wide_statistical_fixture(self, row, spec, facts):
        return adapt(spec, dict(data=encoded([row]), facts=encoded(facts)), {}, {}, {})

    def test_explicit_native_part_sum_excludes_declared_headings_and_checks_all_pages(self):
        row, spec, binding, facts = self.wide_statistical_fixture()
        self.assertEqual(self.run_wide_statistical_fixture(row, spec, facts)[0]["count"]["value"], 18)
        row["count"].update(value=19, literal=19)
        with self.assertRaisesRegex(ValueError, "differs from its reviewed native fact"):
            self.run_wide_statistical_fixture(row, spec, facts)
        row["count"].update(value=18, literal=18)
        facts["products"][0]["tables"].pop()
        with self.assertRaisesRegex(ValueError, "reviewed ballot statistics"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_native_part_sum_rejects_missing_values_and_ambiguous_unique_cells(self):
        row, spec, binding, facts = self.wide_statistical_fixture()
        binding["operation"] = "unique"
        with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
            self.run_wide_statistical_fixture(row, spec, facts)
        binding["operation"] = "sum"
        facts["products"][0]["tables"][1]["rows"][0]["cells"]["total"].update(
            value=None, native_status="blank")
        with self.assertRaisesRegex(ValueError, "Unknown factual cell"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_native_part_sum_rejects_repeated_rows_and_missing_table_identities(self):
        row, spec, binding, facts = self.wide_statistical_fixture()
        table = facts["products"][0]["tables"][0]
        table["rows"].append(copy.deepcopy(table["rows"][1]))
        with self.assertRaisesRegex(ValueError, "unique factual identities"):
            self.run_wide_statistical_fixture(row, spec, facts)
        table["rows"].pop()
        facts["products"][0]["tables"][1] = copy.deepcopy(table)
        with self.assertRaisesRegex(ValueError, "reviewed ballot statistics"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_native_part_sum_requires_review_and_cannot_add_percentages_or_metadata(self):
        row, spec, binding, facts = self.wide_statistical_fixture()
        binding.pop("sum_review_evidence")
        with self.assertRaisesRegex(ValueError, "explicitly reviewed statistical counts"):
            self.run_wide_statistical_fixture(row, spec, facts)
        binding["sum_review_evidence"] = "Synthetic reviewed partition"
        binding["parse"] = "literal"
        with self.assertRaisesRegex(ValueError, "explicitly reviewed statistical counts"):
            self.run_wide_statistical_fixture(row, spec, facts)
        binding.update(parse="count", value_scope="annotations", value_path="native_column_headers.total")
        with self.assertRaisesRegex(ValueError, "explicitly reviewed statistical counts"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_native_column_header_equivalence_needs_exact_literal_and_review(self):
        row, spec, binding, facts = self.wide_statistical_fixture()
        for name, value in (("same_measure_review_evidence", ""),
                ("accepted_measure_literal", "Different measure"), ("native_measure_header", "Candidate votes")):
            original = binding[name]
            binding[name] = value
            with self.assertRaisesRegex(ValueError, "Native numerator label differs"):
                self.run_wide_statistical_fixture(row, spec, facts)
            binding[name] = original

    def native_workbook_fixture(self):
        row = copy.deepcopy(self.original_rows[0])
        row["source_clock"].update(literal=None, timezone=None)
        row["view"]["source_update_label"] = None
        spec = copy.deepcopy(self.spec)
        spec.update(adapter="canonical_json", expected_rows=1)
        spec["inputs"].update(facts=dict(url="https://example.gov/native-facts.json"),
                              recipe=dict(url="https://example.gov/native-recipe.json"))
        source = dict(id="workbook", url="https://example.gov/native.xlsx",
            pin=dict(bytes=10, sha256="a" * 64), state_code=spec["geography"]["state_code"],
            election_year=spec["election"]["year"], retrieved_at_utc="2026-11-12T00:00:00Z",
            native_updated_at=None)
        table = dict(kind="worksheet", workbook="native.xlsx", name="Statistics", rows=[
            dict(row=1, cells=[dict(address="B1", value="Total Ballots Cast")]),
            dict(row=2, cells=[dict(address="A2", value="One County"), dict(address="B2", value=0)])])
        facts = dict(contract="participation.native_factual_tables.v1", source=source, tables=[table])
        query = dict(id="ballots", product="workbook", workbook="native.xlsx", tables=["Statistics"],
            require={"1": {"B": "Total Ballots Cast"}}, first_row=2, last_row=2,
            fields=dict(county="A", total="B"), keys=["county"], counts=["total"])
        recipe = dict(contract="participation.native_product_recipe.v1",
                      products=[copy.deepcopy(source)], queries=[query])
        binding = dict(input="facts", record={"geography.id": row["geography"]["id"]},
            path="count.value", source_id="workbook", query_recipe_input="recipe",
            native_query_id="ballots", native_record=dict(county="One County"),
            native_header_row=1, measure="total", parse="count",
            source_role="native_registration_ballot_reported_turnout_statistics",
            native_measure_header="Total Ballots Cast", accepted_measure_literal="Native ballots",
            same_measure_review_evidence="Reviewed native count-column equivalence; no new turnout qualification")
        spec["format"] = dict(fact_bindings=[binding])
        return row, spec, binding, facts, recipe

    def run_native_workbook_fixture(self, row, spec, facts, recipe):
        return adapt(spec, dict(data=encoded([row]), facts=encoded(facts), recipe=encoded(recipe)),
                     {}, {}, {})

    def test_native_workbook_counts_and_unknown_clock_use_full_pinned_recipe(self):
        row, spec, binding, facts, recipe = self.native_workbook_fixture()
        self.assertEqual(self.run_native_workbook_fixture(row, spec, facts, recipe)[0]["count"]["value"], 0)
        spec["format"]["fact_bindings"].append(dict(binding, path="source_clock.literal",
            value_scope="source", value_path="native_updated_at", parse="literal"))
        self.assertIsNone(self.run_native_workbook_fixture(row, spec, facts, recipe)[0]["source_clock"]["literal"])
        row["count"].update(value=1, literal=1)
        row["view"]["ballots"] = 1
        with self.assertRaisesRegex(ValueError, "differs from its reviewed native fact"):
            self.run_native_workbook_fixture(row, spec, facts, recipe)

    def test_native_workbook_header_and_review_cannot_substitute_candidate_counts(self):
        for change in ("header", "role", "review", "missing_guard"):
            row, spec, binding, facts, recipe = self.native_workbook_fixture()
            if change == "header":
                facts["tables"][0]["rows"][0]["cells"][0]["value"] = "Candidate votes"
                recipe["queries"][0]["require"]["1"]["B"] = "Candidate votes"
            elif change == "role":
                binding["source_role"] = "unofficial_contest_choices_and_vote_accounting"
            elif change == "review":
                binding["same_measure_review_evidence"] = ""
            else:
                recipe["queries"][0]["require"] = {}
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_native_workbook_fixture(row, spec, facts, recipe)

    def test_native_workbook_source_and_election_must_match_canonical_scope(self):
        for change in ("year", "state", "pin", "recipe"):
            row, spec, binding, facts, recipe = self.native_workbook_fixture()
            if change == "year":
                facts["source"]["election_year"] = recipe["products"][0]["election_year"] = 2024
            elif change == "state":
                facts["source"]["state_code"] = recipe["products"][0]["state_code"] = "ZZ"
            elif change == "pin":
                facts["source"]["pin"]["sha256"] = "b" * 64
            else:
                spec["inputs"].pop("recipe")
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_native_workbook_fixture(row, spec, facts, recipe)

    def test_native_workbook_missing_and_duplicate_rows_are_not_filled(self):
        for change in ("missing", "duplicate", "selector"):
            row, spec, binding, facts, recipe = self.native_workbook_fixture()
            if change == "missing":
                facts["tables"][0]["rows"][1]["cells"][1]["value"] = None
            elif change == "duplicate":
                facts["tables"][0]["rows"].append(copy.deepcopy(facts["tables"][0]["rows"][1]))
            else:
                binding["native_record"] = dict(county="Different County")
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_native_workbook_fixture(row, spec, facts, recipe)

    def test_native_workbook_provenance_cannot_supply_a_replacement_count(self):
        row, spec, binding, facts, recipe = self.native_workbook_fixture()
        binding.update(value_scope="source", value_path="election_year", parse="count")
        with self.assertRaisesRegex(ValueError, "Provenance metadata cannot authorize"):
            self.run_native_workbook_fixture(row, spec, facts, recipe)

    def native_reporting_fixture(self):
        row = copy.deepcopy(self.original_rows[0])
        properties = dict(key="native-one", year=2026, state_code="AR", precinct="One",
            registered=None, reporting_unit_kind="source_reporting_unit",
            ballots=0, reported_pct=None, source_update_label="native clock")
        row["view"].update(properties)
        metadata = dict(rows=1, sha256=digest(compressed([properties])),
            data_url="https://example.gov/full-reporting.json.gz", source_url="https://example.gov/counts",
            complete_download_url="https://example.gov/complete-analysis.zip",
            source_update_label="native clock", scope="Complete native source rows, not population turnout",
            geometry_note="No geographic approval or rate allocation")
        table = compressed(dict(contract="participation.reporting_units.v1", state_code="AR",
                                records=[dict(properties=properties, observation=row)]))
        index = dict(contract="participation.native_index.v1", year=2026,
            reporting_tables=dict(AR=dict(file="tables/AR.json.gz", **pin(table), rows=1,
                eligible_modes=["available", "official"], coverage=dict(
                    source_rows=1, reported=1, unknown=0, withheld=0, fractions=0))),
            reporting_sources=dict(AR=metadata))
        files = {"index.json": encoded(index), "tables/AR.json.gz": table,
                 "geometry/unchanged.json.gz": b"unchanged original reference"}
        pins = {name: pin(body) for name, body in sorted(files.items())}
        description = dict(self.description, id="participation-native-bindings-2026",
            record_contract="participation.native_bindings.v1", files=pins,
            index=dict(file="index.json", **pins["index.json"]),
            version=digest(encoded(dict(files=pins, contract="participation.native_bindings.v1"))))
        root = self.root / "native-baseline"
        root.mkdir()
        for name, body in dict(files, **{"dataset.json": encoded(description)}).items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        updated = copy.deepcopy(row)
        updated["count"].update(value=1, literal=1)
        updated["view"]["ballots"] = 1
        current_properties = dict(properties, ballots=1)
        source = dict(spec=copy.deepcopy(self.spec), rows=[updated],
            baseline_source_ids=["native-counts"], reporting_source=dict(
                metadata, sha256=digest(compressed([current_properties]))))
        return root, description, files, index, source

    def test_native_reporting_refresh_preserves_references_and_other_files(self):
        root, description, files, index, source = self.native_reporting_fixture()
        self.assertEqual(native_baseline_files(root)[0], description)
        candidate, output, changed = compile_reporting(description, files, index, [source])
        self.assertEqual(changed, 1)
        self.assertEqual(output["geometry/unchanged.json.gz"], files["geometry/unchanged.json.gz"])
        self.assertNotEqual(candidate["version"], description["version"])
        data = json.loads(gzip.decompress(output["tables/AR.json.gz"]))
        self.assertEqual(data["records"][0]["properties"]["ballots"], 1)
        self.assertEqual(data["records"][0]["observation"]["count"]["value"], 1)
        self.assertIsNone(data["records"][0]["properties"]["reported_pct"])
        self.assertEqual(json.loads(files["index.json"]), index)
        self.assertIn("source-reporting/AR.json.gz", output)

    def test_native_reporting_refresh_cannot_change_inventory_identity_or_rates(self):
        for change in ("id", "geography", "rate", "registration", "missing"):
            with self.subTest(change=change):
                root, description, files, index, source = self.native_reporting_fixture()
                row = source["rows"][0]
                if change == "id":
                    row["id"] = "a" * 32
                elif change == "geography":
                    row["geography"]["id"] = "different"
                elif change == "rate":
                    row["view"]["reported_pct"] = 10
                elif change == "registration":
                    row["view"]["registered"] = 3
                else:
                    source["rows"] = []
                with self.assertRaises(ValueError):
                    compile_reporting(description, files, index, [source])
                for path in sorted(root.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                root.rmdir()

    def test_native_reporting_metadata_cannot_override_its_full_source_rows(self):
        root, description, files, index, source = self.native_reporting_fixture()
        source["reporting_source"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            compile_reporting(description, files, index, [source])

    def test_one_routine_compiles_both_datasets_and_packages_both_complete_baselines(self):
        root, description, files, index, source = self.native_reporting_fixture()
        spec = copy.deepcopy(self.spec)
        spec.update(id="native-reporting-counts", adapter="canonical_json", expected_rows=1)
        spec["inputs"]["data"]["url"] = "https://example.gov/reviewed-reporting.json"
        target = self.supplied / "reporting/data"
        target.parent.mkdir()
        target.write_bytes(encoded(source["rows"]))
        self.plan["native_baseline_version"] = description["version"]
        self.plan["sources"].append(dict(id="reporting", target="native_reporting", spec=spec,
            baseline_source_ids=source["baseline_source_ids"], reporting_source=source["reporting_source"]))
        self.save_plan()
        first = self.execute(native_baseline=root)
        self.assertEqual((first["count_changed_rows"], first["native_changed_rows"]), (0, 1))
        self.assertEqual(first["candidate_version"], self.description["version"])
        self.assertNotEqual(first["native_candidate_version"], description["version"])
        with zipfile.ZipFile(Path(first["directory"]) / "complete-analysis.zip") as archive:
            self.assertEqual(archive.read("originals/native-baseline/geometry/unchanged.json.gz"),
                             files["geometry/unchanged.json.gz"])
            self.assertIn("queries/native/tables/AR.json.gz", archive.namelist())
            self.assertIn("code/scripts/native_products.py", archive.namelist())
            self.assertIn("code/scripts/native_tabular.py", archive.namelist())
        with patch("scripts.participation_batch.run", side_effect=AssertionError("reparse")):
            second = self.execute(native_baseline=root)
        self.assertTrue(second["no_op"])
        self.assertEqual(second["native_candidate_version"], first["native_candidate_version"])

    def test_registered_reference_original_is_verified_and_packaged_by_the_shared_runner(self):
        body = encoded(dict(type="FeatureCollection", features=[
            dict(type="Feature", properties=dict(key=key), geometry=None) for key in ("one", "two")]))
        self.spec["inputs"]["geometry"] = dict(url="https://example.gov/context.json", pin=pin(body))
        (self.supplied / "native/geometry").write_bytes(body)
        self.plan["sources"][0]["references"] = dict(assets={
            "reviewed-context": dict(pin(body), key_path="properties.key",
                approval_evidence="Synthetic already reviewed reference, not a new geographic join")})
        self.save_plan()
        result = self.execute()
        self.assertEqual(result["status"], "unchanged")
        found = False
        with zipfile.ZipFile(Path(result["directory"]) / "complete-analysis.zip") as outer:
            for name in outer.namelist():
                if not name.endswith(".zip"):
                    continue
                with zipfile.ZipFile(io.BytesIO(outer.read(name))) as source:
                    if "references/reviewed-context" in source.namelist():
                        self.assertEqual(source.read("references/reviewed-context"), body)
                        found = True
        self.assertTrue(found, "The complete registered reference original must survive outer packaging")

    def test_overlapping_registry_entries_and_wrong_baseline_rejected(self):
        self.plan["sources"].append(dict(self.plan["sources"][0], id="duplicate-scope"))
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "Duplicate source packet"):
            self.execute()
        self.plan["sources"][1]["spec"] = dict(self.spec, id="different-packet-same-scope")
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.execute()
        self.plan["sources"].pop()
        self.plan["baseline_version"] = "wrong"
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "baseline advanced"):
            self.execute()

    def test_changed_inventory_does_not_silently_replace_a_partial_source(self):
        self.write_input(encoded([dict(unit="different", label="One", ballots=7),
            dict(unit="two", label="Two", ballots="")]))
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.execute()

    def test_source_access_hold_never_requests_or_erases_baseline(self):
        self.spec["inputs"]["data"]["stopped"] = True
        self.save_plan()
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            result = self.execute()
        self.assertEqual(result["status"], "held")
        self.assertEqual(result["compiled_rows"], 0)
        self.assertEqual((Path(result["directory"]) / "counts/states/AR.json.gz").read_bytes(),
            (self.baseline / "states/AR.json.gz").read_bytes())

    def test_private_input_is_quarantined_not_exported_in_outer_bundle(self):
        self.write_input(encoded([dict(unit="one", label="One", ballots=0, firstname="Synthetic private marker"),
            dict(unit="two", label="Two", ballots="")]))
        result = self.execute()
        self.assertEqual(result["status"], "held")
        with zipfile.ZipFile(Path(result["directory"]) / "complete-analysis.zip") as archive:
            self.assertFalse(any(name.startswith("originals/supplied/") for name in archive.namelist()))
            exported_data = b"".join(archive.read(name) for name in archive.namelist()
                if name.startswith(("originals/", "queries/")))
            self.assertNotIn(b"Synthetic private marker", exported_data)

    def test_publication_resumes_cached_compilation_without_mutating_immutable_outputs(self):
        self.write_input(encoded([dict(unit="one", label="One", ballots=7), dict(unit="two", label="Two", ballots="")]))
        first = self.execute()
        output = Path(first["directory"])
        wanted = dict(pin((output / "complete-analysis.zip").read_bytes()), verified_anonymously=True,
            immutable=True, url="https://github.com/example/repo/releases/download/new/complete-analysis.zip")
        manifest = (output / "manifest.json").read_bytes()
        with patch("scripts.participation_batch.publish_datasets",
                side_effect=[RuntimeError("interruption"), dict(status="published")]) as publish, \
                patch("scripts.participation_batch.run", side_effect=AssertionError("reparse")):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                self.execute(website_repo=self.root, complete_download=wanted)
            resumed = self.execute(website_repo=self.root, complete_download=wanted)
        self.assertEqual(resumed["publication"]["status"], "published")
        self.assertEqual(publish.call_count, 2)
        self.assertEqual((output / "manifest.json").read_bytes(), manifest)
        self.assertTrue(self.execute()["no_op"])

    def test_discovery_only_follows_an_unambiguous_preapproved_declared_product(self):
        spec = copy.deepcopy(self.spec)
        spec["discovery"] = dict(index=dict(url="https://example.gov/", redistribution_approved=True),
            input="data", url_pattern=r"https://example.gov/2026/.*\.json",
            approved_urls=["https://example.gov/2026/general.json"])
        found = discover(spec, lambda declaration, supplied: (b'<a href="/2026/general.json">General</a>', None))
        self.assertEqual(found["inputs"]["data"]["url"], "https://example.gov/2026/general.json")
        with self.assertRaisesRegex(ValueError, "scope review"):
            discover(spec, lambda declaration, supplied: (b'<a href="/2026/new.json">New</a>', None))

    def test_discovery_declaration_is_retained_and_reused_offline(self):
        body = b'<a href="/2026/general.json">General election</a>'
        self.spec["discovery"] = dict(index=dict(url="https://example.gov/", redistribution_approved=True),
            input="data", url_pattern=r"https://example.gov/2026/.*\.json",
            approved_urls=["https://example.gov/2026/general.json"])
        (self.supplied / "native/discovery-index").write_bytes(body)
        self.save_plan()
        first = self.execute()
        with zipfile.ZipFile(Path(first["directory"]) / "complete-analysis.zip") as archive:
            self.assertEqual(archive.read("originals/supplied/native/discovery-index"), body)
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            result = execute(self.registry, self.baseline, self.work, offline=True)
        self.assertTrue(result["no_op"])

    def test_measure_reclassification_requires_separate_review(self):
        self.spec["measure"]["literal"] = "Native cards, not the accepted ballot measure"
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "measure"):
            self.execute()

    def test_intake_cache_reuse_preserves_native_conditional_request_metadata(self):
        self.execute()
        db = sqlite3.connect(self.work / "intake/intake.sqlite3")
        db.execute("UPDATE inputs SET etag=?,modified=?", ("native-etag", "native-modified"))
        db.commit()
        db.close()
        self.plan["operator_note"] = "New batch envelope; original and source recipe unchanged"
        self.save_plan()
        result = self.execute()
        self.assertEqual(result["parsed_inputs"], 0)
        db = sqlite3.connect(self.work / "intake/intake.sqlite3")
        self.addCleanup(db.close)
        self.assertEqual(db.execute("SELECT etag,modified FROM inputs").fetchone(),
            ("native-etag", "native-modified"))


if __name__ == "__main__":
    unittest.main()
