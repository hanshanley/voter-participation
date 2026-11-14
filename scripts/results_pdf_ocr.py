"""Bounded local OCR for image-only statistical first pages; never a text-layer override."""

from importlib.metadata import version
from pathlib import Path
import re
import threading

from scripts.participation_intake.contract import pin


_local = threading.local()


def physical_lines(items):
    rows = []
    for box, text, confidence in sorted(items, key=lambda item: min(point[1] for point in item[0])):
        top, bottom = min(point[1] for point in box), max(point[1] for point in box)
        center = (top + bottom) / 2
        matching = [row for row in rows
                    if abs(row["center"] - center) <= .4 * min(row["height"], bottom - top)]
        if len(matching) > 1:
            raise ValueError("Ambiguous physical OCR statistical row")
        row = matching[0] if matching else None
        if row is None:
            row = {"center": center, "height": bottom - top, "cells": []}
            rows.append(row)
        row["cells"].append((min(point[0] for point in box), " ".join(text.split()), float(confidence)))
    rows.sort(key=lambda row: row["center"])
    cells = [sorted(row["cells"]) for row in rows]
    tokens = []
    for row in cells:
        offset, entries = 0, []
        for _left, text, confidence in row:
            entries.append({"start": offset, "end": offset + len(text), "confidence": confidence})
            offset += len(text) + 1
        tokens.append(entries)
    return {"text": "\n".join(" ".join(cell[1] for cell in row) for row in cells),
            "tokens": tokens,
            "confidence": [min((cell[2] for cell in row
                               if re.fullmatch(r"[0-9][0-9,]*", cell[1])),
                              default=min(cell[2] for cell in row)) for row in cells]}


def first_page_views(body):
    import fitz
    import rapidocr_onnxruntime
    from rapidocr_onnxruntime import RapidOCR

    if not hasattr(_local, "engine"):
        _local.engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
        root = Path(rapidocr_onnxruntime.__file__).parent
        _local.models = {path.name: pin(path.read_bytes()) for path in sorted(root.glob("models/*.onnx"))}
        if not _local.models:
            raise ValueError("OCR model inventory is missing")
    views = []
    with fitz.open(stream=body, filetype="pdf") as document:
        page = document[0]
        for dpi in (180, 240):
            if page.rect.width * page.rect.height * (dpi / 72) ** 2 > 15_000_000:
                raise ValueError("Native statistical PDF page exceeds the OCR pixel budget")
            image = page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
            items, _timings = _local.engine(image)
            if not items:
                raise ValueError("Native statistical PDF has no readable OCR statistics")
            view = physical_lines(items)
            view["receipt"] = {"engine": "rapidocr_onnxruntime",
                "version": version("rapidocr_onnxruntime"), "models": _local.models,
                "renderer": "PyMuPDF", "renderer_version": version("PyMuPDF"),
                "dpi": dpi, "page": 1, "image": pin(image), "count_minimum_confidence": .98}
            views.append(view)
    return views
