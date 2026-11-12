import copy
import gzip
import json
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
import zipfile

from scripts.participation_batch import compressed, discover, display, execute
from scripts.participation_intake.adapters import adapt
from scripts.participation_intake.contract import STATES, digest, encoded, pin


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
