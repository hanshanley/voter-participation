import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from house_four_axis_public import replay
from house_four_axis import OUTCOMES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/"data/house-four-axis/20261112-01"
if not DATA.exists():
    DATA = ROOT.parent


class PublicReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((DATA/"inputs/sufficient-scores.json").read_bytes())

    def test_all_complete_queries_and_source_predictive_simulations_replay(self):
        outputs = replay(self.data)
        for name, body in outputs.items():
            self.assertEqual(body, (DATA/"outputs"/name).read_bytes())

    def test_missing_duplicate_or_unequal_scored_cohorts_fail(self):
        for duplicate in (False, True):
            data = copy.deepcopy(self.data)
            data["rows"].pop()
            if duplicate:
                data["rows"].append(data["rows"][0])
            with self.assertRaises(ValueError):
                replay(data)
        data = copy.deepcopy(self.data)
        data["rows"][0]["weight_sum"] = "1"
        with self.assertRaises(ValueError):
            replay(data)

    def test_whole_held_reference_cannot_disclose_or_promote_rare_cells(self):
        data = copy.deepcopy(self.data)
        held = next(row for row in data["references"] if not row["available"])
        held["cells"] = {}
        with self.assertRaisesRegex(ValueError, "Held"):
            replay(data)
        held["available"] = True
        held["cells"] = {key: dict(n=29, weight="1") for key in OUTCOMES[held["cohort"]]}
        with self.assertRaisesRegex(ValueError, "disclosure"):
            replay(data)

    def test_changed_marginals_unknown_partition_and_false_truth_claims_fail(self):
        for kind in ("margin", "unknown", "population", "certificate"):
            data = copy.deepcopy(self.data)
            if kind == "margin":
                row = next(r for r in data["rows"] if r["cohort"] == "marginal_house" and r["model"] == "fixed_pair_marginals")
                row["nll_sum"] = str(float(row["nll_sum"])+.1)
            elif kind == "unknown":
                data["forecasts"][0]["predictions"].pop("unknown_history_any_house")
            elif kind == "population":
                data["population_validation"] = True
            else:
                data["diagnostics"][0]["maximum_pair_marginal_error"] = .001
            with self.assertRaises(ValueError):
                replay(data)


if __name__ == "__main__":
    unittest.main()
