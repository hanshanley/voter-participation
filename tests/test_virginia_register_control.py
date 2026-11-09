import copy
import gzip
import json
from pathlib import Path
import unittest
import zipfile

from scripts.virginia_register_control import parent_frame


class VirginiaRegisterFrameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/virginia-registration-controls/20261108-01/native-parent-snapshots.json"
        if fixture.exists():
            cls.facts = json.loads(fixture.read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/virginia-complete-native-query.zip") as archive:
                cls.facts = json.loads(gzip.decompress(archive.read("native-locality-source/originals/parent-state.gz")))

    def test_parent_preserves_zero_and_reconciled_components(self):
        registered, ballots, parents = parent_frame(self.facts)
        self.assertEqual((registered, ballots), (6494441, 3593781))
        self.assertTrue(all(row["components_match_total"] for row in parents))
        self.assertEqual(self.facts["election"]["ballotsCast"], 0)

    def test_missing_state_parent_cannot_use_locality_sum(self):
        facts = copy.deepcopy(self.facts)
        del facts["election"]["totalVoters"]
        with self.assertRaisesRegex(ValueError, "explicit native parent"):
            parent_frame(facts)

    def test_component_changes_do_not_replace_explicit_total(self):
        facts = copy.deepcopy(self.facts)
        facts["voterRegistration"][0]["activeVoters"] += 1
        registered, _, parents = parent_frame(facts)
        self.assertEqual(registered, 6494441)
        self.assertTrue(any(not row["components_match_total"] for row in parents))

    def test_positive_state_ballots_require_a_new_review(self):
        facts = copy.deepcopy(self.facts)
        facts["election"]["ballotsCast"] = 3593781
        with self.assertRaisesRegex(ValueError, "ballot-zero conflict"):
            parent_frame(facts)

    def test_missing_locality_is_not_complete_support(self):
        facts = copy.deepcopy(self.facts)
        facts["localityElections"].pop()
        with self.assertRaisesRegex(ValueError, "locality parent coverage"):
            parent_frame(facts)

    def test_state_registration_cannot_be_repaired(self):
        facts = copy.deepcopy(self.facts)
        facts["election"]["totalVoters"] += 1
        with self.assertRaisesRegex(ValueError, "registrations disagree"):
            parent_frame(facts)

    def test_source_timezone_cannot_be_invented(self):
        facts = copy.deepcopy(self.facts)
        facts["election"]["lastUpdated"] = "2026-11-04T23:28:02"
        with self.assertRaisesRegex(ValueError, "UTC clocks"):
            parent_frame(facts)


if __name__ == "__main__":
    unittest.main()
