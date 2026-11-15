"""Refresh the reviewed North Carolina state/county reported-ballot family."""

import copy
from datetime import datetime
import json
import re

from scripts.current import reporting_counts
from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_north_carolina_reporting"
CONTRACT = "participation.north_carolina_reporting.v1"
URL = "https://er.ncsbe.gov/enr/20261103/data/county.txt"
COUNTY_SOURCE_ID = (
    "accepted-export:0128bda2273d19a9ed9afd620a509d858374add4ec4ca84e80dfd0c69c1de04f:"
    "counties"
)
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
INITIAL_FULL_PIN = "fc360a8a500f6d376cd246fa9aaa662f0baf57fcd2ec002e9dde488b75b2c4af"
IDENTITY_PIN = "44d070555152b8eaea56d66af03efea1e4343f51b5566c7ca4a727a36939830e"
OBSERVATION_IDS_PIN = "036b365ca9c25e38f616b277054580209582fe0eb923f8471b91dc7b80c4837a"
FIELDS = {
    "bct", "bpt", "cid", "cnm", "imp", "ppt", "prt", "ptl", "rtl", "sub", "tle", "vwp",
}
COUNT_LITERAL = re.compile(r"[0-9]+")
PERCENT_LITERAL = re.compile(r"[0-9]+(?:\.[0-9]+)?%")
CLOCK_FORMAT = "%B %d, %Y %I:%M %p"


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate North Carolina native JSON property")
        result[key] = value
    return result


def _integer(value, field):
    if not isinstance(value, str) or COUNT_LITERAL.fullmatch(value) is None:
        raise ValueError("Missing or invalid North Carolina " + field + " is not zero")
    return int(value)


def _clock(value):
    if not isinstance(value, str):
        raise ValueError("Missing North Carolina native source clock")
    try:
        result = datetime.strptime(value, CLOCK_FORMAT)
    except ValueError as error:
        raise ValueError("Changed North Carolina native source clock format") from error
    if not datetime(2026, 11, 3) <= result < datetime(2027, 2, 1):
        raise ValueError("North Carolina source clock is outside the reviewed election")
    return result


def _county_id(template):
    native = template["view"].get("native_record") or {}
    query = native.get("query") or {}
    identity = str(query.get("county_id", ""))
    if not identity:
        raise ValueError("North Carolina accepted county identity is missing")
    return identity


def _identity(template):
    return {
        "id": template["id"],
        "election": template["election"],
        "geography": template["geography"],
        "measure": template["measure"],
        "source_id": template["source"]["id"],
        "county_id": _county_id(template),
        "county": template["view"]["county"],
        "denominator_basis": template["denominator"]["basis"],
        "source_clock_timezone": template["source_clock"]["timezone"],
        "join": template["geography"]["join"],
    }


def _inventory(templates, identity=False):
    rows = [_identity(row) if identity else row for row in templates]
    return digest(encoded(sorted(rows, key=lambda row: row["id"])))


def route(template):
    """Route only the accepted 100-county aggregate family to the official source."""
    source = template.get("source") or {}
    if (
        source.get("id") != COUNTY_SOURCE_ID
        or template.get("geography", {}).get("state_code") != "NC"
    ):
        return None
    view = template.get("view") or {}
    if (
        template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("type") != "general"
        or template.get("geography", {}).get("state_code") != "NC"
        or template.get("measure") != MEASURE
        or template.get("denominator", {}).get("basis")
        != "active_and_inactive_registered_voters"
        or view.get("source_url") != URL
    ):
        raise ValueError("Reviewed North Carolina participation lineage changed")
    if template["geography"]["level"] != "county" or source.get("url") != URL:
        raise ValueError("Reviewed North Carolina county source bridge changed")
    return {"state": "NC", "adapter": ADAPTER, "url": URL}


def _projected_vector(template):
    native = template["view"].get("native_record") or {}
    query = native.get("query") or {}
    if (
        query.get("county_id") != _county_id(template)
        or query.get("ballots") != template["count"]["value"]
        or query.get("registered") != template["denominator"]["value"]
        or query.get("reported_units") != template["reporting_status"]["reported_units"]
        or query.get("total_units") != template["reporting_status"]["total_units"]
        or query.get("source_clock_literal") != template["source_clock"]["literal"]
        or query.get("source_clock_timezone") is not None
        or native.get("source_original_pin", {}).get("sha256")
        != template["source"]["input_sha256"]
        or template["source"].get("selector", {}).get("native_refresh") != native
        or template["source"]["url"] != URL
        or template["view"]["source_url"] != URL
    ):
        raise ValueError("Projected North Carolina count/query/source vector differs")


def validate_templates(templates):
    if len(templates) != 100 or len({row["id"] for row in templates}) != 100:
        raise ValueError("Complete 100-county North Carolina family is required")
    if digest(encoded(sorted(row["id"] for row in templates))) != OBSERVATION_IDS_PIN:
        raise ValueError("North Carolina observation identities changed")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("North Carolina geography, measure or qualification identities changed")
    if {_county_id(row) for row in templates} != {str(index) for index in range(1, 101)}:
        raise ValueError("North Carolina county native inventory changed")
    if any(route(row) is None for row in templates):
        raise ValueError("North Carolina family contains an unreviewed route")
    projected = [row["view"].get("automatic_source_refresh") is True for row in templates]
    if any(projected) and not all(projected):
        raise ValueError("North Carolina family mixes accepted and projected rows")
    if not any(projected):
        if _inventory(templates) != INITIAL_FULL_PIN:
            raise ValueError("Initial complete North Carolina accepted family changed")
    else:
        for template in templates:
            _projected_vector(template)


def validate_plan(plan):
    sources = [
        source for source in plan.get("NC", {}).values()
        if source.get("adapter") == ADAPTER
    ]
    candidates = [
        template for source in plan.get("NC", {}).values()
        for template in source.get("templates", [])
        if template.get("source", {}).get("id") == COUNTY_SOURCE_ID
    ]
    if not sources and not candidates:
        return plan
    if len(sources) != 1:
        raise ValueError("Exactly one complete North Carolina reporting source is required")
    validate_templates(sources[0]["templates"])
    return plan


def _title(record):
    county_id = record["cid"]
    expected = "STATEWIDE" if county_id == "0" else record["cnm"]
    match = re.fullmatch(
        r"11/03/2026 (UNOFFICIAL|OFFICIAL) GENERAL ELECTION RESULTS - (.+)",
        record["tle"],
    )
    if match is None or match.group(2) != expected:
        raise ValueError("Changed North Carolina election/status/county title")
    status = match.group(1)
    if county_id == "0" and record["cnm"] != "STATE":
        raise ValueError("Changed North Carolina statewide native name")
    return status


def _parse(body):
    try:
        document = json.loads(body, object_pairs_hook=_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed North Carolina native JSON") from error
    if not isinstance(document, list) or len(document) != 101:
        raise ValueError("Changed North Carolina complete state/county scope")
    records = {}
    for raw in document:
        if not isinstance(raw, dict) or set(raw) != FIELDS:
            raise ValueError("Changed North Carolina native record schema")
        county_id = raw.get("cid")
        if (
            not isinstance(county_id, str)
            or COUNT_LITERAL.fullmatch(county_id) is None
            or county_id in records
            or not isinstance(raw.get("cnm"), str)
            or not raw["cnm"]
        ):
            raise ValueError("Changed or duplicate North Carolina native identity")
        for field in ("bct", "prt", "ptl", "rtl"):
            _integer(raw[field], field)
        for field in ("bpt", "ppt"):
            if not isinstance(raw[field], str) or PERCENT_LITERAL.fullmatch(raw[field]) is None:
                raise ValueError("Changed North Carolina native percentage literal")
        _clock(raw["imp"])
        if _clock(raw["sub"]) < _clock(raw["imp"]):
            raise ValueError("North Carolina submit clock precedes its source clock")
        status = _title(raw)
        records[county_id] = {"raw": copy.deepcopy(raw), "status": status}
    if set(records) != {str(index) for index in range(101)}:
        raise ValueError("North Carolina native county IDs changed")
    normalized, reconciliation = reporting_counts(document)
    by_id = {row["county_id"]: row for row in normalized}
    if set(by_id) != set(records):
        raise ValueError("North Carolina parsed and raw identities differ")
    for county_id, item in records.items():
        item["normalized"] = by_id[county_id]
    return document, records, reconciliation


def _template_vector(template):
    county_id = _county_id(template)
    if county_id == "0":
        native = template["view"]["native_record"]
        return {
            "county_id": "0",
            "county": "STATEWIDE",
            "ballots": native["ballots"],
            "registered": native["denominator"],
            "reported_units": native["reported_units"],
            "total_units": native["total_units"],
            "source_clock_literal": native["source_update_label"],
            "status": "UNOFFICIAL",
        }
    query = template["view"]["native_record"]["query"]
    title = re.fullmatch(
        r"11/03/2026 (UNOFFICIAL|OFFICIAL) GENERAL ELECTION RESULTS - (.+)",
        query["election_literal"],
    )
    if title is None:
        raise ValueError("Accepted North Carolina county status literal changed")
    return {
        "county_id": county_id,
        "county": query["county"],
        "ballots": query["ballots"],
        "registered": query["registered"],
        "reported_units": query["reported_units"],
        "total_units": query["total_units"],
        "source_clock_literal": query["source_clock_literal"],
        "status": title.group(1),
    }


def _template_state_vector(templates):
    references = [row["view"].get("native_state_reference") for row in templates]
    reference = references[0]
    if (
        not isinstance(reference, dict)
        or any(item != reference for item in references)
        or str(reference.get("county_id")) != "0"
        or reference.get("county") != "STATE"
    ):
        raise ValueError("Accepted North Carolina statewide reconciliation reference changed")
    title = re.fullmatch(
        r"11/03/2026 (UNOFFICIAL|OFFICIAL) GENERAL ELECTION RESULTS - STATEWIDE",
        reference.get("election_literal", ""),
    )
    if title is None:
        raise ValueError("Accepted North Carolina statewide status literal changed")
    return {
        "county_id": "0",
        "county": "STATEWIDE",
        "ballots": reference["ballots"],
        "registered": reference["registered"],
        "reported_units": reference["reported_units"],
        "total_units": reference["total_units"],
        "source_clock_literal": reference["source_clock_literal"],
        "status": title.group(1),
    }


def _source_vector(item):
    row, raw = item["normalized"], item["raw"]
    return {
        "county_id": row["county_id"],
        "county": row["county"],
        "ballots": row["ballots_cast"],
        "registered": row["registered_voters"],
        "reported_units": row["precincts_reporting"],
        "total_units": row["precincts_total"],
        "source_clock_literal": row["source_update_label"],
        "status": item["status"],
        "election_literal": raw["tle"],
        "native_submit_literal": raw["sub"],
        "published_pct": raw["bpt"],
    }


def _same_clock_values(vector):
    return {
        key: vector[key] for key in (
            "county_id", "county", "ballots", "registered",
            "reported_units", "total_units", "status",
        )
    }


def _guard_successor(current, previous, label):
    current_clock = _clock(current["source_clock_literal"])
    previous_clock = _clock(previous["source_clock_literal"])
    if current_clock < previous_clock:
        raise ValueError("North Carolina " + label + " source clock regressed")
    if (
        current_clock == previous_clock
        and _same_clock_values(current) != _same_clock_values(previous)
    ):
        raise ValueError("North Carolina " + label + " changed under an unchanged source clock")
    if previous["status"] == "OFFICIAL" and current["status"] != "OFFICIAL":
        raise ValueError("North Carolina " + label + " source status regressed")


def _prior_vectors(prior, templates):
    if prior is None:
        return None
    if not isinstance(prior, dict):
        raise ValueError("North Carolina prior source/data registration is incoherent")
    source = prior.get("source") if isinstance(prior, dict) else None
    data = prior.get("data") if isinstance(prior, dict) else None
    if source is None and data is None:
        status = prior.get("status")
        if (
            status in {None, "reported", "retained_after_failure"}
            or prior.get("first_observed_at") not in {None, ""}
            or prior.get("error") not in {None, status}
        ):
            raise ValueError("North Carolina absent prior registration is incoherent")
        return None
    if source is None or data is None:
        raise ValueError("North Carolina prior source/data registration is incoherent")
    if (
        prior.get("status") not in {"reported", "retained_after_failure"}
        or not isinstance(source, dict)
        or source.get("url") != URL
        or not isinstance(source.get("bytes"), int)
        or not isinstance(source.get("sha256"), str)
        or not isinstance(data, dict)
        or data.get("contract") != CONTRACT
        or data.get("source_pin") != {
            "bytes": source["bytes"], "sha256": source["sha256"]
        }
        or data.get("source_url") != URL
    ):
        raise ValueError("North Carolina prior source/data registration is incoherent")
    queries = data.get("complete_native_query")
    if not isinstance(queries, list) or len(queries) != 1:
        raise ValueError("North Carolina prior complete query is missing")
    query = queries[0]
    if (
        query.get("source_pin") != data["source_pin"]
        or query.get("source_url") != URL
        or not isinstance(query.get("records"), list)
        or not isinstance(query.get("source_body"), str)
    ):
        raise ValueError("North Carolina prior source pin/query differs")
    body = query["source_body"].encode()
    if pin(body) != data["source_pin"]:
        raise ValueError("North Carolina prior original bytes/source pin differ")
    document, records, reconciliation = _parse(body)
    if (
        document != query["records"]
        or reconciliation != query.get("reconciliation")
        or digest(encoded(document)) != query.get("records_sha256")
    ):
        raise ValueError("North Carolina prior complete query changed")
    updates = data.get("updates")
    if not isinstance(updates, list) or len(updates) != 100:
        raise ValueError("North Carolina prior update inventory changed")
    templates_by_id = {row["id"]: row for row in templates}
    if {row.get("id") for row in updates} != set(templates_by_id):
        raise ValueError("North Carolina prior update identities changed")
    vectors = {}
    for update in updates:
        template = templates_by_id[update["id"]]
        county_id = _county_id(template)
        vector = _source_vector(records[county_id])
        native = update.get("native") or {}
        native_query = native.get("query") or {}
        expected_query = {
            **vector,
            "native_fraction_literal": vector["published_pct"],
            "native_report_status_literal": vector["status"],
        }
        expected_rate = (
            records[county_id]["normalized"]["reported_ballot_fraction_pct"] is not None
            and vector["reported_units"] == vector["total_units"]
        )
        if (
            update.get("value") != vector["ballots"]
            or update.get("registered") != vector["registered"]
            or update.get("clock") != vector["source_clock_literal"]
            or update.get("reported_units") != vector["reported_units"]
            or update.get("total_units") != vector["total_units"]
            or update.get("rate_compatible") is not expected_rate
            or native_query != expected_query
            or native.get("source_original_pin") != data["source_pin"]
            or native.get("source_clock_timezone") is not None
        ):
            raise ValueError("North Carolina prior query/update/source coherence changed")
        vectors[county_id] = vector
    vectors["0"] = _source_vector(records["0"])
    return vectors


def statistics(body, templates, url, *, prior=None):
    """Parse one complete official aggregate and reject any family rollback."""
    if url != URL:
        raise ValueError("Unreviewed North Carolina participation product")
    validate_templates(templates)
    document, records, reconciliation = _parse(body)
    template_by_county = {_county_id(row): row for row in templates}
    prior_vectors = _prior_vectors(prior, templates)
    source_pin = pin(body)
    state_vector = _source_vector(records["0"])
    baseline_state = _template_state_vector(templates)
    _guard_successor(state_vector, baseline_state, "accepted statewide")
    if prior_vectors is not None:
        _guard_successor(state_vector, prior_vectors["0"], "prior statewide")
    updates = []
    for county_id in sorted(template_by_county, key=int):
        template = template_by_county[county_id]
        vector = _source_vector(records[county_id])
        baseline = _template_vector(template)
        if vector["county"] != baseline["county"]:
            raise ValueError("North Carolina accepted county identity/name changed")
        _guard_successor(vector, baseline, "accepted " + county_id)
        if prior_vectors is not None:
            _guard_successor(vector, prior_vectors[county_id], "prior " + county_id)
        native = copy.deepcopy(template["view"].get("native_record") or {})
        native.update(
            query=copy.deepcopy(vector),
            raw_record=copy.deepcopy(records[county_id]["raw"]),
            source_original_pin=source_pin,
            source_clock_timezone=None,
            source_status_literal=vector["status"],
            native_fraction_literal=vector["published_pct"],
            native_report_status_literal=vector["status"],
            native_reporting_complete_qualified=True,
            reporting_counters_are_not_certification=True,
            analytical_rates_promoted=False,
            candidate_vote_sum_used=False,
            complete_state_county_reconciliation=True,
        )
        native["query"].update(
            native_fraction_literal=vector["published_pct"],
            native_report_status_literal=vector["status"],
        )
        normalized = records[county_id]["normalized"]
        updates.append({
            "id": template["id"],
            "value": vector["ballots"],
            "native": native,
            "registered": vector["registered"],
            "clock": vector["source_clock_literal"],
            "reported_units": vector["reported_units"],
            "total_units": vector["total_units"],
            "rate_compatible": (
                normalized["reported_ballot_fraction_pct"] is not None
                and vector["reported_units"] == vector["total_units"]
            ),
        })
    complete_query = {
        "source_url": URL,
        "source_pin": source_pin,
        "source_body": body.decode("utf-8"),
        "records": document,
        "records_sha256": digest(encoded(document)),
        "reconciliation": reconciliation,
        "state_and_100_counties_complete": True,
        "candidate_vote_sum_used": False,
        "timezone_supplied_by_source": False,
    }
    return {
        "contract": CONTRACT,
        "updates": updates,
        "complete_native_query": [complete_query],
        "source_url": URL,
        "source_pin": source_pin,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "early_mail_frames_changed": False,
        "candidate_vote_sum_used": False,
    }
