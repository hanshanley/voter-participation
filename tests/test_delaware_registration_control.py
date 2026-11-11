import copy
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import unittest
import zipfile

from scripts.delaware_registration_control import integer, native_frame


class DelawareRegisterControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        fixtures = root / "data/delaware-registration-controls/20261108-01"
        if fixtures.exists():
            cls.source = json.loads((fixtures / "native-source-qualification.json").read_bytes())
            cls.native = json.loads((fixtures / "native-turnout.json").read_bytes())
        else:
            with zipfile.ZipFile(root / "inputs/delaware-complete-native-query.zip") as archive:
                cls.source = json.loads(archive.read("source-qualification.json"))
                cls.native = json.loads(archive.read("native-turnout.json"))

    def test_candidate_clock_cannot_fill_turnout_clock(self):
        source = copy.deepcopy(self.source)
        source["native_turnout_update_clock"] = source["separate_candidate_clock"]
        with self.assertRaisesRegex(ValueError, "clock"):
            native_frame(source, self.native)

    def test_native_rate_hold_cannot_be_promoted(self):
        source = copy.deepcopy(self.source)
        source["analysis_rate_approved"] = True
        with self.assertRaisesRegex(ValueError, "approvals"):
            native_frame(source, self.native)

    def test_duplicate_district_is_not_added(self):
        native = copy.deepcopy(self.native)
        native[-1]["Representative District"] = native[-2]["Representative District"]
        with self.assertRaisesRegex(ValueError, "Incomplete or duplicate"):
            native_frame(self.source, native)

    def test_district_accounting_does_not_repair_state(self):
        native = copy.deepcopy(self.native)
        row = next(row for row in native if row["Representative District"] != "ALL")
        row["Ballots Cast"] = integer(row["Ballots Cast"]) + 1
        row["Percentage"] = str((100 * Decimal(row["Ballots Cast"]) / integer(row["Reg Voters"])).quantize(
            Decimal(".01"), rounding=ROUND_HALF_UP))
        with self.assertRaisesRegex(ValueError, "District accounting"):
            native_frame(self.source, native)

    def test_different_election_is_not_merged(self):
        native = copy.deepcopy(self.native)
        native[0]["Election Name"] = "2026 Primary Election"
        with self.assertRaisesRegex(ValueError, "election or status"):
            native_frame(self.source, native)

    def test_missing_register_is_not_zero(self):
        native = copy.deepcopy(self.native)
        native[0]["Reg Voters"] = None
        with self.assertRaisesRegex(ValueError, "literal native count"):
            native_frame(self.source, native)


if __name__ == "__main__":
    unittest.main()
