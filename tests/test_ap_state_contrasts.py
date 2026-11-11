import copy
import csv
import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.ap_state_contrasts import build


class APSameTypeContrastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/ap-state-contrasts/20261109-01/prior-complete-ap-state-analysis.zip"
        if not fixture.exists():
            fixture = root / "inputs/prior-complete-ap-state-analysis.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.snapshot = json.loads(archive.read("inputs/selected-inputs.json"))
        cls.query = cls.result(cls.snapshot)

    @staticmethod
    def result(snapshot):
        return list(csv.DictReader(io.StringIO(build(snapshot)["complete-same-type-state-model-contrasts.csv"].decode())))

    def changed(self):
        return copy.deepcopy(self.snapshot)

    def endpoint(self, snapshot, year):
        return next(row for row in snapshot["rows"] if row["year"] == year
                    and row["state_code"] == "CA" and row["dimension"] == "overall"
                    and row["weight_field"] == "POLLCLOSE_STATE_WEIGHT")

    def contrast(self, snapshot):
        return next(row for row in self.result(snapshot) if row["from_year"] == "2020"
                    and row["state_code"] == "CA" and row["dimension"] == "overall"
                    and row["weight_field"] == "POLLCLOSE_STATE_WEIGHT")

    def test_exact_full_denominator_arithmetic_keeps_unknown_model_mass(self):
        snapshot = self.changed()
        self.endpoint(snapshot, "2020").update(weight="10", modeled_voter_weight="6",
            modeled_nonvoter_weight="3", model_unknown_weight="1")
        self.endpoint(snapshot, "2024").update(weight="20", modeled_voter_weight="14",
            modeled_nonvoter_weight="4", model_unknown_weight="2")
        row = self.contrast(snapshot)
        self.assertEqual((row["modeled_voter_pp_contrast"], row["modeled_nonvoter_pp_contrast"],
                          row["modeled_unknown_pp_contrast"]), ("10", "-10", "0"))

    def test_no_cross_type_or_2026_projection_pairs(self):
        self.assertEqual({(row["from_year"], row["to_year"], row["election_type"]) for row in self.query},
                         {("2018", "2022", "midterm"), ("2020", "2024", "presidential")})

    def test_prior_source_hold_does_not_export_endpoint_statistics(self):
        snapshot = self.changed()
        self.endpoint(snapshot, "2020")["disposition"] = "held_source_support_or_complementary_disclosure"
        row = self.contrast(snapshot)
        self.assertEqual(row["disposition"], "held_prior_source_support_inference_or_disclosure")
        self.assertEqual(row["from_n"], row["to_n"], "")
        self.assertEqual(row["modeled_voter_pp_contrast"], "")

    def test_native_label_change_is_not_silently_harmonized(self):
        snapshot = self.changed()
        self.endpoint(snapshot, "2024")["native_labels"] = "Changed source universe"
        self.assertEqual(self.contrast(snapshot)["disposition"], "held_native_label_changed")

    def test_unreconciled_native_model_masses_are_not_renormalized(self):
        snapshot = self.changed()
        self.endpoint(snapshot, "2024")["modeled_voter_weight"] = "0"
        with self.assertRaisesRegex(ValueError, "full native group denominator"):
            self.result(snapshot)

    def test_missing_source_cell_is_not_zero_or_reconstructed(self):
        snapshot = self.changed()
        snapshot["rows"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete prior public query"):
            self.result(snapshot)

    def test_sex_and_gender_variables_are_not_crosswalked(self):
        rows = [row for row in self.query if row["dimension"] in {"SEX", "GENDER"}]
        self.assertTrue(all(row["disposition"] != "selected_same_type_source_model_arithmetic" for row in rows))
        self.assertTrue(all(row["modeled_voter_pp_contrast"] == "" for row in rows))

    def test_race_membership_change_and_absent_2022_dimension_are_held(self):
        rows = [row for row in self.query if row["dimension"] == "RACETH5"]
        self.assertTrue(all(row["disposition"] != "selected_same_type_source_model_arithmetic" for row in rows))
        self.assertTrue(all(row["from_n"] == row["to_n"] == "" for row in rows))

    def test_dc_and_prior_2022_state_inference_holds_are_not_promoted(self):
        rows = [row for row in self.query if row["state_code"] == "DC"
                or row["to_year"] == "2022" and row["state_code"] in {"DE", "WV"}]
        self.assertTrue(all(row["modeled_voter_pp_contrast"] == "" for row in rows))

    def test_no_turnout_causal_panel_or_design_interval_claims(self):
        row = next(row for row in self.query if row["disposition"] == "selected_same_type_source_model_arithmetic")
        for field in ("observed_turnout_change", "causal_effect", "individual_retention_or_switching",
                      "native_definitions_harmonized", "survey_model_or_population_equivalence_validated",
                      "native_weight_stages_are_independent_samples", "local_allocation"):
            self.assertEqual(row[field], "False")
        self.assertEqual(row["design_confidence_interval"], row["population_count_change"], "")


if __name__ == "__main__":
    unittest.main()
