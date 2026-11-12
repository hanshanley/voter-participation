from decimal import Decimal
import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import house_panel_validation as panel


def record():
    value = {"CC22_412": "1", "CC24_412": "2", "TS_g2022": "1", "TS_g2024": "NA",
             "TS_state_22": "TX", "TS_state_24": "TX", **{key: "1" for key in panel.WEIGHTS}}
    for year in (22, 24):
        for number in range(1, 9 if year == 22 else 6):
            value[f"HouseCand{number}Party_post_{year}"] = "Democratic" if number == 1 else "Republican"
    return value


class HousePanelTests(unittest.TestCase):
    def test_candidate_position_is_not_party(self):
        row = record()
        row["HouseCand1Party_post_22"] = "Republican"
        self.assertEqual(panel.house(row, 22), "R")

    def test_missing_party_placeholders_never_become_other(self):
        for missing in ("", "NA", "__NA__", "-1"):
            row = record()
            row["HouseCand1Party_post_22"] = missing
            self.assertEqual(panel.house(row, 22), "UNKNOWN")

    def test_unknown_history_is_not_resolved_by_reported_choice(self):
        result = panel.review_panel([record()])["scopes"]["ALL_SOURCE"]["frames"][panel.WEIGHTS[0]]
        self.assertEqual(result["both_major_choices"]["DR"]["n"], 1)
        self.assertEqual(result["both_major_choices_and_positive_history"]["DR"]["n"], 0)
        self.assertIn("POSITIVE|D|UNKNOWN|R", result["full_joint"])

    def test_contest_nonvote_is_not_administrative_nonvote(self):
        row = record()
        row.update(CC22_412="11", TS_g2022="1", TS_g2024="7")
        result = panel.review_panel([row])["scopes"]["ALL_SOURCE"]
        self.assertIn("POSITIVE|CONTEST_NONVOTE|EXPLICIT_NONVOTE|R", result["raw_full_joint"])

    def test_2024_does_not_inherit_2022_slots_or_no_election_code(self):
        for code in ("6", "7", "8", "12"):
            row = record()
            row["CC24_412"] = code
            with self.assertRaises(ValueError):
                panel.house(row, 24)

    def test_full_table_hold_prevents_small_cell_complements(self):
        table = {key: dict(n=100, weight=Decimal(100), squared_weight=Decimal(100))
                 for key in ("DD", "DR", "RD", "RR")}
        self.assertTrue(panel.selected_table(table)["available"])
        table["DR"]["n"] = 29
        self.assertEqual(panel.selected_table(table)["cells"], None)
        table["DR"]["n"] = 0
        self.assertEqual(panel.selected_table(table)["statistics"], None)

    def test_missing_weights_and_states_remain_accounted(self):
        row = record()
        row.update(TS_state_24="-1", commonpostweight_24="NA")
        result = panel.review_panel([row])
        self.assertEqual(result["scopes"]["UNLOCATED"]["raw_rows"], 1)
        self.assertEqual(result["scopes"]["ALL_SOURCE"]["frames"][panel.WEIGHTS[0]]["used"]["n"], 0)
        with self.assertRaises(ValueError):
            panel.weight("-0.1")

    def test_record_state_differences_are_not_election_day_migration(self):
        row = record()
        row["TS_state_22"] = "CA"
        self.assertEqual(panel.review_panel([row])["matched_record_state_comparison"]["different"], 1)

    def test_ap_reverse_recall_coding_and_reported_nonvote_filter(self):
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(("POLLCLOSE_STATE_WEIGHT", "LIKELYVOTER", "HOUSEVOTE", "QPVVOTE22", "QVOTE2022"))
        writer.writerows((("2", "(1) Voter", "(1) Democratic", "4", "(1) Republican"),
                          ("3", "1", "2", "4", "2"),
                          ("5", "1", "1", "1", "2")))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AP_VOTECAST_2024_GENERAL.csv", text.getvalue())
            result = panel.review_ap(path)
        self.assertEqual(result["table"]["RD"]["weight"], Decimal(2))
        self.assertEqual(result["table"]["DR"]["weight"], Decimal(3))
        self.assertEqual(sum(v["n"] for v in result["table"].values()), 2)

    def test_public_scope_cannot_release_state_or_sensitivity_tables(self):
        rows = []
        for before in "12":
            for after in "12":
                for unused in range(30):
                    row = record()
                    row.update(CC22_412=before, CC24_412=after, TS_g2024="6")
                    rows.append(row)
        private = panel.review_panel(rows)
        output = panel.public_selection(private, {"table": panel.major_table()})
        available = [row for row in output["decisions"] if row["available"]]
        self.assertEqual(len(output["decisions"]), 319)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0]["scope"], "ALL_SOURCE")
        self.assertEqual(available[0]["weight_frame"], "commonpostweight_24")


if __name__ == "__main__":
    unittest.main()
