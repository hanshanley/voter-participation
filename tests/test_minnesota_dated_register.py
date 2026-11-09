import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.minnesota_dated_register import registration_frame


class MinnesotaDatedRegisterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/minnesota-dated-register/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-minnesota-dated-native-inputs.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.body = archive.read("native-table.html")
            cls.independent = json.loads(archive.read("independent-table.json"))
            cls.scope = json.loads(archive.read("source-scope.json"))

    def frame(self, body=None, independent=None, scope=None):
        return registration_frame(self.body if body is None else body,
            self.independent if independent is None else independent,
            self.scope if scope is None else scope)

    def changed(self, before, after):
        body = self.body.replace(before.encode(), after.encode())
        independent = copy.deepcopy(self.independent)
        for row in independent["rows"]:
            for index, value in enumerate(row):
                if value == before:
                    row[index] = after
        return body, independent

    def test_selects_registered_parent_without_adding_preregistered_adolescents(self):
        registered, preregistered, cells, _ = self.frame()
        self.assertEqual((registered, preregistered), (3927036, 94621))
        self.assertEqual(len(cells), 176)
        self.assertTrue(all(not row["used_for_model_denominator"] for row in cells
                            if row["population_label"] == "Pre-Registered Voters"))

    def test_preregistered_total_change_does_not_change_registered_parent(self):
        body, independent = self.changed("94,621", "999,999")
        registered, _, _, diagnostics = self.frame(body, independent)
        self.assertEqual(registered, 3927036)
        self.assertNotEqual(diagnostics[1]["difference"], 0)

    def test_missing_registered_parent_cannot_use_county_sum_fallback(self):
        body, independent = self.changed("3,927,036", "")
        with self.assertRaisesRegex(ValueError, "no zero or county-sum fallback"):
            self.frame(body, independent)

    def test_missing_total_label_cannot_be_repaired(self):
        body, independent = self.changed("TOTAL", "Unknown")
        with self.assertRaisesRegex(ValueError, "explicit TOTAL"):
            self.frame(body, independent)

    def test_duplicate_county_is_not_complete_native_coverage(self):
        body, independent = self.changed("Aitkin", "Anoka")
        with self.assertRaisesRegex(ValueError, "duplicate native county"):
            self.frame(body, independent)

    def test_independent_count_disagreement_is_not_normalized(self):
        independent = copy.deepcopy(self.independent)
        independent["rows"][1][1] = "12,517"
        with self.assertRaisesRegex(ValueError, "HTML readers disagree"):
            self.frame(independent=independent)

    def test_population_header_cannot_be_swapped(self):
        body, independent = self.changed("Pre-Registered Voters", "Registered Adults")
        with self.assertRaisesRegex(ValueError, "column identity"):
            self.frame(body, independent)

    def test_snapshot_date_cannot_be_inferred_from_older_workbook(self):
        body = self.body.replace(b"November 2, 2026", b"May 1, 2026")
        independent = copy.deepcopy(self.independent)
        independent["caption"] = "Voter Counts by County as of May 1, 2026"
        with self.assertRaisesRegex(ValueError, "snapshot caption/date"):
            self.frame(body, independent)

    def test_preregistration_cannot_be_promoted_into_model_universe(self):
        scope = copy.deepcopy(self.scope)
        scope["preregistered_excluded_from_model_denominator"] = False
        with self.assertRaisesRegex(ValueError, "universe qualification"):
            self.frame(scope=scope)

    def test_literal_zero_remains_observed_instead_of_missing(self):
        body, independent = self.changed("12,516", "0")
        _, _, cells, diagnostics = self.frame(body, independent)
        row = next(row for row in cells if row["county_literal"] == "Aitkin"
                   and row["population_label"] == "Registered Voters")
        self.assertEqual(row["native_count"], 0)
        self.assertFalse(row["missing_imputed_zero"])
        self.assertNotEqual(diagnostics[0]["difference"], 0)


if __name__ == "__main__":
    unittest.main()
