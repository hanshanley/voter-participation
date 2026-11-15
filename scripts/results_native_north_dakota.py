"""Refresh reviewed North Dakota native ballot observations from official JSON."""

import copy
from datetime import datetime, timezone
import json
import re

from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_north_dakota_native_turnout"
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
STORED_SOURCE_URL = "https://www.themarginoferror.com/participation-local/ND.json.gz"
STORED_COUNTY_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "2e7b240d3cece70001ef573dd487538d46ebd5cd/data/precinct-results/"
    "20261105-north-dakota-02/originals/full-results.json.gz"
)
STORED_UNIT_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "2e7b240d3cece70001ef573dd487538d46ebd5cd/data/precinct-results/"
    "20261105-north-dakota-02/participation.json.gz"
)
EXPORT_SHA = "14ba49ba698b3fa4ebe3ee2e846f964f4f13e7b882f7a3cd66a89eee7df77783"
COUNTY_SOURCE_ID = f"accepted-export:{EXPORT_SHA}:counties"
UNIT_SOURCE_ID = f"accepted-export:{EXPORT_SHA}:precincts"
INITIAL_INVENTORY_PIN = "d56f64d69499222def0af694f5cdb8141240506bd135dfa2b679e69cbc70b779"
OBSERVATION_IDS_PIN = "0fda52b0ff1f697b0717e747670f7b4be62f4eebcbf84f412faedefa0acc15f5"
EXPECTED_COUNTIES = 53
EXPECTED_UNITS = 358


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate North Dakota JSON property")
        result[key] = value
    return result


def _document(body, label):
    try:
        value = json.loads(body, object_pairs_hook=_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Unreadable North Dakota {label} JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"Changed North Dakota {label} envelope")
    return value


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Missing or invalid North Dakota {label} is not zero")
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid North Dakota {label}")
    return value


def _clock(value):
    match = re.fullmatch(
        r"(202[67]-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]{1,9}))?Z",
        value or "",
    )
    if match is None:
        raise ValueError("North Dakota source clock is missing explicit UTC")
    try:
        fraction = (match.group(2) or "")[:6].ljust(6, "0")
        parsed = datetime.fromisoformat(
            match.group(1) + ("." + fraction if fraction else "") + "+00:00")
    except ValueError as error:
        raise ValueError("Changed North Dakota source clock") from error
    if not (
        datetime(2026, 11, 3, tzinfo=timezone.utc)
        <= parsed
        < datetime(2027, 2, 1, tzinfo=timezone.utc)
    ):
        raise ValueError("North Dakota source clock is outside the declared election")
    return parsed


def _status(value):
    if type(value) is not bool:
        raise ValueError("North Dakota official-status field is not a literal boolean")
    return "IsOfficial=true" if value else "IsOfficial=false"


def _keys(value, required, optional, label):
    if not isinstance(value, dict) or not set(required) <= set(value) \
            or set(value) - set(required) - set(optional):
        raise ValueError(f"Changed North Dakota {label} fields")


def _bucket(record, label):
    value = record.get("TotalBallotsCast")
    buckets = record.get("BallotsCast")
    if value is None:
        if buckets in (None, []):
            return None
        if (
            isinstance(buckets, list)
            and len(buckets) == 1
            and set(buckets[0]) == {
                "BallotsCast", "BallotsReceived", "VotePercent", "VoteTypeID"
            }
            and buckets[0]["VoteTypeID"] == "1"
            and buckets[0]["BallotsCast"] == buckets[0]["BallotsReceived"] == 0
            and buckets[0]["VotePercent"] == 0
            and record.get("PrecinctsReporting") == record.get("TotalPrecincts")
        ):
            return 0
        raise ValueError(f"Unknown North Dakota {label} has ballot bucket values")
    value = _integer(value, label)
    if (
        not isinstance(buckets, list)
        or len(buckets) != 1
        or set(buckets[0]) != {
            "BallotsCast", "BallotsReceived", "VotePercent", "VoteTypeID"
        }
        or buckets[0]["VoteTypeID"] != "1"
        or _integer(buckets[0]["BallotsCast"], label) != value
        or _integer(buckets[0]["BallotsReceived"], label) != value
        or _number(buckets[0]["VotePercent"], label) != (0 if value == 0 else 100)
    ):
        raise ValueError(f"North Dakota {label} ballot bucket differs")
    received = record.get("TotalBallotsReceived")
    if received is not None and _integer(received, label) != value:
        raise ValueError(f"North Dakota {label} ballots received differs")
    return value


def _canonical_identity(template):
    level = template["geography"]["level"]
    native = template.get("view", {}).get("native_record") or {}
    identity = native.get("canonical_identity") if isinstance(native, dict) else None
    if isinstance(identity, dict):
        result = identity
    elif level == "county":
        result = {
            "state_code": "ND",
            "county_id": native.get("LocationID"),
            "county_name": template["geography"]["name"],
            "precinct_id": None,
            "precinct_name": None,
        }
    else:
        result = {
            "state_code": native.get("state_code"),
            "county_id": native.get("county"),
            "county_name": native.get("county_name"),
            "precinct_id": native.get("precinct"),
            "precinct_name": native.get("precinct_name"),
        }
    county = result.get("county_id")
    if (
        result.get("state_code") != "ND"
        or not isinstance(county, str)
        or not re.fullmatch(r"38[0-9]{3}", county)
        or not isinstance(result.get("county_name"), str)
        or not result["county_name"]
    ):
        raise ValueError("North Dakota accepted county identity changed")
    if level == "county":
        if result.get("precinct_id") is not None or result.get("precinct_name") is not None:
            raise ValueError("North Dakota county was relabelled as a reporting unit")
    elif (
        level != "reporting_unit"
        or not isinstance(result.get("precinct_id"), str)
        or not result["precinct_id"]
        or not isinstance(result.get("precinct_name"), str)
        or not result["precinct_name"]
    ):
        raise ValueError("North Dakota accepted reporting-unit identity changed")
    return result


def route(template):
    """Route only the two exact reviewed North Dakota count families."""
    source = template.get("source", {})
    view = template.get("view", {})
    level = template.get("geography", {}).get("level")
    source_id = COUNTY_SOURCE_ID if level == "county" else UNIT_SOURCE_ID
    stored_view = STORED_COUNTY_VIEW_URL if level == "county" else STORED_UNIT_VIEW_URL
    if source.get("id") != source_id:
        return None
    if (
        template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("date") not in (None, "2026-11-03")
        or template.get("election", {}).get("type") != "general"
        or template.get("geography", {}).get("state_code") != "ND"
        or level not in ("county", "reporting_unit")
        or template.get("measure", {}).get("kind") != "participation_reported"
        or template.get("measure", {}).get("mode") != "source_defined"
        or template.get("measure", {}).get("unit") != "source_reported_count"
        or template.get("denominator") is not None
        or view.get("reported_pct") is not None
        or (source.get("url"), view.get("source_url"))
           not in ((STORED_SOURCE_URL, stored_view),
                   (FULL_RESULTS_URL, FULL_RESULTS_URL))
    ):
        raise ValueError("North Dakota reviewed source lineage or qualification changed")
    _canonical_identity(template)
    return {"state": "ND", "adapter": ADAPTER, "url": FULL_RESULTS_URL}


def validate_templates(templates):
    if (
        len(templates) != EXPECTED_COUNTIES + EXPECTED_UNITS
        or len({row["id"] for row in templates}) != len(templates)
        or sum(row["geography"]["level"] == "county" for row in templates)
           != EXPECTED_COUNTIES
        or sum(row["geography"]["level"] == "reporting_unit" for row in templates)
           != EXPECTED_UNITS
    ):
        raise ValueError("Complete reviewed North Dakota county/unit inventory is required")
    if digest(encoded(sorted(row["id"] for row in templates))) != OBSERVATION_IDS_PIN:
        raise ValueError("North Dakota reviewed observation IDs changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_SOURCE_URL]
    if initial:
        if (
            len(initial) != len(templates)
            or digest(encoded(sorted(templates, key=lambda row: row["id"])))
               != INITIAL_INVENTORY_PIN
        ):
            raise ValueError("North Dakota accepted frozen template inventory changed")
    elif not all(
        row.get("view", {}).get("automatic_source_refresh") is True
        and route(row) is not None
        for row in templates
    ):
        raise ValueError("North Dakota projected template inventory is not reusable")
    identities = []
    for template in templates:
        if route(template) is None:
            raise ValueError("North Dakota reviewed template is not routable")
        identity = _canonical_identity(template)
        key = identity["county_id"], identity.get("precinct_id")
        identities.append(key)
        if template["geography"]["level"] == "county" and (
            template["geography"]["id"] != f"ND|additional:ND:{key[0]}|"
            or template["geography"]["name"] != identity["county_name"]
        ):
            raise ValueError("North Dakota accepted county canonical slot changed")
        if template["geography"]["level"] == "reporting_unit" and (
            template["geography"]["parent_id"] != f"ND|additional:ND:{key[0]}"
            or template["geography"]["name"] != identity["precinct_name"]
        ):
            raise ValueError("North Dakota accepted reporting-unit canonical slot changed")
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate North Dakota accepted literal identity")


def validate_plan(plan):
    candidates = [
        template
        for source in plan.get("ND", {}).values()
        if source.get("adapter") == ADAPTER
        for template in source.get("templates", [])
    ]
    if candidates:
        validate_templates(candidates)
        selected = [
            source for source in plan["ND"].values()
            if source.get("adapter") == ADAPTER
        ]
        if len(selected) != 1 or selected[0]["url"] != FULL_RESULTS_URL:
            raise ValueError("North Dakota reviewed families must share one full-data source")
    return plan


def _authority(document, label):
    expected = {
        "versionID", "lastUpdated", "electionID", "message", "isOfficial",
        "turnout", "response", "errorMessage",
    }
    if set(document) != expected or document["electionID"] != "348" \
            or document["errorMessage"] is not None:
        raise ValueError(f"Changed North Dakota {label} authority envelope")
    if not re.fullmatch(r"v[0-9]+", document["versionID"]):
        raise ValueError("Changed North Dakota native version")
    _clock(document["lastUpdated"])
    _status(document["isOfficial"])
    turnout = document["turnout"]
    if not isinstance(turnout, dict):
        raise ValueError(f"Missing North Dakota {label} turnout declaration")
    for key in ("precinctsReporting", "totalPrecincts", "totalBallotsCast"):
        _integer(turnout.get(key), f"{label} {key}")
    return document


def _choice_total(choice):
    votes = choice.get("Votes")
    if (
        not isinstance(votes, list)
        or len(votes) != 1
        or votes[0].get("VoteTypeID") != "1"
    ):
        raise ValueError("Changed North Dakota House vote bucket")
    value = _integer(votes[0].get("Votes"), "House candidate votes")
    if choice.get("TotalVotes", value) != value:
        raise ValueError("North Dakota House candidate total differs")
    return value


def _house(document, unit_ballots, county_names):
    contests = [
        contest for contest in document
        if str(contest.get("ContestID")) == "22055"
    ]
    if len(contests) != 1:
        raise ValueError("North Dakota House contest 22055 changed")
    contest = contests[0]
    if (
        contest.get("ContestName") != "Representative in Congress"
        or contest.get("HasLocationResults") is not True
        or set(contest.get("Locations", {})) != set(county_names)
    ):
        raise ValueError("North Dakota House contest scope changed")
    total = _integer(contest.get("TotalVotes"), "House statewide candidate votes")
    if sum(_choice_total(choice) for choice in contest.get("Choices", [])) != total:
        raise ValueError("North Dakota statewide House choices do not reconcile")
    observed = {}
    county_totals = 0
    for county_id, county in contest["Locations"].items():
        if (
            county.get("LocationID") != county_id
            or county.get("LocationName") != county_names[county_id]
            or not isinstance(county.get("Locations"), dict)
        ):
            raise ValueError("North Dakota House county identity changed")
        subtotal = 0
        for precinct_id, row in county["Locations"].items():
            if (
                row.get("LocationID") != precinct_id
                or not isinstance(row.get("LocationName"), str)
                or (county_id, precinct_id) in observed
            ):
                raise ValueError("North Dakota House reporting-unit identity changed")
            choice_total = sum(_choice_total(choice) for choice in row.get("Choices", []))
            value = row.get("TotalVotes")
            if value is None and choice_total == 0 \
                    and row.get("PrecinctsReporting") == row.get("TotalPrecincts"):
                value = 0
            value = _integer(value, "House reporting-unit candidate votes")
            if choice_total != value:
                raise ValueError("North Dakota House reporting-unit choices do not reconcile")
            ballots = unit_ballots.get((county_id, precinct_id))
            if ballots is not None and value > ballots:
                raise ValueError("North Dakota House candidate votes exceed ballots")
            observed[county_id, precinct_id] = {
                "county_id": county_id,
                "precinct_id": precinct_id,
                "precinct_name": row["LocationName"],
                "candidate_votes": value,
            }
            subtotal += value
        county_total = _integer(county.get("TotalVotes"), "House county candidate votes")
        if subtotal != county_total:
            raise ValueError("North Dakota House reporting units do not reconcile to county")
        county_totals += county_total
    if set(observed) != set(unit_ballots) or county_totals != total:
        raise ValueError("North Dakota House native reporting-unit inventory changed")
    return total, observed


def statistics(body, templates, url, *, acquire):
    """Parse the complete official full-data file and independent authority parents."""
    if url != FULL_RESULTS_URL:
        raise ValueError("Unreviewed North Dakota native product")
    validate_templates(templates)
    election_body, election_receipt = acquire(ELECTION_URL)
    turnout_body, turnout_receipt = acquire(TURNOUT_URL)
    full = _document(body, "full-results")
    election = _authority(_document(election_body, "election"), "election")
    turnout = _authority(_document(turnout_body, "turnout"), "turnout")
    if set(full) != {"ElectionData", "TurnoutData", "ContestData"}:
        raise ValueError("Changed North Dakota full-results envelope")
    election_data = full["ElectionData"]
    if (
        not isinstance(election_data, dict)
        or set(election_data) != {"ElectionID", "ElectionMessage", "IsOfficial"}
        or election_data["ElectionID"] != "348"
    ):
        raise ValueError("Changed North Dakota full-results election declaration")
    response = election["response"]
    if (
        not isinstance(response, dict)
        or response.get("id") != "348"
        or response.get("name") != "2026 General Election"
        or response.get("date") != "2026-11-03T00:00:00"
    ):
        raise ValueError("Changed North Dakota publisher election declaration")
    statuses = {
        _status(election["isOfficial"]),
        _status(turnout["isOfficial"]),
        _status(election_data["IsOfficial"]),
    }
    if len(statuses) != 1:
        raise ValueError("North Dakota official-status declarations disagree")
    if (
        election["versionID"] != turnout["versionID"]
        or election["lastUpdated"] != turnout["lastUpdated"]
    ):
        raise ValueError("North Dakota election/turnout version or clock differs")
    source_clock = election["lastUpdated"]
    source_version = election["versionID"]
    declared = (((response.get("districts") or {}).get("counties")) or {})
    if not isinstance(declared, dict) or len(declared) != EXPECTED_COUNTIES:
        raise ValueError("Changed North Dakota declared county inventory")
    county_names = {}
    for county_id, row in declared.items():
        if (
            not re.fullmatch(r"38[0-9]{3}", county_id)
            or row.get("locationID") != county_id
            or not isinstance(row.get("locationName"), str)
            or not row["locationName"]
        ):
            raise ValueError("Changed North Dakota declared literal county identity")
        county_names[county_id] = row["locationName"]
    state = full["TurnoutData"]
    _keys(
        state,
        {
            "BallotsCast", "HasLocationTurnout", "Locations", "PrecinctsReporting",
            "RegisteredVoters", "ReportingPercent", "TotalBallotsCast",
            "TotalPrecincts", "VotePercent",
        },
        set(),
        "state turnout",
    )
    if state["HasLocationTurnout"] is not True or set(state["Locations"]) != set(county_names):
        raise ValueError("Changed North Dakota full native county scope")
    state_value = _bucket(state, "state ballots")
    api = turnout["response"]
    if not isinstance(api, dict) or set(api.get("locations", {})) != set(county_names):
        raise ValueError("Changed North Dakota independent turnout county scope")
    county_facts, unit_facts = {}, {}
    for county_id, record in state["Locations"].items():
        _keys(
            record,
            {
                "BallotsCast", "HasLocationTurnout", "LocationID", "Locations",
                "PrecinctsReporting", "RegisteredVoters", "ReportingPercent",
                "TotalBallotsCast", "TotalBallotsReceived", "TotalPrecincts",
                "VotePercent",
            },
            set(),
            "county turnout",
        )
        if (
            record["LocationID"] != county_id
            or record["HasLocationTurnout"] is not True
            or not isinstance(record["Locations"], dict)
        ):
            raise ValueError("Changed North Dakota full native county identity")
        value = _bucket(record, "county ballots")
        reported = _integer(record["PrecinctsReporting"], "county reported units")
        total = _integer(record["TotalPrecincts"], "county total units")
        if reported > total:
            raise ValueError("North Dakota county reported units exceed total")
        units = {}
        for precinct_id, leaf in record["Locations"].items():
            _keys(
                leaf,
                {"LocationID", "PrecinctsReporting", "ReportingPercent", "TotalPrecincts"},
                {"BallotsCast", "TotalBallotsCast", "TotalBallotsReceived"},
                "reporting-unit turnout",
            )
            if leaf["LocationID"] != precinct_id or not isinstance(precinct_id, str) \
                    or not precinct_id:
                raise ValueError("Changed North Dakota literal reporting-unit identity")
            leaf_reported = _integer(
                leaf["PrecinctsReporting"], "reporting-unit reported units")
            leaf_total = _integer(leaf["TotalPrecincts"], "reporting-unit total units")
            leaf_value = _bucket(leaf, "reporting-unit ballots")
            if leaf_reported > leaf_total or (leaf_value is None and leaf_reported == leaf_total):
                raise ValueError("North Dakota missing reporting-unit count is not qualified unknown")
            units[precinct_id] = leaf_value
            unit_facts[county_id, precinct_id] = {
                "county_id": county_id,
                "county_name": county_names[county_id],
                "precinct_id": precinct_id,
                "value": leaf_value,
                "reported_units": leaf_reported,
                "total_units": leaf_total,
                "record": copy.deepcopy(leaf),
            }
        known = [item for item in units.values() if item is not None]
        if len(units) != total or sum(known) != value \
                or (len(known) != len(units) and reported == total):
            raise ValueError("North Dakota reporting-unit ballots do not reconcile to county")
        independent = api["locations"][county_id]
        if (
            independent.get("locationID") != county_id
            or _integer(independent.get("totalBallotsCast"), "independent county ballots")
               != value
            or _integer(independent.get("precinctsReporting"), "independent reported units")
               != reported
            or _integer(independent.get("totalPrecincts"), "independent total units")
               != total
        ):
            raise ValueError("North Dakota full-data and independent county parents differ")
        county_facts[county_id] = {
            "county_id": county_id,
            "county_name": county_names[county_id],
            "value": value,
            "reported_units": reported,
            "total_units": total,
            "record": copy.deepcopy(record),
        }
    if (
        len(unit_facts) != EXPECTED_UNITS
        or sum(item["value"] for item in county_facts.values()) != state_value
        or _integer(api.get("totalBallotsCast"), "independent statewide ballots")
           != state_value
        or _integer(api.get("precinctsReporting"), "independent statewide reported units")
           != _integer(state["PrecinctsReporting"], "state reported units")
        or _integer(api.get("totalPrecincts"), "independent statewide total units")
           != _integer(state["TotalPrecincts"], "state total units")
    ):
        raise ValueError("North Dakota county/state ballot parents do not reconcile")
    house_total, house_units = _house(
        full["ContestData"],
        {key: value["value"] for key, value in unit_facts.items()},
        county_names,
    )
    accepted = {}
    for template in templates:
        identity = _canonical_identity(template)
        key = identity["county_id"], identity.get("precinct_id")
        if key in accepted:
            raise ValueError("Duplicate North Dakota accepted canonical slot")
        accepted[key] = template, identity
    expected = {(key, None) for key in county_facts} | set(unit_facts)
    if set(accepted) != expected:
        raise ValueError(
            "North Dakota source inventory differs; identity onboarding requires review")
    updates = []
    for key, (template, identity) in accepted.items():
        fact = county_facts[key[0]] if key[1] is None else unit_facts[key]
        if key[1] is not None:
            house = house_units[key]
            if house["precinct_name"] != identity["precinct_name"]:
                raise ValueError("North Dakota House/turnout reporting-unit names differ")
        native = {
            "canonical_identity": copy.deepcopy(identity),
            "record": copy.deepcopy(fact["record"]),
            "query": {
                "canonical_identity": copy.deepcopy(identity),
                "source_clock_timezone_literal": "UTC",
            },
            "source_clock_timezone_literal": "UTC",
            "source_version": source_version,
            "source_status_literal": next(iter(statuses)),
            "native_reporting_complete_qualified": False,
            "registered_voters_retained_not_analytical_denominator":
                fact["record"].get("RegisteredVoters"),
            "house_candidate_votes_not_ballots":
                None if key[1] is None else house_units[key]["candidate_votes"],
            "analytical_denominator": None,
            "analytical_rate": None,
            "geographic_join_changed": False,
        }
        updates.append({
            "id": template["id"],
            "value": fact["value"],
            "native": native,
            "registered": None,
            "clock": source_clock,
            "reported_units": fact["reported_units"],
            "total_units": fact["total_units"],
            "rate_compatible": False,
        })
    source_pin = pin(body)
    query = {
        "source_pin": source_pin,
        "election_input_pin": pin(election_body),
        "turnout_input_pin": pin(turnout_body),
        "election_id": "348",
        "house_contest_id": "22055",
        "source_version": source_version,
        "source_updated_at": source_clock,
        "source_status_literal": next(iter(statuses)),
        "state_ballots": state_value,
        "county_rows": len(county_facts),
        "reporting_unit_rows": len(unit_facts),
        "house_candidate_votes_not_ballots": house_total,
        "county_and_statewide_turnout_parents_reconcile": True,
        "house_candidate_votes_do_not_replace_ballots": True,
        "all_analytical_denominators_and_rates_withheld": True,
        "geographic_joins_changed": False,
        "counties": [
            {key: value[key] for key in (
                "county_id", "county_name", "value", "reported_units", "total_units")}
            for value in county_facts.values()
        ],
        "reporting_units": [
            {
                **{name: value[name] for name in (
                    "county_id", "county_name", "precinct_id", "value",
                    "reported_units", "total_units")},
                "precinct_name": house_units[key]["precinct_name"],
                "house_candidate_votes_not_ballots":
                    house_units[key]["candidate_votes"],
            }
            for key, value in unit_facts.items()
        ],
    }
    return {
        "updates": updates,
        "complete_native_query": [query],
        "source_url": FULL_RESULTS_URL,
        "numerical_input_pins": {
            "full_results": source_pin,
            "election": pin(election_body),
            "turnout": pin(turnout_body),
        },
        "source_authority": {
            "publisher": "North Dakota Secretary of State",
            "full_results_url": FULL_RESULTS_URL,
            "election_declaration_url": ELECTION_URL,
            "independent_turnout_url": TURNOUT_URL,
            "retained_receipts_required": True,
        },
        "source_registration": {
            "contract": "participation.reviewed_multi_partition_source_registration.v1",
            "stored_source_url": STORED_SOURCE_URL,
            "stored_view_urls": [STORED_COUNTY_VIEW_URL, STORED_UNIT_VIEW_URL],
            "reviewed_url": FULL_RESULTS_URL,
            "source_ids": [COUNTY_SOURCE_ID, UNIT_SOURCE_ID],
            "prior_full_inventory_pin": INITIAL_INVENTORY_PIN,
            "observation_ids_pin": OBSERVATION_IDS_PIN,
        },
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "new_identity_onboarding": False,
    }


__all__ = [
    "ADAPTER", "ELECTION_URL", "FULL_RESULTS_URL", "TURNOUT_URL",
    "route", "statistics", "validate_plan", "validate_templates",
]
