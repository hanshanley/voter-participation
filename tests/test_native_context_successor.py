import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.native_context_successor import build, export, revise, source_facts, source_packet
from scripts.registered_control_successor import TABLES, csv_bytes, encoded, pin


def fixture():
    columns = ["state", "parent", "unit", "reported", "registered_open", "registered_day", "mode", "total"]
    raw = b"AA;p;1;1;9;1;7;1\nAA;p;2;1;0;0;0;0\n"
    records = [dict(zip(columns, ["AA", "p", "1", "1", 9, 1, 7, 1])),
               dict(zip(columns, ["AA", "p", "2", "1", 0, 0, 0, 0]))]
    queries = dict(units=[dict(source=r, reported=True, total=r["total"],
        residual=r["total"]-r["mode"], excess=r["total"]-r["registered_open"]-r["registered_day"],
        rate=None) for r in records], parents=[dict(id="p", native=dict(
            rows=2, total=1, registered_open=9, registered_day=1, conflicts=1, excesses=0))])
    receipt = dict(url="https://source.example/2026.txt", status=200, **pin(raw))
    page = dict(source_text=["Unofficial election 2026", "Open register:", "9"],
                clock="11/10/26 8:08 AM", timezone=None)
    files = {"native.txt": raw, "receipt.json": encoded(receipt),
             "queries.json": encoded(queries), "page.json": encoded(page)}
    fields = ("id", "state_code", "year", "geographic_level", "geography", "source_family",
              "measure", "native_measure", "numerator", "denominator", "denominator_basis",
              "denominator_label", "source_time_label", "source_url", "native_status",
              "source_kind", "scope_notes", "selected_state_reference", "disposition")
    control = dict.fromkeys(fields, "")
    control.update(id="old-context", state_code="AA", year="2026",
                   geographic_level="partial_state_reporting_units", numerator="0",
                   denominator="5", source_url=receipt["url"], selected_state_reference="False")
    other = dict(control, id="other", state_code="BB")
    tables = ([dict(state_code="AA", control_id="dated", modeled="7.125"),
               dict(state_code="BB", control_id="other", modeled="8.5")], [control, other],
              [dict(state_code="AA", control_id="dated", modeled_voter="7.125", modeled_nonvoter="2.875")])
    review = dict(
        contract="participation.native_context_successor.v1", version=30, year=2026,
        state_code="AA", control_id="old-context", input_pins={},
        expected_states=["AA", "BB"], expected_table_rows=[2, 2, 1],
        source_members=dict(table="native.txt", receipt="receipt.json", queries="queries.json", page="page.json"),
        source_url=receipt["url"], expected_units=2, expected_parents=1,
        table=dict(delimiter=";", columns=columns, numeric_fields=columns[4:],
                   identity_fields=["parent", "unit"], parent_field="parent", state_field="state",
                   reported_field="reported", numerator_field="total",
                   denominator_fields=["registered_open", "registered_day"], component_fields=["mode"]),
        query=dict(units="units", parents="parents", source_record="source", parent_id="id",
                   parent_native_record="native", reported="reported", numerator="total",
                   component_residual="residual", electorate_excess="excess", rate="rate",
                   parent_rows="rows", parent_numerator="total",
                   parent_registered_fields={"registered_open": "registered_open", "registered_day": "registered_day"},
                   parent_conflicts="conflicts", parent_excesses="excesses"),
        page=dict(year_literal="Unofficial election 2026", clock="clock", timezone="timezone",
                  register_control="Open register:", register_field="registered_open"),
        scope_review="Complete native context only; preserve the separate dated register and model.")
    return files, tables, review


def archive(files, manifest_name, key=None):
    files = dict(files)
    manifest = {name: pin(body) for name, body in files.items()}
    files[manifest_name] = encoded({key: manifest} if key else manifest)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        for name, body in files.items():
            output.writestr(name, body)
    return stream.getvalue()


class NativeContextSuccessorTests(unittest.TestCase):
    def test_derives_complete_counts_without_repairing_components_or_zeros(self):
        files, _, review = fixture()
        facts = source_facts(files, review)
        summary = facts["summary"]
        self.assertEqual(summary["derived_native_numerator"], 1)
        self.assertEqual(summary["native_registration_components"], {"registered_open": 9, "registered_day": 1})
        self.assertEqual(summary["native_component_conflicts"], 1)
        self.assertEqual(summary["explicit_reported_zero_rows"], 1)
        self.assertEqual(facts["units"][0]["component_residual"], -6)
        self.assertTrue(all(row["analysis_rate"] is None for row in facts["units"]))
        self.assertIsNone(summary["independently_printed_state_count"])

    def test_rejects_repaired_changed_missing_or_duplicate_native_units(self):
        for change in ("count", "reported", "duplicate", "missing", "year", "register", "query_rate"):
            with self.subTest(change=change):
                files, _, review = fixture()
                if change == "count":
                    files["native.txt"] = files["native.txt"].replace(b";7;1\n", b";7;2\n")
                elif change == "reported":
                    files["native.txt"] = files["native.txt"].replace(b"AA;p;1;1;", b"AA;p;1;0;")
                elif change == "duplicate":
                    files["native.txt"] = files["native.txt"].replace(b"AA;p;2;", b"AA;p;1;")
                elif change == "missing":
                    files["native.txt"] = files["native.txt"].splitlines(keepends=True)[0]
                elif change in ("year", "register"):
                    page = json.loads(files["page.json"])
                    page["source_text"][0 if change == "year" else 2] = "2024" if change == "year" else "10"
                    files["page.json"] = encoded(page)
                else:
                    queries = json.loads(files["queries.json"])
                    queries["units"][0]["rate"] = 0.1
                    files["queries.json"] = encoded(queries)
                receipt = json.loads(files["receipt.json"])
                receipt.update(pin(files["native.txt"]))
                files["receipt.json"] = encoded(receipt)
                with self.assertRaises(ValueError):
                    source_facts(files, review)

    def test_only_one_nonselected_context_changes_not_model_or_registration(self):
        files, tables, review = fixture()
        before = copy.deepcopy(tables)
        updated, changes, change = revise(tables, source_facts(files, review), review)
        self.assertEqual(tables, before)
        self.assertEqual(updated[0], tables[0])
        self.assertEqual(updated[2], tables[2])
        self.assertEqual(updated[1][1], tables[1][1])
        self.assertEqual(updated[1][0]["numerator"], "1")
        self.assertEqual(updated[1][0]["denominator"], "10")
        self.assertEqual(sum(row["changed"] for row in changes), 1)
        self.assertFalse(change["conditional_modeled_counts_changed"])
        self.assertIn("not_qualified_physical_ballots", updated[1][0]["measure"])
        with self.assertRaises(ValueError):
            revise(updated, source_facts(files, review), review)

    def test_cannot_change_selected_reference_or_scenario(self):
        for location in ("control", "state", "scenario", "county"):
            with self.subTest(location=location):
                files, tables, review = fixture()
                if location == "control":
                    tables[1][0]["selected_state_reference"] = "True"
                elif location == "state":
                    tables[0][0]["control_id"] = "old-context"
                elif location == "scenario":
                    tables[2][0]["control_id"] = "old-context"
                else:
                    tables[1][0]["geographic_level"] = "county"
                with self.assertRaises(ValueError):
                    revise(tables, source_facts(files, review), review)

    def test_rejects_metadata_counts_and_incomplete_component_contract(self):
        for change in ("count", "component", "roles"):
            files, _, review = fixture()
            if change == "count":
                review["replacement_count"] = 999
            elif change == "component":
                review["query"]["parent_registered_fields"].pop("registered_day")
            else:
                review["table"]["denominator_fields"] = ["total"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                source_facts(files, review)

    def test_complete_export_retains_prior_queries_and_whole_sufficient_inputs(self):
        files, tables, review = fixture()
        baseline = {name: csv_bytes(rows) for name, rows in zip(TABLES, tables)}
        baseline.update({"complete-other-query.csv": b"native,value\nold,7\n",
                         "registered-frame-change.json": encoded({"prior": "retained"}),
                         "summary.json": encoded({"native_control_version": 29}),
                         "source-qualification.json": encoded({"previous_hold": True})})
        baseline_body = archive(baseline, "checksums.json")
        source_body = archive(files, "manifest.json", "files")
        review["input_pins"] = dict(baseline=pin(baseline_body), native_source=pin(source_body))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "inputs"
            inputs.mkdir()
            (inputs / "baseline-complete-analysis.zip").write_bytes(baseline_body)
            (inputs / "native-source-complete-analysis.zip").write_bytes(source_body)
            (inputs / "reviewed-successor.json").write_bytes(encoded(review))
            summary = export(inputs, root / "output")
            self.assertEqual(summary["changed_existing_scenarios"], 0)
            with zipfile.ZipFile(root / "output/complete-analysis.zip") as result:
                for name in (TABLES[0], TABLES[2], "complete-other-query.csv", "registered-frame-change.json"):
                    self.assertEqual(result.read(name), baseline[name])
                self.assertEqual(result.read("inputs/baseline-complete-analysis.zip"), baseline_body)
                self.assertEqual(result.read("inputs/native-source-complete-analysis.zip"), source_body)
            review["version"] = 29
            (inputs / "reviewed-successor.json").write_bytes(encoded(review))
            with self.assertRaises(ValueError):
                build(inputs)

    def test_source_packet_requires_every_original_and_query_pin(self):
        files, _, _ = fixture()
        body = archive(files, "manifest.json", "files")
        self.assertEqual(source_packet(body, pin(body))["native.txt"], files["native.txt"])
        with self.assertRaises(ValueError):
            source_packet(body, dict(bytes=len(body), sha256="0" * 64))
        files["../outside"] = b"unreviewed"
        body = archive(files, "manifest.json", "files")
        with self.assertRaises(ValueError):
            source_packet(body, pin(body))


if __name__ == "__main__":
    unittest.main()
