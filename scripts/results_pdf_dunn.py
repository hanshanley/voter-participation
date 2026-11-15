"""Reviewed source-lineage bridge and parser for Dunn County, Wisconsin."""

import copy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import re

from scripts.participation_intake.contract import count, digest, encoded, validate


URL = (
    "https://dunncountywi.govoffice2.com/vertical/Sites/"
    "%7B97C2FC1A-69D7-4F5C-BA23-79B5C833BED5%7D/uploads/"
    "Dunn_County_Unofficial_Results_11.03.2026%281%29.pdf"
)
STORED_URL = (
    "https://dunncountywi.govoffice2.com/vertical/Sites/"
    "%7B97C2FC1A-69D7-4F5C-BA23-79B5C833BED5%7D/uploads/"
    "Dunn_County_-_November_3_2026_Geneal_Election_Official_Results.pdf"
)
SOURCE_ID = "wi-dunn-unofficial-20261113"
OBSERVATION_ID = "88eca302e65a1f5224df5cf0673b4aa3"
RETAINED_INPUT_SHA256 = "0dcb0761ba33936d3b14e43d415bab86fa96fbc13879fdbf6c1a5fc2e421d5a0"
ACCEPTED_ROW_SHA256 = "7c9b0a75d984fe2a4f714b2e2674b7bd85b1970211c0edc2b55e1652f45c7ae1"
OFFICIAL_CONTROL = {
    "bytes": 1570293,
    "path": "originals/wi-dunn-official.pdf",
    "sha256": "e2bfb1cfd7fa24a7d29ee1000b28c9c498606efa93e641408a07edc3f12c0742",
}
INTEGER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
ALLOWED_REPLACEMENT_PATHS = (
    "count.literal",
    "count.value",
    "source.fields.eligible_voters",
    "source.fields.printed_eligible_percent",
    "source.fields.printed_registered_percent",
    "source.fields.registered_voters",
    "source.input_sha256",
    "source.url",
    "view.ballots",
    "view.native_record.eligible_voters",
    "view.native_record.printed_eligible_percent",
    "view.native_record.printed_registered_percent",
    "view.native_record.registered_voters",
    "view.registered",
    "view.source_url",
)


def _one(pattern, text, message):
    matches = re.findall(pattern, text, re.I | re.M)
    if len(matches) != 1:
        raise ValueError(message)
    return matches[0]


def _percent(numerator, denominator, literal, label):
    if re.fullmatch(r"[0-9]+%", literal or "") is None:
        raise ValueError(f"Dunn {label} percentage literal changed")
    if denominator <= 0 or numerator > denominator:
        raise ValueError(f"Dunn count exceeds {label} context")
    printed = (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if printed != Decimal(literal[:-1]):
        raise ValueError(f"Dunn {label} percentage disagrees")


def _control(fields):
    if (
        not isinstance(fields, dict)
        or fields.get("official_board_report_pin") != OFFICIAL_CONTROL
        or fields.get("official_max_governor_contest_total") != 19758
    ):
        raise ValueError("Dunn official report control changed")


def _stable_semantics(template):
    if (
        template.get("id") != OBSERVATION_ID
        or template.get("contract") != "participation.observation.v1"
        or template.get("election")
        != {
            "date": "2026-11-03",
            "id": "wi-2026-11-03-general",
            "qualification": "native",
            "type": "general",
            "year": 2026,
        }
        or template.get("geography")
        != {
            "id": "native:WI:county:dunn-county",
            "join": {
                "evidence": None,
                "feature_key": None,
                "reference_id": None,
                "status": "unreviewed",
            },
            "level": "county",
            "name": "Dunn County",
            "parent_id": None,
            "state_code": "WI",
        }
        or template.get("measure")
        != {
            "id": "total-votes-cast",
            "kind": "ballots_cast",
            "literal": "Total Votes Cast",
            "mode": "source_defined",
            "unit": "source_reported_count",
        }
        or template.get("denominator") is not None
        or template.get("source_clock") != {"literal": None, "timezone": None}
        or template.get("reporting_status")
        != {
            "complete": None,
            "literal": "UNOFFICIAL RESULTS",
            "reported_units": None,
            "total_units": None,
        }
        or template.get("quality")
        != {
            "conflicts": [],
            "notes": [
                "analytical_denominators_and_rates_withheld: True",
                "official_canvass_has_contest_totals_not_a_ballot_parent: True",
                "source_clock_absent: True",
            ],
        }
    ):
        raise ValueError("Dunn accepted identity, scope, status, clock or qualification changed")
    source, view = template.get("source", {}), template.get("view", {})
    if (
        source.get("id") != SOURCE_ID
        or source.get("classification") != "public_aggregate"
        or source.get("selector") != {"id": "voter-participation-total"}
        or re.fullmatch(r"[a-f0-9]{64}", str(source.get("input_sha256", ""))) is None
        or view.get("source_status_literal") != "UNOFFICIAL RESULTS"
        or view.get("source_update_label") is not None
        or view.get("source_update_timezone") is not None
        or view.get("denominator") is not None
        or view.get("reported_pct") is not None
        or view.get("native_printed_pct") is not None
        or view.get("maps_approved") is not False
        or view.get("official") is not False
        or view.get("unique_voter_count_qualified") is not False
        or view.get("cast_ballot_count_qualified") is not False
        or view.get("participation_measure_kind") != "total-votes-cast"
        or view.get("participation_measure_literal") != "Total Votes Cast"
        or view.get("participation_measure_label") != "Total Votes Cast"
        or view.get("source_mode") != "source_defined"
    ):
        raise ValueError("Dunn accepted source or view semantics changed")
    _control(source.get("fields"))
    _control(view.get("native_record"))
    value = template.get("count", {}).get("value")
    fields = source["fields"]
    native = view["native_record"]
    if (
        template.get("count") != {"literal": value, "status": "reported", "value": value}
        or count(value) != value
        or view.get("ballots") != value
        or view.get("registered") != fields.get("registered_voters")
        or any(native.get(key) != fields.get(key) for key in fields)
    ):
        raise ValueError("Dunn accepted count or retained native facts changed")
    for fields in (fields, native):
        registered = fields.get("registered_voters")
        eligible = fields.get("eligible_voters")
        if (
            count(registered) != registered
            or count(eligible) != eligible
            or value > registered
            or value > eligible
        ):
            raise ValueError("Dunn retained context is unsafe")
        _percent(value, registered, fields.get("printed_registered_percent"), "registered-voter")
        _percent(value, eligible, fields.get("printed_eligible_percent"), "eligible-voter")


def source_url(template):
    """Return the reviewed transport URL, applying only the pinned Dunn lineage bridge."""
    source, view = template.get("source", {}), template.get("view", {})
    candidate = (
        template.get("id") == OBSERVATION_ID
        or source.get("id") == SOURCE_ID
        or source.get("url") in (STORED_URL, URL)
        or view.get("source_url") in (STORED_URL, URL)
    )
    if not candidate:
        return None
    if template.get("id") != OBSERVATION_ID:
        raise ValueError("Dunn reviewed observation identity changed")
    urls = source.get("url"), view.get("source_url")
    if urls == (STORED_URL, STORED_URL):
        if (
            source.get("id") != SOURCE_ID
            or source.get("input_sha256") != RETAINED_INPUT_SHA256
            or digest(encoded(template)) != ACCEPTED_ROW_SHA256
        ):
            raise ValueError("Dunn legacy URL bridge prior observation pin changed")
    elif urls == (URL, URL):
        _stable_semantics(template)
    else:
        raise ValueError("Dunn source and view URLs are mixed or unreviewed")
    _stable_semantics(template)
    return URL


def _replacement(template, source_pin, value, registered, registered_pct, eligible, eligible_pct):
    replacement = copy.deepcopy(template)
    replacement["count"] = {"literal": value, "status": "reported", "value": value}
    replacement["source"]["url"] = URL
    replacement["source"]["input_sha256"] = source_pin["sha256"]
    replacement["view"]["source_url"] = URL
    replacement["view"]["ballots"] = value
    replacement["view"]["registered"] = registered
    for fields in (replacement["source"]["fields"], replacement["view"]["native_record"]):
        fields.update(
            registered_voters=registered,
            printed_registered_percent=registered_pct,
            eligible_voters=eligible,
            printed_eligible_percent=eligible_pct,
        )
    validate(replacement)
    _stable_semantics(replacement)
    return replacement


def parse_pages(pages, metadata, templates, source_pin):
    if len(pages) != 2 or any(not isinstance(page, str) or not page.strip() for page in pages):
        raise ValueError("Dunn unofficial PDF page inventory or text layer changed")
    if len(templates) != 1 or source_url(templates[0]) != URL:
        raise ValueError("Dunn source must bind its one reviewed county parent")
    title = metadata.get("/Title")
    created = metadata.get("/CreationDate")
    modified = metadata.get("/ModDate")
    if (
        title != "Dunn County Unofficial Results 11.03.2026.xlsx"
        or re.fullmatch(r"D:202611(?:0[3-9]|[12][0-9]|30)[0-9]{6}-06'00'", created or "") is None
        or modified != created
    ):
        raise ValueError("Dunn PDF election metadata changed")
    text = "\n".join(pages)
    normalized = " ".join(text.split())
    if (
        "DUNN COUNTY, WI UNOFFICIAL RESULTS - November 3, 2026 General Election"
        not in normalized
        or re.search(r"\b(?:PRIMARY|SPECIAL|RUNOFF)\b", normalized, re.I)
        or re.search(r"\b(?:Report Generated|Last Updated|Updated at)\b", normalized, re.I)
    ):
        raise ValueError("Dunn election, status or clock semantics changed")
    count_literal = _one(
        r"\bTotal Votes Cast\s*=\s*(" + INTEGER + r")\b",
        text,
        "Dunn direct Total Votes Cast parent is absent or ambiguous",
    )
    registered_literal, registered_pct = _one(
        r"\bTotal Registered Voters\s+(" + INTEGER + r")\s+([0-9]+%)\s+Page 1 of 1\b",
        text,
        "Dunn registered-voter context changed",
    )
    eligible_literal, eligible_pct = _one(
        r"\bEligilbe Voters\s+(" + INTEGER + r")\s+([0-9]+%)",
        text,
        "Dunn eligible-voter context changed",
    )
    value, registered, eligible = map(count, (count_literal, registered_literal, eligible_literal))
    _percent(value, registered, registered_pct, "registered-voter")
    _percent(value, eligible, eligible_pct, "eligible-voter")
    if (
        not isinstance(source_pin, dict)
        or set(source_pin) != {"bytes", "sha256"}
        or count(source_pin["bytes"]) != source_pin["bytes"]
        or re.fullmatch(r"[a-f0-9]{64}", source_pin["sha256"]) is None
    ):
        raise ValueError("Dunn source pin is incomplete")
    query = {
        "county": "Dunn County",
        "election_date": "2026-11-03",
        "native_report_status_literal": "UNOFFICIAL RESULTS",
        "native_measure_literal": "Total Votes Cast",
        "native_count_literal": count_literal,
        "count": value,
        "registered_voters": registered,
        "printed_registered_percent": registered_pct,
        "eligible_voters": eligible,
        "printed_eligible_percent": eligible_pct,
        "physical_pdf_pages": 2,
        "spreadsheet_printed_page_literal": "Page 1 of 1",
        "pdf_title": title,
        "pdf_creation_literal": created,
        "pdf_creation_is_not_count_update_clock": True,
        "source_clock_literal": None,
        "source_clock_timezone": None,
        "source_pin": dict(source_pin),
        "direct_parent_not_contest_total": True,
    }
    template = templates[0]
    replacement = _replacement(
        template, source_pin, value, registered, registered_pct, eligible, eligible_pct
    )
    bridge = {
        "contract": "participation.reviewed_source_url_bridge.v1",
        "observation_id": OBSERVATION_ID,
        "source_id": SOURCE_ID,
        "retained_input_sha256": RETAINED_INPUT_SHA256,
        "accepted_prior_row_sha256": ACCEPTED_ROW_SHA256,
        "stored_source_url": STORED_URL,
        "stored_view_source_url": STORED_URL,
        "reviewed_url": URL,
        "allowed_replacement_paths": list(ALLOWED_REPLACEMENT_PATHS),
        "declaration_status": "held_index_was_ip_blocked_not_a_successful_declaration",
        "qualification_basis": "retained successful HTTP 200 native PDF receipt and exact prior identity",
    }
    native = copy.deepcopy(replacement["view"]["native_record"])
    update = {
        "id": OBSERVATION_ID,
        "value": value,
        "native": native,
        "registered": registered,
        "clock": None,
        "reported_units": None,
        "total_units": None,
        "rate_compatible": False,
        "replacement": replacement,
        "reviewed_source_url_bridge": bridge,
    }
    return {
        "updates": [update],
        "complete_native_query": [query],
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "count_parent_is_direct_source_literal": True,
        "contest_totals_are_not_count_fallbacks": True,
        "pdf_creation_is_not_count_update_clock": True,
        "reviewed_source_url_bridge": bridge,
    }


def statistics(body, templates):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted:
        raise ValueError("Encrypted Dunn source is not qualified")
    pages = [page.extract_text() or "" for page in reader.pages]
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
    source_pin = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    return parse_pages(pages, metadata, templates, source_pin)
