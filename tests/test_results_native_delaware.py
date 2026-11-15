import copy
from decimal import Decimal, ROUND_HALF_UP
import gzip
import json
from pathlib import Path

import pytest

from scripts.participation_intake.contract import encoded, pin
from scripts import results_granular, results_native
from scripts.results_native_delaware import (
    ADAPTER,
    OBSERVATION_ID,
    REVIEWED_URL,
    SOURCE_ID,
    STATUSES,
    STORED_SOURCE_URL,
    STORED_VIEW_URL,
    extend_templates,
    route,
    statistics,
)


FIXTURES = Path(__file__).parent / "fixtures/delaware-native"
STATES = (
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA "
    "WV WI WY"
).split()


def fixture():
    return json.loads((FIXTURES / "complete-turnout.json").read_bytes())


def shard():
    return json.loads((FIXTURES / "accepted-de-shard.json").read_bytes())


def body(rows=None):
    return encoded(rows if rows is not None else fixture()["rows"])


def compressed(value):
    raw = bytearray(gzip.compress(encoded(value), compresslevel=6, mtime=0))
    raw[9] = 3
    return bytes(raw)


def baseline(all_states=False):
    result = {}
    states = STATES if all_states else ["DE"]
    declarations = {}
    for state in states:
        path = "states/" + state + ".json.gz"
        value = shard() if state == "DE" else {
            "contract": "participation.count_snapshot.v1",
            "year": 2026,
            "state_code": state,
            "records": [],
            "views": {},
        }
        result[path] = compressed(value)
        declarations[state] = {"file": path, **pin(result[path])}
    result["index.json"] = encoded({
        "contract": "participation.count_index.v1",
        "year": 2026,
        "states": declarations,
    })
    return result


def template():
    return extend_templates(baseline(), [])[0]


def revised_rows(delta=1):
    rows = copy.deepcopy(fixture()["rows"])
    district = next(row for row in rows if row["Representative District"] == "01")
    state = next(row for row in rows if row["Representative District"] == "ALL")
    for row in (district, state):
        ballots = int(str(row["Ballots Cast"]).replace(",", "")) + delta
        registered = int(str(row["Reg Voters"]).replace(",", ""))
        row["Ballots Cast"] = f"{ballots:,}"
        row["Percentage"] = float(
            (100 * Decimal(ballots) / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP
            )
        )
    return rows


def entry(raw):
    data = statistics(raw, [template()], REVIEWED_URL)
    return {
        "status": "reported",
        "data": data,
        "source": {"url": REVIEWED_URL, **pin(raw)},
        "error": None,
        "first_observed_at": "2026-11-15T11:00:00+00:00",
    }


def test_actual_full_51_source_plan_registers_only_the_reviewed_statewide_slot():
    plan = results_native.source_plan(baseline(all_states=True))
    assert set(plan) == set(STATES)
    sources = [source for source in plan["DE"].values() if source["adapter"] == ADAPTER]
    assert len(sources) == 1
    assert sources[0]["url"] == REVIEWED_URL
    assert [row["id"] for row in sources[0]["templates"]] == [OBSERVATION_ID]
    assert route(sources[0]["templates"][0]) == {
        "adapter": ADAPTER, "state": "DE", "url": REVIEWED_URL,
    }


def test_complete_retained_vector_projects_only_the_existing_statewide_identity():
    raw = body()
    result = statistics(raw, [template()], REVIEWED_URL)
    query = result["complete_native_query"][0]
    assert query["source_pin"] == pin(raw)
    assert query["state_and_district_rows"] == 42
    assert query["representative_district_rows"] == 41
    assert len(query["rows"]) == 42
    assert len(query["withheld_representative_district_contexts"]) == 41
    assert result["representative_district_contexts_projected"] == 0
    assert result["updates"] == [{
        "id": OBSERVATION_ID,
        "value": 384862,
        "native": result["updates"][0]["native"],
        "registered": 810407,
        "clock": None,
        "reported_units": None,
        "total_units": None,
        "rate_compatible": True,
    }]
    assert result["updates"][0]["native"]["all_mode_completion_qualified"] is False
    assert result["updates"][0]["native"]["candidate_clock_not_substituted"] is True
    assert result["updates"][0]["native"]["county_or_precinct_allocation"] is False


def test_semantically_valid_revised_counts_do_not_require_the_retained_body_sha():
    original = body()
    revised = body(revised_rows())
    assert pin(original)["sha256"] != pin(revised)["sha256"]
    result = statistics(revised, [template()], REVIEWED_URL)
    assert result["updates"][0]["value"] == 384863
    assert result["updates"][0]["registered"] == 810407
    assert result["complete_native_query"][0]["source_pin"] == pin(revised)


def test_true_zero_is_not_missing_but_missing_is_never_coerced_to_zero():
    rows = revised_rows(delta=-8082)
    result = statistics(body(rows), [template()], REVIEWED_URL)
    district = next(
        row for row in result["complete_native_query"][0]["rows"]
        if row["representative_district"] == "01"
    )
    assert district["ballots_cast"] == 0
    missing = copy.deepcopy(rows)
    next(row for row in missing if row["Representative District"] == "01")[
        "Ballots Cast"
    ] = None
    with pytest.raises(ValueError, match="not a recorded zero"):
        statistics(body(missing), [template()], REVIEWED_URL)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows: rows.pop(), "inventory"),
        (
            lambda rows: rows.__setitem__(
                0, {**rows[0], "Election Id": "PE2026"}
            ),
            "election",
        ),
        (
            lambda rows: rows.__setitem__(
                0, {**rows[0], "Results Type": "CERTIFIED"}
            ),
            "status",
        ),
        (
            lambda rows: rows.__setitem__(
                0, {**rows[0], "Representative District": "02"}
            ),
            "duplicate",
        ),
        (
            lambda rows: rows.__setitem__(
                0, {**rows[0], "Reg Voters": "1"}
            ),
            "pair",
        ),
    ],
)
def test_corrupt_source_scope_identity_and_components_are_refused(mutation, message):
    rows = copy.deepcopy(fixture()["rows"])
    mutation(rows)
    with pytest.raises(ValueError, match=message):
        statistics(body(rows), [template()], REVIEWED_URL)


def test_state_district_reconciliation_is_not_repaired_or_apportioned():
    rows = copy.deepcopy(fixture()["rows"])
    row = next(item for item in rows if item["Representative District"] == "01")
    row["Ballots Cast"] = "8,083"
    row["Percentage"] = 42.71
    with pytest.raises(ValueError, match="accounting"):
        statistics(body(rows), [template()], REVIEWED_URL)


def test_official_to_unofficial_status_rollback_is_refused():
    accepted = template()
    accepted["reporting_status"]["literal"] = "OFFICIAL RESULTS"
    accepted["view"]["source_status_literal"] = "OFFICIAL RESULTS"
    with pytest.raises(ValueError, match="rolled back"):
        statistics(body(), [accepted], REVIEWED_URL)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["source"].update(id="different-source"),
        lambda row: row["source"].update(url="https://wrong.example/results"),
        lambda row: row["view"].update(source_url="https://wrong.example/results"),
        lambda row: row["measure"].update(literal="Candidate votes"),
        lambda row: row["geography"].update(level="county"),
        lambda row: row["denominator"].update(qualified=False),
        lambda row: row["view"].update(maps_approved=True),
        lambda row: row["source_clock"].update(literal="2026-11-15T10:00:00Z"),
    ],
)
def test_corrupt_accepted_template_scope_is_not_routed(mutate):
    row = template()
    mutate(row)
    assert route(row) is None


def test_projection_preserves_old_modes_geometry_rates_and_all_unrelated_rows():
    base = baseline()
    before_shard = shard()
    raw = body(revised_rows())
    after, changes = results_granular.project(
        base, {"DE-registered-test": entry(raw)}
    )
    path = json.loads(base["index.json"])["states"]["DE"]["file"]
    projected = json.loads(gzip.decompress(after[path]))
    before_rows = {row["id"]: row for row in before_shard["records"]}
    after_rows = {row["id"]: row for row in projected["records"]}
    assert len(changes) == 1
    assert changes[0]["id"] == OBSERVATION_ID
    assert after_rows[OBSERVATION_ID]["count"]["value"] == 384863
    assert after_rows[OBSERVATION_ID]["denominator"] == {
        "basis": "native_registered_voters",
        "literal": "native_registered_voters",
        "qualified": True,
        "value": 810407,
    }
    assert after_rows[OBSERVATION_ID]["geography"] == before_rows[OBSERVATION_ID]["geography"]
    assert after_rows[OBSERVATION_ID]["view"]["maps_approved"] is False
    for identity in set(before_rows) - {OBSERVATION_ID}:
        assert after_rows[identity] == before_rows[identity]
    assert projected["views"] == before_shard["views"]


def test_projection_repeat_is_byte_idempotent_and_source_lineage_is_strict():
    raw = body(revised_rows())
    first, _ = results_granular.project(
        baseline(), {"DE-registered-test": entry(raw)}
    )
    second, changes = results_granular.project(
        first, {"DE-registered-test": {
            **entry(raw),
            "data": statistics(
                raw, extend_templates(first, []), REVIEWED_URL
            ),
        }}
    )
    assert changes == []
    assert second == first
    broken = entry(raw)
    broken["source"]["url"] = "https://wrong.example/results"
    with pytest.raises(ValueError, match="bridge declaration"):
        results_granular.project(baseline(), {"DE-registered-test": broken})


def test_only_supported_literal_statuses_are_declared():
    assert STATUSES == ("UNOFFICIAL RESULTS", "OFFICIAL RESULTS")
    row = template()
    assert row["source"]["id"] == SOURCE_ID
    assert (row["source"]["url"], row["view"]["source_url"]) == (
        STORED_SOURCE_URL, STORED_VIEW_URL,
    )
