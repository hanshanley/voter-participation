import unittest

from scripts.compile_jefferson_reference import SOURCE_ID, build
import json


def observation(name, count=10):
    return {"id": "observation-" + name, "geography": {"name": name, "level": "reporting_unit"},
            "count": {"status": "reported", "value": count}, "source": {"id": SOURCE_ID},
            "source_clock": {"literal": "11/06/2026     9:52 AM"},
            "view": {"unit_key": "jefferson-native:" + name}}


def feature(name, oid, x=0, bowtie=False):
    coordinates = ([[x, 0], [x + 1, 1], [x, 1], [x + 1, 0], [x, 0]] if bowtie else
                   [[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]])
    return {"type": "Feature", "properties": {"OBJECTID": oid, "PRECINCT": name},
            "geometry": {"type": "Polygon", "coordinates": [coordinates]}}


def compile_case(rows, features):
    identities = {"features": [{"attributes": feature["properties"]} for feature in features]}
    return build(rows, {"type": "FeatureCollection", "features": features}, len(features),
                 identities, identities)


class ReferenceTests(unittest.TestCase):
    def test_literal_suffix_is_held_even_if_its_stem_has_a_unique_reference(self):
        output = compile_case([observation("V120 MID")], [feature("V120", 1)])
        summary = json.loads(output["summary.json"])
        self.assertEqual(summary["candidate_eligible_literal_joins"], 0)
        self.assertEqual(summary["nonliteral_source_labels_held_without_suffix_stripping"], 1)

    def test_true_zero_is_not_missing_and_disjoint_literals_survive(self):
        output = compile_case([observation("A107", 0), observation("A108")],
                              [feature("A107", 1), feature("A108", 2, x=2)])
        candidate = json.loads(output["candidate-literal-only-reference.geojson"])
        self.assertEqual([f["properties"]["native_ballots"] for f in candidate["features"]], [0, 10])

    def test_invalid_export_is_held_without_repair(self):
        output = compile_case([observation("K161")], [feature("K161", 1, bowtie=True)])
        summary = json.loads(output["summary.json"])
        self.assertEqual(summary["invalid_export_geometries"], 1)
        self.assertEqual(summary["candidate_eligible_literal_joins"], 0)

    def test_both_members_of_a_positive_area_overlap_are_held(self):
        output = compile_case([observation("A107"), observation("A108")],
                              [feature("A107", 1), feature("A108", 2, x=.5)])
        summary = json.loads(output["summary.json"])
        self.assertEqual(summary["positive_area_pairs"], 1)
        self.assertEqual(summary["candidate_eligible_literal_joins"], 0)

    def test_duplicate_reference_and_incomplete_query_are_rejected(self):
        for reference, count in (([feature("A107", 1), feature("A107", 2, x=2)], 2),
                                 ([feature("A107", 1)], 2)):
            with self.assertRaises(ValueError):
                identities = {"features": [{"attributes": feature["properties"]} for feature in reference]}
                build([observation("A107")], {"type": "FeatureCollection", "features": reference},
                      count, identities, identities)

    def test_invalid_export_holds_potential_neighbors_without_repair(self):
        output = compile_case([observation("K161"), observation("K110")],
                              [feature("K161", 1, bowtie=True), feature("K110", 2, x=.5)])
        summary = json.loads(output["summary.json"])
        self.assertEqual(summary["invalid_geometry_neighbors_conservatively_held"], 1)
        self.assertEqual(summary["candidate_eligible_literal_joins"], 0)

    def test_reference_dates_and_partial_hold_legend_are_explicit(self):
        output = compile_case([observation("A107", 0)], [feature("A107", 1)])
        candidate = json.loads(output["candidate-literal-only-reference.geojson"])
        self.assertIn("unmapped/held, not zero", candidate["legend"])
        self.assertTrue(candidate["reference_scope"]["companion_map_date_is_not_assigned_to_geometry"])
        self.assertFalse(candidate["reference_scope"]["election_day_legal_boundaries_certified"])

    def test_null_identity_and_cross_export_identity_change_are_rejected(self):
        reference = {"type": "FeatureCollection", "features": [feature("A107", 1)]}
        for properties in ({"OBJECTID": None, "PRECINCT": "A107"},
                           {"OBJECTID": 1, "PRECINCT": "A108"}):
            with self.subTest(properties=properties), self.assertRaises(ValueError):
                build([observation("A107")], reference, 1,
                      {"features": [{"attributes": properties}]},
                      {"features": [{"attributes": {"OBJECTID": 1, "PRECINCT": "A107"}}]})


if __name__ == "__main__":
    unittest.main()
