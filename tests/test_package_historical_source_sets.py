from pathlib import Path
import tempfile
import unittest
import zipfile
from scripts.package_historical_source_sets import build


class HistoricalPackageTests(unittest.TestCase):
    def test_complete_source_query_code_package_has_deterministic_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/"source.csv";source.write_bytes(b"precinct,votes\n001,0\n")
            code=root/"calculate.py";code.write_bytes(b"print('offline')\n")
            members={"originals/source.csv":source,"queries/full.csv":source,"code/calculate.py":code}
            a=build(root/"a.zip",members,"Complete reproduction\n")
            b=build(root/"b.zip",members,"Complete reproduction\n")
            self.assertEqual(a,b)
            self.assertEqual((root/"a.zip").read_bytes(),(root/"b.zip").read_bytes())
            with zipfile.ZipFile(root/"a.zip") as archive:
                self.assertEqual(archive.read("queries/full.csv"),source.read_bytes())

    def test_metadata_only_unsafe_and_overwrite_requests_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/"source.csv";source.write_bytes(b"votes\n0\n")
            with self.assertRaises(ValueError):
                build(root/"bad.zip",{"metadata.json":source},"")
            members={name:source for name in ("originals/source.csv","queries/full.csv","code/code.py")}
            with self.assertRaises(ValueError):
                build(root/"unsafe.zip",dict(members,**{"../outside":source}),"")
            build(root/"complete.zip",members,"")
            with self.assertRaises(ValueError):
                build(root/"complete.zip",members,"")


if __name__=="__main__":
    unittest.main()
