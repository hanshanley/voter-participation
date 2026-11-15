"""Refresh Rhode Island's reviewed locality participation counts from its official API."""

import copy
from datetime import datetime, timezone
import json
import re
from uuid import UUID

from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_rhode_island_native_participation"
ENTRY_URL = (
    "https://electionresults.ri.gov/results/public/rhodeisland/elections/"
    "2026StatewideGeneralElection"
)
API_URL = (
    "https://electionresults.ri.gov/results/public/api/elections/rhodeisland/"
    "2026StatewideGeneralElection/data"
)
SOURCE_SHA = "bc403b2030f5f6bb48fdc8f04b9172b67870b15046621fcd6415d05dec660fdd"
COUNTY_SOURCE_ID = "accepted-export:" + SOURCE_SHA + ":counties"
NONGEOGRAPHIC_SOURCE_ID = "accepted-export:" + SOURCE_SHA + ":nongeographic"
SOURCE_IDS = {COUNTY_SOURCE_ID, NONGEOGRAPHIC_SOURCE_ID}
STORED_URL = "https://www.themarginoferror.com/participation-local/RI.json.gz"
STORED_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "14114bc6f9026532252ab17e6176dfaa6a8a975f/"
    "data/precinct-results/20261105-rhode-island-02/participation.json.gz"
)
INITIAL_FULL_PIN = "28e757db89ca9ebeed192aa88bbc3fa3a5cd519740556c5d594517c7bfc6a526"
IDENTITY_PIN = "2c5534e70df6580785e25cc9e3681d72b9e1f16d9d89658ae96df77917d623e2"
EXPECTED_ROWS = 40
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
    "mode": "source_defined",
    "unit": "source_reported_count",
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Rhode Island native JSON property")
        result[key] = value
    return result


def _integer(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value < 0
        or int(value) != value
    ):
        raise ValueError("Missing or invalid Rhode Island native count is not zero")
    return int(value)


def _english(values):
    if not isinstance(values, list):
        raise ValueError("Missing Rhode Island source-declared English label")
    matches = [
        row.get("text") for row in values
        if isinstance(row, dict) and row.get("languageId") == "en"
    ]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise ValueError("Missing or ambiguous Rhode Island source-declared English label")
    return matches[0]


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError("Missing Rhode Island native UUID")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ValueError("Malformed Rhode Island native UUID") from error


def _clock(value):
    if not isinstance(value, str) or re.fullmatch(
        r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,7})?Z",
        value,
    ) is None:
        raise ValueError("Changed Rhode Island literal UTC count clock")
    match = re.fullmatch(r"(.+?)(?:\.([0-9]{1,7}))?Z", value)
    fraction = (match.group(2) or "").ljust(6, "0")[:6]
    normalized = match.group(1) + ("." + fraction if fraction else "") + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("Malformed Rhode Island literal UTC count clock") from error
    if parsed.tzinfo != timezone.utc or parsed < datetime(2026, 11, 3, tzinfo=timezone.utc):
        raise ValueError("Rhode Island count clock is outside the declared election")
    return parsed


def _identity(template):
    return {
        "id": template["id"],
        "election": template["election"],
        "geography": template["geography"],
        "measure": template["measure"],
        "source_id": template["source"]["id"],
        "source_locality_id": template["view"]["native_record"]["source_locality_id"],
        "denominator_basis": template["denominator"]["basis"],
        "maps_approved": template["view"]["maps_approved"],
    }


def _inventory(templates, identity=False):
    rows = [_identity(row) if identity else row for row in templates]
    return digest(encoded(sorted(rows, key=lambda row: row["id"])))


def route(template):
    """Return the exact official 2026 API for an accepted Rhode Island locality slot."""
    source = template.get("source") or {}
    if (
        template.get("geography", {}).get("state_code") != "RI"
        or source.get("id") not in SOURCE_IDS
    ):
        return None
    view = template.get("view") or {}
    geography = template.get("geography") or {}
    expected_source = (
        NONGEOGRAPHIC_SOURCE_ID
        if geography.get("level") == "nongeographic"
        else COUNTY_SOURCE_ID
    )
    if (
        template.get("election", {}).get("id") != "us-2026-general-previously-reviewed"
        or template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("date") is not None
        or template.get("election", {}).get("type") != "general"
        or template.get("measure") != MEASURE
        or geography.get("level") not in {"municipality", "nongeographic"}
        or source.get("id") != expected_source
        or (geography.get("level") == "nongeographic")
            != (geography.get("name") == "Federal")
        or (source.get("url"), view.get("source_url"))
        not in ((STORED_URL, STORED_VIEW_URL), (API_URL, API_URL))
    ):
        raise ValueError("Reviewed Rhode Island locality source lineage changed")
    return {"state": "RI", "adapter": ADAPTER, "url": API_URL}


def validate_templates(templates):
    if len(templates) != EXPECTED_ROWS or len({row["id"] for row in templates}) != EXPECTED_ROWS:
        raise ValueError("The complete reviewed Rhode Island locality inventory is required")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("Reviewed Rhode Island identities or qualifications changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_URL]
    if initial and (len(initial) != EXPECTED_ROWS or _inventory(initial) != INITIAL_FULL_PIN):
        raise ValueError("Initial frozen reviewed Rhode Island templates changed")
    locality_ids = set()
    for template in templates:
        if route(template) is None:
            raise ValueError("Reviewed Rhode Island template is not routed")
        source, view = template["source"], template["view"]
        native = view.get("native_record") or {}
        identity = _uuid(native.get("source_locality_id"))
        if identity in locality_ids:
            raise ValueError("Duplicate reviewed Rhode Island locality identity")
        locality_ids.add(identity)
        is_federal = template["geography"]["name"] == "Federal"
        if (
            template["denominator"].get("basis") != "native_registered_voters"
            or template["denominator"].get("qualified") is not False
            or view.get("reported_pct") is not None
            or view.get("maps_approved") is not False
            or source.get("fields") != view
            or view.get("county") != template["geography"]["name"]
            or native.get("locality") != template["geography"]["name"]
            or native.get("reported_pct") is not None
            or template["reporting_status"].get("complete") is not None
            or (template["geography"]["level"] == "nongeographic") != is_federal
        ):
            raise ValueError("Rhode Island rate, map, scope or native-view hold changed")
        if source["url"] == STORED_URL:
            if (
                source.get("input_sha256") != SOURCE_SHA
                or native.get("ballots") != template["count"]["value"]
                or native.get("registered") != template["denominator"]["value"]
                or native.get("source_updated") != template["source_clock"]["literal"]
                or template["source_clock"]["timezone"] is not None
            ):
                raise ValueError("Initial Rhode Island count, denominator or clock changed")
            continue
        query = native.get("query") or {}
        if (
            (native.get("private_original_pin") or {}).get("sha256")
                != source.get("input_sha256")
            or source.get("selector", {}).get("native_refresh") != native
            or query.get("source_locality_id") != identity
            or query.get("locality") != template["geography"]["name"]
            or query.get("ballots") != template["count"]["value"]
            or query.get("registered") != template["denominator"]["value"]
            or query.get("source_updated") != template["source_clock"]["literal"]
            or query.get("source_clock_timezone_literal") != "UTC"
            or native.get("source_clock_timezone_literal") != "UTC"
            or view.get("ballots") != template["count"]["value"]
            or view.get("denominator") != template["denominator"]["value"]
            or template["source_clock"]["timezone"] != "UTC"
        ):
            raise ValueError("Projected Rhode Island count, denominator, clock or source vector differs")


def validate_plan(plan):
    selected = [
        source for source in plan.get("RI", {}).values()
        if source["adapter"] == ADAPTER
    ]
    if not selected:
        return plan
    if len(selected) != 1:
        raise ValueError("Exactly one complete reviewed Rhode Island source is required")
    validate_templates(selected[0]["templates"])
    return plan


def _prior_success(prior, templates):
    if prior is None:
        return None
    data = prior.get("data") if isinstance(prior, dict) else None
    source = prior.get("source") if isinstance(prior, dict) else None
    if data is None and source is None:
        return None
    if (
        not isinstance(data, dict)
        or not isinstance(source, dict)
        or source.get("url") != API_URL
        or not isinstance(source.get("bytes"), int)
        or source["bytes"] < 1
        or not isinstance(source.get("sha256"), str)
        or re.fullmatch(r"[a-f0-9]{64}", source["sha256"]) is None
        or data.get("source_url") != API_URL
    ):
        raise ValueError("Prior Rhode Island captured source declaration is incomplete")
    queries = data.get("complete_native_query")
    updates = data.get("updates")
    if (
        not isinstance(queries, list)
        or len(queries) != 1
        or not isinstance(updates, list)
        or len(updates) != EXPECTED_ROWS
    ):
        raise ValueError("Prior Rhode Island full query/update vector is incomplete")
    query = queries[0]
    source_pin = {"bytes": source["bytes"], "sha256": source["sha256"]}
    rows = query.get("source_locality_rows")
    parent = query.get("separate_source_parent")
    if (
        query.get("source_pin") != source_pin
        or not isinstance(rows, list)
        or len(rows) != EXPECTED_ROWS
        or not isinstance(parent, dict)
        or parent.get("ballots_qualified_for_projection") is not False
        or parent.get("source_clock_timezone_literal") != "UTC"
    ):
        raise ValueError("Prior Rhode Island source pin or complete query changed")
    expected = {
        template["id"]: {
            "source_locality_id": _uuid(
                template["view"]["native_record"]["source_locality_id"]),
            "locality": template["geography"]["name"],
        }
        for template in templates
    }
    prior_rows = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed prior Rhode Island locality query row")
        identity = _uuid(row.get("source_locality_id"))
        if (
            identity in prior_rows
            or set(row) != {
                "source_locality_id", "locality", "source_updated",
                "source_clock_timezone_literal", "ballots", "registered",
            }
            or row["source_clock_timezone_literal"] != "UTC"
        ):
            raise ValueError("Prior Rhode Island locality query identity changed")
        _clock(row["source_updated"])
        _integer(row["ballots"])
        _integer(row["registered"])
        prior_rows[identity] = row
    if set(prior_rows) != {
            row["source_locality_id"] for row in expected.values()}:
        raise ValueError("Prior Rhode Island complete locality query inventory changed")
    for row in expected.values():
        if prior_rows[row["source_locality_id"]]["locality"] != row["locality"]:
            raise ValueError("Prior Rhode Island locality query name changed")
    prior_updates = {}
    for update in updates:
        if not isinstance(update, dict) or set(update) != {
            "id", "value", "native", "registered", "clock",
            "reported_units", "total_units", "rate_compatible",
        }:
            raise ValueError("Prior Rhode Island update vector changed")
        observation_id = update["id"]
        if observation_id in prior_updates or observation_id not in expected:
            raise ValueError("Prior Rhode Island update identity changed")
        row = prior_rows[expected[observation_id]["source_locality_id"]]
        native = update.get("native")
        if (
            not isinstance(native, dict)
            or native.get("query") != row
            or native.get("private_original_pin") != source_pin
            or native.get("source_clock_timezone_literal") != "UTC"
            or native.get("source_updated") != row["source_updated"]
            or native.get("ballots") != row["ballots"]
            or native.get("registered") != row["registered"]
            or update["value"] != row["ballots"]
            or update["registered"] != row["registered"]
            or update["clock"] != row["source_updated"]
            or update["reported_units"] is not None
            or update["total_units"] is not None
            or update["rate_compatible"] is not False
        ):
            raise ValueError("Prior Rhode Island pin/query/update consistency changed")
        prior_updates[observation_id] = update
    if set(prior_updates) != set(expected):
        raise ValueError("Prior Rhode Island update inventory changed")
    parent_clock = parent.get("source_updated")
    parent_ballots = _integer(parent.get("ballots"))
    parent_registered = _integer(parent.get("registered"))
    if (
        parent_ballots != 0
        or sum(row["registered"] for row in prior_rows.values()) != parent_registered
        or any(_clock(row["source_updated"]) > _clock(parent_clock)
               for row in prior_rows.values())
        or type(parent.get("is_official_results")) is not bool
        or data.get("declared_entry_url") != ENTRY_URL
        or data.get("geographic_joins_changed") is not False
        or data.get("analytical_rates_promoted") is not False
    ):
        raise ValueError("Prior Rhode Island source parent/query reconciliation changed")
    reconciliation = query.get("reconciliation")
    federal = [
        row for row in prior_rows.values() if row["locality"] == "Federal"]
    if (
        len(federal) != 1
        or not isinstance(reconciliation, dict)
        or reconciliation != {
            "source_locality_rows": EXPECTED_ROWS,
            "municipalities": EXPECTED_ROWS - 1,
            "municipal_ballots_literal_sum": sum(
                row["ballots"] for row in prior_rows.values()
                if row["locality"] != "Federal"),
            "federal_ballots_unallocated": federal[0]["ballots"],
            "federal_registered_literal": federal[0]["registered"],
            "locality_registered_sum_matches_separate_parent": True,
            "source_parent_ballots_remain_unqualified": True,
            "candidate_votes_used_as_ballots": False,
            "state_parent_derived_from_locality_sum": False,
        }
    ):
        raise ValueError("Prior Rhode Island complete reconciliation changed")
    return {"rows": prior_rows, "parent": parent}


def statistics(body, templates, url, *, prior=None):
    if url != API_URL:
        raise ValueError("Unreviewed Rhode Island native product")
    validate_templates(templates)
    prior_success = _prior_success(prior, templates)
    document = json.loads(body, object_pairs_hook=_object)
    if not isinstance(document, dict):
        raise ValueError("Changed Rhode Island native JSON envelope")
    jurisdiction = document.get("jurisdiction")
    election = document.get("election")
    locality_rows = document.get("localityElections")
    if (
        not isinstance(jurisdiction, dict)
        or not isinstance(election, dict)
        or not isinstance(locality_rows, list)
        or election.get("electionDate") != "2026-11-03"
        or _english(election.get("name")) != "Statewide General Election"
        or _english(jurisdiction.get("name")) != "Rhode Island"
        or election.get("isPrimary") is not False
        or type(election.get("isOfficialResults")) is not bool
        or type(election.get("isProduction")) is not bool
        or election.get("isProduction") is not True
    ):
        raise ValueError("Changed Rhode Island 2026 general-election declaration")
    parent_clock = election.get("asOf")
    _clock(parent_clock)
    parent_ballots = _integer(election.get("ballotsCast"))
    parent_registered = _integer(election.get("totalVoters"))
    if parent_ballots != 0:
        raise ValueError("Rhode Island source parent ballots are no longer the reviewed zero placeholder")

    children = jurisdiction.get("childLocalities")
    if not isinstance(children, list):
        raise ValueError("Missing Rhode Island source locality declarations")
    child_names = {}
    for child in children:
        if not isinstance(child, dict):
            raise ValueError("Malformed Rhode Island source locality declaration")
        identity = _uuid(child.get("id"))
        if identity in child_names:
            raise ValueError("Duplicate Rhode Island source locality declaration")
        child_names[identity] = _english(child.get("name"))

    native_rows = {}
    for row in locality_rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed Rhode Island native locality row")
        identity = _uuid(row.get("jurisdictionId"))
        if identity in native_rows:
            raise ValueError("Duplicate Rhode Island native locality row")
        clock = row.get("asOf")
        if _clock(clock) > _clock(parent_clock):
            raise ValueError("Rhode Island locality clock is later than the source parent")
        native_rows[identity] = {
            "source_locality_id": identity,
            "locality": child_names.get(identity),
            "source_updated": clock,
            "source_clock_timezone_literal": "UTC",
            "ballots": _integer(row.get("ballotsCast")),
            "registered": _integer(row.get("totalVoters")),
        }

    expected = {
        _uuid(template["view"]["native_record"]["source_locality_id"]): template
        for template in templates
    }
    if (
        len(expected) != EXPECTED_ROWS
        or set(native_rows) != set(expected)
        or set(child_names) != set(expected)
    ):
        raise ValueError("Rhode Island complete native locality inventory changed")

    updates = []
    ordered_rows = []
    for identity, template in sorted(expected.items(), key=lambda item: item[1]["id"]):
        row = native_rows[identity]
        if row["locality"] != template["geography"]["name"]:
            raise ValueError("Changed literal Rhode Island locality identity/name")
        if row["locality"] != "Federal" and row["ballots"] > row["registered"]:
            raise ValueError("Rhode Island municipal ballots exceed native registration")
        if (
            prior_success is not None
            and _clock(row["source_updated"])
                < _clock(prior_success["rows"][identity]["source_updated"])
        ):
            raise ValueError("Rhode Island native locality count clock regressed from prior capture")
        previous_clock = template["source_clock"].get("literal")
        if previous_clock is not None and _clock(row["source_updated"]) < _clock(previous_clock):
            raise ValueError("Rhode Island native locality count clock regressed")
        native = copy.deepcopy(template["view"]["native_record"])
        native.update(
            locality=row["locality"],
            source_locality_id=identity,
            source_updated=row["source_updated"],
            source_clock_timezone_literal="UTC",
            ballots=row["ballots"],
            registered=row["registered"],
            reported_pct=None,
            private_original_pin=pin(body),
            native_reporting_complete_qualified=False,
            analytical_rates_promoted=False,
            state_parent_ballots_unqualified=True,
            federal_reporting_unit_unallocated=row["locality"] == "Federal",
            query=copy.deepcopy(row),
        )
        updates.append({
            "id": template["id"],
            "value": row["ballots"],
            "native": native,
            "registered": row["registered"],
            "clock": row["source_updated"],
            "reported_units": None,
            "total_units": None,
            "rate_compatible": False,
        })
        ordered_rows.append(copy.deepcopy(row))

    if sum(row["registered"] for row in ordered_rows) != parent_registered:
        raise ValueError("Rhode Island locality registrations disagree with the separate source parent")
    if (
        prior_success is not None
        and _clock(parent_clock) < _clock(prior_success["parent"]["source_updated"])
    ):
        raise ValueError("Rhode Island source parent clock regressed from prior capture")
    municipal_ballots = sum(
        row["ballots"] for row in ordered_rows if row["locality"] != "Federal"
    )
    federal = next(row for row in ordered_rows if row["locality"] == "Federal")
    return {
        "updates": updates,
        "complete_native_query": [{
            "source_pin": pin(body),
            "source_locality_rows": ordered_rows,
            "separate_source_parent": {
                "ballots": parent_ballots,
                "registered": parent_registered,
                "source_updated": parent_clock,
                "source_clock_timezone_literal": "UTC",
                "is_official_results": election["isOfficialResults"],
                "ballots_qualified_for_projection": False,
            },
            "reconciliation": {
                "source_locality_rows": len(ordered_rows),
                "municipalities": len(ordered_rows) - 1,
                "municipal_ballots_literal_sum": municipal_ballots,
                "federal_ballots_unallocated": federal["ballots"],
                "federal_registered_literal": federal["registered"],
                "locality_registered_sum_matches_separate_parent": True,
                "source_parent_ballots_remain_unqualified": True,
                "candidate_votes_used_as_ballots": False,
                "state_parent_derived_from_locality_sum": False,
            },
        }],
        "source_url": API_URL,
        "declared_entry_url": ENTRY_URL,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }
