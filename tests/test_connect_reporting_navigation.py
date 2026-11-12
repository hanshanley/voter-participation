import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from connect_reporting_navigation import connect_row


class NavigationTests(unittest.TestCase):
    def fixture(self):
        record = dict(properties=dict(state_code="AR", year=2026, county="Arkansas",
            key="AR|source-row", precinct="Arkansas · source row", reporting_unit_kind="source_reporting_unit",
            ballots=None, reported_pct=None), observation=dict(
                id="source-observation", geography=dict(id="source-unit", state_code="AR",
                    parent_id="old-native-label", level="reporting_unit", join=dict(status="unreviewed")),
                election=dict(year=2026), measure=dict(literal="ballots"), count=dict(value=None, status="unknown"),
                denominator=None, source_clock=dict(literal=None, timezone=None),
                reporting_status=dict(literal=None), source=dict(original_fact="untouched"),
                quality=dict(notes=["Native unknown remains unknown"]),
                view=dict(county_id="Arkansas", quality=[], reported_pct=None)))
        parents = [dict(id="parent-observation", geography=dict(id="canonical-parent", state_code="AR"),
                        view=dict(county="Arkansas County", county_id="additional:AR:05001"))]
        return record, parents

    def test_native_unknown_parent_aliases_and_source_facts_preserved(self):
        record, parents = self.fixture()
        original = copy.deepcopy(record)
        row, query = connect_row(record, parents, "AR")
        self.assertEqual(row["view"]["county_id"], "additional:AR:05001")
        self.assertEqual(row["geography"]["parent_id"], "canonical-parent")
        self.assertEqual(row["view"]["unit_kind"], "source_reporting_unit")
        self.assertIsNone(row["count"]["value"])
        self.assertIsNone(query["analysis_rate"])
        self.assertFalse(row["view"]["maps_approved"])
        for key in ("count", "denominator", "source", "source_clock", "reporting_status"):
            self.assertEqual(row[key], original["observation"][key])
        self.assertEqual(record, original)

    def test_ambiguous_cross_state_wrong_year_and_qualified_rate_rejected(self):
        for case in ("ambiguous", "other_state", "wrong_year", "qualified_rate"):
            record, parents = self.fixture()
            if case == "ambiguous":
                parents.append(copy.deepcopy(parents[0]))
            elif case == "other_state":
                parents[0]["geography"]["state_code"] = "WY"
            elif case == "wrong_year":
                record["properties"]["year"] = 2024
            else:
                record["observation"]["denominator"] = dict(qualified=True)
            with self.subTest(case=case), self.assertRaises(ValueError):
                connect_row(record, parents, "AR")


if __name__ == "__main__":
    unittest.main()
