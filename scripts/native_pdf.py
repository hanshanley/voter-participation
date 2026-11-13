"""Decoded PDF character/geometry facts; no automatic count or scope qualification."""

import io
import math
import re

import fitz
import pdfplumber


def rectangle(value):
    if (len(value) != 4 or any(not math.isfinite(number) for number in value)
            or value[0] >= value[2] or value[1] >= value[3]):
        raise ValueError("Invalid source reading rectangle")
    return list(value)


def independent_reading_matrix(page, independent_page):
    rotation = page.rotation
    if independent_page.rotation != rotation:
        raise ValueError("Independent source rotation metadata disagree")
    x0, y0, x1, y1 = independent_page.page_obj.mediabox
    ctms = {
        0: (1, 0, 0, 1, -x0, -y0),
        90: (0, -1, 1, 0, -y0, x1),
        180: (-1, 0, 0, -1, x1, y1),
        270: (0, 1, -1, 0, y1, -x0),
    }
    if rotation not in ctms:
        raise ValueError("Unsupported native source rotation")
    crop = page.cropbox
    width, height = (page.rect.height, page.rect.width) if rotation in (90, 270) else (
        page.rect.width, page.rect.height)
    scale_x, scale_y = width / crop.width, height / crop.height
    if not math.isclose(scale_x, scale_y, rel_tol=1e-5):
        raise ValueError("Independent source crop coordinate frames disagree")
    mb_x0, mb_top = independent_page.mediabox[:2]
    reading_to_layout = fitz.Matrix(1, 0, 0, -1, -mb_x0, independent_page.height + mb_top)
    layout_to_pdf = ~fitz.Matrix(*ctms[rotation])
    pdf_to_native = fitz.Matrix(scale_x, 0, 0, -scale_y,
        -crop.x0 * scale_x, (page.mediabox.y1 - crop.y0) * scale_y)
    return reading_to_layout * layout_to_pdf * pdf_to_native * page.rotation_matrix


def read(body):
    pages = []
    with fitz.open(stream=body, filetype="pdf") as document, pdfplumber.open(io.BytesIO(body)) as independent:
        if document.needs_pass:
            raise ValueError("Encrypted source requires separate access review")
        if len(document) != len(independent.pages):
            raise ValueError("Independent source page inventories differ")
        for number, page in enumerate(document):
            matrix = page.rotation_matrix
            independent_page = independent.pages[number]
            crop = independent_page.cropbox
            independent_matrix = independent_reading_matrix(page, independent_page)
            glyphs = []
            raw = page.get_text("rawdict")
            for block_index, block in enumerate(raw["blocks"]):
                if block["type"] != 0:
                    continue
                for line_index, line in enumerate(block["lines"]):
                    for span_index, span in enumerate(line["spans"]):
                        for char_index, char in enumerate(span["chars"]):
                            glyphs.append(dict(id=[block_index, line_index, span_index, char_index],
                                text=char["c"], native_bbox=list(char["bbox"]),
                                reading_bbox=list(fitz.Rect(char["bbox"]) * matrix),
                                native_origin=list(char["origin"]), font=span["font"],
                                font_size=span["size"], native_line_direction=list(line["dir"])))
            tables = []
            for table in independent_page.find_tables():
                tables.append(dict(bbox=list(fitz.Rect(table.bbox) * independent_matrix),
                    independent_bbox=list(table.bbox), rows=[
                    [None if cell is None else list(fitz.Rect(cell) * independent_matrix)
                        for cell in row.cells] for row in table.rows],
                    independent_rows=[
                        [None if cell is None else list(cell) for cell in row.cells] for row in table.rows],
                    independent_decoded_rows=table.extract(x_tolerance=1, y_tolerance=2)))
            pages.append(dict(page=number + 1, native_rotation=page.rotation,
                native_mediabox=list(page.mediabox), native_cropbox=list(page.cropbox),
                reading_rect=list(page.rect), native_to_reading_matrix=list(matrix),
                independent_native_cropbox=list(crop),
                independent_to_reading_matrix=list(independent_matrix),
                glyphs=glyphs, detected_tables=tables,
                native_text_absent_requires_separate_review=not bool(glyphs)))
    return dict(contract="participation.pdf_character_facts.v1", pages=pages,
        automatic_count_or_geography_or_clock_qualification=False,
        original_document_templates_redistributed=False)


def select(page, box):
    left, top, right, bottom = rectangle(box)
    bounds = page["reading_rect"]
    if (left < bounds[0] - 1e-3 or top < bounds[1] - 1e-3
            or right > bounds[2] + 1e-3 or bottom > bounds[3] + 1e-3):
        raise ValueError("A reading rectangle leaves the visible source crop")
    return [glyph for glyph in page["glyphs"] if (
        left <= (glyph["reading_bbox"][0] + glyph["reading_bbox"][2]) / 2 < right
        and top <= (glyph["reading_bbox"][1] + glyph["reading_bbox"][3]) / 2 < bottom)]


def text(page, box, line_tolerance=2.5):
    if not math.isfinite(line_tolerance) or line_tolerance <= 0:
        raise ValueError("A positive reading-line tolerance is required")
    glyphs = select(page, box)
    lines = []
    for glyph in sorted(glyphs, key=lambda item: (
            (item["reading_bbox"][1] + item["reading_bbox"][3]) / 2,
            item["reading_bbox"][0], item["id"])):
        middle = (glyph["reading_bbox"][1] + glyph["reading_bbox"][3]) / 2
        matching = [line for line in lines if abs(line["middle"] - middle) <= line_tolerance]
        if len(matching) > 1:
            raise ValueError("Ambiguous native reading line")
        if matching:
            matching[0]["glyphs"].append(glyph)
        else:
            lines.append(dict(middle=middle, glyphs=[glyph]))
    decoded = []
    for line in sorted(lines, key=lambda item: item["middle"]):
        pieces, previous = [], None
        for glyph in sorted(line["glyphs"], key=lambda item: (item["reading_bbox"][0], item["id"])):
            if previous is not None and not pieces[-1].endswith(" ") and glyph["text"] != " ":
                gap = glyph["reading_bbox"][0] - previous["reading_bbox"][2]
                if gap > .32 * min(glyph["font_size"], previous["font_size"]):
                    pieces.append(" ")
            pieces.append(glyph["text"])
            previous = glyph
        decoded.append("".join(pieces).strip())
    return dict(reading_bbox=list(box), decoded_text="\n".join(decoded),
        source_glyph_ids=[glyph["id"] for glyph in glyphs],
        reading_separators_are_not_additional_native_characters=True)


def count(cell, allow_negative=False):
    value = cell["decoded_text"].strip()
    if value == "":
        return dict(value=None, native_status="blank", native_text=value)
    if value in ("-", "\u2014"):
        return dict(value=None, native_status="native_nonapplicability", native_text=value)
    sign = r"-?" if allow_negative else ""
    if not re.fullmatch(sign + r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", value):
        raise ValueError("A multi-value or nonnumeric cell cannot be repaired into a count")
    return dict(value=int(value.replace(",", "")), native_status="reported", native_text=value)


def grid(page, rows, columns):
    if page["native_text_absent_requires_separate_review"]:
        raise ValueError("An image-only source requires separately reviewed transcription or OCR")
    for bands in (rows, columns):
        if any(len(band) != 2 or not band[0] < band[1] for band in bands):
            raise ValueError("Invalid declared grid band")
        if any(left[1] > right[0] for left, right in zip(bands, bands[1:])):
            raise ValueError("Overlapping grid bands cannot duplicate native characters")
    return [[text(page, [x[0], y[0], x[1], y[1]]) for x in columns] for y in rows]


def project(facts, spec):
    number = spec["page"]
    if type(number) is not int or not 1 <= number <= len(facts["pages"]):
        raise ValueError("Undeclared source page")
    page = facts["pages"][number - 1]
    if not spec.get("require"):
        raise ValueError("A projection requires reviewed native header assertions")
    for requirement in spec["require"]:
        actual = text(page, requirement["reading_bbox"])["decoded_text"]
        if actual != requirement["decoded_text"]:
            raise ValueError("Reviewed native PDF header or clock changed")
    fields = spec["fields"]
    if not fields or len({field["id"] for field in fields}) != len(fields):
        raise ValueError("Ambiguous native field inventory")
    if any(field["kind"] not in ("literal", "count") for field in fields):
        raise ValueError("Unsupported native field kind")
    cells = grid(page, spec["rows"], [field["band"] for field in fields])
    rows = []
    for number, row in enumerate(cells, 1):
        values = {}
        for field, cell in zip(fields, row):
            if field["kind"] == "count":
                parsed = count(cell, allow_negative=field.get("allow_negative", False))
            else:
                parsed = dict(value=cell["decoded_text"], native_status="literal")
            values[field["id"]] = dict(**cell, **parsed)
        rows.append(dict(row=number, cells=values))
    return dict(id=spec["id"], source_page=spec["page"],
        source_role=spec["source_role"], native_requirements=spec["require"],
        source_annotations=spec.get("source_annotations", {}),
        rows=rows, automatic_geographic_or_model_qualification=False)
