import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.oregon_monthly_register import held_context, registration_frame


class OregonMonthlyRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/oregon-monthly-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-oregon-monthly-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.views = json.loads(archive.read("registration-source-views.json"))
            cls.held = json.loads(archive.read("held-return-source-views.json"))
            cls.facts = json.loads(archive.read("held-source-context.json"))

    def frame(self, views=None):
        views = self.views if views is None else views
        return registration_frame(views["pymupdf"], views["pdfplumber"])

    def changed_lines(self, page, predicate, transform):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            lines = pages[page].splitlines()
            pages[page] = "\n".join(transform(line) if predicate(" ".join(line.split())) else line
                                    for line in lines)
        return views

    def test_selects_parent_once_not_sum_of_repeated_geographic_views(self):
        total, cells, _ = self.frame()
        self.assertEqual(total, 3112307)
        self.assertEqual(sum(row["geography_literal"] == "Grand Total" for row in cells), 11)
        self.assertEqual(len(cells), 2220)

    def test_missing_county_total_cannot_use_congressional_or_county_sum_fallback(self):
        views = self.changed_lines(1, lambda line: line.startswith("Total "), lambda line: "")
        with self.assertRaisesRegex(ValueError, "explicit Total"):
            self.frame(views)

    def test_missing_fragment_cell_is_not_zero_filled_or_shifted(self):
        views = self.changed_lines(3, lambda line: line.startswith("Jefferson 3 "),
                                   lambda line: " ".join(line.split()).replace(" 0 ", " ", 1))
        with self.assertRaisesRegex(ValueError, "fragment inventory"):
            self.frame(views)

    def test_literal_zero_in_congressional_fragment_remains_observed(self):
        _, cells, _ = self.frame()
        row = next(row for row in cells if row["view"] == "congressional"
                   and row["district_literal"] == "5th" and row["geography_literal"] == "Jefferson"
                   and row["native_column_label"] == "Working Families")
        self.assertEqual((row["native_value"], row["native_kind"]), (0, "observed_count"))
        self.assertFalse(row["missing_imputed_zero"])

    def test_independent_numeric_disagreement_is_not_repaired(self):
        views = copy.deepcopy(self.views)
        views["pdfplumber"][1] = views["pdfplumber"][1].replace("3,112,307", "3,112,308")
        with self.assertRaisesRegex(ValueError, "registration readers disagree"):
            self.frame(views)

    def test_prepared_date_cannot_be_silently_changed(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            pages[0] = pages[0].replace("11/3/2026", "11/7/2026")
        with self.assertRaisesRegex(ValueError, "preparation date"):
            self.frame(views)

    def test_affiliation_header_cannot_be_replaced_with_vote_choice(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            pages[1] = pages[1].replace("Republican", "Votes")
        with self.assertRaisesRegex(ValueError, "affiliation headers"):
            self.frame(views)

    def test_duplicate_county_is_not_a_complete_native_inventory(self):
        views = self.changed_lines(1, lambda line: line.startswith("Benton "),
                                   lambda line: line.replace("Benton", "Baker"))
        with self.assertRaisesRegex(ValueError, "Duplicate native geography"):
            self.frame(views)

    def test_held_formal_analysis_warning_cannot_be_removed(self):
        views = copy.deepcopy(self.held)
        for pages in views.values():
            pages[0] = pages[0].replace("formal analysis", "certified totals")
        with self.assertRaisesRegex(ValueError, "formal-analysis warning"):
            held_context(views, self.facts)

    def test_held_active_snapshot_clock_cannot_be_treated_as_report_clock(self):
        facts = copy.deepcopy(self.facts)
        facts["active_voters_snapshot_at"] = "2026-11-06 15:36"
        with self.assertRaisesRegex(ValueError, "held source facts"):
            held_context(self.held, facts)


if __name__ == "__main__":
    unittest.main()
