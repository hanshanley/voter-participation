import unittest
from scripts.historical_precinct_coverage import decisions


class CoverageTests(unittest.TestCase):
    def test_partial_town_and_ballot_sources_do_not_become_complete_precinct_turnout(self):
        source=dict(state_code="ME",year=2018,source_id="town",scope="native_town",
            provenance="immutable-source-pin",compiled_query_available=True,parsed_rows_or_cells=7,
            native_ballot_field_rows=2)
        rows=decisions(dict(sources=[source]))
        self.assertEqual(len(rows),255)
        row=next(r for r in rows if r["state_code"]=="ME" and r["year"]==2018)
        self.assertEqual(row["native_ballot_field_rows"],2)
        self.assertFalse(row["complete_precinct_coverage_qualified"])
        self.assertFalse(row["group_turnout_qualified"])
        absent=next(r for r in rows if r["state_code"]=="MD" and r["year"]==2018)
        self.assertIn("not_global_source_absence",absent["disposition"])

    def test_alternative_sources_remain_distinct_and_duplicate_evidence_is_refused(self):
        source=dict(state_code="AL",year=2020,source_id="first",scope="returns",
            provenance="source",compiled_query_available=True,parsed_rows_or_cells=4)
        second=dict(source,source_id="alternative")
        row=next(r for r in decisions(dict(sources=[source,second]))
            if r["state_code"]=="AL" and r["year"]==2020)
        self.assertEqual(row["source_ids"],"alternative;first")
        self.assertEqual(row["parsed_native_rows_or_cells"],8)
        self.assertTrue(row["ballot_rows_are_not_participant_totals"])
        with self.assertRaises(ValueError):
            decisions(dict(sources=[source,source]))


if __name__=="__main__":
    unittest.main()
