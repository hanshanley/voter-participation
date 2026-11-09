import copy
import gzip
import json
from pathlib import Path
import unittest
import zipfile

from scripts.arkansas_state_control import parent_frames


class ArkansasParentControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixtures = root / "data/arkansas-state-controls/20261108-01"
        if fixtures.exists():
            cls.identity = json.loads((fixtures / "native-identity.json").read_bytes())
            cls.turnout = json.loads((fixtures / "native-turnout.json").read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/arkansas-complete-native-query.zip") as archive:
                receipts = json.loads(archive.read("native-source/sources.json"))
                def load(route):
                    name = next(name for name, row in receipts.items() if route in row["url"])
                    return json.loads(gzip.decompress(archive.read("native-source/originals/" + name + ".gz")))
                cls.identity = load("/Election/GetElectionInfo?")
                cls.turnout = load("/Turnout/GetTurnout?")

    def test_missing_state_register_cannot_use_partial_leaves(self):
        turnout = copy.deepcopy(self.turnout)
        turnout["response"]["registeredVoters"] = None
        with self.assertRaisesRegex(ValueError, "Missing or invalid native parent"):
            parent_frames(self.identity, turnout)

    def test_native_clock_cannot_be_assigned_a_timezone(self):
        identity, turnout = copy.deepcopy(self.identity), copy.deepcopy(self.turnout)
        identity["lastUpdated"] = turnout["lastUpdated"] = "2026-11-04T21:21:28"
        with self.assertRaisesRegex(ValueError, "UTC report clock"):
            parent_frames(identity, turnout)

    def test_different_api_versions_are_not_joined(self):
        turnout = copy.deepcopy(self.turnout)
        turnout["versionID"] = "different-source-version"
        with self.assertRaisesRegex(ValueError, "snapshot"):
            parent_frames(self.identity, turnout)

    def test_missing_county_parent_is_not_a_statewide_total(self):
        turnout = copy.deepcopy(self.turnout)
        del turnout["response"]["locations"][next(iter(turnout["response"]["locations"]))]
        with self.assertRaisesRegex(ValueError, "county parent coverage"):
            parent_frames(self.identity, turnout)

    def test_county_registered_sum_cannot_repair_state_parent(self):
        identity, turnout = copy.deepcopy(self.identity), copy.deepcopy(self.turnout)
        identity["turnout"]["registeredVoters"] += 1
        turnout["turnout"]["registeredVoters"] += 1
        turnout["response"]["registeredVoters"] += 1
        with self.assertRaisesRegex(ValueError, "County parent sums"):
            parent_frames(identity, turnout)

    def test_native_certification_cannot_be_promoted(self):
        identity = copy.deepcopy(self.identity)
        identity["isOfficial"] = True
        with self.assertRaisesRegex(ValueError, "certification status"):
            parent_frames(identity, self.turnout)


if __name__ == "__main__":
    unittest.main()
