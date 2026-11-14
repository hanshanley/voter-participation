import copy
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.native_reference_model import (
    compare_native_queries, manifest_packet, preservation, revise, verified_prior_query,
)
from scripts.registered_control_successor import FLAGS, csv_bytes, pin


ROOT = Path(__file__).parent


class NativeReferenceModelTests(unittest.TestCase):
    def fixture(self):
        state = dict(
            year="2026", state_code="AA", control_id="control-AA", civic_source_n="10",
            control_measure="source_native_count", control_native_numerator="30",
            control_registered_denominator="300", control_denominator_basis="registered_basis",
            control_native_time="old clock", control_source_url="https://example.test/source",
            reported_cast_ballots="", reported_ballots_per_native_registered_denominator_pct="")
        control = dict(
            year="2026", state_code="AA", id="control-AA", selected_state_reference="True",
            measure="source_native_count", numerator="30", denominator="300",
            denominator_basis="registered_basis", source_time_label="old clock",
            source_url="https://example.test/source")
        scenario = dict(
            year="2026", state_code="AA", control_id="control-AA",
            control_measure="source_native_count", native_registered_denominator="300",
            native_denominator_basis="registered_basis", source_time_label="old clock",
            source_url="https://example.test/source", civic_source_n="10",
            civic_weight="10", civic_modeled_voter_weight="6",
            civic_modeled_nonvoter_weight="4", conditional_modeled_voter_count="180",
            conditional_modeled_nonvoter_count="120", reported_cast_ballot_measure_control="",
            reported_cast_minus_conditional_modeled_voter_count="",
            **{flag: "False" for flag in FLAGS})
        review = dict(
            state_code="AA", control_id="control-AA", year=2026,
            expected_states=["AA", "BB"], expected_table_rows=[2, 2, 1],
            previous_reference=dict(
                numerator=30, registered=300, clock_literal="old literal",
                model_clock="old clock"),
            current_reference=dict(
                numerator=31, registered=300, clock_literal="new literal",
                model_clock="new clock"),
            source_semantics=dict(qualification_flags=dict(
                eligible_population=False, unique_people=False, generic_cast_ballot=False)),
            required_invariants=dict(
                control_measure="source_native_count", denominator_basis="registered_basis",
                source_url="https://example.test/source",
                scenario_values={key: scenario[key] for key in (
                    "civic_source_n", "civic_weight", "civic_modeled_voter_weight",
                    "civic_modeled_nonvoter_weight", "conditional_modeled_voter_count",
                    "conditional_modeled_nonvoter_count")}),
            allowed_changed_fields=dict(
                state=["control_native_numerator", "control_native_time"],
                control=["numerator", "source_time_label"],
                scenario=["source_time_label"]),
            diagnostic_quantum="0.00001")
        native = dict(count=31, registered=300, clock_literal="new literal")
        return (
            [state, dict(state, state_code="BB", control_id="")],
            [control, dict(control, state_code="BB", id="held", selected_state_reference="False")],
            [scenario],
        ), native, review

    def test_revise_changes_only_reviewed_native_fields(self):
        tables, native, review = self.fixture()
        original = copy.deepcopy(tables)
        revised, delta, changes = revise(tables, native, review)
        self.assertEqual(changes["state"][0]["changed_fields"],
                         ["control_native_numerator", "control_native_time"])
        self.assertEqual(changes["control"][0]["changed_fields"],
                         ["numerator", "source_time_label"])
        self.assertEqual(changes["scenario"][0]["changed_fields"], ["source_time_label"])
        self.assertEqual(delta["current_native_minus_model_diagnostic"], "-149.00000")
        self.assertEqual(revised[2][0]["conditional_modeled_voter_count"], "180")
        self.assertEqual(revised[2][0]["conditional_modeled_nonvoter_count"], "120")
        self.assertEqual(revised[0][1], original[0][1])
        self.assertEqual(revised[1][1], original[1][1])
        self.assertEqual(tables, original)

    def test_revise_rejects_mean_flag_or_semantic_promotion(self):
        for mutation in ("mean", "flag", "semantics"):
            tables, native, review = self.fixture()
            if mutation == "mean":
                tables[2][0]["conditional_modeled_voter_count"] = "179"
            elif mutation == "flag":
                tables[2][0][FLAGS[0]] = "True"
            else:
                review["source_semantics"]["qualification_flags"]["unique_people"] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                revise(tables, native, review)

    def test_compare_complete_keys_includes_county_id(self):
        review = {
            "state_code": "AA",
            "previous_reference": {"numerator": 10},
            "current_reference": {"numerator": 11, "reported_units": 1, "total_units": 1},
            "prior_query_contract": {
                "canonical_fields": {
                    "level": "geography_level", "county_id": "county_id",
                    "county": "county", "unit": "unit", "count": "count",
                    "registered": "registered"},
                "key_roles": ["geography_level", "county_id", "county", "unit"],
                "level_roles": {
                    "state": "state", "county": "county", "reporting_unit": "reporting_unit"},
            },
        }
        fields = {
            "geography_level": "level", "county_id": "county_id", "county": "county",
            "unit": "unit", "count": "Ballots", "registered": "Registered"}
        prior = [
            dict(geography_level="state", county_id="", county="AA", unit="",
                 count=10, registered=20),
            dict(geography_level="county", county_id="07", county="Example", unit="",
                 count=10, registered=20),
            dict(geography_level="reporting_unit", county_id="07", county="Example",
                 unit="PCT 1", count=10, registered=20),
        ]
        current = [
            dict(level=row["geography_level"], county_id=row["county_id"],
                 county=row["county"], unit=row["unit"], Ballots=11, Registered=20)
            for row in prior]
        result = compare_native_queries(prior, current, fields, review)
        self.assertTrue(result["all_county_ids_exact"])
        self.assertEqual(result["complete_rows_compared"], 3)
        changed = copy.deepcopy(prior)
        changed[1]["county_id"] = "08"
        with self.assertRaisesRegex(ValueError, "keys differ"):
            compare_native_queries(changed, current, fields, review)

    def test_verified_prior_query_binds_held_ids_not_runtime_values(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            query = [
                dict(geography_level="state", county_id="", county="AA", unit="",
                     count="10", registered="20"),
                dict(geography_level="county", county_id="07", county="Example", unit="",
                     count="10", registered="20"),
                dict(geography_level="reporting_unit", county_id="07", county="Example",
                     unit="PCT 1", count="10", registered="20"),
            ]
            (root / "query.csv").write_bytes(csv_bytes(query))
            identity = {
                "records": [
                    {"geography": {"level": "county"},
                     "source": {"id": "held:counties", "fields": {
                         "county_id": "07", "county": "Example", "ballots": 9,
                         "denominator": 19}}},
                    {"geography": {"level": "reporting_unit"},
                     "source": {"id": "held:units", "fields": {
                         "county_id": "07", "county": "Example", "precinct": "PCT 1",
                         "ballots": 9, "denominator": 19}}},
                ]}
            (root / "identity.json.gz").write_bytes(gzip.compress(
                json.dumps(identity).encode(), mtime=0))
            for name, body in {
                    "state.csv": csv_bytes([dict(
                        native_county="TOTAL", native_precinct="",
                        native_votes_cast="10", native_registered_voters="20")]),
                    "counties.csv": csv_bytes([dict(
                        native_county="Example", native_precinct="",
                        native_votes_cast="10", native_registered_voters="20")]),
                    "units.csv": csv_bytes([dict(
                        native_county="Example", native_precinct="PCT 1",
                        native_votes_cast="10", native_registered_voters="20")]),
            }.items():
                (root / name).write_bytes(body)
            receipt = {
                "contract": "prior.v1", "key": [
                    "geography_level", "county_id", "county", "unit"],
                "query_rows": 3, "identity_source_ids": [
                    "held:counties", "held:units"],
                "runtime_counts_or_registered_used_as_model_values": False,
            }
            (root / "receipt.json").write_text(json.dumps(receipt))
            review = {
                "accepted_outputs": {
                    "state": "state.csv", "counties": "counties.csv",
                    "reporting_units": "units.csv"},
                "prior_query_contract": {
                    "query_input": "query.csv", "query_pin": pin((root / "query.csv").read_bytes()),
                    "receipt_input": "receipt.json",
                    "receipt_pin": pin((root / "receipt.json").read_bytes()),
                    "receipt_contract": "prior.v1",
                    "identity_input": "identity.json.gz",
                    "identity_pin": pin((root / "identity.json.gz").read_bytes()),
                    "identity_source_ids": ["held:counties", "held:units"],
                    "expected_rows": 3,
                    "key_roles": ["geography_level", "county_id", "county", "unit"],
                    "canonical_fields": {
                        "level": "geography_level", "county_id": "county_id",
                        "county": "county", "unit": "unit", "count": "count",
                        "registered": "registered"},
                    "level_roles": {
                        "state": "state", "county": "county",
                        "reporting_unit": "reporting_unit"},
                    "state_identity": ["state", "", "AA", ""],
                    "accepted_columns": {
                        "county": "native_county", "unit": "native_precinct",
                        "count": "native_votes_cast",
                        "registered": "native_registered_voters"},
                },
            }
            result = verified_prior_query(root, review)
            self.assertEqual(result[1]["county_id"], "07")
            self.assertEqual(result[1]["count"], 10)

    def test_manifest_packet_checks_every_member(self):
        member = b"complete selected facts"
        manifest = {
            "members": {"facts.json": pin(member)},
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("facts.json", member)
            archive.writestr("manifest.json", json.dumps(manifest))
        body = stream.getvalue()
        packet, loaded = manifest_packet(body, pin(body))
        self.assertEqual(packet["facts.json"], member)
        self.assertEqual(loaded, manifest)
        with self.assertRaises(ValueError):
            manifest_packet(body + b"changed", pin(body))

    def test_preservation_contract_is_recipe_driven(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            query = csv_bytes([
                dict(state_code="AA", available="True"),
                dict(state_code="BB", available="False"),
            ])
            sensitivity = json.dumps({"rows": [
                {"qualified": True}, {"qualified": False}]}).encode()
            disclosure = json.dumps({
                "qualified_states": 1, "held_states": 1,
                "complete_state_group_metric_variant_witnesses": 2}).encode()
            values = {
                "query.csv": query, "sensitivity.json": sensitivity,
                "disclosure.json": disclosure}
            for name, body in values.items():
                (root / name).write_bytes(body)
            review = {
                "preservation_inputs": {
                    name: pin(body) for name, body in values.items()},
                "preservation_contract": {
                    "query_file": "query.csv", "sensitivity_file": "sensitivity.json",
                    "disclosure_file": "disclosure.json", "query_rows": 2,
                    "state_rows": 2, "qualified_states": 1, "held_states": 1},
            }
            result = preservation(root, review)
            self.assertEqual(result["complete_state_group_metric_variant_rows"], 2)
            self.assertEqual((result["qualified_states"], result["held_states"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
