"""Refresh Delaware's reviewed statewide Ballots Cast observation."""

import copy
from decimal import Decimal, ROUND_HALF_UP, localcontext
import gzip
import json
import re

from scripts.participation_intake.contract import digest, encoded, pin
from scripts.results_granular import public_facts


ADAPTER = "reviewed_delaware_statewide"
ENTRY_URL = "https://elections.delaware.gov/results/enr/GE2026.html?group=state"
REVIEWED_URL = (
    "https://elections.delaware.gov/results/enr/"
    "Election_VoterTurnout_ID_GE2026.json"
)
STORED_SOURCE_URL = "https://www.themarginoferror.com/voter-participation/"
STORED_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "64d0fd238464211b9634b83a8b3f27490f1141ab/"
    "data/county-source-reviews/20261106-delaware-statewide-native-01/"
    "statewide-participation.csv"
)
SOURCE_ID = (
    "accepted-export:9dfbfe6ce11851be136dd9036c45b5a52c38bffbfb0231865b4c427c6bb84dd3:"
    "states"
)
OBSERVATION_ID = "e277d3329267a8248624951a9888232c"
ELECTION = {
    "id": "us-2026-general-previously-reviewed",
    "year": 2026,
    "date": None,
    "type": "general",
    "qualification": "previously_reviewed",
}
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Ballots Cast",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
FIELDS = {
    "Election Id", "Election Name", "Results Type", "Representative District",
    "Ballots Cast", "Reg Voters", "Percentage",
}
STATUSES = ("UNOFFICIAL RESULTS", "OFFICIAL RESULTS")
MISSING_CLOCK_LABEL = (
    "Native turnout update clock/timezone not supplied; candidate clock is separate "
    "and not substituted."
)
AUTHORITY = {
    "declaring_page_url": ENTRY_URL,
    "declared_election_id": "GE2026",
    "declared_election_date": "2026-11-03",
    "declared_source_template": (
        "/results/enr/Election_VoterTurnout_ID_${electionId}.json?t=${tstamp}"
    ),
    "reviewed_source_script_sha256": (
        "ee821c831ae08bdfb53294692807dc67efd8896ab04eb02deb889f3e0598be58"
    ),
    "client_timestamp_is_cache_key_not_source_clock": True,
}


def _integer(value):
    if isinstance(value, bool):
        raise ValueError("Invalid Delaware native count")
    if type(value) is int and value >= 0:
        return value
    if not isinstance(value, str) or re.fullmatch(
            r"(?:0|[1-9]\d{0,2}(?:,\d{3})*)", value) is None:
        raise ValueError("Missing Delaware native count is not a recorded zero")
    return int(value.replace(",", ""))


def _percentage(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Invalid Delaware printed percentage")
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError("Invalid Delaware printed percentage") from error
    if not result.is_finite() or result < 0 or result > 100:
        raise ValueError("Invalid Delaware printed percentage")
    return result


def _template_contract(template):
    source, view = template.get("source", {}), template.get("view", {})
    denominator = template.get("denominator")
    source_urls = source.get("url"), view.get("source_url")
    clock = template.get("source_clock", {})
    reporting = template.get("reporting_status", {})
    if (
        template.get("contract") != "participation.observation.v1"
        or template.get("id") != OBSERVATION_ID
        or template.get("election") != ELECTION
        or template.get("measure") != MEASURE
        or template.get("geography") != {
            "id": "DE|state|",
            "join": {
                "evidence": (
                    "Existing export map qualifications and reference bindings remain literal "
                    "in source.fields and view; this migration approves no new join."
                ),
                "feature_key": None,
                "reference_id": None,
                "status": "unreviewed",
            },
            "level": "state",
            "name": "Delaware",
            "parent_id": None,
            "state_code": "DE",
        }
        or not isinstance(denominator, dict)
        or denominator.get("basis") != "native_registered_voters"
        or denominator.get("literal") != "native_registered_voters"
        or denominator.get("qualified") is not True
        or type(denominator.get("value")) is not int
        or denominator["value"] <= 0
        or template.get("count", {}).get("status") != "reported"
        or type(template.get("count", {}).get("value")) is not int
        or source.get("id") != SOURCE_ID
        or source.get("classification") != "public_aggregate"
        or source_urls not in (
            (STORED_SOURCE_URL, STORED_VIEW_URL),
            (REVIEWED_URL, REVIEWED_URL),
        )
        or clock.get("timezone") is not None
        or clock.get("literal") not in (MISSING_CLOCK_LABEL, None)
        or reporting.get("literal") not in STATUSES
        or reporting.get("reported_units") is not None
        or reporting.get("total_units") is not None
        or reporting.get("complete") is not None
        or view.get("state_code") != "DE"
        or view.get("state") != "Delaware"
        or view.get("mode") != "official"
        or view.get("geography_level") != "statewide"
        or view.get("maps_approved") is not False
        or view.get("denominator_basis") != "native_registered_voters"
        or view.get("participation_measure_literal") != "Ballots Cast"
    ):
        raise ValueError("Delaware accepted statewide source/identity scope changed")
    return template


def extend_templates(baseline, templates):
    index = json.loads(baseline["index.json"])
    declaration = index["states"].get("DE")
    if not isinstance(declaration, dict):
        return templates
    shard = json.loads(gzip.decompress(baseline[declaration["file"]]))
    matches = [row for row in shard["records"] if row.get("id") == OBSERVATION_ID]
    if not matches:
        return templates
    if len(matches) != 1:
        raise ValueError("Delaware reviewed statewide observation inventory changed")
    current = _template_contract(matches[0])
    result = list(templates)
    if not any(row.get("id") == OBSERVATION_ID for row in result):
        result.append(current)
    return result


def route(template):
    try:
        _template_contract(template)
    except ValueError:
        return None
    return {"adapter": ADAPTER, "state": "DE", "url": REVIEWED_URL}


def validate_plan(plan):
    candidates = [
        template
        for source in plan.get("DE", {}).values()
        for template in source.get("templates", [])
        if template.get("id") == OBSERVATION_ID
    ]
    sources = [
        source for source in plan.get("DE", {}).values()
        if source.get("adapter") == ADAPTER
    ]
    if not candidates and not sources:
        return plan
    if len(candidates) != 1 or len(sources) != 1 or sources[0]["url"] != REVIEWED_URL:
        raise ValueError("Delaware reviewed automatic source inventory changed")
    if sources[0]["templates"] != candidates:
        raise ValueError("Delaware automatic source contains an unreviewed template")
    _template_contract(candidates[0])
    return plan


def _rows(body):
    try:
        source = json.loads(body)
    except Exception as error:
        raise ValueError("Unreadable Delaware native turnout JSON") from error
    if not isinstance(source, list) or len(source) != 42:
        raise ValueError("Incomplete Delaware state/district turnout inventory")
    expected = {"ALL"} | {f"{number:02}" for number in range(1, 42)}
    if {row.get("Representative District") for row in source
            if isinstance(row, dict)} != expected:
        raise ValueError("Incomplete or duplicate Delaware district inventory")
    normalized = []
    statuses = set()
    for row in source:
        if (
            not isinstance(row, dict)
            or set(row) != FIELDS
            or row["Election Id"] != "GE2026"
            or row["Election Name"] != "2026 General Election"
            or row["Results Type"] not in STATUSES
        ):
            raise ValueError("Delaware native schema, election or status changed")
        ballots = _integer(row["Ballots Cast"])
        registered = _integer(row["Reg Voters"])
        printed = _percentage(row["Percentage"])
        if registered <= 0 or ballots > registered:
            raise ValueError("Invalid Delaware Ballots Cast/Reg Voters pair")
        with localcontext() as context:
            context.prec = 80
            calculated = (100 * Decimal(ballots) / registered).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP)
        if calculated != printed:
            raise ValueError("Delaware printed registered fraction does not reconcile")
        statuses.add(row["Results Type"])
        normalized.append({
            "election_id": row["Election Id"],
            "election_name": row["Election Name"],
            "native_report_status_literal": row["Results Type"],
            "representative_district": row["Representative District"],
            "geography_level": (
                "state" if row["Representative District"] == "ALL"
                else "representative_district"
            ),
            "ballots_cast": ballots,
            "registered_voters": registered,
            "printed_percentage": format(printed, "f"),
            "native_fraction_literal": format(printed, "f") + "%",
            "native_measure_literal": "Ballots Cast",
            "native_denominator_literal": "Reg Voters",
            "source_clock": None,
            "source_timezone": None,
            "native_fips": None,
            "analysis_rate_approved": False,
            "maps_approved": False,
            "all_mode_complete": False,
            "certified": False,
            "candidate_votes_substituted": False,
            "county_or_precinct_allocation": False,
        })
    if len(statuses) != 1:
        raise ValueError("Conflicting Delaware native result statuses")
    by_district = {row["representative_district"]: row for row in normalized}
    state = by_district["ALL"]
    districts = [by_district[f"{number:02}"] for number in range(1, 42)]
    if (
        sum(row["ballots_cast"] for row in districts) != state["ballots_cast"]
        or sum(row["registered_voters"] for row in districts) != state["registered_voters"]
    ):
        raise ValueError("Delaware district accounting disagrees with statewide totals")
    return state, normalized


def statistics(body, templates, url):
    if url != REVIEWED_URL or len(templates) != 1:
        raise ValueError("Wrong Delaware reviewed source or template inventory")
    template = _template_contract(templates[0])
    state, rows = _rows(body)
    prior_status = template["reporting_status"]["literal"]
    if prior_status == "OFFICIAL RESULTS" and state["native_report_status_literal"] != prior_status:
        raise ValueError("Delaware native result status rolled back")
    query = {
        "contract": "participation.delaware_native_turnout_query.v1",
        "source_url": REVIEWED_URL,
        "source_pin": pin(body),
        "source_authority": copy.deepcopy(AUTHORITY),
        "election_id": "GE2026",
        "election_date": "2026-11-03",
        "native_turnout_update_clock": None,
        "native_turnout_timezone": None,
        "candidate_clock_not_substituted": True,
        "client_cache_key_not_source_clock": True,
        "native_ballot_modes_separately_reported": False,
        "all_mode_completion_qualified": False,
        "state_and_district_rows": len(rows),
        "representative_district_rows": 41,
        "projected_observation_ids": [OBSERVATION_ID],
        "withheld_representative_district_contexts": [
            row["representative_district"] for row in rows
            if row["geography_level"] == "representative_district"
        ],
        "withheld_context_reason": (
            "No reviewed canonical representative-district count slots; retained as complete "
            "native numerical context without inventing identities, rates or maps."
        ),
        "rows": rows,
    }
    native = {
        "query": copy.deepcopy(state),
        "complete_inventory": {
            "state_and_district_rows": 42,
            "representative_district_rows": 41,
            "rows_sha256": digest(encoded(rows)),
        },
        "native_fraction_literal": state["printed_percentage"] + "%",
        "native_report_status_literal": state["native_report_status_literal"],
        "native_reporting_complete_qualified": False,
        "native_turnout_update_clock": None,
        "native_turnout_timezone": None,
        "candidate_clock_not_substituted": True,
        "client_cache_key_not_source_clock": True,
        "native_ballot_modes_separately_reported": False,
        "all_mode_completion_qualified": False,
        "maps_approved": False,
        "county_or_precinct_allocation": False,
    }
    updates = [{
        "id": OBSERVATION_ID,
        "value": state["ballots_cast"],
        "native": native,
        "registered": state["registered_voters"],
        "clock": None,
        "reported_units": None,
        "total_units": None,
        "rate_compatible": True,
    }]
    bridge = {
        "contract": "participation.reviewed_source_url_bridge.v1",
        "source_id": SOURCE_ID,
        "stored_source_url": STORED_SOURCE_URL,
        "stored_view_source_url": STORED_VIEW_URL,
        "reviewed_url": REVIEWED_URL,
        "prior_full_inventory_pin": digest(encoded({
            "observation_ids": [OBSERVATION_ID],
            "source_id": SOURCE_ID,
            "measure": MEASURE,
        })),
        "observation_ids_pin": digest(encoded([OBSERVATION_ID])),
        "declared_entry_url": ENTRY_URL,
        "qualification_basis": (
            "Previously reviewed statewide slot plus the official page-declared GE2026 turnout "
            "JSON and the complete reconciled 41-district/state vector."
        ),
    }
    public_facts(query)
    return {
        "updates": updates,
        "complete_native_query": [query],
        "reviewed_source_url_bridge": bridge,
        "source_url": REVIEWED_URL,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "new_count_identities_added": False,
        "representative_district_contexts_projected": 0,
        "representative_district_contexts_withheld": 41,
        "candidate_votes_are_ballots": False,
    }
