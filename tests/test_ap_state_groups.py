import copy
import csv
import io
import json
from pathlib import Path
import unittest

from scripts.ap_state_groups import build, select_private, WEIGHTS, YEARS


class HistoricalAPStateGroupsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/ap-state-demographics/20261109-01/selected-inputs.json"
        if not fixture.exists():
            fixture = root / "inputs/selected-inputs.json"
        cls.snapshot = json.loads(fixture.read_bytes())

    def changed(self):
        return copy.deepcopy(self.snapshot)

    def selected(self, snapshot):
        return next(row for row in snapshot["rows"]
                    if row["disposition"] == "selected_broad_source_model"
                    and row["dimension"] != "overall")

    def test_denominator_includes_unknown_model_weight(self):
        snapshot = self.changed()
        source = self.selected(snapshot)
        source.update(weight="10", modeled_voter_weight="6",
                      modeled_nonvoter_weight="3", model_unknown_weight="1")
        query = list(csv.DictReader(io.StringIO(build(snapshot)["complete-state-demographic-query.csv"].decode())))
        row = next(row for row in query if all(row[key] == source[key]
                   for key in ("year", "weight_field", "state_code", "dimension", "group")))
        self.assertEqual((row["modeled_voter_pct"], row["modeled_nonvoter_pct"],
                          row["modeled_unknown_pct"]), ("60", "30", "10"))

    def test_held_cell_statistics_cannot_be_exported(self):
        snapshot = self.changed()
        next(row for row in snapshot["rows"] if row["disposition"].startswith("held"))["n"] = 1
        with self.assertRaisesRegex(ValueError, "Held-cell statistics"):
            build(snapshot)

    def test_dc_cannot_be_synthesized_from_other_states(self):
        snapshot = self.changed()
        row = next(row for row in snapshot["rows"] if row["state_code"] == "DC")
        row["disposition"] = "selected_broad_source_model"
        with self.assertRaisesRegex(ValueError, "Absent, removed or withheld"):
            build(snapshot)

    def test_missing_2022_race_dimension_cannot_be_crosswalked(self):
        snapshot = self.changed()
        row = next(row for row in snapshot["rows"] if row["year"] == "2022"
                   and row["state_code"] == "CA" and row["dimension"] == "RACETH5")
        row["disposition"] = "selected_broad_source_model"
        with self.assertRaisesRegex(ValueError, "Absent, removed or withheld"):
            build(snapshot)

    def test_2022_publisher_state_holds_cannot_be_removed(self):
        snapshot = self.changed()
        row = next(row for row in snapshot["rows"] if row["year"] == "2022"
                   and row["state_code"] == "DE")
        row["disposition"] = "selected_broad_source_model"
        with self.assertRaisesRegex(ValueError, "Absent, removed or withheld"):
            build(snapshot)

    def test_2018_state_inference_cannot_be_promoted(self):
        snapshot = self.changed()
        row = next(row for row in snapshot["rows"] if row["year"] == "2018")
        row["inference_status"] = "publisher_state_weight_descriptive_not_administrative_turnout"
        with self.assertRaisesRegex(ValueError, "state inference qualification"):
            build(snapshot)

    def test_insufficient_positive_weight_support_is_not_raw_sample_support(self):
        snapshot = self.changed()
        self.selected(snapshot)["positive_weight_n"] = 499
        with self.assertRaisesRegex(ValueError, "positive-weight source sample"):
            build(snapshot)

    def test_per_model_class_case_support_cannot_be_claimed(self):
        snapshot = self.changed()
        snapshot["qualification"]["no_per_model_class_case_support_claim"] = False
        with self.assertRaisesRegex(ValueError, "source, disclosure or population"):
            build(snapshot)

    def test_private_extra_input_fields_are_not_permitted(self):
        snapshot = self.changed()
        snapshot["respondent_records"] = []
        with self.assertRaisesRegex(ValueError, "Unapproved fields"):
            build(snapshot)

    def test_class_masses_cannot_be_renormalized_over_missing_weight(self):
        snapshot = self.changed()
        self.selected(snapshot)["modeled_voter_weight"] = "0"
        with self.assertRaisesRegex(ValueError, "denominator does not reconcile"):
            build(snapshot)

    @staticmethod
    def synthetic(state, group, n, weight):
        return dict(year="2024", weight_field=weight, scope=state,
                    dimension="EDUC", group=group, native_labels="Synthetic group",
                    n=str(n), positive_weight_n=str(n), weight=str(n),
                    modeled_voter_weight=str(n), modeled_nonvoter_weight="0",
                    model_unknown_weight="0")

    def policy(self, cells):
        waves = {year: [] for year in YEARS}
        waves["2024"] = cells
        result = select_private(waves, {"provenance": self.snapshot["provenance"]})
        return {(row["state_code"], row["weight_field"], row["dimension"], row["group"]): row
                for row in result["rows"] if row["year"] == "2024"}

    def test_positive_unknown_complement_holds_an_additional_large_group(self):
        cells = [self.synthetic("CA", group, n, weight)
                 for weight in WEIGHTS for group, n in (("1", 900), ("2", 600), ("99", 1))]
        query = self.policy(cells)
        for weight in WEIGHTS:
            self.assertEqual(query["CA", weight, "EDUC", "1"]["disposition"],
                             "held_source_support_or_complementary_disclosure")
            self.assertIsNone(query["CA", weight, "EDUC", "1"]["n"])
            self.assertEqual(query["CA", weight, "EDUC", "2"]["disposition"], "selected_broad_source_model")

    def test_across_state_singleton_holds_another_state(self):
        cells = [self.synthetic(state, group, n, weight)
                 for weight in WEIGHTS
                 for state, group, n in (("CA", "1", 900), ("NY", "1", 1),
                                          ("CA", "2", 600), ("NY", "2", 600))]
        query = self.policy(cells)
        for weight in WEIGHTS:
            self.assertEqual(query["CA", weight, "EDUC", "1"]["disposition"],
                             "held_source_support_or_complementary_disclosure")

    def test_low_support_in_one_stage_holds_both_stage_views(self):
        cells = [self.synthetic("CA", "1", n, weight)
                 for weight, n in zip(WEIGHTS, (900, 499))]
        query = self.policy(cells)
        self.assertTrue(all(query["CA", weight, "EDUC", "1"]["n"] is None for weight in WEIGHTS))

    def test_mismatched_stage_masks_are_rejected(self):
        snapshot = self.changed()
        row = self.selected(snapshot)
        row["disposition"] = "held_source_support_or_complementary_disclosure"
        for field in ("n", "positive_weight_n", "weight", "modeled_voter_weight",
                      "modeled_nonvoter_weight", "model_unknown_weight"):
            row[field] = None
        with self.assertRaisesRegex(ValueError, "Different-stage mask"):
            build(snapshot)


if __name__ == "__main__":
    unittest.main()
