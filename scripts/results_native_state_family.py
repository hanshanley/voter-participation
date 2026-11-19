"""Reviewed automatic native participation sources for Arkansas, Arizona and Wyoming."""

import copy
from datetime import datetime, timezone
import json
import re

from scripts.native_products import query as native_query, unpack as native_unpack
from scripts.participation_intake.contract import count, digest, encoded, pin


ADAPTER = "reviewed_native_state_family"
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
AR_ENTRY_URL = (
    "https://arkansas.tally-enr.com/"
    "#bucket=results&filter=Federal&contest=eafd140a-9378-43a2-bd6d-f8661524139b"
)
AR_REVIEWED_URL = (
    "https://arkansas.tally-enr.com/assets/__verdict-download/"
    "6a1f15f8fcc7/mw3h9e64-0-7yxhd8qe/"
    "2026_General_Election_%26_Judical_Runoff.json"
)
AR_ELECTION_ID = "11b07106-031e-4d7c-911a-d01fb473d6dd"
AR_PARENT_FIELDS = ("TotalBallotsCast", "RegisteredVoters", "PrecinctsReporting",
                    "TotalPrecincts", "PrecinctsPartiallyReporting")
AR_COUNTY_IDS = tuple(f"05{i:03}" for i in range(1, 150, 2))
AR_SOURCE_ID = (
    "accepted-export:b128dc3cef02ae063e840495611b3747dc9454692d2788a8cb94e3b160f4908a:"
    "reporting/AR"
)
AR_STORED_SOURCE_URL = (
    "https://www.themarginoferror.com/participation-reporting-units/20261109-02/AR.json.gz"
)
AR_ACCEPTED_INVENTORY = "fa9eee0ff75f10accd070499bf4a876b5112eb201340868f823a8882c6d0c0c6"
AZ_ENTRY_URL = "https://app.enhancedvoting.com/results/public/Arizona/110326GeneralElection"
AZ_API_ROOT = "https://app.enhancedvoting.com/results/public/api/elections/"
AZ_ROOT_URL = AZ_API_ROOT + "Arizona/110326GeneralElection/data"
AZ_SOURCE_ID = (
    "accepted-export:bc9f1e93785e4a83148b96afa6855701f511be995f7469b8e9e4dfcb7e6cb51f:"
    "reporting/AZ"
)
AZ_STORED_SOURCE_URL = (
    "https://www.themarginoferror.com/participation-reporting-units/20261109-02/AZ.json.gz"
)
AZ_ACCEPTED_INVENTORY = "9397a83b95838fd3d7ef9c54a32461e4350eb93e4a65a746205976fed67a6bde"
AZ_COUNTIES = {
    "01": ("Apache County", "apache-county-az", "01000000-0496-9e5d-8720-08dbda36ae85"),
    "02": ("Cochise County", "cochise-county-az", "01000000-0496-9e5d-604a-08dbda36ae89"),
    "03": ("Coconino County", "coconino-county-az", "01000000-0496-9e5d-f29e-08dbda36ae8a"),
    "04": ("Gila County", "gila-county-az", "01000000-0496-9e5d-e1ca-08dbda36ae8b"),
    "05": ("Graham County", "graham-county-az", "01000000-0496-9e5d-d553-08dbda36ae8c"),
    "06": ("Greenlee County", "greenlee-county-az", "01000000-0496-9e5d-991f-08dbda36ae8e"),
    "07": ("La Paz County", "la-paz-county-az", "01000000-0496-9e5d-d168-08dbda36ae8f"),
    "maricopa": ("Maricopa County", "maricopa-county-az", "01000000-0496-9e5d-9eb9-08dbda36ae91"),
    "09": ("Mohave County", "mohave-county-az", "01000000-0496-9e5d-cc92-08dbda36ae92"),
    "10": ("Navajo County", "navajo-county-az", "01000000-0496-9e5d-f590-08dbda36ae93"),
    "pima": ("Pima County", "pima-county-az", "01000000-0496-9e5d-f471-08dbda36ae94"),
    "12": ("Pinal County", "pinal-county-az", "01000000-0496-9e5d-d66a-08dbda36ae95"),
    "13": ("Santa Cruz County", "santa-cruz-county-az", "01000000-0496-9e5d-aff3-08dbda36ae96"),
    "14": ("Yavapai County", "yavapai-county-az", "01000000-0496-9e5d-1def-08dbda36ae98"),
    "15": ("Yuma County", "yuma-county-az", "01000000-0496-9e5d-12e0-08dbda36ae99"),
}

WY_ENTRY_URL = "https://sos.wyo.gov/Elections/Docs/2026/2026GeneralResults.aspx"
WY_REVIEWED_URL = (
    "https://sos.wyo.gov/Elections/Docs/2026/Results/General/"
    "2026_Wyoming_General_Results.zip"
)
WY_SOURCE_ID = (
    "accepted-export:cea7eba88d5ae521db73653ce33992dbe2d253a2854cd81d27655890e74be161:"
    "reporting/WY"
)
WY_STORED_SOURCE_URL = (
    "https://www.themarginoferror.com/participation-reporting-units/20261109-02/WY.json.gz"
)
WY_ACCEPTED_INVENTORY = "a62e043fc81cad5382f5f8e86b4e9afdbf60052781449205050befd8bb7cbb56"
WY_MEMBERS = {
    "2026 General Results Summaries - OFFICIAL.xlsx": [
        "Statewide Total Ballots Cast", "Statewide Candidates", "Statewide Senate Odd",
        "Statewide House", "Statewide Judicial", "Statewide Ballot Issue",
    ],
    "2026 County General PbP - OFFICIAL.xlsx": [
        "Albany", "Big Horn", "Campbell", "Carbon", "Converse", "Crook", "Fremont",
        "Goshen", "Hot Springs", "Johnson", "Laramie", "Lincoln", "Natrona", "Niobrara",
        "Park", "Platte", "Sheridan", "Sublette", "Sweetwater", "Teton", "Uinta",
        "Washakie", "Weston",
    ],
    "2026 County General PbP TBC - OFFICIAL.xlsx": [
        "Albany", "Big Horn", "Campbell", "Carbon", "Converse", "Crook", "Fremont",
        "Goshen", "Hot Springs", "Johnson", "Laramie", "Lincoln", "Natrona", "Niobrara",
        "Park", "Platte", "Sheridan", "Sublette", "Sweetwater", "Teton", "Uinta",
        "Washakie", "Weston",
    ],
}
WY_CATEGORIES = {
    "R": "Chuck Gray (R)",
    "D": "Lisa Kinney (D)",
    "L": "Shawn Johnson (L)",
    "C": "Jeffrey Haggit (C)",
    "write_ins": "Write-Ins",
    "overvotes": "Overvotes",
    "undervotes": "Undervotes",
}

EXPECTED = {
    "AR": (2768, AR_ACCEPTED_INVENTORY, 1),
    "AZ": (1763, AZ_ACCEPTED_INVENTORY, 15),
    "WY": (432, WY_ACCEPTED_INVENTORY, 1),
}


def _english(values):
    matches = [item.get("text") for item in values if item.get("languageId") == "en"]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise ValueError("Missing or ambiguous source-declared English label")
    return matches[0]


def _exact_count(value):
    result = count(value)
    if result is None:
        raise ValueError("Missing native count is not a recorded zero")
    return result


def _api_count(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or int(value) != value:
        raise ValueError("Missing or nonintegral native API count")
    return int(value)


def _clock(value):
    normalized = re.sub(r"(\.[0-9]{6})[0-9]+Z$", r"\1Z", value)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _utc_clock(value):
    if not isinstance(value, str) or re.fullmatch(
            r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,7})?Z",
            value) is None:
        raise ValueError("Arizona native count clock is not a supported literal UTC timestamp")
    try:
        parsed = _clock(value)
    except ValueError as error:
        raise ValueError("Arizona native count clock is malformed") from error
    if parsed.tzinfo != timezone.utc or parsed < datetime(2026, 11, 3, tzinfo=timezone.utc):
        raise ValueError("Arizona native count clock is outside the reviewed election")
    return value


def _uuid(value):
    if not isinstance(value, str) or re.fullmatch(
            r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value) is None:
        raise ValueError("Invalid source-declared UUID")
    return value.lower()


def _indexed_uuids(nodes, field):
    result = {}
    for node in nodes:
        identity = _uuid(node.get(field, ""))
        if identity in result:
            raise ValueError("Duplicate Arizona root locality UUID")
        result[identity] = node
    return result


def _native_label(node):
    labels = [node.get(key) for key in ("LocationName", "Name")
              if isinstance(node.get(key), str) and node[key].strip()]
    if len(set(labels)) > 1:
        raise ValueError("Conflicting literal native location labels")
    return labels[0] if labels else None


def _retained_label(native, kind):
    return native.get(kind) or native.get("retained_accepted_" + kind + "_label")


def _wyoming_identity(native):
    query = native.get("ballot_count_query")
    return query if isinstance(query, dict) else native


def _route_state(template):
    if (
        template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("date") not in (None, "2026-11-03")
        or template.get("election", {}).get("type") != "general"
        or template.get("geography", {}).get("level") != "reporting_unit"
        or template.get("measure") != MEASURE
    ):
        return None
    state = template["geography"]["state_code"]
    source, view = template.get("source", {}), template.get("view", {})
    expected_source = {"AR": AR_SOURCE_ID, "AZ": AZ_SOURCE_ID, "WY": WY_SOURCE_ID}.get(state)
    if source.get("id") != expected_source:
        return None
    stored = {"AR": AR_STORED_SOURCE_URL, "AZ": AZ_STORED_SOURCE_URL,
              "WY": WY_STORED_SOURCE_URL}[state]
    entry = {"AR": AR_ENTRY_URL, "AZ": AZ_ENTRY_URL, "WY": WY_ENTRY_URL}[state]
    if source.get("url") == stored and view.get("source_url") != entry:
        raise ValueError(state + " accepted source/view URL lineage changed")
    return state


def route(template):
    """Return one exact reviewed numerical source for an accepted family observation."""
    state = _route_state(template)
    if state is None:
        return None
    native = template["view"].get("native_record") or {}
    if state == "AR":
        if (
            not str(native.get("county_code", ""))
            or not str(native.get("precinct_code", ""))
            or not str(_retained_label(native, "precinct") or "")
        ):
            raise ValueError("Arkansas accepted native identity changed")
        url = AR_REVIEWED_URL
    elif state == "AZ":
        code = str(native.get("county_code", ""))
        declared = AZ_COUNTIES.get(code)
        if (
            declared is None
            or native.get("county") != declared[0]
            or _uuid(native.get("native_county_uuid", "")) != _uuid(declared[2])
            or not str(native.get("precinct_code", ""))
            or not str(native.get("precinct", ""))
        ):
            raise ValueError("Arizona accepted county/precinct identity changed")
        url = AZ_API_ROOT + declared[1] + "/110326GeneralElection/data"
    else:
        identity = _wyoming_identity(native)
        if not str(identity.get("county", "")) or not str(identity.get("precinct", "")):
            raise ValueError("Wyoming accepted native identity changed")
        url = WY_REVIEWED_URL
    current = source_url = template["source"]["url"]
    view_url = template["view"].get("source_url")
    stored = {"AR": AR_STORED_SOURCE_URL, "AZ": AZ_STORED_SOURCE_URL,
              "WY": WY_STORED_SOURCE_URL}[state]
    entry = {"AR": AR_ENTRY_URL, "AZ": AZ_ENTRY_URL, "WY": WY_ENTRY_URL}[state]
    if (current, view_url) not in ((stored, entry), (url, url)):
        raise ValueError(state + " source URL bridge is mixed or unreviewed")
    return {"adapter": ADAPTER, "state": state, "url": url, "source_url": source_url}


def validate_plan(plan):
    """Pin the complete initial family inventory; accept only validated projected successors."""
    for state, (expected_rows, accepted_pin, expected_sources) in EXPECTED.items():
        expected_source_id = {"AR": AR_SOURCE_ID, "AZ": AZ_SOURCE_ID, "WY": WY_SOURCE_ID}[state]
        candidates = [
            template for source in plan.get(state, {}).values()
            for template in source.get("templates", [])
            if template.get("source", {}).get("id") == expected_source_id
        ]
        sources = [source for source in plan.get(state, {}).values()
                   if source.get("adapter") == ADAPTER]
        if not candidates and not sources:
            continue
        templates = [template for source in sources for template in source["templates"]]
        if len(sources) != expected_sources or len(templates) != expected_rows:
            raise ValueError(state + " reviewed automatic source inventory changed")
        initial = all(template["source"]["url"] == {
            "AR": AR_STORED_SOURCE_URL, "AZ": AZ_STORED_SOURCE_URL,
            "WY": WY_STORED_SOURCE_URL,
        }[state] for template in templates)
        if initial:
            if digest(encoded(templates)) != accepted_pin:
                raise ValueError(state + " accepted family inventory pin changed")
        elif not all(template.get("view", {}).get("automatic_source_refresh") is True
                     and route(template) is not None for template in templates):
            raise ValueError(state + " projected family inventory is not reusable")
    return plan


def _updates(templates, facts, source_pin, url, state):
    updates = []
    for template in templates:
        native = template["view"]["native_record"]
        if state == "AR":
            key = str(native["county_code"]), str(native["precinct_code"])
        elif state == "AZ":
            key = _uuid(native["precinct_code"])
        else:
            identity = _wyoming_identity(native)
            key = identity["county"], identity["precinct"]
        fact = facts.get(key)
        expected_name = (
            _wyoming_identity(native).get("precinct") if state == "WY"
            else _retained_label(native, "precinct")
        )
        if fact is None or fact["name"] != expected_name:
            raise ValueError(state + " literal native reporting-unit identity changed")
        previous_clock = template.get("source_clock", {}).get("literal")
        if (
            previous_clock is not None
            and fact["clock"] is not None
            and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z", previous_clock)
            and _clock(fact["clock"]) < _clock(previous_clock)
        ):
            raise ValueError(state + " native count clock regressed")
        updates.append({
            "id": template["id"],
            "value": fact["value"],
            "native": copy.deepcopy(fact["native"]),
            "registered": fact["registered"],
            "clock": fact["clock"],
            "reported_units": fact.get("reported"),
            "total_units": fact.get("total"),
            "rate_compatible": False,
        })
    if len(updates) != len(facts):
        raise ValueError(state + " complete native inventory differs from accepted templates")
    return updates


def _source_bridge(templates, url, state):
    source_ids = {template["source"]["id"] for template in templates}
    stored_source_urls = {template["source"]["url"] for template in templates}
    stored_view_urls = {template["view"].get("source_url") for template in templates}
    if len(source_ids) != 1 or len(stored_source_urls) != 1 or len(stored_view_urls) != 1:
        raise ValueError(state + " source-level reviewed URL bridge inventory changed")
    return {
        "contract": "participation.reviewed_source_url_bridge.v1",
        "source_id": source_ids.pop(),
        "stored_source_url": stored_source_urls.pop(),
        "stored_view_source_url": stored_view_urls.pop(),
        "reviewed_url": url,
        "prior_full_inventory_pin": EXPECTED[state][1],
        "observation_ids_pin": digest(encoded(sorted(template["id"] for template in templates))),
        "declared_entry_url": {"AR": AR_ENTRY_URL, "AZ": AZ_ENTRY_URL, "WY": WY_ENTRY_URL}[state],
        "declaration_status": {
            "AR": "reviewed native download-button original; successor export discovery remains held",
            "AZ": "reviewed public application API route and root locality declaration",
            "WY": "reviewed official results index to complete official workbook ZIP",
        }[state],
        "qualification_basis": (
            "Exact accepted source identity, complete reviewed family inventory pin, source-specific "
            "observation-ID inventory, and successful retained public aggregate original."
        ),
    }


def arkansas_parent(statewide, counties):
    def values(node, *, county=False):
        counts = [None if county and field in {"PrecinctsReporting", "PrecinctsPartiallyReporting"}
                  and node.get(field) is None else _exact_count(node.get(field))
                  for field in AR_PARENT_FIELDS]
        ballots, registered, reported, total, partial = counts
        if (ballots > registered or total == 0 or (reported or 0) + (partial or 0) > total
                or ((reported is None or partial is None) and (reported or partial) != total)):
            raise ValueError("Arkansas statewide reporting controls changed")
        return counts

    if tuple(sorted(counties)) != AR_COUNTY_IDS or any(
        county.get("LocationID") != code for code, county in counties.items()
    ):
        raise ValueError("Arkansas statewide county identities changed")
    rows = [[code, *values(counties[code], county=True)] for code in AR_COUNTY_IDS]
    parent = values(statewide)
    if [sum(value or 0 for value in column) for column in zip(*(row[1:] for row in rows))] != parent:
        raise ValueError("Arkansas statewide and county reporting controls disagree")
    return {"statewide": parent, "counties": rows}


def _arkansas(body, templates, url):
    accepted = {}
    for template in templates:
        native = template["view"]["native_record"]
        key = str(native["county_code"]), str(native["precinct_code"])
        value = _retained_label(native, "county"), _retained_label(native, "precinct")
        if key in accepted or not all(isinstance(item, str) and item for item in value):
            raise ValueError("Arkansas accepted label context changed")
        accepted[key] = value
    expected_counties = {key[0] for key in accepted}
    data = json.loads(body)
    if (
        set(data) != {"ElectionData", "TurnoutData", "ContestData"}
        or data["ElectionData"].get("ElectionID") != AR_ELECTION_ID
        or type(data["ElectionData"].get("IsOfficial")) is not bool
        or url != AR_REVIEWED_URL
    ):
        raise ValueError("Wrong Arkansas native general-election export")
    status = "OFFICIAL" if data["ElectionData"]["IsOfficial"] else "UNOFFICIAL"
    turnout = data["TurnoutData"]
    counties = turnout.get("Locations")
    if not isinstance(counties, dict) or set(counties) != expected_counties:
        raise ValueError("Arkansas complete native county inventory changed")
    facts, query_rows, county_totals = {}, [], []
    for county_id, county in counties.items():
        leaves = county.get("Locations")
        current_county_label = _native_label(county)
        if not re.fullmatch(r"05[0-9]{3}", county_id) or not isinstance(leaves, dict) or not leaves:
            raise ValueError("Arkansas county/precinct identity changed")
        observed = []
        for precinct_id, node in leaves.items():
            if str(node.get("LocationID")) != str(precinct_id):
                raise ValueError("Arkansas literal precinct identity changed")
            value = count(node.get("TotalBallotsCast"))
            registered = count(node.get("RegisteredVoters"))
            buckets = node.get("BallotsCast")
            if (
                not isinstance(buckets, list) or len(buckets) != 1
                or count(buckets[0].get("BallotsCast")) != (0 if value is None else value)
            ):
                raise ValueError("Arkansas native turnout bucket disagrees")
            if value is not None:
                observed.append(value)
            reported = count(node.get("PrecinctsReporting"))
            partial = count(node.get("PrecinctsPartiallyReporting"))
            total = count(node.get("TotalPrecincts"))
            if (
                total is None
                or reported is not None and reported > total
                or partial is not None and partial > total
                or reported is None and partial is None
            ):
                raise ValueError("Arkansas native reporting counters changed")
            compact = {
                "election_id": AR_ELECTION_ID,
                "native_report_status_literal": status,
                "county_code": county_id,
                "precinct_code": str(precinct_id),
                "native_county_label": current_county_label,
                "native_precinct_label": _native_label(node),
                "retained_accepted_county_label": None,
                "retained_accepted_precinct_label": None,
                "label_qualification": None,
                "ballots": value,
                "registered_voters": registered,
                "missing_total_preserved": value is None,
                "missing_registration_preserved": registered is None,
                "precincts_reporting": reported,
                "precincts_partially_reporting": partial,
                "total_precincts": total,
                "reporting_percent": node.get("ReportingPercent"),
                "ballot_bucket": copy.deepcopy(buckets[0]),
                "source_clock_literal": None,
                "source_clock_timezone": None,
                "native_reporting_complete_qualified": False,
                "query": {"native_report_status_literal": status},
            }
            facts[county_id, str(precinct_id)] = {
                "name": None, "value": value, "registered": registered, "clock": None,
                "status": status, "reported": reported, "total": total, "native": compact,
            }
            query_rows.append(compact)
        county_total = _exact_count(county.get("TotalBallotsCast"))
        if sum(observed) != county_total:
            raise ValueError("Arkansas observed precinct ballots do not reconcile to county")
        county_totals.append(county_total)
    if (
        set(facts) != set(accepted)
        or sum(county_totals) != _exact_count(turnout.get("TotalBallotsCast"))
    ):
        raise ValueError("Arkansas complete native turnout scope changed")
    for key, fact in facts.items():
        labels = accepted.get(key)
        if labels is None:
            raise ValueError("Arkansas accepted identity inventory changed")
        accepted_county, accepted_precinct = labels
        native = fact["native"]
        if (
            native["native_county_label"] is not None
            and native["native_county_label"] != accepted_county
            or native["native_precinct_label"] is not None
            and native["native_precinct_label"] != accepted_precinct
        ):
            raise ValueError("Arkansas current native label differs from accepted identity context")
        native["retained_accepted_county_label"] = accepted_county
        native["retained_accepted_precinct_label"] = accepted_precinct
        native["label_qualification"] = (
            "Current native label checked against accepted identity."
            if native["native_county_label"] is not None
            and native["native_precinct_label"] is not None else
            "Retained accepted identity context; this native turnout body supplies IDs, not labels."
        )
        fact["name"] = accepted_precinct
    source_pin = pin(body)
    updates = _updates(templates, facts, source_pin, url, "AR")
    missing_ballots = sum(row["ballots"] is None for row in query_rows)
    missing_registrations = sum(row["registered_voters"] is None for row in query_rows)
    parent = {}
    if tuple(sorted(counties)) == AR_COUNTY_IDS:
        try:
            parent["statewide_ballot_parent"] = {
                **arkansas_parent(turnout, counties), "election_id": AR_ELECTION_ID,
                "status": status, "count_source_clock": None,
            }
        except ValueError as exc:
            parent["statewide_ballot_hold"] = str(exc)
    return {
        **parent,
        "updates": updates,
        "complete_native_query": [{
            "state_code": "AR", "election_date": "2026-11-03",
            "native_report_status_literal": status,
            "source_pin": source_pin, "rows": query_rows,
            "missing_ballot_cells": missing_ballots,
            "missing_registration_cells": missing_registrations,
            "candidate_votes_used_as_ballots": False,
            "successor_export_discovery_hold": (
                "The held app/download evidence does not declare a stable successor full-export URL template."
            ),
        }],
        "reviewed_source_url_bridge": _source_bridge(templates, url, "AR"),
        "numerical_data_qualified": False,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }


def _acquire(acquire, url):
    if acquire is None:
        raise ValueError("Arizona county API requires its reviewed root declaration")
    body, receipt = acquire(url)
    if receipt.get("bytes") not in (None, len(body)) or receipt.get("sha256") not in (
            None, digest(body)):
        raise ValueError("Arizona root declaration receipt disagrees")
    return body


def _arizona(body, templates, url, acquire):
    data = json.loads(body)
    root_body = _acquire(acquire, AZ_ROOT_URL)
    root = json.loads(root_body)
    election = data.get("election") or {}
    jurisdiction = data.get("jurisdiction") or {}
    if (
        election.get("electionDate") != "2026-11-03"
        or election.get("isPrimary") is not False
        or election.get("isProduction") is not True
        or type(election.get("isOfficialResults")) is not bool
        or _english(election.get("name", [])) != "2026 General Election"
    ):
        raise ValueError("Wrong Arizona county general-election API")
    status = "OFFICIAL" if election["isOfficialResults"] else "UNOFFICIAL"
    clock = _utc_clock(election.get("asOf"))
    name = _english(jurisdiction.get("name", []))
    matches = [(code, row) for code, row in AZ_COUNTIES.items()
               if row[0] == name and _uuid(row[2]) == _uuid(jurisdiction.get("id", ""))]
    if len(matches) != 1:
        raise ValueError("Arizona county API identity changed")
    code, declared = matches[0]
    expected_url = AZ_API_ROOT + declared[1] + "/110326GeneralElection/data"
    if url != expected_url:
        raise ValueError("Arizona county API route changed")
    root_election = root.get("election") or {}
    root_jurisdiction = root.get("jurisdiction") or {}
    children = _indexed_uuids(root_jurisdiction.get("childLocalities", []), "id")
    declarations = _indexed_uuids(root.get("localityElections", []), "jurisdictionId")
    registrations = _indexed_uuids(root.get("voterRegistration", []), "id")
    root_ballots = _api_count(root_election.get("ballotsCast"))
    county_uuid = _uuid(declared[2])
    if (
        root_election.get("electionDate") != "2026-11-03"
        or type(root_election.get("isOfficialResults")) is not bool
        or county_uuid not in children or county_uuid not in declarations
        or county_uuid not in registrations
        or children[county_uuid].get("shortName") != declared[1]
        or _english(children[county_uuid].get("name", [])) != declared[0]
    ):
        raise ValueError("Arizona root declaration or statewide backend-zero conflict changed")
    declared_ballots = sum(_api_count(item.get("ballotsCast")) for item in declarations.values())
    if root_ballots != 0 and root_ballots != declared_ballots:
        raise ValueError("Arizona root statewide count differs from declared county totals")
    precincts = {}
    for node in data.get("precincts", []):
        identity = _uuid(node.get("id", ""))
        if identity in precincts:
            raise ValueError("Duplicate Arizona precinct UUID")
        precincts[identity] = node
    turnout = {}
    for node in data.get("voterTurnout", []):
        identity = _uuid(node.get("id", ""))
        if identity in turnout:
            raise ValueError("Duplicate Arizona turnout UUID")
        turnout[identity] = node
    if not precincts or not set(turnout) <= set(precincts):
        raise ValueError("Arizona county turnout inventory changed")
    facts, query_rows, observed_ballots, observed_registered = {}, [], [], []
    for identity, precinct in precincts.items():
        label = _english(precinct.get("name", []))
        if type(precinct.get("isVirtual")) is not bool:
            raise ValueError("Arizona native virtual-precinct flag changed")
        node = turnout.get(identity)
        if node is None:
            value = registered = native_turnout = None
        else:
            if node.get("precinctName") != label:
                raise ValueError("Arizona precinct/turnout label conflict")
            value = _api_count(node.get("ballotsCast"))
            native_turnout = _api_count(node.get("voterTurnout"))
            registered = _api_count(node.get("voterRegistration"))
            if value != native_turnout:
                raise ValueError("Arizona native voter-turnout count differs from ballots")
            observed_ballots.append(value)
            observed_registered.append(registered)
        compact = {
            "election_date": "2026-11-03",
            "native_report_status_literal": (
                status + " · reportingStatus " + str(precinct.get("reportingStatus"))
            ),
            "native_count_clock": clock,
            "source_clock_timezone_literal": "UTC",
            "county_code": code,
            "county": name,
            "native_county_uuid": jurisdiction["id"],
            "precinct_code": precinct["id"],
            "precinct": label,
            "ballots": value,
            "registered_voters": registered,
            "native_voter_turnout_count": native_turnout,
            "native_observation_present": node is not None,
            "native_virtual_precinct": precinct["isVirtual"],
            "native_reporting_status": str(precinct.get("reportingStatus")),
            "query": {
                "native_report_status_literal": (
                    status + " · reportingStatus " + str(precinct.get("reportingStatus"))
                ),
                "source_clock_timezone_literal": "UTC",
            },
        }
        facts[identity] = {
            "name": label, "value": value, "registered": registered,
            "clock": clock,
            "status": status + " · reportingStatus " + str(precinct.get("reportingStatus")),
            "native": compact,
        }
        query_rows.append(compact)
    county_ballots = _api_count(election.get("ballotsCast"))
    county_registered = _api_count(election.get("totalVoters"))
    declaration = declarations[county_uuid]
    registration = registrations[county_uuid]
    if (
        sum(observed_ballots) != county_ballots
        or sum(observed_registered) != county_registered
        or county_ballots != _api_count(declaration.get("ballotsCast"))
        or county_registered != _api_count(declaration.get("totalVoters"))
        or county_registered != _api_count(registration.get("total"))
    ):
        raise ValueError("Arizona precinct/county participation reconciliation changed")
    source_pin, root_pin = pin(body), pin(root_body)
    updates = _updates(templates, facts, source_pin, url, "AZ")
    return {
        "updates": updates,
        "complete_native_query": [{
            "state_code": "AZ", "county_code": code, "county": name,
            "election_date": "2026-11-03",
            "native_report_status_literal": status,
            "root_native_report_status_literal": (
                "OFFICIAL" if root_election["isOfficialResults"] else "UNOFFICIAL"
            ),
            "source_pin": source_pin, "root_declaration_pin": root_pin,
            "root_backend_statewide_ballots": root_ballots,
            "root_declared_county_ballots": declared_ballots,
            "root_backend_zero_not_substituted_for_positive_county_counts": (
                root_ballots == 0 and county_ballots > 0
            ),
            "county_ballots": county_ballots, "county_registered_voters": county_registered,
            "rows": query_rows,
            "candidate_votes_used_as_ballots": False,
        }],
        "reviewed_source_url_bridge": _source_bridge(templates, url, "AZ"),
        "numerical_data_qualified": False,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }


def _worksheet_cell(table, address):
    values = [cell.get("value") for row in table.get("rows", [])
              for cell in row.get("cells", []) if cell.get("address") == address]
    if len(values) != 1:
        raise ValueError("Wyoming workbook heading cell inventory changed")
    return values[0]


def _validate_wyoming_heading(workbook, sheet, heading):
    summary = {
        "Statewide Total Ballots Cast":
            "Statewide Total Ballots Cast\nWyoming General Election - November 3, 2026",
        "Statewide Candidates":
            "Statewide Candidates Official Summary\nWyoming General Election - November 3, 2026",
        "Statewide Senate Odd":
            "Statewide Senate Official Summary\nWyoming General Election - November 3, 2026",
        "Statewide House":
            "Statewide House Official Summary\nWyoming General Election - November 3, 2026",
        "Statewide Judicial":
            "Statewide Judicial Retentions Official Summary\nWyoming General Election - November 3, 2026",
        "Statewide Ballot Issue":
            "Statewide Ballot Propositions Official Summary\nWyoming General Election - November 3, 2026",
    }
    if workbook == "2026 General Results Summaries - OFFICIAL.xlsx":
        expected = summary.get(sheet)
    elif workbook == "2026 County General PbP - OFFICIAL.xlsx":
        expected = (sheet + " County Official Precinct-by-Precinct Summary\n"
                    "Wyoming General Election - November 3, 2026")
    elif workbook == "2026 County General PbP TBC - OFFICIAL.xlsx":
        separator = ("Precinct-by Precinct"
                     if sheet in ("Albany", "Big Horn") else "Precinct-by-Precinct")
        expected = (sheet + " County Official " + separator + " Total Ballots Summary\n"
                    "Wyoming General Election - November 3, 2026")
    else:
        expected = None
    if heading != expected:
        raise ValueError("Wyoming workbook election/year/OFFICIAL heading changed")
    return heading


def _validate_wyoming_identity(product):
    for table in product.get("tables", []):
        _validate_wyoming_heading(
            table.get("workbook"), table.get("name"), _worksheet_cell(table, "B1"))


def _wyoming_parent_controls(precinct_ballots, precinct_house, county_ballots,
                             state_ballots, county_house, state_house):
    category_fields = tuple(WY_CATEGORIES)
    ballot_units = {(row["county"], row["precinct"]): row for row in precinct_ballots}
    house_units = {(row["county"], row["precinct"]): row for row in precinct_house}
    county_ballot_rows = {row["county"]: row for row in county_ballots}
    state_ballot_rows = {row["county"]: row for row in state_ballots}
    county_house_rows = {row["county"]: row for row in county_house}
    state_house_rows = {row["county"]: row for row in state_house}
    counties = set(county_ballot_rows)
    if (
        not ballot_units or set(ballot_units) != set(house_units)
        or not counties
        or set(county_house_rows) != counties
        or set(state_ballot_rows) != counties | {"Total"}
        or set(state_house_rows) != counties | {"Total"}
    ):
        raise ValueError("Wyoming native parent inventory changed")
    controls = []
    for county in sorted(counties):
        keys = [key for key in ballot_units if key[0] == county]
        ballot_sum = sum(ballot_units[key]["ballots"] for key in keys)
        category_sums = {
            field: sum(house_units[key][field] for key in keys) for field in category_fields}
        if (
            ballot_sum != county_ballot_rows[county]["ballots"]
            or ballot_sum != state_ballot_rows[county]["ballots"]
            or any(category_sums[field] != county_house_rows[county][field]
                   or category_sums[field] != state_house_rows[county][field]
                   for field in category_fields)
            or sum(category_sums.values()) != ballot_sum
        ):
            raise ValueError("Wyoming precinct/county/state ballot parent reconciliation changed")
        controls.append({
            "county": county, "precinct_ballots": ballot_sum,
            "printed_county_ballots": county_ballot_rows[county]["ballots"],
            "statewide_county_ballots": state_ballot_rows[county]["ballots"],
            "choice_accounting": {WY_CATEGORIES[field]: category_sums[field]
                                  for field in category_fields},
        })
    if (
        sum(row["ballots"] for county, row in state_ballot_rows.items() if county != "Total")
            != state_ballot_rows["Total"]["ballots"]
        or any(
            sum(row[field] for county, row in state_house_rows.items() if county != "Total")
                != state_house_rows["Total"][field]
            for field in category_fields)
        or sum(state_house_rows["Total"][field] for field in category_fields)
            != state_ballot_rows["Total"]["ballots"]
    ):
        raise ValueError("Wyoming statewide ballot parent reconciliation changed")
    return {
        "counties": controls,
        "statewide_ballots": state_ballot_rows["Total"]["ballots"],
        "statewide_choice_accounting": {
            WY_CATEGORIES[field]: state_house_rows["Total"][field] for field in category_fields},
        "all_precinct_county_state_ballot_parents_reconcile": True,
    }


def _wyoming(body, templates, url):
    if url != WY_REVIEWED_URL:
        raise ValueError("Wrong Wyoming reviewed workbook URL")
    source_pin = pin(body)
    spec = {
        "id": "wy-workbooks", "kind": "xlsx_zip", "state_code": "WY",
        "election_year": 2026, "url": url, "pin": source_pin,
        "retrieved_at_utc": None, "native_updated_at": None,
        "redistribution": "Public aggregate official workbook facts.", "members": WY_MEMBERS,
    }
    product = native_unpack(spec, body)
    _validate_wyoming_identity(product)
    ballot_spec = {
        "id": "wy-precinct-ballots", "product": "wy-workbooks",
        "workbook": "2026 County General PbP TBC - OFFICIAL.xlsx",
        "require": {"3": {"A": "Precinct", "B": "Total Ballots Cast"}},
        "first_row": 4,
        "fields": {"county": "$table", "precinct": "A", "ballots": "B"},
        "exclude": {"precinct": [None, "", "Total", "Precincts Continue\non Next Page"]},
        "keys": ["county", "precinct"], "counts": ["ballots"],
    }
    candidate_spec = {
        "id": "wy-precinct-house", "product": "wy-workbooks",
        "workbook": "2026 County General PbP - OFFICIAL.xlsx",
        "require": {
            "3": {"G": "United States Representative"},
            "4": {"A": "Precinct", "G": "Chuck\nGray (R)", "H": "Lisa\nKinney (D)",
                  "I": "Shawn\nJohnson (L)", "J": "Jeffrey\nHaggit (C)",
                  "K": "Write-Ins", "L": "Overvotes", "M": "Undervotes"},
        },
        "first_row": 5,
        "fields": {
            "county": "$table", "precinct": {"column": "A", "display": "excel_month_day"},
            "precinct_native_value": "A", "R": "G", "D": "H", "L": "I", "C": "J",
            "write_ins": "K", "overvotes": "L", "undervotes": "M",
        },
        "exclude": {"precinct": [None, "", "Total", "Precincts Continue\non Next Page"]},
        "keys": ["county", "precinct"],
        "counts": ["R", "D", "L", "C", "write_ins", "overvotes", "undervotes"],
    }
    county_ballot_spec = {
        "id": "wy-county-ballots", "product": "wy-workbooks",
        "workbook": "2026 County General PbP TBC - OFFICIAL.xlsx",
        "first_row": 4,
        "fields": {"county": "$table", "precinct": "A", "ballots": "B"},
        "where": {"precinct": ["Total"]}, "keys": ["county"], "counts": ["ballots"],
    }
    state_ballot_spec = {
        "id": "wy-state-ballots", "product": "wy-workbooks",
        "workbook": "2026 General Results Summaries - OFFICIAL.xlsx",
        "tables": ["Statewide Total Ballots Cast"],
        "require": {"4": {"B": "Total Ballots Cast"}},
        "first_row": 5, "last_row": 28,
        "fields": {"county": "A", "ballots": "B"},
        "keys": ["county"], "counts": ["ballots"],
    }
    county_house_spec = {
        "id": "wy-county-house", "product": "wy-workbooks",
        "workbook": "2026 County General PbP - OFFICIAL.xlsx", "first_row": 5,
        "fields": {
            "county": "$table", "precinct": "A", "R": "G", "D": "H", "L": "I", "C": "J",
            "write_ins": "K", "overvotes": "L", "undervotes": "M",
        },
        "where": {"precinct": ["Total"]}, "keys": ["county"],
        "counts": ["R", "D", "L", "C", "write_ins", "overvotes", "undervotes"],
    }
    state_house_spec = {
        "id": "wy-state-house", "product": "wy-workbooks",
        "workbook": "2026 General Results Summaries - OFFICIAL.xlsx",
        "tables": ["Statewide Candidates"],
        "require": {
            "3": {"G": "United States Representative"},
            "4": {"G": "Chuck\nGray (R)", "H": "Lisa\nKinney (D)",
                  "I": "Shawn\nJohnson (L)", "J": "Jeffrey\nHaggit (C)",
                  "K": "Write-Ins", "L": "Overvotes", "M": "Undervotes"},
        },
        "first_row": 5, "last_row": 28,
        "fields": {
            "county": "A", "R": "G", "D": "H", "L": "I", "C": "J",
            "write_ins": "K", "overvotes": "L", "undervotes": "M",
        },
        "keys": ["county"],
        "counts": ["R", "D", "L", "C", "write_ins", "overvotes", "undervotes"],
    }
    ballots = native_query(product, ballot_spec)["rows"]
    candidates = native_query(product, candidate_spec)["rows"]
    county_ballots = native_query(product, county_ballot_spec)["rows"]
    state_ballots = native_query(product, state_ballot_spec)["rows"]
    county_house = native_query(product, county_house_spec)["rows"]
    state_house = native_query(product, state_house_spec)["rows"]
    parent_controls = _wyoming_parent_controls(
        ballots, candidates, county_ballots, state_ballots, county_house, state_house)
    by_ballot = {(row["county"], row["precinct"]): row for row in ballots}
    by_candidate = {(row["county"], row["precinct"]): row for row in candidates}
    if set(by_ballot) != set(by_candidate) or len(by_ballot) != 432:
        raise ValueError("Wyoming complete native reporting-unit inventory changed")
    facts, query_rows = {}, []
    for key, ballot in by_ballot.items():
        candidate = by_candidate[key]
        categories = {literal: candidate[field] for field, literal in WY_CATEGORIES.items()}
        if sum(categories.values()) != ballot["ballots"]:
            raise ValueError("Wyoming candidate accounting differs from direct ballot count")
        compact = {
            "ballot_count_query": copy.deepcopy(ballot),
            "choice_accounting_query": copy.deepcopy(candidate),
            "counts_repaired": False,
            "legacy_identity_preserved_not_current_workbook_row": True,
            "native_original_pin": source_pin,
            "native_result_clock": None,
            "native_timezone": None,
        }
        facts[key] = {
            "name": key[1], "value": ballot["ballots"], "registered": None, "clock": None,
            "status": "OFFICIAL", "native": compact,
        }
        query_rows.append(compact)
    updates = _updates(templates, facts, source_pin, url, "WY")
    return {
        "updates": updates,
        "complete_native_query": [{
            "state_code": "WY", "election_date": "2026-11-03",
            "native_result_status_literal": "OFFICIAL",
            "source_pin": source_pin, "rows": query_rows,
            "registered_denominator_supplied": False,
            "source_clock_literal": None, "source_clock_timezone": None,
            "candidate_votes_used_as_ballots": False,
            "direct_ballot_rows_reconcile_to_choice_accounting": True,
            "parent_controls": parent_controls,
        }],
        "reviewed_source_url_bridge": _source_bridge(templates, url, "WY"),
        "numerical_data_qualified": False,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }


def statistics(body, templates, url, acquire=None):
    """Parse one reviewed numerical source and return exact full-replacement updates."""
    if not templates:
        raise ValueError("A reviewed native family source cannot have an empty template inventory")
    routes = [route(template) for template in templates]
    if any(item is None or item["url"] != url for item in routes):
        raise ValueError("Reviewed native family source/template routing changed")
    states = {item["state"] for item in routes}
    if len(states) != 1:
        raise ValueError("One reviewed native source cannot span states")
    state = states.pop()
    if state == "AR":
        return _arkansas(body, templates, url)
    if state == "AZ":
        return _arizona(body, templates, url, acquire)
    return _wyoming(body, templates, url)
