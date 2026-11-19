"""Refresh D.C.'s reviewed citywide participation count from its native 2026 report."""

import copy
import csv
from datetime import datetime, timezone
import io
import json
import re
from urllib.parse import urlsplit

from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_dc_native_participation"
ENTRY_URL = "https://electionresults.dcboe.org/election_results/2026-General-Election"
ELECTION_URL = (
    "https://electionresults.dcboe.org/electionResults/getElectionInfo/"
    "2026-General-Election"
)
FEED = "DC-registered-" + digest(ELECTION_URL.encode())[:16]
VOTERS_URL = (
    "https://electionresults.dcboe.org/cityWide/getVoterSummaryInfo/"
    "2026-General-Election"
)
SOURCE_SHA = "9dfbfe6ce11851be136dd9036c45b5a52c38bffbfb0231865b4c427c6bb84dd3"
SOURCE_ID = "accepted-export:" + SOURCE_SHA + ":counties"
STORED_URL = "https://www.themarginoferror.com/voter-participation/"
STORED_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "ae1673add884650dd2a0537863e6d29f01c958db/"
    "data/county-source-reviews/20261105-dc-reviewed-01/county-participation.csv"
)
INITIAL_FULL_PIN = "f1f55f00967d4b69c1fa27ca5748e5c84dacebe988431772a71892d29c1bdcc5"
IDENTITY_PIN = "9a594217a5d65a9f17fd4633366e269cdb6edaca63d6f38a02f878d531e4df88"
UNIT_IDENTITY_PIN = "3acd2c75664f000d94ce46e3e22c411cb7fc36aac7b448a108341933fe23a678"
EXPECTED_UNITS = 144
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
CSV_FIELDS = [
    "ElectionDate", "ElectionName", "ContestNumber", "ContestName",
    "PrecinctNumber", "WardNumber", "Candidate", "Party", "Votes",
]
PARTICIPATION_CONTESTS = {
    "-2": ("REGISTERED VOTERS - TOTAL", "registered_voters"),
    "-1": ("BALLOTS CAST - TOTAL", "ballots_cast"),
}
ALLOWED_STATUS = {"Election Night Unofficial Results", "Official Results"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate D.C. native JSON property")
        result[key] = value
    return result


def _document(body):
    value = json.loads(body, object_pairs_hook=_object)
    if not isinstance(value, dict):
        raise ValueError("Changed D.C. native JSON envelope")
    return value


def _integer(value):
    if isinstance(value, bool):
        raise ValueError("Missing or invalid D.C. native count is not zero")
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value):
        return int(value)
    raise ValueError("Missing or invalid D.C. native count is not zero")


def _clock(value):
    if not isinstance(value, str) or re.fullmatch(
            r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]{1,7})?Z", value) is None:
        raise ValueError("Changed D.C. literal UTC count clock")
    match = re.fullmatch(r"(.+?)(?:\.([0-9]{1,7}))?Z", value)
    fraction = (match.group(2) or "").ljust(6, "0")[:6]
    normalized = match.group(1) + ("." + fraction if fraction else "") + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("Malformed D.C. literal UTC count clock") from error
    if parsed.tzinfo != timezone.utc or parsed < datetime(2026, 11, 3, tzinfo=timezone.utc):
        raise ValueError("D.C. count clock is outside the declared election")
    return parsed


def _accepted_clock(value):
    prefix = "source_update_literal: "
    return value[len(prefix):] if isinstance(value, str) and value.startswith(prefix) else value


def _identity(template):
    return {
        "id": template["id"],
        "election": template["election"],
        "geography": template["geography"],
        "measure": template["measure"],
        "source_id": template["source"]["id"],
        "denominator_basis": template["denominator"]["basis"],
        "denominator_qualified": template["denominator"]["qualified"],
        "maps_approved": template["view"]["maps_approved"],
        "review_id": template["view"]["review_id"],
    }


def _inventory(templates, identity=False):
    values = [_identity(row) if identity else row for row in templates]
    return digest(encoded(sorted(values, key=lambda row: row["id"])))


def route(template):
    """Return the exact official 2026 declaration for the accepted D.C. count slot."""
    if (
        template.get("geography", {}).get("state_code") != "DC"
        or template.get("source", {}).get("id") != SOURCE_ID
    ):
        return None
    source, view = template["source"], template.get("view", {})
    if (
        template.get("election", {}).get("id") != "us-2026-general-previously-reviewed"
        or template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("type") != "general"
        or template.get("geography", {}).get("level") != "county_equivalent"
        or template.get("geography", {}).get("id") != "DC|11001|"
        or template.get("measure") != MEASURE
        or (source.get("url"), view.get("source_url"))
        not in ((STORED_URL, STORED_VIEW_URL), (ELECTION_URL, ELECTION_URL))
    ):
        raise ValueError("Reviewed D.C. citywide source lineage changed")
    return {"state": "DC", "adapter": ADAPTER, "url": ELECTION_URL}


def validate_templates(templates):
    if len(templates) != 1 or len({row["id"] for row in templates}) != 1:
        raise ValueError("The complete reviewed D.C. citywide inventory is required")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("Reviewed D.C. identity or qualification changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_URL]
    if initial and (len(initial) != 1 or _inventory(initial) != INITIAL_FULL_PIN):
        raise ValueError("Initial frozen reviewed D.C. template changed")
    template = templates[0]
    if route(template) is None:
        raise ValueError("Reviewed D.C. template is not routed")
    view, source = template["view"], template["source"]
    denominator = template["denominator"]
    if (
        denominator.get("basis") != "native_registered_voters"
        or denominator.get("qualified") is not True
        or view.get("maps_approved") is not False
        or source.get("fields") != view
    ):
        raise ValueError("D.C. denominator, map hold or native view coherence changed")
    if source["url"] == STORED_URL:
        if source.get("input_sha256") != SOURCE_SHA:
            raise ValueError("Initial D.C. export pin changed")
        return
    native = view.get("native_record") or {}
    query = native.get("query") or {}
    if (
        (native.get("private_original_pin") or {}).get("sha256")
            != source.get("input_sha256")
        or source.get("selector", {}).get("native_refresh") != native
        or query.get("citywide", {}).get("ballots_cast") != template["count"]["value"]
        or query.get("citywide", {}).get("registered_voters") != denominator["value"]
        or view.get("ballots") != template["count"]["value"]
        or view.get("denominator") != denominator["value"]
        or native.get("source_updated_at") != template["source_clock"]["literal"]
        or template["source_clock"]["timezone"] != "UTC"
        or native.get("native_report_status_literal")
            != template["reporting_status"]["literal"]
    ):
        raise ValueError("Projected D.C. count, denominator, clock, status or source vector differs")


def validate_plan(plan):
    selected = [source for source in plan.get("DC", {}).values()
                if source["adapter"] == ADAPTER]
    if not selected:
        return plan
    if len(selected) != 1:
        raise ValueError("Exactly one complete reviewed D.C. source is required")
    validate_templates(selected[0]["templates"])
    return plan


def citywide_view(record, *, retained=False):
    """Expose the same native observation at both coextensive display levels."""
    if route(record) is None:
        return None
    validate_templates([record])
    view = copy.deepcopy(record["view"])
    ballots = record["count"]["value"]
    registered = record["denominator"]["value"]
    if ballots is None or registered is None or registered <= 0 or ballots > registered:
        raise ValueError("Invalid reviewed D.C. citywide participation fraction")
    clock = _accepted_clock(record["source_clock"]["literal"])
    _clock(clock)
    archived = record["source"]["url"] == STORED_URL
    if archived:
        source_hash = "fd6e5c4d2349d7b536734a31ccdb1ef20eeedc9ed2110dddcb3263268b159887"
    else:
        source_hash = view["native_record"]["numerical_input_manifest"]["voter_summary"]["sha256"]
    for key in ("county", "county_id"):
        view.pop(key, None)
    view.update(state="District of Columbia", geography_level="statewide", mode="official",
                status="retained_after_failure" if archived or retained else "reported",
                source_update_label=clock, source_update_timezone="UTC",
                source_url=VOTERS_URL, source_sha256=source_hash, automatic_source_refresh=True,
                equivalent_county_observation_id=record["id"],
                validated_pct=100 * ballots / registered, reported_pct=100 * ballots / registered)
    view["quality"].append(
        "District-wide and county-equivalent views show the same citywide report; do not add them together.")
    return view


def _source_url(value, *, suffix=None):
    if not isinstance(value, str):
        raise ValueError("Missing D.C. native report URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "electionresults.dcboe.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or suffix is not None and not parsed.path.endswith(suffix)
    ):
        raise ValueError("Changed D.C. native report authority or path")
    return value


def _election(body):
    value = _document(body)
    if (
        value.get("ElectionName") != "General Election"
        or value.get("ElectionCode") != "G"
        or value.get("ElectionDate") != "2026-11-03T00:00:00"
        or value.get("ElectionNameDisplay") != "General Election 2026"
        or value.get("ElectionResultsTypeName") not in ALLOWED_STATUS
        or type(value.get("IsLive")) is not bool
        or type(value.get("ShowEarlyVotes")) is not bool
        or value.get("PrecintsJsonMap") != "OCTO_VotingPrecinct_2019.json"
        or _integer(value.get("TotalPrecincts")) != EXPECTED_UNITS
        or not 0 <= _integer(value.get("PrecinctsCounted")) <= EXPECTED_UNITS
    ):
        raise ValueError("Changed D.C. 2026 general-election declaration")
    _clock(value.get("LastUpdated"))
    _source_url(value.get("CsvLink"), suffix=".csv")
    return value


def _voters(body):
    value = _document(body)
    if (
        value.get("SummaryType") != "c"
        or value.get("WardNumber") is not None
        or value.get("PrecinctNumber") is not None
        or value.get("Party") is not None
    ):
        raise ValueError("Changed D.C. citywide voter-summary identity")
    for field in (
        "RegisteredVoters", "ElectionDayVoters", "EarlyVotes",
        "AbsenteeSpecialBallotVotes", "TotalBallotsCast",
    ):
        _integer(value.get(field))
    return value


def _participation(body):
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames != CSV_FIELDS:
        raise ValueError("Changed D.C. native CSV schema")
    units, participation_rows, seen = {}, [], set()
    source_rows = 0
    for row in reader:
        source_rows += 1
        if (
            set(row) != set(CSV_FIELDS)
            or any(value is None for value in row.values())
            or row["ElectionDate"] != "11/3/2026 12:00:00 AM"
            or row["ElectionName"] != "General Election"
        ):
            raise ValueError("Malformed or wrong-election D.C. CSV row")
        precinct = _integer(row["PrecinctNumber"])
        ward = _integer(row["WardNumber"])
        votes = _integer(row["Votes"])
        identity = (
            row["ContestNumber"], precinct, row["Candidate"], row["Party"])
        if identity in seen:
            raise ValueError("Duplicate D.C. native CSV observation")
        seen.add(identity)
        if row["ContestNumber"] not in PARTICIPATION_CONTESTS:
            continue
        expected, field = PARTICIPATION_CONTESTS[row["ContestNumber"]]
        if (
            row["ContestName"] != expected
            or row["Candidate"]
            or row["Party"] != "CITYWIDE"
            or not 1 <= precinct <= EXPECTED_UNITS
            or not 1 <= ward <= 8
        ):
            raise ValueError("Changed D.C. participation-row identity")
        unit = units.setdefault(precinct, {
            "precinct_number": precinct, "ward_number": ward})
        if unit["ward_number"] != ward or field in unit:
            raise ValueError("Duplicate or conflicting D.C. participation unit")
        unit[field] = votes
        participation_rows.append({
            "precinct_number": precinct, "ward_number": ward,
            "measure": field, "value": votes,
        })
    if (
        len(units) != EXPECTED_UNITS
        or set(units) != set(range(1, EXPECTED_UNITS + 1))
        or any(set(row) != {
            "precinct_number", "ward_number", "registered_voters", "ballots_cast"}
            for row in units.values())
    ):
        raise ValueError("Incomplete D.C. native participation vector")
    ordered = [units[key] for key in sorted(units)]
    identities = [
        {"precinct_number": row["precinct_number"], "ward_number": row["ward_number"]}
        for row in ordered
    ]
    if digest(encoded(identities)) != UNIT_IDENTITY_PIN:
        raise ValueError("D.C. native precinct/ward identity inventory changed")
    return source_rows, participation_rows, ordered


def statistics(body, templates, url, *, acquire):
    if url != ELECTION_URL:
        raise ValueError("Unreviewed D.C. native product")
    validate_templates(templates)
    election = _election(body)
    voters_body, voters_receipt = acquire(VOTERS_URL)
    voters = _voters(voters_body)
    report_url = election["CsvLink"]
    report_body, report_receipt = acquire(report_url)
    source_rows, participation_rows, units = _participation(report_body)
    registered = _integer(voters["RegisteredVoters"])
    ballots = _integer(voters["TotalBallotsCast"])
    if (
        sum(row["registered_voters"] for row in units) != registered
        or sum(row["ballots_cast"] for row in units) != ballots
        or ballots > registered
    ):
        raise ValueError("D.C. precinct and citywide participation totals differ")
    components = {
        "election_day_voters": _integer(voters["ElectionDayVoters"]),
        "early_votes": _integer(voters["EarlyVotes"]),
        "absentee_special_ballot_votes": _integer(
            voters["AbsenteeSpecialBallotVotes"]),
    }
    if sum(components.values()) != ballots:
        raise ValueError("D.C. citywide native mode accounting differs from ballots cast")
    template = templates[0]
    previous_clock = template["source_clock"].get("literal")
    if (previous_clock is not None
            and _clock(election["LastUpdated"]) < _clock(_accepted_clock(previous_clock))):
        raise ValueError("D.C. native count clock regressed")
    if (
        template["geography"]["name"] != "District of Columbia"
        or template["view"].get("county") != "District of Columbia"
        or template["view"].get("county_id") != "11001"
    ):
        raise ValueError("D.C. accepted citywide identity changed")
    root_pin = pin(body)
    numerical_manifest = {
        "election": {"url": ELECTION_URL, **root_pin},
        "voter_summary": {"url": VOTERS_URL, **pin(voters_body)},
        "participation_report": {"url": report_url, **pin(report_body)},
    }
    native = copy.deepcopy(template["view"]["native_record"])
    native.update(
        citywide=copy.deepcopy(voters),
        source_updated_at=election["LastUpdated"],
        native_report_status_literal=election["ElectionResultsTypeName"],
        native_reporting_complete_qualified=False,
        source_clock_timezone_literal="UTC",
        private_original_pin=root_pin,
        numerical_input_manifest=numerical_manifest,
        official_entry_url=ENTRY_URL,
        official_election_declaration_url=ELECTION_URL,
        official_voter_summary_url=VOTERS_URL,
        official_participation_report_url=report_url,
        early_ballot_total_established=False,
        candidate_votes_used_as_ballots=False,
        september_registration_or_mode_reports_substituted=False,
        query={
            "citywide": {
                "registered_voters": registered,
                "ballots_cast": ballots,
                **components,
            },
            "native_report_status_literal": election["ElectionResultsTypeName"],
            "source_clock_timezone_literal": "UTC",
        },
    )
    complete_query = {
        "source_pin": root_pin,
        "source_inputs": numerical_manifest,
        "election": copy.deepcopy(election),
        "citywide": copy.deepcopy(voters),
        "native_unit_rows": units,
        "source_participation_rows": participation_rows,
        "source_csv_rows": source_rows,
        "reconciliation": {
            "native_units": EXPECTED_UNITS,
            "registered_voters": registered,
            "ballots_cast": ballots,
            "precinct_registration_sum": registered,
            "precinct_ballot_sum": ballots,
            "mode_component_sum": sum(components.values()),
            "candidate_votes_used_as_ballots": False,
            "september_registration_stock_substituted": False,
            "early_or_mail_reports_added": False,
            "unknowns_imputed_as_zero": False,
            "official_app_2019_named_reference_recognized_not_certified_2026_boundary": True,
            "analytical_rate_is_existing_accepted_ratio_not_new_approval": True,
        },
    }
    return {
        "updates": [{
            "id": template["id"],
            "value": ballots,
            "native": native,
            "registered": registered,
            "clock": election["LastUpdated"],
            "reported_units": election["PrecinctsCounted"],
            "total_units": election["TotalPrecincts"],
            "rate_compatible": True,
        }],
        "complete_native_query": [complete_query],
        "source_url": ELECTION_URL,
        "numerical_input_pins": {
            "voter_summary": {"url": VOTERS_URL, **pin(voters_body)},
            "participation_report": {"url": report_url, **pin(report_body)},
        },
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "reviewed_source_url_bridge": {
            "contract": "participation.reviewed_source_url_bridge.v1",
            "source_id": SOURCE_ID,
            "stored_source_url": STORED_URL,
            "stored_view_source_url": STORED_VIEW_URL,
            "reviewed_url": ELECTION_URL,
            "prior_full_inventory_pin": INITIAL_FULL_PIN,
            "observation_ids_pin": digest(encoded([template["id"]])),
            "declared_entry_url": ENTRY_URL,
        },
        "acquisition_receipts": {
            "voter_summary": voters_receipt,
            "participation_report": report_receipt,
        },
    }
