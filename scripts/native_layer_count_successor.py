"""Refresh counts on already-bound native geometry without creating new joins."""

import copy
import gzip
import json
import math

from scripts.participation_intake.contract import IntakeError, digest, encoded, pin, validate_all


CONTRACT = "participation.reviewed_native_layer_count_successor.v1"
REVIEW_KEYS = {
    "baseline_count_shard",
    "baseline_native_index",
    "baseline_native_layer",
    "complete_inventory_review_evidence",
    "contract",
    "expected_changes",
    "layer_id",
    "pairs",
    "source_clock",
    "source_input_sha256",
    "source_inventory",
    "state_code",
    "unmatched_inventory",
}
BRIDGE_KEY = "primary_source_url_bridge"
BRIDGE_KEYS = {
    "classification",
    "full_review_inventory_pin",
    "native_product_url",
    "new_input_sha256",
    "new_primary_url",
    "old_input_sha256",
    "old_primary_url",
    "reason",
    "source_id",
}
BRIDGE_REASON = "artifact_wrapper_to_underlying_official_product"
AUTHORITY_LABELS = {
    "current_authoritative_mirrors": [
        "observation.count",
        "observation.view",
        "properties",
        "count_successor.facts",
    ],
    "historical_pre_successor_facts_retained": [
        "observation.source.fields",
    ],
}
PAIR_KEYS = {
    "native_key",
    "native_observation_id",
    "native_row",
    "new_count_id",
    "new_count_row",
    "old_count_id",
    "old_count_row",
    "unit_key",
}
FLAT_PATHS = {
    "count": ["ballots"],
    "denominator": ["denominator"],
    "rate": ["reported_pct"],
}
FRAME_FIELDS = (
    "cast_ballot_count_qualified",
    "denominator_basis",
    "registration_frame_qualified",
    "source_count_qualified",
    "unique_voter_count_qualified",
)


def compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=9, mtime=0))
    body[9] = 3
    return bytes(body)


def inventory(rows):
    return [
        dict(id=row["id"], pin=pin(encoded(row)), unit_key=row["view"].get("unit_key"))
        for row in sorted(rows, key=lambda item: (str(item["view"].get("unit_key")), item["id"]))
    ]


def unmatched_inventory(rows):
    return [
        dict(key=row["key"], pin=pin(encoded(row)))
        for row in sorted(rows, key=lambda item: item["key"])
    ]


def mirror(row, new, qualified, source_inventory, bridge):
    count = new["count"]["value"]
    denominator = copy.deepcopy(new["denominator"])
    if denominator is not None:
        denominator["qualified"] = qualified
    rate = new["view"].get("reported_pct") if qualified else None
    if qualified:
        value = denominator["value"]
        if (type(count) is not int or type(value) is not int or value <= 0 or count > value
                or type(rate) not in (int, float) or not math.isfinite(rate)
                or not 0 <= rate <= 100
                or abs(rate - 100 * count / value) > 1e-12):
            raise IntakeError("native_layer_scope", "A retained qualified fraction no longer reconciles")
    observation = row["observation"]
    geometry_source = copy.deepcopy(observation["source"])
    observation["count"] = copy.deepcopy(new["count"])
    observation["denominator"] = denominator
    observation["source_clock"] = copy.deepcopy(new["source_clock"])
    view = observation["view"]
    view["ballots"] = count
    view["denominator"] = denominator["value"] if denominator else None
    view["reported_pct"] = rate
    view["source_update_label"] = new["source_clock"]["literal"]
    properties = row["properties"]
    properties["ballots"] = count
    properties["denominator"] = denominator["value"] if denominator else None
    properties["reported_pct"] = rate
    properties["source_update_label"] = new["source_clock"]["literal"]
    row["count_successor"] = {
        "authority": copy.deepcopy(AUTHORITY_LABELS),
        "canonical_row": {"id": new["id"], "pin": pin(encoded(new))},
        "classification": new["source"]["classification"],
        "contract": CONTRACT,
        "current_count_source": {
            "classification": new["source"]["classification"],
            "id": new["source"]["id"],
            "input_sha256": new["source"]["input_sha256"],
            "native_product_url": new["view"]["source_url"],
            "selector": copy.deepcopy(new["source"]["selector"]),
            "url": new["source"]["url"],
        },
        "facts": {
            "ballots": count,
            "denominator": denominator["value"] if denominator else None,
            "reported_pct": rate,
            "source_clock": new["source_clock"]["literal"],
        },
        "input_sha256": new["source"]["input_sha256"],
        "selector": copy.deepcopy(new["source"]["selector"]),
        "source_id": new["source"]["id"],
        "source_inventory": copy.deepcopy(source_inventory),
        "url": new["source"]["url"],
    }
    if bridge is not None:
        row["count_successor"][BRIDGE_KEY] = copy.deepcopy(bridge)
    if observation["source"] != geometry_source:
        raise IntakeError("native_layer_scope", "Native observation source must retain geometry lineage")
    validate_all([observation])


def refresh(description, files, index, baseline_description, baseline_files, baseline_index,
            count_description, count_files, count_index, sources):
    if not sources:
        return description, files, 0
    updated = copy.deepcopy(index)
    result = dict(files)
    changed = 0
    seen = set()
    for source in sources:
        review = source.get("native_layer_successor")
        review_keys = set(review) if isinstance(review, dict) else set()
        if (not isinstance(review, dict)
                or review_keys not in (REVIEW_KEYS, REVIEW_KEYS | {BRIDGE_KEY})
                or review["contract"] != CONTRACT
                or not review["complete_inventory_review_evidence"].strip()
                or review["state_code"] != source["spec"]["geography"]["state_code"]
                or review["layer_id"] in seen):
            raise IntakeError("native_layer_scope", "A unique complete reviewed native layer successor is required")
        seen.add(review["layer_id"])
        if review["baseline_native_index"] != pin(
                baseline_files[baseline_description["index"]["file"]]):
            raise IntakeError("native_layer_scope", "The reviewed native index preimage changed")
        layer_id = review["layer_id"]
        baseline_declaration = baseline_index["layers"].get(layer_id)
        candidate_declaration = updated["layers"].get(layer_id)
        if (not baseline_declaration or not candidate_declaration
                or candidate_declaration != baseline_declaration):
            raise IntakeError("native_layer_scope", "The reviewed native layer declaration changed")
        filename = baseline_declaration["file"]
        baseline_body = baseline_files[filename]
        if (review["baseline_native_layer"] != pin(baseline_body)
                or result[filename] != baseline_body):
            raise IntakeError("native_layer_scope", "The complete native layer preimage changed")
        code = review["state_code"]
        count_declaration = count_index["states"].get(code)
        if (not count_declaration
                or review["baseline_count_shard"] != pin(count_files[count_declaration["file"]])):
            raise IntakeError("native_layer_scope", "The complete count-shard preimage changed")
        count_state = json.loads(gzip.decompress(count_files[count_declaration["file"]]))
        if count_state["state_code"] != code:
            raise IntakeError("native_layer_scope", "The reviewed count shard changed jurisdiction")
        old_by_id = {row["id"]: row for row in count_state["records"]}
        if len(old_by_id) != len(count_state["records"]):
            raise IntakeError("native_layer_scope", "The count baseline has duplicate observations")
        new_rows = [row for row in source["rows"]
                    if row["geography"]["state_code"] == code
                    and row["geography"]["level"] == "reporting_unit"]
        validate_all(new_rows)
        new_by_id = {row["id"]: row for row in new_rows}
        new_keys = [row["view"].get("unit_key") for row in new_rows]
        expected_source = review["source_inventory"]
        if (set(expected_source) != {"rows", "inventory"}
                or expected_source["rows"] != len(new_rows)
                or len(new_by_id) != len(new_rows)
                or None in new_keys or len(set(new_keys)) != len(new_keys)
                or expected_source["inventory"] != pin(encoded(inventory(new_rows)))):
            raise IntakeError("native_layer_scope", "The complete new source-row inventory changed")
        bridge = review.get(BRIDGE_KEY)
        if bridge is not None:
            if (not isinstance(bridge, dict) or set(bridge) != BRIDGE_KEYS
                    or any(not isinstance(bridge[key], str) or not bridge[key].strip()
                           for key in BRIDGE_KEYS - {"full_review_inventory_pin"})
                    or not isinstance(bridge["full_review_inventory_pin"], dict)
                    or bridge["full_review_inventory_pin"]
                        != review["source_inventory"]["inventory"]
                    or bridge["reason"] != BRIDGE_REASON
                    or bridge["old_primary_url"] == bridge["new_primary_url"]):
                raise IntakeError(
                    "native_layer_scope",
                    "A primary source URL bridge requires exact reviewed lineage roles",
                )
        source_ids = {row["source"]["id"] for row in new_rows}
        source_urls = {row["source"]["url"] for row in new_rows}
        source_classes = {row["source"]["classification"] for row in new_rows}
        if (len(source_ids) != 1 or len(source_urls) != 1 or len(source_classes) != 1
                or {row["source_clock"]["literal"] for row in new_rows}
                    != {review["source_clock"]}
                or {row["source"]["input_sha256"] for row in new_rows}
                    != {review["source_input_sha256"]}):
            raise IntakeError("native_layer_scope", "The reviewed source clock or input hash changed")

        layer = json.loads(gzip.decompress(baseline_body))
        if (layer["contract"] != "participation.native_bindings.v1"
                or layer["state_code"] != code or layer["id"] != layer_id
                or layer["geometry"]["sha256"] != baseline_declaration["geometry_sha256"]
                or layer["approval"].get("existing_qualification_retained") is not True):
            raise IntakeError("native_layer_scope", "Native geometry or prior approval changed")
        geometry_file = layer["geometry"]["file"]
        if (geometry_file not in baseline_files or geometry_file not in result
                or result[geometry_file] != baseline_files[geometry_file]):
            raise IntakeError("native_layer_scope", "Native geometry bytes changed")
        native_by_key = {row["key"]: row for row in layer["rows"]}
        if len(native_by_key) != len(layer["rows"]):
            raise IntakeError("native_layer_scope", "Native geometry keys are not unique")
        if any(row.get("paths") != FLAT_PATHS for row in layer["rows"]):
            raise IntakeError("native_layer_scope", "Only the reviewed flat native count layout is supported")
        pairs = review["pairs"]
        if (not isinstance(pairs, list) or not pairs
                or any(not isinstance(item, dict) or set(item) != PAIR_KEYS for item in pairs)
                or len({item["native_key"] for item in pairs}) != len(pairs)
                or len({item["unit_key"] for item in pairs}) != len(pairs)):
            raise IntakeError("native_layer_scope", "Reviewed native/count pairs are incomplete or duplicated")
        pair_native_keys = {item["native_key"] for item in pairs}
        pair_unit_keys = {item["unit_key"] for item in pairs}
        bound = [row for row in layer["rows"] if row["properties"].get("unit_key") is not None]
        unmatched = [row for row in layer["rows"] if row["properties"].get("unit_key") is None]
        expected_unmatched = review["unmatched_inventory"]
        if (set(expected_unmatched) != {"rows", "inventory"}
                or expected_unmatched["rows"] != len(unmatched)
                or expected_unmatched["inventory"] != pin(encoded(unmatched_inventory(unmatched)))
                or {row["key"] for row in bound} != pair_native_keys
                or {row["properties"]["unit_key"] for row in bound} != pair_unit_keys):
            raise IntakeError("native_layer_scope", "Bound and unmatched native inventories changed")
        for row in unmatched:
            observation, properties = row["observation"], row["properties"]
            if (observation["count"] != dict(literal=None, status="unknown", value=None)
                    or observation["denominator"] is not None
                    or observation["view"].get("reported_pct") is not None
                    or properties.get("ballots") is not None
                    or properties.get("denominator") is not None
                    or properties.get("reported_pct") is not None
                    or observation["geography"]["join"]["status"] != "unmatched"):
                raise IntakeError("native_layer_scope", "Unmatched native geometry cannot acquire count facts")

        output = copy.deepcopy(layer)
        output_by_key = {row["key"]: row for row in output["rows"]}
        count_changes = registration_changes = clock_changes = withdrawals = 0
        qualified_before = qualified_after = 0
        for pair in pairs:
            native = native_by_key.get(pair["native_key"])
            old = old_by_id.get(pair["old_count_id"])
            new = new_by_id.get(pair["new_count_id"])
            if (native is None or old is None or new is None
                    or pair["native_observation_id"] != native["observation"]["id"]
                    or pair["native_row"] != pin(encoded(native))
                    or pair["old_count_row"] != pin(encoded(old))
                    or pair["new_count_row"] != pin(encoded(new))):
                raise IntakeError("native_layer_scope", "A reviewed native/count pair changed")
            properties, observation = native["properties"], native["observation"]
            if (properties["unit_key"] != pair["unit_key"]
                    or old["view"].get("unit_key") != pair["unit_key"]
                    or new["view"].get("unit_key") != pair["unit_key"]
                    or old["election"] != new["election"]
                    or old["geography"] != new["geography"]
                    or old["measure"] != new["measure"]
                    or observation["geography"]["join"]["status"] != "approved"
                    or observation["geography"]["join"]["feature_key"] != native["key"]
                    or observation["geography"]["join"]["reference_id"]
                        != layer["geometry"]["sha256"]):
                raise IntakeError("native_layer_scope", "The reviewed source-key bridge or geometry approval changed")
            old_denominator_role = {
                key: (old["denominator"] or {}).get(key)
                for key in ("basis", "literal")
            }
            new_denominator_role = {
                key: (new["denominator"] or {}).get(key)
                for key in ("basis", "literal")
            }
            if bridge is None:
                primary_source_roles_match = (
                    old["source"]["url"] == new["source"]["url"]
                )
            else:
                primary_source_roles_match = (
                    old["source"]["url"] == bridge["old_primary_url"]
                    and new["source"]["url"] == bridge["new_primary_url"]
                    and old["source"]["input_sha256"] == bridge["old_input_sha256"]
                    and new["source"]["input_sha256"] == bridge["new_input_sha256"]
                    and old["source"]["id"] == bridge["source_id"]
                    and new["source"]["id"] == bridge["source_id"]
                    and old["source"]["classification"] == bridge["classification"]
                    and new["source"]["classification"] == bridge["classification"]
                    and old["view"].get("source_url") == bridge["native_product_url"]
                    and new["view"].get("source_url") == bridge["native_product_url"]
                    and old["source"]["fields"].get("source_url")
                        == bridge["native_product_url"]
                    and new["source"]["fields"].get("source_url")
                        == bridge["native_product_url"]
                )
            if (old["source"]["id"] != new["source"]["id"]
                    or not primary_source_roles_match
                    or old["source"]["classification"] != new["source"]["classification"]
                    or old_denominator_role != new_denominator_role
                    or any(old["view"].get(name) != new["view"].get(name)
                           for name in FRAME_FIELDS)
                    or any(old["source"]["fields"].get(name)
                           != new["source"]["fields"].get(name)
                           for name in FRAME_FIELDS)):
                raise IntakeError("native_layer_scope", "Same-source or denominator-frame roles changed")
            if (new["count"]["status"] != "reported"
                    or type(new["count"]["value"]) is not int
                    or new["count"]["value"] < 0
                    or new["count"]["literal"] != new["count"]["value"]
                    or not isinstance(new["denominator"], dict)
                    or type(new["denominator"]["value"]) is not int
                    or new["denominator"]["value"] < 0):
                raise IntakeError("native_layer_scope", "Bound native successors require reported integer counts")
            old_count = old["count"]["value"]
            old_denominator = (old["denominator"] or {}).get("value")
            old_clock = old["source_clock"]["literal"]
            old_qualified = bool(
                observation["denominator"] and observation["denominator"]["qualified"]
            )
            old_rate = old["view"].get("reported_pct") if old_qualified else None
            qualified_before += old_qualified
            if (observation["count"] != old["count"]
                    or (observation["denominator"] or {}).get("value") != old_denominator
                    or {key: (observation["denominator"] or {}).get(key)
                        for key in ("basis", "literal")} != old_denominator_role
                    or observation["source_clock"]["literal"] != old_clock
                    or observation["view"].get("ballots") != old_count
                    or observation["view"].get("denominator") != old_denominator
                    or observation["view"].get("reported_pct") != old_rate
                    or observation["source"]["fields"].get("ballots") != old_count
                    or observation["source"]["fields"].get("denominator") != old_denominator
                    or observation["source"]["fields"].get("denominator_basis")
                        != old["source"]["fields"].get("denominator_basis")
                    or observation["source"]["fields"].get("source_update_label") != old_clock
                    or properties.get("ballots") != old_count
                    or properties.get("denominator") != old_denominator
                    or properties.get("reported_pct") != old_rate
                    or properties.get("source_update_label") != old_clock
                    or observation["view"].get("denominator_basis")
                        != old["view"].get("denominator_basis")):
                raise IntakeError("native_layer_scope", "The old native/count/source mirrors do not agree")
            new_count = new["count"]["value"]
            new_denominator = (new["denominator"] or {}).get("value")
            valid = (new["denominator"]["qualified"] is True
                     and type(new_count) is int and type(new_denominator) is int
                     and new_denominator > 0 and new_count <= new_denominator
                     and new["view"].get("reported_pct") is not None)
            qualified = old_qualified and valid
            qualified_after += qualified
            withdrawals += old_qualified and not qualified
            count_changes += new_count != old_count
            registration_changes += new_denominator != old_denominator
            clock_changes += new["source_clock"]["literal"] != old_clock
            mirror(
                output_by_key[pair["native_key"]],
                new,
                qualified,
                review["source_inventory"]["inventory"],
                bridge,
            )

        expected = review["expected_changes"]
        actual = dict(
            bound_rows=len(pairs),
            count_changes=count_changes,
            qualified_after=qualified_after,
            qualified_before=qualified_before,
            registration_changes=registration_changes,
            source_clock_changes=clock_changes,
            unmatched_rows=len(unmatched),
            withdrawals=withdrawals,
        )
        if expected != actual:
            raise IntakeError("native_layer_scope", "Reviewed native layer change counts differ")
        body = compressed(output)
        result[filename] = body
        declaration = updated["layers"][layer_id]
        declaration.update(pin(body))
        declaration["coverage"].update(
            fractions=qualified_after,
            reported=len(pairs),
            source_rows=len(pairs),
            unknown=len(unmatched),
            withheld=0,
        )
        declaration["count_successor"] = dict(
            authority=copy.deepcopy(AUTHORITY_LABELS),
            classification=next(iter(source_classes)),
            contract=CONTRACT,
            current_count_source=dict(
                classification=next(iter(source_classes)),
                id=next(iter(source_ids)),
                input_sha256=review["source_input_sha256"],
                native_product_url=next(iter(
                    {row["view"]["source_url"] for row in new_rows}
                )),
                url=next(iter(source_urls)),
            ),
            pair_rows=len(pairs),
            review_evidence=review["complete_inventory_review_evidence"],
            source_clock=review["source_clock"],
            source_id=next(iter(source_ids)),
            source_input_sha256=review["source_input_sha256"],
            source_inventory=copy.deepcopy(review["source_inventory"]["inventory"]),
            source_rows=len(new_rows),
            source_url=next(iter(source_urls)),
        )
        if bridge is not None:
            declaration["count_successor"][BRIDGE_KEY] = copy.deepcopy(bridge)
        changed += len(pairs)
    result[description["index"]["file"]] = encoded(updated)
    pins = {name: pin(body) for name, body in sorted(result.items())}
    candidate = dict(
        description,
        files=pins,
        index=dict(file=description["index"]["file"], **pins[description["index"]["file"]]),
        version=digest(encoded(dict(files=pins, contract=description["record_contract"]))),
        complete_download=None,
    )
    return candidate, result, changed
