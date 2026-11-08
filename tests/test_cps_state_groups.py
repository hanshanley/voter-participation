import csv
import io
import unittest

from scripts.cps_state_groups import OUTCOMES, build, weight_units


def cell(sex="Female", yes=1, no=1, unknown=2):
    outcomes = {outcome: 0 for outcome in OUTCOMES}
    outcomes.update(yes=yes, no=no, supplement_noninterview=unknown)
    total = sum(outcomes.values())
    return dict(
        year="2024", state_fips="01", age_group="18 to 24 Years", sex=sex,
        education="High school / GED", race_ethnicity="White, non-Hispanic",
        sample_n=str(total), citizens_weighted=str(total * 100),
        reported_voters_weighted=str(yes * 100), reported_nonvoters_weighted=str(no * 100),
        unknown_weighted=str(unknown * 100),
        **{outcome + "_n": str(value) for outcome, value in outcomes.items()},
        **{outcome + "_weighted": str(value * 100) for outcome, value in outcomes.items()},
    )


def rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode())))


class StateCpsGroupTests(unittest.TestCase):
    def test_unknown_noninterviews_stay_in_the_full_group_denominator(self):
        files, _ = build([cell()], [])
        row = next(row for row in rows(files["complete-state-demographic-participation.csv"])
                   if row["year"] == "2024" and row["state_code"] == "AL"
                   and row["dimension"] == "sex" and row["group"] == "Female")
        self.assertEqual(row["reported_voting_pct"], "25")
        self.assertEqual(row["known_response_only_voting_pct"], "50")
        self.assertEqual(row["unknown_pct"], "50")
        self.assertEqual(row["supplement_noninterview_n"], "2")
        self.assertEqual(row["observed_staying_home"], "False")
        self.assertEqual(row["registered_voter_population_count"], "")

    def test_exclusive_groups_reconcile_without_adding_demographic_dimensions(self):
        files, _ = build([cell(), cell("Male", yes=3, no=0, unknown=1)], [])
        checks = rows(files["complete-exclusive-state-partition-checks.csv"])
        self.assertTrue(all(row["exclusive_group_sum"] == row["state_total"] for row in checks))
        all_rows = rows(files["complete-state-demographic-participation.csv"])
        overall = next(row for row in all_rows if row["year"] == "2024"
                       and row["state_code"] == "AL" and row["dimension"] == "overall")
        self.assertEqual(overall["sample_n"], "8")
        self.assertEqual(overall["reported_voting_pct"], "50")

    def test_absent_group_is_not_zero_participation(self):
        files, _ = build([cell()], [])
        row = next(row for row in rows(files["complete-state-demographic-participation.csv"])
                   if row["year"] == "2024" and row["state_code"] == "AL"
                   and row["dimension"] == "sex" and row["group"] == "Male")
        self.assertEqual(row["reported_voting_pct"], "")
        self.assertEqual(row["disposition"], "no_observed_source_cell")

    def test_unknown_assignments_are_not_confidence_intervals_or_population_bounds(self):
        files, _ = build([cell()], [])
        selected = [row for row in rows(files["complete-state-demographic-nonresponse-scenarios.csv"])
                    if row["year"] == "2024" and row["state_code"] == "AL"
                    and row["dimension"] == "overall"]
        self.assertEqual([row["assigned_reported_voting_pct"] for row in selected], ["25", "50", "75"])
        self.assertTrue(all(row["is_confidence_interval_or_actual_turnout_bound"] == "False"
                            for row in selected))

    def test_duplicate_joint_cells_or_incompatible_categories_are_rejected(self):
        for source in ([cell(), cell()], [dict(cell(), education="Guessed education")]):
            with self.subTest():
                with self.assertRaises(ValueError):
                    build(source, [])

    def test_outcome_accounting_and_weight_scale_are_not_repaired(self):
        with self.assertRaises(ValueError):
            build([dict(cell(), unknown_weighted="201")], [])
        with self.assertRaises(ValueError):
            weight_units("1.00001")
        self.assertEqual(weight_units("1.0001"), 10001)


if __name__ == "__main__":
    unittest.main()
