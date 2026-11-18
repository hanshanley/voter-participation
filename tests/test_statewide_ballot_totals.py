import copy
import gzip
import json

import pytest

from scripts import statewide_ballot_totals as totals
from scripts import automatic_native_refresh as native
from scripts.participation_intake.contract import encoded, pin
from test_protected_official_wyoming import entry, native as workbook, changed
from scripts import protected_official_wyoming as official


def source(delta=0):
    data = official.parse(workbook(changed(delta)))
    return {"status": "reported", "data": data,
            "source": {"url": official.URL, **data["native_facts"]["original"]}}


def snapshot(value):
    return {"congress": {"official_candidate_evidence": {official.IDENTITY: value}}}


def baseline(monkeypatch):
    shard = {"contract": "participation.count_snapshot.v1", "state_code": "WY",
             "year": 2026, "records": [], "views": {"official": {"counties": [], "precincts": []}}}
    body = totals.compressed(shard)
    monkeypatch.setitem(totals.PROFILES["WY"], "initial_shard", pin(body))
    index = {"contract": "participation.count_index.v1", "year": 2026,
             "states": {"WY": {"file": "states/WY.json.gz", "records": 0, **pin(body)}},
             "coverage": {"WY": {}}}
    current = {"contract": "participation.current_snapshot.v1",
               "reviewed_states": [], "snapshot": {"reporting": []}}
    return {"states/WY.json.gz": body, "index.json": encoded(index),
            "current.json.gz": totals.compressed(current), "other-file": b"unchanged"}


def row(files):
    return json.loads(gzip.decompress(files["states/WY.json.gz"]))["records"][-1]


def test_direct_native_parent_is_count_only_and_congressional_contract_stays_separate(monkeypatch):
    initial = baseline(monkeypatch)
    value = entry()
    output, changes = totals.project(initial, snapshot(value))
    item = row(output)
    assert item["count"]["value"] == 191713
    assert item["count"]["value"] != value["data"]["races"][0]["contest_total"]
    assert item["denominator"] is item["view"]["validated_pct"] is None
    assert item["source_clock"] == {"literal": None, "timezone": None}
    assert item["reporting_status"]["complete"] is None
    assert item["view"]["unique_voter_count_qualified"] is False
    assert item["view"]["maps_approved"] is False
    assert value["data"]["participation_observation_qualified"] is False
    assert changes == [{"state_code": "WY", "id": item["id"], "previous": None,
                        "current": 191713, "source_status": "reported"}]
    current = json.loads(gzip.decompress(output["current.json.gz"]))
    assert current["snapshot"]["reporting"] == [item["view"]]
    assert output["other-file"] == initial["other-file"]
    assert totals.project(output, snapshot(value)) == (output, [])
    assert b"WY,2026,191713,reported,,," in totals.exports(output)[
        "participation/native-statewide-ballot-totals.csv"]


@pytest.mark.parametrize("delta", [7, -13])
def test_both_native_revision_directions_propagate_to_canonical_mirror_and_download(monkeypatch, delta):
    output, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    revised, changes = totals.project(output, snapshot(source(delta)))
    item = row(revised)
    assert item["id"] == row(output)["id"]
    assert item["count"]["value"] == 191713 + delta
    assert changes[0]["previous"] == 191713
    assert item["source"]["input_sha256"] != row(output)["source"]["input_sha256"]
    assert native.observation_identity(item) == native.observation_identity(row(output))
    current = json.loads(gzip.decompress(revised["current.json.gz"]))
    assert current["snapshot"]["reporting"][0] == item["view"]
    exported = json.loads(gzip.decompress(totals.exports(revised)[
        "participation/native-statewide-ballot-totals.json.gz"]))
    assert exported["rows"][0]["ballots"] == 191713 + delta


def test_failure_retains_last_good_without_inventing_an_initial_observation_and_recovers(monkeypatch):
    initial = baseline(monkeypatch)
    failed = {"status": "source_stopped", "data": None}
    assert totals.project(initial, snapshot(failed)) == (initial, [])
    good, _ = totals.project(initial, snapshot(source()))
    held, changes = totals.project(good, snapshot(failed))
    assert row(held)["count"] == row(good)["count"]
    assert row(held)["source"]["input_sha256"] == row(good)["source"]["input_sha256"]
    assert row(held)["view"]["status"] == changes[0]["source_status"] == "retained_after_failure"
    assert totals.project(held, snapshot(failed)) == (held, [])
    recovered, _ = totals.project(held, snapshot(source()))
    assert recovered == good


def test_missing_display_mirror_is_restored_without_changing_canonical_observation(monkeypatch):
    good, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    incomplete = dict(good)
    current = json.loads(gzip.decompress(incomplete["current.json.gz"]))
    current["snapshot"]["reporting"] = []
    incomplete["current.json.gz"] = totals.compressed(current)
    repaired, changes = totals.project(incomplete, snapshot(source()))
    assert changes == []
    assert repaired == good
    assert totals.project(repaired, snapshot(source())) == (good, [])


def test_complete_native_zero_is_not_missing_or_a_turnout_rate(monkeypatch):
    good, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    facts = changed()
    for table in facts["tables"]:
        for selected in table["rows"]:
            for cell in selected["cells"]:
                if selected["row"] >= 5 and type(cell["value"]) is int:
                    cell["value"] = 0
                    cell["cached_literal"] = "0"
    data = official.parse(workbook(facts))
    empty = {"status": "reported", "data": data,
             "source": {"url": official.URL, **data["native_facts"]["original"]}}
    revised, changes = totals.project(good, snapshot(empty))
    assert row(revised)["count"] == {"value": 0, "literal": 0, "status": "reported"}
    assert row(revised)["view"]["ballots"] == changes[0]["current"] == 0
    assert row(revised)["denominator"] is row(revised)["view"]["validated_pct"] is None
    assert totals.project(revised, snapshot(empty)) == (revised, [])


@pytest.mark.parametrize("mutation", ["count", "denominator", "clock", "map", "source"])
def test_corrupt_prior_or_promoted_qualifications_are_refused(monkeypatch, mutation):
    good, _ = totals.project(baseline(monkeypatch), snapshot(source()))
    shard = json.loads(gzip.decompress(good["states/WY.json.gz"]))
    item = shard["records"][0]
    if mutation == "count":
        item["count"]["value"] += 1
    elif mutation == "denominator":
        item["denominator"] = {"value": 200000, "qualified": True}
    elif mutation == "clock":
        item["source_clock"]["literal"] = "retrieval time"
    elif mutation == "map":
        item["view"]["maps_approved"] = True
    else:
        item["source"]["input_sha256"] = "f" * 64
    good["states/WY.json.gz"] = totals.compressed(shard)
    index = json.loads(good["index.json"])
    index["states"]["WY"].update(pin(good["states/WY.json.gz"]))
    good["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="Existing statewide ballot"):
        totals.project(good, snapshot(source()))


def test_native_inventory_and_display_preimages_remain_fail_closed(monkeypatch):
    initial = baseline(monkeypatch)
    edited = dict(initial)
    shard = json.loads(gzip.decompress(edited["states/WY.json.gz"]))
    shard["views"]["official"]["counties"] = ["unexpected"]
    edited["states/WY.json.gz"] = totals.compressed(shard)
    index = json.loads(edited["index.json"])
    index["states"]["WY"].update(pin(edited["states/WY.json.gz"]))
    edited["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="Unreviewed initial"):
        totals.project(edited, snapshot(source()))
    current = json.loads(gzip.decompress(initial["current.json.gz"]))
    current["snapshot"]["reporting"] = [{"state_code": "WY", "ballots": 1}]
    initial["current.json.gz"] = totals.compressed(current)
    with pytest.raises(ValueError, match="display preimage"):
        totals.project(initial, snapshot(source()))


def test_only_the_reviewed_single_append_passes_native_inventory_guard(monkeypatch):
    initial = baseline(monkeypatch)
    good, _ = totals.project(initial, snapshot(source()))
    before, after, states = native.changed_records(initial, good)
    assert before == after == {} and states == {"WY"}
    shard = json.loads(gzip.decompress(good["states/WY.json.gz"]))
    shard["records"].append(copy.deepcopy(shard["records"][0]))
    shard["records"][-1]["id"] = "unexpected"
    good["states/WY.json.gz"] = totals.compressed(shard)
    index = json.loads(good["index.json"])
    index["states"]["WY"].update(pin(good["states/WY.json.gz"]))
    good["index.json"] = encoded(index)
    with pytest.raises(ValueError, match="only existing count IDs"):
        native.changed_records(initial, good)
