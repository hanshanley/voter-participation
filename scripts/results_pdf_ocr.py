"""Bounded local OCR for reviewed image-only statistical pages."""

from importlib.metadata import version
from pathlib import Path
import re
import threading

from scripts.participation_intake.contract import pin


_local = threading.local()


def vertical_layout(items):
    vertical = horizontal = 0
    for box, _text, _confidence in items:
        width = max(point[0] for point in box) - min(point[0] for point in box)
        height = max(point[1] for point in box) - min(point[1] for point in box)
        vertical += height > 1.5 * width
        horizontal += width > 1.5 * height
    return vertical >= 3 and vertical > horizontal


def physical_lines(items, strict_role_alignment=False):
    rows = []
    if strict_role_alignment:
        ordered = sorted(items, key=lambda item: (
            min(point[1] for point in item[0]), min(point[0] for point in item[0])))
    else:
        ordered = sorted(items, key=lambda item: min(point[1] for point in item[0]))
    for box, text, confidence in ordered:
        top, bottom = min(point[1] for point in box), max(point[1] for point in box)
        center = (top + bottom) / 2
        matching = [row for row in rows
                    if abs(row["center"] - center) <= .4 * min(row["height"], bottom - top)]
        if len(matching) > 1:
            if not strict_role_alignment:
                raise ValueError("Ambiguous physical OCR statistical row")
            matching.sort(key=lambda row: abs(row["center"] - center))
            first, second = (abs(row["center"] - center) for row in matching[:2])
            if second - first <= .1 * min(
                    matching[0]["height"], matching[1]["height"], bottom - top):
                raise ValueError("Ambiguous strict physical OCR role alignment")
        row = matching[0] if matching else None
        if row is None:
            row = {"center": center, "height": bottom - top,
                   "weight": bottom - top, "cells": []}
            rows.append(row)
        elif strict_role_alignment:
            weight = row["weight"] + bottom - top
            row["center"] = (
                row["center"] * row["weight"] + center * (bottom - top)) / weight
            row["weight"] = weight
            row["height"] = min(row["height"], bottom - top)
        row["cells"].append((
            min(point[0] for point in box), max(point[0] for point in box),
            " ".join(text.split()), float(confidence)))
    rows.sort(key=lambda row: row["center"])
    cells = [sorted(row["cells"]) for row in rows]
    tokens = []
    role_cells = []
    for row in cells:
        offset, entries, geometry = 0, [], []
        for left, right, text, confidence in row:
            entries.append({"start": offset, "end": offset + len(text), "confidence": confidence})
            geometry.append({"left": left, "right": right, "start": offset,
                             "end": offset + len(text), "text": text,
                             "confidence": confidence})
            offset += len(text) + 1
        tokens.append(entries)
        role_cells.append(geometry)
    result = {"text": "\n".join(" ".join(cell[2] for cell in row) for row in cells),
            "tokens": tokens,
            "confidence": [min((cell[3] for cell in row
                               if re.fullmatch(r"[0-9][0-9,]*", cell[2])),
                              default=min(cell[3] for cell in row)) for row in cells]}
    if strict_role_alignment:
        result["role_cells"] = role_cells
    return result


def page_views(body, strict_role_alignment=False, text_angle_classifier=True,
               page_index=0, region=None, rotation=None):
    import fitz
    import rapidocr_onnxruntime
    from rapidocr_onnxruntime import RapidOCR

    if type(page_index) is not int or page_index < 0:
        raise ValueError("Native statistical PDF page index must be a nonnegative integer")
    if region is not None and (
            len(region) != 4 or not 0 <= region[0] < region[2] <= 1
            or not 0 <= region[1] < region[3] <= 1):
        raise ValueError("Native statistical PDF region must be a bounded normalized rectangle")
    if rotation is not None and (not strict_role_alignment or rotation not in (0, 90)):
        raise ValueError("Known PDF orientation requires a reviewed strict layout")
    if not hasattr(_local, "engine"):
        _local.engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        root = Path(rapidocr_onnxruntime.__file__).parent
        _local.models = {path.name: pin(path.read_bytes()) for path in sorted(root.glob("models/*.onnx"))}
        if not _local.models:
            raise ValueError("OCR model inventory is missing")
    views = []
    options = {} if text_angle_classifier else {"use_cls": False}
    with fitz.open(stream=body, filetype="pdf") as document:
        page = document[page_index]
        rectangle = page.rect
        options_region = {}
        if region is not None:
            rectangle = fitz.Rect(
                page.rect.x0 + page.rect.width * region[0],
                page.rect.y0 + page.rect.height * region[1],
                page.rect.x0 + page.rect.width * region[2],
                page.rect.y0 + page.rect.height * region[3])
            options_region["clip"] = rectangle
        for dpi in (180, 240):
            if rectangle.width * rectangle.height * (dpi / 72) ** 2 > 15_000_000:
                raise ValueError("Native statistical PDF page exceeds the OCR pixel budget")
            angle = rotation or 0
            if angle:
                matrix = fitz.Matrix(dpi / 72, dpi / 72).prerotate(angle)
                image = page.get_pixmap(matrix=matrix, alpha=False, **options_region).tobytes("png")
            else:
                image = page.get_pixmap(dpi=dpi, alpha=False, **options_region).tobytes("png")
            items, _timings = _local.engine(image, **options)
            if not items:
                raise ValueError("Native statistical PDF has no readable OCR statistics")
            if strict_role_alignment and vertical_layout(items):
                if rotation is not None:
                    raise ValueError("Native statistical PDF orientation requires review")
                angle = 90
                matrix = fitz.Matrix(dpi / 72, dpi / 72).prerotate(angle)
                image = page.get_pixmap(matrix=matrix, alpha=False, **options_region).tobytes("png")
                items, _timings = _local.engine(image, **options)
                if not items or vertical_layout(items):
                    raise ValueError("Native statistical PDF orientation requires review")
            view = physical_lines(items, strict_role_alignment=strict_role_alignment)
            receipt = {"engine": "rapidocr_onnxruntime",
                "version": version("rapidocr_onnxruntime"), "models": _local.models,
                "renderer": "PyMuPDF", "renderer_version": version("PyMuPDF"),
                "dpi": dpi, "page": page_index + 1,
                "image": pin(image), "count_minimum_confidence": .98}
            if region is not None:
                receipt["normalized_region"] = list(region)
            if strict_role_alignment:
                receipt["rotation_degrees"] = angle
            if not text_angle_classifier:
                receipt["text_angle_classifier_enabled"] = False
            view["receipt"] = receipt
            views.append(view)
    return views


def first_page_views(body, strict_role_alignment=False, text_angle_classifier=True):
    return page_views(body, strict_role_alignment=strict_role_alignment,
                      text_angle_classifier=text_angle_classifier)
