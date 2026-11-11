import copy
from pathlib import Path
import unittest

from scripts.california_registration import BOOKS, tables, workbook


class CaliforniaRegistrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixtures = root / "data/california-registration/20261108-01"
        if not fixtures.exists():
            fixtures = root / "inputs"
        cls.books = {name: workbook((fixtures / name).read_bytes()) for name in BOOKS}

    def changed(self):
        return copy.deepcopy(self.books)

    def test_age_group_cannot_replace_source_bin(self):
        books = self.changed()
        books["age.xlsx"][0]["C1"] = "18 - 29"
        with self.assertRaisesRegex(ValueError, "header or age"):
            tables(books)

    def test_missing_zero_count_is_not_fabricated(self):
        books = self.changed()
        row = next(row for row in books["pre-reg.xlsx"][1:]
                   if next(iter(row.values())) == "Alpine")
        del row[next(key for key, value in row.items() if value == "0")]
        with self.assertRaisesRegex(ValueError, "nonrectangular"):
            tables(books)

    def test_county_sum_cannot_repair_statewide_total(self):
        books = self.changed()
        row = books["county.xlsx"][1]
        reference = next(key for key in row if key.startswith("C"))
        row[reference] = str(int(row[reference]) + 1)
        with self.assertRaisesRegex(ValueError, "county sums"):
            tables(books)

    def test_age_partition_must_match_registered_population(self):
        books = self.changed()
        row = books["age.xlsx"][1]
        reference = next(key for key in row if key.startswith("C"))
        row[reference] = str(int(row[reference]) + 1)
        with self.assertRaises(ValueError):
            tables(books)

    def test_preregistration_county_alias_is_not_joined(self):
        books = self.changed()
        row = books["pre-reg.xlsx"][1]
        reference = next(iter(row))
        row[reference] += " County"
        with self.assertRaisesRegex(ValueError, "county identities"):
            tables(books)

    def test_incomplete_county_book_is_not_statewide(self):
        books = self.changed()
        books["age.xlsx"].pop(1)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            tables(books)


if __name__ == "__main__":
    unittest.main()
