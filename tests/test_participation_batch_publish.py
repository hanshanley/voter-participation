import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts.participation_batch_publish import publish_datasets


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"))+"\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


class BatchPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.download = dict(url="https://github.com/example/repo/releases/download/frozen/complete-analysis.zip",
            bytes=100, sha256="d"*64, verified_anonymously=True, immutable=True)
        self.catalog = dict(contract="participation.dataset_catalog.v1", datasets={})
        self.snapshots = {"parent": {"catalog.json": encoded(self.catalog)}}
        self.head, self.commits, self.pushes, self.validations = "parent", [], [], []
        self.fail_verification = False
        outer = self

        class FakePublisher:
            github_repository = "example/repo"
            def __init__(self, repository):
                pass
            def remote_head(self):
                return outer.head
            def fetch_parent(self, parent):
                pass
            def catalog(self, parent):
                return json.loads(outer.snapshots[parent]["catalog.json"])
            def tree(self, parent, bodies):
                return dict(outer.snapshots[parent], **bodies)
            def commit(self, tree, parent, message):
                identity = "commit-"+str(len(outer.commits)+1)
                outer.snapshots[identity] = tree
                outer.commits.append((identity, parent, message))
                return identity
            def promote(self, commit, expected):
                if outer.head != expected:
                    raise ValueError("Concurrent publisher")
                outer.head = commit
                outer.pushes.append(commit)
            def verify_files(self, commit, files):
                if outer.fail_verification:
                    outer.fail_verification = False
                    raise RuntimeError("Interrupted anonymous verification")
                for name, expected in files.items():
                    if pin(outer.snapshots[commit][name]) != expected:
                        raise ValueError("Published bytes differ")
                return list(files)

        def validate(root):
            outer.validations.append(str(root))
            description = json.loads((root/"dataset.json").read_bytes())
            for name, expected in description["files"].items():
                if pin((root/name).read_bytes()) != expected:
                    raise ValueError("Changed immutable local bytes")
            return description

        package = types.ModuleType("scripts.participation_intake")
        package.__path__ = []
        contract = types.ModuleType("scripts.participation_intake.contract")
        contract.encoded, contract.pin = encoded, pin
        publisher = types.ModuleType("scripts.participation_intake.publisher")
        publisher.GitPublisher, publisher.validate_dataset = FakePublisher, validate
        self.patch = patch.dict(sys.modules, {"scripts.participation_intake": package,
            "scripts.participation_intake.contract": contract, "scripts.participation_intake.publisher": publisher})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def dataset(self, identity, version):
        root = self.root/identity
        root.mkdir()
        body = encoded(dict(observations=version))
        (root/"index.json").write_bytes(body)
        description = dict(id=identity, version=version, files={"index.json": pin(body)}, complete_download=self.download)
        (root/"dataset.json").write_bytes(encoded(description))
        return root, description

    def install(self, identity, description):
        self.catalog["datasets"][identity] = copy.deepcopy(description)
        self.snapshots["parent"]["catalog.json"] = encoded(self.catalog)

    def publish(self, roots, expected):
        return publish_datasets(self.root, roots, expected, self.download, self.root/"journal.json")

    def test_two_datasets_activate_in_one_catalog_commit_and_preserve_unrelated_entry(self):
        counts, _ = self.dataset("counts", "new-counts")
        native, _ = self.dataset("native", "new-native")
        self.install("counts", dict(version="old-counts"))
        self.install("native", dict(version="old-native"))
        self.install("resident", dict(version="untouched", arbitrary="preserve"))
        result = self.publish([counts, native], {"counts": "old-counts", "native": "old-native"})
        self.assertEqual(len(self.commits), 2)
        self.assertEqual(json.loads(self.snapshots["commit-1"]["catalog.json"]), self.catalog)
        final = json.loads(self.snapshots[self.head]["catalog.json"])
        self.assertEqual(final["datasets"]["resident"], self.catalog["datasets"]["resident"])
        self.assertEqual(final["datasets"]["counts"]["version"], "new-counts")
        self.assertEqual(final["datasets"]["native"]["version"], "new-native")
        self.assertEqual(result["datasets_changed"], 2)

    def test_interrupted_verification_resumes_without_duplicate_staging_or_early_activation(self):
        counts, _ = self.dataset("counts", "new")
        self.install("counts", dict(version="old"))
        self.fail_verification = True
        with self.assertRaises(RuntimeError):
            self.publish([counts], {"counts": "old"})
        self.assertEqual(self.head, "commit-1")
        self.assertEqual(json.loads(self.snapshots[self.head]["catalog.json"]), self.catalog)
        result = self.publish([counts], {"counts": "old"})
        self.assertEqual(len(self.commits), 2)
        self.assertEqual(result["catalog_commit"], "commit-2")

    def test_noop_still_rejects_tampered_immutable_local_bytes(self):
        root, description = self.dataset("counts", "same")
        self.install("counts", description)
        (root/"index.json").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.publish([root], {"counts": "same"})
        self.assertFalse(self.commits)

    def test_valid_noop_checks_bytes_without_rewriting_or_publishing(self):
        root, description = self.dataset("counts", "same")
        self.install("counts", description)
        before = (root/"dataset.json").read_bytes()
        result = self.publish([root], {"counts": "same"})
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual((root/"dataset.json").read_bytes(), before)
        self.assertEqual(self.validations, [str(root)])
        self.assertFalse(self.commits or self.pushes)

    def test_duplicate_dataset_rejected_before_any_remote_stage(self):
        root, _ = self.dataset("counts", "new")
        self.install("counts", dict(version="old"))
        with self.assertRaises(ValueError):
            self.publish([root, root], {"counts": "old"})
        self.assertFalse(self.commits or self.pushes)

    def test_changed_resume_inputs_and_advanced_catalog_do_not_overwrite(self):
        root, _ = self.dataset("counts", "new")
        self.install("counts", dict(version="old"))
        self.fail_verification = True
        with self.assertRaises(RuntimeError):
            self.publish([root], {"counts": "old"})
        self.snapshots["external"] = copy.deepcopy(self.snapshots[self.head])
        self.head = "external"
        with self.assertRaises(ValueError):
            self.publish([root], {"counts": "old"})
        self.assertEqual(self.head, "external")
        self.assertEqual(len(self.commits), 1)


if __name__ == "__main__":
    unittest.main()
