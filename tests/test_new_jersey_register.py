import copy
import json
from pathlib import Path
import re
import unittest
import zipfile

from scripts.new_jersey_register import registration_frame


ATLANTIC = r"A[ \t]*t[ \t]*l[ \t]*a[ \t]*n[ \t]*t[ \t]*i[ \t]*c"


class NewJerseyRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/new-jersey-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/new-jersey-complete-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.first, cls.second = (json.loads(archive.read(name)) for name in ("pymupdf-pages.json", "pypdf-pages.json"))

    def frame(self, first=None, second=None):
        return registration_frame(self.first if first is None else first, self.second if second is None else second)

    def transformed(self, transform):
        return ([transform(page) for page in self.first], [transform(page) for page in self.second])

    def test_selects_native_grand_total_not_party_population(self):
        parent, rows, discrepancies = self.frame()
        self.assertEqual((parent["total"], parent["DEM"], parent["REP"]), (6747375, 2578959, 1686761))
        self.assertEqual((len(rows), discrepancies), (22, []))

    def test_missing_native_parent_cannot_use_county_or_party_sum(self):
        first, second = self.transformed(lambda page: re.sub(r"(?m)^\s*total\s+[0-9][^\n]*", "", page))
        with self.assertRaisesRegex(ValueError, "native total parent"):
            self.frame(first, second)

    def test_duplicate_native_parent_is_not_added(self):
        first, second = copy.deepcopy(self.first), copy.deepcopy(self.second)
        for pages in (first, second):
            line = next(line for line in pages[0].splitlines() if re.match(r"^\s*total\s+[0-9]", line))
            pages[0] += "\n" + line + "\n"
        with self.assertRaisesRegex(ValueError, "duplicate native total parent"):
            self.frame(first, second)

    def test_missing_county_is_not_treated_as_zero(self):
        first, second = self.transformed(lambda page: re.sub(r"(?m)^[ \t]*" + ATLANTIC + r"[^\n]*", "", page))
        with self.assertRaisesRegex(ValueError, "21-county coverage"):
            self.frame(first, second)

    def test_changed_date_requires_new_review(self):
        first, second = self.transformed(lambda page: page.replace("11/3/26", "11/2/26"))
        with self.assertRaisesRegex(ValueError, "native date"):
            self.frame(first, second)

    def test_independent_extraction_disagreement_is_not_repaired(self):
        first = copy.deepcopy(self.first)
        first[0] = first[0].replace("72261", "72260", 1)
        with self.assertRaisesRegex(ValueError, "extractions disagree"):
            self.frame(first, self.second)

    def test_truncated_count_row_cannot_substitute_party_counts(self):
        first, second = self.transformed(lambda page: re.sub(r"(?m)^([ \t]*" + ATLANTIC + r"[ \t]*)[0-9]+[ \t]+", r"\1", page))
        with self.assertRaisesRegex(ValueError, "11-column"):
            self.frame(first, second)

    def test_column_reordering_is_not_silently_reinterpreted(self):
        first, second = self.transformed(lambda page: page.replace("COUNTY", "UNREVIEWED"))
        with self.assertRaisesRegex(ValueError, "column order"):
            self.frame(first, second)

    def test_source_discrepancies_are_reported_not_used_to_repair_parent(self):
        first, second = self.transformed(lambda page: page.replace("72261", "72260", 1))
        parent, rows, discrepancies = self.frame(first, second)
        self.assertEqual(parent["total"], 6747375)
        self.assertEqual(next(row for row in rows if row["county_literal"] == "Atlantic")["UNA"], 72260)
        self.assertEqual(len(discrepancies), 2)

    def test_changed_label_characters_are_not_fuzzy_matched(self):
        first, second = self.transformed(lambda page: re.sub(ATLANTIC, "Atlantiq", page))
        with self.assertRaisesRegex(ValueError, "21-county coverage"):
            self.frame(first, second)


if __name__ == "__main__":
    unittest.main()
