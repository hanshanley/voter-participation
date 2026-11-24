import copy
from fractions import Fraction
import unittest

from scripts import statewide_source_model as source


def priors():
    joint = [[(i * 5 + j + 1) / 325 for j in range(5)] for i in range(5)]
    prior = {
        "contract": "participation.norc_house_demographic_priors.v1",
        "categories": list("DRONU"), "source_cases": {"ap2024": 1000, "chep": 1000},
        "source_input_sha256": {"ap2024": "a" * 64, "chep": "b" * 64},
        "raw_records_or_private_fine_cells_exported": False,
        "old_synthetic_state_couplings_used": False,
        "design_confidence_intervals": None, "measured_staying_home": None,
        "assumptions": ["Synthetic test inputs, not empirical estimates"],
        "states": {code: {
            "state_code": code, "source_joint_cells_reconstructed_or_exported": False,
            "prior_joint": copy.deepcopy(joint),
            "groups": [{"dimension": "AGE6", "group": "All", "label": "All source ages",
                        "available": True, "prior_joint": copy.deepcopy(joint)},
                       {"dimension": "AGE6", "group": "held", "label": "Held source category",
                        "available": False, "prior_joint": None}],
        } for code in source.STATES},
    }
    result = {}
    for profile in source.PROFILES:
        for family in source.FAMILIES:
            value = copy.deepcopy(prior)
            if profile != "original":
                value["structural_association_stress"] = {
                    "profile": profile, "current_return_targets_used": False,
                    "state_and_group_year_marginals_preserved": True,
                }
            result[profile + "/" + family] = value
    return result


class StatewideSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.priors = priors()
        cls.product = source.build(cls.priors)

    def test_all_states_use_the_same_unconditioned_method(self):
        metadata = self.product["index"]["metadata"]
        self.assertEqual(metadata["states"], 50)
        self.assertFalse(metadata["return_conditioned"])
        self.assertFalse(metadata["population_calibrated"])
        self.assertFalse(metadata["current_partisan_return_constraints_used"])
        self.assertFalse(metadata["source_weight_calibration_independent_of_returns_qualified"])
        for profile in source.PROFILES:
            for family in source.FAMILIES:
                rows = self.product["profiles"][profile]["models"][family]["rows"]
                self.assertEqual({row["state_code"] for row in rows}, source.STATES)
                self.assertTrue(all(row["available"] for row in rows))

    def test_source_shift_and_partition_accounting(self):
        joint = [[Fraction(i * 5 + j + 1, 325) for j in range(5)] for i in range(5)]
        before = [sum(row) for row in joint]
        after = [sum(joint[i][j] for i in range(5)) for j in range(5)]
        expected = 100 * ((after[0] - after[1]) / (after[0] + after[1])
                          - (before[0] - before[1]) / (before[0] + before[1]))
        for rows in self.product["profiles"]["original"]["models"].values():
            row = rows["rows"][0]
            self.assertAlmostEqual(row["point"]["total_change_pp"], float(expected), places=9)
            self.assertAlmostEqual(sum(row["point"]["contributions_pp"].values()), float(expected), places=9)
            group = row["groups"][0]
            self.assertAlmostEqual(group["point"]["allocated_change_pp"], float(expected), places=9)
            self.assertNotIn("current_margin_pp", group["point"])
            self.assertAlmostEqual(row["point"]["net_participation_pp"],
                                   row["point"]["contributions_pp"]["entry"] +
                                   row["point"]["contributions_pp"]["exit"], places=9)

    def test_recorded_return_changes_and_old_holds_do_not_change_source_estimates(self):
        seed = {"scenarios": {key: {"prior": value, "accepted_result": {"point": 123}}
                              for key, value in self.priors.items()},
                "accepted_candidates": [{"votes": "1"}], "qualification": {"held_state_codes": ["TX"]}}
        seed["accepted_candidates"][0]["votes"] = "999999999"
        seed["qualification"]["held_state_codes"] = list(source.STATES)
        self.assertEqual(source.files(source.from_seed(seed)), source.files(self.product))

    def test_full_sensitivity_includes_every_selected_estimate_and_held_cells_stay_null(self):
        self.assertEqual(len(self.product["queries"]["cases"]), 27)
        for profile in self.product["profiles"].values():
            for model in profile["models"].values():
                for row in model["rows"]:
                    for metric in source.METRICS:
                        value = source.metric_value(row, metric)
                        bounds = row["sensitivity"][metric]
                        self.assertLessEqual(bounds["minimum"] - 1e-10, value)
                        self.assertGreaterEqual(bounds["maximum"] + 1e-10, value)
                    held = row["groups"][1]
                    self.assertIsNone(held["point"])
                    self.assertIsNone(held["joint"])
                    self.assertTrue(all(value is None for value in held["sensitivity"].values()))

    def test_invalid_prior_scope_numbers_and_disclosure_are_rejected(self):
        for change in (lambda p: p["states"].pop("TX"),
                       lambda p: p.update(raw_records_or_private_fine_cells_exported=True),
                       lambda p: p["states"]["TX"]["prior_joint"][0].__setitem__(0, float("nan")),
                       lambda p: p["states"]["TX"]["prior_joint"][0].__setitem__(0, True),
                       lambda p: p["states"]["TX"]["groups"][1].update(prior_joint=[[0] * 5 for _ in range(5)])):
            value = copy.deepcopy(self.priors["original/accepted_ridge_multinomial"])
            change(value)
            with self.assertRaises(ValueError):
                source.validate_prior(value, "original")

    def test_model_families_cannot_change_source_or_demographic_masks(self):
        value = copy.deepcopy(self.priors)
        value["original/extra_randomized_trees"]["source_input_sha256"]["chep"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "Source variants"):
            source.build(value)
        value = copy.deepcopy(self.priors)
        value["original/extra_randomized_trees"]["states"]["TX"]["groups"][1]["label"] = "Different"
        with self.assertRaisesRegex(ValueError, "Source variants"):
            source.build(value)

    def test_dates_are_not_invented_and_serialization_is_order_independent(self):
        self.assertIsNone(self.product["index"]["metadata"]["interview_dates"])
        self.assertIsNone(self.product["index"]["metadata"]["source_fit_date"])
        reordered = dict(reversed(list(self.priors.items())))
        self.assertEqual(source.files(source.build(reordered)), source.files(self.product))


if __name__ == "__main__":
    unittest.main()
