"""Batch validation of printed total columns in reviewed scanned tables."""

import math
from pathlib import Path
import re

from scripts.participation_intake.contract import IntakeError, count, encoded, pin
from scripts.results_pdf_ocr import page_views

DPI = (180, 240)
MINIMUM = 0.98
RECONCILIATION_FAILED = "scan_reconciliation_failed"


def fail(message):
    raise IntakeError(RECONCILIATION_FAILED, message)


def scan_policy(adapter, profile):
    from importlib.metadata import version
    import platform

    return pin(encoded({
        "profile": profile,
        "code": [pin(Path(file).read_bytes()) for file in (
            adapter, __file__, Path(__file__).with_name("results_pdf_ocr.py"))],
        "versions": {package: version(package) for package in (
            "pypdf", "PyMuPDF", "rapidocr-onnxruntime", "onnxruntime", "numpy")},
        "runtime": [platform.system(), platform.machine(), platform.python_version()],
    }))["sha256"]


class ScanRejection:
    """Skip deterministic scan failures only for the same report and parser policy."""

    def __init__(self, previous):
        self.receipt = previous.get("rejected_scan")

    def parse(self, report, policy, parser):
        key = {"report": report, "policy": policy}
        if self.receipt and self.receipt["key"] == key:
            fail(self.receipt["detail"])
        try:
            result = parser()
        except IntakeError as error:
            if error.code == RECONCILIATION_FAILED:
                self.receipt = {"key": key, "detail": str(error)}
            raise
        self.receipt = None
        return result

    def attach(self, entry):
        if self.receipt is None:
            entry.pop("rejected_scan", None)
        else:
            entry["rejected_scan"] = self.receipt


def label(text):
    return re.sub(r"[^a-z]", "", text.lower())


def heading_key(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def extract(body, page_indices, *, rotation=None):
    try:
        return {str(page): page_views(body, page_index=page, strict_role_alignment=True,
                                      text_angle_classifier=False, rotation=rotation)
                for page in sorted(set(page_indices))}
    except (ValueError, IndexError) as error:
        fail(f"Scanned table extraction failed: {error}")


def panel(view, specification, aliases):
    # Bands are in PDF points, independent of render resolution.
    _, headings, names, name_band, total_band = specification
    scale = 72 / view["receipt"]["dpi"]
    lines = view["text"].splitlines()
    header = heading_key(" ".join(lines[:8]))
    if not all(heading_key(heading) in header for heading in headings):
        fail("Missing scanned table heading")
    expected_names = {label(name) for name in names}
    physical_rows = view["role_cells"]
    output = []
    for physical_row, cells in enumerate(physical_rows, 1):
        names_here = [cell for cell in cells if name_band[0] <= cell["left"] * scale < name_band[1]]
        totals = [cell for cell in cells if total_band[0] <= cell["right"] * scale < total_band[1]
                  and re.fullmatch(r"[0-9][0-9,]*", cell["text"], flags=re.ASCII)]
        if not totals:
            continue
        if len(names_here) != 1 or len(totals) != 1:
            fail("Ambiguous scanned county or total column")
        observed, total = names_here[0]["text"], totals[0]
        native = label(observed)
        if (aliases.get(native, native) not in expected_names and physical_row < len(physical_rows)
                and len(following := physical_rows[physical_row]) == 1
                and name_band[0] <= following[0]["left"] * scale < name_band[1]
                and native + label(following[0]["text"]) in expected_names):
            observed += " " + following[0]["text"]
            native = label(observed)
        confidence = total["confidence"]
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            fail("Invalid OCR confidence")
        output.append({"name": aliases.get(native, native), "literal_name": observed,
                       "literal_total": total["text"], "total": count(total["text"]),
                       "high_confidence": confidence >= MINIMUM, "row": physical_row})
    if [row["name"] for row in output] != [label(name) for name in names]:
        fail("Scanned table county roster or row order differs")
    return output


def native_control(lines, name, fields):
    candidates = []
    for line in lines:
        parts = line.rsplit(None, fields)
        if len(parts) != fields + 1 or parts[0].casefold() != name.casefold():
            continue
        if not all(re.fullmatch(r"[0-9][0-9,]*", part, flags=re.ASCII) for part in parts[1:]):
            continue
        total, *components = map(count, parts[1:])
        if total == sum(components):
            candidates.append((line, total))
    return candidates[0] if len(candidates) == 1 else (None, None)


def verify(evidence, profile):
    if set(evidence) != {"cover", "tables"}:
        fail("Incomplete scan evidence")
    cover = evidence["cover"]
    if len(cover) != 2 or any(
            item["receipt"]["page"] != profile["cover_page"] + 1 or item["receipt"]["dpi"] != dpi
            or not all(heading_key(term) in heading_key(item["text"]) for term in profile["cover_headings"])
            for item, dpi in zip(cover, DPI, strict=True)):
        fail("Scanned report authority or election date differs")
    tables = evidence["tables"]
    if set(tables) != set(profile["tables"]):
        fail("Scanned table inventory differs")
    result = {}
    for table, panels in profile["tables"].items():
        if len(tables[table]) != len(panels):
            fail("Scanned report panel inventory differs")
        result[table] = {}
        for pair, (page, _, names, _, _) in zip(tables[table], panels, strict=True):
            if len(pair) != 2:
                fail("Scanned report requires two distinct renders")
            for item, dpi in zip(pair, DPI, strict=True):
                receipt = item["receipt"]
                if receipt["page"] != page + 1 or receipt["dpi"] != dpi or len(item["rows"]) != len(names):
                    fail("Scanned report page, resolution, or row inventory differs")
                positions = [row["row"] for row in item["rows"]]
                if positions != sorted(set(positions)) or positions[0] < 1:
                    fail("Scanned physical row order differs")
            for name, a, b in zip(names, pair[0]["rows"], pair[1]["rows"], strict=True):
                values = [count(row["literal_total"]) for row in (a, b)]
                previous = result[table].get(name)
                if ((previous is not None and (name != "TOTAL" or previous != values[0])) or any(
                        row["name"] != label(name) or row["name"] != profile["aliases"].get(
                            label(row["literal_name"]), label(row["literal_name"]))
                        or row["total"] != value or type(row["high_confidence"]) is not bool
                        for row, value in zip((a, b), values, strict=True))
                        or values[0] != values[1]):
                    fail("Scanned totals or identities disagree between renders")
                if not (a["high_confidence"] or b["high_confidence"]):
                    fields = profile.get("native_controls", {}).get(table)
                    line = pair[0].get("native_controls", {}).get(name)
                    if not fields or not line or native_control((line,), name, fields)[1] != values[0]:
                        fail(f"Neither render clears the OCR confidence floor for {table}: {name}")
                result[table][name] = values[0]
        totals = result[table]
        if "TOTAL" not in totals or sum(v for k, v in totals.items() if k != "TOTAL") != totals["TOTAL"]:
            fail("Scanned county amounts do not reconcile to the printed state total")
    return result


def parse(body, profile, native_page=None):
    indices = [profile["cover_page"], *(p[0] for panels in profile["tables"].values() for p in panels)]
    views = extract(body, indices)
    evidence = {"cover": [{"text": view["text"], "receipt": view["receipt"]}
                          for view in views[str(profile["cover_page"])]], "tables": {
        table: [[{"receipt": view["receipt"], "rows": panel(view, spec, profile["aliases"])}
                 for view in views[str(spec[0])]] for spec in panels]
        for table, panels in profile["tables"].items()}}
    for table, fields in profile.get("native_controls", {}).items():
        for pair, spec in zip(evidence["tables"][table], profile["tables"][table], strict=True):
            low = [name for name, a, b in zip(spec[2], pair[0]["rows"], pair[1]["rows"], strict=True)
                   if not (a["high_confidence"] or b["high_confidence"])]
            if low and native_page is not None:
                lines = [" ".join(line.split()) for line in native_page(spec[0]).splitlines()]
                pair[0]["native_controls"] = {name: native_control(lines, name, fields)[0] for name in low}
    return verify(evidence, profile), evidence
