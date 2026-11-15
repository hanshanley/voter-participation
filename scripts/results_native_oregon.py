"""Refresh reviewed Oregon county ballot counts without new rate or map approvals."""

import copy
from datetime import datetime
import html
import json
import re

from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_oregon_county_turnout"
PAGE_URL = "https://results.oregonvotes.gov/VoterTurnoutDetails.aspx"
API_URL = "https://orresultswebservices.azureedge.us/ResultsAjax.svc/GetVoterTurnoutData"
SOURCE_SHA = "8d2e22266c23be606b126a157eae4402a33d04aaffb42904fe8869358bcb2fb2"
SOURCE_ID = "accepted-export:" + SOURCE_SHA + ":counties"
STORED_URL = "https://www.themarginoferror.com/participation-local/OR.json.gz"
STORED_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "95f54b7304b5d895c90cfb4f8389b2aaa307d202/data/county-source-reviews/"
    "20261106-oregon-participation-01/county-participation.csv"
)
INITIAL_FULL_PIN = "a658b4db8018ad5cbbf76d45f78a80e704d334aa6936950c39d6c0511a9906db"
IDENTITY_PIN = "677bd55d954257509990259106ae5a55a9eb74bf7c457f2d8a110e095d8ed1f1"
FIELDS = {
    "BallotsAccepted", "BallotsUnderReview", "CountyID", "CountyName", "CountyPercent",
    "CurrentDateTime", "IsReported", "NextBallotCount", "PartialPrecincts", "PrecinctName",
    "PrecinctsReporting", "TotalPrecincts", "Voters", "__type", "calcVoterTurnout",
}


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Missing or invalid Oregon native count is not zero")
    return value


def _clock(value):
    if not isinstance(value, str):
        raise ValueError("Missing Oregon native county clock")
    try:
        result = datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p")
    except ValueError as error:
        raise ValueError("Changed Oregon native county clock format") from error
    if not datetime(2026, 11, 3) <= result < datetime(2027, 2, 1):
        raise ValueError("Oregon county clock is outside the declared election")
    return result


def _identity(template):
    view = template["view"]
    return {
        "id": template["id"], "election": template["election"],
        "geography": template["geography"], "measure": template["measure"],
        "source_id": template["source"]["id"], "county_id": view["county_id"],
        "county": view["county"], "native_county_id": view["native_record"]["native_county_id"],
        "denominator_basis": template["denominator"]["basis"],
        "maps_approved": view["maps_approved"],
    }


def _inventory(templates, identity=False):
    return digest(encoded(sorted(
        [_identity(row) if identity else row for row in templates], key=lambda row: row["id"])))


def route(template):
    if template.get("source", {}).get("id") != SOURCE_ID:
        return None
    view, source = template.get("view", {}), template["source"]
    if (
        template["geography"]["state_code"] != "OR"
        or template["geography"]["level"] != "county"
        or template["election"]["year"] != 2026
        or template["election"]["type"] != "general"
        or (source.get("url"), view.get("source_url"))
        not in ((STORED_URL, STORED_VIEW_URL), (API_URL, API_URL))
    ):
        raise ValueError("Reviewed Oregon county source lineage changed")
    return {"state": "OR", "adapter": ADAPTER, "url": API_URL}


def validate_templates(templates):
    if len(templates) != 36 or len({row["id"] for row in templates}) != 36:
        raise ValueError("Complete reviewed Oregon county inventory is required")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("Reviewed Oregon county identities or qualifications changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_URL]
    if initial:
        if len(initial) != 36 or _inventory(initial) != INITIAL_FULL_PIN:
            raise ValueError("Initial complete reviewed Oregon source frame changed")
    for template in templates:
        assert route(template) is not None
        view, source = template["view"], template["source"]
        if (template["denominator"]["qualified"] is not False
                or view.get("reported_pct") is not None or view.get("maps_approved") is not False
                or source["fields"] != view):
            raise ValueError("Oregon rate/map holds or native view coherence changed")
        if source["url"] == STORED_URL:
            if source["input_sha256"] != SOURCE_SHA:
                raise ValueError("Initial Oregon export pin changed")
            continue
        native = view["native_record"]
        record = native.get("record") or {}
        if (
            (native.get("private_original_pin") or {}).get("sha256") != source["input_sha256"]
            or source.get("selector", {}).get("native_refresh") != native
            or record.get("CountyID") != native["native_county_id"]
            or record.get("CountyName") != view["county"]
            or record.get("calcVoterTurnout") != template["count"]["value"]
            or view.get("ballots") != template["count"]["value"]
            or record.get("Voters") != template["denominator"]["value"]
            or native.get("source_updated_at") != record.get("CurrentDateTime")
            or template["source_clock"]["literal"] != record.get("CurrentDateTime")
            or template["source_clock"]["timezone"] is not None
        ):
            raise ValueError("Projected Oregon native vector, count, clock or pin differs")


def validate_plan(plan):
    selected = [source for source in plan.get("OR", {}).values() if source["adapter"] == ADAPTER]
    if not selected:
        return plan
    if len(selected) != 1:
        raise ValueError("Exactly one complete reviewed Oregon county source is required")
    validate_templates(selected[0]["templates"])
    return plan


def _label(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def _header(body):
    text = body.decode("windows-1252")
    title, = re.findall(r"<title>(.*?)</title>", text, re.S)
    if _label(title) != "Oregon Secretary of State":
        raise ValueError("Changed Oregon native publisher")
    date, = re.findall(r'id="hidElectionDate" value="([^"]+)"', text)
    kind, = re.findall(r'id="hidElectionType" value="([^"]+)"', text)
    block, = re.findall(r'<div class="col header-box1">(.*?)</div>', text, re.S)
    status, = re.findall(r"<h3>(.*?)</h3>", block, re.S)
    election, = re.findall(r"<h2>(.*?)</h2>", block, re.S)
    status = _label(status)
    if (date != "11/3/2026" or kind != "General"
            or _label(election) != "General Election November 3, 2026"
            or status not in ("Unofficial", "Official")):
        raise ValueError("Changed Oregon election or declared source status")
    facts = re.findall(
        r'<span class="vt-text">([^<]+)</span><span class="vt-number">([^<]+)</span>', text)
    if len(facts) != 2 or [item[0] for item in facts] != [
            "Ballots Counted", "Active Registered Voters"]:
        raise ValueError("Changed Oregon native header count roles")
    values = []
    for _, value in facts:
        if not re.fullmatch(r"[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+", value):
            raise ValueError("Missing Oregon header count is not zero")
        values.append(int(value.replace(",", "")))
    counties = re.findall(
        r'<a id="MainContent_rptVoterTurnoutSW_lnkCountyName_[0-9]+" '
        r'href="ResultsSW\.aspx\?type=CTYALL&amp;cty=([0-9]+)">([^<]+)</a>', text)
    if len(counties) != 36 or len(dict(counties)) != 36:
        raise ValueError("Changed Oregon rendered county inventory")
    fractions = re.findall(
        r'<a id="MainContent_rptVoterTurnoutSW_lnkCountyName_[0-9]+" '
        r'href="ResultsSW\.aspx\?type=CTYALL&amp;cty=([0-9]+)">[^<]+</a>.*?'
        r'<canvas id="Turnout\1"></canvas>.*?<span class="int">([0-9]+)</span>'
        r'<span class="dec">(\.[0-9]{2}%)</span>', text, re.S)
    if len(fractions) != 36 or {item[0] for item in fractions} != set(dict(counties)):
        raise ValueError("Changed Oregon native county fraction display")
    clock, = re.findall(r'<div class="next-count">Results last updated: ([^<]+)</div>', text)
    parsed = datetime.strptime(clock, "%m/%d/%Y | %I:%M %p PT")
    if not datetime(2026, 11, 3) <= parsed < datetime(2027, 2, 1):
        raise ValueError("Oregon statewide clock is outside the declared election")
    return {
        "election_type": kind, "election_date": date, "status": status,
        "ballots_counted": values[0], "active_registered_voters": values[1],
        "source_update_label": clock, "statewide_clock_zone_literal": "PT",
        "county_clocks_have_no_declared_timezone": True,
        "counties": {key: html.unescape(name) for key, name in counties},
        "county_printed_fractions": {key: whole + part for key, whole, part in fractions},
        "source_pin": pin(body),
    }


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Oregon native JSON property")
        result[key] = value
    return result


def statistics(body, templates, url, *, acquire):
    if url != API_URL:
        raise ValueError("Unreviewed Oregon turnout product")
    validate_templates(templates)
    page, _ = acquire(PAGE_URL)
    header = _header(page)
    document = json.loads(body, object_pairs_hook=_object)
    if set(document) != {"d"} or not isinstance(document["d"], list) or len(document["d"]) != 36:
        raise ValueError("Changed Oregon native API envelope or complete county scope")
    records = {}
    for record in document["d"]:
        if (not isinstance(record, dict) or set(record) != FIELDS
                or record["__type"] != "TurnoutData:#ORResultsWebService"
                or record["PrecinctName"] != "Countywide"
                or not isinstance(record["CountyID"], str)
                or record["CountyID"] in records
                or type(record["IsReported"]) is not bool):
            raise ValueError("Changed Oregon native county record or identity")
        _integer(record["calcVoterTurnout"])
        _integer(record["Voters"])
        _clock(record["CurrentDateTime"])
        records[record["CountyID"]] = record
    if {key: row["CountyName"] for key, row in records.items()} != header["counties"]:
        raise ValueError("Oregon API and official page county identities differ")
    if (sum(row["calcVoterTurnout"] for row in records.values()) != header["ballots_counted"]
            or sum(row["Voters"] for row in records.values()) != header["active_registered_voters"]):
        raise ValueError("Oregon county and statewide count frames do not reconcile")
    updates = []
    for template in templates:
        prior = template["view"]["native_record"]
        identity = prior["native_county_id"]
        record = records.get(identity)
        if record is None or record["CountyName"] != template["view"]["county"]:
            raise ValueError("Reviewed Oregon native county identity differs")
        if _clock(record["CurrentDateTime"]) < _clock(prior["source_updated_at"]):
            raise ValueError("Oregon native county count clock regressed")
        native = copy.deepcopy(prior)
        native.setdefault("retained_accepted_export_context", {
            "qualification": prior.get("qualification"),
            "native_reported_percent": prior.get("native_reported_percent"),
        })
        fraction = header["county_printed_fractions"][identity]
        if record["Voters"] and abs(
                float(fraction[:-1]) - 100 * record["calcVoterTurnout"] / record["Voters"]) > 0.011:
            raise ValueError("Oregon native displayed fraction and source counts differ")
        native.update(
            record=copy.deepcopy(record), native_record_json=encoded(record).decode(),
            ballots_counted=str(record["calcVoterTurnout"]),
            active_registered_voters=str(record["Voters"]),
            source_updated_at=record["CurrentDateTime"], source_status_literal=header["status"],
            native_reported_percent=fraction, native_fraction_literal=fraction,
            private_original_pin=pin(body), native_reporting_complete_qualified=False,
            native_report_status_literal=header["status"],
            query={"record": copy.deepcopy(record), "native_report_status_literal": header["status"],
                   "native_fraction_literal": fraction},
            separate_statewide_header=copy.deepcopy(header),
            official_page_url=PAGE_URL, analytical_rates_promoted=False,
            qualification=(
                "Native ballots counted and active registrations; displayed fraction is source context, "
                "not a newly qualified analytical rate. County timestamps have no supplied timezone. "
                "Native IsReported and ancillary counters are retained, not certification or completion. "
                "No new geographic joins, residential allocation or demographic turnout."
            ),
        )
        updates.append({
            "id": template["id"], "value": record["calcVoterTurnout"], "native": native,
            "registered": record["Voters"], "clock": record["CurrentDateTime"],
            "reported_units": None, "total_units": None, "rate_compatible": False,
        })
    return {
        "updates": updates,
        "complete_native_query": [{
            "source_pin": pin(body), "county_records": document["d"],
            "independent_official_header": header,
            "county_and_statewide_count_and_registration_totals_reconcile": True,
            "is_reported_and_ancillary_zeros_do_not_erase_positive_ballots": True,
        }],
        "source_url": API_URL, "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "reviewed_source_url_bridge": {
            "contract": "participation.reviewed_source_url_bridge.v1", "source_id": SOURCE_ID,
            "stored_source_url": STORED_URL, "stored_view_source_url": STORED_VIEW_URL,
            "reviewed_url": API_URL, "prior_full_inventory_pin": INITIAL_FULL_PIN,
            "observation_ids_pin": digest(encoded(sorted(row["id"] for row in templates))),
            "declared_entry_url": PAGE_URL,
        },
    }
