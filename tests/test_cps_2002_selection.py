import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import shutil
import unittest

from scripts.cps_2002_selection import build, load_inputs, result_files
from scripts.verify_cps_2002_selection import verify


INPUTS = Path(os.environ.get("CPS_2002_INPUTS",
    Path(__file__).resolve().parents[1] / "data/participation-cps-2002/20261111-01"))


class Cps2002SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = load_inputs(INPUTS)
        cls.result = build(*cls.inputs)

    def test_adult_groups_are_not_relabelled_citizen_rates(self):
        rows = [row for row in self.result["records"] if row["native"]["geography"] == "CALIFORNIA"]
        totals = [row for row in rows if row["native"]["native_label"] == ".Total"]
        citizen = next(row for row in rows if row["native"]["role"] == "citizen_overall")
        self.assertTrue(all(row["population_frame"] == "vap" and row["selected_voted_pct"] == 34.2 for row in totals))
        self.assertEqual((citizen["population_frame"], citizen["selected_voted_pct"]), ("cvap", 42.5))
        self.assertEqual(self.result["summary"]["selected_distinct_geography_frame_group_cells"], 642)

    def test_conflicting_pennsylvania_totals_stay_held_even_when_percent_matches(self):
        totals = [row for row in self.result["records"] if row["native"]["geography"] == "PENNSYLVANIA"
            and (row["native"]["native_label"] == ".Total" or row["native"]["role"] == "citizen_overall")]
        self.assertEqual(len(totals), 3)
        self.assertTrue(all(row["decision"] == "withheld_cross_table_total_count_conflict"
            and row["selected_voted_pct"] is None for row in totals))
        self.assertEqual({row["native"]["values"]["voted_thousands"] for row in totals}, {3925, 3928})
        comparisons = [row for row in self.result["snapshot_comparisons"] if row["reference_state_code"] == "PA"]
        self.assertTrue(all(row["endpoint"] and row["reported_voted_difference_pp"] is None for row in comparisons))

    def test_suppressed_rates_and_exact_race_labels_are_not_reconstructed_or_merged(self):
        held = [row for row in self.result["records"]
            if row["decision"] == "withheld_native_missing_or_suppressed_rate"]
        self.assertEqual(len(held), 131)
        self.assertTrue(all(row["selected_voted_pct"] is None for row in held))
        labels = {row["native"]["native_label"] for row in self.result["records"]}
        self.assertTrue({".White", ".Non-Hispanic White", ".Black",
            ".Non-Hispanic Black", ".Hispanic (of any race)", ".Asian and Pacific Islander"} <= labels)
        defective = [row for row in self.result["records"] if row["native"]["native_flags"]]
        self.assertEqual(len(defective), 6)
        self.assertTrue(all(row["selected_voted_pct"] is None for row in defective))

    def test_only_direct_national_interval_is_retained_and_mapping_is_not_generalized(self):
        anchored = [row for row in self.result["records"] if row["published_national_citizen_interval"]]
        self.assertEqual(len(anchored), 1)
        self.assertEqual(anchored[0]["published_national_citizen_interval"]["voted"], [45.8, 46.4])
        self.assertTrue(all(row["standard_error"] is None and row["interpreted_workbook_interval"] is None
            for row in self.result["records"]))

    def test_weighted_population_caution_is_not_unweighted_support(self):
        native, methods, baseline, policy = copy.deepcopy(self.inputs)
        source = next(row for row in native["observations"] if row["display_disposition"].startswith("candidate"))
        base = "citizen_adults_thousands" if source["denominator"] == "citizen" else "adults_thousands"
        source["values"][base] = 75
        result = build(native, methods, baseline, policy)
        row = next(row for row in result["records"] if row["native"] == source)
        self.assertEqual(row["decision"], "withheld_weighted_population_caution")
        self.assertFalse(row["weighted_population_is_sample_size"])
        self.assertIsNone(row["selected_voted_pct"])

    def test_missing_endpoint_stays_missing_and_election_type_change_is_refused(self):
        native, methods, baseline, policy = self.inputs
        subset = [row for row in baseline if not (
            row["year"] == "2022" and row["reference_state_code"] == "CA" and row["population_frame"] == "cvap")]
        result = build(native, methods, subset, policy)
        row = next(row for row in result["snapshot_comparisons"]
            if row["reference_state_code"] == "CA" and row["to_year"] == 2022)
        self.assertIsNone(row["reported_voted_difference_pp"])
        changed = dict(policy, same_type_comparison_years=[2018, 2024])
        with self.assertRaisesRegex(ValueError, "point-only"):
            build(native, methods, baseline, changed)

    def test_citizen_denominator_and_new_interval_policy_cannot_be_substituted(self):
        native, methods, baseline, policy = copy.deepcopy(self.inputs)
        native["observations"][0]["denominator"] = "citizen"
        with self.assertRaisesRegex(ValueError, "denominator"):
            build(native, methods, baseline, policy)
        with self.assertRaisesRegex(ValueError, "point-only"):
            build(*self.inputs[:3], dict(policy, new_intervals_allowed=True))

    def test_independent_verifier_rejects_repaired_count_and_invented_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, body in result_files(self.result).items():
                (output / name).write_bytes(body)
            self.assertEqual(verify(INPUTS, output)["selected_reported_point_rows"], 693)
            modified = copy.deepcopy(self.result)
            row = next(row for row in modified["records"]
                if row["native"]["geography"] == "PENNSYLVANIA" and row["native"]["native_label"] == ".Total")
            row["native"]["values"]["voted_thousands"] = 3926
            (output / "complete-result.json").write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, "repaired"):
                verify(INPUTS, output)
            modified = copy.deepcopy(self.result)
            modified["records"][0]["interpreted_workbook_interval"] = [0, 100]
            (output / "complete-result.json").write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, "without support"):
                verify(INPUTS, output)

    def test_rewritten_manifest_cannot_rebind_originals_to_an_old_reduction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "inputs"
            shutil.copytree(INPUTS, root)
            original = root / "originals/2002-table4a.xls"
            body = original.read_bytes() + b"changed"
            original.write_bytes(body)
            manifest = json.loads((root / "manifest.json").read_bytes())
            manifest["files"]["originals/2002-table4a.xls"] = dict(
                bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Original differs"):
                load_inputs(root)

    def test_complete_query_bytes_survive_a_canonical_json_roundtrip(self):
        decoded = json.loads(json.dumps(self.result, sort_keys=True))
        self.assertEqual(result_files(self.result), result_files(decoded))


if __name__ == "__main__":
    unittest.main()
