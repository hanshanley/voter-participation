"""Refresh reviewed Virginia locality ballots and retain complete native unit queries."""

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re

from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_virginia_native_localities"
ENTRY_URL = (
    "https://enr.elections.virginia.gov/results/public/virginia/elections/"
    "2026-November-General"
)
API_ROOT = "https://enr.elections.virginia.gov/results/public/api/elections/"
ROOT_URL = API_ROOT + "virginia/2026-November-General/data"
SOURCE_SHA = "5b1c2ada5bfb8cbdeaf335f29ce731476a41da34d529c27b1d826b26aa2f0ab2"
SOURCE_ID = "accepted-export:" + SOURCE_SHA + ":counties"
STORED_URL = "https://www.themarginoferror.com/participation-local/VA.json.gz"
STORED_VIEW_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "e385639467f2bbe8c8e3368fb1534287cfa71134/"
    "data/precinct-source-reviews/20261105/VA-2026-native-locality-counts/"
    "counts-review.json"
)
INITIAL_FULL_PIN = "bd78838a1e2f792fbc108eda937423a3c670e57340298a9940b041ab58f3bb0c"
IDENTITY_PIN = "c38d616646ad9e5d726112ddf99a56d83ae8dbd66563f54e08e123f98001cfcc"
LOCALITY_DECLARATION_PIN = "b7036420f2bd1cde4e5cecd9225230b3ae65868c6448b61a27415e96491dd7ae"
LOCALITY_URLS_PIN = "ef06cacd867515cd1934e13369b8c70137a3e761048c9bf80d130fce6cd5bb35"
UNIT_IDENTITY_PIN = "4e8ead21c2f1a111d160023f1bb26aabfd4506e821d463e0d37c6fb906b278c8"
ELECTION_ID = "01000000-ebdd-00dc-0143-08df1fee4ade"
EXPECTED_LOCALITIES = 133
EXPECTED_UNITS = 2529
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Reported ballots (previously reviewed export label, not a new native qualification)",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
DOCUMENT_FIELDS = {
    "jurisdiction", "election", "localityElections", "ballotItems", "precincts",
    "pollingPlaces", "statistics", "voterRegistration", "voterTurnout",
    "ballotItemWithBreakdown",
}
LOCALITY_SLUGS = {
    "001": "accomack-county", "003": "albemarle-county", "005": "alleghany-county",
    "007": "amelia-county", "009": "amherst-county", "011": "appomattox-county",
    "013": "arlington-county", "015": "augusta-county", "017": "bath-county",
    "019": "bedford-county", "021": "bland-county", "023": "botetourt-county",
    "025": "brunswick-county", "027": "buchanan-county", "029": "buckingham-county",
    "031": "campbell-county", "033": "caroline-county", "035": "carroll-county",
    "036": "charles-city-county", "037": "charlotte-county",
    "041": "chesterfield-county", "043": "clarke-county", "045": "craig-county",
    "047": "culpeper-county", "049": "cumberland-county", "051": "dickenson-county",
    "053": "dinwiddie-county", "057": "essex-county", "059": "fairfax-county",
    "061": "fauquier-county", "063": "floyd-county", "065": "fluvanna-county",
    "067": "franklin-county", "069": "frederick-county", "071": "giles-county",
    "073": "gloucester-county", "075": "goochland-county", "077": "grayson-county",
    "079": "greene-county", "081": "greensville-county", "083": "halifax-county",
    "085": "hanover-county", "087": "henrico-county", "089": "henry-county",
    "091": "highland-county", "093": "isle-of-wight-county",
    "095": "james-city-county", "097": "king-queen-county",
    "099": "king-george-county", "101": "king-william-county",
    "103": "lancaster-county", "105": "lee-county", "107": "loudoun-county",
    "109": "louisa-county", "111": "lunenburg-county", "113": "madison-county",
    "115": "mathews-county", "117": "mecklenburg-county",
    "119": "middlesex-county", "121": "montgomery-county", "125": "nelson-county",
    "127": "new-kent-county", "131": "northampton-county",
    "133": "northumberland-county", "135": "nottoway-county", "137": "orange-county",
    "139": "page-county", "141": "patrick-county", "143": "pittsylvania-county",
    "145": "powhatan-county", "147": "prince-edward-county",
    "149": "prince-george-county", "153": "prince-william-county",
    "155": "pulaski-county", "157": "rappahannock-county",
    "159": "richmond-county", "161": "roanoke-county",
    "163": "rockbridge-county", "165": "rockingham-county", "167": "russell-county",
    "169": "scott-county", "171": "shenandoah-county", "173": "smyth-county",
    "175": "southampton-county", "177": "spotsylvania-county",
    "179": "stafford-county", "181": "surry-county", "183": "sussex-county",
    "185": "tazewell-county", "187": "warren-county", "191": "washington-county",
    "193": "westmoreland-county", "195": "wise-county", "197": "wythe-county",
    "199": "york-county", "510": "alexandria-city", "520": "bristol-city",
    "530": "buena-vista-city", "540": "charlottesville-city",
    "550": "chesapeake-city", "570": "colonial-heights-city",
    "580": "covington-city", "590": "danville-city", "595": "emporia-city",
    "600": "fairfax-city", "610": "falls-church-city", "620": "franklin-city",
    "630": "fredericksburg-city", "640": "galax-city", "650": "hampton-city",
    "660": "harrisonburg-city", "670": "hopewell-city", "678": "lexington-city",
    "680": "lynchburg-city", "683": "manassas-city", "685": "manassas-park-city",
    "690": "martinsville-city", "700": "newport-news-city", "710": "norfolk-city",
    "720": "norton-city", "730": "petersburg-city", "735": "poquoson-city",
    "740": "portsmouth-city", "750": "radford-city", "760": "richmond-city",
    "770": "roanoke-city", "775": "salem-city", "790": "staunton-city",
    "800": "suffolk-city", "810": "virginia-beach-city", "820": "waynesboro-city",
    "830": "williamsburg-city", "840": "winchester-city",
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Virginia native JSON property")
        result[key] = value
    return result


def _document(body):
    value = json.loads(body, object_pairs_hook=_object)
    if not isinstance(value, dict) or set(value) != DOCUMENT_FIELDS:
        raise ValueError("Changed Virginia native JSON envelope")
    return value


def _english(values):
    matches = [item.get("text") for item in values if item.get("languageId") == "en"]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise ValueError("Missing or ambiguous Virginia source-declared English label")
    return matches[0]


def _integer(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or value < 0 or int(value) != value):
        raise ValueError("Missing or invalid Virginia native count is not zero")
    return int(value)


def _uuid(value):
    if not isinstance(value, str) or re.fullmatch(
            r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value) is None:
        raise ValueError("Invalid Virginia source UUID")
    return value.lower()


def _clock(value):
    match = re.fullmatch(
        r"(20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]{1,7}))?Z",
        value if isinstance(value, str) else "",
    )
    if match is None:
        raise ValueError("Changed Virginia literal UTC count clock")
    fraction = (match.group(2) or "").ljust(6, "0")[:6]
    normalized = match.group(1) + ("." + fraction if fraction else "") + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("Malformed Virginia literal UTC count clock") from error
    if parsed.tzinfo != timezone.utc or parsed < datetime(2026, 11, 3, tzinfo=timezone.utc):
        raise ValueError("Virginia count clock is outside the declared election")
    return parsed


def _election(value, expected_id=None):
    if (
        not isinstance(value, dict)
        or expected_id is not None and _uuid(value.get("id", "")) != _uuid(expected_id)
        or value.get("electionDate") != "2026-11-03"
        or _english(value.get("name", [])) != "2026 November General"
        or value.get("isProduction") is not True
        or type(value.get("isOfficialResults")) is not bool
        or value.get("isPrimary") not in (None, False)
    ):
        raise ValueError("Changed Virginia 2026 general-election declaration")
    for field in ("asOf", "lastUpdated"):
        _clock(value.get(field))
    return value


def _identity(template):
    view, native = template["view"], template["view"]["native_record"]
    return {
        "id": template["id"], "election": template["election"],
        "geography": template["geography"], "measure": template["measure"],
        "source_id": template["source"]["id"], "locality_code": native["locality_code"],
        "county": view["county"], "maps_approved": view["maps_approved"],
        "denominator": template["denominator"],
    }


def _inventory(templates, identity=False):
    values = [_identity(row) if identity else row for row in templates]
    return digest(encoded(sorted(values, key=lambda row: row["id"])))


def route(template):
    if template.get("source", {}).get("id") != SOURCE_ID:
        return None
    source, view = template["source"], template.get("view", {})
    native = view.get("native_record") or {}
    if (
        template.get("election", {}).get("year") != 2026
        or template.get("election", {}).get("type") != "general"
        or template.get("election", {}).get("id") != "us-2026-general-previously-reviewed"
        or template.get("geography", {}).get("state_code") != "VA"
        or template.get("geography", {}).get("level") not in ("county", "county_equivalent")
        or template.get("measure") != MEASURE
        or str(native.get("locality_code", "")) not in LOCALITY_SLUGS
        or (source.get("url"), view.get("source_url"))
        not in ((STORED_URL, STORED_VIEW_URL), (ROOT_URL, ROOT_URL))
    ):
        raise ValueError("Reviewed Virginia locality source lineage changed")
    return {"state": "VA", "adapter": ADAPTER, "url": ROOT_URL}


def validate_templates(templates):
    if len(templates) != EXPECTED_LOCALITIES or len({row["id"] for row in templates}) != len(templates):
        raise ValueError("Complete reviewed Virginia locality inventory is required")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("Reviewed Virginia locality identities or qualifications changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_URL]
    if initial and (len(initial) != EXPECTED_LOCALITIES
                    or _inventory(initial) != INITIAL_FULL_PIN):
        raise ValueError("Initial complete Virginia locality source frame changed")
    for template in templates:
        if route(template) is None:
            raise ValueError("Virginia locality template is not routed")
        view, source = template["view"], template["source"]
        if (
            template["denominator"] is not None
            or view.get("reported_pct") is not None
            or view.get("maps_approved") is not False
            or source["fields"] != view
        ):
            raise ValueError("Virginia rate, map or native-view holds changed")
        if source["url"] == STORED_URL:
            if source["input_sha256"] != SOURCE_SHA:
                raise ValueError("Initial Virginia export pin changed")
            continue
        native = view["native_record"]
        locality = native.get("locality_election") or {}
        root_locality = native.get("root_locality_election") or {}
        if (
            (native.get("private_original_pin") or {}).get("sha256")
                != source["input_sha256"]
            or source.get("selector", {}).get("native_refresh") != native
            or root_locality.get("jurisdictionId", "").lower()
                != native.get("native_locality_uuid", "").lower()
            or _integer(locality.get("ballotsCast")) != template["count"]["value"]
            or view.get("ballots") != template["count"]["value"]
            or native.get("source_updated_at") != template["source_clock"]["literal"]
            or template["source_clock"]["timezone"] != "UTC"
            or native.get("native_report_status_literal")
                != template["reporting_status"]["literal"]
        ):
            raise ValueError("Projected Virginia count, clock, status or source vector differs")


def validate_plan(plan):
    selected = [source for source in plan.get("VA", {}).values()
                if source["adapter"] == ADAPTER]
    if not selected:
        return plan
    if len(selected) != 1:
        raise ValueError("Exactly one complete reviewed Virginia locality source is required")
    validate_templates(selected[0]["templates"])
    return plan


def _locality_url(code):
    return API_ROOT + LOCALITY_SLUGS[code] + "/2026-November-General/data"


def _declared_localities(root):
    children = root.get("jurisdiction", {}).get("childLocalities")
    if not isinstance(children, list) or len(children) != EXPECTED_LOCALITIES:
        raise ValueError("Changed Virginia complete locality declaration")
    result = []
    seen = set()
    for child in children:
        code = str(child.get("mapFeatureId", ""))
        if (code not in LOCALITY_SLUGS or code in seen
                or child.get("shortName") != LOCALITY_SLUGS[code]):
            raise ValueError("Changed Virginia source-declared locality route")
        seen.add(code)
        result.append({
            "code": code, "id": _uuid(child.get("id", "")),
            "short_name": child["shortName"], "name": _english(child.get("name", [])),
            "url": _locality_url(code),
        })
    result.sort(key=lambda row: row["code"])
    if (digest(encoded(result)) != LOCALITY_DECLARATION_PIN
            or digest(encoded([row["url"] for row in result])) != LOCALITY_URLS_PIN):
        raise ValueError("Virginia reviewed locality declaration pin changed")
    return result


def _indexed(values, field, label):
    result = {}
    for value in values:
        identity = _uuid(value.get(field, ""))
        if identity in result:
            raise ValueError("Duplicate Virginia " + label)
        result[identity] = value
    return result


def statistics(body, templates, url, *, acquire):
    if url != ROOT_URL:
        raise ValueError("Unreviewed Virginia native product")
    validate_templates(templates)
    root = _document(body)
    election = _election(root.get("election"), ELECTION_ID)
    localities = _declared_localities(root)
    children = {row["id"]: row for row in localities}
    summaries = _indexed(root.get("localityElections", []), "jurisdictionId",
                         "locality election summary")
    registrations = _indexed(root.get("voterRegistration", []), "id",
                             "locality registration summary")
    if set(children) != set(summaries) or set(children) != set(registrations):
        raise ValueError("Virginia root locality count/registration inventory changed")

    def fetch(item):
        child_body, _ = acquire(item["url"])
        return item, child_body, _document(child_body)

    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(fetch, localities))
    documents, source_pins, units = {}, [], []
    locality_facts = {}
    for child, child_body, document in fetched:
        code, identity = child["code"], child["id"]
        jurisdiction = document.get("jurisdiction", {})
        if (
            _uuid(jurisdiction.get("id", "")) != identity
            or jurisdiction.get("shortName") != child["short_name"]
            or _english(jurisdiction.get("name", [])) != child["name"]
        ):
            raise ValueError("Changed Virginia literal native locality identity")
        summary = _election(summaries[identity])
        local_election = _election(document.get("election"), summary["id"])
        registration = registrations[identity]
        active = _integer(registration.get("activeVoters"))
        inactive = _integer(registration.get("inactiveVoters"))
        registered = _integer(registration.get("total"))
        if active + inactive != registered:
            raise ValueError("Virginia native registration components changed")
        ballots = _integer(local_election.get("ballotsCast"))
        if (
            ballots != _integer(summary.get("ballotsCast"))
            or registered != _integer(summary.get("totalVoters"))
            or registered != _integer(local_election.get("totalVoters"))
            or local_election.get("isOfficialResults") != summary.get("isOfficialResults")
        ):
            raise ValueError("Virginia root/locality count, registration or status differs")
        precincts = _indexed(document.get("precincts", []), "id", "precinct declaration")
        turnout = _indexed(document.get("voterTurnout", []), "id", "precinct turnout row")
        if set(precincts) != set(turnout):
            raise ValueError("Virginia precinct declaration/turnout scope changed")
        registration_sum = 0
        for unit_id, row in turnout.items():
            native = {
                "locality_code": code, "id": unit_id,
                "name": row.get("precinctName"),
            }
            if not isinstance(native["name"], str) or not native["name"]:
                raise ValueError("Missing Virginia native precinct name")
            unit_ballots = _integer(row.get("ballotsCast"))
            unit_turnout = _integer(row.get("voterTurnout"))
            unit_registered = _integer(row.get("voterRegistration"))
            registration_sum += unit_registered
            units.append({
                **native, "ballotsCast": unit_ballots, "voterTurnout": unit_turnout,
                "voterRegistration": unit_registered,
                "precinct": copy.deepcopy(precincts[unit_id]),
                "turnout": copy.deepcopy(row),
                "source_url": child["url"],
                "source_clock": local_election["asOf"],
            })
        if registration_sum != registered:
            raise ValueError("Virginia precinct registrations do not reconcile to locality parent")
        documents[code] = copy.deepcopy(document)
        source_pins.append({"code": code, "url": child["url"], **pin(child_body)})
        locality_facts[code] = {
            "child": child, "summary": summary, "election": local_election,
            "registration": copy.deepcopy(registration),
        }
    unit_identities = sorted(
        [{"locality_code": row["locality_code"], "id": row["id"], "name": row["name"]}
         for row in units],
        key=lambda row: (row["locality_code"], row["id"]),
    )
    if len(units) != EXPECTED_UNITS or digest(encoded(unit_identities)) != UNIT_IDENTITY_PIN:
        raise ValueError("Virginia complete native precinct identity inventory changed")
    root_registered = _integer(election.get("totalVoters"))
    if (
        sum(_integer(row["totalVoters"]) for row in summaries.values()) != root_registered
        or sum(_integer(row["total"]) for row in registrations.values()) != root_registered
    ):
        raise ValueError("Virginia locality registrations do not reconcile to state parent")

    source_pins.sort(key=lambda row: row["code"])
    root_pin = pin(body)
    numerical_manifest = {
        "root": {"url": ROOT_URL, **root_pin},
        "localities": source_pins,
    }
    numerical_pin = pin(encoded(numerical_manifest))
    templates_by_code = {
        str(row["view"]["native_record"]["locality_code"]): row for row in templates}
    if set(templates_by_code) != set(LOCALITY_SLUGS):
        raise ValueError("Virginia templates and source localities differ")
    updates = []
    for code, template in sorted(templates_by_code.items()):
        fact = locality_facts[code]
        child, summary, local_election = fact["child"], fact["summary"], fact["election"]
        locality_status = (
            "OFFICIAL" if local_election["isOfficialResults"] else "UNOFFICIAL")
        if (
            template["view"]["county"] != child["name"]
            or template["geography"]["name"] != child["name"]
        ):
            raise ValueError("Virginia accepted/source locality name differs")
        previous_clock = template["source_clock"].get("literal")
        if previous_clock is not None and _clock(local_election["asOf"]) < _clock(previous_clock):
            raise ValueError("Virginia native locality count clock regressed")
        prior = template["view"]["native_record"]
        native = copy.deepcopy(prior)
        native.setdefault("retained_accepted_export_context", copy.deepcopy(prior))
        native.update(
            native_locality_uuid=child["id"], reviewed_locality_url=child["url"],
            locality_election=copy.deepcopy(local_election),
            root_locality_election=copy.deepcopy(summary),
            root_registration=copy.deepcopy(fact["registration"]),
            ballots_cast=_integer(local_election["ballotsCast"]),
            registered_voters=_integer(local_election["totalVoters"]),
            source_updated_at=local_election["asOf"],
            source_last_updated=local_election["lastUpdated"],
            root_as_of=summary["asOf"], root_last_updated=summary["lastUpdated"],
            native_report_status_literal=locality_status,
            source_clock_timezone_literal="UTC",
            native_reporting_complete_qualified=False,
            private_original_pin=numerical_pin,
            count_role="Locality election ballotsCast; never voterTurnout or candidate votes.",
            registration_role=(
                "Native totalVoters retained as unqualified context; no new analytical rate."
            ),
            statewide_ballots_control={
                "value": _integer(election["ballotsCast"]), "qualified": False,
                "not_repaired_from_locality_sum": True,
            },
            query={
                "native_report_status_literal": locality_status,
                "source_clock_timezone_literal": "UTC",
                "locality_code": code,
                "locality_ballotsCast": _integer(local_election["ballotsCast"]),
                "locality_totalVoters": _integer(local_election["totalVoters"]),
            },
            analytical_rates_promoted=False,
            geographic_joins_changed=False,
        )
        updates.append({
            "id": template["id"], "value": _integer(local_election["ballotsCast"]),
            "native": native, "registered": _integer(local_election["totalVoters"]),
            "clock": local_election["asOf"], "reported_units": None,
            "total_units": None, "rate_compatible": False,
        })
    unit_ballots = sum(row["ballotsCast"] for row in units)
    unit_turnout = sum(row["voterTurnout"] for row in units)
    query = {
        "source_pin": root_pin,
        "numerical_input_manifest": numerical_manifest,
        "numerical_input_manifest_pin": numerical_pin,
        "root_document": copy.deepcopy(root),
        "locality_documents": documents,
        "native_unit_rows": units,
        "reconciliation": {
            "localities": len(localities), "native_unit_rows": len(units),
            "locality_ballots_cast": sum(_integer(row["ballotsCast"])
                                         for row in summaries.values()),
            "state_total_voters": root_registered,
            "state_ballots_cast_control": _integer(election["ballotsCast"]),
            "state_ballots_cast_control_qualified": False,
            "native_unit_ballots_cast_subtotal": unit_ballots,
            "native_unit_voter_turnout_subtotal": unit_turnout,
            "ballots_cast_voter_turnout_differences": sum(
                row["ballotsCast"] != row["voterTurnout"] for row in units),
            "unit_ballots_not_summed_to_replace_locality_parents": True,
            "pooled_modes_or_parent_residuals_allocated": False,
            "registration_components_and_precinct_sums_reconcile": True,
            "analytical_rates_promoted": False,
            "geographic_joins_changed": False,
        },
    }
    return {
        "updates": updates, "complete_native_query": [query],
        "source_url": ROOT_URL,
        "numerical_input_pins": {"voterTurnout_Electiondata": numerical_pin},
        "geographic_joins_changed": False, "analytical_rates_promoted": False,
        "reviewed_source_url_bridge": {
            "contract": "participation.reviewed_source_url_bridge.v1",
            "source_id": SOURCE_ID, "stored_source_url": STORED_URL,
            "stored_view_source_url": STORED_VIEW_URL, "reviewed_url": ROOT_URL,
            "prior_full_inventory_pin": INITIAL_FULL_PIN,
            "observation_ids_pin": digest(encoded(sorted(row["id"] for row in templates))),
            "declared_entry_url": ENTRY_URL,
            "reviewed_locality_urls_pin": LOCALITY_URLS_PIN,
        },
    }
