"""Lossless factual tables; no election, count, geography or denominator qualification."""

import csv
import io
import json
from pathlib import PurePosixPath
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def delimited(body, delimiter=",", preamble_rows=0, encoding="utf-8-sig"):
    rows = list(csv.reader(io.StringIO(body.decode(encoding), newline=""),
        delimiter=delimiter, strict=True))
    if type(preamble_rows) is not int or preamble_rows < 0 or len(rows) <= preamble_rows:
        raise ValueError("A declared native header is required")
    header = rows[preamble_rows]
    if not header or any(len(row) != len(header) for row in rows[preamble_rows + 1:]):
        raise ValueError("Native table field width changed")
    return dict(header=header, preamble=rows[:preamble_rows],
        rows=[dict(row=index, values=values) for index, values in
            enumerate(rows[preamble_rows + 1:], preamble_rows + 2)])


def column(table, label):
    indices = [index for index, value in enumerate(table["header"]) if value == label]
    if len(indices) != 1:
        raise ValueError("Required native column is missing or ambiguous: " + label)
    return indices[0]


def xls(body):
    import xlrd

    workbook = xlrd.open_workbook(file_contents=body, formatting_info=True, on_demand=True)
    try:
        if workbook.datemode not in (0, 1):
            raise ValueError("Unknown native BIFF date system")
        tables = []
        for sheet in workbook.sheets():
            rows = []
            for number in range(sheet.nrows):
                cells = []
                for column_number in range(sheet.ncols):
                    cell = sheet.cell(number, column_number)
                    if cell.ctype == xlrd.XL_CELL_EMPTY:
                        continue
                    value = cell.value
                    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        value = None
                    elif cell.ctype == xlrd.XL_CELL_NUMBER and isinstance(value, float) and value.is_integer():
                        value = int(value)
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        value = bool(value)
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        value = xlrd.error_text_from_code[value]
                    index, letters = column_number + 1, ""
                    while index:
                        index, remainder = divmod(index - 1, 26)
                        letters = chr(65 + remainder) + letters
                    cells.append(dict(address=letters + str(number + 1),
                        attributes=dict(s=str(cell.xf_index)), storage_type="biff:" + str(cell.ctype),
                        cached_value=cell.value, value=value))
                rows.append(dict(row=number + 1, cells=cells))
            tables.append(dict(name=sheet.name, rows=rows, nrows=sheet.nrows, ncols=sheet.ncols,
                absent_cells_are_implicit_empty=True,
                source_format="BIFF_cached_cells",
                formula_provenance="Formula expressions are not exposed by this reader; cached values are not recalculated.",
                workbook_properties=dict(date1904=str(workbook.datemode)),
                workbook_number_formats={str(key): item.format_str for key, item in workbook.format_map.items()},
                workbook_cell_formats=[dict(numFmtId=str(item.format_key)) for item in workbook.xf_list]))
        if not tables or len({table["name"] for table in tables}) != len(tables):
            raise ValueError("Native BIFF worksheet identities are absent or ambiguous")
        return tables
    finally:
        workbook.release_resources()


def json_records(body, items_path=None, encoding="utf-8-sig", record_guards=None):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate native JSON object key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Nonfinite native JSON value: " + value)

    data = json.loads(body.decode(encoding), object_pairs_hook=unique_object,
        parse_constant=invalid_constant)
    if items_path:
        for part in items_path.split("."):
            if isinstance(data, dict) and part in data:
                data = data[part]
            elif isinstance(data, list) and part.isdecimal() and int(part) < len(data):
                data = data[int(part)]
            else:
                raise ValueError("Declared native JSON record path is absent")
    if not isinstance(data, list) or not data or not all(isinstance(row, dict) for row in data):
        raise ValueError("A complete native JSON record array is required")
    header = list(data[0])
    if not header or any(not name for name in header):
        raise ValueError("Native JSON field identities are empty")
    rows = []
    for index, row in enumerate(data):
        if set(row) != set(header) or any(isinstance(value, (dict, list)) for value in row.values()):
            raise ValueError("Native JSON record schema changed or needs an explicit nested-field reader")
        for key, pattern in (record_guards or {}).items():
            if not isinstance(row.get(key), str) or re.fullmatch(pattern, row[key]) is None:
                raise ValueError("Native JSON record guard failed: " + key)
        rows.append(dict(row=index, values=[row[name] for name in header]))
    return dict(header=header, rows=rows, record_address_basis="zero_based_json_array_index")


def xlsx(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Ambiguous duplicate workbook member")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {row.attrib["Id"]: row.attrib["Target"] for row in relationships}
        properties = workbook.find("{" + NS + "}workbookPr")
        formats, cell_formats = {}, []
        if "xl/styles.xml" in archive.namelist():
            styles = ET.fromstring(archive.read("xl/styles.xml"))
            formats = {item.attrib["numFmtId"]: item.attrib["formatCode"]
                for item in styles.findall("{" + NS + "}numFmts/{" + NS + "}numFmt")}
            cell_formats = [dict(item.attrib)
                for item in styles.findall("{" + NS + "}cellXfs/{" + NS + "}xf")]
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.text or "" for node in item.iter("{" + NS + "}t"))
                for item in shared]
        tables = []
        for sheet in workbook.findall("{" + NS + "}sheets/{" + NS + "}sheet"):
            target = targets[sheet.attrib["{" + REL + "}id"]]
            member = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                else posixpath.join("xl", target))
            if not member.startswith("xl/") or ".." in PurePosixPath(member).parts:
                raise ValueError("Worksheet reference leaves the workbook")
            source = ET.fromstring(archive.read(member))
            rows = []
            seen_rows, seen_cells = set(), set()
            for native_row in source.findall("{" + NS + "}sheetData/{" + NS + "}row"):
                number = int(native_row.attrib["r"])
                if number in seen_rows or number < 1:
                    raise ValueError("Ambiguous native worksheet row")
                seen_rows.add(number)
                cells = []
                for cell in native_row.findall("{" + NS + "}c"):
                    address = cell.attrib["r"]
                    if (not re.fullmatch(r"[A-Z]+" + str(number), address)
                            or address in seen_cells):
                        raise ValueError("Ambiguous native worksheet cell")
                    seen_cells.add(address)
                    kind = cell.attrib.get("t", "n")
                    raw = cell.find("{" + NS + "}v")
                    literal = raw.text if raw is not None else None
                    formula = cell.find("{" + NS + "}f")
                    if kind == "s" and literal is not None:
                        if not re.fullmatch(r"[0-9]+", literal) or int(literal) >= len(strings):
                            raise ValueError("Invalid native shared-string index")
                        value = strings[int(literal)]
                    elif kind == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter("{" + NS + "}t"))
                    elif kind == "b" and literal is not None:
                        if literal not in ("0", "1"):
                            raise ValueError("Unrecognized native boolean")
                        value = literal == "1"
                    elif kind == "n" and literal is not None and re.fullmatch(r"[+-]?[0-9]+", literal):
                        value = int(literal)
                    else:
                        value = literal
                    cells.append(dict(address=cell.attrib["r"], attributes=dict(cell.attrib),
                        storage_type=kind, cached_literal=literal, value=value,
                        formula=None if formula is None else dict(
                            text=formula.text, attributes=dict(formula.attrib))))
                rows.append(dict(row=number, cells=cells))
            tables.append(dict(name=sheet.attrib["name"], member=member,
                attributes=dict(sheet.attrib), rows=rows,
                workbook_properties={} if properties is None else dict(properties.attrib),
                workbook_number_formats=formats, workbook_cell_formats=cell_formats))
        return tables


def values(table, number):
    matches = [row for row in table["rows"] if row["row"] == number]
    if len(matches) != 1:
        raise ValueError("Native worksheet row is absent or ambiguous")
    return {re.sub(r"[0-9]+$", "", cell["address"]): cell["value"] for cell in matches[0]["cells"]}
