import copy
import json
import unittest

from scripts.participation_intake.contract import observation_id, pin
from scripts.results_native_state_family import (
    AR_ENTRY_URL,
    AR_REVIEWED_URL,
    AR_SOURCE_ID,
    AR_STORED_SOURCE_URL,
    AZ_API_ROOT,
    AZ_COUNTIES,
    AZ_ENTRY_URL,
    AZ_SOURCE_ID,
    AZ_STORED_SOURCE_URL,
    MEASURE,
    _validate_wyoming_heading,
    _wyoming_parent_controls,
    route,
    statistics,
)


COUNTY_CODE = "01"
COUNTY_NAME, COUNTY_SLUG, COUNTY_UUID = AZ_COUNTIES[COUNTY_CODE]
COUNTY_URL = AZ_API_ROOT + COUNTY_SLUG + "/110326GeneralElection/data"
PRECINCTS = (
    ("01000000-0000-0000-0000-000000000001", "ONE"),
    ("01000000-0000-0000-0000-000000000002", "ZERO"),
    ("01000000-0000-0000-0000-000000000003", "BLANK"),
)


def template(precinct_id, name, value, registered):
    geography_id = "AZ|synthetic|" + precinct_id
    identity = observation_id(
        AZ_SOURCE_ID, "us-2026-general-previously-reviewed", geography_id,
        MEASURE["id"], MEASURE["mode"],
    )
    native = {
        "county": COUNTY_NAME,
        "county_code": COUNTY_CODE,
        "native_county_uuid": COUNTY_UUID,
        "precinct": name,
        "precinct_code": precinct_id,
    }
    denominator = None if registered is None else {
        "value": registered,
        "literal": "synthetic native registration context",
        "basis": "synthetic native registration context",
        "qualified": False,
    }
    view = {
        "source_url": AZ_ENTRY_URL,
        "native_record": native,
        "ballots": value,
        "denominator": registered,
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
            "id": geography_id,
            "name": COUNTY_NAME + " · " + name,
            "state_code": "AZ",
            "level": "reporting_unit",
            "parent_id": "AZ|synthetic-parent",
            "join": {
                "status": "unreviewed",
                "reference_id": None,
                "feature_key": None,
                "evidence": "Synthetic identity test; no boundary join.",
            },
        },
        "measure": copy.deepcopy(MEASURE),
        "count": {
            "value": value,
            "literal": value,
            "status": "reported" if value is not None else "unknown",
        },
        "denominator": denominator,
        "source_clock": {
            "literal": "2026-11-05T00:00:00Z",
            "timezone": "UTC",
            "qualification": "native_clock_or_explicitly_not_supplied",
        },
        "reporting_status": {
            "literal": None,
            "reported_units": None,
            "total_units": None,
            "complete": None,
        },
        "source": {
            "id": AZ_SOURCE_ID,
            "url": AZ_STORED_SOURCE_URL,
            "input_sha256": "1" * 64,
            "selector": {"synthetic": True},
            "classification": "public_aggregate",
            "fields": copy.deepcopy(view),
        },
        "quality": {"conflicts": [], "notes": ["Synthetic portable behavior fixture."]},
        "view": view,
    }


def county_body(clock="2026-11-05T01:00:00Z"):
    return {
        "jurisdiction": {
            "id": COUNTY_UUID,
            "name": [{"languageId": "en", "text": COUNTY_NAME}],
        },
        "election": {
            "electionDate": "2026-11-03",
            "isPrimary": False,
            "isProduction": True,
            "isOfficialResults": False,
            "name": [{"languageId": "en", "text": "2026 General Election"}],
            "ballotsCast": 11.0,
            "totalVoters": 7.0,
            "asOf": clock,
        },
        "precincts": [
            {
                "id": identity,
                "name": [{"languageId": "en", "text": name}],
                "isVirtual": name == "BLANK",
                "reportingStatus": 2,
            }
            for identity, name in PRECINCTS
        ],
        "voterTurnout": [
            {
                "id": PRECINCTS[0][0],
                "precinctName": "ONE",
                "ballotsCast": 11.0,
                "voterTurnout": 11,
                "voterRegistration": 7,
            },
            {
                "id": PRECINCTS[1][0],
                "precinctName": "ZERO",
                "ballotsCast": 0.0,
                "voterTurnout": 0,
                "voterRegistration": 0,
            },
        ],
    }


def root_body():
    return {
        "election": {
            "electionDate": "2026-11-03",
            "isOfficialResults": False,
            "ballotsCast": 0.0,
        },
        "jurisdiction": {
            "childLocalities": [{
                "id": COUNTY_UUID,
                "shortName": COUNTY_SLUG,
                "name": [{"languageId": "en", "text": COUNTY_NAME}],
            }],
        },
        "localityElections": [{
            "id": "01000000-0000-0000-0000-000000000010",
            "jurisdictionId": COUNTY_UUID,
            "ballotsCast": 11.0,
            "totalVoters": 7.0,
        }],
        "voterRegistration": [{
            "id": COUNTY_UUID,
            "total": 7,
        }],
    }


def ar_template(precinct_id, name, value):
    geography_id = "AR|synthetic|" + precinct_id
    identity = observation_id(
        AR_SOURCE_ID, "us-2026-general-previously-reviewed", geography_id,
        MEASURE["id"], MEASURE["mode"],
    )
    native = {
        "county": "Arkansas", "county_code": "05001",
        "precinct": name, "precinct_code": precinct_id,
    }
    view = {"source_url": AR_ENTRY_URL, "native_record": native,
            "ballots": value, "denominator": None}
    return {
        "contract": "participation.observation.v1", "id": identity,
        "election": {"id": "us-2026-general-previously-reviewed", "year": 2026,
                     "date": None, "type": "general", "qualification": "previously_reviewed"},
        "geography": {
            "id": geography_id, "name": "Arkansas · " + name, "state_code": "AR",
            "level": "reporting_unit", "parent_id": "AR|synthetic-parent",
            "join": {"status": "unreviewed", "reference_id": None,
                     "feature_key": None, "evidence": "Synthetic identity test."}},
        "measure": copy.deepcopy(MEASURE),
        "count": {"value": value, "literal": value,
                  "status": "reported" if value is not None else "unknown"},
        "denominator": None,
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": None, "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": AR_SOURCE_ID, "url": AR_STORED_SOURCE_URL,
                   "input_sha256": "1" * 64, "selector": {},
                   "classification": "public_aggregate", "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": ["Synthetic portable behavior fixture."]},
        "view": view,
    }


def ar_body(first_value=None):
    def node(identity, value):
        result = {
            "LocationID": identity,
            "BallotsCast": [{"BallotsCast": 0 if value is None else value,
                             "BallotsReceived": 0, "VotePercent": 100,
                             "VoteTypeID": "total"}],
            "PrecinctsReporting": 1, "TotalPrecincts": 1, "ReportingPercent": 100,
        }
        if value is not None:
            result["TotalBallotsCast"] = value
        return result
    total = 0 if first_value is None else first_value
    return {
        "ElectionData": {"ElectionID": "11b07106-031e-4d7c-911a-d01fb473d6dd",
                         "IsOfficial": False},
        "ContestData": [],
        "TurnoutData": {
            "TotalBallotsCast": total,
            "Locations": {"05001": {
                "TotalBallotsCast": total,
                "Locations": {"1": node("1", first_value), "2": node("2", 0)}}},
        },
    }


class NativeStateFamilyTests(unittest.TestCase):
    def setUp(self):
        self.templates = [
            template(PRECINCTS[0][0], "ONE", 9, 7),
            template(PRECINCTS[1][0], "ZERO", 4, 0),
            template(PRECINCTS[2][0], "BLANK", None, None),
        ]
        self.body = json.dumps(county_body()).encode()
        self.root = json.dumps(root_body()).encode()

    def acquire(self, url):
        self.assertEqual(url, AZ_API_ROOT + "Arizona/110326GeneralElection/data")
        return self.root, pin(self.root)

    def test_numeric_successor_zero_blank_clock_and_source_roles(self):
        result = statistics(self.body, self.templates, COUNTY_URL, acquire=self.acquire)
        updates = result["updates"]
        self.assertEqual([row["value"] for row in updates], [11, 0, None])
        self.assertEqual([row["registered"] for row in updates], [7, 0, None])
        self.assertEqual(updates[0]["clock"], "2026-11-05T01:00:00Z")
        self.assertEqual(updates[0]["native"]["source_clock_timezone_literal"], "UTC")
        self.assertTrue(updates[2]["native"]["native_observation_present"] is False)
        query = result["complete_native_query"][0]
        self.assertEqual(query["root_backend_statewide_ballots"], 0)
        self.assertTrue(query["root_backend_zero_not_substituted_for_positive_county_counts"])
        self.assertEqual(query["source_pin"], pin(self.body))
        bridge = result["reviewed_source_url_bridge"]
        self.assertEqual(bridge["source_id"], AZ_SOURCE_ID)
        self.assertEqual(bridge["stored_source_url"], AZ_STORED_SOURCE_URL)
        self.assertEqual(bridge["stored_view_source_url"], AZ_ENTRY_URL)
        self.assertEqual(bridge["reviewed_url"], COUNTY_URL)

    def test_clock_rollback_is_rejected(self):
        body = json.dumps(county_body("2026-11-04T23:59:59Z")).encode()
        with self.assertRaisesRegex(ValueError, "clock regressed"):
            statistics(body, self.templates, COUNTY_URL, acquire=self.acquire)

    def test_malformed_or_non_utc_arizona_clock_is_rejected(self):
        for clock in (
            "2026-11-05T01:00:00-07:00",
            "2026-11-05 01:00:00Z",
            "2026-13-05T01:00:00Z",
        ):
            body = json.dumps(county_body(clock)).encode()
            with self.assertRaisesRegex(ValueError, "clock"):
                statistics(body, self.templates, COUNTY_URL, acquire=self.acquire)

    def test_explicit_arizona_official_status_is_retained_without_promoting_rates(self):
        body = county_body()
        body["election"]["isOfficialResults"] = True
        root = root_body()
        root["election"]["isOfficialResults"] = True
        root = json.dumps(root).encode()
        result = statistics(
            json.dumps(body).encode(), self.templates, COUNTY_URL,
            acquire=lambda url: (root, pin(root)),
        )
        query = result["complete_native_query"][0]
        self.assertEqual(query["native_report_status_literal"], "OFFICIAL")
        self.assertEqual(query["root_native_report_status_literal"], "OFFICIAL")
        self.assertEqual([update["value"] for update in result["updates"]], [11, 0, None])
        self.assertTrue(all(
            update["native"]["native_report_status_literal"].startswith("OFFICIAL")
            and update["rate_compatible"] is False
            for update in result["updates"]
        ))
        self.assertFalse(result["analytical_rates_promoted"])

    def test_january_utc_update_still_refers_to_the_2026_election(self):
        body = json.dumps(county_body("2027-01-05T01:00:00Z")).encode()
        result = statistics(body, self.templates, COUNTY_URL, acquire=self.acquire)
        self.assertEqual(result["updates"][0]["clock"], "2027-01-05T01:00:00Z")
        self.assertEqual(result["complete_native_query"][0]["election_date"], "2026-11-03")

    def test_official_status_requires_a_literal_boolean(self):
        for value in (None, "true", 1):
            body = county_body()
            body["election"]["isOfficialResults"] = value
            with self.assertRaisesRegex(ValueError, "general-election"):
                statistics(
                    json.dumps(body).encode(), self.templates, COUNTY_URL, acquire=self.acquire,
                )
            body = ar_body()
            body["ElectionData"]["IsOfficial"] = value
            with self.assertRaisesRegex(ValueError, "general-election"):
                statistics(
                    json.dumps(body).encode(),
                    [ar_template("1", "UNKNOWN", None), ar_template("2", "ZERO", 0)],
                    AR_REVIEWED_URL,
                )

    def test_explicit_arkansas_official_status_preserves_unknown_and_zero(self):
        body = ar_body()
        body["ElectionData"]["IsOfficial"] = True
        result = statistics(
            json.dumps(body).encode(),
            [ar_template("1", "UNKNOWN", None), ar_template("2", "ZERO", 0)],
            AR_REVIEWED_URL,
        )
        self.assertEqual(result["complete_native_query"][0]["native_report_status_literal"], "OFFICIAL")
        self.assertEqual([update["value"] for update in result["updates"]], [None, 0])
        self.assertTrue(all(
            update["native"]["native_report_status_literal"] == "OFFICIAL"
            and update["rate_compatible"] is False
            for update in result["updates"]
        ))

    def test_mixed_or_unreviewed_url_is_rejected(self):
        changed = copy.deepcopy(self.templates[0])
        changed["view"]["source_url"] = "https://wrong.example/results"
        with self.assertRaisesRegex(ValueError, "lineage changed"):
            route(changed)

    def test_measure_and_source_identity_are_not_inferred(self):
        changed = copy.deepcopy(self.templates[0])
        changed["measure"]["literal"] = "Candidate total"
        self.assertIsNone(route(changed))
        changed = copy.deepcopy(self.templates[0])
        changed["source"]["id"] = "different-source"
        self.assertIsNone(route(changed))

    def test_root_backend_positive_total_requires_declared_county_reconciliation(self):
        root = root_body()
        root["election"]["ballotsCast"] = 12.0
        raw = json.dumps(root).encode()

        def acquire(url):
            return raw, pin(raw)

        with self.assertRaisesRegex(ValueError, "differs from declared county"):
            statistics(self.body, self.templates, COUNTY_URL, acquire=acquire)

    def test_corrected_positive_state_parent_does_not_block_county_updates(self):
        root = root_body()
        root["election"]["ballotsCast"] = 11.0
        raw = json.dumps(root).encode()
        result = statistics(
            self.body, self.templates, COUNTY_URL, acquire=lambda url: (raw, pin(raw)),
        )
        self.assertEqual([update["value"] for update in result["updates"]], [11, 0, None])
        query = result["complete_native_query"][0]
        self.assertEqual(query["root_backend_statewide_ballots"], 11)
        self.assertFalse(query["root_backend_zero_not_substituted_for_positive_county_counts"])

    def test_duplicate_root_locality_records_are_not_silently_overwritten(self):
        for field in ("localityElections", "voterRegistration"):
            root = root_body()
            root[field].append(copy.deepcopy(root[field][0]))
            raw = json.dumps(root).encode()
            with self.assertRaisesRegex(ValueError, "Duplicate.*UUID"):
                statistics(
                    self.body, self.templates, COUNTY_URL, acquire=lambda url: (raw, pin(raw)),
                )

    def test_arkansas_unknown_can_become_reported_true_zero_and_repeat_stably(self):
        templates = [ar_template("1", "UNKNOWN", None), ar_template("2", "ZERO", 0)]
        first = statistics(
            json.dumps(ar_body()).encode(), templates, AR_REVIEWED_URL)
        self.assertEqual([update["value"] for update in first["updates"]], [None, 0])
        self.assertEqual(first["complete_native_query"][0]["missing_ballot_cells"], 1)
        reported_body = json.dumps(ar_body(5)).encode()
        reported = statistics(reported_body, templates, AR_REVIEWED_URL)
        self.assertEqual([update["value"] for update in reported["updates"]], [5, 0])
        self.assertEqual(reported["complete_native_query"][0]["missing_ballot_cells"], 0)
        successors = []
        for template, update in zip(templates, reported["updates"]):
            successor = copy.deepcopy(template)
            successor["source"]["url"] = AR_REVIEWED_URL
            successor["source"]["input_sha256"] = pin(reported_body)["sha256"]
            successor["view"]["source_url"] = AR_REVIEWED_URL
            successor["view"]["native_record"] = copy.deepcopy(update["native"])
            successor["view"]["automatic_source_refresh"] = True
            successors.append(successor)
        repeated = statistics(reported_body, successors, AR_REVIEWED_URL)
        self.assertEqual([update["value"] for update in repeated["updates"]], [5, 0])

    def test_wyoming_rejects_relabelled_year_primary_or_status_heading(self):
        workbook = "2026 County General PbP - OFFICIAL.xlsx"
        correct = (
            "Albany County Official Precinct-by-Precinct Summary\n"
            "Wyoming General Election - November 3, 2026"
        )
        self.assertEqual(_validate_wyoming_heading(workbook, "Albany", correct), correct)
        for changed in (
            correct.replace("2026", "2024"),
            correct.replace("General Election", "Primary Election"),
            correct.replace("Official", "Unofficial"),
        ):
            with self.assertRaisesRegex(ValueError, "election/year/OFFICIAL"):
                _validate_wyoming_heading(workbook, "Albany", changed)

    def test_wyoming_rejects_wrong_direct_parent(self):
        categories = {
            "R": 2, "D": 1, "L": 0, "C": 0,
            "write_ins": 0, "overvotes": 0, "undervotes": 0,
        }
        precinct_ballots = [{"county": "Alpha", "precinct": "1", "ballots": 3}]
        precinct_house = [{"county": "Alpha", "precinct": "1", **categories}]
        county_ballots = [{"county": "Alpha", "ballots": 3}]
        state_ballots = [{"county": "Alpha", "ballots": 3},
                         {"county": "Total", "ballots": 3}]
        county_house = [{"county": "Alpha", **categories}]
        state_house = [{"county": "Alpha", **categories},
                       {"county": "Total", **categories}]
        controls = _wyoming_parent_controls(
            precinct_ballots, precinct_house, county_ballots,
            state_ballots, county_house, state_house)
        self.assertTrue(controls["all_precinct_county_state_ballot_parents_reconcile"])
        state_ballots[0]["ballots"] = 4
        with self.assertRaisesRegex(ValueError, "parent reconciliation"):
            _wyoming_parent_controls(
                precinct_ballots, precinct_house, county_ballots,
                state_ballots, county_house, state_house)


if __name__ == "__main__":
    unittest.main()
