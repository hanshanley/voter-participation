import copy
import gzip
import json
import unittest

from scripts.native_layer_count_successor import compressed, inventory, refresh, unmatched_inventory
from scripts.participation_intake.contract import digest, encoded, observation_id, pin


class NativeLayerCountSuccessorTests(unittest.TestCase):
    geometry_sha = "2" * 64
    source_sha = "1" * 64
    election = dict(
        date=None,
        id="us-2026-general-previously-reviewed",
        qualification="previously_reviewed",
        type="general",
        year=2026,
    )
    measure = dict(
        id="previously-reviewed-participation-count",
        kind="participation_reported",
        literal="Reported ballots",
        mode="source_defined",
        unit="source_reported_count",
    )

    def count_row(self, unit_key, count, denominator, clock, qualified):
        source_id = "same-native-count-source"
        geography_id = "NM|" + unit_key
        rate = 100 * count / denominator if qualified else None
        row = dict(
            contract="participation.observation.v1",
            count=dict(literal=count, status="reported", value=count),
            denominator=dict(
                basis="eligible_voters_source_definition",
                literal="eligible_voters_source_definition",
                qualified=qualified,
                value=denominator,
            ),
            election=copy.deepcopy(self.election),
            geography=dict(
                id=geography_id,
                join=dict(evidence=None, feature_key=None, reference_id=None, status="unreviewed"),
                level="reporting_unit",
                name="PRECINCT " + unit_key,
                parent_id="NM|01",
                state_code="NM",
            ),
            measure=copy.deepcopy(self.measure),
            quality=dict(conflicts=[], notes=["Same-source reviewed count"]),
            reporting_status=dict(
                complete=None, literal=None, reported_units=None, total_units=None
            ),
            source=dict(
                classification="public_aggregate",
                fields=dict(
                    ballots=count,
                    denominator=denominator,
                    quality=["Same-source reviewed count"],
                    reported_pct=rate,
                    source_sha256=self.source_sha,
                    source_update_label=clock,
                    source_url="https://example.gov/NM",
                    unit_key=unit_key,
                ),
                id=source_id,
                input_sha256=self.source_sha,
                selector=dict(unit_key=unit_key),
                url="https://example.gov/NM",
            ),
            source_clock=dict(literal=clock, qualification="literal", timezone=None),
            view=dict(
                ballots=count,
                complete_download_url="https://example.gov/complete.zip",
                count_source_quality=["Same-source reviewed count"],
                denominator=denominator,
                geography_level="reporting_unit",
                native_record=dict(unit_key=unit_key),
                quality=["Same-source reviewed count"],
                reported_pct=rate,
                source_retrieved_at=None,
                source_sha256=self.source_sha,
                source_update_label=clock,
                source_url="https://example.gov/NM",
                state_code="NM",
                unit="PRECINCT " + unit_key,
                unit_key=unit_key,
                year=2026,
            ),
        )
        row["id"] = observation_id(
            source_id, self.election["id"], geography_id, self.measure["id"], "source_defined"
        )
        return row

    def native_row(self, old, native_key, source_key):
        observation = copy.deepcopy(old)
        observation["geography"] = dict(
            id="NM|native|" + native_key,
            join=dict(
                evidence="Existing approved source-key bridge",
                feature_key=native_key,
                reference_id=self.geometry_sha,
                status="approved",
            ),
            level="reporting_unit",
            name=old["geography"]["name"],
            parent_id="NM|native",
            state_code="NM",
        )
        observation["source"]["id"] = "accepted-native-layer"
        observation["source"]["input_sha256"] = self.geometry_sha
        observation["source"]["url"] = "https://example.gov/geometry"
        observation["view"]["unit_key"] = native_key
        observation["source"]["fields"]["unit_key"] = native_key
        observation["id"] = observation_id(
            observation["source"]["id"],
            observation["election"]["id"],
            observation["geography"]["id"],
            observation["measure"]["id"],
            observation["measure"]["mode"],
        )
        return dict(
            geometry_type="MultiPolygon",
            key=native_key,
            observation=observation,
            paths=dict(count=["ballots"], denominator=["denominator"], rate=["reported_pct"]),
            properties=dict(
                ballots=old["count"]["value"],
                denominator=old["denominator"]["value"],
                key=native_key,
                reported_pct=old["view"]["reported_pct"],
                source_update_label=old["source_clock"]["literal"],
                source_url=old["view"]["source_url"],
                unit_key=source_key,
            ),
        )

    def unknown_row(self):
        observation = self.count_row("unknown", 1, 2, "old", False)
        observation["count"] = dict(literal=None, status="unknown", value=None)
        observation["denominator"] = None
        observation["geography"]["join"]["status"] = "unmatched"
        observation["view"].update(
            ballots=None,
            denominator=None,
            reported_pct=None,
            source_update_label=None,
            source_url=None,
        )
        observation["source_clock"]["literal"] = None
        return dict(
            geometry_type="MultiPolygon",
            key="native-unknown",
            observation=observation,
            paths=dict(count=["ballots"], denominator=["denominator"], rate=["reported_pct"]),
            properties=dict(
                ballots=None,
                denominator=None,
                key="native-unknown",
                reported_pct=None,
                source_update_label=None,
                source_url=None,
                unit_key=None,
            ),
        )

    def fixture(self):
        old_qualified = self.count_row("01|1", 10, 20, "old clock", True)
        old_held = self.count_row("01|2", 5, 10, "old clock", True)
        new_qualified = self.count_row("01|1", 12, 24, "new clock", True)
        new_held = self.count_row("01|2", 6, 12, "new clock", True)
        native_held = self.native_row(old_held, "native-two", "01|2")
        native_held["observation"]["denominator"]["qualified"] = False
        native_held["observation"]["view"]["reported_pct"] = None
        native_held["observation"]["source"]["fields"]["reported_pct"] = None
        native_held["properties"]["reported_pct"] = None
        native_rows = [
            self.native_row(old_qualified, "native-one", "01|1"),
            native_held,
            self.unknown_row(),
        ]
        layer = dict(
            approval=dict(existing_qualification_retained=True, source_revision="c4"),
            contract="participation.native_bindings.v1",
            geometry=dict(file="geometry.json.gz", sha256=self.geometry_sha),
            id="precinct/NM",
            metadata=dict(boundary_label="unchanged"),
            rows=native_rows,
            state_code="NM",
        )
        layer_body = compressed(layer)
        geometry = b"unchanged geometry"
        native_index = dict(
            contract="participation.native_index.v1",
            layers={
                "precinct/NM": dict(
                    coverage=dict(
                        fractions=1, reported=2, source_rows=2, unknown=1, withheld=0
                    ),
                    features=3,
                    file="layer.json.gz",
                    geometry_sha256=self.geometry_sha,
                    **pin(layer_body),
                )
            },
            unrelated=dict(exact=True),
            year=2026,
        )
        native_files = dict(
            **{
                "geometry.json.gz": geometry,
                "index.json": encoded(native_index),
                "layer.json.gz": layer_body,
            }
        )
        native_description = dict(
            complete_download=dict(
                sha256="accepted", url="https://example.gov/accepted.zip",
                verified_anonymously=True),
            contract="participation.dataset.v1",
            files={name: pin(body) for name, body in native_files.items()},
            id="participation-native-bindings-2026",
            index=dict(file="index.json", **pin(native_files["index.json"])),
            record_contract="participation.native_bindings.v1",
            version=digest(
                encoded(
                    dict(
                        files={name: pin(body) for name, body in native_files.items()},
                        contract="participation.native_bindings.v1",
                    )
                )
            ),
        )
        count_state = dict(
            contract="participation.count_state.v1",
            records=[old_qualified, old_held],
            state_code="NM",
            views={},
            year=2026,
        )
        count_body = compressed(count_state)
        count_index = dict(states={"NM": dict(file="states/NM.json.gz")})
        count_files = {"states/NM.json.gz": count_body}
        new_rows = [new_qualified, new_held]
        pairs = []
        for native, old, new in zip(native_rows[:2], count_state["records"], new_rows):
            pairs.append(
                dict(
                    native_key=native["key"],
                    native_observation_id=native["observation"]["id"],
                    native_row=pin(encoded(native)),
                    new_count_id=new["id"],
                    new_count_row=pin(encoded(new)),
                    old_count_id=old["id"],
                    old_count_row=pin(encoded(old)),
                    unit_key=native["properties"]["unit_key"],
                )
            )
        review = dict(
            baseline_count_shard=pin(count_body),
            baseline_native_index=pin(native_files["index.json"]),
            baseline_native_layer=pin(layer_body),
            complete_inventory_review_evidence="Synthetic complete source-key bridge review",
            contract="participation.reviewed_native_layer_count_successor.v1",
            expected_changes=dict(
                bound_rows=2,
                count_changes=2,
                qualified_after=1,
                qualified_before=1,
                registration_changes=2,
                source_clock_changes=2,
                unmatched_rows=1,
                withdrawals=0,
            ),
            layer_id="precinct/NM",
            pairs=pairs,
            source_clock="new clock",
            source_input_sha256=self.source_sha,
            source_inventory=dict(rows=2, inventory=pin(encoded(inventory(new_rows)))),
            state_code="NM",
            unmatched_inventory=dict(
                rows=1, inventory=pin(encoded(unmatched_inventory(native_rows[2:])))
            ),
        )
        source = dict(
            native_layer_successor=review,
            rows=new_rows,
            spec=dict(geography=dict(state_code="NM")),
        )
        return (
            native_description,
            native_files,
            native_index,
            count_files,
            count_index,
            source,
            layer,
        )

    def update_new_review(self, source):
        review = source["native_layer_successor"]
        rows = source["rows"]
        review["source_inventory"] = dict(
            rows=len(rows), inventory=pin(encoded(inventory(rows)))
        )
        by_id = {row["id"]: row for row in rows}
        for pair in review["pairs"]:
            pair["new_count_row"] = pin(encoded(by_id[pair["new_count_id"]]))

    def add_primary_source_url_bridge(self, source):
        review = source["native_layer_successor"]
        new_sha = "3" * 64
        native_url = "https://example.gov/NM"
        new_primary_url = "https://example.gov/current-counts.json"
        for row in source["rows"]:
            row["source"]["url"] = new_primary_url
            row["source"]["input_sha256"] = new_sha
            row["source"]["fields"]["source_sha256"] = new_sha
            row["view"]["source_sha256"] = new_sha
        review["source_input_sha256"] = new_sha
        self.update_new_review(source)
        review["primary_source_url_bridge"] = {
            "classification": "public_aggregate",
            "full_review_inventory_pin": copy.deepcopy(
                review["source_inventory"]["inventory"]
            ),
            "native_product_url": native_url,
            "new_input_sha256": new_sha,
            "new_primary_url": new_primary_url,
            "old_input_sha256": self.source_sha,
            "old_primary_url": native_url,
            "reason": "artifact_wrapper_to_underlying_official_product",
            "source_id": "same-native-count-source",
        }

    def rebind_layer(self, files, index, baseline_files, baseline_index, source, layer):
        body = compressed(layer)
        for target_files, target_index in (
            (files, index),
            (baseline_files, baseline_index),
        ):
            target_files["layer.json.gz"] = body
            target_index["layers"]["precinct/NM"].update(pin(body))
            target_files["index.json"] = encoded(target_index)
        review = source["native_layer_successor"]
        review["baseline_native_layer"] = pin(body)
        review["baseline_native_index"] = pin(baseline_files["index.json"])
        by_key = {row["key"]: row for row in layer["rows"]}
        for pair in review["pairs"]:
            pair["native_row"] = pin(encoded(by_key[pair["native_key"]]))
        unmatched = [
            row for row in layer["rows"] if row["properties"].get("unit_key") is None
        ]
        review["unmatched_inventory"] = dict(
            rows=len(unmatched), inventory=pin(encoded(unmatched_inventory(unmatched)))
        )

    def run_fixture(self, change=None):
        description, files, index, count_files, count_index, source, layer = self.fixture()
        baseline_files = copy.deepcopy(files)
        baseline_index = copy.deepcopy(index)
        review = source["native_layer_successor"]
        if change == "index":
            review["baseline_native_index"]["sha256"] = "0" * 64
        elif change == "layer":
            review["baseline_native_layer"]["sha256"] = "0" * 64
        elif change == "count":
            review["baseline_count_shard"]["sha256"] = "0" * 64
        elif change == "source_inventory":
            review["source_inventory"]["rows"] = 1
        elif change == "pair":
            review["pairs"][0]["new_count_row"]["sha256"] = "0" * 64
        elif change == "candidate_declaration":
            index["layers"]["precinct/NM"]["coverage"]["reported"] = 1
            files["index.json"] = encoded(index)
        elif change == "bridge":
            first, second = layer["rows"][:2]
            first["properties"]["unit_key"], second["properties"]["unit_key"] = (
                second["properties"]["unit_key"],
                first["properties"]["unit_key"],
            )
            review["pairs"][0]["unit_key"] = first["properties"]["unit_key"]
            review["pairs"][1]["unit_key"] = second["properties"]["unit_key"]
            self.rebind_layer(
                files, index, baseline_files, baseline_index, source, layer
            )
        elif change == "unmatched":
            layer["rows"][2]["properties"]["ballots"] = 0
            self.rebind_layer(
                files, index, baseline_files, baseline_index, source, layer
            )
        elif change == "paths":
            layer["rows"][0]["paths"]["count"] = ["unsupported"]
            self.rebind_layer(
                files, index, baseline_files, baseline_index, source, layer
            )
        elif change == "geometry":
            files["geometry.json.gz"] = b"changed geometry"
        elif change == "source":
            for row in source["rows"]:
                row["source"]["url"] = "https://different.example/NM"
                row["view"]["source_url"] = "https://different.example/NM"
                row["source"]["fields"]["source_url"] = "https://different.example/NM"
            self.update_new_review(source)
        elif change in (
            "bridge_success",
            "bridge_wrong_url",
            "bridge_wrong_native_url",
            "bridge_wrong_old_input_sha",
            "bridge_wrong_new_input_sha",
            "bridge_wrong_inventory_pin",
            "bridge_absent",
            "bridge_changed_source_id",
        ):
            self.add_primary_source_url_bridge(source)
            bridge = review["primary_source_url_bridge"]
            if change == "bridge_wrong_url":
                for row in source["rows"]:
                    row["source"]["url"] = "https://wrong.example/current.json"
                self.update_new_review(source)
                bridge["full_review_inventory_pin"] = copy.deepcopy(
                    review["source_inventory"]["inventory"]
                )
            elif change == "bridge_wrong_native_url":
                source["rows"][0]["view"]["source_url"] = "https://wrong.example/product"
                source["rows"][0]["source"]["fields"]["source_url"] = (
                    "https://wrong.example/product"
                )
                self.update_new_review(source)
                bridge["full_review_inventory_pin"] = copy.deepcopy(
                    review["source_inventory"]["inventory"]
                )
            elif change == "bridge_wrong_old_input_sha":
                bridge["old_input_sha256"] = "4" * 64
            elif change == "bridge_wrong_new_input_sha":
                bridge["new_input_sha256"] = "4" * 64
            elif change == "bridge_wrong_inventory_pin":
                bridge["full_review_inventory_pin"]["sha256"] = "4" * 64
            elif change == "bridge_absent":
                del review["primary_source_url_bridge"]
            elif change == "bridge_changed_source_id":
                bridge["source_id"] = "different-count-source"
        elif change == "frame":
            row = source["rows"][0]
            row["denominator"]["basis"] = "different_frame"
            row["denominator"]["literal"] = "different_frame"
            row["view"]["denominator_basis"] = "different_frame"
            row["source"]["fields"]["denominator_basis"] = "different_frame"
            self.update_new_review(source)
        elif change == "unknown":
            row = source["rows"][0]
            row["count"] = dict(literal=None, status="unknown", value=None)
            row["denominator"]["qualified"] = False
            row["view"].update(ballots=None, reported_pct=None)
            row["source"]["fields"].update(
                ballots=None, reported_pct=None
            )
            self.update_new_review(source)
        elif change == "true_zero":
            row = source["rows"][0]
            row["count"] = dict(literal=0, status="reported", value=0)
            row["view"].update(ballots=0, reported_pct=0.0)
            row["source"]["fields"].update(ballots=0, reported_pct=0.0)
            self.update_new_review(source)
        elif change in ("withdrawal", "unqualified"):
            row = source["rows"][0]
            if change == "withdrawal":
                row["count"] = dict(literal=0, status="reported", value=0)
                row["denominator"]["value"] = 0
                row["denominator"]["qualified"] = False
                row["view"].update(ballots=0, denominator=0, reported_pct=None)
                row["source"]["fields"].update(
                    ballots=0, denominator=0, reported_pct=None
                )
            else:
                row["denominator"]["qualified"] = False
            review["expected_changes"].update(
                qualified_after=0, withdrawals=1
            )
            self.update_new_review(source)
        elif change == "bool_rate":
            row = source["rows"][0]
            row["view"]["reported_pct"] = True
            row["source"]["fields"]["reported_pct"] = True
            self.update_new_review(source)
        return refresh(
            description,
            files,
            index,
            description,
            baseline_files,
            baseline_index,
            dict(index=dict(file="index.json")),
            count_files,
            count_index,
            [source],
        )

    def test_refreshes_only_bound_count_mirrors_and_retains_rate_masks(self):
        description, files, changed = self.run_fixture()
        self.assertEqual(changed, 2)
        index = json.loads(files["index.json"])
        layer = json.loads(gzip.decompress(files["layer.json.gz"]))
        one, two, unknown = layer["rows"]
        old_source = self.fixture()[-1]["rows"][0]["observation"]["source"]
        self.assertEqual(one["properties"]["unit_key"], "01|1")
        self.assertEqual(one["observation"]["view"]["unit_key"], "native-one")
        self.assertEqual(one["observation"]["source"], old_source)
        self.assertEqual(
            (one["properties"]["ballots"], one["properties"]["denominator"],
             one["properties"]["source_update_label"], one["properties"]["reported_pct"]),
            (12, 24, "new clock", 50.0),
        )
        self.assertEqual(
            (two["properties"]["ballots"], two["properties"]["denominator"],
             two["properties"]["source_update_label"], two["properties"]["reported_pct"]),
            (6, 12, "new clock", None),
        )
        self.assertFalse(two["observation"]["denominator"]["qualified"])
        self.assertIsNone(two["observation"]["view"]["reported_pct"])
        self.assertEqual(
            unknown,
            self.fixture()[-1]["rows"][2],
            "Unmatched geometry/count rows must remain exact",
        )
        self.assertEqual(files["geometry.json.gz"], b"unchanged geometry")
        self.assertEqual(index["unrelated"], dict(exact=True))
        declaration = index["layers"]["precinct/NM"]
        self.assertEqual(declaration["coverage"]["fractions"], 1)
        self.assertEqual(declaration["coverage"]["unknown"], 1)
        self.assertEqual(declaration["count_successor"]["source_clock"], "new clock")
        self.assertEqual(
            declaration["count_successor"]["source_inventory"],
            one["count_successor"]["source_inventory"],
        )
        self.assertEqual(one["count_successor"]["source_id"], "same-native-count-source")
        self.assertEqual(one["count_successor"]["input_sha256"], self.source_sha)
        self.assertEqual(one["count_successor"]["canonical_row"]["id"],
                         self.fixture()[5]["rows"][0]["id"])
        self.assertNotEqual(description["version"], self.fixture()[0]["version"])

    def test_true_zero_remains_reported_and_qualified(self):
        _, files, _ = self.run_fixture("true_zero")
        index = json.loads(files["index.json"])
        row = json.loads(gzip.decompress(files["layer.json.gz"]))["rows"][0]
        self.assertEqual(row["observation"]["count"],
                         dict(literal=0, status="reported", value=0))
        self.assertTrue(row["observation"]["denominator"]["qualified"])
        self.assertEqual(row["properties"]["reported_pct"], 0.0)
        self.assertEqual(index["layers"]["precinct/NM"]["coverage"]["reported"], 2)

    def test_explicit_primary_source_url_bridge_records_lineage_and_authority(self):
        _, files, _ = self.run_fixture("bridge_success")
        index = json.loads(files["index.json"])
        row = json.loads(gzip.decompress(files["layer.json.gz"]))["rows"][0]
        successor = row["count_successor"]
        declaration = index["layers"]["precinct/NM"]["count_successor"]
        bridge = successor["primary_source_url_bridge"]
        self.assertEqual(
            bridge,
            declaration["primary_source_url_bridge"],
        )
        self.assertEqual(
            successor["current_count_source"]["url"],
            bridge["new_primary_url"],
        )
        self.assertEqual(
            successor["current_count_source"]["native_product_url"],
            bridge["native_product_url"],
        )
        self.assertEqual(
            successor["authority"]["historical_pre_successor_facts_retained"],
            ["observation.source.fields"],
        )
        self.assertEqual(
            successor["authority"]["current_authoritative_mirrors"],
            [
                "observation.count",
                "observation.view",
                "properties",
                "count_successor.facts",
            ],
        )
        self.assertEqual(
            row["observation"]["source"],
            self.fixture()[-1]["rows"][0]["observation"]["source"],
        )

    def test_primary_source_url_bridge_rejects_any_unreviewed_lineage_change(self):
        failures = (
            "bridge_wrong_url",
            "bridge_wrong_native_url",
            "bridge_wrong_old_input_sha",
            "bridge_wrong_new_input_sha",
            "bridge_wrong_inventory_pin",
            "bridge_absent",
            "bridge_changed_source_id",
        )
        for change in failures:
            with self.subTest(change=change), self.assertRaisesRegex(
                    ValueError,
                    "Same-source or denominator-frame|primary source URL bridge"):
                self.run_fixture(change)

    def test_withdraws_invalid_or_newly_unqualified_rates_without_promotion(self):
        for change in ("withdrawal", "unqualified"):
            with self.subTest(change=change):
                _, files, _ = self.run_fixture(change)
                index = json.loads(files["index.json"])
                row = json.loads(gzip.decompress(files["layer.json.gz"]))["rows"][0]
                self.assertFalse(row["observation"]["denominator"]["qualified"])
                self.assertIsNone(row["properties"]["reported_pct"])
                self.assertEqual(
                    index["layers"]["precinct/NM"]["coverage"]["fractions"], 0
                )

    def test_reaches_specific_layout_bridge_unknown_source_frame_and_status_guards(self):
        failures = {
            "candidate_declaration": "layer declaration",
            "bridge": "source-key bridge",
            "unmatched": "Unmatched native geometry",
            "paths": "flat native count layout",
            "source": "Same-source or denominator-frame",
            "frame": "Same-source or denominator-frame",
            "unknown": "reported integer counts",
            "bool_rate": "qualified fraction",
            "geometry": "geometry bytes",
        }
        for change, message in failures.items():
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                self.run_fixture(change)

    def test_rejects_changed_preimage_inventory_and_pair_pins(self):
        for change in ("index", "layer", "count", "source_inventory", "pair"):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_fixture(change)


if __name__ == "__main__":
    unittest.main()
