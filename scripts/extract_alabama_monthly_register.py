"""Read stored workbook values and formula records without running formulas."""

import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"s": MAIN}
MONTHS = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
          "JULY", "AUGUST", "SEPTEMBER", "October")


def column_name(number):
    value = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        value = chr(65 + remainder) + value
    return value


def read_workbook(body):
    sheets = []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if any("externalLinks/" in name or name.endswith("vbaProject.bin") for name in archive.namelist()):
            raise ValueError("Unexpected external links or executable workbook content")
        strings = ["".join(node.text or "" for node in item.findall(".//s:t", NS))
                   for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        relationships = {node.attrib["Id"]: node.attrib["Target"]
                         for node in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            target = relationships[sheet.attrib["{" + DOCREL + "}id"]]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not path.startswith("xl/worksheets/") or ".." in path.split("/"):
                raise ValueError("Unexpected native worksheet relationship")
            root = ET.fromstring(archive.read(path))
            if root.find("s:dimension", NS).attrib["ref"] != "A1:V70":
                raise ValueError("Changed complete native worksheet dimensions")
            native = {node.attrib["r"]: node for node in root.findall("s:sheetData/s:row/s:c", NS)}
            cells = {}
            for row in range(1, 71):
                for column in range(1, 23):
                    address = column_name(column) + str(row)
                    node = native.get(address)
                    kind = node.get("t", "n") if node is not None else None
                    value_node = node.find("s:v", NS) if node is not None else None
                    literal = value_node.text if value_node is not None else None
                    formula = node.find("s:f", NS) if node is not None else None
                    if kind == "s" and literal is not None:
                        value = strings[int(literal)]
                    elif kind == "inlineStr":
                        value = "".join(part.text or "" for part in node.findall(".//s:t", NS))
                    elif literal is None:
                        value = None
                    elif kind in ("n", None) and re.fullmatch(r"-?\d+", literal):
                        value = int(literal)
                    else:
                        raise ValueError("Unexpected native cached value type; no coercion")
                    cells[address] = dict(value=value, raw_value=literal, source_type=kind,
                        source_cell_present=node is not None, is_formula=formula is not None,
                        stored_formula_text=(formula.text or "") if formula is not None else None,
                        stored_formula_attributes=dict(formula.attrib) if formula is not None else None)
            if set(native) - set(cells):
                raise ValueError("Native cell outside complete preserved grid")
            sheets.append(dict(name=sheet.attrib["name"], rows=70, columns=22, cells=cells,
                state=sheet.get("state", "visible"),
                merged_ranges=[node.attrib["ref"] for node in root.findall("s:mergeCells/s:mergeCell", NS)]))
    if tuple(sheet["name"] for sheet in sheets) != MONTHS:
        raise ValueError("Changed month inventory; November is not a native worksheet")
    return sheets
