import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import shapefile
from scripts.historical_gis_attributes import build
from scripts.historical_precinct_rows import pin


class GISAttributeTests(unittest.TestCase):
    def test_allocated_variant_and_native_zero_keep_distinct_source_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);dbf=io.BytesIO()
            writer=shapefile.Writer(dbf=dbf)
            writer.field("NAME","C");writer.field("SEN18D","N",decimal=2)
            writer.record("001",0);writer.close()
            with zipfile.ZipFile(root/"source.zip","w") as archive:
                archive.writestr("source.dbf",dbf.getvalue())
            source=dict(source_id="allocated",original_path="source.zip",original_pin=pin(root/"source.zip"),
                dbf_member="source.dbf",encoding="ascii",expected_fields=["NAME","SEN18D"],
                election_fields=["SEN18D"],year=2018,state_code="MD",
                scope="publisher_allocated_not_observed",license="ODbL-1.0")
            spec=root/"spec.json";spec.write_text(json.dumps(dict(sources=[source])))
            result=build(spec,root,root/"out")
            self.assertEqual(result[0]["native_attribute_rows"],1)
            with gzip.open(root/"out/allocated.csv.gz","rt") as stream:
                content=stream.read()
            self.assertIn("publisher_allocated_not_observed",content)
            self.assertIn("geometry_not_approved",content)
            with self.assertRaises(ValueError):
                build(spec,root,root/"out")


if __name__=="__main__":
    unittest.main()
