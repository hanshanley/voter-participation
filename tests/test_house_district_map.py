import io
import unittest
import zipfile

import shapefile

from scripts.house_district_map import (
    CRS, compressed, conic, district_key, display_paths, read_archive,
)


PRJ = ('GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
       'SPHEROID["GRS_1980",6378137,298.257222101]],PRIMEM["Greenwich",0],'
       'UNIT["Degree",0.017453292519943295]]')


def source(rows=None, projection=PRJ, congress=120, rings=None):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    with shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON) as writer:
        for field in ("STATEFP", f"CD{congress}FP", "GEOID", "CDSESSN"):
            writer.field(field, "C", size=16)
        for row in rows or [("10", "00", "1000", str(congress))]:
            writer.poly(rings or [[[-76, 38], [-76, 40], [-74, 40], [-74, 38], [-76, 38]]])
            writer.record(*row)
    stem = f"tl_2026_10_cd{congress}"
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        for extension, value in (("shp", shp.getvalue()), ("shx", shx.getvalue()),
                                 ("dbf", dbf.getvalue()), ("prj", projection.encode())):
            archive.writestr(stem + "." + extension, value)
    return body.getvalue()


class DistrictMapTests(unittest.TestCase):
    def test_projection_matches_independent_proj_and_north_is_up(self):
        from pyproj import Proj

        for meridian, lower, upper in ((-96, 29.5, 45.5), (-154, 55, 65), (-157, 8, 18)):
            project = conic(meridian, lower, upper)
            reference = Proj(
                f"+proj=aea +R=1 +lon_0={meridian} +lat_1={lower} +lat_2={upper}")
            origin = (meridian, (lower + upper) / 2)
            actual_origin, expected_origin = project(*origin), reference(*origin)
            for lon, lat in ((meridian - 10, lower), (meridian, upper), (meridian + 10, lower)):
                with self.subTest(meridian=meridian, lon=lon, lat=lat):
                    actual, expected = project(lon, lat), reference(lon, lat)
                    for axis in (0, 1):
                        self.assertAlmostEqual(actual[axis] - actual_origin[axis],
                                               expected[axis] - expected_origin[axis], places=12)
            self.assertGreater(project(meridian, upper)[1], project(meridian, lower)[1])

    def test_literal_at_large_and_leading_zero_identifiers(self):
        records, shapes = read_archive(source(), "DE", 2026, 120)
        self.assertEqual(records[0]["district"], "DE-AL")
        self.assertEqual(records[0]["geoid"], "1000")
        self.assertEqual(records[0]["native_crs"], CRS)
        self.assertTrue(shapes["DE-AL"].is_valid)
        self.assertEqual(district_key("AL", "01"), "AL-01")
        self.assertEqual(district_key("CT", "ZZ"), "CT-ZZ")

    def test_wrong_session_state_and_duplicate_identity_refused(self):
        for rows in ([("10", "00", "1000", "119")],
                     [("01", "00", "1000", "120")],
                     [("10", "00", "100", "120")],
                     [("10", "00", "1000", "120")] * 2):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "Duplicate district"):
                read_archive(source(rows), "DE", 2026, 120)

    def test_wgs84_not_silently_substituted_for_nad83(self):
        wgs = PRJ.replace("GCS_North_American_1983", "WGS 84").replace(
            "D_North_American_1983", "WGS_1984").replace("GRS_1980", "WGS 84").replace(
            "298.257222101", "298.257223563")
        with self.assertRaisesRegex(ValueError, "native NAD83"):
            read_archive(source(projection=wgs), "DE", 2026, 120)

    def test_display_is_separate_and_preserves_input_geometry(self):
        from shapely.geometry import Polygon

        rows, shapes = read_archive(source(), "DE", 2026, 120)
        for state, ring in (
            ("AK", [(-160, 55), (-160, 65), (-140, 65), (-140, 55), (-160, 55)]),
            ("HI", [(-160, 19), (-160, 21), (-155, 21), (-155, 19), (-160, 19)]),
        ):
            key = state + "-AL"
            rows.append({**rows[0], "district": key, "state_code": state,
                         "geoid": state, "state_fips": state})
            shapes[key] = Polygon(ring)
        before = {key: value.wkb for key, value in shapes.items()}
        paths = display_paths(rows, shapes)
        self.assertEqual({row["district"] for row in paths}, {"DE-AL", "AK-AL", "HI-AL"})
        self.assertTrue(all(row["d"].startswith("M") and row["d"].endswith("Z") for row in paths))
        self.assertEqual({key: value.wkb for key, value in shapes.items()}, before)
        for row in paths:
            self.assertTrue(all(0 <= value <= 1000 for value in row["point"]))

    def test_unsafe_archive_and_noncontiguous_seats_refused(self):
        body = io.BytesIO(source())
        with zipfile.ZipFile(body, "a") as archive:
            archive.writestr("../outside", b"no")
        with self.assertRaisesRegex(ValueError, "archive member"):
            read_archive(body.getvalue(), "DE", 2026, 120)
        with self.assertRaisesRegex(ValueError, "contiguous"):
            read_archive(source([("10", "02", "1002", "120")]), "DE", 2026, 120)

    def test_self_intersecting_native_polygon_is_not_silently_repaired(self):
        body = source(rings=[[[-76,38],[-74,40],[-76,40],[-74,38],[-76,38]]])
        with self.assertRaisesRegex(ValueError, "invalid"):
            read_archive(body, "DE", 2026, 120)


if __name__ == "__main__":
    unittest.main()
