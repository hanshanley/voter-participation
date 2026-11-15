import copy
import gzip
import json
from pathlib import Path
import sys

import pytest

from scripts import results_granular
from scripts.participation_intake.contract import pin
try:
    from scripts import results_native_north_dakota as nd
except ImportError:
    import results_native_north_dakota as nd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nd_native_fixture_support as fixture_support


FIXTURES = Path(__file__).with_name("fixtures") / "nd-native-automatic"


def fixture():
    templates = fixture_support.load_gzip(
        FIXTURES / "accepted-templates.json.gz")["records"]
    facts = fixture_support.load_gzip(FIXTURES / "nd-complete-facts.json.gz")
    return templates, facts


def parse(templates, facts):
    documents = fixture_support.source_documents(facts)
    result = nd.statistics(
        documents[nd.FULL_RESULTS_URL], templates, nd.FULL_RESULTS_URL,
        acquire=lambda url: (documents[url], pin(documents[url])),
    )
    return result, documents


def baseline(templates):
    shard = {
        "contract": "participation.count_snapshot.v1",
        "state_code": "ND",
        "year": 2026,
        "records": templates,
        "views": {},
    }
    body = bytearray(gzip.compress(
        (json.dumps(shard, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        compresslevel=6, mtime=0))
    body[9] = 3
    return {
        "index.json": json.dumps({
            "contract": "participation.count_index.v1",
            "year": 2026,
            "states": {"ND": {"file": "states/ND.json.gz", **pin(bytes(body))}},
            "coverage": {},
        }, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        "states/ND.json.gz": bytes(body),
    }


def entry(result, documents):
    return {
        "ND-registered-fixture": {
            "status": "reported",
            "data": result,
            "source": {"url": nd.FULL_RESULTS_URL, **pin(documents[nd.FULL_RESULTS_URL])},
            "error": None,
        }
    }


def projected_rows(files):
    return json.loads(gzip.decompress(files["states/ND.json.gz"]))["records"]


def identity(row):
    native = row["view"]["native_record"]
    return native.get("canonical_identity", native)


def test_complete_fixture_preserves_native_parents_zero_and_all_holds():
    templates, facts = fixture()
    result, _ = parse(templates, facts)
    query = result["complete_native_query"][0]
    assert len(result["updates"]) == 411
    assert query["county_rows"] == 53
    assert query["reporting_unit_rows"] == 358
    assert query["state_ballots"] == 239057
    assert query["house_candidate_votes_not_ballots"] == 234595
    assert sum(update["value"] == 0 for update in result["updates"]) == 3
    assert sum(update["value"] is None for update in result["updates"]) == 0
    assert all(
        update["registered"] is None
        and update["rate_compatible"] is False
        and update["native"]["analytical_denominator"] is None
        and update["native"]["analytical_rate"] is None
        and update["native"]["geographic_join_changed"] is False
        for update in result["updates"]
    )


def test_changed_count_true_zero_unknown_successor_and_repeat_are_exact():
    templates, facts = fixture()
    successor_facts = fixture_support.controlled_successor(facts)
    result, documents = parse(templates, successor_facts)
    before = baseline(templates)
    after, changes = results_granular.project(before, entry(result, documents))
    assert len(changes) == 411
    rows = projected_rows(after)
    changed = next(row for row in rows if (
        identity(row).get("county_id"), identity(row).get("precinct_id"))
        == ("38003", "2401"))
    unknown = next(row for row in rows if (
        identity(row).get("county_id"), identity(row).get("precinct_id"))
        == ("38003", "2402"))
    assert changed["count"] == {"value": 278, "literal": 278, "status": "reported"}
    assert unknown["count"] == {"value": None, "literal": None, "status": "unknown"}
    assert sum(row["count"]["value"] == 0 for row in rows) == 3
    assert all(row["denominator"] is None for row in rows)
    repeated_result, repeated_documents = parse(rows, successor_facts)
    repeated, repeated_changes = results_granular.project(
        after, entry(repeated_result, repeated_documents))
    assert repeated_changes == []
    assert repeated == after


def test_literal_identity_rejects_ordinal_county_codes_and_new_units():
    templates, facts = fixture()
    changed = copy.deepcopy(templates)
    unit = next(row for row in changed if row["geography"]["level"] == "reporting_unit")
    unit["view"]["native_record"]["county"] = "01"
    with pytest.raises(ValueError, match="county identity"):
        nd.route(unit)
    documents = fixture_support.source_documents(facts)
    full = json.loads(documents[nd.FULL_RESULTS_URL])
    county = full["TurnoutData"]["Locations"]["38003"]
    county["Locations"]["new-unit"] = {
        "BallotsCast": [{"BallotsCast": 0, "BallotsReceived": 0,
                         "VotePercent": 0, "VoteTypeID": "1"}],
        "LocationID": "new-unit", "PrecinctsReporting": 1,
        "ReportingPercent": 100, "TotalPrecincts": 1,
    }
    county["PrecinctsReporting"] += 1
    county["TotalPrecincts"] += 1
    full["TurnoutData"]["PrecinctsReporting"] += 1
    full["TurnoutData"]["TotalPrecincts"] += 1
    house = full["ContestData"][0]["Locations"]["38003"]
    house["Locations"]["new-unit"] = {
        "Choices": [], "LocationID": "new-unit", "LocationName": "NEW",
        "PrecinctsReporting": 1, "TotalPrecincts": 1, "TotalVotes": 0,
        "WriteinChoices": [],
    }
    documents[nd.FULL_RESULTS_URL] = fixture_support.encoded(full)
    with pytest.raises(ValueError, match="inventory|scope|onboarding|parents differ"):
        nd.statistics(
            documents[nd.FULL_RESULTS_URL], templates, nd.FULL_RESULTS_URL,
            acquire=lambda url: (documents[url], pin(documents[url])),
        )
