"""Refresh reviewed New Jersey periodic administrative PDF subtotals."""

import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change, public_facts


ROLE = "unofficial_administrative_measures_not_candidate_returns"
MEASURE = {
    "id": "previously-reviewed-participation-count",
    "kind": "participation_reported",
    "literal": "Derived EV + ED + mail-tallied subtotal; no provisional-issued counts added",
    "mode": "source_defined",
    "unit": "source_reported_count",
}
BASE = "https://nj.gov/state/elections/assets/pdf/periodic-report/2026/2026-1112-"
IMAGE_ONLY = BASE + "sussex-periodic-report.pdf"
IMAGE_ONLY_PIN = "b4df2a7604e7138651d6d4801826779620d82b1feacc5461484f9f263e89babf"
CURRENT_REVIEWED_PINS = {
    BASE + "cumberland-periodic-report.pdf":
        "42efb9391440983ff22adcdbc24dbfd2134d794515ddc45dec60a9c5cf95c978",
    BASE + "middlesex-periodic-report.pdf":
        "fc82617a71b7e45bda37943ca71a277e38d039a4b4ca914a131c57fed3b16165",
}
TABLE_CLOCK = re.compile(
    r"^(?P<date>[0-1]?[0-9]/[0-3]?[0-9]/(?:[0-9]{2}|20[0-9]{2}))\s+"
    r"(?P<time>[0-2]?[0-9]:[0-5][0-9]\s*(?:AM|PM))$", re.I)
HEADER_DATE = re.compile(r"^[0-1]?[0-9]/[0-3]?[0-9]/20[0-9]{2}$")
HEADER_TIME = re.compile(r"^[0-2]?[0-9]:[0-5][0-9]\s*(?:AM|PM)$", re.I)


def _profiles():
    path = Path(__file__).with_name("results_pdf_periodic_grids.json")
    value = json.loads(path.read_bytes())
    if value.get("contract") != "participation.nj_periodic_pdf_profiles.v1":
        raise ValueError("Reviewed New Jersey periodic grid profiles are required")
    result = {}
    for source in value["sources"]:
        if source["url"] in result:
            raise ValueError("Repeated New Jersey periodic source URL")
        result[source["url"]] = {
            "state": "NJ", "layout": "nj_periodic_administrative",
            "measure": MEASURE, **source,
        }
    return result


PROFILES = _profiles()
PROFILES[IMAGE_ONLY] = {
    "state": "NJ", "layout": "nj_periodic_image_ocr", "measure": MEASURE,
    "id": "nj-sussex", "url": IMAGE_ONLY, "filename": "sussex.pdf",
    "expected_pages": 1, "pin": {"sha256": IMAGE_ONLY_PIN, "bytes": 884901},
    "grids": [],
}


def clock_value(literal):
    match = TABLE_CLOCK.fullmatch(" ".join(literal.split()))
    if not match:
        raise ValueError("Native periodic table clock changed")
    date = match.group("date")
    year_format = "%Y" if len(date.rsplit("/", 1)[-1]) == 4 else "%y"
    return datetime.strptime(
        date + " " + match.group("time").upper(),
        f"%m/%d/{year_format} %I:%M %p",
    )


def _page_text(body):
    import fitz

    with fitz.open(stream=body, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("Encrypted periodic PDF requires separate review")
        return [
            [" ".join(line.split()) for line in page.get_text().splitlines() if line.strip()]
            for page in document
        ]


def _header(lines, expected, table_clock):
    if not expected:
        return []
    dates = [line for line in lines if HEADER_DATE.fullmatch(line)]
    times = [line for line in lines if HEADER_TIME.fullmatch(line)]
    if len(dates) != 1 or len(times) != 1:
        raise ValueError("Native periodic header clock is absent or ambiguous")
    header = datetime.strptime(dates[0] + " " + times[0].upper(), "%m/%d/%Y %I:%M %p")
    if not table_clock <= header <= table_clock + timedelta(minutes=30):
        raise ValueError("Native periodic header and table clocks disagree")
    return [dates[0], times[0]]


def _selected_identity(template):
    native = template["view"].get("native_record") or {}
    query = native.get("query") or {}
    source_record_id = native.get("source_record_id") or query.get("source_record_id")
    source_query = native.get("source_query") or query.get("source_query")
    selected = (native.get("selected_native_aggregate_literal")
                or query.get("selected_native_aggregate_literal"))
    if (not isinstance(source_record_id, str) or not re.fullmatch(r"[a-z0-9-]+:[1-9][0-9]*",
            source_record_id) or not isinstance(source_query, str) or not source_query
            or not isinstance(selected, str) or not selected):
        raise ValueError("Reviewed periodic physical source identity is missing")
    table, row = source_record_id.rsplit(":", 1)
    return table, int(row), source_query, selected


def _guard_template(template, url):
    if (template["geography"]["state_code"] != "NJ"
            or template["geography"]["level"] != "county"
            or template["election"]["year"] != 2026
            or template["election"]["type"] != "general"
            or template["measure"] != MEASURE
            or template["count"]["status"] != "reported"
            or template["view"].get("source_url") != url):
        raise ValueError("Reviewed New Jersey periodic identity, measure or source binding changed")
    previous = template["source_clock"].get("literal")
    if not isinstance(previous, str):
        raise ValueError("Reviewed New Jersey periodic source clock is missing")
    clock_value(previous)


def _complete_tables(body, profile):
    from scripts.native_pdf import project, read, text

    facts = read(body)
    if len(facts["pages"]) != profile["expected_pages"]:
        raise ValueError("Native periodic PDF page inventory changed")
    lines = _page_text(body)
    tables, table_clocks, headers = [], {}, {}
    for original in profile["grids"]:
        if original.get("source_role") != ROLE:
            raise ValueError("Native periodic source role changed")
        spec = copy.deepcopy(original)
        annotations = spec.get("source_annotations") or {}
        old_clock = annotations.get("native_table_clock_literal")
        clock_requirements = [
            requirement for requirement in spec["require"]
            if requirement.get("decoded_text") == old_clock
        ]
        if len(clock_requirements) != 1:
            raise ValueError("Reviewed periodic table clock cell is absent or ambiguous")
        page = facts["pages"][spec["page"] - 1]
        actual_clock = text(page, clock_requirements[0]["reading_bbox"])["decoded_text"]
        current_clock = clock_value(actual_clock)
        clock_requirements[0]["decoded_text"] = actual_clock
        actual_headers = _header(
            lines[spec["page"] - 1],
            annotations.get("native_header_clock_literals") or [],
            current_clock,
        )
        upper = " ".join(lines[spec["page"] - 1]).upper()
        if spec.get("require_unofficial_header") and "UNOFFICIAL" not in upper:
            raise ValueError("Native periodic report status changed")
        if spec.get("require_general_election_header") and "GENERAL ELECTION" not in upper:
            raise ValueError("Native periodic election header changed")
        spec["source_annotations"] = {
            **annotations,
            "native_table_clock_literal": actual_clock,
            "native_header_clock_literals": actual_headers,
            "assume_latest_from_page_order": False,
        }
        table = project(facts, spec)
        selected = {
            tuple(identity)
            for row in table["rows"]
            for cell in row["cells"].values()
            for identity in cell["source_glyph_ids"]
        }
        left = min(field["band"][0] for field in spec["fields"])
        right = max(field["band"][1] for field in spec["fields"])
        top = spec["rows"][0][0]
        bottom = min(spec["numeric_guard_bottom"], page["reading_rect"][3])
        for glyph in page["glyphs"]:
            box = glyph["reading_bbox"]
            middle_x = (box[0] + box[2]) / 2
            middle_y = (box[1] + box[3]) / 2
            if (glyph["text"].isdigit() and left <= middle_x < right
                    and top <= middle_y < bottom and tuple(glyph["id"]) not in selected):
                raise ValueError("An unselected native numerical periodic row requires review")
        tables.append(table)
        table_clocks[table["id"]] = actual_clock
        headers[table["id"]] = actual_headers
    return facts, tables, table_clocks, headers


def _query(table, record, source_query, selected_literal, clock, profile, source_pin):
    fields = {}
    for name, cell in record["cells"].items():
        fields[name] = {
            "value": cell["value"], "native_status": cell["native_status"],
            "native_text": cell.get("native_text", cell["decoded_text"]),
            "reading_bbox": cell["reading_bbox"],
            "source_glyph_ids": cell["source_glyph_ids"],
        }
    if fields["native_unit"]["value"] != selected_literal:
        raise ValueError("Reviewed periodic native aggregate literal changed")
    components = {}
    for name in ("early_votes_cast", "election_day_votes_cast", "mail_ballots_tallied"):
        value = fields[name]["value"]
        if type(value) is not int or value < 0:
            raise ValueError("A suppressed or negative participation component cannot be promoted")
        components[name] = value
    subtotal = sum(components.values())
    return {
        "query_id": source_query,
        "source_record_id": f"{table['id']}:{record['row']}",
        "source_table_id": table["id"],
        "source_page": table["source_page"],
        "source_role": table["source_role"],
        "selected_native_aggregate_literal": selected_literal,
        "native_unit": selected_literal,
        "native_table_clock_literal": clock,
        "native_report_status_literal": "UNOFFICIAL",
        "fields": fields,
        **components,
        "reported_participation_subtotal": subtotal,
        "participation_measure_label": MEASURE["literal"],
        "provisional_added_to_subtotal": False,
        "source_pin": source_pin,
        "reviewed_reference_pin": profile["pin"],
        "source_url": profile["url"],
    }


def statistics(body, templates, url):
    profile = PROFILES[url]
    if len(templates) != 1:
        raise ValueError("One reviewed county template is required per periodic product")
    template = templates[0]
    _guard_template(template, url)
    if url == IMAGE_ONLY:
        try:
            from scripts.results_pdf_periodic_ocr import statistics as ocr_statistics
        except ModuleNotFoundError:
            from results_pdf_periodic_ocr import statistics as ocr_statistics
        result = ocr_statistics(body, templates, url, profile)
        if clock_value(result["source_clock"]) < clock_value(
                template["source_clock"]["literal"]):
            raise ValueError("Native periodic report clock regressed")
        return result
    facts, tables, clocks, headers = _complete_tables(body, profile)
    table_id, row_number, source_query, selected_literal = _selected_identity(template)
    selected_tables = [table for table in tables if table["id"] == table_id]
    if len(selected_tables) != 1:
        raise ValueError("Reviewed periodic physical table is absent or ambiguous")
    table = selected_tables[0]
    if not 1 <= row_number <= len(table["rows"]):
        raise ValueError("Reviewed periodic physical row is absent")
    record = table["rows"][row_number - 1]
    if record["row"] != row_number:
        raise ValueError("Reviewed periodic physical row numbering changed")
    query = _query(
        table, record, source_query, selected_literal, clocks[table_id], profile, pin(body),
    )
    if clock_value(query["native_table_clock_literal"]) < clock_value(
            template["source_clock"]["literal"]):
        raise ValueError("Native periodic report clock regressed")
    complete = {
        "contract": "participation.complete_nj_periodic_pdf_query.v1",
        "source": {
            "id": profile["id"], "url": url, "pin": pin(body),
            "reviewed_reference_pin": profile["pin"],
        },
        "pages": [{
            "page": page["page"],
            "native_rotation": page["native_rotation"],
            "reading_rect": page["reading_rect"],
            "native_text_absent_requires_separate_review":
                page["native_text_absent_requires_separate_review"],
        } for page in facts["pages"]],
        "tables": tables,
        "table_clocks": clocks,
        "header_clock_literals": headers,
        "selected_query": query,
        "all_native_cells_retained": True,
        "source_count_repairs": 0,
        "automatic_geographic_or_model_qualification": False,
    }
    public_facts(complete)
    native = {
        "statistical_pdf_layout": "nj_periodic_administrative",
        "query": query,
        "source_record_id": query["source_record_id"],
        "source_query": query["query_id"],
        "selected_native_aggregate_literal": selected_literal,
        "source_clock_literal": query["native_table_clock_literal"],
        "private_original_pin": pin(body),
        "native_report_status_literal": "UNOFFICIAL",
        "native_reporting_complete_qualified": False,
        "retained_source_context_is_historical": True,
        "pdf_report_timezone_literal": None,
    }
    update = change(
        template, query["reported_participation_subtotal"], native,
        registered=None, clock=query["native_table_clock_literal"],
        rate_compatible=False,
    )
    return {
        "updates": [update],
        "complete_native_query": complete,
        "source_clock": query["native_table_clock_literal"],
        "native_missing_timezone_is_not_inferred": True,
        "native_measure_is_administrative_subtotal_not_unique_person_turnout": True,
        "native_reporting_complete_qualified": False,
        "retained_source_context_is_historical": True,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }


def hosted_disposition(url, source_pin):
    profile = PROFILES[url]
    sha256 = source_pin.get("sha256")
    if url == IMAGE_ONLY:
        if sha256 == profile["pin"]["sha256"]:
            return {
                "status": "retained_original_matches_hosted_body_strict_ocr_qualified",
                "url": url, "hosted_pin": source_pin, "reviewed_pin": profile["pin"],
            }
        return {
            "status": "held_hosted_body_has_no_retained_matching_original",
            "url": url, "hosted_pin": source_pin, "reviewed_pin": profile["pin"],
        }
    if sha256 == profile["pin"]["sha256"]:
        return {
            "status": "retained_original_matches_hosted_body",
            "url": url, "hosted_pin": source_pin, "reviewed_pin": profile["pin"],
        }
    return {
        "status": "held_hosted_body_has_no_retained_matching_original",
        "url": url, "hosted_pin": source_pin, "reviewed_pin": profile["pin"],
    }
