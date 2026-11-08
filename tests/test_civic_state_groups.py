import copy
import csv
import io
import json
from pathlib import Path
import unittest

from scripts.civic_state_groups import build


INPUT = Path(__file__).parents[1] / "inputs/selected-inputs.json"
if not INPUT.exists():
    INPUT = Path(__file__).parents[1] / "data/civic-state-demographics/20261108-01/selected-inputs.json"


class CivicStateGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(INPUT.read_bytes())

    def test_all_50_models_and_dc_absence_remain_separate(self):
        files = build(self.source)
        rows = list(csv.DictReader(io.StringIO(files["complete-state-demographic-query.csv"].decode())))
        overall = [row for row in rows if row["dimension"] == "overall"]
        self.assertEqual(len(overall), 51)
        self.assertEqual(sum(row["modeled_voter_pct"] != "" for row in overall), 50)
        dc = next(row for row in overall if row["state_code"] == "DC")
        self.assertEqual(dc["modeled_voter_pct"], "")
        self.assertEqual(dc["disposition"], "no_dc_source_sample")

    def test_native_full_model_denominator_is_not_known_vote_choice(self):
        source = copy.deepcopy(self.source)
        row = next(row for row in source["groups"] if row["disposition"] == "selected_broad_source_model")
        row.update(n=200, native_model_voter_cases=100, native_model_nonvoter_cases=100,
                   weight="400", weight_squared="800", modeled_voter_weight="100", modeled_nonvoter_weight="300")
        result = build(source)
        actual = json.loads(result["viewer-data.json"])["groups"][0]
        self.assertEqual(actual["modeled_voter_pct"], "25")
        self.assertFalse(actual["administratively_observed_turnout"])
        self.assertIsNone(actual["estimated_group_participants"])

    def test_held_cell_cannot_export_counts_or_fake_zero_rates(self):
        source = copy.deepcopy(self.source)
        row = next(row for row in source["groups"] if row["disposition"] != "selected_broad_source_model")
        row["n"] = 1
        with self.assertRaises(ValueError):
            build(source)

    def test_missing_duplicate_wrong_year_or_promoted_precision_fail_closed(self):
        for change in ("missing", "duplicate", "year", "precision", "population"):
            source = copy.deepcopy(self.source)
            if change == "missing":
                source["groups"].pop()
            elif change == "duplicate":
                source["groups"][1] = source["groups"][0]
            elif change == "year":
                source["groups"][0]["year"] = 2024
            elif change == "precision":
                source["groups"][0]["design_confidence_interval"] = [0, 100]
            else:
                source["weight_target_and_calibration"] = "registered electorate"
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    build(source)

    def test_sparse_model_class_and_changed_outcome_mass_are_rejected(self):
        for field, value in (("native_model_nonvoter_cases", 1), ("modeled_nonvoter_weight", "0")):
            source = copy.deepcopy(self.source)
            source["groups"][0][field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    build(source)


if __name__ == "__main__":
    unittest.main()
