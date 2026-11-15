"""Strict refresh of reviewed JSON statistics without creating geographic joins."""

from collections import Counter
from datetime import datetime
from decimal import Decimal
import json
import re

from scripts.participation_intake.contract import count, pin
from scripts.results_granular import change, public_facts


PORTER_URL = (
    "https://app.enhancedvoting.com/results/public/api/elections/"
    "porter-county-in/GeneralNov032026"
)
MONROE_URL = (
    "https://services1.arcgis.com/nYfGJ9xFTKW6VPqW/arcgis/rest/services/"
    "Join_Features_to_MonroeCountyGeneralElection2026_Precincts_inner_view/"
    "FeatureServer/0/query?where=1%3D1&outFields=Precinct_ID%2CPrecinct%2C"
    "Registered_Voters%2CBallots_Cast%2CTurnout_Percentage%2CPrecinct_Reporting"
    "&returnDistinctValues=true&returnGeometry=false&orderByFields=Precinct_ID&f=json"
)
PROFILES = {
    PORTER_URL: {
        "state": "IN", "county": "Porter County", "layout": "election_summary",
        "election_id": "01000000-e138-d223-a89a-08df2ed94aa0",
        "jurisdiction_id": "a00fe01c-80ed-404a-b9bf-9845a21b7b1b",
    },
    MONROE_URL: {
        "state": "IN", "county": "Monroe County", "layout": "distinct_layer_indicator",
        "units": 103,
    },
}
MONROE_FIELDS = {
    "Precinct_ID": ("esriFieldTypeInteger", "Precinct ID"),
    "Precinct": ("esriFieldTypeString", "Precinct"),
    "Registered_Voters": ("esriFieldTypeInteger", "Registered Voters"),
    "Ballots_Cast": ("esriFieldTypeInteger", "Ballots Cast"),
    "Turnout_Percentage": ("esriFieldTypeInteger", "Turnout Percentage"),
    "Precinct_Reporting": ("esriFieldTypeString", "Precinct Reporting"),
}
COUNT_MEASURE = {
    "id": "previously-reviewed-participation-count", "kind": "participation_reported",
    "mode": "source_defined", "unit": "source_reported_count",
}
INDICATOR = "Publisher-defined distinct Precinct_ID indicator, reproduced without geographic filtering"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate native JSON object key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Nonfinite native JSON statistic: " + value)


def _number(value, *, whole_float=False):
    if whole_float and type(value) is float and value.is_integer():
        value = int(value)
    if type(value) is not int:
        raise ValueError("A blank, fractional, boolean or textual JSON value is not a native count")
    return count(value)


def _clock(value):
    if not isinstance(value, str) or re.fullmatch(
            r"[0-9]{4}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]"
            r"(?:\.[0-9]{1,9})?Z", value) is None:
        raise ValueError("Expected a native UTC report clock")
    seconds, _, fraction = value[:-1].partition(".")
    parsed = datetime.strptime(seconds, "%Y-%m-%dT%H:%M:%S")
    if not datetime(2026, 11, 3) <= parsed < datetime(2027, 2, 1):
        raise ValueError("Native clock is outside the reviewed election update window")
    return parsed, Decimal("0." + (fraction or "0"))


def _native(template):
    native = template["view"].get("native_record") or {}
    return native.get("native_fields", native)


def _scope(templates, profile, url):
    if not templates:
        raise ValueError("No reviewed statistical templates")
    for template in templates:
        measure = template["measure"]
        if (template["geography"]["state_code"] != profile["state"]
                or template["election"]["year"] != 2026
                or template["election"]["type"] != "general"
                or template["view"].get("source_url") != url
                or template["view"].get("county") != profile["county"]
                or template["count"]["status"] != "reported"
                or template["denominator"] is not None
                or any(measure.get(key) != value for key, value in COUNT_MEASURE.items())):
            raise ValueError("Reviewed JSON election, measure, source or county scope changed")


def _facts(query, native_fields, body, *, timezone=None):
    result = {
        "query": query, "native_fields": native_fields, "private_original_pin": pin(body),
        "native_report_status_literal": query["native_report_status_literal"],
        "native_reporting_complete_qualified": False,
        "retained_source_context_is_historical": True,
        "whole_publisher_html_redistributed": False,
    }
    if timezone:
        result["source_clock_timezone_literal"] = timezone
    return result


def _summary(data, templates, profile, body):
    if (len(templates) != 1
            or templates[0]["geography"]["level"] != "county"
            or templates[0]["geography"]["name"] != profile["county"]
            or templates[0]["measure"]["literal"] != "ballotsCast"
            or data.get("id") != profile["election_id"]
            or data.get("jurisdictionId") != profile["jurisdiction_id"]
            or data.get("electionDate") != "2026-11-03"
            or data.get("name") != [{"languageId": "en", "text": "2026 General Election"}]
            or data.get("dateText") != [{"languageId": "en", "text": "November 3, 2026"}]
            or data.get("isProduction") is not True
            or data.get("isPrimary") is not False
            or type(data.get("isOfficialResults")) is not bool):
        raise ValueError("Native election summary identity or production/general scope changed")
    template = templates[0]
    previous = _native(template)
    if (previous.get("id") != profile["election_id"]
            or previous.get("jurisdictionId") != profile["jurisdiction_id"]):
        raise ValueError("Accepted native election identity changed")
    clock = data.get("asOf")
    current = _clock(clock)
    if _clock(previous.get("asOf")) != _clock(template["source_clock"]["literal"]):
        raise ValueError("Accepted summary clock and native query disagree")
    if current < _clock(template["source_clock"]["literal"]):
        raise ValueError("Native summary clock regressed")
    for key in ("lastUpdated", "publishDate"):
        if _clock(data.get(key)) < _clock(previous.get(key)):
            raise ValueError("Native summary edition regressed")
    if _clock(data["lastUpdated"]) > current or current > _clock(data["publishDate"]):
        raise ValueError("Native summary clocks disagree")
    value = _number(data.get("ballotsCast"), whole_float=True)
    _number(data.get("totalVoters"), whole_float=True)
    _number(data.get("precinctsReporting"), whole_float=True)
    if any(not isinstance(data.get(key), list) for key in (
            "groupReportingStatus", "precinctReportingStatus", "countGroups")):
        raise ValueError("Native summary reporting status arrays changed")
    status = "isOfficialResults=" + str(data["isOfficialResults"]).lower()
    query = {
        "query_id": "reviewed-native-election-summary", "count": value,
        "source_clock": clock, "source_clock_timezone_literal": "UTC",
        "native_report_status_literal": status,
        "native_election_id": data["id"], "native_jurisdiction_id": data["jurisdictionId"],
        "native_fields": data,
    }
    return [change(template, value, _facts(query, data, body, timezone="UTC"), clock=clock)], [query]


def _distinct_indicator(data, templates, profile, body):
    fields = data.get("fields")
    if (data.get("exceededTransferLimit", False) is not False
            or "error" in data or not isinstance(fields, list)
            or len(fields) != len(MONROE_FIELDS)
            or any(not isinstance(field, dict) for field in fields)
            or {field.get("name"): (field.get("type"), field.get("alias"))
                for field in fields} != MONROE_FIELDS
            or not isinstance(data.get("features"), list)):
        raise ValueError("Incomplete or changed native statistical field inventory")
    rows = {}
    for feature in data["features"]:
        if not isinstance(feature, dict) or set(feature) != {"attributes"}:
            raise ValueError("Expected complete native attributes without inferred geometry")
        row = feature["attributes"]
        if not isinstance(row, dict) or set(row) != set(MONROE_FIELDS):
            raise ValueError("Native statistical row columns changed")
        identity = _number(row["Precinct_ID"])
        for key in ("Registered_Voters", "Ballots_Cast"):
            _number(row[key])
        if row["Turnout_Percentage"] is not None:
            _number(row["Turnout_Percentage"])
        if any(not isinstance(row[key], str) or not row[key].strip()
               for key in ("Precinct", "Precinct_Reporting")):
            raise ValueError("Native unit identity/status is missing")
        if identity in rows:
            raise ValueError("Duplicate native Precinct_ID is not a distinct reporting unit")
        rows[identity] = row
    expected, parents = {}, []
    for template in templates:
        native = _native(template)
        if template["geography"]["level"] == "reporting_unit":
            identity = _number(native.get("Precinct_ID"))
            if (identity in expected or template["measure"]["literal"] != "Native Ballots Cast"
                    or native.get("Precinct") != template["view"].get("unit")
                    or native.get("Precinct") != template["geography"]["name"]):
                raise ValueError("Accepted literal statistical unit binding changed")
            expected[identity] = template
        elif (template["geography"]["level"] == "county"
                and template["geography"]["name"] == profile["county"]
                and template["measure"]["literal"] == "Total Ballots Cast"
                and native.get("derivation") == INDICATOR
                and native.get("distinct_native_precincts") == profile["units"]):
            parents.append(template)
        else:
            raise ValueError("Unreviewed native indicator/parent scope")
    if (len(parents) != 1 or len(rows) != profile["units"]
            or set(rows) != set(expected)
            or any(row["Precinct"] != _native(expected[key])["Precinct"] for key, row in rows.items())):
        raise ValueError("Complete accepted native reporting-unit inventory changed")
    ordered = [rows[key] for key in sorted(rows)]
    statuses = dict(sorted(Counter(row["Precinct_Reporting"] for row in ordered).items()))
    parent = {
        "county": "Monroe", "publisher_indicator": "Total Ballots Cast",
        "derivation": INDICATOR, "distinct_native_precincts": len(rows),
        "native_precinct_reporting": statuses,
    }
    parent_query = {
        **parent, "query_id": "reviewed-distinct-native-layer-indicator",
        "count": _number(sum(row["Ballots_Cast"] for row in ordered)), "source_clock": None,
        "native_report_status_literal": next(iter(statuses)) if len(statuses) == 1 else None,
    }
    updates = [change(parents[0], parent_query["count"], _facts(parent_query, parent, body))]
    queries = [parent_query]
    for identity, row in sorted(rows.items()):
        query = {
            "query_id": "reviewed-native-layer-unit", "native_unit_id": identity,
            "count": row["Ballots_Cast"], "registered": row["Registered_Voters"],
            "source_clock": None, "native_report_status_literal": row["Precinct_Reporting"],
            "native_fields": row,
        }
        queries.append(query)
        updates.append(change(expected[identity], row["Ballots_Cast"], _facts(query, row, body),
                              registered=row["Registered_Voters"]))
    return updates, queries


def statistics(body, templates, url):
    profile = PROFILES[url]
    _scope(templates, profile, url)
    data = json.loads(body.decode("utf-8-sig"), object_pairs_hook=_unique, parse_constant=_nonfinite)
    if not isinstance(data, dict):
        raise ValueError("Expected a native statistical JSON object")
    public_facts(data)
    parser = _summary if profile["layout"] == "election_summary" else _distinct_indicator
    updates, queries = parser(data, templates, profile, body)
    return {
        "updates": updates, "complete_native_query": queries,
        "factual_product": {"native_json": data, "source_pin": pin(body)},
        "native_column_bindings": profile,
        "geographic_joins_changed": False, "analytical_rates_promoted": False,
        "reporting_counters_not_certification_or_all_machine_completeness": True,
    }
