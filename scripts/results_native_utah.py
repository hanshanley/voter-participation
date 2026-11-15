"""Refresh four reviewed Utah county totals from official summary reports."""

import copy
from datetime import datetime, timezone
import io
import json
import re
from urllib.parse import quote, urlsplit

from scripts.participation_intake.contract import digest, encoded, pin


ADAPTER = "reviewed_utah_official_summary_participation"
ENTRY_URL = (
    "https://electionresults.utah.gov/results/public/Utah/elections/"
    "General11032026"
)
API_URL = (
    "https://electionresults.utah.gov/results/public/api/elections/Utah/"
    "General11032026/data"
)
JURISDICTION_ID = "a7510980-7b10-4aca-a2d8-ff92951aca1c"
ELECTION_ID = "01000000-3eb9-2098-2ce9-08df22ebab67"
CDN_ROOT = "https://electionresults.utah.gov/cdn/results/" + JURISDICTION_ID + "/"
STORED_URL = (
    "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
    "68c22a9e14b1ba0d61ed5a953d58e2cf8c641c1f/"
    "data/participation-count-successors/20261111-ut-01/native-facts.json"
)
REPORTS = {
    "Cache County": {
        "source_id": "native-utah-total-20261110-cache",
        "report_name": "Cache County Official Summary Results",
        "status": "OFFICIAL RESULTS",
        "accepted_url": (
            CDN_ROOT
            + "2026%20General%20Summary%20Results_Cache_"
            "c8e8c7b4-81e3-45fb-9eba-c8240d7695f2.pdf"
        ),
    },
    "Kane County": {
        "source_id": "native-utah-total-20261110-kane",
        "report_name": "Kane County Official Summary Results",
        "status": "OFFICIAL RESULTS",
        "accepted_url": (
            CDN_ROOT
            + "Official%20Nov%203%20General%20Election%20Summary%20Results_"
            "f3ffbdcf-a736-466c-b668-5103809e9051.pdf"
        ),
    },
    "Millard County": {
        "source_id": "native-utah-total-20261110-millard",
        "report_name": "Millard County Official Summary Results",
        "status": "OFFICIAL RESULTS",
        "accepted_url": (
            CDN_ROOT
            + "Summary%20Results%2011-10-26_"
            "a24a5aae-13e3-4834-8828-28b178430c3d.pdf"
        ),
    },
    "Piute County": {
        "source_id": "native-utah-total-20261110-piute",
        "report_name": "Piute County Official Summary Results",
        "status": "2026 General Election Official Results",
        "accepted_url": (
            CDN_ROOT
            + "2026%20General%20Election%20Summary%20report_"
            "658680f6-2bab-4a91-b85f-801e48b25281.pdf"
        ),
    },
}
SOURCE_IDS = {row["source_id"] for row in REPORTS.values()}
MEASURE = {
    "id": "native-20261110-total-ballots",
    "kind": "ballots_cast",
    "literal": "Native Ballots Cast - Total",
    "mode": "all_methods",
    "unit": "source_reported_count",
}
IDENTITY_PIN = "24f43f144a6684dc2baa9747c2d4f466175d0b2e93015baf54903113be399855"
INITIAL_FULL_PIN = "a50aa063d8ccf1a67347bc810c31902c339be46581548c6e10c87594e3771b9e"
UTC_CLOCK = re.compile(
    r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:"
    r"[0-5][0-9](?:\.[0-9]{1,7})?Z"
)
LOCAL_CLOCK = re.compile(
    r"(?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/20[0-9]{2} "
    r"(?:0[1-9]|1[0-2]):[0-5][0-9](?:AM|PM)"
)
UPLOAD_CLOCK = re.compile(
    r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:"
    r"[0-5][0-9](?:\.[0-9]{1,7})?"
)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Utah native JSON property")
        result[key] = value
    return result


def _integer(value, label):
    if isinstance(value, bool):
        raise ValueError("Invalid Utah " + label)
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and value >= 0 and value.is_integer():
        return int(value)
    raise ValueError("Missing or invalid Utah " + label + " is not zero")


def _english(values, label):
    if not isinstance(values, list):
        raise ValueError("Missing Utah " + label)
    found = [
        row.get("text")
        for row in values
        if isinstance(row, dict) and row.get("languageId") == "en"
    ]
    if len(found) != 1 or not isinstance(found[0], str) or not found[0].strip():
        raise ValueError("Missing or ambiguous Utah English " + label)
    return found[0]


def _utc_clock(value, label):
    if not isinstance(value, str) or UTC_CLOCK.fullmatch(value) is None:
        raise ValueError("Missing or changed Utah " + label)
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
        raise ValueError("Utah UTC clock is outside the declared election")
    return parsed


def _local_clock(value):
    if not isinstance(value, str) or LOCAL_CLOCK.fullmatch(value) is None:
        raise ValueError("Missing Utah summary clock is not an inferred time")
    parsed = datetime.strptime(value, "%m/%d/%Y %I:%M%p")
    if not datetime(2026, 11, 3) <= parsed < datetime(2027, 2, 1):
        raise ValueError("Utah summary clock is outside the declared election")
    return parsed


def _upload_clock(value):
    if not isinstance(value, str) or UPLOAD_CLOCK.fullmatch(value) is None:
        raise ValueError("Missing Utah official report declaration clock")
    base = value
    if "." in base:
        prefix, fraction = base.split(".", 1)
        base = prefix + "." + (fraction + "000000")[:6]
    parsed = datetime.fromisoformat(base)
    if not datetime(2026, 11, 3) <= parsed < datetime(2027, 2, 1):
        raise ValueError("Utah official report declaration clock is outside the election")
    return parsed


def _official_pdf_url(value):
    parsed = urlsplit(value) if isinstance(value, str) else None
    return bool(
        parsed is not None
        and parsed.scheme == "https"
        and parsed.hostname == "electionresults.utah.gov"
        and parsed.path.startswith("/cdn/results/" + JURISDICTION_ID + "/")
        and parsed.path.lower().endswith(".pdf")
    )


def _county(template):
    source_id = template.get("source", {}).get("id")
    matches = [
        county for county, declaration in REPORTS.items()
        if declaration["source_id"] == source_id
    ]
    return matches[0] if len(matches) == 1 else None


def _identity(template):
    return {
        "id": template["id"],
        "election": template["election"],
        "geography": template["geography"],
        "measure": template["measure"],
        "source_id": template["source"]["id"],
        "denominator": template["denominator"],
        "maps_approved": template["view"]["maps_approved"],
        "reporting_complete": template["reporting_status"]["complete"],
    }


def _inventory(templates, identity=False):
    rows = [_identity(row) if identity else row for row in templates]
    return digest(encoded(sorted(rows, key=lambda row: row["id"])))


def _route_contract(template):
    county = _county(template)
    source = template.get("source", {})
    view = template.get("view", {})
    if (
        county is None
        or template.get("contract") != "participation.observation.v1"
        or template.get("geography", {}).get("state_code") != "UT"
        or template.get("geography", {}).get("level") != "county"
        or template.get("geography", {}).get("name") != county
        or template.get("election") != {
            "date": "2026-11-03",
            "id": "UT-General11032026",
            "qualification": "native",
            "type": "general",
            "year": 2026,
        }
        or template.get("measure") != MEASURE
        or template.get("denominator") is not None
        or template.get("reporting_status", {}).get("complete") is not None
        or source.get("classification") != "public_aggregate"
        or view.get("county") != county
        or view.get("maps_approved") is not True
        or view.get("denominator") is not None
        or view.get("reported_pct") is not None
        or view.get("geography_level") != "county"
        or view.get("participation_measure_kind")
            != "source_defined_participation_count"
        or view.get("source_url") != source.get("url")
        or source.get("url") != STORED_URL
        and not _official_pdf_url(source.get("url"))
    ):
        raise ValueError("Utah accepted source, identity or qualification scope changed")
    return county


def route(template):
    if _county(template) is None:
        return None
    _route_contract(template)
    return {"state": "UT", "adapter": ADAPTER, "url": API_URL}


def validate_templates(templates):
    if len(templates) != 4 or len({row["id"] for row in templates}) != 4:
        raise ValueError("The complete four-county Utah summary inventory is required")
    if _inventory(templates, identity=True) != IDENTITY_PIN:
        raise ValueError("Reviewed Utah identities or qualifications changed")
    initial = [row for row in templates if row["source"]["url"] == STORED_URL]
    if initial and (len(initial) != 4 or _inventory(initial) != INITIAL_FULL_PIN):
        raise ValueError("Initial frozen reviewed Utah templates changed")
    seen = set()
    for template in templates:
        county = _route_contract(template)
        if county in seen:
            raise ValueError("Duplicate reviewed Utah county identity")
        seen.add(county)
        view = template["view"]
        native = view.get("native_record") or {}
        if template["source"]["url"] == STORED_URL:
            if (
                native.get("source_url") != REPORTS[county].get("accepted_url")
                or native.get("native_reported_total")
                    != str(template["count"]["value"])
                or native.get("source_counting_complete") is not None
                or template["source_clock"].get("timezone") is not None
            ):
                raise ValueError("Initial Utah native count or clock hold changed")
            continue
        query = native.get("query") or {}
        source_pin = native.get("source_original_pin")
        if (
            source_pin != {
                "url": template["source"]["url"],
                "bytes": source_pin.get("bytes") if isinstance(source_pin, dict) else None,
                "sha256": template["source"].get("input_sha256"),
            }
            or template["source"].get("selector", {}).get("native_refresh") != native
            or query.get("county") != county
            or query.get("ballots_cast") != template["count"]["value"]
            or query.get("source_url") != template["source"]["url"]
            or query.get("source_pin") != source_pin
            or query.get("source_clock") != template["source_clock"]["literal"]
            or query.get("pdf_report_timezone_literal") is not None
            or native.get("pdf_report_timezone_literal") is not None
            or native.get("native_reporting_complete_qualified") is not False
            or native.get("maps_approved") is not True
            or native.get("candidate_votes_not_used_as_ballots") is not True
            or native.get("analytical_rates_promoted") is not False
            or view.get("ballots") != template["count"]["value"]
            or view.get("source_update_label") != template["source_clock"]["literal"]
            or template["source_clock"]["timezone"] is not None
        ):
            raise ValueError("Projected Utah source, count, clock or qualification vector differs")
    if seen != set(REPORTS):
        raise ValueError("Reviewed Utah county inventory changed")


def validate_plan(plan):
    selected = [
        source for source in plan.get("UT", {}).values()
        if source["adapter"] == ADAPTER
    ]
    if not selected:
        return plan
    if len(selected) != 1:
        raise ValueError("Exactly one complete reviewed Utah source is required")
    validate_templates(selected[0]["templates"])
    return plan


def _report_declarations(document):
    jurisdiction = document.get("jurisdiction")
    election = document.get("election")
    if (
        not isinstance(jurisdiction, dict)
        or not isinstance(election, dict)
        or jurisdiction.get("id") != JURISDICTION_ID
        or _english(jurisdiction.get("name"), "jurisdiction name") != "Utah"
        or election.get("id") != ELECTION_ID
        or election.get("jurisdictionId") != JURISDICTION_ID
        or election.get("electionDate") != "2026-11-03"
        or _english(election.get("name"), "election name") != "2026 General Election"
        or election.get("isPrimary") is not False
        or election.get("isProduction") is not True
        or type(election.get("isOfficialResults")) is not bool
    ):
        raise ValueError("Changed Utah 2026 general-election declaration")
    api_as_of = election.get("asOf")
    api_last_updated = election.get("lastUpdated")
    _utc_clock(api_as_of, "API as-of clock")
    _utc_clock(api_last_updated, "API last-updated clock")
    categories = election.get("publicReportCategories")
    if not isinstance(categories, list):
        raise ValueError("Missing Utah official report declarations")
    categories = [
        row for row in categories
        if isinstance(row, dict) and row.get("categoryName") == "Official Summary Results"
    ]
    if len(categories) != 1 or not isinstance(categories[0].get("reports"), list):
        raise ValueError("Changed Utah official summary report category")
    expected_names = {
        declaration["report_name"]: county
        for county, declaration in REPORTS.items()
    }
    found = {}
    for report in categories[0]["reports"]:
        if not isinstance(report, dict) or report.get("reportName") not in expected_names:
            continue
        county = expected_names[report["reportName"]]
        if county in found or report.get("county") != county:
            raise ValueError("Duplicate or changed Utah official summary identity")
        blob = report.get("blobName")
        versions = report.get("versions")
        if (
            not isinstance(blob, str)
            or not blob.lower().endswith(".pdf")
            or not isinstance(versions, list)
        ):
            raise ValueError("Missing Utah official summary PDF declaration")
        current = [
            row for row in versions
            if isinstance(row, dict)
            and row.get("blobName") == blob
            and row.get("reportName") == report["reportName"]
        ]
        if len(current) != 1:
            raise ValueError("Utah current official summary version is ambiguous")
        version = current[0]
        upload = version.get("uploadDate")
        _upload_clock(upload)
        status = version.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("Missing Utah official summary version status")
        url = CDN_ROOT + quote(blob, safe="()")
        if not _official_pdf_url(url):
            raise ValueError("Changed Utah official summary PDF authority")
        found[county] = {
            "county": county,
            "report_name": report["reportName"],
            "blob_name": blob,
            "source_url": url,
            "upload_date": upload,
            "version_status": status,
        }
    if set(found) != set(REPORTS):
        raise ValueError("Incomplete Utah four-county official summary declarations")
    return {
        "api_as_of": api_as_of,
        "api_last_updated": api_last_updated,
        "api_is_official_results": election["isOfficialResults"],
        "reports": found,
    }


def _summary_values(text, county):
    compact = re.sub(r"\s+", "", text)
    if (
        "GeneralElection" not in compact
        or "November3,2026" not in compact
        or county.replace(" ", "") + ",Utah" not in compact
    ):
        raise ValueError("Changed Utah summary election or county identity")
    lines = [re.sub(r"\s+", "", line) for line in text.splitlines() if line.strip()]

    def field(pattern, label):
        found = [match for line in lines if (match := re.fullmatch(pattern, line))]
        if len(found) != 1:
            raise ValueError("Missing or ambiguous Utah " + label)
        return found[0]

    count = field(r"BallotsCast-Total([0-9][0-9,]*)", "ballots total")
    registered = field(
        r"RegisteredVoters-Total([0-9][0-9,]*)", "registration context")
    fraction = field(
        r"VoterTurnout-Total([0-9]+(?:\.[0-9]+)?)%", "display fraction")
    clock = re.search(
        r"ElectionSummary-"
        r"((?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/20[0-9]{2})"
        r"((?:0[1-9]|1[0-2]):[0-5][0-9](?:AM|PM))",
        compact,
    )
    if clock is None:
        raise ValueError("Missing Utah native summary count, clock or display fraction")
    expected_status = REPORTS[county]["status"]
    compact_status = expected_status.replace(" ", "")
    if not any(
        line in {compact_status, "SummaryResultsReport" + compact_status}
        for line in lines
    ):
        raise ValueError("Utah native summary result status regressed")
    result = {
        "ballots_cast": _integer(int(count.group(1).replace(",", "")), "ballots cast"),
        "registered_voters": _integer(
            int(registered.group(1).replace(",", "")), "registered voters"),
        "native_fraction_literal": fraction.group(1) + "%",
        "native_report_status_literal": expected_status,
        "source_clock": clock.group(1) + " " + clock.group(2),
        "pdf_report_timezone_literal": None,
    }
    _local_clock(result["source_clock"])
    if result["ballots_cast"] > result["registered_voters"]:
        raise ValueError("Utah native ballots exceed the displayed registration context")
    return result


def _text_views(body):
    import fitz
    import pdfplumber

    try:
        with fitz.open(stream=body, filetype="pdf") as document:
            if document.page_count < 1:
                raise ValueError("Empty Utah official summary PDF")
            page = document[0]
            fitz_text = page.get_text()
            words = page.get_text("words")
            grouped = []
            for word in words:
                center = (word[1] + word[3]) / 2
                height = word[3] - word[1]
                matching = [
                    row for row in grouped
                    if abs(row["center"] - center)
                        <= 0.4 * min(row["height"], height)
                ]
                row = min(
                    matching,
                    key=lambda item: abs(item["center"] - center),
                    default=None,
                )
                if row is None:
                    row = {"center": center, "height": height, "words": []}
                    grouped.append(row)
                row["words"].append(word)
            fitz_physical = "\n".join(
                " ".join(
                    word[4] for word in sorted(row["words"], key=lambda word: word[0])
                )
                for row in sorted(grouped, key=lambda row: row["center"])
            )
        with pdfplumber.open(io.BytesIO(body)) as document:
            if not document.pages:
                raise ValueError("Empty Utah independent PDF view")
            plumber_text = document.pages[0].extract_text() or ""
    except Exception as error:
        raise ValueError("Unreadable Utah official summary PDF") from error
    if "Ballots Cast" in fitz_text and "Ballots Cast" in plumber_text:
        return [
            {
                "text": fitz_physical,
                "receipt": {
                    "engine": "PyMuPDF",
                    "version": fitz.VersionBind,
                    "page": 1,
                    "mode": "embedded_text",
                },
            },
            {
                "text": plumber_text,
                "receipt": {
                    "engine": "pdfplumber",
                    "version": pdfplumber.__version__,
                    "page": 1,
                    "mode": "embedded_text",
                },
            },
        ]
    from scripts.results_pdf_ocr import first_page_views
    return first_page_views(body)


def _summary(body, county):
    views = _text_views(body)
    if len(views) != 2:
        raise ValueError("Utah summary requires two independent first-page reads")
    parsed = [_summary_values(view["text"], county) for view in views]
    if parsed[0] != parsed[1]:
        raise ValueError("Utah independent summary reads disagree")
    count_confidence = []
    for view in views:
        if "confidence" not in view:
            continue
        lines = view["text"].splitlines()
        matching = [
            index for index, line in enumerate(lines)
            if "BallotsCast-Total" in re.sub(r"\s+", "", line)
        ]
        if len(matching) != 1:
            raise ValueError("Utah OCR ballots row is ambiguous")
        count_confidence.append(view["confidence"][matching[0]])
    if count_confidence and min(count_confidence) < 0.98:
        raise ValueError("Utah OCR selected count confidence requires review")
    return {
        **parsed[0],
        "extraction_receipts": [view["receipt"] for view in views],
        "selected_count_minimum_confidence": (
            min(count_confidence) if count_confidence else None),
    }


def _prior_success(prior, templates):
    if prior is None:
        return None
    data = prior.get("data") if isinstance(prior, dict) else None
    source = prior.get("source") if isinstance(prior, dict) else None
    if data is None and source is None:
        return None
    expected_data_fields = {
        "updates", "complete_native_query", "numerical_input_pins",
        "source_url", "declared_entry_url", "geographic_joins_changed",
        "analytical_rates_promoted", "new_count_identities_added",
        "candidate_votes_used_as_ballots",
    }
    if (
        not isinstance(data, dict)
        or set(data) != expected_data_fields
        or not isinstance(source, dict)
        or set(source) != {"url", "bytes", "sha256"}
        or source.get("url") != API_URL
        or not isinstance(source.get("bytes"), int)
        or source["bytes"] < 1
        or re.fullmatch(r"[a-f0-9]{64}", source.get("sha256", "")) is None
        or data.get("source_url") != API_URL
        or data.get("declared_entry_url") != ENTRY_URL
        or data.get("geographic_joins_changed") is not False
        or data.get("analytical_rates_promoted") is not False
        or data.get("new_count_identities_added") is not False
        or data.get("candidate_votes_used_as_ballots") is not False
    ):
        raise ValueError("Prior Utah captured source declaration is incomplete")
    queries = data.get("complete_native_query")
    updates = data.get("updates")
    numerical_pins = data.get("numerical_input_pins")
    if (
        not isinstance(queries, list)
        or len(queries) != 1
        or not isinstance(updates, list)
        or len(updates) != 4
        or not isinstance(numerical_pins, dict)
        or set(numerical_pins) != {
            "data_api", *{"summary_" + county.lower().replace(" County", "")
                           for county in REPORTS}
        }
    ):
        raise ValueError("Prior Utah full query/update vector is incomplete")
    query = queries[0]
    source_pin = {"bytes": source["bytes"], "sha256": source["sha256"]}
    if (
        not isinstance(query, dict)
        or set(query) != {
            "contract", "source_url", "source_pin", "declared_entry_url",
            "api_as_of", "api_last_updated", "api_is_official_results",
            "report_records", "reconciliation",
        }
        or query.get("contract") != "participation.utah_official_summary_query.v1"
        or query.get("source_url") != API_URL
        or query.get("source_pin") != source_pin
        or query.get("declared_entry_url") != ENTRY_URL
        or numerical_pins.get("data_api") != {"url": API_URL, **source_pin}
        or type(query.get("api_is_official_results")) is not bool
    ):
        raise ValueError("Prior Utah source pin or query declaration changed")
    _utc_clock(query.get("api_as_of"), "prior API as-of clock")
    _utc_clock(query.get("api_last_updated"), "prior API last-updated clock")
    expected = {_county(row): row for row in templates}
    records = {}
    record_fields = {
        "county", "report_name", "blob_name", "source_url", "source_pin",
        "upload_date", "version_status", "ballots_cast", "registered_voters",
        "native_fraction_literal", "native_report_status_literal",
        "source_clock", "pdf_report_timezone_literal", "extraction_receipts",
        "selected_count_minimum_confidence",
    }
    for row in query.get("report_records", []):
        county = row.get("county") if isinstance(row, dict) else None
        input_name = (
            "summary_" + county.lower().replace(" County", "")
            if isinstance(county, str) else None
        )
        if (
            not isinstance(row, dict)
            or set(row) != record_fields
            or county in records
            or county not in expected
            or row.get("report_name") != REPORTS[county]["report_name"]
            or row.get("native_report_status_literal") != REPORTS[county]["status"]
            or row.get("pdf_report_timezone_literal") is not None
            or row.get("source_pin") != numerical_pins.get(input_name)
            or row.get("source_url") != row["source_pin"].get("url")
            or not _official_pdf_url(row.get("source_url"))
        ):
            raise ValueError("Prior Utah official report vector changed")
        _integer(row.get("ballots_cast"), "prior ballots cast")
        _integer(row.get("registered_voters"), "prior registered voters")
        _local_clock(row.get("source_clock"))
        _upload_clock(row.get("upload_date"))
        if (
            not isinstance(row.get("native_fraction_literal"), str)
            or re.fullmatch(
                r"[0-9]+(?:\.[0-9]+)?%", row["native_fraction_literal"]) is None
            or not isinstance(row.get("extraction_receipts"), list)
            or len(row["extraction_receipts"]) != 2
        ):
            raise ValueError("Prior Utah summary display facts changed")
        records[county] = row
    if set(records) != set(expected):
        raise ValueError("Prior Utah official report inventory changed")
    expected_updates = {row["id"]: row for row in templates}
    seen_updates = {}
    for update in updates:
        if (
            not isinstance(update, dict)
            or set(update) != {
                "id", "value", "native", "registered", "clock",
                "reported_units", "total_units", "rate_compatible", "source_input",
            }
            or update.get("id") in seen_updates
            or update.get("id") not in expected_updates
        ):
            raise ValueError("Prior Utah update inventory changed")
        template = expected_updates[update["id"]]
        county = _county(template)
        row = records[county]
        input_name = "summary_" + county.lower().replace(" County", "")
        native = update.get("native")
        if (
            not isinstance(native, dict)
            or native.get("query") != row
            or native.get("county") != county
            or native.get("source_input") != input_name
            or native.get("source_original_pin") != row["source_pin"]
            or native.get("native_report_status_literal")
                != row["native_report_status_literal"]
            or native.get("native_fraction_literal")
                != row["native_fraction_literal"]
            or native.get("pdf_report_timezone_literal") is not None
            or native.get("native_reporting_complete_qualified") is not False
            or update["value"] != row["ballots_cast"]
            or update["registered"] is not None
            or update["clock"] != row["source_clock"]
            or update["reported_units"] is not None
            or update["total_units"] is not None
            or update["rate_compatible"] is not False
            or update["source_input"] != input_name
        ):
            raise ValueError("Prior Utah pin/query/update consistency changed")
        seen_updates[update["id"]] = update
    if set(seen_updates) != set(expected_updates):
        raise ValueError("Prior Utah update inventory changed")
    reconciliation = query.get("reconciliation")
    if reconciliation != {
        "selected_counties": 4,
        "native_total_ballots_sum": sum(
            row["ballots_cast"] for row in records.values()),
        "candidate_votes_used_as_ballots": False,
        "denominators_or_rates_promoted": False,
        "state_parent_derived_from_county_sum": False,
        "counting_completion_certified": False,
    }:
        raise ValueError("Prior Utah complete reconciliation changed")
    return {
        "api_as_of": query["api_as_of"],
        "api_last_updated": query["api_last_updated"],
        "records": records,
    }


def statistics(body, templates, url, *, acquire, prior=None):
    if url != API_URL:
        raise ValueError("Unreviewed Utah native product")
    validate_templates(templates)
    prior_success = _prior_success(prior, templates)
    try:
        document = json.loads(body, object_pairs_hook=_object)
    except Exception as error:
        raise ValueError("Malformed Utah native JSON") from error
    if not isinstance(document, dict):
        raise ValueError("Changed Utah native JSON envelope")
    declarations = _report_declarations(document)
    if prior_success is not None:
        if (
            _utc_clock(declarations["api_as_of"], "API as-of clock")
                < _utc_clock(prior_success["api_as_of"], "prior API as-of clock")
            or _utc_clock(declarations["api_last_updated"], "API last-updated clock")
                < _utc_clock(
                    prior_success["api_last_updated"],
                    "prior API last-updated clock",
                )
        ):
            raise ValueError("Utah API source clock regressed from prior capture")
    expected = {_county(row): row for row in templates}
    records = {}
    numerical_pins = {"data_api": {"url": API_URL, **pin(body)}}
    for county in sorted(REPORTS):
        declaration = declarations["reports"][county]
        pdf, _receipt = acquire(declaration["source_url"])
        facts = _summary(pdf, county)
        source_pin = {"url": declaration["source_url"], **pin(pdf)}
        input_name = "summary_" + county.lower().replace(" County", "")
        numerical_pins[input_name] = source_pin
        row = {
            **declaration,
            "source_pin": source_pin,
            **facts,
        }
        template = expected[county]
        if _local_clock(row["source_clock"]) < _local_clock(
                template["source_clock"]["literal"]):
            raise ValueError("Utah native summary clock regressed from frozen registration")
        if prior_success is not None:
            previous = prior_success["records"][county]
            if (
                _local_clock(row["source_clock"])
                    < _local_clock(previous["source_clock"])
                or _upload_clock(row["upload_date"])
                    < _upload_clock(previous["upload_date"])
            ):
                raise ValueError("Utah native summary clock regressed from prior capture")
            if (
                previous["native_report_status_literal"] == REPORTS[county]["status"]
                and row["native_report_status_literal"] != REPORTS[county]["status"]
            ):
                raise ValueError("Utah native summary status regressed from prior capture")
        records[county] = row
    updates = []
    for county, template in sorted(expected.items(), key=lambda item: item[1]["id"]):
        row = records[county]
        input_name = "summary_" + county.lower().replace(" County", "")
        native = copy.deepcopy(template["view"]["native_record"])
        native.update(
            contract="participation.utah_official_summary_refresh.v1",
            native_kind="county_official_summary",
            county=county,
            report_name=row["report_name"],
            source_input=input_name,
            source_original_pin=row["source_pin"],
            native_report_status_literal=row["native_report_status_literal"],
            native_fraction_literal=row["native_fraction_literal"],
            pdf_report_timezone_literal=None,
            native_reporting_complete_qualified=False,
            maps_approved=template["view"]["maps_approved"],
            candidate_votes_not_used_as_ballots=True,
            analytical_rates_promoted=False,
            state_parent_derived_from_county_sum=False,
            query=copy.deepcopy(row),
        )
        updates.append({
            "id": template["id"],
            "value": row["ballots_cast"],
            "native": native,
            "registered": None,
            "clock": row["source_clock"],
            "reported_units": None,
            "total_units": None,
            "rate_compatible": False,
            "source_input": input_name,
        })
    ordered = [copy.deepcopy(records[county]) for county in sorted(records)]
    return {
        "updates": updates,
        "complete_native_query": [{
            "contract": "participation.utah_official_summary_query.v1",
            "source_url": API_URL,
            "source_pin": pin(body),
            "declared_entry_url": ENTRY_URL,
            "api_as_of": declarations["api_as_of"],
            "api_last_updated": declarations["api_last_updated"],
            "api_is_official_results": declarations["api_is_official_results"],
            "report_records": ordered,
            "reconciliation": {
                "selected_counties": len(ordered),
                "native_total_ballots_sum": sum(
                    row["ballots_cast"] for row in ordered),
                "candidate_votes_used_as_ballots": False,
                "denominators_or_rates_promoted": False,
                "state_parent_derived_from_county_sum": False,
                "counting_completion_certified": False,
            },
        }],
        "numerical_input_pins": numerical_pins,
        "source_url": API_URL,
        "declared_entry_url": ENTRY_URL,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "new_count_identities_added": False,
        "candidate_votes_used_as_ballots": False,
    }
