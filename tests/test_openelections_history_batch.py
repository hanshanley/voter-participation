import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.openelections_history_batch import collect, statewide_files, supplemental_files
from scripts.precinct_source_batch import STATE_CODES
from scripts.participation_intake.contract import encoded,pin


class StatewideHistoryTests(unittest.TestCase):
    def test_county_and_county_level_files_are_not_national_precinct_inputs(self):
        tree=dict(truncated=False,tree=[dict(type="blob",path=p) for p in [
            "2018/20181106__al__general__precinct.csv",
            "2020/20201103__al__general__precinct__federal.csv",
            "2020/20201103__al__general__county.csv",
            "2020/20201103__al__general__autauga__precinct.csv",
            "2020/20200303__al__primary__precinct.csv",
            "2020/20201103__ar__general__precinct.csv"]])
        selected=statewide_files(tree,"AL")
        self.assertEqual(len(selected),2)
        self.assertEqual([row["year"] for row in selected],[2018,2020])

    def test_truncated_or_unsafe_inventory_is_not_accepted(self):
        with self.assertRaises(ValueError):
            statewide_files(dict(truncated=True,tree=[]),"AL")
        with self.assertRaises(ValueError):
            statewide_files(dict(truncated=False,tree=[dict(type="blob",path="../escape")]),"AL")

    def test_supplements_keep_native_scope_and_do_not_repeat_statewide_years(self):
        tree=dict(truncated=False,tree=[dict(type="blob",path=p) for p in [
            "2018/20181106__wi__general__ward.csv",
            "2020/20201103__wi__general__ward.csv",
            "2020/20201103__wi__general__dane__precinct.csv",
            "2020/20201103__wi__general__county.csv",
            "2020/20200407__wi__general__ward.csv"]])
        prior=dict(acquired_files=[dict(year=2018,acquisition=dict(acquired=True))])
        selected=supplemental_files(tree,"WI",prior)
        self.assertEqual(len(selected),2)
        self.assertEqual({row["year"] for row in selected},{2020})
        self.assertEqual({row["source_product_scope"] for row in selected},
            {"native_ward_not_assumed_precinct","county_partition_geography_unqualified"})
        with self.assertRaises(ValueError):
            supplemental_files(dict(tree=[],truncated=True),"WI",prior)

    def test_completed_different_selection_is_not_a_valid_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            rows=[dict(state_code=state,acquired_files=[],selection_scope="supplemental_partitions")
                  for state in sorted(STATE_CODES.values())]
            (root/"complete-jurisdiction-query.json").write_bytes(encoded(rows))
            repositories=[dict(full_name="openelections/openelections-data-"+state.lower(),private=False)
                          for state in STATE_CODES.values()]
            with self.assertRaises(ValueError):
                collect(repositories,root)

    def test_completed_batch_verifies_originals_without_requests_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            body=b"county,precinct,office,votes\nA,001,US House,0\n"
            source=root/"AL/originals/20181106__al__general__precinct.csv"
            source.parent.mkdir(parents=True);source.write_bytes(body)
            product=dict(path=source.name,year=2018,native_git_blob=hashlib.sha1(
                b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest(),
                acquisition=dict(acquired=True,**pin(body)))
            rows=[dict(state_code=state,acquired_files=[product] if state=="AL" else [])
                  for state in sorted(STATE_CODES.values())]
            (root/"complete-jurisdiction-query.json").write_bytes(encoded(rows))
            repositories=[dict(full_name="openelections/openelections-data-"+state.lower(),private=False)
                          for state in STATE_CODES.values()]
            with patch("scripts.openelections_history_batch.github_json",side_effect=AssertionError("network")):
                self.assertEqual(collect(repositories,root)["source_requests"],0)
                source.write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    collect(repositories,root)


if __name__=="__main__":
    unittest.main()
