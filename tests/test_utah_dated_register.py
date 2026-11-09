import copy
import csv
import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.utah_dated_register import active_frame


class UtahDatedActiveFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/utah-dated-register/20261108-01/native-registration-snapshots.json"
        if fixture.exists():
            cls.sources = json.loads(fixture.read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/utah-complete-native-numerical-query.zip") as archive:
                cls.sources = dict(
                    registration=json.loads(archive.read("source-qualification.json"))["registration_review"],
                    state_rows=list(csv.DictReader(io.StringIO(archive.read("state-party-registrations.csv").decode()))))

    def frame(self, sources):
        return active_frame(sources["registration"], sources["state_rows"])

    def test_selects_active_not_combined_and_keeps_discrepancy(self):
        parent = self.frame(self.sources)
        self.assertEqual(parent["active"], 1784255)
        self.assertEqual(parent["total"], 2099225)
        self.assertEqual(parent["active"] + parent["inactive"] - parent["total"], 1)

    def test_missing_total_cannot_use_county_marginals(self):
        sources = copy.deepcopy(self.sources)
        sources["registration"]["native_state_party_rows"] = [
            row for row in sources["registration"]["native_state_party_rows"] if row["party_literal"] != "Total"]
        with self.assertRaisesRegex(ValueError, "native Total parent"):
            self.frame(sources)

    def test_missing_active_cannot_use_combined_total(self):
        sources = copy.deepcopy(self.sources)
        del next(row for row in sources["registration"]["native_state_party_rows"] if row["party_literal"] == "Total")["active"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            self.frame(sources)

    def test_different_date_requires_a_new_frame_review(self):
        sources = copy.deepcopy(self.sources)
        sources["registration"]["source_date_literal"] = "11/03/2026"
        with self.assertRaisesRegex(ValueError, "snapshot date"):
            self.frame(sources)

    def test_duplicate_total_is_not_added(self):
        sources = copy.deepcopy(self.sources)
        sources["registration"]["native_state_party_rows"].append(
            next(row for row in sources["registration"]["native_state_party_rows"] if row["party_literal"] == "Total"))
        with self.assertRaisesRegex(ValueError, "duplicate native Total"):
            self.frame(sources)

    def test_parent_csv_disagreement_is_not_repaired(self):
        sources = copy.deepcopy(self.sources)
        next(row for row in sources["state_rows"] if row["party_literal"] == "Total")["active"] = "1"
        with self.assertRaisesRegex(ValueError, "accounting query disagree"):
            self.frame(sources)

    def test_county_marginal_changes_do_not_replace_parent(self):
        sources = copy.deepcopy(self.sources)
        for row in sources["registration"]["native_rows"]:
            row["active_registered_voters"] = 999999
        self.assertEqual(self.frame(sources)["active"], 1784255)

    def test_party_components_do_not_replace_native_total_active(self):
        sources = copy.deepcopy(self.sources)
        for row in sources["registration"]["native_state_party_rows"]:
            if row["party_literal"] != "Total":
                row["active"] = 0
        self.assertEqual(self.frame(sources)["active"], 1784255)


if __name__ == "__main__":
    unittest.main()
