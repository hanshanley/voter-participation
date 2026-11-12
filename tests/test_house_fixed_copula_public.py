"""Whole-query, source-scope and inner-only decision regressions."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from house_fixed_copula_public import replay

ROOT = Path(__file__).resolve().parents[1]


class PublicCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT/"data/house-fixed-copula/20261112-01/inputs/sufficient-scores.json").read_bytes())
        cls.reference = json.loads((ROOT/"data/house-fixed-copula/20261112-01/inputs/reference-concordance.json").read_bytes())

    def test_complete_replay_and_original_baseline(self):
        output = replay(self.data, self.reference)
        self.assertEqual(len(output), 8)
        for name, body in output.items():
            self.assertEqual(body, (ROOT/"data/house-fixed-copula/20261112-01/outputs"/name).read_bytes())

    def test_reject_incomplete_duplicated_or_unequal_queries(self):
        for field in ("curves", "rows", "decisions"):
            for duplicate in (False, True):
                data = copy.deepcopy(self.data)
                data[field].pop()
                if duplicate:
                    data[field].append(data[field][0])
                with self.assertRaises(ValueError):
                    replay(data, self.reference)
        data = copy.deepcopy(self.data)
        data["curves"][0]["calibration_n"] += 1
        with self.assertRaisesRegex(ValueError, "unequal"):
            replay(data, self.reference)

    def test_reject_outer_selected_theta_and_false_validation(self):
        for field, value in (("population_validation", True), ("source_code_transport_conditional", False)):
            data = copy.deepcopy(self.data)
            data[field] = value
            with self.assertRaises(ValueError):
                replay(data, self.reference)
        data = copy.deepcopy(self.data)
        data["decisions"][0]["selected_theta"] = 64
        with self.assertRaisesRegex(ValueError, "inner-only"):
            replay(data, self.reference)

    def test_reject_negative_or_failed_projection_certificate(self):
        for field, value in (("maximum_case_marginal_error", "-1"), ("maximum_dual_certificate_error", "1e-4"),
                             ("brier_sum", "-1")):
            data = copy.deepcopy(self.data)
            data["curves"][0][field] = value
            with self.assertRaises(ValueError):
                replay(data, self.reference)


if __name__ == "__main__":
    unittest.main()
