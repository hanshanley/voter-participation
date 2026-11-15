"""Refresh Cass County, Indiana's native turnout-display numerator."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import io
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change


URL = (
    "https://www.in.gov/counties/cass/departments/clerk/"
    "UNOFFICIAL%20Cumulative%20Results-11-3-2026%2007-59-37%20PM-FINAL.pdf"
    "?language_id=1"
)
QUALIFICATION_SOURCE = {
    "bytes": 291064,
    "sha256": "ed11b24aa9b36e2cc5a8bf7e940d71feb293d497e12e5632915baede7d5c4f4b",
}
TARGET_ID = "66f08ea007705c35d64589a55b610e59"
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Native turnout numerator (not cast ballots)",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
PROFILES = {
    URL: {
        "state": "IN",
        "target_id": TARGET_ID,
        "county": "Cass County",
        "native_county": "Cass",
        "county_id": "additional:IN:18017",
        "geography_id": "IN|additional:IN:18017|",
        "election": {"year": 2026, "type": "general"},
        "election_identity": "CASS COUNTY 2026 General, 11/3/2026",
        "min_pages": 1,
        "max_pages": 200,
    },
}
INTEGER = r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
PERCENT = r"(?:0|[1-9][0-9]?|100)\.[0-9]{2}%"
FRACTION = re.compile(
    rf"(?P<numerator>{INTEGER}) of (?P<denominator>{INTEGER}) = (?P<percent>{PERCENT})"
)
TABLE_COLUMNS = (
    "Choice",
    "Party",
    "Absentee Voting",
    "Early Voting",
    "Election Day Voting",
    "Total",
)
STATUS = "Unofficial Results; OFFICIAL 2026 GENERAL"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value):
    _require(isinstance(value, str) and re.fullmatch(INTEGER, value) is not None,
             "A complete Cass native integer literal is required")
    return int(value.replace(",", ""))


def _clock(value):
    try:
        return datetime.strptime(" ".join(value.split()), "%m/%d/%Y %I:%M %p")
    except (TypeError, ValueError) as error:
        raise ValueError("Cass native printed clock changed") from error


def _source_pin(source_pin):
    _require(
        isinstance(source_pin, dict)
        and type(source_pin.get("bytes")) is int
        and source_pin["bytes"] >= 0
        and isinstance(source_pin.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", source_pin["sha256"]) is not None,
        "A complete source pin is required",
    )
    return {"bytes": source_pin["bytes"], "sha256": source_pin["sha256"]}


def _lines(text):
    _require(isinstance(text, str), "Cass PDF page text is absent")
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _fraction(literal, role):
    match = FRACTION.fullmatch(literal)
    _require(match is not None, f"Cass native {role} display changed")
    numerator = _integer(match["numerator"])
    denominator = _integer(match["denominator"])
    _require(denominator > 0 and numerator <= denominator,
             f"Cass native {role} fraction is out of scope")
    expected = (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    printed = Decimal(match["percent"][:-1])
    _require(printed == expected, f"Cass native {role} percentage disagrees")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent_literal": match["percent"],
        "display": literal,
    }


def factual_query_from_pages(page_texts, source_pin, profile=None):
    """Build the complete selected query from already decoded PDF page text."""
    profile = profile or PROFILES[URL]
    pages = tuple(page_texts)
    _require(profile["min_pages"] <= len(pages) <= profile["max_pages"],
             "Cass native page inventory changed")
    source_pin = _source_pin(source_pin)
    common = None
    contexts = []
    for page_number, text in enumerate(pages, 1):
        lines = _lines(text)
        _require(len(lines) > 21, "Cass native cumulative-results page is incomplete")
        _require(lines[:4] == [
            "Cumulative Results Report",
            "OFFICIAL 2026 GENERAL",
            "Run Time",
            "Run Date",
        ], "Cass PDF report type or election declaration changed")
        _clock(f"{lines[5]} {lines[4]}")
        _require(lines[5] == "11/03/2026"
                 and lines[6] == "CASS COUNTY"
                 and lines[7] == "2026 General"
                 and lines[8] == "11/3/2026",
                 "Cass PDF election, county or scope changed")
        _require(lines[9] == f"Page {page_number}",
                 "Cass native page sequence changed")
        _require(lines[10:12] == ["Unofficial Results", "Registered Voters"],
                 "Cass native status or selected measure label changed")
        turnout = _fraction(lines[12], "turnout")
        _require(lines[13] == "Precincts Reporting",
                 "Cass native reporting-scope label changed")
        precincts = _fraction(lines[14], "precinct reporting")
        _require(tuple(lines[16:22]) == TABLE_COLUMNS,
                 "Cass contest columns changed")
        _require(lines.count("Registered Voters") == 1
                 and lines.count("Precincts Reporting") == 1,
                 "Cass native selected display is absent or ambiguous")
        facts = {
            "source_clock": f"{lines[5]} {lines[4]}",
            "turnout": turnout,
            "precincts": precincts,
        }
        if common is None:
            common = facts
        _require(facts == common,
                 "Cass PDF pages do not form one cumulative report edition")
        contexts.append({"page": page_number, "first_contest_context": lines[15]})
    return {
        "contract": "participation.cass_in_native_turnout_display.v1",
        "source": {"url": URL, **source_pin},
        "qualification_source": QUALIFICATION_SOURCE,
        "election": profile["election"],
        "election_identity": profile["election_identity"],
        "county": profile["county"],
        "native_county": profile["native_county"],
        "county_id": profile["county_id"],
        "measure_literal": "Registered Voters",
        "native_count": common["turnout"]["numerator"],
        "native_display_reference": common["turnout"]["denominator"],
        "native_turnout_display": common["turnout"]["display"],
        "printed_percentage": common["turnout"]["percent_literal"],
        "reported_precincts": common["precincts"]["numerator"],
        "total_precincts": common["precincts"]["denominator"],
        "native_precincts_display": common["precincts"]["display"],
        "source_clock": common["source_clock"],
        "source_clock_timezone": None,
        "source_clock_qualification": "native_printed_clock_timezone_not_supplied",
        "native_report_status_literals": [
            "Unofficial Results",
            "OFFICIAL 2026 GENERAL",
        ],
        "native_report_status_literal": STATUS,
        "scope": "county cumulative report",
        "page_count": len(pages),
        "pages": contexts,
        "candidate_and_contest_totals_not_selected": True,
        "native_display_reference_is_not_a_qualified_denominator": True,
        "filename_final_is_not_completion_or_certification": True,
        "automatic_geographic_or_rate_qualification": False,
    }


def factual_query(body, url=URL):
    if url not in PROFILES:
        raise ValueError("Unreviewed Cass cumulative-results source")
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    _require(not reader.is_encrypted, "Encrypted Cass statistical PDF")
    profile = PROFILES[url]
    _require(profile["min_pages"] <= len(reader.pages) <= profile["max_pages"],
             "Cass native page inventory changed")
    title = (reader.metadata or {}).get("/Title")
    _require(title in (None, "Count_CumulativeReport"),
             "Cass PDF product metadata changed")
    pages = (page.extract_text() for page in reader.pages)
    return factual_query_from_pages(pages, pin(body), profile)


def _source_bound(template):
    source = template.get("source") or {}
    view = template.get("view") or {}
    fields = source.get("fields") or {}
    return URL in {source.get("url"), view.get("source_url"), fields.get("source_url")}


def _template_clock(template):
    literal = (template.get("source_clock") or {}).get("literal")
    _require(isinstance(literal, str), "Accepted Cass source clock is absent")
    return _clock(literal)


def statistics(body, templates, url=URL):
    if url not in PROFILES:
        raise ValueError("Unreviewed Cass cumulative-results source")
    profile = PROFILES[url]
    query = factual_query(body, url)
    _require(len(templates) == 1, "Accepted Cass template inventory changed")
    template = templates[0]
    geography = template.get("geography") or {}
    election = template.get("election") or {}
    view = template.get("view") or {}
    native = view.get("native_record") or {}
    _require(
        template.get("id") == profile["target_id"]
        and _source_bound(template)
        and geography.get("state_code") == profile["state"]
        and geography.get("level") == "county"
        and geography.get("name") == profile["county"]
        and geography.get("id") == profile["geography_id"]
        and view.get("county_id") == profile["county_id"]
        and view.get("county") == profile["county"]
        and all(election.get(key) == value for key, value in profile["election"].items())
        and template.get("measure") == MEASURE
        and template.get("denominator") is None
        and (template.get("count") or {}).get("status") == "reported"
        and view.get("selected_source_kind") == "native_turnout_numerator"
        and view.get("cast_ballot_count_qualified") is False
        and view.get("unique_voter_count_qualified") is False
        and native.get("county") == profile["native_county"]
        and native.get("measure_literal") == "Registered Voters",
        "Accepted Cass target, parent, measure or qualification changed",
    )
    _require(_clock(query["source_clock"]) >= _template_clock(template),
             "Cass native printed source clock regressed")
    selected_query = {
        key: query[key]
        for key in (
            "county",
            "native_county",
            "county_id",
            "election_identity",
            "measure_literal",
            "native_count",
            "native_display_reference",
            "native_turnout_display",
            "printed_percentage",
            "reported_precincts",
            "total_precincts",
            "native_precincts_display",
            "source_clock",
            "source_clock_timezone",
            "native_report_status_literals",
            "native_report_status_literal",
            "scope",
            "page_count",
        )
    }
    native_record = {
        "query": selected_query,
        "county": profile["native_county"],
        "election_identity": query["election_identity"],
        "measure_literal": query["measure_literal"],
        "native_count": query["native_count"],
        "native_display_reference": query["native_display_reference"],
        "native_turnout_display": query["native_turnout_display"],
        "printed_percentage": query["printed_percentage"],
        "scope": query["scope"],
        "native_reporting_and_status_notes": [
            f"{query['reported_precincts']} of {query['total_precincts']} precincts reporting.",
            "The report simultaneously prints Unofficial Results and OFFICIAL 2026 GENERAL.",
            "The numerator is accepted only in its native turnout-display role.",
            "No claim of ballots cast, unique voters, certification, or final completion.",
            "Timezone remains unknown.",
        ],
        "native_report_status_literal": query["native_report_status_literal"],
        "native_reporting_complete_qualified": False,
        "source_clock_timezone_not_supplied": True,
        "native_display_reference_is_not_a_qualified_denominator": True,
        "candidate_and_contest_totals_not_selected": True,
        "filename_final_is_not_completion_or_certification": True,
        "geographic_join_changed": False,
    }
    update = change(
        template,
        query["native_count"],
        native_record,
        registered=None,
        clock=query["source_clock"],
        reported=query["reported_precincts"],
        total=query["total_precincts"],
        rate_compatible=False,
    )
    return {
        "updates": [update],
        "complete_native_query": query,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "county_parent_updated": True,
        "statewide_statistics_context_updated": False,
        "candidate_and_contest_totals_not_selected": True,
        "native_nulls_and_zeros_preserved": True,
        "numerical_data_qualified": True,
    }
