"""Canonical onboarding and unattended refresh for Louisiana native # VOTING."""

import copy
import gzip
import json
import re

from scripts.participation_intake.contract import (
    VERSION,
    digest,
    encoded,
    observation_id,
    pin,
    validate_all,
)
from scripts import results_native_louisiana as source


ADAPTER = "reviewed_louisiana_post_election_statistics"
SOURCE_ID = "la-sos-post-election-statistics-2026-11-03"
ELECTION_ID = "LA-2026-11-03-general"
MEASURE_ID = "native-voters-participating"
CANONICAL_IDENTITY_PIN = "85a166f8cde8aa40bbfc6494ab40a1fe43722e72dbeecb53213604cf36fd2d0e"

SAFE_DECLARATION_CONTRACT = "participation.safe_factual_source_declaration.v1"


def _source_bodies(bodies):
    result = dict(bodies)
    expected = {
        source.STATE_INDEX_URL: source.STATE_XLSX_URL,
        source.PARISH_INDEX_URL: source.PARISH_XLSX_URL,
    }
    for page_url, product_url in expected.items():
        body = result[page_url]
        if not body.lstrip().startswith(b"{"):
            continue
        declaration = json.loads(body)
        if (
            declaration.get("contract") != SAFE_DECLARATION_CONTRACT
            or declaration.get("page_url") != page_url
            or declaration.get("declared_products") != [product_url]
            or declaration.get("authority_status")
                != "verified_exact_publisher_executed_production_mapping"
            or not isinstance(declaration.get("private_original"), dict)
            or declaration["private_original"].get("bytes", 0) <= 0
            or not re.fullmatch(
                r"[a-f0-9]{64}",
                declaration["private_original"].get("sha256", ""),
            )
        ):
            raise ValueError("Malformed Louisiana safe factual source declaration")
        result[page_url] = (
            '<a href="' + product_url + '">declared workbook</a>'
        ).encode()
    return result


def _geography_id(native_id):
    return "native:LA:post-election:" + re.sub(r"[^A-Za-z0-9]+", ":", native_id).strip(":")


def _physical_selectors(data):
    selected = {}
    tables = data["complete_native_query"]["physical_tables"]
    for role, workbook in (
        ("state_workbook", tables["statewide_workbook"]),
        ("parish_workbook", tables["parish_workbook"]),
    ):
        for table in workbook:
            if role == "state_workbook" and table["name"] != "Sheet1":
                continue
            for row in table["rows"]:
                cells = {cell["address"][:1]: cell["value"] for cell in row["cells"]}
                identity = cells.get("B")
                if identity == "STATE ":
                    identity = "STATE"
                if isinstance(identity, str) and (
                    identity == "STATE"
                    or re.fullmatch(r"PAR [0-9]{2}", identity)
                    or re.fullmatch(r"PAR [0-9]{2} W [A-Z0-9-]+ P [A-Z0-9-]+", identity)
                ):
                    selected[(role, identity)] = {
                        "workbook_role": role,
                        "sheet": table["name"],
                        "identity_row": row["row"],
                        "voting_row": row["row"] + 1,
                        "percentage_row": row["row"] + 2,
                        "columns": dict(
                            native_identity="B",
                            registered_total="D",
                            voters_participating_total="D",
                            percent_voting_total="D",
                        ),
                    }
    return selected


def _parent_counts(observations):
    result = {}
    for row in observations:
        parent = row["parent_native_id"]
        if parent is not None:
            result[parent] = result.get(parent, 0) + 1
    return result


def _canonical_identity(row):
    return {
        "id": row["id"],
        "election": row["election"],
        "geography": row["geography"],
        "measure": row["measure"],
        "source_id": row["source"]["id"],
        "source_url": row["source"]["url"],
        "native_id": row["view"]["native_record"]["native_id"],
        "source_input": row["view"]["native_record"]["source_input"],
    }


def _identity_pin(rows):
    return digest(encoded([_canonical_identity(row) for row in rows]))


def canonical_rows(bodies):
    data = source.statistics(_source_bodies(bodies))
    selectors = _physical_selectors(data)
    parent_counts = _parent_counts(data["observations"])
    pins = {
        "state_workbook": {"url": source.STATE_XLSX_URL, **pin(bodies[source.STATE_XLSX_URL])},
        "parish_workbook": {"url": source.PARISH_XLSX_URL, **pin(bodies[source.PARISH_XLSX_URL])},
    }
    native_to_geo = {
        row["native_id"]: _geography_id(row["native_id"]) for row in data["observations"]
    }
    rows = []
    for item in data["observations"]:
        native_id = item["native_id"]
        level = item["native_level"]
        source_input = "state_workbook" if level == "state" else "parish_workbook"
        selector = selectors[(source_input, native_id)]
        geography_id = native_to_geo[native_id]
        parent_id = (
            None
            if item["parent_native_id"] is None
            else native_to_geo[item["parent_native_id"]]
        )
        county_id = (
            None
            if level == "state"
            else geography_id if level == "parish" else parent_id
        )
        county = (
            None
            if level == "state"
            else item["native_name"]
            if level == "parish"
            else next(
                row["native_name"]
                for row in data["observations"]
                if row["native_id"] == item["parent_native_id"]
            )
        )
        geography_level = "state" if level == "state" else (
            "county_equivalent" if level == "parish" else "precinct"
        )
        geography = {
            "id": geography_id,
            "name": item["native_name"],
            "state_code": "LA",
            "level": geography_level,
            "parent_id": parent_id,
            "join": {
                "status": "nongeographic" if level == "state" else "unreviewed",
                "reference_id": None,
                "feature_key": None,
                "evidence": None,
            },
        }
        measure = {
            "id": MEASURE_ID,
            "literal": "# VOTING",
            "kind": "voters_reported",
            "mode": "all_methods",
            "unit": "source_reported_voters_participating",
        }
        stock = item["registration_stock"]["value"]
        count = item["count"]["value"]
        source_status = item["reporting_status"]["source_status_literal"]
        known_query_inventory = parent_counts.get(native_id, 1)
        reported_units = None
        total_units = None
        native = {
            "native_id": native_id,
            "native_name": item["native_name"],
            "native_level": level,
            "native_parent_id": item["parent_native_id"],
            "source_input": source_input,
            "source_original_pin": pins[source_input],
            "physical_selector": selector,
            "registered_voters_stock": stock,
            "voters_participating": count,
            "native_percent_voting": item["native_percent_voting"],
            "native_vectors": copy.deepcopy(item["native_vectors"]),
            "native_report_status_literal": source_status,
            "native_reporting_complete_qualified": False,
            "known_query_inventory": known_query_inventory,
            "source_clock_literal": None,
            "registration_is_not_analytical_denominator": True,
            "state_and_parish_parents_are_not_summed_with_precincts": True,
            "query": {
                "native_id": native_id,
                "source_input": source_input,
                "registered_voters_stock": stock,
                "voters_participating": count,
                "native_percent_voting": item["native_percent_voting"],
                "native_report_status_literal": source_status,
            },
        }
        view = {
            "year": 2026,
            "state_code": "LA",
            "county": county,
            "county_id": county_id,
            "county_fips": None,
            "geography_level": geography_level,
            "unit": item["native_name"] if level == "precinct" else None,
            "unit_key": native_id if level == "precinct" else None,
            "unit_kind": "native_louisiana_precinct" if level == "precinct" else None,
            "source_mode": "all_methods",
            "denominator_basis": "source_registration_stock_not_analytical_denominator",
            "participation_measure_kind": "voters_reported",
            "participation_measure_literal": "# VOTING",
            "participation_measure_label": "Native # VOTING",
            "cast_ballot_count_qualified": False,
            "unique_voter_count_qualified": False,
            "maps_approved": False,
            "ballots": count,
            "registered": stock,
            "denominator": None,
            "reported_pct": None,
            "native_printed_pct": None,
            "reported_units": reported_units,
            "total_units": total_units,
            "source_status_literal": source_status,
            "source_update_label": None,
            "source_url": pins[source_input]["url"],
            "source_sha256": pins[source_input]["sha256"],
            "native_parent_only": level == "state",
            "frontend_activation_approved": False,
            "automatic_source_refresh": True,
            "source_reporting_label": (
                "Automatic same-source native statistical refresh. Missing reporting stays unknown; "
                "source counts are not certification or independently observed people. "
                "Prior geographic qualifications retained; no new boundary join or local model."
            ),
            "quality": [
                "Candidate totals, ballot returns and rounded-percent reconstruction are not used.",
                "Source parish codes are native identifiers, not assumed FIPS.",
                "No map, reference, rate, model or frontend activation is approved.",
                "State and parish parents are separate printed controls and are never added to precincts.",
            ],
            "native_record": native,
        }
        source_pin = pins[source_input]
        row = {
            "contract": VERSION,
            "id": observation_id(SOURCE_ID, ELECTION_ID, geography_id, MEASURE_ID, "all_methods"),
            "election": {
                "id": ELECTION_ID,
                "year": 2026,
                "date": "2026-11-03",
                "type": "general",
                "qualification": "native",
            },
            "geography": geography,
            "measure": measure,
            "count": {"value": count, "status": "reported", "literal": count},
            "denominator": None,
            "source_clock": {
                "literal": None,
                "timezone": None,
                "qualification": "native_clock_or_explicitly_not_supplied",
            },
            "reporting_status": {
                "literal": source_status,
                "reported_units": reported_units,
                "total_units": total_units,
                "complete": None,
            },
            "source": {
                "id": SOURCE_ID,
                "url": source_pin["url"],
                "input_sha256": source_pin["sha256"],
                "selector": {"native_refresh": native},
                "classification": "public_aggregate",
                "fields": view,
            },
            "quality": {
                "conflicts": [],
                "notes": list(view["quality"]),
            },
            "view": view,
        }
        rows.append(row)
    validate_all(rows)
    if len(rows) != 3783 or len({row["id"] for row in rows}) != 3783:
        raise ValueError("Louisiana canonical observation inventory changed")
    identity_pin = _identity_pin(rows)
    if CANONICAL_IDENTITY_PIN != "TO_BE_FILLED" and identity_pin != CANONICAL_IDENTITY_PIN:
        raise ValueError("Louisiana canonical identity frame changed")
    return rows


def extend_templates(baseline, templates):
    index = json.loads(baseline["index.json"])
    declaration = index["states"]["LA"]
    shard = json.loads(gzip.decompress(baseline[declaration["file"]]))
    selected = {row["id"] for row in templates}
    extra = [
        row
        for row in shard["records"]
        if row.get("source", {}).get("id") == SOURCE_ID and row["id"] not in selected
    ]
    if extra and (
        len(extra) != 1
        or extra[0]["geography"]["level"] != "state"
        or extra[0]["view"].get("native_parent_only") is not True
    ):
        raise ValueError("Louisiana unselected native parent inventory changed")
    return [*templates, *extra]


def validate_templates(templates):
    if len(templates) != 3783 or len({row["id"] for row in templates}) != 3783:
        raise ValueError("Complete Louisiana canonical source family is required")
    ordered = sorted(
        templates,
        key=lambda row: (
            {"state": 0, "county_equivalent": 1, "precinct": 2}.get(
                row["geography"]["level"], 9
            ),
            row["view"]["native_record"]["native_id"],
        ),
    )
    for row in ordered:
        view = row.get("view", {})
        native = view.get("native_record", {})
        source_input = native.get("source_input")
        expected_url = (
            source.STATE_XLSX_URL
            if source_input == "state_workbook"
            else source.PARISH_XLSX_URL
        )
        if (
            row["source"]["id"] != SOURCE_ID
            or row["source"]["url"] != expected_url
            or view.get("source_url") != expected_url
            or row["measure"]
            != {
                "id": MEASURE_ID,
                "literal": "# VOTING",
                "kind": "voters_reported",
                "mode": "all_methods",
                "unit": "source_reported_voters_participating",
            }
            or row["denominator"] is not None
            or view.get("denominator") is not None
            or view.get("reported_pct") is not None
            or view.get("maps_approved") is not False
            or view.get("frontend_activation_approved") is not False
            or row["source"]["fields"] != view
        ):
            raise ValueError("Louisiana canonical scope, source or qualifications changed")
    if _identity_pin(ordered) != CANONICAL_IDENTITY_PIN:
        raise ValueError("Louisiana canonical identities changed")


def route(template):
    if template.get("source", {}).get("id") != SOURCE_ID:
        return None
    view = template.get("view", {})
    native = view.get("native_record", {})
    expected = (
        source.STATE_XLSX_URL
        if native.get("source_input") == "state_workbook"
        else source.PARISH_XLSX_URL
    )
    if (
        template["geography"]["state_code"] != "LA"
        or template["election"]["id"] != ELECTION_ID
        or template["measure"]["id"] != MEASURE_ID
        or template["source"]["url"] != expected
        or view.get("source_url") != expected
    ):
        raise ValueError("Louisiana canonical source route changed")
    return {"state": "LA", "adapter": ADAPTER, "url": source.STATE_XLSX_URL}


def validate_plan(plan):
    selected = [
        item
        for item in plan.get("LA", {}).values()
        if item.get("adapter") == ADAPTER
    ]
    if not selected:
        return plan
    if len(selected) != 1:
        raise ValueError("Exactly one Louisiana native source family is required")
    validate_templates(selected[0]["templates"])
    return plan


def statistics(body, templates, url, *, acquire):
    if url != source.STATE_XLSX_URL:
        raise ValueError("Unreviewed Louisiana native product")
    bodies = {source.STATE_XLSX_URL: body}
    receipts = {source.STATE_XLSX_URL: {"url": url, **pin(body)}}
    for dependency in (
        source.ELECTION_DATES_URL,
        source.STATE_INDEX_URL,
        source.PARISH_INDEX_URL,
        source.PARISH_XLSX_URL,
    ):
        bodies[dependency], receipts[dependency] = acquire(dependency)
    parsed = source.statistics(_source_bodies(bodies))
    validate_templates(templates)
    by_native = {
        row["native_id"]: row for row in parsed["observations"]
    }
    updates = []
    for template in templates:
        old_native = template["view"]["native_record"]
        native_id = old_native["native_id"]
        item = by_native.get(native_id)
        if (
            item is None
            or item["native_name"] != old_native["native_name"]
            or item["native_level"] != old_native["native_level"]
            or item["parent_native_id"] != old_native["native_parent_id"]
        ):
            raise ValueError("Louisiana native source identity differs")
        if (
            template["reporting_status"]["literal"] == "Official"
            and parsed["source_status"]["official"] is False
        ):
            raise ValueError("Louisiana official source status regressed")
        source_input = old_native["source_input"]
        source_pin = (
            pin(body)
            if source_input == "state_workbook"
            else pin(bodies[source.PARISH_XLSX_URL])
        )
        native = copy.deepcopy(old_native)
        native.update(
            source_original_pin={
                "url": (
                    source.STATE_XLSX_URL
                    if source_input == "state_workbook"
                    else source.PARISH_XLSX_URL
                ),
                **source_pin,
            },
            registered_voters_stock=item["registration_stock"]["value"],
            voters_participating=item["count"]["value"],
            native_percent_voting=item["native_percent_voting"],
            native_vectors=copy.deepcopy(item["native_vectors"]),
            native_report_status_literal=parsed["source_status"]["literal"],
            source_clock_literal=None,
            query={
                "native_id": native_id,
                "source_input": source_input,
                "registered_voters_stock": item["registration_stock"]["value"],
                "voters_participating": item["count"]["value"],
                "native_percent_voting": item["native_percent_voting"],
                "native_report_status_literal": parsed["source_status"]["literal"],
            },
        )
        updates.append(
            {
                "id": template["id"],
                "value": item["count"]["value"],
                "native": native,
                "registered": item["registration_stock"]["value"],
                "clock": None,
                "reported_units": template["reporting_status"]["reported_units"],
                "total_units": template["reporting_status"]["total_units"],
                "rate_compatible": False,
                "source_input": source_input,
            }
        )
    return {
        "updates": updates,
        "complete_native_query": [
            {
                "source_pins": {
                    key: {"url": bodies_url, **pin(bodies[bodies_url])}
                    for key, bodies_url in (
                        ("state_workbook", source.STATE_XLSX_URL),
                        ("parish_workbook", source.PARISH_XLSX_URL),
                    )
                },
                "event_inventory_record": parsed["source_status"]["record"],
                "state_observations": parsed["state_observations"],
                "parish_observations": parsed["parish_observations"],
                "precinct_observations": parsed["precinct_observations"],
                "reported_zero_observations": parsed["reported_zero_observations"],
                "identity_pin": parsed["identity_pin"],
            }
        ],
        "full_native_source_query": parsed["complete_native_query"],
        "numerical_input_pins": {
            "state_workbook": {
                "url": source.STATE_XLSX_URL,
                **pin(bodies[source.STATE_XLSX_URL]),
            },
            "parish_workbook": {
                "url": source.PARISH_XLSX_URL,
                **pin(bodies[source.PARISH_XLSX_URL]),
            },
        },
        "source_url": source.STATE_XLSX_URL,
        "source_status_literal": parsed["source_status"]["literal"],
        "source_clock": None,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "registration_promoted_to_analytical_denominator": False,
        "parents_and_precincts_summed_together": False,
    }


__all__ = [
    "ADAPTER",
    "SOURCE_ID",
    "canonical_rows",
    "extend_templates",
    "route",
    "statistics",
    "validate_plan",
    "validate_templates",
]

