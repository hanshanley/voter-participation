import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import ak_senate_controls as primary
from scripts import verify_ak_senate_controls as independent


INPUTS = Path(os.environ.get("AK_SENATE_INPUTS",
    Path(__file__).resolve().parents[1] / "data/ak-senate-native-controls/20261112-01"))


class AlaskaSenateControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = primary.load(INPUTS)
        cls.result = primary.build(*cls.inputs)

    def test_native_scope_qualifies_four_controls_not_boroughs(self):
        qualified = [r for r in self.result["scope_candidate_checks"] if r["native_role_state_control_qualified"]]
        self.assertEqual(len(qualified), 4)
        self.assertTrue(all(r["native_units"] == 31 and r["source_minus_state"] == 0 for r in qualified))
        self.assertTrue(all(r["source_minus_state"] != 0 for r in self.result["scope_candidate_checks"] if r["scope"] == "boroughs"))
        nested = [r for r in self.result["scope_candidate_checks"] if r["scope"] == "house_districts_plus_explicit_overseas"]
        self.assertTrue(all(r["source_minus_nested_state"] == 0 and r["source_minus_state"] != 0 for r in nested))

    def test_missing_district_or_overseas_never_becomes_zero_or_qualified(self):
        for unit in ("house_district_40", "federal_overseas_absentee"):
            changed = copy.deepcopy(self.inputs)
            changed[2][:] = [r for r in changed[2] if not
                (r["provider"] == "civic" and r["state"] == "AK" and r["native_unit_id"] == unit)]
            value = primary.build(*changed)
            self.assertEqual(value["summary"]["qualified_state_accounting_controls"], 229)
            self.assertTrue(all(r["alternative_native_votes"] is None for r in value["control_decisions"] if r["state"] == "AK"))

    def test_duplicate_candidate_and_changed_state_control_fail(self):
        changed = copy.deepcopy(self.inputs)
        changed[2].append(next(r for r in changed[2] if r["state"] == "AK" and r["provider"] == "civic").copy())
        with self.assertRaises(ValueError):
            primary.build(*changed)
        changed = copy.deepcopy(self.inputs)
        next(r for r in changed[1] if r["state"] == "AK")["native_state_votes"] = "0"
        with self.assertRaises(ValueError):
            primary.build(*changed)

    def test_partial_round_one_is_not_turnout_or_final_RCV_and_ME_stays_held(self):
        self.assertEqual(self.result["summary"]["partial_percent_reporting"], 73.9)
        self.assertIsNone(self.result["summary"]["registered_voters"])
        self.assertTrue(all(not r["final_RCV_qualified"] and r["turnout"] is None for r in self.result["scope_margins"]))
        row = next(r for r in self.result["control_decisions"] if r["state"] == "ME" and r["candidate"] == "Write-in")
        self.assertEqual(row["county_plus_explicit_unlocated_minus_state"], "-882")
        self.assertIsNone(row["selected_state_accounting_scope"])
        self.assertEqual(self.result["summary"]["prior_different_counts_preserved"], 215)

    def test_roundtrip_and_independent_verifier_reject_count_repair(self):
        self.assertEqual(primary.files(self.result, self.inputs[3]),
                         primary.files(json.loads(primary.encoded(self.result)), self.inputs[3]))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for path, body in primary.files(self.result, self.inputs[3]).items():
                (root / path).write_bytes(body)
            self.assertEqual(independent.verify(INPUTS, root)["separate_state_accounting_qualified"], 233)
            changed = copy.deepcopy(self.result)
            next(r for r in changed["control_decisions"] if r["state"] == "ME" and r["candidate"] == "Write-in")[
                "county_plus_explicit_unlocated_minus_state"] = "0"
            for path, body in primary.files(changed, self.inputs[3]).items():
                (root / path).write_bytes(body)
            with self.assertRaises(ValueError):
                independent.verify(INPUTS, root)


if __name__ == "__main__":
    unittest.main()
