import csv
from fractions import Fraction
import io
import unittest

from scripts.extract_civic_history_classifications import prior_block, current_block, PRIOR, CURRENT
from scripts.civic_history_classifications import STATES, YEARS, select, build


def sources():
    parents = {s: dict(scope=s, n=200, weight="200", modeled_voter_weight="100", modeled_nonvoter_weight="100")
               for s in STATES if s != "DC"}
    tables = {(y, s): {(p, c): [50, Fraction(50)] for p in PRIOR for c in CURRENT}
              for y in YEARS for s in parents}
    return tables, parents


def snapshot(tables, parents):
    return dict(year=2026, dc_sample=False, minimum_parent_n=100, minimum_positive_coarse_cell_n=30,
        other_prior_block_is_not_inferred_nonvoting=True, frames=select(tables, parents),
        public_current_parents=list(parents.values()))


def rows(body):
    return list(csv.DictReader(io.StringIO(body.decode())))


class CivicHistoryClassificationsTest(unittest.TestCase):
    def test_other_candidate_is_retained_with_reported_choice(self):
        self.assertEqual(prior_block("O"), "recalled_candidate_choice")

    def test_unknown_not_recoded_as_prior_nonvoting(self):
        self.assertEqual(prior_block("U"), "other_unresolved_prior_response")
        self.assertEqual(prior_block("N"), "other_unresolved_prior_response")
        self.assertNotIn("nonvoter", prior_block("U"))

    def test_unknown_current_choice_still_native_model_participant(self):
        self.assertEqual(current_block("U"), "modeled_participant")
        self.assertEqual(current_block("N"), "modeled_nonparticipant")

    def test_unsupported_native_codes_rejected(self):
        for function in (prior_block, current_block):
            with self.assertRaises(ValueError):
                function("invented")

    def test_sparse_cell_holds_entire_table_and_positive_state_complement(self):
        tables, parents = sources()
        tables[2022, "AL"][PRIOR[0], CURRENT[0]] = [29, Fraction(29)]
        tables[2022, "AL"][PRIOR[1], CURRENT[0]] = [71, Fraction(71)]
        frames = select(tables, parents)
        held = [f for f in frames if f["prior_year"] == 2022 and f["cells"] is None and f["state_code"] != "DC"]
        self.assertEqual(len(held), 2)
        self.assertTrue(all(f["source_n"] is None for f in held))

    def test_zero_source_block_has_undefined_conditional_rate_not_zero_percent(self):
        tables, parents = sources()
        for p in PRIOR:
            for c in CURRENT:
                tables[2022, "AL"][p, c] = [100, Fraction(100)] if p == PRIOR[0] else [0, Fraction(0)]
        files = build(snapshot(tables, parents))
        rates = rows(files["complete-conditional-source-model-rates.csv"])
        row = next(r for r in rates if r["prior_year"] == "2022" and r["state_code"] == "AL" and r["prior_block"] == PRIOR[1])
        self.assertEqual(row["source_block_n"], "0")
        self.assertEqual(row["conditional_modeled_participant_pct"], "")

    def test_held_statistics_not_allowed_in_sufficient_public_snapshot(self):
        tables, parents = sources()
        data = snapshot(tables, parents)
        dc = next(f for f in data["frames"] if f["state_code"] == "DC")
        dc["source_n"] = 1
        with self.assertRaisesRegex(ValueError, "Held private statistics"):
            build(data)

    def test_source_weight_partition_not_repaired(self):
        tables, parents = sources()
        tables[2022, "AL"][PRIOR[0], CURRENT[0]][1] += 1
        with self.assertRaisesRegex(ValueError, "accepted full current source"):
            select(tables, parents)

    def test_current_model_parent_not_reestimated(self):
        tables, parents = sources()
        tables[2022, "AL"][PRIOR[0], CURRENT[0]][1] += 1
        tables[2022, "AL"][PRIOR[0], CURRENT[1]][1] -= 1
        with self.assertRaisesRegex(ValueError, "Current model class"):
            select(tables, parents)

    def test_dc_source_cannot_be_fabricated(self):
        tables, parents = sources()
        parents["DC"] = parents["AL"]
        with self.assertRaisesRegex(ValueError, "accepted current source parents"):
            select(tables, parents)

    def test_complete_queries_keep_dc_absence_and_current_state_scope(self):
        tables, parents = sources()
        files = build(snapshot(tables, parents))
        decisions = rows(files["complete-classification-decisions.csv"])
        self.assertEqual(len(decisions), 102)
        self.assertEqual(len(rows(files["complete-nonpartisan-classification-cells.csv"])), 408)
        self.assertEqual(len(rows(files["complete-conditional-source-model-rates.csv"])), 204)
        self.assertTrue(all(r["state_scope"] == "current_2026_source_state_not_verified_prior_residence" for r in decisions))
        self.assertTrue(all(r["source_n"] == "" for r in decisions if r["state_code"] == "DC"))

    def test_sparse_positive_public_cell_rejected_even_when_marked_selected(self):
        tables, parents = sources()
        data = snapshot(tables, parents)
        frame = next(f for f in data["frames"] if f["state_code"] == "AL")
        frame["cells"][0]["n"] = 29
        with self.assertRaisesRegex(ValueError, "Sparse positive cell"):
            build(data)

    def test_no_individual_unknown_or_explicit_nonvote_population_inferred(self):
        tables, parents = sources()
        rates = rows(build(snapshot(tables, parents))["complete-conditional-source-model-rates.csv"])
        self.assertTrue(all(r["explicit_prior_nonvote_weight"] == r["unknown_prior_response_weight"] == "" for r in rates))
        self.assertTrue(all(r["new_or_returning_voter_population"] == r["observed_staying_home"] == "" for r in rates))

    def test_prior_offices_not_silently_harmonized(self):
        tables, parents = sources()
        data = snapshot(tables, parents)
        data["frames"][0]["prior_office"] = "president"
        with self.assertRaisesRegex(ValueError, "different retrospective offices"):
            build(data)

    def test_missing_native_state_contest_table_rejected(self):
        tables, parents = sources()
        del tables[2022, "AL"]
        with self.assertRaisesRegex(ValueError, "Incomplete native"):
            select(tables, parents)


if __name__ == "__main__":
    unittest.main()
