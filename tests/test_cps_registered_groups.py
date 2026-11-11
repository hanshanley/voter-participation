import copy
from pathlib import Path
import unittest
import zipfile

from scripts.extract_cps_registered_groups import registration_class
from scripts.cps_registered_groups import build, read_csv


def pairs(interview=1, voted=1, registered=-1, n=2, units=200):
    return [dict(year="2024", state_fips="01", dimension=d, group=g,
        interview=interview, voted=voted, registered=registered, sample_n=n, weight_units=units)
        for d, g in (("overall", "All"), ("age_group", "18 to 24 Years"), ("sex", "Female"),
                     ("education", "High school / GED"), ("race_ethnicity", "White, non-Hispanic"))]


def example():
    return (pairs() + pairs(voted=2, registered=1, n=1, units=100)
            + pairs(voted=-2, registered=1, n=1, units=100)
            + pairs(interview=2, voted=-1, registered=-1, n=3, units=300))


def overall(source):
    files = build(source, [], [])
    return next(row for row in read_csv(files["complete-state-registered-group-query.csv"])
                if row["year"] == "2024" and row["state_code"] == "AL" and row["dimension"] == "overall")


class CpsRegisteredGroupsTest(unittest.TestCase):
    def test_routed_voters_not_misclassified_unregistered(self):
        self.assertEqual(registration_class(1, 1, -1)[0], "registration_supported")
        row = overall(example())
        self.assertEqual(row["routed_reported_voter_n"], "2")
        self.assertEqual(row["registration_supported_n"], "4")
        self.assertEqual(row["explicitly_registered_n"], "2")

    def test_noninterview_registration_is_unknown_not_no(self):
        self.assertEqual(registration_class(2, -1, -1), ("registration_unknown", "supplement_noninterview"))
        row = overall(example())
        self.assertEqual(row["excluded_unknown_registration_n"], "3")
        self.assertEqual(row["registration_supported_weight_units"], "400")

    def test_registered_voting_unknowns_remain_in_full_denominator(self):
        row = overall(example())
        self.assertEqual(row["reported_voting_within_source_registration_pct"], "50")
        self.assertEqual(row["reported_nonvoting_within_source_registration_pct"], "25")
        self.assertEqual(row["unknown_voting_within_source_registration_pct"], "25")
        self.assertNotEqual(row["known_voting_response_only_pct"], "50")

    def test_unknown_registration_not_assigned_to_registered(self):
        row = overall(example() + pairs(voted=2, registered=-2, n=4, units=400))
        self.assertEqual(row["registration_supported_n"], "4")
        self.assertEqual(row["excluded_unknown_registration_n"], "7")
        self.assertEqual(row["reported_voting_within_source_registration_pct"], "50")

    def test_explicit_nonregistration_stays_separate(self):
        self.assertEqual(registration_class(1, 2, 2), ("reported_not_registered", "explicit_registration_no"))
        row = overall(example() + pairs(voted=2, registered=2, n=1, units=100))
        self.assertEqual(row["registration_supported_n"], "4")
        self.assertEqual(row["excluded_unknown_registration_n"], "3")

    def test_unknown_vote_can_have_explicit_yes_registration(self):
        self.assertEqual(registration_class(1, -3, 1), ("registration_supported", "explicit_registration_yes"))

    def test_incompatible_native_routing_rejected(self):
        for codes in ((1, 1, 2), (2, 2, 1), (1, 2, -1), (1, 9, 1)):
            with self.subTest(codes=codes), self.assertRaises(ValueError):
                registration_class(*codes)

    def test_no_registration_supported_cases_is_undefined_not_zero_percent(self):
        row = overall(pairs(interview=2, voted=-1, registered=-1))
        self.assertEqual(row["reported_voting_within_source_registration_pct"], "")
        self.assertEqual(row["disposition"], "no_registration_supported_source_cases")

    def test_absent_demographic_group_not_zero_turnout(self):
        files = build(example(), [], [])
        row = next(row for row in read_csv(files["complete-state-registered-group-query.csv"])
                   if row["year"] == "2024" and row["state_code"] == "AL"
                   and row["dimension"] == "sex" and row["group"] == "Male")
        self.assertEqual(row["registration_supported_n"], "0")
        self.assertEqual(row["reported_voting_within_source_registration_pct"], "")

    def test_duplicate_native_pairs_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate coarse"):
            build(example() + pairs(), [], [])

    def test_nonpositive_native_case_or_weight_not_coerced(self):
        for source in (pairs(n=0), pairs(units=-1)):
            with self.subTest(), self.assertRaisesRegex(ValueError, "positive cases"):
                build(source, [], [])

    def test_exclusive_partition_error_not_silently_repaired(self):
        source = example()
        source[1]["weight_units"] += 1
        with self.assertRaisesRegex(ValueError, "partition"):
            build(source, [], [])

    def test_no_administrative_or_2026_population_projection(self):
        row = overall(example())
        self.assertEqual(row["administrative_registry_population_count"], "")
        self.assertEqual(row["design_confidence_interval"], "")
        self.assertEqual(row["projected_2026_turnout"], "False")
        self.assertEqual(row["local_allocation"], "False")

    def test_native_unknown_registration_types_not_collapsed_as_no(self):
        for code, reason in ((-2, "registration_dont_know"), (-3, "registration_refused"), (-9, "registration_no_response")):
            with self.subTest(code=code):
                self.assertEqual(registration_class(1, 2, code), ("registration_unknown", reason))

    def test_changed_accepted_citizen_baseline_rejected(self):
        root = Path(__file__).parents[1]
        fixture = root / "data/cps-registered-groups/20261109-01/sufficient-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-cps-registration-sufficient-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            baseline = read_csv(archive.read("previous-citizen-group-query.csv"))
            source = read_csv(archive.read("complete-coarse-native-response-pairs.csv"))
        baseline = copy.deepcopy(baseline)
        baseline[0]["sample_n"] = str(int(baseline[0]["sample_n"]) + 1)
        with self.assertRaisesRegex(ValueError, "accepted citizen-frame counts"):
            build(source, baseline, [])


if __name__ == "__main__":
    unittest.main()
