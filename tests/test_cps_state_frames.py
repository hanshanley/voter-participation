import unittest

from scripts.cps_state_frames import STATE_NAMES, build, native_cells, numeric


def inputs(early=False):
    workbooks, votes = [], []
    for election, years in (("presidential", (1976, 1972) if early else (2024, 2020)),
                            ("midterm", (1974,) if early else (2022, 2018))):
        for measure in ("voted", "registered"):
            columns = [(year, "Total") for year in years] if early else [
                (year, population) for year in years for population in ("Total", "Citizen")]
            header = ["State"] + [year if index == 0 or year != columns[index - 1][0] else None
                                   for index, (year, population) in enumerate(columns)]
            population = [None] + [pop for year, pop in columns]
            basename = election + "-" + measure + ".xlsx"
            title = ("Reported Voting" if measure == "voted" else "Reported Registration") + " for " + (
                "Presidential Elections" if election == "presidential" else "Congressional Elections")
            rows = [["Native header"], [title], ["Percent"], header, population]
            for ordinal, name in enumerate(STATE_NAMES.values(), start=6):
                rows.append([name] + [60 if measure == "voted" else 70 for column in columns])
                if measure == "voted":
                    votes.extend(dict(state=name, year=year, denominator="vap" if pop == "Total" else "cvap",
                                      turnout_pct=60, source=basename, source_row=ordinal) for year, pop in columns)
            workbooks.append(dict(election_type=election, measure=measure, path=basename,
                                  url="native", sha256="bound", retrieved_at="held",
                                  sheets=[dict(name="native", rows=rows)]))
    return workbooks, votes


def survey(**changes):
    return dict(dict(year="2024", scope="AK", dimension="overall", group="all",
                     weight_field="FINALVOTE_STATE_WEIGHT", positive_weight_n="600",
                     weight="100", modeled_voter_weight="60", modeled_nonvoter_weight="30",
                     model_unknown_weight="10", inference_status="native frame"), **changes)


class CpsStateFrameTests(unittest.TestCase):
    def test_complete_population_grid_preserves_absent_early_citizen_columns(self):
        workbooks, votes = inputs(early=True)
        files, summary = build(workbooks, votes, dict(selected_rows=[]))
        self.assertEqual(summary["complete_state_year_population_pairs"], 3 * 51 * 2)
        self.assertEqual(summary["missing_native_population_columns"], 3 * 51)
        self.assertIn(b"held_native_population_column_absent", files["complete-state-year-population-pairs.csv"])

    def test_unavailable_N_and_zero_are_distinct(self):
        self.assertIsNone(numeric("N"))
        self.assertEqual(numeric("0"), 0)
        workbooks, votes = inputs()
        workbooks[0]["sheets"][0]["rows"][5][1] = 0
        votes[0]["turnout_pct"] = 0
        files, summary = build(workbooks, votes, dict(selected_rows=[]))
        self.assertEqual(summary["known_voting_source_rows"], len(votes))
        self.assertIn(b"0.000000000000000000", files["complete-state-year-population-pairs.csv"])

    def test_preserved_voter_query_mismatch_is_not_repaired(self):
        workbooks, votes = inputs()
        votes[0]["turnout_pct"] = 61
        with self.assertRaisesRegex(ValueError, "preserved voter query"):
            build(workbooks, votes, dict(selected_rows=[]))

    def test_full_survey_mass_and_two_population_diagnostics_not_population_counts(self):
        workbooks, votes = inputs()
        files, summary = build(workbooks, votes, dict(selected_rows=[survey()]))
        self.assertEqual(summary["supported_AP_state_diagnostic_rows"], 2)
        self.assertEqual(summary["modeled_population_counts"], 0)
        self.assertIn(b"10", files["complete-AP-state-frame-diagnostics.csv"])
        self.assertIn(b"False", files["complete-AP-state-frame-diagnostics.csv"])

    def test_unmatched_national_and_demographic_queries_remain_in_decisions(self):
        workbooks, votes = inputs()
        files, summary = build(workbooks, votes, dict(selected_rows=[
            survey(scope="US50_SOURCE"), survey(dimension="AGE65", group="1"), survey(positive_weight_n="40")]))
        self.assertEqual(summary["complete_AP_population_frame_decisions"], 6)
        self.assertEqual(summary["supported_AP_state_diagnostic_rows"], 0)
        self.assertIn(b"source_support_hold", files["complete-AP-frame-dispositions.csv"])

    def test_source_title_prevents_registration_file_becoming_vote_data(self):
        workbooks, votes = inputs()
        workbooks[0]["measure"] = "registered"
        with self.assertRaisesRegex(ValueError, "source title"):
            native_cells(workbooks)

    def test_duplicate_native_source_and_unreconciled_mass_rejected(self):
        workbooks, votes = inputs()
        with self.assertRaisesRegex(ValueError, "Duplicate native source"):
            native_cells(workbooks + [workbooks[0]])
        with self.assertRaisesRegex(ValueError, "survey mass"):
            build(workbooks, votes, dict(selected_rows=[survey(model_unknown_weight="11")]))


if __name__ == "__main__":
    unittest.main()
