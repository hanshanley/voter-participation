import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.nebraska_registry_count import registry_frame


class NebraskaRegistryCountTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/nebraska-registry/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-nebraska-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.views = json.loads(archive.read("coordinate-views.json"))

    def frame(self, views=None):
        views = self.views if views is None else views
        return registry_frame(views["pymupdf"], views["pdfplumber"])

    def changed_word(self, page, before, after, body_only=True):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            words = [word for word in pages[page]["words"]
                     if word[4] == before and (not body_only or word[1] > 200)]
            self.assertEqual(len(words), 1)
            words[0][4] = after
        return views

    def test_selects_explicit_state_parent_even_if_component_diagnostic_fails(self):
        views = self.changed_word(0, "19281", "19282")
        total, _, _, diagnostics = self.frame(views)
        self.assertEqual(total, 1265022)
        equation = next(row for row in diagnostics if row["scope"] == "Adams")
        self.assertEqual(equation["difference"], -1)

    def test_blank_middle_columns_do_not_shift_nonpartisan_and_total_left(self):
        _, rows, _, diagnostics = self.frame()
        row = next(row for row in rows if row["jurisdiction_literal"] == "Antelope")
        self.assertEqual(row["counts"], [3334, 449, 30, 17, None, None, 511, 4341])
        equation = next(row for row in diagnostics if row["scope"] == "Antelope")
        self.assertEqual(equation["difference"], 0)
        self.assertFalse(equation["complete_equation_qualified"])

    def test_missing_native_parent_cannot_use_county_or_party_fallback(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            pages[-1]["words"] = [word for word in pages[-1]["words"] if word[4] != "1265022"]
        with self.assertRaisesRegex(ValueError, "explicit positive native statewide"):
            self.frame(views)

    def test_missing_parent_label_is_not_relabelled(self):
        views = self.changed_word(6, "Grand", "Unknown")
        with self.assertRaisesRegex(ValueError, "Missing or duplicate native Grand Total"):
            self.frame(views)

    def test_missing_county_row_cannot_be_zero_filled(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            pages[0]["words"] = [word for word in pages[0]["words"] if word[4] != "Antelope"]
        with self.assertRaisesRegex(ValueError, "Missing native geography"):
            self.frame(views)

    def test_duplicate_county_is_not_a_complete_inventory(self):
        views = self.changed_word(0, "Antelope", "Adams")
        with self.assertRaisesRegex(ValueError, "duplicate native 93-county"):
            self.frame(views)

    def test_independent_numeric_disagreement_is_not_repaired(self):
        views = copy.deepcopy(self.views)
        next(word for word in views["pdfplumber"][0]["words"] if word[4] == "19281")[4] = "19282"
        with self.assertRaisesRegex(ValueError, "coordinate readers disagree"):
            self.frame(views)

    def test_observed_zero_remains_distinct_from_adjacent_blank(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            y = next(word[1] for word in pages[0]["words"] if word[4] == "Antelope")
            pages[0]["words"].append([445, y, 449.4, y + 8, "0"])
        _, rows, _, _ = self.frame(views)
        row = next(row for row in rows if row["jurisdiction_literal"] == "Antelope")
        self.assertEqual(row["counts"][4], 0)
        self.assertIsNone(row["counts"][5])

    def test_native_registry_filter_cannot_be_replaced_with_estimated_vep(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            pages[0]["text"] = pages[0]["text"].replace(
                "Count of Voters Eligible to Vote", "Estimated Voting Eligible Population"
            )
        with self.assertRaisesRegex(ValueError, "registry-filtered report identity"):
            self.frame(views)

    def test_processed_clock_cannot_be_silently_changed(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            pages[0]["text"] = pages[0]["text"].replace("11/01/2026 2:00 AM", "11/03/2026 2:00 AM")
        with self.assertRaisesRegex(ValueError, "processed/printed clocks"):
            self.frame(views)

    def test_registration_affiliation_header_cannot_be_changed_to_votes(self):
        views = self.changed_word(0, "Republican", "Votes", body_only=False)
        with self.assertRaisesRegex(ValueError, "registration-affiliation column"):
            self.frame(views)

    def test_continuation_grid_cannot_be_treated_as_first_page(self):
        views = copy.deepcopy(self.views)
        for pages in views.values():
            for word in pages[1]["words"]:
                if 200 < word[1] < 565:
                    word[1] += 3
                    word[3] += 3
        with self.assertRaisesRegex(ValueError, "native body row position"):
            self.frame(views)


if __name__ == "__main__":
    unittest.main()
