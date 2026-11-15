"""Refresh Jefferson County, Kentucky precinct ballot statistics by literal unit."""

from datetime import datetime
import hashlib
import io
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change


URL = (
    "https://www.jeffersoncountyclerk.org/files/assets/clerk/v/1/elections/"
    "documents/26general_precinct2.pdf"
)
QUALIFICATION_SOURCE = {
    "bytes": 12645299,
    "sha256": "6cd6bcb2b677e5ce72e765ae5b2688909eac19d922010e31119fc83b729d0fbe",
}
MODES = (
    "TOTAL", "Election Day", "Mail", "Walk-in Excuse", "Walk-in Early", "Provisional",
)
MEASURE = {
    "id": "native-ballots-cast-total",
    "kind": "ballots_cast",
    "literal": "Ballots Cast - Total",
    "mode": "source_defined",
    "unit": "ballots",
}
PREFIX = (
    "Summary Results Report",
    "2026 General Election",
    "November 3, 2026",
    "UNOFFICIAL RESULTS",
    "Jefferson County",
)
STATISTICS_HEADER = (
    "Statistics TOTAL Election",
    "Day",
    "Mail Walk-in",
    "Excuse",
    "Walk-in",
    "Early",
    "Provision",
    "al",
)
PROFILES = {
    URL: {
        "state": "KY",
        "expected_pages": 4773,
        "expected_units": 646,
        "election": {"date": "2026-11-03", "year": 2026, "type": "general"},
        "native_report_status_literal": "UNOFFICIAL RESULTS",
    },
}
INTEGER = re.compile(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)")
FOOTER = re.compile(
    r"Precinct Summary - (?P<clock>.+?)\s+"
    r"(?P<page>[0-9,]+) of (?P<pages>[0-9,]+)(?:\n|$)"
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value):
    _require(isinstance(value, str) and INTEGER.fullmatch(value) is not None,
             "A complete native integer literal is required")
    return int(value.replace(",", ""))


def _clock(value):
    try:
        return datetime.strptime(" ".join(value.split()), "%m/%d/%Y %I:%M %p")
    except (TypeError, ValueError) as error:
        raise ValueError("Jefferson native printed clock changed") from error


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _mode_row(line, label):
    match = re.fullmatch(
        re.escape(label) + r" ((?:" + INTEGER.pattern + r")(?: " + INTEGER.pattern + r"){5})",
        line,
    )
    _require(match is not None, "Jefferson native participation row changed")
    literals = match[1].split()
    values = [_integer(value) for value in literals]
    _require(values[0] == sum(values[1:]),
             "Jefferson native ballot modes do not reconcile")
    return {
        mode: {"value": value, "literal": literal}
        for mode, value, literal in zip(MODES, values, literals)
    }


def _statistics(lines):
    if len(lines) <= 6 or not lines[6].startswith("Statistics"):
        _require(not any(line.startswith("Statistics") for line in lines[7:]),
                 "Jefferson statistics block moved inside a contest page")
        return None, lines[6] if len(lines) > 6 else None
    _require(tuple(lines[6:14]) == STATISTICS_HEADER,
             "Jefferson native statistics columns changed")
    _require(len(lines) > 16, "Jefferson native statistics page is incomplete")
    total = _mode_row(lines[14], "Ballots Cast - Total")
    blank = _mode_row(lines[15], "Ballots Cast - Blank")
    _require(all(blank[mode]["value"] <= total[mode]["value"] for mode in MODES),
             "Jefferson native blank ballots exceed cast ballots")
    return {
        "Ballots Cast - Total": total,
        "Ballots Cast - Blank": blank,
    }, lines[16]


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


def factual_query_from_pages(page_texts, source_pin, profile=None):
    """Build the complete numerical query from already decoded PDF page text."""
    profile = profile or PROFILES[URL]
    expected_pages = profile["expected_pages"]
    expected_units = profile["expected_units"]
    source_pin = _source_pin(source_pin)
    runs, by_unit, seen_units = [], {}, set()
    printed_clock = None
    page_count = 0
    for page_number, text in enumerate(page_texts, 1):
        page_count = page_number
        lines = _lines(text)
        _require(tuple(lines[:5]) == PREFIX,
                 "Jefferson PDF election, status or county declaration changed")
        _require(len(lines) > 6, "Jefferson PDF page lacks a literal reporting unit")
        unit = lines[5]
        footer = list(FOOTER.finditer(text))
        _require(len(footer) == 1, "Jefferson printed report clock/page is absent or ambiguous")
        footer = footer[0]
        _require(
            _integer(footer["page"]) == page_number
            and _integer(footer["pages"]) == expected_pages,
            "Jefferson native page sequence changed",
        )
        literal_clock = footer["clock"]
        _clock(literal_clock)
        if printed_clock is None:
            printed_clock = literal_clock
        _require(literal_clock == printed_clock,
                 "Jefferson native page clocks do not form one source edition")
        values, context = _statistics(lines)
        _require(isinstance(context, str) and context,
                 "Jefferson page lacks a distinct native report context")
        if not runs or runs[-1]["native_unit"] != unit:
            _require(unit not in seen_units,
                     "Jefferson literal reporting unit appears in multiple page groups")
            seen_units.add(unit)
            run = {
                "native_unit": unit,
                "source_page": page_number,
                "last_source_page": page_number,
                "source_pages": 1,
                "context_rows": [],
                "measures": None,
            }
            runs.append(run)
            by_unit[unit] = run
        else:
            run = runs[-1]
            run["last_source_page"] = page_number
            run["source_pages"] += 1
        if values is not None:
            _require(run["measures"] is None,
                     "Jefferson reporting unit has a changed duplicate statistical vector")
            _require(page_number == run["source_page"],
                     "Jefferson participation statistics moved outside the unit's first page")
            run["measures"] = values
        run["context_rows"].append(context)
    _require(page_count == expected_pages, "Jefferson native page inventory changed")
    _require(len(runs) == expected_units and len(by_unit) == expected_units,
             "Jefferson literal reporting-unit inventory changed")
    for run in runs:
        _require(run["measures"] is not None,
                 "A Jefferson reporting-unit page group lacks native statistics")
        context_rows = run.pop("context_rows")
        run["context_count"] = len(context_rows)
        run["distinct_context_count"] = len(set(context_rows))
        run["native_context_digest"] = hashlib.sha256(
            "\n".join(
                f"{run['source_page'] + index}:{context}"
                for index, context in enumerate(context_rows)
            ).encode()
        ).hexdigest()
        roles = "\n".join(
            f"{run['source_page'] + index}:{'statistics' if index == 0 else 'contest'}"
            for index in range(run["source_pages"])
        )
        run["page_role_digest"] = hashlib.sha256(roles.encode()).hexdigest()
    return {
        "contract": "participation.jefferson_ky_precinct_statistics.v1",
        "source": {"url": URL, **source_pin},
        "qualification_source": QUALIFICATION_SOURCE,
        "election": profile["election"],
        "native_report_status_literal": profile["native_report_status_literal"],
        "source_clock": printed_clock,
        "source_clock_timezone": None,
        "source_clock_qualification": "native_printed_clock_timezone_not_supplied",
        "page_count": page_count,
        "native_unit_count": len(runs),
        "units": runs,
        "candidate_totals_not_selected": True,
        "county_parent_present_in_this_product": False,
        "native_reporting_completeness_is_certification": False,
        "automatic_geographic_or_rate_qualification": False,
    }


def factual_query(body, url=URL):
    if url not in PROFILES:
        raise ValueError("Unreviewed Jefferson precinct source")
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    _require(not reader.is_encrypted, "Encrypted Jefferson statistical PDF")
    _require(len(reader.pages) == PROFILES[url]["expected_pages"],
             "Jefferson native page inventory changed")
    pages = (page.extract_text() for page in reader.pages)
    return factual_query_from_pages(pages, pin(body), PROFILES[url])


def _source_bound(template):
    source = template.get("source") or {}
    view = template.get("view") or {}
    return (
        source.get("url") == URL
        or view.get("source_url") == URL
        or (source.get("fields") or {}).get("source_url") == URL
    )


def _template_unit(template):
    view = template.get("view") or {}
    native = view.get("native_record") or {}
    selector = (template.get("source") or {}).get("selector") or {}
    candidates = [
        (template.get("geography") or {}).get("name"),
        view.get("unit"),
        selector.get("native_unit"),
        (native.get("profile") or {}).get("native_unit"),
        (native.get("query") or {}).get("native_unit"),
    ]
    identities = {value for value in candidates if value is not None}
    _require(len(identities) == 1, "Accepted Jefferson literal unit identity changed")
    unit, = identities
    _require(isinstance(unit, str) and unit, "Accepted Jefferson unit identity is absent")
    return unit


def _template_clock(template):
    value = (template.get("source_clock") or {}).get("literal")
    _require(isinstance(value, str), "Accepted Jefferson source clock is absent")
    return _clock(value)


def statistics(body, templates, url=URL):
    if url not in PROFILES:
        raise ValueError("Unreviewed Jefferson precinct source")
    profile = PROFILES[url]
    query = factual_query(body, url)
    _require(len(templates) == profile["expected_units"],
             "Accepted Jefferson template inventory changed")
    parsed = {row["native_unit"]: row for row in query["units"]}
    accepted = {}
    for template in templates:
        geography = template.get("geography") or {}
        election = template.get("election") or {}
        _require(
            _source_bound(template)
            and geography.get("state_code") == profile["state"]
            and geography.get("level") == "reporting_unit"
            and all(election.get(key) == value
                    for key, value in profile["election"].items())
            and template.get("measure") == MEASURE
            and template.get("denominator") is None
            and (template.get("count") or {}).get("status") == "reported",
            "Accepted Jefferson template semantics changed",
        )
        unit = _template_unit(template)
        _require(unit not in accepted, "Duplicate accepted Jefferson literal unit")
        accepted[unit] = template
    _require(set(accepted) == set(parsed),
             "Jefferson source/template literal unit identities differ")
    current_clock = _clock(query["source_clock"])
    updates = []
    for unit, template in accepted.items():
        _require(current_clock >= _template_clock(template),
                 "Jefferson native printed source clock regressed")
        row = parsed[unit]
        native = {
            "query": {
                "native_unit": unit,
                "source_page": row["source_page"],
                "last_source_page": row["last_source_page"],
                "source_pages": row["source_pages"],
                "context_count": row["context_count"],
                "distinct_context_count": row["distinct_context_count"],
                "native_context_digest": row["native_context_digest"],
                "page_role_digest": row["page_role_digest"],
                "measures": row["measures"],
                "source_clock": query["source_clock"],
                "source_clock_timezone": None,
                "native_report_status_literal": query["native_report_status_literal"],
            },
            "private_original_pin": {
                "bytes": query["source"]["bytes"],
                "sha256": query["source"]["sha256"],
            },
            "native_report_status_literal": query["native_report_status_literal"],
            "native_reporting_complete_qualified": False,
            "source_clock_timezone_not_supplied": True,
            "county_parent_present_in_this_product": False,
            "county_parent_updated": False,
            "native_mail_is_not_qualified_as_returned_envelopes": True,
            "candidate_totals_not_selected": True,
            "geographic_join_changed": False,
        }
        updates.append(change(
            template,
            row["measures"]["Ballots Cast - Total"]["TOTAL"]["value"],
            native,
            registered=None,
            clock=query["source_clock"],
            reported=None,
            total=None,
            rate_compatible=False,
        ))
    return {
        "updates": updates,
        "complete_native_query": query,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
        "county_parent_updated": False,
        "native_duplicates_nulls_and_zeros_preserved": True,
        "numerical_data_qualified": True,
    }
