import copy
import io
from pathlib import Path
import unittest
import zipfile

from scripts.extract_cps_earlier_history import registry
from scripts.cps_earlier_registered_history import build_earlier, read_csv, late_projection, comparisons


def pairs(voted=1, registered=-1, n=2, units=200):
    return [dict(year="2018", state_fips="01", dimension=d, group=g,
        voted=voted, registered=registered, sample_n=n, weight_units=units)
        for d, g in (("overall", "All"), ("age_group", "18 to 24 Years"), ("sex", "Female"),
                     ("education", "High school / GED"), ("race_ethnicity", "White, non-Hispanic"))]


def example():
    return pairs() + pairs(2, 1, 1, 100) + pairs(-2, 1, 1, 100) + pairs(-9, -9, 3, 300)


def overall(source):
    return next(row for row in build_earlier(source)[0]
                if row["year"] == 2018 and row["state_code"] == "AL" and row["dimension"] == "overall")


class CpsEarlierRegisteredHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/cps-earlier-registered-history/20261109-01/sufficient-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-earlier-cps-sufficient-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.early = build_earlier(read_csv(archive.read("complete-earlier-coarse-response-pairs.csv")))[0]
            with zipfile.ZipFile(io.BytesIO(archive.read("complete-accepted-2022-2024-analysis.zip"))) as old:
                cls.registered = read_csv(old.read("complete-state-registered-group-query.csv"))
                with zipfile.ZipFile(io.BytesIO(old.read("inputs/complete-cps-registration-sufficient-inputs.zip"))) as inputs:
                    cls.citizens = read_csv(inputs.read("previous-citizen-group-query.csv"))
        cls.all = cls.early + late_projection(cls.registered, cls.citizens)

    def test_routed_yes_voter_is_registration_supported(self):
        self.assertEqual(registry(1, -1), "registration_supported")
        self.assertEqual(overall(example())["routed_reported_voter_n"], 2)

    def test_native_minus9_is_unknown_not_invented_noninterview(self):
        self.assertEqual(registry(-9, -9), "registration_unknown")
        dispositions = build_earlier(example())[3]
        row = next(r for r in dispositions if r["voted"] == -9)
        self.assertEqual(row["native_voting_response"], "no_response_noninterview_not_separately_identified")
        self.assertFalse(row["PRSUPINT_present"])
        self.assertFalse(row["noninterview_flag_invented"])

    def test_registered_voting_unknowns_remain_in_full_denominator(self):
        row = overall(example())
        self.assertEqual(row["registered_frame_voting_pct"], "50")
        self.assertEqual(row["unknown_voting_weight_units"], 100)

    def test_unknown_registration_not_assigned_registered(self):
        row = overall(example() + pairs(2, -2, 4, 400))
        self.assertEqual(row["registration_supported_n"], 4)
        self.assertEqual(row["excluded_unknown_registration_n"], 7)
        self.assertEqual(row["registered_frame_voting_pct"], "50")

    def test_explicit_nonregistration_separate_from_unknown(self):
        self.assertEqual(registry(2, 2), "reported_not_registered")
        self.assertEqual(registry(2, -3), "registration_unknown")

    def test_incompatible_native_routing_rejected(self):
        for codes in ((1, 2), (-1, 1), (2, -1), (9, 1)):
            with self.subTest(codes=codes), self.assertRaises(ValueError):
                registry(*codes)

    def test_no_registered_frame_is_undefined_not_zero_percent(self):
        row = overall(pairs(-9, -9))
        self.assertEqual(row["registration_supported_weight_units"], 0)
        self.assertIsNone(row["registered_frame_voting_pct"])
        self.assertIsNone(row["administrative_registry_population_count"])

    def test_duplicate_pair_or_nonpositive_weight_rejected(self):
        for source in (example() + pairs(), pairs(units=0)):
            with self.subTest(), self.assertRaises(ValueError):
                build_earlier(source)

    def test_exclusive_group_partition_error_rejected(self):
        source = example()
        source[1]["weight_units"] += 1
        with self.assertRaisesRegex(ValueError, "partition"):
            build_earlier(source)

    def test_2018_native_question_placeholder_not_replaced_by_calendar_date(self):
        row = overall(example())
        self.assertTrue(row["native2018_question_literal_date_placeholder"])
        self.assertIn("no_PR_SUPINT", row["native_response_scheme"])
        self.assertFalse(row["unknown_response_subclasses_harmonized"])

    def test_accepted_later_rates_remain_exact_in_projection(self):
        projected = late_projection(self.registered, self.citizens)
        for old, new in zip(self.registered, projected):
            self.assertEqual(old["reported_voting_within_source_registration_pct"], new["registered_frame_voting_pct"] or "")

    def test_same_type_pairs_only_not_2018to2020_or_2022to2024(self):
        result = comparisons(self.all)
        self.assertEqual(len(result), 1734)
        self.assertEqual({(r["from_year"], r["to_year"]) for r in result}, {(2018, 2022), (2020, 2024)})

    def test_missing_registered_endpoint_does_not_destroy_citizen_comparison(self):
        data = copy.deepcopy(self.all)
        row = next(r for r in data if r["year"] == 2018 and r["state_code"] == "AL" and r["dimension"] == "overall")
        row["registered_frame_voting_pct"] = None
        result = next(r for r in comparisons(data) if r["from_year"] == 2018 and r["state_code"] == "AL" and r["dimension"] == "overall")
        self.assertIsNone(result["registered_source_percentage_point_difference"])
        self.assertIsNotNone(result["citizen_source_percentage_point_difference"])

    def test_source_arithmetic_not_individual_or_causal_turnout_change(self):
        row = comparisons(self.all)[0]
        self.assertFalse(row["matched_person_panel"])
        self.assertFalse(row["definitions_and_weight_targets_harmonized"])
        self.assertFalse(row["causal_or_administratively_observed_turnout_change"])
        self.assertIsNone(row["retention_or_new_voter_population"])

    def test_no_2026_projection_or_design_interval_fabricated(self):
        row = overall(example())
        self.assertFalse(row["projected_2026_turnout"])
        self.assertFalse(row["local_allocation"])
        self.assertIsNone(row["design_confidence_interval"])


if __name__ == "__main__":
    unittest.main()
