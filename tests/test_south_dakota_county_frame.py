import copy
import gzip
import json
from pathlib import Path
import unittest
import zipfile

from scripts.south_dakota_county_frame import aggregate_frame


class SouthDakotaCountyFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/south-dakota-county-frame/20261108-01/native-county-snapshots.json"
        if fixture.exists():
            cls.sources = json.loads(fixture.read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/south-dakota-complete-native-query.zip") as archive:
                cls.sources = {name: json.loads(gzip.decompress(archive.read("originals/" + name + ".json.gz")))
                               for name in ("county-turnout-api", "turnout-facts")}

    def frame(self, sources):
        return aggregate_frame(sources["county-turnout-api"], sources["turnout-facts"])

    def test_complete_county_aggregate_uses_each_parent_once(self):
        registered, numerator, rows = self.frame(self.sources)
        self.assertEqual((registered, numerator, len(rows)), (628563, 310298, 66))

    def test_repeated_vote_center_leaf_counts_are_not_denominators(self):
        sources = copy.deepcopy(self.sources)
        county = next(row for row in sources["turnout-facts"]["counties"] if row["vote_center"])
        for row in county["records"]:
            row["registered"] = 999999
        self.assertEqual(self.frame(sources)[0], 628563)

    def test_missing_county_is_not_complete_state_coverage(self):
        sources = copy.deepcopy(self.sources)
        sources["county-turnout-api"]["d"].pop()
        with self.assertRaisesRegex(ValueError, "county coverage"):
            self.frame(sources)

    def test_duplicate_county_cannot_be_double_counted(self):
        sources = copy.deepcopy(self.sources)
        sources["county-turnout-api"]["d"][-1] = sources["county-turnout-api"]["d"][0]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.frame(sources)

    def test_missing_county_register_cannot_use_leaf_fallback(self):
        sources = copy.deepcopy(self.sources)
        del sources["county-turnout-api"]["d"][0]["Voters"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            self.frame(sources)

    def test_missing_county_turnout_is_not_zero(self):
        sources = copy.deepcopy(self.sources)
        del sources["county-turnout-api"]["d"][0]["calcVoterTurnout"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            self.frame(sources)

    def test_different_election_is_not_joined(self):
        sources = copy.deepcopy(self.sources)
        sources["turnout-facts"]["year"] = 2024
        with self.assertRaisesRegex(ValueError, "election identity"):
            self.frame(sources)

    def test_source_county_names_are_not_fuzzy_joined(self):
        sources = copy.deepcopy(self.sources)
        sources["county-turnout-api"]["d"][0]["CountyName"] = "different county"
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.frame(sources)


if __name__ == "__main__":
    unittest.main()
