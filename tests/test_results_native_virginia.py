import copy
import gzip
import json
from unittest.mock import patch

import pytest

from scripts import results_native_virginia as adapter
from scripts.participation_intake.contract import digest, encoded, observation_id, pin
from scripts.results_granular import project


def english(value):
    return [{"languageId": "en", "text": value}]


def document(*, jurisdiction, election, locality_elections=None, precincts=None,
             registrations=None, turnout=None):
    return {
        "jurisdiction": jurisdiction,
        "election": election,
        "localityElections": locality_elections or [],
        "ballotItems": [],
        "precincts": precincts or [],
        "pollingPlaces": [],
        "statistics": [],
        "voterRegistration": registrations or [],
        "voterTurnout": turnout or [],
        "ballotItemWithBreakdown": None,
    }


def election(identity, ballots, registered, clock, official=False):
    return {
        "id": identity,
        "name": english("2026 November General"),
        "electionDate": "2026-11-03",
        "isProduction": True,
        "isOfficialResults": official,
        "isPrimary": False,
        "asOf": clock,
        "lastUpdated": clock,
        "ballotsCast": float(ballots),
        "totalVoters": float(registered),
        "groupReportingStatus": [],
    }


def template(code, name, ballots, clock):
    geography = "VA|additional:VA:" + code
    identity = observation_id(
        adapter.SOURCE_ID, "us-2026-general-previously-reviewed", geography,
        adapter.MEASURE["id"], adapter.MEASURE["mode"],
    )
    native = {
        "as_of": clock,
        "ballots_cast": ballots,
        "locality_code": code,
        "publish_version": "safe-portable-fixture",
    }
    view = {
        "ballots": ballots,
        "complete_download_url": "https://example.test/complete-source.zip",
        "county": name,
        "county_id": "additional:VA:" + code,
        "denominator": None,
        "denominator_basis": "native_registered_voters",
        "geography_level": "county",
        "maps_approved": False,
        "native_printed_pct": None,
        "native_record": native,
        "quality": ["Portable complete Virginia behavior fixture."],
        "reported_pct": None,
        "reported_units": None,
        "review_id": "additional:VA-2026-native-locality-counts",
        "source_reporting_label": "Native whole-locality ballots.",
        "source_rows": 0,
        "source_status_literal": None,
        "source_update_label": clock,
        "source_url": adapter.STORED_VIEW_URL,
        "state_code": "VA",
        "total_units": None,
        "year": 2026,
    }
    return {
        "contract": "participation.observation.v1",
        "id": identity,
        "election": {
            "id": "us-2026-general-previously-reviewed",
            "year": 2026,
            "date": None,
            "type": "general",
            "qualification": "previously_reviewed",
        },
        "geography": {
            "id": geography,
            "name": name,
            "state_code": "VA",
            "level": "county" if int(code) < 500 else "county_equivalent",
            "parent_id": None,
            "join": {
                "status": "unreviewed",
                "reference_id": None,
                "feature_key": None,
                "evidence": "Portable behavior fixture; no new join.",
            },
        },
        "measure": copy.deepcopy(adapter.MEASURE),
        "count": {"value": ballots, "literal": ballots, "status": "reported"},
        "denominator": None,
        "source_clock": {
            "literal": clock,
            "timezone": None,
            "qualification": "previously_reviewed_export_label_not_new_native_clock",
        },
        "reporting_status": {
            "literal": None,
            "reported_units": None,
            "total_units": None,
            "complete": None,
        },
        "source": {
            "id": adapter.SOURCE_ID,
            "url": adapter.STORED_URL,
            "input_sha256": adapter.SOURCE_SHA,
            "selector": {},
            "classification": "public_aggregate",
            "fields": copy.deepcopy(view),
        },
        "quality": {"conflicts": [], "notes": ["Portable complete fixture."]},
        "view": view,
    }


def safe_complete_fixture():
    old_clock = "2026-11-05T02:19:25.1234567Z"
    children, summaries, registrations, templates = [], [], [], []
    bodies, unit_identities = {}, []
    state_registered = 0
    difference_budget = 659
    for ordinal, (code, slug) in enumerate(sorted(adapter.LOCALITY_SLUGS.items()), 1):
        locality_uuid = f"00000000-0000-0000-0001-{ordinal:012x}"
        election_uuid = f"00000000-0000-0000-0002-{ordinal:012x}"
        name = "LOCALITY " + code
        count = 21 if ordinal == 1 else 19
        precincts, turnout = [], []
        registered = count * 10
        ballots = 100 + ordinal
        state_registered += registered
        for unit_ordinal in range(1, count + 1):
            unit_uuid = f"00000000-0000-{ordinal:04x}-0003-{unit_ordinal:012x}"
            unit_name = f"{unit_ordinal:03d} - UNIT {unit_ordinal}"
            unit_ballots = 5
            differs = difference_budget > 0
            difference_budget -= int(differs)
            precincts.append({
                "id": unit_uuid,
                "name": english(unit_name + " (0000)"),
                "isVirtual": False,
                "mapFeatureId": None,
                "precinctOrder": unit_ordinal,
                "reportingStatus": 4,
            })
            turnout.append({
                "id": unit_uuid,
                "precinctName": unit_name,
                "ballotsCast": float(unit_ballots),
                "voterTurnout": unit_ballots - int(differs),
                "voterRegistration": 10,
            })
            unit_identities.append({
                "locality_code": code,
                "id": unit_uuid,
                "name": unit_name,
            })
        child = {
            "id": locality_uuid,
            "mapFeatureId": code,
            "shortName": slug,
            "name": english(name),
        }
        summary = election(election_uuid, ballots, registered, old_clock)
        summary["jurisdictionId"] = locality_uuid
        registration = {
            "id": locality_uuid,
            "activeVoters": registered - 1,
            "inactiveVoters": 1,
            "total": registered,
            "localityName": english(name),
        }
        child_document = document(
            jurisdiction={"id": locality_uuid, "shortName": slug, "name": english(name)},
            election=election(election_uuid, ballots, registered, old_clock),
            precincts=precincts,
            turnout=turnout,
        )
        url = adapter.API_ROOT + slug + "/2026-November-General/data"
        bodies[url] = encoded(child_document)
        children.append(child)
        summaries.append(summary)
        registrations.append(registration)
        templates.append(template(code, name, ballots, old_clock))
    assert difference_budget == 0
    root = document(
        jurisdiction={"childLocalities": children},
        election=election(adapter.ELECTION_ID, 0, state_registered, old_clock),
        locality_elections=summaries,
        registrations=registrations,
    )
    declarations = [{
        "code": child["mapFeatureId"],
        "id": child["id"],
        "short_name": child["shortName"],
        "name": child["name"][0]["text"],
        "url": adapter.API_ROOT + child["shortName"] + "/2026-November-General/data",
    } for child in children]
    identity_values = [adapter._identity(row) for row in templates]
    pins = {
        "identity": digest(encoded(sorted(identity_values, key=lambda row: row["id"]))),
        "full": digest(encoded(sorted(templates, key=lambda row: row["id"]))),
        "declarations": digest(encoded(sorted(declarations, key=lambda row: row["code"]))),
        "units": digest(encoded(sorted(
            unit_identities, key=lambda row: (row["locality_code"], row["id"])))),
    }
    return {
        "root": encoded(root),
        "bodies": bodies,
        "templates": templates,
        "pins": pins,
    }


def parse_fixture(fixture, templates=None):
    def acquire(url):
        body = fixture["bodies"][url]
        return body, {"origin": "portable_fixture", **pin(body)}

    with (
        patch.object(adapter, "IDENTITY_PIN", fixture["pins"]["identity"]),
        patch.object(adapter, "INITIAL_FULL_PIN", fixture["pins"]["full"]),
        patch.object(adapter, "LOCALITY_DECLARATION_PIN", fixture["pins"]["declarations"]),
        patch.object(adapter, "UNIT_IDENTITY_PIN", fixture["pins"]["units"]),
    ):
        return adapter.statistics(
            fixture["root"],
            fixture["templates"] if templates is None else templates,
            adapter.ROOT_URL,
            acquire=acquire,
        )


def baseline(templates):
    frame = {"counties": [row["id"] for row in templates],
             "precincts": [], "nongeographic": []}
    body = gzip.compress(encoded({
        "records": templates,
        "views": {
            "available": frame,
            "official": copy.deepcopy(frame),
            "in_person_early": {"counties": [], "precincts": [], "nongeographic": []},
            "mail_returned": {"counties": [], "precincts": [], "nongeographic": []},
        },
    }), mtime=0)
    return {
        "index.json": encoded({"states": {"VA": {"file": "VA.json.gz"}}}),
        "VA.json.gz": body,
    }


def entry(fixture, data):
    return {
        "status": "reported",
        "source": {"url": adapter.ROOT_URL, **pin(fixture["root"])},
        "data": data,
    }


def test_complete_safe_fixture_projects_parents_and_retains_all_native_units():
    fixture = safe_complete_fixture()
    data = parse_fixture(fixture)
    query = data["complete_native_query"][0]
    assert len(data["updates"]) == 133
    assert len(query["native_unit_rows"]) == 2529
    assert query["reconciliation"] == {
        "localities": 133,
        "native_unit_rows": 2529,
        "locality_ballots_cast": sum(range(101, 234)),
        "state_total_voters": 25290,
        "state_ballots_cast_control": 0,
        "state_ballots_cast_control_qualified": False,
        "native_unit_ballots_cast_subtotal": 12645,
        "native_unit_voter_turnout_subtotal": 11986,
        "ballots_cast_voter_turnout_differences": 659,
        "unit_ballots_not_summed_to_replace_locality_parents": True,
        "pooled_modes_or_parent_residuals_allocated": False,
        "registration_components_and_precinct_sums_reconcile": True,
        "analytical_rates_promoted": False,
        "geographic_joins_changed": False,
    }
    before = baseline(fixture["templates"])
    after, changes = project(before, {"VA-native": entry(fixture, data)})
    assert len(changes) == 133
    rows = json.loads(gzip.decompress(after["VA.json.gz"]))["records"]
    assert [row["count"]["value"] for row in rows] == list(range(101, 234))
    assert all(row["denominator"] is None for row in rows)
    assert all(row["view"]["reported_pct"] is None for row in rows)
    assert all(row["view"]["maps_approved"] is False for row in rows)
    assert all(row["source_clock"]["timezone"] == "UTC" for row in rows)
    assert all(row["reporting_status"]["complete"] is None for row in rows)
    repeated_data = parse_fixture(fixture, rows)
    repeated, repeated_changes = project(after, {"VA-native": entry(fixture, repeated_data)})
    assert repeated == after
    assert repeated_changes == []


def test_future_revised_parent_and_unit_counts_use_ballots_cast_without_rate_promotion():
    fixture = safe_complete_fixture()
    first = parse_fixture(fixture)
    before = baseline(fixture["templates"])
    after, _ = project(before, {"VA-native": entry(fixture, first)})
    rows = json.loads(gzip.decompress(after["VA.json.gz"]))["records"]
    code = "001"
    child_url = adapter._locality_url(code)
    root = json.loads(fixture["root"])
    child = json.loads(fixture["bodies"][child_url])
    root["localityElections"][0]["ballotsCast"] += 1
    child["election"]["ballotsCast"] += 1
    child["voterTurnout"][0]["ballotsCast"] += 1
    later = "2026-11-15T04:00:00.1234567Z"
    root["localityElections"][0]["asOf"] = later
    root["localityElections"][0]["lastUpdated"] = later
    child["election"]["asOf"] = later
    child["election"]["lastUpdated"] = later
    fixture["root"] = encoded(root)
    fixture["bodies"][child_url] = encoded(child)
    revised = parse_fixture(fixture, rows)
    update = next(row for row in revised["updates"]
                  if row["native"]["locality_code"] == code)
    assert update["value"] == 102
    assert update["value"] != sum(
        unit["voterTurnout"] for unit in revised["complete_native_query"][0]["native_unit_rows"]
        if unit["locality_code"] == code)
    assert update["rate_compatible"] is False
    projected, changes = project(after, {"VA-native": entry(fixture, revised)})
    assert len(changes) == 133
    assert sum(row["previous"] != row["current"] for row in changes) == 1
    current = json.loads(gzip.decompress(projected["VA.json.gz"]))["records"]
    changed = next(row for row in current if row["view"]["native_record"]["locality_code"] == code)
    assert changed["count"]["value"] == 102
    assert changed["denominator"] is None
    assert changed["view"]["reported_pct"] is None
    assert changed["view"]["maps_approved"] is False


def test_changed_identity_clock_or_count_schema_fails_closed():
    fixture = safe_complete_fixture()
    changed = copy.deepcopy(fixture)
    root = json.loads(changed["root"])
    root["jurisdiction"]["childLocalities"][0]["shortName"] = "invented-route"
    changed["root"] = encoded(root)
    with pytest.raises(ValueError, match="route"):
        parse_fixture(changed)

    changed = safe_complete_fixture()
    child_url = adapter._locality_url("001")
    child = json.loads(changed["bodies"][child_url])
    child["election"]["asOf"] = "2026-11-04T00:00:00Z"
    child["election"]["lastUpdated"] = "2026-11-04T00:00:00Z"
    changed["bodies"][child_url] = encoded(child)
    with pytest.raises(ValueError, match="regressed"):
        parse_fixture(changed)

    changed = safe_complete_fixture()
    child_url = adapter._locality_url("001")
    child = json.loads(changed["bodies"][child_url])
    child["voterTurnout"][0]["ballotsCast"] = None
    changed["bodies"][child_url] = encoded(child)
    with pytest.raises(ValueError, match="not zero"):
        parse_fixture(changed)


def test_route_never_relabels_saved_early_or_mail_frames():
    fixture = safe_complete_fixture()
    parent = fixture["templates"][0]
    assert adapter.route(parent)["url"] == adapter.ROOT_URL
    for mode in ("in_person_early", "mail_returned"):
        changed = copy.deepcopy(parent)
        changed["source"]["id"] = "saved-" + mode
        changed["measure"]["mode"] = mode
        assert adapter.route(changed) is None
