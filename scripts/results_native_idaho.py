"""Refresh Idaho's reviewed county and reporting-unit ballot observations."""

import copy
from datetime import datetime, timezone
import io
import json
import re
from urllib.parse import quote, urlsplit

from scripts.participation_intake.contract import digest, encoded, pin
from scripts.results_granular import public_facts


ADAPTER = "reviewed_idaho_ballots_by_precinct"
ENTRY_URL = "https://results.voteidaho.gov/results/public/id/elections/nov2026"
DATA_URL = (
    "https://results.voteidaho.gov/results/public/api/elections/id/nov2026/data"
)
JURISDICTION = "8c9d6490-6c2e-460e-8e42-0d1c8609ce42"
ELECTION_ID = "01000000-9c16-51a0-5d47-08df20ba1eaa"
CDN_ROOT = "https://results.voteidaho.gov/cdn/results/" + JURISDICTION + "/"
STORED_URL = "https://www.themarginoferror.com/participation-local/ID.json.gz"
COUNTY_SOURCE_ID = (
    "accepted-export:efe2bfce82528da8e8fa01323a3d1eba9c6e78c249fe753f6b65cb628d3d9f81:"
    "counties"
)
UNIT_SOURCE_ID = (
    "accepted-export:efe2bfce82528da8e8fa01323a3d1eba9c6e78c249fe753f6b65cb628d3d9f81:"
    "precincts"
)
SOURCE_IDS = {COUNTY_SOURCE_ID, UNIT_SOURCE_ID}
INITIAL_FULL_PIN = "1a7b5fe2d6cb47a0d613046079b194223b7544609f7d38d919ae23acbe887976"
IDENTITY_PIN = "0b5d60ff480b625c1b246a9f769221c7af83c17414bcdceea2c53c86e9f44ee3"
QUALIFICATION_PIN = "d82d83d77100f93a9f82746ca91bdf4ced86b5503bd9af6a0b9a2a9fab752f64"
WORKBOOK_FIELDS = (
    "County",
    "Precinct",
    "Total Number of Registered Voters at the cutoff",
    "Total Number of Election Day Registrants",
    "Total Number of Registered Voters",
    "Total Number of Ballots Cast",
    "% of Registered Voters who Voted",
)
REPORT_PATTERNS = {
    "ballots": re.compile(r"Ballots Cast by Precinct_[A-Za-z0-9-]+\.xlsx"),
    "summary_pdf": re.compile(
        r"Summary Results with Contest-Level Details_[A-Za-z0-9-]+\.PDF"
    ),
    "detail_pdf": re.compile(
        r"Detailed Results with Write-Ins by Contest Table_[A-Za-z0-9-]+\.pdf"
    ),
    "results_workbook": re.compile(r"Results_[A-Za-z0-9-]+\.xlsx"),
}
PERCENT = re.compile(r"(?:0|[1-9][0-9]{0,2}(?:,[0-9]{3})*) %")
ISO_CLOCK = re.compile(
    r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:"
    r"[0-5][0-9](?:\.[0-9]{1,7})?Z"
)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Idaho native JSON property")
        result[key] = value
    return result


def _integer(value, label):
    if isinstance(value, bool):
        raise ValueError("Invalid Idaho " + label)
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and value >= 0 and value.is_integer():
        return int(value)
    raise ValueError("Missing or invalid Idaho " + label + " is not zero")


def _english(values, label):
    if not isinstance(values, list):
        raise ValueError("Missing Idaho " + label)
    found = [
        row.get("text")
        for row in values
        if isinstance(row, dict) and row.get("languageId") == "en"
    ]
    if len(found) != 1 or not isinstance(found[0], str) or not found[0].strip():
        raise ValueError("Missing or ambiguous Idaho English " + label)
    return found[0]


def _clock(value, label):
    if not isinstance(value, str) or ISO_CLOCK.fullmatch(value) is None:
        raise ValueError("Missing or changed Idaho " + label)
    base = value[:-1]
    if "." in base:
        prefix, fraction = base.split(".", 1)
        base = prefix + "." + (fraction + "000000")[:6]
    parsed = datetime.fromisoformat(base + "+00:00")
    if not (
        datetime(2026, 11, 3, tzinfo=timezone.utc)
        <= parsed
        < datetime(2027, 2, 1, tzinfo=timezone.utc)
    ):
        raise ValueError("Idaho source clock is outside the declared election")
    return parsed


def _workbook_url(value):
    parsed = urlsplit(value) if isinstance(value, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.hostname != "results.voteidaho.gov"
        or not parsed.path.startswith("/cdn/results/" + JURISDICTION + "/")
    ):
        return False
    name = parsed.path.rsplit("/", 1)[-1]
    return REPORT_PATTERNS["ballots"].fullmatch(name.replace("%20", " ")) is not None


def _template_kind(template):
    source_id = template.get("source", {}).get("id")
    if source_id == COUNTY_SOURCE_ID:
        return "county"
    if source_id == UNIT_SOURCE_ID:
        return "reporting_unit"
    return None


def _native_identity(template):
    kind = _template_kind(template)
    native = template.get("view", {}).get("native_record", {})
    if kind == "county":
        if native.get("native_kind") == "county":
            county = native.get("county")
            jurisdiction_id = native.get("jurisdiction_id")
            locality_election_id = native.get("locality_election_id")
        else:
            registration = native.get("voter_registration", {})
            locality = native.get("locality_election", {})
            county = _english(registration.get("localityName"), "county identity")
            jurisdiction_id = registration.get("id")
            locality_election_id = locality.get("id")
        return {
            "kind": kind,
            "county": county,
            "jurisdiction_id": jurisdiction_id,
            "locality_election_id": locality_election_id,
        }
    if kind == "reporting_unit":
        return {
            "kind": kind,
            "county": native.get("county"),
            "precinct": native.get("precinct"),
            "unit_key": native.get("unit_key", native.get("key")),
            "reporting_unit_kind": native.get(
                "reporting_unit_kind", template.get("view", {}).get("unit_kind")
            ),
        }
    raise ValueError("Unreviewed Idaho source family")


def _identity(template):
    return {
        "id": template["id"],
        "election": template["election"],
        "geography": template["geography"],
        "measure": template["measure"],
        "source_id": template["source"]["id"],
        "denominator_basis": (
            None
            if template.get("denominator") is None
            else template["denominator"]["basis"]
        ),
        "maps_approved": template["view"].get("maps_approved"),
        "native_identity": _native_identity(template),
    }


def _inventory(templates, identity=False):
    rows = [_identity(row) if identity else row for row in templates]
    return digest(encoded(sorted(rows, key=lambda row: row["id"])))


def _qualification_pin(templates):
    return digest(encoded(sorted([
        {
            "id": row["id"],
            "qualified": row["denominator"]["qualified"],
            "basis": row["denominator"]["basis"],
            "complete": row["reporting_status"]["complete"],
            "maps_approved": row["view"]["maps_approved"],
        }
        for row in templates
    ], key=lambda row: row["id"])))


def _route_contract(template):
    kind = _template_kind(template)
    source = template.get("source", {})
    view = template.get("view", {})
    source_url = source.get("url")
    if (
        kind is None
        or template.get("contract") != "participation.observation.v1"
        or template.get("geography", {}).get("state_code") != "ID"
        or template.get("geography", {}).get("level")
        != ("county" if kind == "county" else "reporting_unit")
        or template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("type") != "general"
        or template.get("measure", {}).get("id")
        != "previously-reviewed-participation-count"
        or source.get("classification") != "public_aggregate"
        or source.get("fields") != view
        or view.get("maps_approved") is not (kind == "county")
        or source_url not in (STORED_URL, DATA_URL)
        and not _workbook_url(source_url)
    ):
        raise ValueError("Idaho accepted source, identity or qualification scope changed")
    return kind


def route(template):
    if _template_kind(template) is None:
        return None
    _route_contract(template)
    return {"state": "ID", "adapter": ADAPTER, "url": DATA_URL}


def validate_templates(templates):
    if len(templates) != 1030 or len({row["id"] for row in templates}) != 1030:
        raise ValueError("Complete Idaho county/reporting-unit inventory is required")
    counts = {"county": 0, "reporting_unit": 0}
    for template in templates:
        kind = _route_contract(template)
        counts[kind] += 1
        view = template["view"]
        denominator = template.get("denominator")
        native = view["native_record"]
        if (
            template["source"]["fields"] != view
            or view.get("ballots") != template["count"]["value"]
            or view.get("denominator")
            != (None if denominator is None else denominator["value"])
            or denominator is None
            or view.get("reported_pct")
            != (
                100 * template["count"]["value"] / denominator["value"]
                if denominator["qualified"]
                else None
            )
            or template["reporting_status"].get("complete") is not None
        ):
            raise ValueError("Idaho canonical count, denominator or view coherence changed")
        if kind == "county":
            if (
                view.get("county") != template["geography"]["name"]
                or view.get("unit") is not None
                or view.get("denominator_basis") != "native_total_registered_voters"
            ):
                raise ValueError("Idaho county parent scope changed")
        elif (
            view.get("county") != _native_identity(template)["county"]
            or view.get("unit") != _native_identity(template)["precinct"]
            or view.get("denominator_basis") != "native_registered_voters"
        ):
            raise ValueError("Idaho reporting-unit scope changed")
        if native.get("native_kind") is not None:
            query = native.get("query", {})
            source_pin = native.get("source_original_pin")
            expected_input = (
                "data_api" if kind == "county" else "ballots_workbook")
            common_native_fields = {
                "contract", "native_kind", "source_input",
                "source_original_pin", "native_report_status_literal",
                "native_reporting_complete_qualified", "maps_approved",
                "candidate_votes_not_used_as_ballots",
                "registration_stock_not_ballot_denominator_substitute",
                "county_to_unit_allocation", "analytical_rates_promoted",
                "query",
            }
            expected_native_fields = common_native_fields | (
                {
                    "county", "jurisdiction_id", "locality_election_id",
                    "source_as_of", "source_last_updated",
                    "is_official_results",
                    "source_clock_timezone_literal",
                }
                if kind == "county" else
                {
                    "unit_key", "county", "precinct",
                    "reporting_unit_kind", "source_clock_scope",
                    "parent_api_context", "workbook_source_clock",
                    "workbook_source_timezone",
                    "retained_house_contest_ballots_context",
                    "retained_quality_flags",
                }
            )
            if (
                set(native) != expected_native_fields
                or native.get("contract")
                    != "participation.idaho_native_refresh.v1"
                or native.get("source_input") != expected_input
                or not isinstance(source_pin, dict)
                or set(source_pin) != {"url", "bytes", "sha256"}
                or source_pin["url"] != template["source"]["url"]
                or source_pin["sha256"] != template["source"]["input_sha256"]
                or not isinstance(source_pin["bytes"], int)
                or source_pin["bytes"] < 1
                or re.fullmatch(r"[a-f0-9]{64}", source_pin["sha256"]) is None
                or query.get("ballots_cast") != template["count"]["value"]
                or query.get("registered_voters") != denominator["value"]
                or native.get("maps_approved") != view["maps_approved"]
                or native.get("native_reporting_complete_qualified") is not False
                or native.get("candidate_votes_not_used_as_ballots") is not True
                or native.get(
                    "registration_stock_not_ballot_denominator_substitute"
                ) is not True
                or native.get("county_to_unit_allocation") is not False
                or native.get("analytical_rates_promoted") is not False
                or template["source"].get("selector", {}).get("native_refresh")
                    != native
                or query.get("native_kind") != kind
                or query.get("native_report_status_literal")
                    != native.get("native_report_status_literal")
                or view.get("source_status_literal")
                    != native.get("native_report_status_literal")
                or template["reporting_status"].get("literal")
                    != native.get("native_report_status_literal")
            ):
                raise ValueError("Projected Idaho source vector or holds changed")
            if kind == "county":
                county_query_fields = {
                    "native_kind", "county", "jurisdiction_id",
                    "locality_election_id", "ballots_cast",
                    "registered_voters", "source_as_of",
                    "source_last_updated",
                    "source_clock_timezone_literal",
                    "native_report_status_literal", "is_official_results",
                    "precinct_reporting_status",
                }
                if isinstance(query, dict):
                    _clock(
                        query.get("source_as_of"),
                        "projected county as-of clock")
                    _clock(
                        query.get("source_last_updated"),
                        "projected county last-updated clock")
                if (
                    not isinstance(query, dict)
                    or set(query) != county_query_fields
                    or source_pin["url"] != DATA_URL
                    or query.get("county") != native.get("county")
                    or query.get("jurisdiction_id")
                        != native.get("jurisdiction_id")
                    or query.get("locality_election_id")
                        != native.get("locality_election_id")
                    or query.get("source_as_of") != native.get("source_as_of")
                    or query.get("source_last_updated")
                        != native.get("source_last_updated")
                    or query.get("is_official_results")
                        != native.get("is_official_results")
                    or type(query.get("is_official_results")) is not bool
                    or query.get("source_clock_timezone_literal") != "UTC"
                    or native.get("source_clock_timezone_literal") != "UTC"
                    or template["source_clock"] != {
                        "literal": query.get("source_as_of"),
                        "timezone": "UTC",
                        "qualification": "native_clock_or_explicitly_not_supplied",
                    }
                    or view.get("source_update_label")
                        != query.get("source_as_of")
                ):
                    raise ValueError(
                        "Projected Idaho county clock, status or source vector differs")
            else:
                context = query.get("parent_api_context")
                if isinstance(context, dict):
                    _clock(
                        context.get("source_as_of"),
                        "projected parent county as-of clock")
                    _clock(
                        context.get("source_last_updated"),
                        "projected parent county last-updated clock")
                unit_query_fields = {
                    "native_kind", "unit_key", "county", "precinct",
                    "reporting_unit_kind", "registered_at_cutoff",
                    "election_day_registrants", "registered_voters",
                    "ballots_cast", "source_reported_percent",
                    "parent_api_context", "source_clock_scope",
                    "workbook_source_clock", "workbook_source_timezone",
                    "native_report_status_literal",
                }
                parent_fields = {
                    "county", "jurisdiction_id", "locality_election_id",
                    "source_as_of", "source_last_updated",
                    "source_clock_timezone_literal", "is_official_results",
                    "native_report_status_literal",
                    "precinct_reporting_status",
                }
                if (
                    not isinstance(query, dict)
                    or set(query) != unit_query_fields
                    or not _workbook_url(source_pin["url"])
                    or query.get("unit_key") != native.get("unit_key")
                    or query.get("county") != native.get("county")
                    or query.get("precinct") != native.get("precinct")
                    or query.get("reporting_unit_kind")
                        != native.get("reporting_unit_kind")
                    or query.get("source_clock_scope")
                        != "parent_api_context_not_workbook_clock"
                    or native.get("source_clock_scope")
                        != query.get("source_clock_scope")
                    or query.get("workbook_source_clock") is not None
                    or query.get("workbook_source_timezone") is not None
                    or native.get("workbook_source_clock") is not None
                    or native.get("workbook_source_timezone") is not None
                    or "source_clock_timezone_literal" in query
                    or "source_clock_timezone_literal" in native
                    or not isinstance(context, dict)
                    or set(context) != parent_fields
                    or context != native.get("parent_api_context")
                    or context.get("source_clock_timezone_literal") != "UTC"
                    or type(context.get("is_official_results")) is not bool
                    or context.get("native_report_status_literal")
                        != native.get("native_report_status_literal")
                    or template["source_clock"] != {
                        "literal": None,
                        "timezone": None,
                        "qualification": "native_clock_or_explicitly_not_supplied",
                    }
                    or view.get("source_update_label") is not None
                    or not isinstance(
                        native.get("retained_quality_flags"), list)
                ):
                    raise ValueError(
                        "Projected Idaho unit clock, parent context or source vector differs")
    if counts != {"county": 44, "reporting_unit": 986}:
        raise ValueError("Idaho native family cardinality changed")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("Idaho accepted identities changed")
    if _qualification_pin(templates) != QUALIFICATION_PIN:
        raise ValueError(
            "Idaho denominator qualification, completeness or map masks changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_URL]
    if initial and (
        len(initial) != len(templates) or _inventory(initial) != INITIAL_FULL_PIN
    ):
        raise ValueError("Initial complete Idaho accepted source frame changed")


def validate_plan(plan):
    selected = [
        source
        for source in plan.get("ID", {}).values()
        if source.get("adapter") == ADAPTER
    ]
    if not selected:
        return plan
    if len(selected) != 1 or selected[0].get("url") != DATA_URL:
        raise ValueError("Exactly one complete Idaho native source is required")
    validate_templates(selected[0]["templates"])
    return plan


def _declared_workbook(document):
    election = document.get("election", {})
    if (
        election.get("id") != ELECTION_ID
        or election.get("jurisdictionId") != JURISDICTION
        or election.get("electionDate") != "2026-11-03"
        or election.get("isPrimary") is not False
        or election.get("isProduction") is not True
        or type(election.get("isOfficialResults")) is not bool
        or _english(election.get("name"), "election name")
        != "General Election - November 3, 2026"
        or document.get("jurisdiction", {}).get("id") != JURISDICTION
    ):
        raise ValueError("Incorrect Idaho general-election authority")
    _clock(election.get("asOf"), "state as-of clock")
    _clock(election.get("lastUpdated"), "state last-updated clock")
    categories = election.get("publicReportCategories")
    reports = (
        categories[0].get("reports")
        if isinstance(categories, list) and len(categories) == 1
        and isinstance(categories[0], dict)
        else None
    )
    if not isinstance(reports, list) or len(reports) != len(REPORT_PATTERNS):
        raise ValueError("Incomplete Idaho official report declaration")
    found = {}
    for report in reports:
        name = report.get("blobName") if isinstance(report, dict) else None
        roles = [
            role for role, pattern in REPORT_PATTERNS.items()
            if isinstance(name, str) and pattern.fullmatch(name)
        ]
        if len(roles) != 1 or roles[0] in found:
            raise ValueError("Changed or duplicate Idaho official report role")
        found[roles[0]] = name
    if set(found) != set(REPORT_PATTERNS):
        raise ValueError("Missing Idaho official report role")
    return CDN_ROOT + quote(found["ballots"], safe="")


def _county_records(document, templates):
    expected = {
        _native_identity(row)["jurisdiction_id"]: {
            "county": _native_identity(row)["county"],
            "locality_election_id": _native_identity(row)["locality_election_id"],
            "template": row,
        }
        for row in templates
        if _template_kind(row) == "county"
    }
    if len(expected) != 44 or None in expected:
        raise ValueError("Incomplete Idaho county template identities")
    registrations = {}
    for row in document.get("voterRegistration", []):
        identity = row.get("id") if isinstance(row, dict) else None
        county = _english(row.get("localityName"), "county registration name")
        total = _integer(row.get("total"), "county registration")
        active = _integer(row.get("activeVoters"), "active county registration")
        inactive = _integer(row.get("inactiveVoters"), "inactive county registration")
        if identity in registrations:
            raise ValueError("Duplicate Idaho county registration")
        registrations[identity] = {
            "county": county, "registered_voters": total,
            "active_voters": active, "inactive_voters": inactive,
        }
    localities = {}
    for row in document.get("localityElections", []):
        identity = row.get("jurisdictionId") if isinstance(row, dict) else None
        if (
            identity in localities
            or row.get("electionDate") != "2026-11-03"
            or row.get("isPrimary") is not False
            or row.get("isProduction") is not True
            or _english(row.get("name"), "county election name")
            != "General Election - November 3, 2026"
        ):
            raise ValueError("Duplicate or incorrect Idaho county election")
        localities[identity] = {
            "locality_election_id": row.get("id"),
            "ballots_cast": _integer(row.get("ballotsCast"), "county ballots"),
            "registered_voters": _integer(
                row.get("totalVoters"), "county electorate"
            ),
            "as_of": row.get("asOf"),
            "last_updated": row.get("lastUpdated"),
            "is_official_results": row.get("isOfficialResults"),
            "precinct_reporting_status": copy.deepcopy(
                row.get("precinctReportingStatus")
            ),
        }
        _clock(row.get("asOf"), "county as-of clock")
        _clock(row.get("lastUpdated"), "county last-updated clock")
        if type(row.get("isOfficialResults")) is not bool:
            raise ValueError("Missing Idaho county result status")
    if set(registrations) != set(expected) or set(localities) != set(expected):
        raise ValueError("Idaho county API/template inventory changed")
    records = {}
    for identity, declared in expected.items():
        registration, locality = registrations[identity], localities[identity]
        if (
            registration["county"] != declared["county"]
            or locality["locality_election_id"]
            != declared["locality_election_id"]
            or locality["registered_voters"] != registration["registered_voters"]
        ):
            raise ValueError("Idaho county identity or registration frame changed")
        prior = declared["template"]["view"]["native_record"]
        prior_clock = (
            prior.get("source_as_of")
            if prior.get("native_kind") == "county"
            else prior.get("locality_election", {}).get("asOf")
        )
        if prior_clock is not None and _clock(
            locality["as_of"], "county as-of clock"
        ) < _clock(prior_clock, "prior county as-of clock"):
            raise ValueError("Idaho county source clock regressed")
        prior_official = (
            prior.get("is_official_results")
            if prior.get("native_kind") == "county"
            else prior.get("locality_election", {}).get("isOfficialResults")
        )
        if prior_official is True and locality["is_official_results"] is not True:
            raise ValueError("Idaho county official status rolled back")
        records[declared["county"]] = {
            "county": declared["county"],
            "jurisdiction_id": identity,
            **locality,
            "active_voters": registration["active_voters"],
            "inactive_voters": registration["inactive_voters"],
        }
    state_total = _integer(
        document["election"].get("totalVoters"), "state registration stock"
    )
    if state_total != sum(row["registered_voters"] for row in records.values()):
        raise ValueError("Idaho county API registration does not reconcile statewide")
    return records


def _workbook_records(body, templates):
    from openpyxl import load_workbook

    expected = {
        (_native_identity(row)["county"], _native_identity(row)["precinct"]): row
        for row in templates
        if _template_kind(row) == "reporting_unit"
    }
    if len(expected) != 986:
        raise ValueError("Incomplete Idaho reporting-unit template identities")
    try:
        book = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    except Exception as error:
        raise ValueError("Unreadable Idaho ballots workbook") from error
    try:
        if book.sheetnames != ["Ballots Cast by Precinct"]:
            raise ValueError("Changed Idaho ballots workbook inventory")
        rows = book["Ballots Cast by Precinct"].iter_rows(values_only=True)
        header = next(rows)
        if (
            tuple(header[: len(WORKBOOK_FIELDS)]) != WORKBOOK_FIELDS
            or any(value is not None for value in header[len(WORKBOOK_FIELDS):])
        ):
            raise ValueError("Changed Idaho ballots workbook schema")
        records = {}
        for values in rows:
            if not any(value is not None for value in values):
                continue
            if any(value is not None for value in values[len(WORKBOOK_FIELDS):]):
                raise ValueError("Unexpected Idaho workbook data outside reviewed columns")
            county, precinct = values[:2]
            key = county, precinct
            if (
                not isinstance(county, str)
                or not county
                or not isinstance(precinct, str)
                or not precinct
                or key in records
            ):
                raise ValueError("Duplicate or missing Idaho reporting-unit identity")
            cutoff, election_day, registered, ballots = [
                _integer(value, label)
                for value, label in zip(
                    values[2:6],
                    (
                        "registration at cutoff",
                        "election-day registration",
                        "reporting-unit registration",
                        "reporting-unit ballots",
                    ),
                )
            ]
            printed = values[6]
            if not isinstance(printed, str) or PERCENT.fullmatch(printed) is None:
                raise ValueError("Changed Idaho printed participation fraction")
            records[key] = {
                "county": county,
                "precinct": precinct,
                "registered_at_cutoff": cutoff,
                "election_day_registrants": election_day,
                "registered_voters": registered,
                "ballots_cast": ballots,
                "source_reported_percent": printed,
            }
    finally:
        book.close()
    if set(records) != set(expected):
        raise ValueError("Idaho complete reporting-unit inventory changed")
    return records


def _prior_success(prior, templates):
    if prior is None:
        return None
    data = prior.get("data") if isinstance(prior, dict) else None
    source = prior.get("source") if isinstance(prior, dict) else None
    if data is None and source is None:
        return None
    data_fields = {
        "updates", "complete_native_query", "numerical_input_pins",
        "source_url", "geographic_joins_changed",
        "analytical_rates_promoted", "new_count_identities_added",
        "candidate_votes_used_as_ballots",
        "registration_stock_used_as_ballot_denominator",
    }
    if (
        not isinstance(data, dict)
        or set(data) != data_fields
        or not isinstance(source, dict)
        or set(source) != {"url", "bytes", "sha256"}
        or source.get("url") != DATA_URL
        or not isinstance(source.get("bytes"), int)
        or source["bytes"] < 1
        or re.fullmatch(r"[a-f0-9]{64}", source.get("sha256", "")) is None
        or data.get("source_url") != DATA_URL
        or data.get("geographic_joins_changed") is not False
        or data.get("analytical_rates_promoted") is not False
        or data.get("new_count_identities_added") is not False
        or data.get("candidate_votes_used_as_ballots") is not False
        or data.get("registration_stock_used_as_ballot_denominator") is not False
    ):
        raise ValueError("Prior Idaho captured source declaration is incomplete")
    queries = data.get("complete_native_query")
    updates = data.get("updates")
    numerical_pins = data.get("numerical_input_pins")
    if (
        not isinstance(queries, list)
        or len(queries) != 1
        or not isinstance(updates, list)
        or len(updates) != 1030
        or not isinstance(numerical_pins, dict)
        or set(numerical_pins) != {"data_api", "ballots_workbook"}
    ):
        raise ValueError("Prior Idaho full query/update vector is incomplete")
    query = queries[0]
    query_fields = {
        "contract", "source_pin", "source_url", "declaring_page_url",
        "declared_workbook_url", "numerical_input_pins", "election",
        "county_records", "reporting_unit_records", "reconciliation",
    }
    source_pin = {"bytes": source["bytes"], "sha256": source["sha256"]}
    data_pin = numerical_pins["data_api"]
    workbook_pin = numerical_pins["ballots_workbook"]
    if (
        not isinstance(query, dict)
        or set(query) != query_fields
        or query.get("contract") != "participation.idaho_native_query.v1"
        or query.get("source_url") != DATA_URL
        or query.get("source_pin") != source_pin
        or query.get("numerical_input_pins") != numerical_pins
        or data_pin != {"url": DATA_URL, **source_pin}
        or not isinstance(workbook_pin, dict)
        or set(workbook_pin) != {"url", "bytes", "sha256"}
        or not _workbook_url(workbook_pin["url"])
        or not isinstance(workbook_pin["bytes"], int)
        or workbook_pin["bytes"] < 1
        or re.fullmatch(r"[a-f0-9]{64}", workbook_pin.get("sha256", "")) is None
        or query.get("declared_workbook_url") != workbook_pin["url"]
        or query.get("declaring_page_url") != ENTRY_URL
    ):
        raise ValueError("Prior Idaho source pins or declared workbook changed")
    election = query.get("election")
    election_fields = {
        "id", "jurisdiction_id", "date", "type", "is_primary", "name",
        "state_as_of", "state_last_updated", "state_is_official_results",
        "state_registration_stock", "state_ballots_field_not_used",
    }
    if (
        not isinstance(election, dict)
        or set(election) != election_fields
        or election.get("id") != ELECTION_ID
        or election.get("jurisdiction_id") != JURISDICTION
        or election.get("date") != "2026-11-03"
        or election.get("type") != "general"
        or election.get("is_primary") is not False
        or election.get("name") != "General Election - November 3, 2026"
        or type(election.get("state_is_official_results")) is not bool
    ):
        raise ValueError("Prior Idaho election declaration changed")
    _clock(election.get("state_as_of"), "prior state as-of clock")
    _clock(election.get("state_last_updated"), "prior state last-updated clock")
    expected_counties = {
        _native_identity(row)["county"]: row
        for row in templates if _template_kind(row) == "county"
    }
    expected_units = {
        _native_identity(row)["unit_key"]: row
        for row in templates if _template_kind(row) == "reporting_unit"
    }
    counties = {}
    county_fields = {
        "native_kind", "county", "jurisdiction_id", "locality_election_id",
        "ballots_cast", "registered_voters", "source_as_of",
        "source_last_updated", "source_clock_timezone_literal",
        "native_report_status_literal", "is_official_results",
        "precinct_reporting_status",
    }
    for row in query.get("county_records", []):
        if (
            not isinstance(row, dict)
            or set(row) != county_fields
            or row.get("native_kind") != "county"
            or row.get("county") in counties
            or row.get("county") not in expected_counties
            or row.get("source_clock_timezone_literal") != "UTC"
            or type(row.get("is_official_results")) is not bool
            or row.get("native_report_status_literal")
                != "isOfficialResults=" + str(
                    row.get("is_official_results")).lower()
        ):
            raise ValueError("Prior Idaho county query vector changed")
        _integer(row.get("ballots_cast"), "prior county ballots")
        _integer(row.get("registered_voters"), "prior county registration")
        _clock(row.get("source_as_of"), "prior county as-of clock")
        _clock(row.get("source_last_updated"), "prior county last-updated clock")
        identity = _native_identity(expected_counties[row["county"]])
        if (
            row["jurisdiction_id"] != identity["jurisdiction_id"]
            or row["locality_election_id"] != identity["locality_election_id"]
        ):
            raise ValueError("Prior Idaho county identity changed")
        counties[row["county"]] = row
    if set(counties) != set(expected_counties):
        raise ValueError("Prior Idaho county query inventory changed")
    if _integer(
        election.get("state_registration_stock"),
        "prior state registration stock",
    ) != sum(row["registered_voters"] for row in counties.values()):
        raise ValueError(
            "Prior Idaho county registration does not reconcile statewide")
    units = {}
    unit_fields = {
        "native_kind", "unit_key", "county", "precinct",
        "reporting_unit_kind", "registered_at_cutoff",
        "election_day_registrants", "registered_voters", "ballots_cast",
        "source_reported_percent", "parent_api_context",
        "source_clock_scope", "workbook_source_clock",
        "workbook_source_timezone", "native_report_status_literal",
    }
    parent_fields = {
        "county", "jurisdiction_id", "locality_election_id",
        "source_as_of", "source_last_updated",
        "source_clock_timezone_literal", "is_official_results",
        "native_report_status_literal", "precinct_reporting_status",
    }
    for row in query.get("reporting_unit_records", []):
        if (
            not isinstance(row, dict)
            or set(row) != unit_fields
            or row.get("native_kind") != "reporting_unit"
            or row.get("unit_key") in units
            or row.get("unit_key") not in expected_units
            or row.get("source_clock_scope")
                != "parent_api_context_not_workbook_clock"
            or row.get("workbook_source_clock") is not None
            or row.get("workbook_source_timezone") is not None
            or not isinstance(row.get("parent_api_context"), dict)
            or set(row["parent_api_context"]) != parent_fields
        ):
            raise ValueError("Prior Idaho reporting-unit query vector changed")
        identity = _native_identity(expected_units[row["unit_key"]])
        if (
            row["county"] != identity["county"]
            or row["precinct"] != identity["precinct"]
            or row["reporting_unit_kind"] != identity["reporting_unit_kind"]
        ):
            raise ValueError("Prior Idaho reporting-unit identity changed")
        for field in (
            "registered_at_cutoff", "election_day_registrants",
            "registered_voters", "ballots_cast",
        ):
            _integer(row.get(field), "prior reporting-unit " + field)
        if (
            not isinstance(row.get("source_reported_percent"), str)
            or PERCENT.fullmatch(row["source_reported_percent"]) is None
        ):
            raise ValueError("Prior Idaho printed participation fraction changed")
        parent = row["parent_api_context"]
        county = counties.get(row["county"])
        expected_parent = {
            key: county[key] for key in parent_fields
        } if county is not None else None
        if (
            parent != expected_parent
            or row["native_report_status_literal"]
                != parent["native_report_status_literal"]
        ):
            raise ValueError("Prior Idaho unit parent API context changed")
        units[row["unit_key"]] = row
    if set(units) != set(expected_units):
        raise ValueError("Prior Idaho reporting-unit query inventory changed")
    expected_updates = {
        row["id"]: row for row in templates
    }
    seen_updates = {}
    update_fields = {
        "id", "value", "native", "registered", "clock",
        "reported_units", "total_units", "rate_compatible", "source_input",
    }
    for update in updates:
        if (
            not isinstance(update, dict)
            or set(update) != update_fields
            or update.get("id") in seen_updates
            or update.get("id") not in expected_updates
        ):
            raise ValueError("Prior Idaho update inventory changed")
        template = expected_updates[update["id"]]
        kind = _template_kind(template)
        native = update.get("native")
        identity = _native_identity(template)
        row = (
            counties[identity["county"]]
            if kind == "county" else units[identity["unit_key"]]
        )
        input_name = "data_api" if kind == "county" else "ballots_workbook"
        input_pin = data_pin if kind == "county" else workbook_pin
        expected_clock = row["source_as_of"] if kind == "county" else None
        common_native_fields = {
            "contract", "native_kind", "source_input",
            "source_original_pin", "native_report_status_literal",
            "native_reporting_complete_qualified", "maps_approved",
            "candidate_votes_not_used_as_ballots",
            "registration_stock_not_ballot_denominator_substitute",
            "county_to_unit_allocation", "analytical_rates_promoted",
            "query",
        }
        expected_native_fields = common_native_fields | (
            {
                "county", "jurisdiction_id", "locality_election_id",
                "source_as_of", "source_last_updated",
                "is_official_results", "source_clock_timezone_literal",
            }
            if kind == "county" else
            {
                "unit_key", "county", "precinct",
                "reporting_unit_kind", "source_clock_scope",
                "parent_api_context", "workbook_source_clock",
                "workbook_source_timezone",
                "retained_house_contest_ballots_context",
                "retained_quality_flags",
            }
        )
        if (
            not isinstance(native, dict)
            or set(native) != expected_native_fields
            or native.get("contract")
                != "participation.idaho_native_refresh.v1"
            or native.get("query") != row
            or native.get("source_input") != input_name
            or native.get("source_original_pin") != input_pin
            or native.get("native_kind") != kind
            or native.get("native_report_status_literal")
                != row["native_report_status_literal"]
            or native.get("native_reporting_complete_qualified") is not False
            or native.get("maps_approved")
                != template["view"]["maps_approved"]
            or native.get("candidate_votes_not_used_as_ballots") is not True
            or native.get(
                "registration_stock_not_ballot_denominator_substitute"
            ) is not True
            or native.get("county_to_unit_allocation") is not False
            or native.get("analytical_rates_promoted") is not False
            or update["value"] != row["ballots_cast"]
            or update["registered"] != row["registered_voters"]
            or update["clock"] != expected_clock
            or update["reported_units"] is not None
            or update["total_units"]
                != (template["reporting_status"].get("total_units")
                    if kind == "county" else None)
            or update["rate_compatible"] is not (
                row["registered_voters"] > 0
                and row["ballots_cast"] <= row["registered_voters"]
            )
            or update["source_input"] != input_name
        ):
            raise ValueError("Prior Idaho pin/query/update consistency changed")
        if kind == "county":
            if (
                native.get("source_as_of") != row["source_as_of"]
                or native.get("source_last_updated")
                    != row["source_last_updated"]
                or native.get("source_clock_timezone_literal") != "UTC"
                or native.get("is_official_results")
                    != row["is_official_results"]
            ):
                raise ValueError("Prior Idaho county native clock/status changed")
        elif (
            native.get("parent_api_context") != row["parent_api_context"]
            or native.get("source_clock_scope")
                != "parent_api_context_not_workbook_clock"
            or native.get("workbook_source_clock") is not None
            or native.get("workbook_source_timezone") is not None
            or "source_clock_timezone_literal" in native
        ):
            raise ValueError("Prior Idaho unit native clock context changed")
        seen_updates[update["id"]] = update
    if set(seen_updates) != set(expected_updates):
        raise ValueError("Prior Idaho complete update inventory changed")
    grouped = {}
    for row in units.values():
        grouped.setdefault(row["county"], []).append(row)
    differences = []
    for county, rows in grouped.items():
        parent = counties[county]
        if sum(row["ballots_cast"] for row in rows) != parent["ballots_cast"]:
            raise ValueError("Prior Idaho county/unit ballot reconciliation changed")
        registered = sum(row["registered_voters"] for row in rows)
        if registered != parent["registered_voters"]:
            differences.append({
                "county": county,
                "workbook_registered_voters": registered,
                "api_registered_voters": parent["registered_voters"],
            })
    reconciliation = query.get("reconciliation")
    expected_reconciliation = {
        "county_records": len(counties),
        "reporting_unit_records": len(units),
        "county_ballots": sum(row["ballots_cast"] for row in counties.values()),
        "reporting_unit_ballots": sum(row["ballots_cast"] for row in units.values()),
        "county_and_reporting_unit_ballots_reconcile": True,
        "registration_differences": differences,
        "candidate_votes_used_as_ballots": False,
        "state_registration_stock_used_as_ballot_denominator": False,
        "county_to_reporting_unit_allocations": 0,
        "new_count_identities": 0,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }
    if reconciliation != expected_reconciliation:
        raise ValueError("Prior Idaho complete reconciliation changed")
    return {"counties": counties, "election": election}


def statistics(body, templates, url, *, acquire, prior=None):
    if url != DATA_URL:
        raise ValueError("Unreviewed Idaho election product")
    validate_templates(templates)
    try:
        document = json.loads(body, object_pairs_hook=_object)
    except Exception as error:
        if isinstance(error, ValueError) and str(error).startswith(
                "Duplicate Idaho native JSON property"):
            raise
        raise ValueError("Unreadable Idaho election data") from error
    if not isinstance(document, dict):
        raise ValueError("Changed Idaho election data envelope")
    workbook_url = _declared_workbook(document)
    workbook, _ = acquire(workbook_url)
    prior_success = _prior_success(prior, templates)
    counties = _county_records(document, templates)
    if prior_success is not None:
        if (
            _clock(document["election"]["asOf"], "state as-of clock")
                < _clock(
                    prior_success["election"]["state_as_of"],
                    "prior state as-of clock")
            or _clock(
                document["election"]["lastUpdated"],
                "state last-updated clock")
                < _clock(
                    prior_success["election"]["state_last_updated"],
                    "prior state last-updated clock")
            or prior_success["election"]["state_is_official_results"] is True
                and document["election"]["isOfficialResults"] is not True
        ):
            raise ValueError("Idaho state source clock regressed from prior capture")
        for county, record in counties.items():
            previous = prior_success["counties"][county]
            if (
                _clock(record["as_of"], "county as-of clock")
                    < _clock(previous["source_as_of"], "prior county as-of clock")
                or _clock(record["last_updated"], "county last-updated clock")
                    < _clock(
                        previous["source_last_updated"],
                        "prior county last-updated clock")
                or previous["is_official_results"] is True
                    and record["is_official_results"] is not True
            ):
                raise ValueError(
                    "Idaho county clock or official status regressed from prior capture")
    units = _workbook_records(workbook, templates)
    workbook_pin = {"url": workbook_url, **pin(workbook)}
    data_pin = {"url": DATA_URL, **pin(body)}
    county_groups = {}
    for record in units.values():
        county_groups.setdefault(record["county"], []).append(record)
    if set(county_groups) != set(counties):
        raise ValueError("Idaho workbook and county API scopes differ")
    registration_differences = []
    for county, records in county_groups.items():
        api = counties[county]
        ballots = sum(row["ballots_cast"] for row in records)
        registered = sum(row["registered_voters"] for row in records)
        if ballots != api["ballots_cast"]:
            raise ValueError("Idaho reporting units do not reconcile to county ballots")
        if registered != api["registered_voters"]:
            registration_differences.append({
                "county": county,
                "workbook_registered_voters": registered,
                "api_registered_voters": api["registered_voters"],
            })
    updates = []
    query_units = []
    query_counties = []
    for template in templates:
        kind = _template_kind(template)
        prior = template["view"]["native_record"]
        if kind == "county":
            county = _native_identity(template)["county"]
            record = counties[county]
            query = {
                "native_kind": kind,
                "county": county,
                "jurisdiction_id": record["jurisdiction_id"],
                "locality_election_id": record["locality_election_id"],
                "ballots_cast": record["ballots_cast"],
                "registered_voters": record["registered_voters"],
                "source_as_of": record["as_of"],
                "source_last_updated": record["last_updated"],
                "source_clock_timezone_literal": "UTC",
                "native_report_status_literal": (
                    "isOfficialResults="
                    + str(record["is_official_results"]).lower()
                ),
                "is_official_results": record["is_official_results"],
                "precinct_reporting_status": record["precinct_reporting_status"],
            }
            native = {
                "contract": "participation.idaho_native_refresh.v1",
                **{key: query[key] for key in (
                    "native_kind", "county", "jurisdiction_id",
                    "locality_election_id", "source_as_of",
                    "source_last_updated", "is_official_results",
                )},
                "source_input": "data_api",
                "source_original_pin": data_pin,
                "source_clock_timezone_literal": "UTC",
                "native_report_status_literal": query[
                    "native_report_status_literal"
                ],
                "native_reporting_complete_qualified": False,
                "maps_approved": template["view"]["maps_approved"],
                "candidate_votes_not_used_as_ballots": True,
                "registration_stock_not_ballot_denominator_substitute": True,
                "county_to_unit_allocation": False,
                "analytical_rates_promoted": False,
                "query": copy.deepcopy(query),
            }
            query_counties.append(copy.deepcopy(query))
            updates.append({
                "id": template["id"],
                "value": record["ballots_cast"],
                "native": native,
                "registered": record["registered_voters"],
                "clock": record["as_of"],
                "reported_units": None,
                "total_units": template["reporting_status"].get("total_units"),
                "rate_compatible": (
                    record["registered_voters"] > 0
                    and record["ballots_cast"] <= record["registered_voters"]
                ),
                "source_input": "data_api",
            })
            continue
        identity = _native_identity(template)
        record = units[(identity["county"], identity["precinct"])]
        county = counties[identity["county"]]
        parent_api_context = {
            "county": identity["county"],
            "jurisdiction_id": county["jurisdiction_id"],
            "locality_election_id": county["locality_election_id"],
            "source_as_of": county["as_of"],
            "source_last_updated": county["last_updated"],
            "source_clock_timezone_literal": "UTC",
            "is_official_results": county["is_official_results"],
            "native_report_status_literal": (
                "isOfficialResults="
                + str(county["is_official_results"]).lower()
            ),
            "precinct_reporting_status": copy.deepcopy(
                county["precinct_reporting_status"]),
        }
        query = {
            "native_kind": kind,
            "unit_key": identity["unit_key"],
            "county": identity["county"],
            "precinct": identity["precinct"],
            "reporting_unit_kind": identity["reporting_unit_kind"],
            **record,
            "parent_api_context": parent_api_context,
            "source_clock_scope": "parent_api_context_not_workbook_clock",
            "workbook_source_clock": None,
            "workbook_source_timezone": None,
            "native_report_status_literal":
                parent_api_context["native_report_status_literal"],
        }
        native = {
            "contract": "participation.idaho_native_refresh.v1",
            **{key: query[key] for key in (
                "native_kind", "unit_key", "county", "precinct",
                "reporting_unit_kind", "source_clock_scope",
            )},
            "parent_api_context": copy.deepcopy(parent_api_context),
            "workbook_source_clock": None,
            "workbook_source_timezone": None,
            "source_input": "ballots_workbook",
            "source_original_pin": workbook_pin,
            "native_report_status_literal": query[
                "native_report_status_literal"
            ],
            "native_reporting_complete_qualified": False,
            "maps_approved": template["view"]["maps_approved"],
            "candidate_votes_not_used_as_ballots": True,
            "retained_house_contest_ballots_context": prior.get(
                "retained_house_contest_ballots_context",
                prior.get("house_contest_ballots"),
            ),
            "retained_quality_flags": copy.deepcopy(
                prior.get("retained_quality_flags", prior.get("quality_flags", []))
            ),
            "registration_stock_not_ballot_denominator_substitute": True,
            "county_to_unit_allocation": False,
            "analytical_rates_promoted": False,
            "query": copy.deepcopy(query),
        }
        query_units.append(copy.deepcopy(query))
        updates.append({
            "id": template["id"],
            "value": record["ballots_cast"],
            "native": native,
            "registered": record["registered_voters"],
            "clock": None,
            "reported_units": None,
            "total_units": None,
            "rate_compatible": (
                record["registered_voters"] > 0
                and record["ballots_cast"] <= record["registered_voters"]
            ),
            "source_input": "ballots_workbook",
        })
    query = {
        "contract": "participation.idaho_native_query.v1",
        "source_pin": pin(body),
        "source_url": DATA_URL,
        "declaring_page_url": ENTRY_URL,
        "declared_workbook_url": workbook_url,
        "numerical_input_pins": {
            "data_api": data_pin,
            "ballots_workbook": workbook_pin,
        },
        "election": {
            "id": ELECTION_ID,
            "jurisdiction_id": JURISDICTION,
            "date": "2026-11-03",
            "type": "general",
            "is_primary": False,
            "name": "General Election - November 3, 2026",
            "state_as_of": document["election"]["asOf"],
            "state_last_updated": document["election"]["lastUpdated"],
            "state_is_official_results":
                document["election"]["isOfficialResults"],
            "state_registration_stock": _integer(
                document["election"]["totalVoters"], "state registration stock"
            ),
            "state_ballots_field_not_used": document["election"].get("ballotsCast"),
        },
        "county_records": query_counties,
        "reporting_unit_records": query_units,
        "reconciliation": {
            "county_records": len(query_counties),
            "reporting_unit_records": len(query_units),
            "county_ballots": sum(row["ballots_cast"] for row in query_counties),
            "reporting_unit_ballots": sum(
                row["ballots_cast"] for row in query_units
            ),
            "county_and_reporting_unit_ballots_reconcile": True,
            "registration_differences": registration_differences,
            "candidate_votes_used_as_ballots": False,
            "state_registration_stock_used_as_ballot_denominator": False,
            "county_to_reporting_unit_allocations": 0,
            "new_count_identities": 0,
            "geographic_joins_changed": False,
            "analytical_rates_promoted": False,
        },
    }
    public_facts(query)
    return {
        "updates": updates,
        "complete_native_query": [query],
        "numerical_input_pins": query["numerical_input_pins"],
        "source_url": DATA_URL,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "new_count_identities_added": False,
        "candidate_votes_used_as_ballots": False,
        "registration_stock_used_as_ballot_denominator": False,
    }
