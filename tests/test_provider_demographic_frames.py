import copy
import csv
import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.provider_demographic_frames import analyze


class ProviderDemographicFramesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/provider-demographic-frames/20261109-01/capture-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-provider-capture-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.capture = json.loads(archive.read("qualified-capture.json"))
            cls.components = json.loads(archive.read("native-mode-parent-components.json"))

    def changed(self):
        return copy.deepcopy(self.capture), copy.deepcopy(self.components)

    def query(self, capture, components):
        result = analyze(capture, components)
        read = lambda name: list(csv.DictReader(io.StringIO(result[name].decode())))
        scopes = read("complete-provider-frame-query.csv")
        groups = read("complete-provider-group-compositions.csv")
        scope = next(row for row in scopes if row["state_code"] == "CO" and row["mode_native"] == "inperson"
                     and row["dimension_native"] == "age_range")
        selected = [row for row in groups if row["state_code"] == "CO" and row["mode_native"] == "inperson"
                    and row["dimension_native"] == "age_range"]
        return scope, selected

    def test_composition_uses_own_total_not_larger_mode_parent(self):
        capture, components = self.changed()
        data = capture["datasets"]["CO-inperson-age_range"]["data"]
        data.update(total=10, groups=[dict(group="Known native label", ballots=6), dict(group="Unknown", ballots=4)])
        capture["datasets"]["CO-inperson"]["data"]["total"] = 20
        components["CO-inperson"]["native_count_components"] = [20]
        scope, groups = self.query(capture, components)
        self.assertEqual([row["within_own_demographic_frame_pct"] for row in groups], ["60", "40"])
        self.assertEqual(scope["demographic_minus_mode_total"], "-10")
        self.assertEqual(scope["group_turnout_pct"], "")

    def test_no_unknown_group_is_invented_from_mode_parent_gap(self):
        scope, groups = self.query(self.capture, self.components)
        self.assertEqual(scope["demographic_minus_mode_total"], "-7211")
        self.assertEqual(len(groups), 4)
        self.assertEqual(sum(int(row["native_group_count"]) for row in groups), 130916)
        self.assertEqual(scope["source_discrepancy_imputed_as_unknown_group"], "False")

    def test_missing_response_is_held_without_a_zero_group(self):
        capture, components = self.changed()
        capture["datasets"].pop("CO-inperson-age_range")
        scope, groups = self.query(capture, components)
        self.assertEqual(scope["disposition"], "no_usable_current_demographic_response")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["native_group_count"], groups[0]["within_own_demographic_frame_pct"], "")

    def test_zero_frame_does_not_create_composition_or_zero_turnout(self):
        capture, components = self.changed()
        data = capture["datasets"]["CO-inperson-age_range"]["data"]
        data["total"] = 0
        for group in data["groups"]:
            group["ballots"] = 0
        scope, groups = self.query(capture, components)
        self.assertEqual(scope["disposition"], "held_zero_native_frame_no_composition_or_turnout_inference")
        self.assertEqual(groups[0]["native_group_count"], "")
        self.assertEqual(groups[0]["group_turnout_pct"], "")

    def test_future_source_date_is_held_not_treated_as_current(self):
        capture, components = self.changed()
        capture["datasets"]["CO-inperson-age_range"]["data"]["date"] = "2026-11-10"
        scope, groups = self.query(capture, components)
        self.assertEqual(scope["disposition"], "held_source_date_after_capture")
        self.assertEqual(groups[0]["within_own_demographic_frame_pct"], "")

    def test_duplicate_native_labels_are_rejected(self):
        capture, components = self.changed()
        data = capture["datasets"]["CO-inperson-age_range"]["data"]
        data["groups"].append(dict(data["groups"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate native demographic group"):
            self.query(capture, components)

    def test_negative_native_count_is_not_coerced(self):
        capture, components = self.changed()
        capture["datasets"]["CO-inperson-age_range"]["data"]["groups"][0]["ballots"] = -1
        with self.assertRaisesRegex(ValueError, "native nonnegative integer count"):
            self.query(capture, components)

    def test_unreconciled_own_frame_is_not_renormalized(self):
        capture, components = self.changed()
        capture["datasets"]["CO-inperson-age_range"]["data"]["total"] += 1
        with self.assertRaisesRegex(ValueError, "own source total; no renormalization"):
            self.query(capture, components)

    def test_zero_native_group_and_its_label_are_retained(self):
        capture, components = self.changed()
        capture["datasets"]["CO-inperson-age_range"]["data"].update(
            total=10, groups=[dict(group="Age Over 65", ballots=10), dict(group="Unknown native label", ballots=0)])
        _, groups = self.query(capture, components)
        self.assertEqual(groups[1]["group_label_native"], "Unknown native label")
        self.assertEqual(groups[1]["native_group_count"], "0")
        self.assertEqual(groups[1]["within_own_demographic_frame_pct"], "0")

    def test_missing_mode_parent_does_not_replace_own_frame_or_invent_coverage(self):
        capture, components = self.changed()
        capture["datasets"].pop("CO-inperson")
        components.pop("CO-inperson")
        scope, groups = self.query(capture, components)
        self.assertEqual(scope["mode_parent_native_total"], "")
        self.assertEqual(scope["native_demographic_total"], "130916")
        self.assertEqual(scope["same_date_and_arithmetic_parent_match"], "False")
        self.assertTrue(all(row["within_own_demographic_frame_pct"] for row in groups))

    def test_matching_totals_do_not_hide_different_native_dates(self):
        capture, components = self.changed()
        capture["datasets"]["CO-inperson-age_range"]["data"].update(
            date="2026-11-06", total=138127, groups=[dict(group="Native bin", ballots=138127)])
        scope, _ = self.query(capture, components)
        self.assertEqual(scope["demographic_minus_mode_total"], "0")
        self.assertEqual(scope["same_date_and_arithmetic_parent_match"], "False")
        self.assertEqual((scope["native_source_date"], scope["mode_parent_source_date"]),
                         ("2026-11-06", "2026-11-07"))

    def test_provider_404_is_explicit_absence_not_zero_or_missing_jurisdiction(self):
        result = analyze(self.capture, self.components)
        rows = list(csv.DictReader(io.StringIO(result["complete-provider-frame-query.csv"].decode())))
        absent = [row for row in rows if row["state_code"] in {"AL", "DC", "MA", "NH"}]
        self.assertEqual(len(absent), 32)
        self.assertTrue(all(row["disposition"] == "provider_capability_not_reported_current_capture" for row in absent))
        self.assertTrue(all(row["provider_capability_http_status"] == "404" for row in absent))
        self.assertTrue(all(row["native_demographic_total"] == row["mode_parent_native_total"] == "" for row in absent))


if __name__ == "__main__":
    unittest.main()
