import copy
import gzip
import json

import pytest

from scripts import results_native_virginia as adapter
from scripts.results_granular import project
from test_results_native_virginia import (
    baseline,
    entry,
    parse_fixture,
    safe_complete_fixture,
)


def set_statuses(fixture, root_official, locality_overrides):
    root = json.loads(fixture["root"])
    root["election"]["isOfficialResults"] = root_official
    by_code = {
        child["id"].lower(): child["mapFeatureId"]
        for child in root["jurisdiction"]["childLocalities"]
    }
    for summary in root["localityElections"]:
        code = by_code[summary["jurisdictionId"].lower()]
        summary["isOfficialResults"] = locality_overrides.get(code, root_official)
    fixture["root"] = adapter.encoded(root)
    for code, slug in adapter.LOCALITY_SLUGS.items():
        url = adapter.API_ROOT + slug + "/2026-November-General/data"
        child = json.loads(fixture["bodies"][url])
        child["election"]["isOfficialResults"] = locality_overrides.get(
            code, root_official)
        fixture["bodies"][url] = adapter.encoded(child)
    return fixture


@pytest.mark.parametrize(
    "root_official,overrides,expected_root,expected_locality",
    [
        (False, {"001": True}, "UNOFFICIAL", "OFFICIAL"),
        (True, {"001": False}, "OFFICIAL", "UNOFFICIAL"),
    ],
)
def test_locality_status_survives_mixed_root_status_without_completion_upgrade(
        root_official, overrides, expected_root, expected_locality):
    fixture = set_statuses(
        safe_complete_fixture(), root_official, overrides)
    data = parse_fixture(fixture)
    selected = next(
        row for row in data["updates"]
        if row["native"]["locality_code"] == "001")
    assert selected["native"]["native_report_status_literal"] == expected_locality
    assert selected["native"]["query"]["native_report_status_literal"] == expected_locality
    query = data["complete_native_query"][0]
    assert query["root_document"]["election"]["isOfficialResults"] is root_official
    assert sum(
        row["native"]["native_report_status_literal"] == expected_locality
        for row in data["updates"]) == 1
    assert sum(
        row["native"]["native_report_status_literal"] == expected_root
        for row in data["updates"]) == 132

    projected, _ = project(
        baseline(fixture["templates"]), {"VA-native": entry(fixture, data)})
    rows = json.loads(gzip.decompress(projected["VA.json.gz"]))["records"]
    locality = next(
        row for row in rows
        if row["view"]["native_record"]["locality_code"] == "001")
    assert locality["reporting_status"] == {
        "literal": expected_locality,
        "reported_units": None,
        "total_units": None,
        "complete": None,
    }
    assert locality["view"]["source_status_literal"] == expected_locality
    assert locality["denominator"] is None
    assert locality["view"]["reported_pct"] is None
    assert locality["view"]["maps_approved"] is False


def test_true_zero_parent_and_unit_project_repeat_while_unknown_retains_last_good():
    fixture = safe_complete_fixture()
    root = json.loads(fixture["root"])
    root["localityElections"][0]["ballotsCast"] = 0.0
    child_url = adapter._locality_url("001")
    child = json.loads(fixture["bodies"][child_url])
    child["election"]["ballotsCast"] = 0.0
    child["voterTurnout"][0]["ballotsCast"] = 0.0
    child["voterTurnout"][0]["voterTurnout"] = 0
    fixture["root"] = adapter.encoded(root)
    fixture["bodies"][child_url] = adapter.encoded(child)

    data = parse_fixture(fixture)
    update = next(
        row for row in data["updates"]
        if row["native"]["locality_code"] == "001")
    unit = next(
        row for row in data["complete_native_query"][0]["native_unit_rows"]
        if row["locality_code"] == "001" and row["id"] == child["voterTurnout"][0]["id"])
    assert update["value"] == 0
    assert unit["ballotsCast"] == 0
    assert unit["voterTurnout"] == 0

    before = baseline(fixture["templates"])
    projected, _ = project(before, {"VA-native": entry(fixture, data)})
    rows = json.loads(gzip.decompress(projected["VA.json.gz"]))["records"]
    locality = next(
        row for row in rows
        if row["view"]["native_record"]["locality_code"] == "001")
    assert locality["count"] == {"value": 0, "literal": 0, "status": "reported"}
    assert locality["reporting_status"]["complete"] is None
    repeated_data = parse_fixture(fixture, rows)
    repeated, repeated_changes = project(
        projected, {"VA-native": entry(fixture, repeated_data)})
    assert repeated == projected
    assert repeated_changes == []

    unknown = copy.deepcopy(fixture)
    root = json.loads(unknown["root"])
    root["localityElections"][0]["ballotsCast"] = None
    child = json.loads(unknown["bodies"][child_url])
    child["election"]["ballotsCast"] = None
    unknown["root"] = adapter.encoded(root)
    unknown["bodies"][child_url] = adapter.encoded(child)
    with pytest.raises(ValueError, match="not zero"):
        parse_fixture(unknown, rows)
    retained_after_failure = projected
    assert retained_after_failure == projected
