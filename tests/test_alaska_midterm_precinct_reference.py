import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import Polygon, box, mapping

from scripts import alaska_midterm_precinct_reference as precinct


class PrecinctReferenceTest(unittest.TestCase):
    def setUp(self):
        labels = [f"01-{number:03} Place" for number in range(401)]
        attrs = [{"OBJECTID": i, "Precinct_Name": label, "HouseDistrict": 1,
                  "AsOfDate": precinct.VINTAGE} for i, label in enumerate(labels)]
        self.rows = [{"source_unit_id": label.split()[0], "reporting_unit": label,
                      "district": "1", "reported_ballots": 10} for label in labels]
        self.roster = {"features": [{"attributes": a} for a in attrs]}
        self.ids = {"objectIds": list(range(401))}
        self.geo = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": dict(a),
             "geometry": mapping(box(-152 + i * .005, 63, -151.998 + i * .005, 63.01))}
            for i, a in enumerate(attrs)]}
        self.parents = json.dumps({"features": [{"id": 1, "geometry": mapping(box(-153, 62, -149, 64))}]})

    def audit(self):
        with patch.object(precinct, "midterm_exports", return_value=self.rows):
            return precinct.audit({}, self.roster, self.ids, self.geo, self.parents)

    def test_strict_holds_preserve_all_counts_and_original_shapes(self):
        geos = self.geo["features"]
        geos[0]["geometry"] = geos[1]["geometry"]
        geos[2]["geometry"] = mapping(box(-146, 63, -145.99, 63.01))
        geos[3]["geometry"] = mapping(Polygon([(-152, 63), (-151, 64), (-152, 64), (-151, 63)]))
        self.rows[4]["reporting_unit"] = "01-004 Place/Bay"
        self.roster["features"][4]["attributes"]["Precinct_Name"] = "01-004 Place- Bay"
        geos[4]["properties"]["Precinct_Name"] = "01-004 Place- Bay"
        before = copy.deepcopy(self.geo)
        decisions, shapes, _ = self.audit()
        self.assertEqual(self.geo, before)
        self.assertEqual((len(decisions), len(shapes)), (401, 397))
        self.assertEqual([row["issues"] for row in decisions[:5]], [
            "overlapping_precinct_polygon", "overlapping_precinct_polygon",
            "outside_interim_house_district", "invalid_source_polygon", ""])
        self.assertEqual(decisions[2]["outside_district_percent"], 100)
        self.assertEqual(sum(r["election_day_ballots"] for r in decisions if not r["map_qualified"]), 40)
        self.assertEqual(shapes[0]["geometry"], before["features"][4]["geometry"])

    def test_missing_id_wrong_vintage_and_nonpunctuation_mismatch_fail(self):
        self.ids["objectIds"].pop()
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.audit()
        self.ids["objectIds"].append(400)
        attrs = self.roster["features"][0]["attributes"]
        props = self.geo["features"][0]["properties"]
        attrs["AsOfDate"] = props["AsOfDate"] = 0
        with self.assertRaisesRegex(ValueError, "dated reporting roster"):
            self.audit()
        attrs["AsOfDate"] = props["AsOfDate"] = precinct.VINTAGE
        attrs["Precinct_Name"] = props["Precinct_Name"] = "01-000 Different"
        with self.assertRaisesRegex(ValueError, "dated reporting roster"):
            self.audit()

    def test_changed_original_fails_before_parse(self):
        with tempfile.TemporaryDirectory() as output:
            path = Path(output)
            (path / "state-roster.json").write_text("different bytes")
            with self.assertRaisesRegex(ValueError, "pin differs"):
                precinct.read_pinned(path, "state-roster.json")
