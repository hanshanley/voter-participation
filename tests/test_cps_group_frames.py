import unittest

from scripts.cps_group_frames import (
    build, historical_rows, native_count_rows, number, response_scenarios, time_comparisons,
)


def modern(margin=False):
    rows = [
        ["Table 1a. Margins of Error" if margin else "Table 1. Estimates"],
        ["Sex and age", None, "United States citizen"],
        [None, None, "Total citizen population", "Reported registered", None,
         "Reported not registered", None, "No response to registration1", None,
         "Reported voted", None, "Reported not voted", None, "No response to voting2"],
        ["BOTH SEXES", "Total 18 years and over", 100, 70, 70, 20, 20, 10, 10, 60, 60, 30, 30, 10],
    ]
    return dict(kind="election", year=2024, table=1, path="native.xlsx", url="native",
                sha256="bound", retrieved_at="held", sheets=[dict(name="Table 1", rows=rows)])


def historical(years=(2000, 2004), race=False):
    rows = []
    for measure, value in (("Voted", 60), ("Registered", 70)):
        rows.append(["Total, Percent " + measure])
        for year in years:
            row = [None] * 16
            row[0], row[2], row[4] = year, value, value
            row[3] = "N"
            rows.append(row)
    return dict(kind="history_age", path="native.xlsx", url="native", sha256="bound",
                sheets=[dict(name="history", rows=rows)])


class CpsGroupFrameTests(unittest.TestCase):
    def test_margin_sheet_is_never_a_population_estimate(self):
        observations, decisions = native_count_rows(modern(margin=True))
        self.assertEqual(observations, [])
        self.assertTrue(all(row["disposition"] == "held_margin_of_error_not_population" for row in decisions))

    def test_unknown_response_assignments_keep_full_citizen_denominator(self):
        observations, decisions = native_count_rows(modern())
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["native_unknown_voted_thousands"], "10")
        self.assertEqual(observations[0]["native_voting_accounting_residual_thousands"], "0")
        rows = response_scenarios(observations)
        self.assertEqual([row["response_assignment_pct"] for row in rows],
                         ["60.000000000000000000", "70.000000000000000000"])
        self.assertTrue(all(not row["administrative_turnout_bound"] for row in rows))
        self.assertTrue(all(not row["confidence_interval"] for row in rows))

    def test_legacy_unknown_is_not_reclassified_as_known_nonvoter(self):
        header = [None] * 13
        header[10] = "U.S. citizen"
        row = ["Total 18 years and over", 100, 70, 70, 30, 30, 60, 60, 40, 40, 70, 20, 10]
        workbook = dict(modern(), sheets=[dict(name="legacy", rows=[
            ["Table 1"], header, ["BOTH SEXES"], row])])
        observations, _ = native_count_rows(workbook)
        self.assertEqual(observations[0]["native_citizen_thousands"], "90")
        self.assertIsNone(observations[0]["native_unknown_voted_thousands"])
        self.assertEqual(observations[0]["reported_voting_pct"], "60.000000000000000000")
        self.assertEqual(response_scenarios(observations), [])

    def test_native_unavailability_and_zero_are_distinct(self):
        rows = historical_rows(historical())
        citizen = [row for row in rows if row["population_frame"] == "citizen_population"
                   and row["dimension"] == "overall"]
        self.assertTrue(all(row["native_reported_voted_pct"] is None for row in citizen))
        self.assertTrue(all(row["raw_native_voted_value"] == "N" for row in citizen))
        self.assertEqual(number("0"), 0)
        self.assertIsNone(number("N"))

    def test_inline_margin_section_is_held_without_losing_estimate_rows(self):
        workbook = modern()
        workbook["table"] = 5
        workbook["sheets"][0]["rows"] += [["Margins of Error"], workbook["sheets"][0]["rows"][-1]]
        observations, decisions = native_count_rows(workbook)
        self.assertEqual(len(observations), 1)
        self.assertEqual(decisions[-1]["disposition"], "held_margin_of_error_not_population")

    def test_citizen_header_does_not_imply_separate_nonresponse_categories(self):
        workbook = modern()
        header, data = workbook["sheets"][0]["rows"][2:]
        header[5], header[11], header[7], header[13] = "Not Registered", "Did Not Vote", None, None
        data[5], data[11] = 30, 40
        observations, _ = native_count_rows(workbook)
        self.assertEqual(observations[0]["native_not_voted_thousands"], "40")
        self.assertEqual(observations[0]["voting_nonresponse_disposition"], "merged_with_native_did_not_vote")
        self.assertEqual(response_scenarios(observations), [])

    def test_reported_did_not_vote_variant_retains_known_no_and_accounting(self):
        workbook = modern()
        workbook["sheets"][0]["rows"][2][11] = "Reported did not vote"
        observations, _ = native_count_rows(workbook)
        self.assertEqual(observations[0]["native_not_voted_thousands"], "30")
        self.assertEqual(observations[0]["native_voting_accounting_residual_thousands"], "0")

    def test_same_election_type_comparison_holds_race_definition_break(self):
        rows = historical_rows(historical())
        comparisons = time_comparisons(rows)
        overall = next(row for row in comparisons if row["dimension"] == "overall"
                       and row["population_frame"] == "total_population")
        race = next(row for row in comparisons if row["dimension"] == "race"
                    and row["native_group"] == "White" and row["population_frame"] == "total_population")
        self.assertEqual(overall["reported_voted_percentage_point_difference"], "0")
        self.assertIsNone(race["reported_voted_percentage_point_difference"])
        self.assertFalse(overall["cohort_retention_inferred"])

    def test_no_population_scaling_or_gender_reclassification_from_mismatched_frame(self):
        ap = dict(selected_rows=[dict(year="2024", scope="US50_SOURCE", dimension="GENDER",
                  group="3", native_labels="Nonbinary", weight_field="FINALVOTE_NATIONAL_WEIGHT",
                  weight="100", modeled_voter_weight="60", modeled_nonvoter_weight="30",
                  model_unknown_weight="10")])
        files, summary = build([modern(), historical()], ap)
        self.assertEqual(summary["population_scaled_survey_estimates"], 0)
        self.assertEqual(summary["complete_public_survey_frame_dispositions"], 1)
        self.assertIn(b"held_US50_source", files["complete-survey-frame-dispositions.csv"])


if __name__ == "__main__":
    unittest.main()
