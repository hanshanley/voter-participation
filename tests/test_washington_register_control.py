import copy
import gzip
import json
from pathlib import Path
import unittest
import zipfile

from scripts.washington_register_control import parent_frame


class WashingtonRegisterFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/washington-registration-controls/20261108-01/native-parent-snapshots.json"
        if fixture.exists():
            cls.facts = json.loads(fixture.read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/washington-complete-native-query.zip") as archive:
                cls.facts = json.loads(gzip.decompress(archive.read("source-records.json.gz")))

    def test_explicit_parent_does_not_promote_state_ballot_zero(self):
        self.assertEqual(parent_frame(self.facts), (5170951, 2266746))
        self.assertEqual(self.facts["state_election"]["ballotsCast"], 0)

    def test_missing_state_parent_cannot_use_county_sum(self):
        facts = copy.deepcopy(self.facts)
        del facts["state_election"]["totalVoters"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            parent_frame(facts)

    def test_positive_state_ballots_require_a_new_review(self):
        facts = copy.deepcopy(self.facts)
        facts["state_election"]["ballotsCast"] = 2266746
        with self.assertRaisesRegex(ValueError, "ballot-zero conflict"):
            parent_frame(facts)

    def test_missing_county_is_not_complete_support(self):
        facts = copy.deepcopy(self.facts)
        facts["counties"].pop()
        with self.assertRaisesRegex(ValueError, "county parent coverage"):
            parent_frame(facts)

    def test_state_registration_cannot_be_repaired(self):
        facts = copy.deepcopy(self.facts)
        facts["state_election"]["totalVoters"] += 1
        with self.assertRaisesRegex(ValueError, "registrations disagree"):
            parent_frame(facts)

    def test_distinct_native_county_headers_must_match(self):
        facts = copy.deepcopy(self.facts)
        facts["state_locality_elections"][0]["totalVoters"] += 1
        with self.assertRaisesRegex(ValueError, "parent counts disagree"):
            parent_frame(facts)

    def test_source_timezone_cannot_be_invented(self):
        facts = copy.deepcopy(self.facts)
        facts["state_election"]["lastUpdated"] = "2026-11-05T03:57:41"
        with self.assertRaisesRegex(ValueError, "UTC clocks"):
            parent_frame(facts)


if __name__ == "__main__":
    unittest.main()
