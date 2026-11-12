import hashlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

from scripts.acquire_medsl_partitions import acquire, selected_files
from scripts.participation_intake.engine import Store


class Response(io.BytesIO):
    status = 200
    headers = {}


class PartitionAcquisitionTests(unittest.TestCase):
    def test_identical_concurrent_originals_are_published_as_one_complete_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/"cache")
            body=b"same complete native original\n"*100000
            with ThreadPoolExecutor(max_workers=8) as pool:
                paths=list(pool.map(store.object,[body]*16))
            self.assertEqual(len(set(paths)),1)
            self.assertEqual(paths[0].read_bytes(),body)
            self.assertEqual(list(paths[0].parent.glob(".original-*")),[])
            store.db.close()

    def fixture(self, root):
        bodies = {"README.md":b"Publisher notes", "LICENSE":b"MIT"}
        for office in ("house","president","senate","state","local"):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream,"w") as archive:
                archive.writestr("returns.csv","year,state,votes\n2016,AA,1\n")
            bodies[f"2016-precinct-{office}/2016-precinct-{office}.zip"] = stream.getvalue()
        tree = dict(truncated=False, tree=[dict(type="blob",path=name,size=len(body),
            sha=hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest())
            for name,body in bodies.items()])
        (root/"repository.json").write_text(json.dumps(dict(full_name="MEDSL/official-precinct-returns",license=dict(spdx_id="MIT"))))
        (root/"commit.json").write_text(json.dumps(dict(sha="a"*40)))
        (root/"tree.json").write_text(json.dumps(tree))
        return bodies,tree

    def test_alternative_state_and_RDA_copies_are_not_added_to_office_partitions(self):
        with tempfile.TemporaryDirectory() as temporary:
            _,tree = self.fixture(Path(temporary))
            tree["tree"] += [dict(type="blob",path="source/2016-al-precinct.zip"),
                             dict(type="blob",path="2016-precinct-house/house_precincts_2016.rda")]
            selected = selected_files(tree,2016)
            self.assertEqual(len(selected),7)
            self.assertFalse(any(row["path"].startswith("source/") or row["path"].endswith(".rda") for row in selected))

    def test_complete_run_resumes_without_network_and_tampered_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bodies,_ = self.fixture(root)
            def response(request,**kwargs):
                name = request.full_url.split("/"+"a"*40+"/",1)[1]
                return Response(bodies[name])
            with patch("urllib.request.OpenerDirector.open",side_effect=response) as network:
                first = acquire(root,2016)
                self.assertEqual(first["office_partitions"],5)
                self.assertEqual(network.call_count,7)
            with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("network not allowed")):
                second = acquire(root,2016)
                self.assertEqual(second["source_requests"],0)
                (root/"source/LICENSE").write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    acquire(root,2016)

    def test_access_denial_is_persisted_without_an_alternate_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bodies,_ = self.fixture(root)
            def response(request,**kwargs):
                url = request.full_url
                name = url.split("/"+"a"*40+"/",1)[1]
                if name=="LICENSE":
                    raise urllib.error.HTTPError(url,403,"Forbidden",{},None)
                return Response(bodies[name])
            with patch("urllib.request.OpenerDirector.open",side_effect=response):
                result = acquire(root,2016)
                self.assertEqual(result["acquired_files"],6)
            with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("denied route retried")):
                resumed = acquire(root,2016)
                self.assertEqual(resumed["source_requests"],0)
                self.assertEqual(resumed["acquired_files"],6)


if __name__=="__main__":
    unittest.main()
