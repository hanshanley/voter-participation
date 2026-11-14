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
    compile_counts, compile_reporting, compressed, discover, display, execute, native_baseline_files,
    reviewed_view_aliases, supplied_reference_bodies,
)
from scripts.participation_intake.adapters import adapt
from scripts.participation_intake.contract import IntakeError, STATES, digest, encoded, pin
from scripts.participation_intake.engine import Store


class SuppliedReferenceBodyTests(unittest.TestCase):
    def test_declared_geometry_input_is_pinned_and_forwarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "geometry.json"
            path.write_bytes(b'{"type":"FeatureCollection","features":[]}')
            asset = dict(pin(path.read_bytes()), input="geometry")
            entry = {"references": {"assets": {"reference": asset}}}
            inputs = {"geometry": {"path": path, **pin(path.read_bytes())}}
            self.assertEqual(supplied_reference_bodies(entry, inputs), {"reference": path.read_bytes()})
            with self.assertRaises(IntakeError):
                supplied_reference_bodies(entry, {})
            path.write_bytes(b"changed")
            with self.assertRaises(IntakeError):
                supplied_reference_bodies(entry, inputs)


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

    def alias_refresh_fixture(self):
        state = json.loads(gzip.decompress((self.baseline / "states/AR.json.gz").read_bytes()))
        state["records"][0]["source"]["selector"]["partition"] = "original-export"
        alias = copy.deepcopy(state["records"][0])
        alias["id"] = "a" * 32
        alias["source"]["id"] = "retained-export-copy"
        alias["source"]["selector"]["partition"] = "copied-export"
        state["records"].append(alias)
        for mode in ("uf_vep", "uf_vap"):
            state["views"][mode]["precincts"][0] = alias["id"]
        native = encoded([dict(unit="one", label="One", ballots=7), dict(unit="two", label="Two", ballots="")])
        rows = [display(row, self.spec) for row in adapt(self.spec, {"data": native},
            {"data": pin(native)}, {"literal": "native clock", "timezone": None}, {})]
        spec = copy.deepcopy(self.spec)
        spec["format"] = dict(view_aliases=dict(
            contract="participation.reviewed_view_aliases.v1", review_evidence="Synthetic same-source copy review",
            baseline_views=pin(encoded(state["views"])),
            aliases=[dict(id=alias["id"], pin=pin(encoded(alias)),
                          refreshed_from=self.original_rows[0]["id"],
                          selector_partitions=dict(alias="copied-export", origin="original-export"),
                          occurrences=[dict(mode=mode, partition="precincts", index=0)
                                       for mode in state["views"] if mode in ("uf_vep", "uf_vap")])]))
        replacements = dict(zip([row["id"] for row in self.original_rows], rows))
        return state, spec, replacements, alias

    def test_explicit_alias_review_updates_all_selected_modes_and_retains_original_copy(self):
        state, spec, replacements, alias = self.alias_refresh_fixture()
        files = {name: (self.baseline / name).read_bytes() for name in self.description["files"]}
        index = json.loads(files["index.json"])
        files["states/AR.json.gz"] = compressed(state)
        source = dict(spec=spec, rows=list(replacements.values()), baseline_source_ids=["native-counts"])
        _, result, _ = compile_counts(self.description, files, index, [source])
        actual = json.loads(gzip.decompress(result["states/AR.json.gz"]))
        self.assertIn(alias, actual["records"])
        for mode in ("available", "official", "uf_vep", "uf_vap"):
            selected = actual["views"][mode]["precincts"][0]
            row = next(row for row in actual["records"] if row["id"] == selected)
            self.assertEqual(row["count"]["value"], 7)
            self.assertEqual(row["source"]["id"], "native-counts")
        for mode, frame in state["views"].items():
            for partition in ("counties", "precincts", "nongeographic"):
                expected = [replacements[self.original_rows[0]["id"]]["id"]
                            if key == alias["id"] else key for key in frame[partition]]
                self.assertEqual(actual["views"][mode][partition], expected)
        for name in self.description["files"]:
            if name not in ("states/AR.json.gz", "index.json"):
                self.assertEqual(result[name], files[name])
        spec["format"] = {}
        self.assertEqual(reviewed_view_aliases(state, spec, replacements), {})

    def test_alias_review_rejects_changed_preimages_unknown_origins_and_duplicate_selections(self):
        for failure in ("views", "pin", "origin", "repeated", "selected", "cross_partition", "occurrence", "lineage"):
            with self.subTest(failure=failure):
                state, spec, replacements, alias = self.alias_refresh_fixture()
                review = spec["format"]["view_aliases"]
                if failure == "views":
                    review["baseline_views"] = pin(b"changed")
                elif failure == "pin":
                    review["aliases"][0]["pin"] = pin(b"changed")
                elif failure == "origin":
                    review["aliases"][0]["refreshed_from"] = "b" * 32
                elif failure == "repeated":
                    review["aliases"].append(copy.deepcopy(review["aliases"][0]))
                elif failure == "selected":
                    state["views"]["uf_vep"]["precincts"].append(self.original_rows[0]["id"])
                    review["baseline_views"] = pin(encoded(state["views"]))
                elif failure == "cross_partition":
                    state["views"]["uf_vep"]["counties"].append(self.original_rows[0]["id"])
                    review["baseline_views"] = pin(encoded(state["views"]))
                elif failure == "occurrence":
                    review["aliases"][0]["occurrences"].pop()
                else:
                    review["aliases"][0]["selector_partitions"]["alias"] = "unreviewed-export"
                with self.assertRaises(IntakeError):
                    reviewed_view_aliases(state, spec, replacements)

    def test_rechecksummed_alias_cannot_bridge_source_measure_count_clock_or_population(self):
        for failure in ("source", "measure", "count", "clock", "denominator", "geography", "visible"):
            with self.subTest(failure=failure):
                state, spec, replacements, alias = self.alias_refresh_fixture()
                if failure == "source":
                    alias["source"]["input_sha256"] = "b" * 64
                elif failure == "measure":
                    alias["measure"]["literal"] = "Cards"
                elif failure == "count":
                    alias["count"].update(value=1, literal=1)
                elif failure == "clock":
                    alias["source_clock"]["literal"] = "other snapshot"
                elif failure == "denominator":
                    alias["denominator"] = dict(value=100, qualified=False, literal="Registry", basis="other")
                elif failure == "geography":
                    alias["geography"]["name"] = "Different source unit"
                else:
                    alias["view"]["source_status_literal"] = "Unreviewed source status"
                spec["format"]["view_aliases"]["aliases"][0]["pin"] = pin(encoded(alias))
                with self.assertRaises(IntakeError):
                    reviewed_view_aliases(state, spec, replacements)

    def test_alias_target_cannot_promote_a_qualified_denominator_or_rate(self):
        for failure in ("denominator", "rate"):
            with self.subTest(failure=failure):
                state, spec, replacements, alias = self.alias_refresh_fixture()
                target = replacements[self.original_rows[0]["id"]]
                if failure == "denominator":
                    target["denominator"] = dict(value=100, qualified=True, literal="Registry", basis="other")
                else:
                    target["view"]["reported_pct"] = 7
                with self.assertRaises(IntakeError):
                    reviewed_view_aliases(state, spec, replacements)

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

    def component_statistical_fixture(self):
        row, spec, binding, facts = self.wide_statistical_fixture()
        binding.pop("measure")
        binding.pop("native_measure_header")
        binding.pop("table_ids")
        binding.update(table_id="first", operation="component_sum",
            administrative_measure_review_evidence="Synthetic reviewed administrative mode columns",
            components=[dict(measure=name, native_header=header, header_requirement=index)
                for index, (name, header) in enumerate((
                    ("early", "Votes Cast"), ("election_day", "Votes Cast"), ("tallied_mail", "Ballots Tallied")))])
        table = facts["products"][0]["tables"][0]
        facts["products"][0]["tables"] = [table]
        table["source_role"] = "unofficial_administrative_measures_not_candidate_returns"
        table["rows"] = [table["rows"][1]]
        table["native_requirements"] = [dict(decoded_text=part["native_header"],
            reading_bbox=[index * 10, 0, index * 10 + 9, 5])
            for index, part in enumerate(binding["components"])]
        table["rows"][0]["cells"].update({name: dict(value=value, native_status="reported",
            reading_bbox=[index * 10, 5, index * 10 + 9, 10])
            for index, (name, value) in enumerate((("early", 0), ("election_day", 5), ("tallied_mail", 13)))})
        return row, spec, binding, facts

    def test_reviewed_component_sum_checks_all_three_canonical_count_mirrors_and_zero(self):
        row, spec, binding, facts = self.component_statistical_fixture()
        spec["format"]["fact_bindings"] = [dict(binding, path=path)
            for path in ("count.value", "count.literal", "view.ballots")]
        self.assertEqual(self.run_wide_statistical_fixture(row, spec, facts)[0]["count"]["value"], 18)
        row["view"]["ballots"] = 19
        with self.assertRaisesRegex(ValueError, "differs from its reviewed native fact"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_component_sum_rejects_duplicate_columns_and_repeated_or_cross_parent_rows(self):
        row, spec, binding, facts = self.component_statistical_fixture()
        binding["components"].append(copy.deepcopy(binding["components"][0]))
        with self.assertRaisesRegex(ValueError, "distinct reviewed native count columns"):
            self.run_wide_statistical_fixture(row, spec, facts)
        binding["components"].pop()
        table = facts["products"][0]["tables"][0]
        table["rows"].append(copy.deepcopy(table["rows"][0]))
        with self.assertRaisesRegex(ValueError, "exactly one native parent row"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_component_sum_rejects_wrong_header_wrong_physical_column_and_unknown_component(self):
        row, spec, binding, facts = self.component_statistical_fixture()
        table = facts["products"][0]["tables"][0]
        table["native_requirements"][2]["decoded_text"] = "Ballots Issued"
        with self.assertRaisesRegex(ValueError, "header or physical column changed"):
            self.run_wide_statistical_fixture(row, spec, facts)
        table["native_requirements"][2]["decoded_text"] = "Ballots Tallied"
        table["rows"][0]["cells"]["tallied_mail"]["reading_bbox"][0] += 1
        with self.assertRaisesRegex(ValueError, "header or physical column changed"):
            self.run_wide_statistical_fixture(row, spec, facts)
        table["rows"][0]["cells"]["tallied_mail"]["reading_bbox"][0] -= 1
        table["rows"][0]["cells"]["tallied_mail"].update(value=None, native_status="blank")
        with self.assertRaisesRegex(ValueError, "Unknown factual cell"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_component_sum_cannot_use_unreviewed_admin_roles_metadata_or_changed_measure(self):
        for mutation in ("role", "metadata", "measure", "review"):
            with self.subTest(mutation=mutation):
                row, spec, binding, facts = self.component_statistical_fixture()
                if mutation == "role":
                    binding.pop("administrative_measure_review_evidence")
                elif mutation == "metadata":
                    binding.update(value_scope="annotations", value_path="native_column_headers")
                elif mutation == "measure":
                    binding["accepted_measure_literal"] = "All ballots"
                else:
                    binding.pop("sum_review_evidence")
                with self.assertRaises(ValueError):
                    self.run_wide_statistical_fixture(row, spec, facts)

    def test_component_image_sum_requires_explicit_pinned_visual_review(self):
        row, spec, binding, facts = self.component_statistical_fixture()
        table = facts["products"][0]["tables"][0]
        table.pop("native_requirements")
        with self.assertRaisesRegex(ValueError, "pinned explicit visual review"):
            self.run_wide_statistical_fixture(row, spec, facts)
        method = "visually_reviewed_source_image_transcription"
        table["source_annotations"].update(source_method=method,
            reviewed_image_pin=dict(bytes=100, sha256="a" * 64))
        for component in binding["components"]:
            table["rows"][0]["cells"][component["measure"]]["source_method"] = method
        binding["visual_header_review_evidence"] = "Synthetic independent header and image review"
        self.assertEqual(self.run_wide_statistical_fixture(row, spec, facts)[0]["count"]["value"], 18)
        table["source_annotations"]["reviewed_image_pin"]["sha256"] = "not-a-pin"
        with self.assertRaisesRegex(ValueError, "pinned explicit visual review"):
            self.run_wide_statistical_fixture(row, spec, facts)

    def test_component_columns_reject_other_operations_and_non_pdf_contracts_before_dispatch(self):
        row, spec, binding, facts = self.component_statistical_fixture()
        binding["operation"] = "unique"
        with self.assertRaisesRegex(ValueError, "explicit sum operation"):
            self.run_wide_statistical_fixture(row, spec, facts)
        binding["operation"] = "component_sum"
        for contract in ("participation.native_factual_tables.v1", "participation.selected_html_statistics.v1"):
            facts["contract"] = contract
            with self.assertRaisesRegex(ValueError, "reviewed factual PDF columns"):
                self.run_wide_statistical_fixture(row, spec, facts)

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

    def native_records_fixture(self, kind="json_records"):
        from scripts.native_products import unpack

        row, spec, binding, _, recipe = self.native_workbook_fixture()
        source = recipe["products"][0]
        source.update(url="https://example.gov/counts.json", redistribution="public_aggregate",
            kind=kind, reader={}, expected_rows=1)
        body = (b'[{"county":"One County","bct":"0","clock":"Native report date","candidateVotes":"9"}]'
            if kind == "json_records" else
            b"county,bct,clock,candidateVotes\nOne County,0,Native report date,9\n")
        source["pin"] = pin(body)
        facts = unpack(source, body)
        recipe["queries"][0] = dict(id="ballots", product=source["id"],
            fields=dict(county="county", total="bct", clock="clock"), counts=["total"], keys=["county"])
        binding.pop("native_header_row")
        binding["native_measure_header"] = "bct"
        row["source_clock"]["literal"] = row["view"]["source_update_label"] = "Native report date"
        spec["format"]["fact_bindings"].append(dict(binding, path="source_clock.literal",
            value_scope="row", value_path="clock", parse="literal"))
        return row, spec, binding, facts, recipe

    def test_native_json_and_delimited_headers_bind_counts_and_per_record_clocks(self):
        for kind in ("json_records", "delimited"):
            row, spec, binding, facts, recipe = self.native_records_fixture(kind)
            actual = self.run_native_workbook_fixture(row, spec, facts, recipe)[0]
            self.assertEqual(actual["count"]["value"], 0)
            self.assertEqual(actual["source_clock"]["literal"], "Native report date")
            row["source_clock"]["literal"] = row["view"]["source_update_label"] = "Acquisition time"
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "reviewed native fact"):
                self.run_native_workbook_fixture(row, spec, facts, recipe)

    def test_native_record_fields_cannot_masquerade_as_workbook_or_candidate_columns(self):
        for change in ("worksheet", "candidate"):
            row, spec, binding, facts, recipe = self.native_records_fixture()
            if change == "worksheet":
                binding["native_header_row"] = 1
            else:
                recipe["queries"][0]["fields"]["total"] = "candidateVotes"
                binding["native_measure_header"] = "candidateVotes"
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "worksheet or candidate"):
                self.run_native_workbook_fixture(row, spec, facts, recipe)

    def test_native_record_clock_literals_cannot_supply_statistical_counts(self):
        row, spec, binding, facts, recipe = self.native_records_fixture()
        binding.update(value_scope="row", value_path="clock", parse="count")
        with self.assertRaisesRegex(ValueError, "record literals"):
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

    def addition_fixture(self):
        from scripts.participation_batch import baseline_files
        description, files, index = baseline_files(self.baseline)
        spec = copy.deepcopy(self.spec)
        spec["id"] = "new-source"
        spec["expected_rows"] = 1
        spec["view"]["identities"] = dict(three=dict(
            spec["view"]["identities"]["one"], unit_key="three", unit="Three", precinct="Three"))
        body = encoded([dict(unit="three", label="Three", ballots=0)])
        rows = [display(row, spec) for row in adapt(spec, {"data": body},
            {"data": pin(body)}, {"literal": "native clock", "timezone": None}, {})]
        state = json.loads(gzip.decompress(files["states/AR.json.gz"]))
        binding = dict(contract="participation.reviewed_count_addition.v1",
            baseline_shard=pin(files["states/AR.json.gz"]),
            source_scope_review_evidence="Synthetic independently reviewed new reporting unit",
            records={row["id"]: pin(encoded(row)) for row in rows},
            views={mode: {part: dict(before=list(frame[part]),
                append=[rows[0]["id"]] if part == "precincts" else [])
                for part in ("counties", "precincts", "nongeographic")}
                for mode, frame in state["views"].items()})
        source = dict(spec=spec, rows=rows, baseline_source_ids=[], target="counts_addition", addition=binding)
        return description, files, index, source, body

    def test_explicit_addition_retains_all_old_rows_views_and_other_fifty_states(self):
        from scripts.participation_batch import compile_counts
        description, files, index, source, body = self.addition_fixture()
        result, output, changed = compile_counts(description, files, index, [source])
        self.assertEqual(changed, 1)
        self.assertNotEqual(result["version"], description["version"])
        for name in files:
            if name not in ("states/AR.json.gz", "index.json"):
                self.assertEqual(output[name], files[name])
        shard = json.loads(gzip.decompress(output["states/AR.json.gz"]))
        self.assertEqual(shard["records"][:-1], self.original_rows)
        self.assertEqual(shard["records"][-1]["count"]["value"], 0)
        declaration = json.loads(output["index.json"])["states"]["AR"]
        self.assertEqual(declaration["records"], 3)
        self.assertEqual(declaration["views"]["official"]["precincts"], 3)

    def test_addition_requires_exact_preimage_rows_modes_and_cannot_overwrite(self):
        from scripts.participation_batch import compile_counts
        for change in ("preimage", "count", "before", "mode", "existing"):
            with self.subTest(change=change):
                description, files, index, source, body = self.addition_fixture()
                if change == "preimage":
                    source["addition"]["baseline_shard"]["sha256"] = "0"*64
                elif change == "count":
                    source["rows"][0]["view"]["ballots"] = 7
                elif change == "before":
                    source["addition"]["views"]["official"]["precincts"]["before"] = []
                elif change == "mode":
                    source["addition"]["views"]["new-mode"] = {}
                else:
                    source["rows"] = [self.original_rows[0]]
                    source["addition"]["records"] = {
                        source["rows"][0]["id"]: pin(encoded(source["rows"][0]))}
                with self.assertRaises(ValueError):
                    compile_counts(description, files, index, [source])

    def test_county_addition_rejects_exact_selected_name_but_not_literal_variant(self):
        from scripts.participation_count_additions import append_reviewed
        from scripts.participation_intake.contract import observation_id
        _, _, _, source, _ = self.addition_fixture()
        row = source["rows"][0]
        row["geography"].update(
            id="native:AR:county:hancock",
            level="county",
            name="Hancock",
            parent_id=None,
        )
        row["view"].update(
            county="Hancock",
            county_id="native-hancock",
            geography_level="county",
            maps_approved=False,
            unit=None,
            unit_key=None,
        )
        row["id"] = observation_id(
            row["source"]["id"],
            row["election"]["id"],
            row["geography"]["id"],
            row["measure"]["id"],
            row["measure"]["mode"],
        )
        old = copy.deepcopy(row)
        old["id"] = "existing-hancock"
        old["geography"]["id"] = "additional:AR:18059"
        old["view"]["county_id"] = "additional:AR:18059"
        old["count"] = dict(literal=None, status="unknown", value=None)
        old["view"]["ballots"] = None
        state = dict(
            state_code="AR",
            year=2026,
            records=[old],
            views={
                mode: dict(
                    qualified=True,
                    counties=["existing-hancock"],
                    precincts=[],
                    nongeographic=[],
                    holds=[],
                )
                for mode in ("available", "official", "uf_vap", "uf_vep")
            },
        )
        baseline = pin(encoded(state))

        def candidate(name):
            current = copy.deepcopy(row)
            current["geography"]["name"] = name
            current["view"]["county"] = name
            current["id"] = observation_id(
                current["source"]["id"],
                current["election"]["id"],
                current["geography"]["id"],
                current["measure"]["id"],
                current["measure"]["mode"],
            )
            binding = dict(
                contract="participation.reviewed_count_addition.v1",
                baseline_shard=baseline,
                source_scope_review_evidence="Synthetic exact-literal county review",
                records={current["id"]: pin(encoded(current))},
                views={
                    mode: {
                        partition: dict(
                            before=list(frame[partition]),
                            append=[current["id"]] if partition == "counties" else [],
                        )
                        for partition in ("counties", "precincts", "nongeographic")
                    }
                    for mode, frame in state["views"].items()
                },
            )
            return dict(
                addition=binding,
                baseline_source_ids=[],
                rows=[current],
                spec=source["spec"],
                target="counts_addition",
            )

        with self.assertRaisesRegex(ValueError, "exact selected county name"):
            append_reviewed(state, candidate("Hancock"), baseline)
        duplicate = candidate("Distinct County")
        second = copy.deepcopy(duplicate["rows"][0])
        second["geography"]["id"] += "-second"
        second["view"]["county_id"] += "-second"
        second["id"] = observation_id(
            second["source"]["id"], second["election"]["id"], second["geography"]["id"],
            second["measure"]["id"], second["measure"]["mode"])
        duplicate["rows"].append(second)
        duplicate["addition"]["records"][second["id"]] = pin(encoded(second))
        for frame in duplicate["addition"]["views"].values():
            frame["counties"]["append"].append(second["id"])
        with self.assertRaisesRegex(ValueError, "exact selected county name"):
            append_reviewed(state, duplicate, baseline)
        result, changed = append_reviewed(state, candidate("Hancock County"), baseline)
        self.assertEqual(changed, 1)
        self.assertEqual(result["views"]["official"]["counties"],
                         ["existing-hancock", result["records"][-1]["id"]])

    def test_addition_runs_through_shared_cli_and_offline_cached_noop(self):
        description, files, index, source, body = self.addition_fixture()
        self.plan["sources"] = [dict(id="native", **{key: source[key] for key in
            ("spec", "baseline_source_ids", "target", "addition")})]
        self.write_input(body)
        self.save_plan()
        first = self.execute()
        self.assertEqual((first["status"], first["changed_rows"]), ("changed", 1))
        with patch("scripts.participation_batch.run", side_effect=AssertionError("reparse")):
            second = self.execute()
        self.assertTrue(second["no_op"])
        self.assertEqual(second["candidate_version"], first["candidate_version"])

    def test_source_access_hold_never_requests_or_erases_baseline(self):
        self.spec["inputs"]["data"]["stopped"] = True
        self.save_plan()
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            result = self.execute()
        self.assertEqual(result["status"], "held")
        self.assertEqual(result["compiled_rows"], 0)
        self.assertEqual((Path(result["directory"]) / "counts/states/AR.json.gz").read_bytes(),
            (self.baseline / "states/AR.json.gz").read_bytes())

    def county_reference_fixture(self):
        source = self.addition_fixture()[3]
        row = source["rows"][0]
        row["geography"].update(level="county", name="New County",
            join=dict(status="approved", feature_key="05001", reference_id="context",
                evidence="Synthetic reviewed existing county context"))
        row["view"].update(county_id="new-county", county="New County", county_fips="05001",
            geography_level="county", maps_approved=True, reference_geometry=dict(
                sha256="a"*64, boundary_year=2026, url="https://example.gov/context.json.gz"))
        binding = dict(sha256="a"*64, features=1, feature_keys=["05001"], rows=[],
            feature_scopes={"05001": dict(state_code="AR", name="New County", boundary_year=2026)})
        index = dict(county_bindings=dict(AR=dict(official=binding)))
        files = {"index.json": encoded(index), "geometry.json.gz": b"unchanged contextual geometry"}
        description = dict(index=dict(file="index.json"), record_contract="participation.native_bindings.v1")
        source["addition"]["views"] = dict(official=dict(counties=dict(append=[row["id"]])))
        source["addition"]["county_reference"] = dict(
            contract="participation.reviewed_county_reference_addition.v1",
            review_evidence="Synthetic separately reviewed identity", baseline_index=pin(files["index.json"]),
            modes=dict(official=dict(before=pin(encoded(binding)), append=[row["id"]])))
        return description, files, index, source

    def test_county_reference_addition_retains_all_geometry_and_old_binding_fields(self):
        from scripts.participation_count_additions import append_county_references
        description, files, index, source = self.county_reference_fixture()
        descriptor, output, changed = append_county_references(description, files, index, [source])
        self.assertEqual(changed, 1)
        self.assertEqual(output["geometry.json.gz"], files["geometry.json.gz"])
        binding = json.loads(output["index.json"])["county_bindings"]["AR"]["official"]
        self.assertEqual({k: v for k, v in binding.items() if k != "rows"},
            {k: v for k, v in index["county_bindings"]["AR"]["official"].items() if k != "rows"})
        self.assertEqual(binding["rows"][0]["feature_key"], "05001")
        self.assertEqual(binding["rows"][0]["county_id"], "new-county")
        self.assertIsNone(descriptor["complete_download"])
        self.assertEqual(index["county_bindings"]["AR"]["official"]["rows"], [])

    def test_county_reference_addition_rejects_changed_preimages_modes_scopes_or_rates(self):
        from scripts.participation_count_additions import append_county_references
        for change in ("index", "binding", "mode", "ids", "state", "name", "year",
                       "hash", "key", "denominator", "duplicate"):
            with self.subTest(change=change):
                description, files, index, source = self.county_reference_fixture()
                review = source["addition"]["county_reference"]
                row = source["rows"][0]
                if change == "index": review["baseline_index"]["sha256"] = "0"*64
                elif change == "binding": review["modes"]["official"]["before"]["sha256"] = "0"*64
                elif change == "mode": review["modes"]["mail_returned"] = {}
                elif change == "ids": review["modes"]["official"]["append"] = []
                elif change == "state": row["geography"]["state_code"] = "MI"
                elif change == "name": row["view"]["county"] = "Other County"
                elif change == "year": row["view"]["reference_geometry"]["boundary_year"] = 2024
                elif change == "hash": row["view"]["reference_geometry"]["sha256"] = "b"*64
                elif change == "key": row["view"]["county_fips"] = "05003"
                elif change == "denominator": row["view"]["reported_pct"] = 0
                else:
                    binding = index["county_bindings"]["AR"]["official"]
                    binding["rows"].append(dict(county_id="new-county", feature_key="05001"))
                    review["modes"]["official"]["before"] = pin(encoded(binding))
                with self.assertRaises(ValueError):
                    append_county_references(description, files, index, [source])

    def test_mapped_county_cannot_be_added_without_its_native_reference_review(self):
        from scripts.participation_batch import compile_counts
        description, files, index, source, body = self.addition_fixture()
        source["rows"][0]["geography"]["level"] = "county"
        source["rows"][0]["view"].update(geography_level="county", maps_approved=True)
        source["addition"]["records"] = {
            row["id"]: pin(encoded(row)) for row in source["rows"]}
        with self.assertRaisesRegex(ValueError, "Mapped county additions require"):
            compile_counts(description, files, index, [source])

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
