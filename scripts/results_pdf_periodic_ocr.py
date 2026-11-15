"""Strict same-engine two-resolution OCR for the Sussex periodic report."""

import copy
from datetime import datetime
import json
from pathlib import Path
import re

from scripts.participation_intake.contract import pin
from scripts.results_granular import change, public_facts


MINIMUM_CONFIDENCE = .98
NUMBER = re.compile(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)")


def _profile():
    value = json.loads(
        Path(__file__).with_name("results_pdf_periodic_sussex.json").read_bytes()
    )
    if value.get("contract") != "participation.nj_sussex_strict_ocr_profile.v1":
        raise ValueError("Reviewed Sussex OCR geometry profile is required")
    return value


PROFILE = _profile()


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _clock(value, four_digit_year=False):
    compact = re.sub(r"\s+", "", value).upper()
    match = re.fullmatch(
        r"([0-1]?[0-9]/[0-3]?[0-9]/(?:[0-9]{2}|20[0-9]{2}))"
        r"([0-2]?[0-9]:[0-5][0-9])(AM|PM)",
        compact,
    )
    if not match:
        raise ValueError("Sussex OCR native clock changed")
    date, time, meridiem = match.groups()
    year = date.rsplit("/", 1)[-1]
    if four_digit_year != (len(year) == 4):
        raise ValueError("Sussex OCR header/table clock role changed")
    instant = datetime.strptime(
        date + " " + time + " " + meridiem,
        "%m/%d/%Y %I:%M %p" if four_digit_year else "%m/%d/%y %I:%M %p",
    )
    literal = date + " " + time + " " + meridiem
    return instant, literal


def _source_page(body):
    import fitz

    with fitz.open(stream=body, filetype="pdf") as document:
        if document.needs_pass or len(document) != PROFILE["source"]["expected_pages"]:
            raise ValueError("Sussex OCR source page inventory changed")
        page = document[0]
        expected = PROFILE["page"]
        if (page.rotation != expected["rotation"]
                or [float(value) for value in page.rect] != expected["reading_rect"]
                or bool(page.get_text().strip()) == expected["requires_absent_text_layer"]
                or len(page.get_images(full=True)) != expected["image_objects"]):
            raise ValueError("Sussex OCR source page geometry or text-layer status changed")


def _column(point):
    matches = [
        column["id"] for column in PROFILE["columns"]
        if column["band"][0] <= point < column["band"][1]
    ]
    if len(matches) > 1:
        raise ValueError("Sussex OCR token crosses ambiguous reviewed columns")
    return matches[0] if matches else None


def _parse_clock_and_headers(view, first_row_line):
    lines = view["text"].splitlines()
    dates = [line for line in lines[:first_row_line]
             if re.fullmatch(r"[0-1]?[0-9]/[0-3]?[0-9]/20[0-9]{2}", line)]
    times = [line for line in lines[:first_row_line]
             if re.fullmatch(r"[0-2]?[0-9]:[0-5][0-9]\s*(?:AM|PM)", line, re.I)]
    statuses = [line for line in lines[:first_row_line]
                if line == PROFILE["native_report_status_literal"]]
    if len(dates) != 1 or len(times) != 1 or len(statuses) != 1:
        raise ValueError("Sussex OCR header date, time or status is absent or ambiguous")
    header_instant, header_literal = _clock(dates[0] + times[0], four_digit_year=True)
    scale = view["receipt"]["dpi"] / 72
    header_cells = []
    by_column = {column["id"]: [] for column in PROFILE["columns"]}
    table_clocks = []
    for line_number, cells in enumerate(view["role_cells"][:first_row_line], 1):
        for cell in cells:
            point = (cell["left"] + cell["right"]) / 2 / scale
            column = _column(point)
            if column is None:
                continue
            record = {
                "line": line_number, "column": column, "text": cell["text"],
                "confidence": cell["confidence"], "reading_center_x": point,
            }
            header_cells.append(record)
            if column == "native_unit" and re.fullmatch(
                    r"[0-9/:\s]+(?:AM|PM)", cell["text"], re.I):
                table_clocks.append(cell["text"])
            elif column != "native_unit":
                by_column[column].append(cell["text"])
    if len(table_clocks) != 1:
        raise ValueError("Sussex OCR native table clock is absent or ambiguous")
    table_instant, table_literal = _clock(table_clocks[0], four_digit_year=False)
    if table_instant != header_instant:
        raise ValueError("Sussex OCR header and table clocks disagree")
    expected_roles = {
        "early_machines_deployed": "Machines Deployed",
        "early_machines_not_included": "Machines Not Included",
        "early_votes_cast": "Votes Cast",
        "election_day_machines_deployed": "Machines Deployed",
        "election_day_machines_not_included": "Machines Not Included",
        "election_day_votes_cast": "Votes Cast",
        "mail_ballots_issued": "Ballots Issued",
        "mail_received_into_svrs": "Received into SVRS",
        "mail_ballots_tallied": "Ballots Tallied",
        "mail_ballots_to_be_processed": "Ballots to be Processed",
        "provisional_eligible_received": "Eligible Received",
        "provisional_eligible_counted": "Eligible Counted",
    }
    actual_roles = {
        field: " ".join(values) for field, values in by_column.items()
        if field != "native_unit"
    }
    if any(_normalized(expected) not in _normalized(actual_roles.get(field, ""))
           for field, expected in expected_roles.items()):
        raise ValueError("Sussex OCR native statistical heading roles changed")
    heading_text = _normalized(" ".join(lines[:first_row_line]))
    for role in ("Early Voting", "Election Day", "Vote-by-Mail", "Provisional"):
        if _normalized(role) not in heading_text:
            raise ValueError("Sussex OCR native mode heading changed")
    return {
        "native_header_clock_literal": header_literal,
        "native_table_clock_literal": table_literal,
        "native_report_status_literal": statuses[0],
        "native_header_ocr_lines": lines[:first_row_line],
        "native_header_role_cells": header_cells,
        "native_column_role_literals": actual_roles,
    }


def _parse_view(view):
    receipt = view.get("receipt") or {}
    if (receipt.get("engine") != "rapidocr_onnxruntime"
            or receipt.get("count_minimum_confidence") != MINIMUM_CONFIDENCE
            or receipt.get("rotation_degrees") != 0
            or receipt.get("dpi") not in (180, 240)
            or not receipt.get("models")):
        raise ValueError("Sussex OCR engine, resolution, orientation or model receipt changed")
    scale = receipt["dpi"] / 72
    expected = PROFILE["row_identities"]
    expected_by_key = {_normalized(label): label for label in expected}
    rows = []
    for line_number, cells in enumerate(view["role_cells"], 1):
        labels, values, nonnumeric = [], {}, []
        for cell in cells:
            point = (cell["left"] + cell["right"]) / 2 / scale
            field = _column(point)
            if field is None:
                continue
            text = cell["text"]
            if field == "native_unit":
                labels.append(cell)
            elif NUMBER.fullmatch(text):
                if field in values:
                    raise ValueError("Sussex OCR repeated a native numerical cell")
                values[field] = {
                    "value": int(text.replace(",", "")),
                    "native_status": "reported",
                    "native_text": text,
                    "confidence": float(cell["confidence"]),
                    "reading_center_x": point,
                    "ocr_line": line_number,
                }
            elif text in ("-", "\u2014"):
                if field in values:
                    raise ValueError("Sussex OCR repeated a native nonapplicability cell")
                values[field] = {
                    "value": None,
                    "native_status": "native_nonapplicability",
                    "native_text": text,
                    "confidence": float(cell["confidence"]),
                    "reading_center_x": point,
                    "ocr_line": line_number,
                }
            else:
                nonnumeric.append((field, text))
        label_text = " ".join(cell["text"] for cell in labels)
        key = _normalized(label_text)
        if key not in expected_by_key:
            continue
        if nonnumeric:
            raise ValueError("Sussex OCR found nonnumeric text in a reviewed count column")
        fields = {}
        for column in PROFILE["columns"][1:]:
            field = column["id"]
            fields[field] = values.get(field, {
                "value": None, "native_status": "blank", "native_text": "",
                "confidence": None, "reading_center_x": sum(column["band"]) / 2,
                "ocr_line": line_number,
            })
        rows.append({
            "row": len(rows) + 1,
            "native_unit": expected_by_key[key],
            "native_unit_ocr_text": label_text,
            "native_unit_confidence": min(float(cell["confidence"]) for cell in labels),
            "ocr_line": line_number,
            "cells": fields,
        })
    if ([row["native_unit"] for row in rows] != expected
            or len({_normalized(row["native_unit_ocr_text"]) for row in rows}) != len(expected)):
        raise ValueError("Sussex OCR native row identity or order changed")
    headers = _parse_clock_and_headers(view, rows[0]["ocr_line"] - 1)
    return {"receipt": receipt, "headers": headers, "rows": rows}


def _selected_identity(template):
    native = template["view"].get("native_record") or {}
    query = native.get("query") or {}
    source_record_id = native.get("source_record_id") or query.get("source_record_id")
    source_query = native.get("source_query") or query.get("source_query")
    selected = (native.get("selected_native_aggregate_literal")
                or query.get("selected_native_aggregate_literal"))
    if (source_record_id != "sussex-administrative-page-1:1"
            or not isinstance(source_query, str) or not source_query
            or selected != PROFILE["selected_native_aggregate_literal"]):
        raise ValueError("Reviewed Sussex physical source identity changed")
    return source_query, selected


def parse_views(views, template, url, profile, source_pin):
    if len(views) != 2 or sorted(view["receipt"].get("dpi") for view in views) != [180, 240]:
        raise ValueError("Sussex OCR requires exactly the reviewed two resolutions")
    parsed = [_parse_view(copy.deepcopy(view)) for view in views]
    first, second = parsed
    receipt_keys = ("engine", "version", "models", "renderer", "renderer_version")
    if any(first["receipt"].get(key) != second["receipt"].get(key) for key in receipt_keys):
        raise ValueError("Sussex OCR passes did not use the same engine and models")
    if first["headers"]["native_table_clock_literal"] != second["headers"][
            "native_table_clock_literal"]:
        raise ValueError("Sussex OCR native clocks disagree")
    complete_rows = []
    for left, right in zip(first["rows"], second["rows"]):
        if left["native_unit"] != right["native_unit"]:
            raise ValueError("Sussex OCR row identities disagree")
        cells = {}
        for column in PROFILE["columns"][1:]:
            field = column["id"]
            a, b = left["cells"][field], right["cells"][field]
            if (a["value"], a["native_status"]) != (b["value"], b["native_status"]):
                raise ValueError("Sussex OCR complete numerical cells disagree")
            cells[field] = {
                "value": a["value"], "native_status": a["native_status"],
                "native_text": a["native_text"],
                "ocr_passes": [
                    {"dpi": first["receipt"]["dpi"], **a},
                    {"dpi": second["receipt"]["dpi"], **b},
                ],
            }
        complete_rows.append({
            "row": left["row"], "native_unit": left["native_unit"],
            "native_unit_ocr_passes": [
                {"dpi": first["receipt"]["dpi"],
                 "text": left["native_unit_ocr_text"],
                 "confidence": left["native_unit_confidence"],
                 "ocr_line": left["ocr_line"]},
                {"dpi": second["receipt"]["dpi"],
                 "text": right["native_unit_ocr_text"],
                 "confidence": right["native_unit_confidence"],
                 "ocr_line": right["ocr_line"]},
            ],
            "cells": cells,
        })
    source_query, selected_literal = _selected_identity(template)
    selected = [row for row in complete_rows if row["native_unit"] == selected_literal]
    if len(selected) != 1:
        raise ValueError("Sussex OCR selected native parent is absent or ambiguous")
    selected = selected[0]
    components = {}
    confidence = {}
    for field in PROFILE["selected_count_fields"]:
        cell = selected["cells"][field]
        if type(cell["value"]) is not int or cell["value"] < 0:
            raise ValueError("Sussex OCR selected count component is suppressed or negative")
        values = [item["confidence"] for item in cell["ocr_passes"]]
        if min(values) < MINIMUM_CONFIDENCE:
            raise ValueError("Sussex OCR selected numeric confidence requires review")
        components[field] = cell["value"]
        confidence[field] = values
    subtotal = sum(components.values())
    query = {
        "query_id": source_query,
        "source_record_id": "sussex-administrative-page-1:1",
        "source_page": 1,
        "source_role": PROFILE["source_role"],
        "selected_native_aggregate_literal": selected_literal,
        "native_unit": selected_literal,
        "native_table_clock_literal": first["headers"]["native_table_clock_literal"],
        "native_header_clock_literal": first["headers"]["native_header_clock_literal"],
        "native_report_status_literal": first["headers"]["native_report_status_literal"],
        **components,
        "reported_participation_subtotal": subtotal,
        "selected_numeric_confidence_by_pass": confidence,
        "provisional_added_to_subtotal": False,
        "source_pin": source_pin,
        "reviewed_reference_pin": profile["pin"],
        "source_url": url,
    }
    complete = {
        "contract": "participation.complete_nj_sussex_ocr_query.v1",
        "source": {"id": profile["id"], "url": url, "pin": source_pin,
                   "reviewed_reference_pin": profile["pin"]},
        "source_role": PROFILE["source_role"],
        "headers": [item["headers"] for item in parsed],
        "rows": complete_rows,
        "ocr": {
            "passes": [item["receipt"] for item in parsed],
            "same_engine_resolution_check_not_independent_validation": True,
            "selected_numeric_minimum_confidence": MINIMUM_CONFIDENCE,
            "full_numeric_cell_vectors_equal": True,
        },
        "complete_numerical_cell_positions": len(complete_rows) * (
            len(PROFILE["columns"]) - 1),
        "old_visual_transcription_values_used_as_numeric_inputs": False,
        "reviewed_geometry_and_identity_only": True,
        "source_count_repairs": 0,
        "automatic_geographic_or_model_qualification": False,
        "selected_query": query,
    }
    public_facts(complete)
    native = {
        "statistical_pdf_layout": "nj_periodic_image_ocr",
        "query": query,
        "source_record_id": query["source_record_id"],
        "source_query": query["query_id"],
        "selected_native_aggregate_literal": selected_literal,
        "source_clock_literal": query["native_table_clock_literal"],
        "private_original_pin": source_pin,
        "native_report_status_literal": query["native_report_status_literal"],
        "native_reporting_complete_qualified": False,
        "retained_source_context_is_historical": True,
        "pdf_report_timezone_literal": None,
        "ocr_selected_count_minimum_confidence": min(
            value for values in confidence.values() for value in values),
        "same_engine_resolution_check_not_independent_validation": True,
    }
    return {
        "updates": [change(
            template, subtotal, native, registered=None,
            clock=query["native_table_clock_literal"], rate_compatible=False,
        )],
        "complete_native_query": complete,
        "source_clock": query["native_table_clock_literal"],
        "native_missing_timezone_is_not_inferred": True,
        "native_measure_is_administrative_subtotal_not_unique_person_turnout": True,
        "native_reporting_complete_qualified": False,
        "retained_source_context_is_historical": True,
        "geographic_joins_changed": False,
        "analytical_rates_promoted": False,
    }


def statistics(body, templates, url, profile):
    from scripts.results_pdf_ocr import first_page_views

    if len(templates) != 1:
        raise ValueError("One reviewed Sussex county template is required")
    _source_page(body)
    views = first_page_views(body, strict_role_alignment=True)
    return parse_views(views, templates[0], url, profile, pin(body))
