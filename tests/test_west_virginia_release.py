import copy
import json
from pathlib import Path
import unittest
import zipfile

from scripts.west_virginia_release import qualify_facts


class WestVirginiaReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixture = root / "data/west-virginia-preliminary-release/20261109-01/native-inputs.zip"
        if not fixture.exists():
            fixture = root / "inputs/complete-permitted-native-facts.zip"
        with zipfile.ZipFile(fixture) as archive:
            cls.facts = json.loads(archive.read("native-facts.json"))

    def changed(self, **updates):
        facts = copy.deepcopy(self.facts)
        facts.update(updates)
        return facts

    def test_selects_direct_native_parents_not_mode_totals(self):
        self.assertEqual(qualify_facts(self.facts), (463912, 1210385))

    def test_missing_cast_parent_cannot_use_early_or_received(self):
        with self.assertRaisesRegex(ValueError, "explicit native"):
            qualify_facts(self.changed(native_ballots_cast=None))

    def test_missing_register_cannot_use_eligible_population(self):
        facts = self.changed(native_registered=None, eligible_population=1500000)
        with self.assertRaisesRegex(ValueError, "explicit native"):
            qualify_facts(facts)

    def test_boolean_is_not_a_native_count(self):
        with self.assertRaisesRegex(ValueError, "explicit native"):
            qualify_facts(self.changed(native_ballots_cast=True))

    def test_changed_election_identity_requires_review(self):
        with self.assertRaisesRegex(ValueError, "statewide scope"):
            qualify_facts(self.changed(election_date="2026-05-12"))

    def test_preliminary_reference_cannot_silently_become_final(self):
        with self.assertRaisesRegex(ValueError, "statewide scope"):
            qualify_facts(self.changed(preliminary=False))

    def test_publication_date_is_not_assigned_as_count_cutoff(self):
        with self.assertRaisesRegex(ValueError, "not a native count"):
            qualify_facts(self.changed(count_snapshot_time="2026-11-06"))

    def test_percentage_disagreement_is_not_repaired(self):
        with self.assertRaisesRegex(ValueError, "percentage disagreement"):
            qualify_facts(self.changed(native_printed_pct="39.00"))

    def test_mode_counts_do_not_replace_or_add_to_state_reference(self):
        facts = self.changed(native_early_cast=999999, native_absentee_received=9999999)
        self.assertEqual(qualify_facts(facts), (463912, 1210385))

    def test_public_quote_budget_is_enforced(self):
        facts = self.changed(quoted_factual_fragments=[" ".join(["word"] * 26)])
        with self.assertRaisesRegex(ValueError, "quotation budget"):
            qualify_facts(facts)


if __name__ == "__main__":
    unittest.main()
