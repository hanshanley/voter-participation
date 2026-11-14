import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import apply_metadata_errata
import replay_repaired_facts


class RepairedPublicFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(
            (ROOT / "forensic" / "original-coarse-facts.json").read_bytes()
        )
        cls.erratum = json.loads((ROOT / "ERRATUM.json").read_bytes())
        cls.repaired = json.loads((ROOT / "facts" / "coarse-facts.json").read_bytes())

    def test_errata_transform_reproduces_repaired_facts(self):
        self.assertEqual(
            apply_metadata_errata.repair(self.original, self.erratum),
            self.repaired,
        )

    def test_all_numeric_model_metrics_are_unchanged(self):
        for study, blocks in self.original["results"].items():
            for block, old in blocks.items():
                new = self.repaired["results"][study][block]
                for key in (
                    "source_weighted_log_loss",
                    "source_weighted_multiclass_brier",
                    "known_major_party_source_log_loss",
                    "train_cases",
                    "test_cases",
                    "vocabulary_size",
                    "train_weight_mean_before_normalization",
                ):
                    self.assertEqual(old[key], new[key])

    def test_fit_accounting_is_ten_estimators_two_marginals(self):
        metrics, _ = replay_repaired_facts.flatten(self.repaired)
        self.assertEqual(len(metrics), 12)
        self.assertEqual(
            sum(row["logistic_estimator_fit_performed"] for row in metrics), 10
        )

    def test_chep_rows_are_pooled_presence_not_state_qualification(self):
        rows = [
            row for row in self.repaired["jurisdiction_decisions"]
            if row["study"] == "current_chep2026_holdout"
        ]
        observed = [row for row in rows if row["source_presence"]]
        self.assertEqual(len(observed), 50)
        self.assertTrue(all(row["qualified_for_pooled_source_response_analysis"]
                            for row in observed))
        self.assertTrue(all(
            row["state_inference_qualification"]
            == "not_established_by_held_codebook_evidence" for row in observed
        ))
        self.assertFalse(next(row for row in rows if row["jurisdiction"] == "DC")
                         ["source_presence"])

    def test_historical_scope_is_explicit_common_48(self):
        rows = [
            row for row in self.repaired["jurisdiction_decisions"]
            if row["study"] == "historical_ap2022_to_ap2024"
        ]
        self.assertEqual(
            sum(row["qualified_for_common_48_transfer_score"] for row in rows), 48
        )
        for state in ("DE", "WV", "DC"):
            self.assertFalse(next(row for row in rows if row["jurisdiction"] == state)
                             ["qualified_for_common_48_transfer_score"])

    def test_timing_and_promotion_claims_are_withdrawn(self):
        self.assertFalse(self.repaired["protocol_status"]
                         ["rule_frozen_before_native_fits"])
        promotion = self.repaired["promotion_decision"]
        self.assertFalse(promotion["scientific_promotion"])
        self.assertFalse(promotion["generalization_claim"])
        self.assertEqual(
            promotion["classification"],
            "exploratory_post_hoc_comparison_on_seen_source_outcomes",
        )


if __name__ == "__main__":
    unittest.main()
