"""Read only the native statewide age cells and explicit boundary labels."""

from decimal import Decimal
import io
import re
import xml.etree.ElementTree as ET
import zipfile


NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
AGE_BOUNDS = {"18_29": (18, 29), "30_49": (30, 49), "50_64": (50, 64), "65_plus": (65, None)}
SC_BINS = [("18 - 24", 18, 24), ("25 - 44", 25, 44), ("45 - 64", 45, 64), ("65 - Up", 65, None)]
CA_BINS = [("17.5* - 25", None, 25), ("26 - 35", 26, 35), ("36 - 45", 36, 45),
           ("46 - 55", 46, 55), ("56 - 65", 56, 65), ("66+", 66, None)]
COLUMNS = {"Female": ("J", ("K", "L", "M", "N")),
           "Male": ("P", ("Q", "R", "S", "T")),
           "Unknown": ("W", ("X", "Y", "Z", "AA"))}


def cells(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        shared = ["".join(node.itertext()) for node in ET.fromstring(
            archive.read("xl/sharedStrings.xml")).findall("s:si", NS)] if "xl/sharedStrings.xml" in archive.namelist() else []
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    result = {}
    for cell in root.findall(".//s:sheetData/s:row/s:c", NS):
        if cell.find("s:f", NS) is not None:
            raise ValueError("Unreviewed native formula")
        kind, value = "blank", None
        raw = cell.find("s:v", NS)
        if cell.get("t") == "s":
            kind, value = "text", shared[int(raw.text)]
        elif cell.get("t") == "inlineStr":
            kind, value = "text", "".join(cell.find("s:is", NS).itertext())
        elif raw is not None and raw.text is not None:
            if cell.get("t", "n") == "n":
                kind, value = "number", format(Decimal(raw.text).normalize(), "f")
            elif cell.get("t") == "str":
                kind, value = "text", raw.text
            else:
                raise ValueError("Unreviewed native cell type")
        result[cell.get("r")] = dict(kind=kind, value=value)
    return result


def count(cell):
    if cell is None or cell["kind"] == "blank" or cell["kind"] == "text" and cell["value"] == "":
        return None
    if cell["kind"] != "number" or not re.fullmatch(r"\d+", cell["value"] or ""):
        raise ValueError("Invalid native registration count")
    return int(cell["value"])


def matching_bins(bins, group):
    if group not in AGE_BOUNDS:
        return None
    lower, upper = AGE_BOUNDS[group]
    included = [(label, lo, hi) for label, lo, hi in bins if lo is not None and lo >= lower
                and (upper is None or hi is not None and hi <= upper)]
    expected, labels = lower, []
    for label, lo, hi in sorted(included, key=lambda value: value[1]):
        if lo != expected:
            return None
        labels.append(label)
        if hi is None:
            return labels if upper is None else None
        expected = hi + 1
    return labels if upper is not None and expected == upper + 1 else None


def register_frames(source):
    expected = {"C1": "RP0040", "B3": "VR Totals by County / Race / Gender / Age",
                "C7": "Race: All", "D58": "TOTAL", "I9": "Female", "O9": "Male", "U9": "Unknown"}
    for key, value in expected.items():
        if source.get(key, {}).get("value") != value:
            raise ValueError("Changed statewide All-race registration identity or gender labels")
    parent = count(source.get("H58"))
    if parent is None or parent <= 0:
        raise ValueError("No explicit positive statewide registration parent")
    raw, frames, accounting = [], [], []
    for gender, (total_col, columns) in COLUMNS.items():
        values = []
        for (label, _, _), column in zip(SC_BINS, columns):
            if source.get(column + "10", {}).get("value") != label:
                raise ValueError("Changed native age boundary")
            address = column + "58"
            cell = source.get(address, dict(kind="blank", value=None))
            value = count(cell)
            values.append(value)
            raw.append(dict(state_code="SC", native_race_view="All", native_gender_label=gender,
                native_age_label=label, source_sheet="Sheet1", source_cell=address,
                native_cell_kind=cell["kind"], native_value=cell["value"],
                native_registered_count=value, missing_is_zero=False,
                registration_stock_not_participation=True))
        total = count(source.get(total_col + "58"))
        known = sum(value for value in values if value is not None)
        complete = total is not None and all(value is not None for value in values)
        accounting.append(dict(scope="state_age_partition_" + gender, native_parent=total,
            observed_child_subtotal=known, missing_children=sum(v is None for v in values),
            complete=complete, complete_sum_minus_parent=known - total if complete else None,
            unknown_complement_recovered=False))
    for label, _, _ in SC_BINS:
        selected = [row for row in raw if row["native_age_label"] == label]
        complete = all(row["native_registered_count"] is not None for row in selected)
        known = sum(row["native_registered_count"] for row in selected if row["native_registered_count"] is not None)
        frames.append(dict(state_code="SC", native_age_label=label, source_gender_cells=len(selected),
            observed_registered_subtotal=known, missing_gender_cells=sum(r["native_registered_count"] is None for r in selected),
            derived_all_gender_age_register=known if complete else None,
            printed_all_gender_age_parent=None, derived_not_printed=True,
            unknown_gender_included=True, partial_subtotal_not_promoted_to_total=True))
    totals = [count(source.get(col + "58")) for col, _ in COLUMNS.values()]
    complete = all(value is not None for value in totals)
    accounting.append(dict(scope="state_gender_partition", native_parent=parent,
        observed_child_subtotal=sum(v for v in totals if v is not None),
        missing_children=sum(v is None for v in totals), complete=complete,
        complete_sum_minus_parent=sum(totals) - parent if complete else None,
        unknown_complement_recovered=False))
    return parent, raw, frames, accounting
