"""Lossless factual tables; no election, count, geography or denominator qualification."""

import csv
import io
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
