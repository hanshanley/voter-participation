import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.mevp_state_participation import build, load_inputs, result_files
from scripts.verify_mevp_state_participation import verify


INPUTS = Path(os.environ.get("MEVP_PARTICIPATION_INPUTS",
    Path(__file__).resolve().parents[1] / "data/participation-mevp-state-participation/20261111-01"))


class MevpParticipantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = load_inputs(INPUTS)
        cls.result = build(*cls.inputs)

    def test_only_actual_state_columns_supply_state_profiles(self):
        rows = {(row["scope"], row["source_group"]): row for row in self.result["profiles"]}
        self.assertEqual(rows["AZ", "latino"]["first_2026_pct"], 11)
        self.assertEqual(rows["TX", "latino"]["first_2026_pct"], 22)
        self.assertNotIn(("NY", "latino"), rows)
        dc = [row for row in self.result["state_group_decisions"] if row["state_code"] == "DC"]
        self.assertEqual(len(dc), 5)
        self.assertTrue(all(row["profile"] is None for row in dc))

    def test_printed_rounding_residual_is_signed_and_not_renormalized(self):
        row = next(row for row in self.result["profiles"] if row["scope"] == "US" and row["source_group"] == "latino")
        self.assertEqual((row["first_2026_pct"], row["reported_prior_bin_sum_pct"]), (17, 84))
        self.assertEqual(row["printed_history_sum_pct"], 101)
        self.assertEqual(row["signed_unallocated_rounding_or_response_pp"], -1)
        self.assertEqual(row["history_pct"]["first_2026"], 17)

    def test_partisan_and_multistate_banners_do_not_become_state_estimates(self):
        context = [row for row in self.result["source_column_decisions"] if row["scope"] is None]
        self.assertEqual(len(context), 35)
        self.assertTrue(all(row["disposition"] == "excluded_multistate_or_partisan_context" for row in context))
        native = [row for row in self.result["state_group_decisions"] if row["source_group"] == "native-american"]
        self.assertTrue(all(row["profile"] is None for row in native))

    def test_no_multiresponse_union_or_population_absence_is_invented(self):
        self.assertTrue(all(row["any_experience_union_pct"] is None
            and row["turnout_or_absence_estimate"] is None and row["first_ever_voter_estimate"] is None
            and row["design_confidence_interval"] is None for row in self.result["profiles"]))
        row = next(row for row in self.result["profiles"] if row["scope"] == "TX" and row["source_group"] == "latino")
        self.assertEqual(row["experience_pct"]["waiting_line"], 27)
        self.assertEqual(row["experience_pct"]["none_selected"], 54)

    def test_small_supplied_state_is_held_not_imputed_or_called_absent(self):
        facts, states, methods, policy = copy.deepcopy(self.inputs)
        facts["tables"][0]["raw_respondent_n"][1] = 99
        result = build(facts, states, methods, policy)
        row = next(row for row in result["state_group_decisions"]
            if row["state_code"] == "AZ" and row["source_group"] == "latino")
        self.assertIsNone(row["profile"])
        self.assertEqual(row["disposition"], "held_raw_source_support")
        with self.assertRaisesRegex(ValueError, "policy"):
            build(facts, states, methods, dict(policy, renormalize_history_bins=True))

    def test_source_zero_and_independent_query_bytes_survive_serialization(self):
        facts, states, methods, policy = copy.deepcopy(self.inputs)
        facts["tables"][0]["experience_pct"]["language_information"][1] = 0
        result = build(facts, states, methods, policy)
        row = next(row for row in result["profiles"] if row["scope"] == "AZ" and row["source_group"] == "latino")
        self.assertEqual(row["experience_pct"]["language_information"], 0)
        self.assertEqual(result_files(self.result),
            result_files(json.loads(json.dumps(self.result, sort_keys=True))))

    def test_independent_verifier_rejects_repaired_bins_and_invented_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, body in result_files(self.result).items():
                (output / name).write_bytes(body)
            self.assertEqual(verify(INPUTS, output)["native_state_group_profiles"], 11)
            altered = copy.deepcopy(self.result)
            altered["profiles"][0]["signed_unallocated_rounding_or_response_pp"] = 0
            (output / "complete-result.json").write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "residual"):
                verify(INPUTS, output)
            altered = copy.deepcopy(self.result)
            altered["profiles"][0]["turnout_or_absence_estimate"] = 20
            (output / "complete-result.json").write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, "Invented"):
                verify(INPUTS, output)


if __name__ == "__main__":
    unittest.main()
