"""Read literal primary-report cells without executing or recalculating a workbook."""

import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile


WORKBOOK_SHA = "b30fe348a8acd8535c9b3d3530b0a3710cfe5bb38151f2a966ae0f7a955d40c3"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_workbook(body):
    if hashlib.sha256(body).hexdigest() != WORKBOOK_SHA:
        raise ValueError("Changed original native primary workbook")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if any("externalLinks/" in name or name.endswith("vbaProject.bin") for name in archive.namelist()):
            raise ValueError("Unexpected external or executable workbook content")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("s:sheets/s:sheet", NS)
        if len(sheets) != 1 or sheets[0].get("state", "visible") != "visible":
            raise ValueError("Changed native primary worksheet inventory")
        strings = ["".join(node.text or "" for node in item.findall(".//s:t", NS))
                   for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        custom = {int(node.get("numFmtId")): node.get("formatCode")
                  for node in styles.findall("s:numFmts/s:numFmt", NS)}
        builtins = {0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%"}
        formats = [custom.get(int(node.get("numFmtId", "0")),
                             builtins.get(int(node.get("numFmtId", "0")), "unqualified_native_number_format"))
                   for node in styles.findall("s:cellXfs/s:xf", NS)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        if sheet.find("s:dimension", NS).get("ref") != "A1:G95":
            raise ValueError("Changed complete source grid")
        native = {node.get("r"): node for node in sheet.findall("s:sheetData/s:row/s:c", NS)}
        cells = {}
        for row in range(1, 96):
            for column in "ABCDEFG":
                address = column + str(row)
                node = native.get(address)
                kind = node.get("t", "n") if node is not None else None
                v = node.find("s:v", NS) if node is not None else None
                literal = v.text if v is not None else None
                formula = node.find("s:f", NS) if node is not None else None
                if formula is not None:
                    raise ValueError("Unexpected formula; no execution or replacement value")
                if kind == "s" and literal is not None:
                    value = strings[int(literal)]
                elif literal is None:
                    value = None
                elif kind == "n" and re.fullmatch(r"-?\d+", literal):
                    value = int(literal)
                elif kind == "n":
                    value = literal
                else:
                    raise ValueError("Changed native source value type")
                cells[address] = dict(value=value, raw_value=literal, source_type=kind,
                    source_cell_present=node is not None,
                    number_format=formats[int(node.get("s", "0"))] if node is not None else "General")
        if set(native) - set(cells):
            raise ValueError("Native cell outside complete preserved grid")
        return dict(sheet=sheets[0].get("name"), rows=95, columns=7, cells=cells,
                    merged_ranges=[node.get("ref") for node in sheet.findall("s:mergeCells/s:mergeCell", NS)])
