from decimal import Decimal, localcontext
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import house_pair_public as public


def fixture():
    rows = []
    for frame in public.FRAMES:
        for model in public.MODELS:
            for fold in range(5):
                row = dict(weight_frame=frame, model=model, fold=fold, n=200, weight_sum="200",
                    admin_nll_sum="400", admin_brier_sum="100", house_nll_sum="600",
                    house_brier_sum="120", known_admin_n=150, known_admin_weight_sum="150",
                    known_admin_nll_sum="200", known_admin_brier_sum="80")
                if frame == public.FRAMES[0]:
                    row.update(selected_source_n=120, selected_weight_sum="120",
                        selected_major_nll_sum="166.3553233343868", selected_major_brier_sum="90",
                        selected_major_predictions={key: "30" for key in public.PAIRS})
                rows.append(row)
    reference = dict(population_validation=False, source_code_transport_assumption_required=True,
        decisions=[dict(source="CES_retained_panel", available=True,
                        cells={key: dict(n=150, weight="150", squared_weight="150") for key in public.PAIRS})])
    return dict(rows=rows), reference


class PublicPairTests(unittest.TestCase):
    def test_equal_margins_do_not_identify_switching(self):
        with localcontext() as context:
            context.prec = 70
            target = {key: Decimal(value) for key, value in dict(DD=40, DR=10, RD=20, RR=30).items()}
            weak = public.fit_margins({key: Decimal(25) for key in public.PAIRS}, target)
            strong_prior = {key: Decimal(value) for key, value in dict(DD=50, DR=5, RD=5, RR=40).items()}
            strong = public.fit_margins(strong_prior, target)
            for result in (weak, strong):
                self.assertLess(abs(result["DD"] + result["DR"] - 50), Decimal("1e-50"))
                self.assertLess(abs(result["DD"] + result["RD"] - 60), Decimal("1e-50"))
            self.assertLess(abs(public.odds_ratio(strong) / public.odds_ratio(strong_prior) - 1), Decimal("1e-50"))
            self.assertGreater(abs(public.switch_rate(weak) - public.switch_rate(strong)), 10)

    def test_complete_composition_grid_not_a_confidence_interval(self):
        values = list(public.compositions())
        self.assertEqual(len(values), 126)
        self.assertEqual(sum(m for counts, m in values), 3125)
        self.assertEqual(dict(values)[(1, 1, 1, 1, 1)], 120)

    def test_all_queries_and_correct_weighted_scores_replayed(self):
        inputs, reference = fixture()
        outputs = public.replay(inputs, reference)
        summary = json.loads(outputs["summary.json"])
        self.assertEqual(len(outputs), 7)
        self.assertEqual(summary["source_fold_rows"], 75)
        self.assertEqual(summary["score_rows"], 100)
        self.assertEqual(summary["stress_rows"], 5040)
        self.assertEqual(summary["primary_scores"]["paired_history"]["admin_logloss"], "2.000000000000")
        self.assertFalse(summary["population_validation"])

    def test_unmatched_model_source_frames_rejected(self):
        inputs, reference = fixture()
        inputs["rows"][5]["weight_sum"] = "201"
        with self.assertRaises(ValueError):
            public.replay(inputs, reference)

    def test_missing_queries_or_hidden_private_fields_rejected(self):
        inputs, reference = fixture()
        inputs["rows"].pop()
        with self.assertRaises(ValueError):
            public.replay(inputs, reference)
        inputs, reference = fixture()
        inputs["rows"][0]["per_case_prediction"] = [0.1]
        with self.assertRaises(ValueError):
            public.replay(inputs, reference)


if __name__ == "__main__":
    unittest.main()
