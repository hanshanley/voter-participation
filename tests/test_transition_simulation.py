import math
import unittest
import warnings

import numpy as np

from scripts.transition_simulation import (
    CELLS, MATRIX, allocate_agents, calibrate_persistence, condition_participation,
    fit_coupling, poll_switching_targets, summarize)


def published_poll(state, switching_pct=4):
    return dict(state_code=state, office="senate", source_url="https://example.invalid/poll",
        source_sha256="fixture", source_timestamp="2026-11-04",
        status="published_joint_question_reviewed",
        composition_quality="within_four_row_rounding_tolerance",
        joint_question_rows={prior: dict(prior_choice_share_pct=50,
            current_choice_pct_within_prior_choice={current: switching_pct})
            for prior, current in (("D", "R"), ("R", "D"))},
        arithmetic_from_rounded_percentages_per_100_current_group_voters={
            "gross_reported_major_party_switchers": switching_pct})


class TransitionSimulationTests(unittest.TestCase):
    def test_agent_budget_and_floors_are_conserved_for_lopsided_states(self):
        result = allocate_agents({"large": 999999, "small": 1, "tiny": 0.01}, 10000, 500)
        self.assertEqual(sum(result.values()), 10000)
        self.assertTrue(all(value >= 500 for value in result.values()))
        with self.assertRaises(ValueError):
            allocate_agents({"A": 1, "B": 1}, 100, 100)

    def test_multiple_synthetic_couplings_match_public_moments_without_identifying_gross_flows(self):
        original = np.full(len(CELLS), 1 / len(CELLS))
        target = MATRIX @ original
        flat, _ = fit_coupling(target, 1)
        persistent, _ = fit_coupling(target, 16)
        self.assertTrue(np.all(np.abs(MATRIX @ flat - target) <= 2e-10))
        self.assertTrue(np.all(np.abs(MATRIX @ persistent - target) <= 2e-10))
        self.assertGreater(summarize(persistent)["synthetic_retaining_share_of_recalled_major_party"],
            summarize(flat)["synthetic_retaining_share_of_recalled_major_party"])
        self.assertFalse(summarize(flat)["identified_individual_histories"])

    def test_demographic_model_class_conditioning_does_not_make_an_unknown_probability_zero(self):
        original = np.full(len(CELLS), 1 / len(CELLS))
        result = condition_participation(original, 0.6)
        self.assertTrue(math.isclose(float(result.sum()), 1))
        self.assertTrue(math.isclose(summarize(result)["modeled_nonvoter_share"], 0.6))
        with self.assertRaises((ValueError, TypeError)):
            condition_participation(original, None)

    def test_seeded_agents_keep_exact_margin_accounting_and_are_reproducible(self):
        generator = np.random.default_rng(42)
        probabilities = np.arange(1, len(CELLS) + 1, dtype=float)
        probabilities /= probabilities.sum()
        counts = generator.multinomial(20000, probabilities)
        repeated = np.random.default_rng(42).multinomial(20000, probabilities)
        self.assertEqual(counts.tolist(), repeated.tolist())
        result = summarize(counts / counts.sum())
        self.assertAlmostEqual(sum(result["components_pp"].values()), result["source_frame_change_pp"])
        self.assertIsNone(result["measured_staying_home"])

    def test_released_texas_moments_fit_without_numerical_warnings_across_prior_strengths(self):
        target = np.asarray([-.022529535879513618, .4659859018904002,
            .033360147633152704, .5387116139268194, .43669857290536623,
            .017981744492120796, -.0042317193269467025, .03209106083080037,
            .006258451303948791, .003790146212743064])
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            for factor in (.5, 1, 4, 16, 256):
                result, diagnostic = fit_coupling(target, factor)
                self.assertLessEqual(diagnostic["maximum_moment_residual"], 2e-10)
                self.assertTrue(np.isfinite(result).all())
                self.assertTrue(np.all(result >= 0))

    def test_missing_native_switching_cell_is_held_but_rounded_zero_has_positive_upper_bound(self):
        missing, zero = published_poll("AA"), published_poll("BB", 0)
        missing["joint_question_rows"]["D"]["current_choice_pct_within_prior_choice"]["R"] = None
        rows = poll_switching_targets({"missing": missing, "zero": zero}, {"AA", "BB"})
        self.assertIsNone(rows[0]["target_fraction"])
        self.assertEqual(rows[1]["target_fraction"], 0)
        self.assertGreater(rows[1]["rounding_only_bounds"][1], 0)
        self.assertIsNone(rows[1]["nonvoter_estimate"])

    def test_state_blocked_calibration_excludes_every_same_state_office(self):
        target = MATRIX @ np.full(len(CELLS), 1 / len(CELLS))
        targets = {code: target for code in ("AA", "BB", "CC")}
        polls = {code + "-senate": published_poll(code) for code in targets}
        polls["AA-governor"] = dict(published_poll("AA"), office="governor")
        original = calibrate_persistence(targets, polls, (1., 4., 16.))
        polls["AA-senate"] = published_poll("AA", 40)
        polls["AA-governor"] = dict(published_poll("AA", 40), office="governor")
        changed = calibrate_persistence(targets, polls, (1., 4., 16.))
        before = next(row for row in original["folds"] if row["heldout_state"] == "AA")
        after = next(row for row in changed["folds"] if row["heldout_state"] == "AA")
        self.assertEqual(before, after)
        self.assertEqual(after["training_states"], ["BB", "CC"])
        self.assertEqual(len([row for row in changed["heldout_predictions"]
            if row["state_code"] == "AA"]), 2)
        self.assertFalse(changed["reported_returns_used_for_calibration"])

    def test_infeasible_and_nonfinite_public_moments_are_rejected(self):
        target = MATRIX @ np.full(len(CELLS), 1 / len(CELLS))
        for value in (2., float("nan")):
            broken = target.copy()
            broken[1] = value
            with self.assertRaises(ValueError):
                fit_coupling(broken)


if __name__ == "__main__":
    unittest.main()
