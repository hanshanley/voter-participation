import copy
import gzip
import json
from pathlib import Path
import unittest
import zipfile

from scripts.alaska_state_control import HOUSE, parent_frame, select


class AlaskaFederalFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/alaska-state-controls/20261108-01/native-parent-snapshots.json"
        if fixture.exists():
            cls.facts = json.loads(fixture.read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/alaska-complete-native-query.zip") as archive:
                cls.facts = {name: json.loads(gzip.decompress(archive.read("originals/" + name + "-original.json.gz")))
                             for name in ("statewide", "precincts")}
                rows = json.loads(gzip.decompress(archive.read("participation.json.gz")))
                cls.facts["federal"] = next(row for row in rows if row["reporting_unit_kind"] == "federal_overseas")

    def frame(self, facts):
        return parent_frame(facts["statewide"], facts["precincts"], facts["federal"])

    def test_explicit_federal_parent_preserves_legacy_export_format(self):
        house, governor = self.frame(self.facts)
        self.assertEqual((house["b"], house["v"], house["p"], house["r"]), (215906, 605433, 403, 400))
        self.assertEqual(governor["b"], 215776)
        self.assertEqual(self.facts["statewide"]["format"], "2024")

    def test_missing_register_cannot_use_reporting_unit_sum(self):
        facts = copy.deepcopy(self.facts)
        del select(facts["statewide"], HOUSE)["v"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            self.frame(facts)

    def test_candidate_total_never_replaces_ballots(self):
        facts = copy.deepcopy(self.facts)
        for key in ("statewide", "precincts"):
            select(facts[key], HOUSE)["t"] = 999999
        house, _ = self.frame(facts)
        self.assertEqual(house["b"], 215906)

    def test_missing_ballots_cannot_use_candidate_total(self):
        facts = copy.deepcopy(self.facts)
        del select(facts["statewide"], HOUSE)["b"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            self.frame(facts)

    def test_federal_overseas_scope_cannot_be_blended(self):
        facts = copy.deepcopy(self.facts)
        facts["federal"]["ballots"] += 1
        with self.assertRaisesRegex(ValueError, "scopes must remain distinct"):
            self.frame(facts)

    def test_distinct_snapshot_clock_is_not_silently_joined(self):
        facts = copy.deepcopy(self.facts)
        facts["precincts"]["updated"] = "different native clock"
        with self.assertRaisesRegex(ValueError, "snapshots disagree"):
            self.frame(facts)

    def test_legacy_format_does_not_authorize_2024_election(self):
        facts = copy.deepcopy(self.facts)
        facts["statewide"]["name"] = "Alaska 2024 General Election"
        with self.assertRaisesRegex(ValueError, "election identity"):
            self.frame(facts)

    def test_native_certification_cannot_be_promoted(self):
        facts = copy.deepcopy(self.facts)
        facts["statewide"]["certified"] = True
        with self.assertRaisesRegex(ValueError, "certification"):
            self.frame(facts)


if __name__ == "__main__":
    unittest.main()
