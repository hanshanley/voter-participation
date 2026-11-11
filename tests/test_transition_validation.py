import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.transition_validation import historical_validation_decisions, reconcile_return_checks
from scripts.verify_transition_simulation import Verifier


class TransitionValidationTests(unittest.TestCase):
    def test_return_equation_keeps_current_residual_and_prior_office_baseline_separate(self):
        checks = [dict(id="AA-house", state_code="AA", office="house",
            reported_current_margin_pp=20., unallocated_return_minus_model_pp=5.)]
        source = dict(rows=[dict(id="AA-house", state_code="AA", office="house",
            current_return_margin_pp=20., reported_comparison=dict(status="reported_source_comparison",
                previous=dict(D=100, R=100), reported_change_pp=20.))])
        analytic = dict(AA=dict(prior_recalled_margin_pp=10., source_frame_change_pp=5.,
            components_pp=dict(switching=3., denominator=2.)))
        result = reconcile_return_checks(checks, source, analytic)[0]
        self.assertEqual(result["prior_baseline_alignment_pp"], 10.)
        self.assertEqual(result["total_unallocated_alignment_pp"], 15.)
        self.assertEqual(result["reconciliation_residual_pp"], 0.)
        source["rows"][0]["current_return_margin_pp"] = 21.
        with self.assertRaises(ValueError):
            reconcile_return_checks(checks, source, analytic)

    def test_unavailable_same_office_baseline_is_not_zero(self):
        checks = [dict(id="AA-house", state_code="AA", office="house",
            reported_current_margin_pp=20., unallocated_return_minus_model_pp=5.)]
        source = dict(rows=[dict(id="AA-house", state_code="AA", office="house",
            current_return_margin_pp=20., reported_comparison=dict(status="unavailable"))])
        analytic = dict(AA=dict(prior_recalled_margin_pp=10., source_frame_change_pp=5.,
            components_pp=dict(switching=5.)))
        result = reconcile_return_checks(checks, source, analytic)[0]
        self.assertIsNone(result["reported_same_office_change_pp"])
        self.assertIsNone(result["prior_baseline_alignment_pp"])
        self.assertIsNone(result["reconciliation_residual_pp"])

    def test_historical_native_unavailability_is_retained_and_marginals_do_not_validate_transitions(self):
        rows = [dict(year=2024, reference_state_code=code, population_frame="cvap",
            election_type="presidential", reported_voted_pct=value,
            voted_source_sha256="fixture", voted_source_url="https://example.invalid/cps")
            for code, value in (("AA", ""), ("BB", "60"))]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cps.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("complete-state-year-population-pairs.csv", stream.getvalue())
            result = historical_validation_decisions(path)
        self.assertFalse(result["historical_joint_holdout_passed"])
        self.assertIsNone(result["complete_historical_source_decisions"][0]["reported_voted_pct"])
        self.assertEqual(result["complete_historical_source_decisions"][1]["reported_voted_pct"], 60.)
        self.assertTrue(all(row["joint_transition_target"] is None
            for row in result["complete_historical_source_decisions"]))

    def test_independent_checker_rejects_feasible_but_wrong_declared_entropy_coupling(self):
        verifier = Verifier()
        flat = [1 / 25] * 25
        targets = verifier.distribution(flat)
        verifier.entropy_stationarity(flat, targets, 1)
        with self.assertRaisesRegex(ValueError, "relative-entropy optimum"):
            verifier.entropy_stationarity(flat, targets, 16)
        with self.assertRaises(ValueError):
            verifier.distribution([float("nan")] * 25)


if __name__ == "__main__":
    unittest.main()
