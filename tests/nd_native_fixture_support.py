"""Portable builders for complete safe North Dakota factual fixtures."""

import copy
import gzip
import json


FULL_RESULTS_URL = (
    "https://resultsnd.sos.nd.gov/results/north-dakota/348/FullDataFile.json"
)
ELECTION_URL = (
    "https://api.resultsnd.sos.nd.gov/Election/GetElectionInfo?cId=north-dakota"
)
TURNOUT_URL = (
    "https://api.resultsnd.sos.nd.gov/Turnout/GetTurnout?"
    "cId=north-dakota&electionID=348"
)


def encoded(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def load_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def controlled_successor(facts):
    result = copy.deepcopy(facts)
    result["version_id"] = "v76"
    result["last_updated"] = "2026-11-06T01:30:08.5674284Z"
    county = next(row for row in result["counties"] if row["county_id"] == "38003")
    changed = next(row for row in county["units"] if row["precinct_id"] == "2401")
    unknown = next(row for row in county["units"] if row["precinct_id"] == "2402")
    changed["ballots"] += 1
    removed = unknown["ballots"]
    unknown["ballots"] = None
    unknown["reported_units"] = 0
    delta = 1 - removed
    county["ballots"] += delta
    county["reported_units"] -= 1
    result["state_ballots"] += delta
    result["state_reported_units"] -= 1
    result["controlled_successor"] = {
        "changed_count": {"county_id": "38003", "precinct_id": "2401"},
        "unknown_count": {"county_id": "38003", "precinct_id": "2402"},
        "retained_true_zero_count": sum(
            unit["ballots"] == 0
            for item in result["counties"] for unit in item["units"]),
    }
    return result


def _bucket(value):
    if value is None:
        return []
    return [{
        "BallotsCast": value,
        "BallotsReceived": value,
        "VotePercent": 0 if value == 0 else 100,
        "VoteTypeID": "1",
    }]


def _turnout_record(identity, value, reported, total, *, registered=None, locations=None):
    result = {
        "BallotsCast": _bucket(value),
        "LocationID": identity,
        "PrecinctsReporting": reported,
        "ReportingPercent": 100 * reported / total if total else 0,
        "TotalPrecincts": total,
    }
    if value is not None and value != 0:
        result["TotalBallotsCast"] = value
        result["TotalBallotsReceived"] = value
    if registered is not None:
        result.update(
            HasLocationTurnout=True,
            RegisteredVoters=registered,
            VotePercent=round(100 * value / registered, 2) if registered and value is not None else 0,
        )
    if locations is not None:
        result["Locations"] = locations
    return result


def _choice(value):
    result = {
        "ChoiceID": "fixture-total",
        "Name": "Complete fixture candidate total",
        "PartyID": "FIX",
        "VotePercent": 0,
        "Votes": [{"VotePercent": 0, "VoteTypeID": "1", "Votes": value}],
    }
    if value:
        result["TotalVotes"] = value
    return result


def source_documents(facts):
    county_declarations = {}
    full_counties = {}
    api_counties = {}
    house_counties = {}
    for county in facts["counties"]:
        county_id = county["county_id"]
        county_declarations[county_id] = {
            "locationID": county_id,
            "locationName": county["county_name"],
            "locations": {},
            "message": None,
        }
        units = {}
        house_units = {}
        for unit in county["units"]:
            units[unit["precinct_id"]] = _turnout_record(
                unit["precinct_id"], unit["ballots"],
                unit["reported_units"], unit["total_units"])
            house_units[unit["precinct_id"]] = {
                "Choices": [_choice(unit["house_candidate_votes"])],
                "LocationID": unit["precinct_id"],
                "LocationName": unit["precinct_name"],
                "PrecinctsReporting": 1,
                "TotalPrecincts": 1,
                "TotalVotes": unit["house_candidate_votes"],
                "WriteinChoices": [],
            }
        full_counties[county_id] = _turnout_record(
            county_id, county["ballots"], county["reported_units"],
            county["total_units"],
            registered=county["registered_voters_retained_only"],
            locations=units,
        )
        api_counties[county_id] = {
            "ballotsCast": [{
                "ballotsCast": county["ballots"],
                "ballotsReceived": county["ballots"],
                "votePercent": 100,
                "voteTypeID": "1",
            }],
            "hasLocationTurnout": True,
            "locationID": county_id,
            "precinctsPartiallyReporting": 0,
            "precinctsReporting": county["reported_units"],
            "registeredVoters": county["registered_voters_retained_only"],
            "reportingPercent": 100 * county["reported_units"] / county["total_units"],
            "totalBallotsCast": county["ballots"],
            "totalPrecincts": county["total_units"],
            "votePercent": round(
                100 * county["ballots"] / county["registered_voters_retained_only"], 2),
        }
        house_counties[county_id] = {
            "Choices": [_choice(county["house_candidate_votes"])],
            "ContestID": "22055",
            "DistrictID": "",
            "HasLocationResults": True,
            "LocationID": county_id,
            "LocationName": county["county_name"],
            "Locations": house_units,
            "PrecinctsReporting": county["reported_units"],
            "TotalPrecincts": county["total_units"],
            "TotalVotes": county["house_candidate_votes"],
            "WriteinChoices": [],
        }
    state_turnout = _turnout_record(
        "state", facts["state_ballots"], facts["state_reported_units"],
        facts["state_total_units"],
        registered=facts["state_registered_voters_retained_only"],
        locations=full_counties,
    )
    state_turnout.pop("LocationID")
    state_turnout.pop("TotalBallotsReceived")
    common = {
        "versionID": facts["version_id"],
        "lastUpdated": facts["last_updated"],
        "electionID": facts["election_id"],
        "message": "",
        "isOfficial": facts["is_official"],
        "turnout": {
            "precinctsPartiallyReporting": 0,
            "precinctsReporting": facts["state_reported_units"],
            "registeredVoters": facts["state_registered_voters_retained_only"],
            "reportingPercent": 100 * facts["state_reported_units"] / facts["state_total_units"],
            "totalBallotsCast": facts["state_ballots"],
            "totalPrecincts": facts["state_total_units"],
            "votePercent": round(
                100 * facts["state_ballots"]
                / facts["state_registered_voters_retained_only"], 2),
        },
        "errorMessage": None,
    }
    election = {
        **common,
        "response": {
            "id": facts["election_id"],
            "name": facts["election_name"],
            "date": facts["election_date"],
            "districts": {"counties": county_declarations},
        },
    }
    turnout = {
        **common,
        "response": {
            "registeredVoters": facts["state_registered_voters_retained_only"],
            "precinctsReporting": facts["state_reported_units"],
            "precinctsPartiallyReporting": 0,
            "totalPrecincts": facts["state_total_units"],
            "totalBallotsCast": facts["state_ballots"],
            "reportingPercent": 100 * facts["state_reported_units"] / facts["state_total_units"],
            "votePercent": round(
                100 * facts["state_ballots"]
                / facts["state_registered_voters_retained_only"], 2),
            "hasLocationTurnout": True,
            "ballotsCast": [{
                "ballotsCast": facts["state_ballots"],
                "ballotsReceived": facts["state_ballots"],
                "votePercent": 100,
                "voteTypeID": "1",
            }],
            "locations": api_counties,
        },
    }
    full = {
        "ElectionData": {
            "ElectionID": facts["election_id"],
            "ElectionMessage": "",
            "IsOfficial": facts["is_official"],
        },
        "TurnoutData": state_turnout,
        "ContestData": [{
            "Choices": [_choice(facts["house_candidate_votes_not_ballots"])],
            "ContestID": facts["house_contest_id"],
            "ContestName": "Representative in Congress",
            "DistrictID": "",
            "HasLocationResults": True,
            "Locations": house_counties,
            "PrecinctsReporting": facts["state_reported_units"],
            "Recounts": [],
            "TotalPrecincts": facts["state_total_units"],
            "TotalVotes": facts["house_candidate_votes_not_ballots"],
            "WriteinChoices": [],
        }],
    }
    return {
        FULL_RESULTS_URL: encoded(full),
        ELECTION_URL: encoded(election),
        TURNOUT_URL: encoded(turnout),
    }
