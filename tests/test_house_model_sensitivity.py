import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.house_model_sensitivity import FAMILIES, PROFILES, STATES, build, summarize


def fixture():
    models = {}
    for profile_index, profile in enumerate(PROFILES):
        families = {}
        for family_index, family in enumerate(FAMILIES):
            value = 1+3*profile_index+family_index
            contributions = dict(switching=value, entry=2, exit=-1, other_choice=3-value, unresolved=0)
            rows = []
            for code in sorted(STATES):
                group = dict(dimension="AGE6", group="example", available=True,
                    contributions_pp=contributions, net_participation_pp=1,
                    total_contribution_pp=4, gross_outcomes=dict(retaining=.8+.001*(value-1)))
                rows.append(dict(state_code=code, source_comparison_available=code != "TX",
                    reported_comparison=dict(current_snapshot="frozen-source-version",
                        reason="Incompatible source endpoints" if code == "TX" else None),
                    point=dict(contributions_pp=contributions, net_participation_pp=1,
                        total_change_pp=4),
                    gross_outcomes=dict(retaining=.8+.001*(value-1)),
                    groups=[group, dict(dimension="AGE6", group="held", available=False,
                        reason="Suppressed source group")]))
            families[family] = dict(rows=rows, model_units_are_people=False,
                current_party_totals_used_in_source_model_training=False)
        models[profile] = dict(contract="participation.house_model_families.v1", families=families)
    return models


class HouseSensitivityTests(unittest.TestCase):
    def test_compressed_publication_retains_every_numeric_and_held_witness(self):
        models = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = {}
            for profile in PROFILES:
                body = json.dumps(models[profile]).encode()
                name = "viewer-"+profile+".json"
                (root/name).write_bytes(body)
                metadata[profile] = dict(file=name, bytes=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                    url="https://raw.githubusercontent.com/hanshanley/voter-participation/"
                        +"a"*40+"/data/house-official-source-update/test-01/"+name)
            (root/"inputs.json").write_text(json.dumps(metadata))
            build(root, root/"output")
            output = root/"output"
            self.assertEqual(gzip.decompress((output/"sensitivity.json.gz").read_bytes()),
                (output/"sensitivity.json").read_bytes())
            with (output/"complete-nine-variant-query.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 50*3*8*9)
            self.assertTrue(all(row["value_json"] == "null" for row in rows
                if row["state_code"] == "TX"))

    def test_ranges_preserve_units_defaults_and_every_held_decision(self):
        result, witness = summarize(fixture(), {profile: {} for profile in PROFILES})
        ar = next(row for row in result["rows"] if row["state_code"] == "AR")
        tx = next(row for row in result["rows"] if row["state_code"] == "TX")
        self.assertEqual(ar["scopes"][""]["metrics"]["switching"],
            dict(minimum=1, maximum=9, default=1, variants=9))
        self.assertEqual(ar["scopes"]["AGE6|example"]["metrics"]["retaining"]["minimum"], .8)
        self.assertEqual(ar["scopes"]["AGE6|example"]["metrics"]["retaining"]["maximum"], .808)
        self.assertFalse(ar["scopes"]["AGE6|held"]["available"])
        self.assertTrue(all(value is None for value in ar["scopes"]["AGE6|held"]["metrics"].values()))
        self.assertFalse(tx["qualified"])
        self.assertTrue(all(value is None for scope in tx["scopes"].values()
            for value in scope["metrics"].values()))
        self.assertEqual(len(witness), 50*3*8*9)
        self.assertTrue(all(row["value_json"] == "null" and not row["available"]
            for row in witness if row["state_code"] == "TX"))

    def test_incompatible_endpoints_or_qualification_cannot_form_a_spread(self):
        for change in (
            lambda row: row["reported_comparison"].update(current_snapshot="different"),
            lambda row: row.update(source_comparison_available=False),
        ):
            models = fixture()
            row = models["full"]["families"][FAMILIES[1]]["rows"][0]
            change(row)
            with self.assertRaisesRegex(ValueError, "endpoints"):
                summarize(models, {profile: {} for profile in PROFILES})

    def test_changed_disclosure_masks_cannot_recover_suppressed_groups(self):
        models = fixture()
        models["full"]["families"][FAMILIES[1]]["rows"][0]["groups"][1]["available"] = True
        with self.assertRaisesRegex(ValueError, "disclosure masks"):
            summarize(models, {profile: {} for profile in PROFILES})

    def test_missing_metric_is_null_without_erasing_other_supported_metrics(self):
        models = fixture()
        models["full"]["families"][FAMILIES[1]]["rows"][0]["gross_outcomes"]["retaining"] = None
        result, _ = summarize(models, {profile: {} for profile in PROFILES})
        row = result["rows"][0]
        self.assertIsNone(row["scopes"][""]["metrics"]["retaining"])
        self.assertIsNotNone(row["scopes"][""]["metrics"]["switching"])

    def test_missing_contribution_does_not_create_a_zero_width_summary(self):
        models = fixture()
        row = models["full"]["families"][FAMILIES[1]]["rows"][0]
        row["point"]["contributions_pp"] = dict(row["point"]["contributions_pp"], switching=None)
        result, _ = summarize(models, {profile: {} for profile in PROFILES})
        self.assertIsNone(result["rows"][0]["scopes"][""]["metrics"]["switching"])
        summary = result["summary"]["statewide_spread_margin_pp"]["switching"]
        self.assertEqual(summary["states_with_complete_variants"], 48)
        self.assertEqual(summary["median"], 8)
        self.assertEqual(result["summary"]["qualified_states"], 49)

    def test_all_held_is_not_a_zero_width_uncertainty_claim(self):
        models = fixture()
        for profile in models.values():
            for model in profile["families"].values():
                for row in model["rows"]:
                    row["source_comparison_available"] = False
        result, witness = summarize(models, {profile: {} for profile in PROFILES})
        self.assertEqual(result["summary"]["qualified_states"], 0)
        self.assertIsNone(result["summary"]["statewide_spread_margin_pp"]["switching"]["median"])
        self.assertTrue(all(row["value_json"] == "null" for row in witness))


if __name__ == "__main__":
    unittest.main()
