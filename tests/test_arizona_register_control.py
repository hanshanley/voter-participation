import copy
import gzip
import json
from pathlib import Path
import unittest
import zipfile

from scripts.arizona_register_control import URL, parent_frame


class ArizonaRegisterFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/arizona-registration-controls/20261108-01/native-parent-snapshots.json"
        if fixture.exists():
            cls.facts = json.loads(fixture.read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/arizona-complete-native-query.zip") as archive:
                receipts = json.loads(archive.read("native-source/sources.json"))
                name = next(name for name, row in receipts.items() if row["url"] == URL)
                cls.facts = json.loads(gzip.decompress(archive.read("native-source/originals/" + name + ".gz")))

    def test_parent_keeps_ballot_zero_and_component_conflicts(self):
        registered, ballots, components = parent_frame(self.facts)
        self.assertEqual((registered, ballots), (4374827, 2248900))
        self.assertTrue(any(not row["components_match_total"] for row in components))
        self.assertEqual(self.facts["election"]["ballotsCast"], 0)

    def test_missing_state_parent_cannot_use_county_sum(self):
        facts = copy.deepcopy(self.facts)
        del facts["election"]["totalVoters"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            parent_frame(facts)

    def test_active_inactive_components_do_not_replace_total(self):
        facts = copy.deepcopy(self.facts)
        facts["voterRegistration"][0]["activeVoters"] = 1
        registered, _, components = parent_frame(facts)
        self.assertEqual(registered, 4374827)
        self.assertTrue(any(row["native_total_minus_components"] != 0 for row in components))

    def test_positive_state_ballots_require_a_new_review(self):
        facts = copy.deepcopy(self.facts)
        facts["election"]["ballotsCast"] = 2248900
        with self.assertRaisesRegex(ValueError, "ballot-zero conflict"):
            parent_frame(facts)

    def test_missing_county_registration_is_not_complete_support(self):
        facts = copy.deepcopy(self.facts)
        facts["voterRegistration"].pop()
        with self.assertRaisesRegex(ValueError, "county parent coverage"):
            parent_frame(facts)

    def test_state_registration_cannot_be_repaired(self):
        facts = copy.deepcopy(self.facts)
        facts["election"]["totalVoters"] += 1
        with self.assertRaisesRegex(ValueError, "registrations disagree"):
            parent_frame(facts)

    def test_source_timezone_cannot_be_invented(self):
        facts = copy.deepcopy(self.facts)
        facts["election"]["lastUpdated"] = "2026-11-05T01:56:17"
        with self.assertRaisesRegex(ValueError, "UTC clocks"):
            parent_frame(facts)


if __name__ == "__main__":
    unittest.main()
