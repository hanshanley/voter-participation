import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import source_predictor_blocks as blocks


class SourcePredictorBlockTests(unittest.TestCase):
    def test_native_unknown_categories_remain_distinct(self):
        self.assertEqual(blocks.native_category("", range(1, 7)), "missing")
        self.assertEqual(blocks.native_category("88", range(1, 7)), "disclosure_removed_88")
        self.assertEqual(blocks.native_category("(99) refused", range(1, 7)), "unknown_refused_99")
        self.assertEqual(blocks.native_category("7", range(1, 7)), "other_native_7")

    def test_recalled_no_choice_is_nonvote_not_unknown(self):
        row = dict(P_STATE="(TX) Texas", QPVVOTE20="(1) did not vote", QVOTE2020="",
                   AGE65="3", EDUC="2")
        self.assertEqual(blocks.ap_record(row)["prior_2020_president"], "N")
        self.assertEqual(blocks.choice("4"), "N")
        self.assertEqual(blocks.choice(""), "U")

    def test_zero_and_invalid_weight_routing_is_literal(self):
        self.assertEqual(blocks.route_weight("0")[0], "zero")
        self.assertEqual(blocks.route_weight("-1")[0], "negative")
        self.assertEqual(blocks.route_weight("bad")[0], "invalid")
        self.assertEqual(blocks.route_weight("2.5"), ("positive", 2.5))

    def test_features_exclude_outcomes_and_add_only_declared_interactions(self):
        row = dict(state="TX", p24="D", h22="N", AGE6="3", EDUC="2",
                   RACETH5="1", INCOME="4", SEX="2", RUCC="1")
        result = blocks.predictor_features(row, "prior_state_age_education", "current_chep_holdout")
        self.assertEqual(
            set(result),
            {"state", "p24", "h22", "AGE6", "EDUC",
             "p24_x_AGE6", "p24_x_EDUC", "h22_x_AGE6", "h22_x_EDUC"},
        )
        self.assertFalse(blocks.FORBIDDEN_PREDICTORS & set(result))

    def test_state_split_is_disjoint_and_state_stratified(self):
        records = [{"state": state} for state in ("AA", "BB") for _ in range(10)]
        train, test = blocks.state_stratified_split(records, 7)
        self.assertFalse(set(train) & set(test))
        self.assertEqual(set(train) | set(test), set(range(20)))
        self.assertEqual(sum(records[i]["state"] == "AA" for i in test), 2)
        self.assertEqual(sum(records[i]["state"] == "BB" for i in test), 2)

    def test_weight_normalization_uses_training_rows_only(self):
        values, mean = blocks.normalized_training_weights(
            np.asarray([1.0, 3.0, 1000.0]), np.asarray([0, 1])
        )
        self.assertEqual(mean, 2.0)
        self.assertTrue(np.allclose(values, [.5, 1.5]))

    def test_training_only_vocabulary_does_not_learn_test_level(self):
        from sklearn.feature_extraction import DictVectorizer

        vectorizer = DictVectorizer()
        train = [blocks.predictor_features({"prior_2020_president": "D"}, "prior_only",
                                           "historical_ap_transfer")]
        test = [blocks.predictor_features({"prior_2020_president": "unseen"}, "prior_only",
                                          "historical_ap_transfer")]
        vectorizer.fit(train)
        self.assertNotIn("prior_2020_president=unseen", vectorizer.vocabulary_)
        self.assertEqual(vectorizer.transform(test).nnz, 0)

    def test_marginal_baseline_uses_training_weights(self):
        result = blocks.weighted_marginal(np.asarray([0, 0, 1, 2, 3, 4]),
                                          np.asarray([1, 3, 2, 2, 1, 1], dtype=float))
        self.assertTrue(np.allclose(result, [.4, .2, .2, .1, .1]))

    def test_disclosure_holds_whole_calibration_table(self):
        labels = np.asarray([0] * 30 + [1] * 30 + [2] * 29 + [3] * 30 + [4] * 30)
        probabilities = np.repeat(np.full((1, 5), .2), len(labels), axis=0)
        self.assertIsNone(blocks.calibration_rows(labels, probabilities, np.ones(len(labels))))


if __name__ == "__main__":
    unittest.main()
