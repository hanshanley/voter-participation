import gzip
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "louisiana_native_builder", ROOT / "scripts/build_louisiana_native_groups.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class LouisianaNativeGroupsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = os.environ.get("LOUISIANA_NATIVE_SDK_PACKAGE")
        if not package:
            raise unittest.SkipTest(
                "Set LOUISIANA_NATIVE_SDK_PACKAGE to the extracted complete numerical SDK.")
        cls.package = Path(package) / "inputs"
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name) / "dataset"
        BUILDER.build(cls.package / "source-inputs", cls.package / "source-results", cls.output)
        cls.index = json.loads((cls.output / "index.json").read_bytes())
        cls.state = json.loads(gzip.decompress((cls.output / "states/LA.json.gz").read_bytes()))
        cls.observations = json.loads(gzip.decompress(
            (cls.output / "observations.json.gz").read_bytes()))["records"]

    def test_inventory_and_state_controls(self):
        self.assertEqual(len(self.state["parishes"]), 64)
        self.assertEqual(len(self.observations), 1040)
        self.assertEqual(self.state["state_parent"]["votes"], 536190)
        self.assertEqual(self.state["state_parent"]["native_fields"]["INPER"], 448588)
        self.assertEqual(self.state["state_parent"]["native_fields"]["ABS"], 87602)
        self.assertEqual(self.state["state_parent"]["margin_residuals"]["sex"], 278)
        self.assertEqual(sum(row["margin_residuals"]["sex"] != 0
            for row in self.state["parishes"]), 37)

    def test_zeros_unknowns_and_native_abs_are_not_promoted(self):
        self.assertEqual(sum(value == 0 for row in [self.state["state_parent"], *self.state["parishes"]]
            for value in row["native_fields"].values()), 21)
        self.assertTrue(all(row["count"]["status"] == "reported" for row in self.observations))
        abs_rows = [row for row in self.observations if row["measure"]["literal"] == "ABS"]
        self.assertEqual(len(abs_rows), 65)
        self.assertTrue(all(row["measure"]["mode"] == "source_defined" for row in abs_rows))
        self.assertFalse(self.state["semantics"]["native_abs_is_mail_returned"])

    def test_compositions_use_own_votes_and_preserve_residual(self):
        for profile in [self.state["state_parent"], *self.state["parishes"]]:
            self.assertEqual(len(profile["groups"]), 7)
            self.assertTrue(all(group["denominator"] == "own_native_VOTES_not_registered_population"
                and group["turnout_rate"] is None for group in profile["groups"]))
            by_dimension = {}
            for group in profile["groups"]:
                by_dimension.setdefault(group["dimension"], 0)
                by_dimension[group["dimension"]] += group["count"]
            self.assertEqual(by_dimension["race"], profile["votes"])
            self.assertEqual(by_dimension["native_method"], profile["votes"])
            self.assertEqual(profile["votes"] - by_dimension["sex"], profile["margin_residuals"]["sex"])

    def test_bindings_use_the_shared_reader_alias_and_explicit_context(self):
        self.assertEqual(len({row["reference"]["feature_key"] for row in self.state["parishes"]}), 64)
        self.assertTrue(all(not row["reference"]["native_code_is_fips"]
            and row["reference"]["context_not_2026_voting_precinct"]
            for row in self.state["parishes"]))
        self.assertEqual(self.index["reference"]["features"], 64)
        self.assertEqual(self.index["reference"]["file"], "references/LA-context.json.gz")
        self.assertEqual(
            (self.output / self.index["reference"]["file"]).read_bytes(),
            (self.package / "source-inputs/LA-reference.geojson.gz").read_bytes())

    def test_catalog_candidate_remains_unpublishable_until_new_sdk_is_public(self):
        descriptor = json.loads((self.output / "dataset.json").read_bytes())
        self.assertEqual(descriptor["status"], "prepared_private_not_activated")
        self.assertFalse(descriptor["complete_download"]["published"])
        self.assertFalse(descriptor["complete_download"]["verified_anonymously"])
        self.assertIsNone(descriptor["complete_download"]["url"])

    def test_rejects_source_or_geometry_change(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "inputs"
            copied.mkdir()
            for path in (self.package / "source-inputs").iterdir():
                (copied / path.name).write_bytes(path.read_bytes())
            body = json.loads((copied / "source-native-facts.json").read_bytes())
            body["changed"] = True
            (copied / "source-native-facts.json").write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError, "Changed accepted input"):
                BUILDER.build(copied, self.package / "source-results", Path(directory) / "out")


if __name__ == "__main__":
    unittest.main()
