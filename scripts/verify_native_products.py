"""Independently verify every exported source record and cached/formula cell."""

import argparse
import csv
from datetime import datetime, time, timedelta
from decimal import Decimal
import gzip
import io
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

import openpyxl
from openpyxl.utils.datetime import from_excel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded, pin

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def verify(recipe, source_root, compiled):
    manifest = json.loads((compiled / "manifest.json").read_bytes())
    if manifest["recipe_pin"] != pin(encoded(recipe)):
        raise ValueError("The compiled recipe differs")
    for name, expected in manifest["outputs"].items():
        if pin((compiled / name).read_bytes()) != expected:
            raise ValueError("Changed compiled output: " + name)
    queries = json.loads((compiled / "complete-queries.json").read_bytes())["queries"]
    reports = []
    for spec in recipe["products"]:
        body = (source_root / spec["path"]).read_bytes()
        if pin(body) != spec["pin"]:
            raise ValueError("Changed independent source")
        product = json.loads(gzip.decompress(
            (compiled / (spec["id"] + ".factual-tables.json.gz")).read_bytes()))
        if spec["kind"] == "delimited":
            native = list(csv.reader(io.StringIO(body.decode(
                spec["reader"].get("encoding", "utf-8-sig")), newline=""),
                delimiter=spec["reader"].get("delimiter", ","), strict=True))
            table = product["tables"][0]
            restored = table["preamble"] + [table["header"]] + [row["values"] for row in table["rows"]]
            if native != restored or len(table["rows"]) != spec["expected_rows"]:
                raise ValueError("A complete delimited source record changed")
            reports.append(dict(product=spec["id"], data_rows=len(table["rows"]),
                full_source_values_checked=sum(map(len, native))))
            continue
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            for member in spec["members"]:
                workbook_body = archive.read(member)
                selected = [table for table in product["tables"] if table["workbook"] == member]
                report = dict(product=spec["id"], workbook=member,
                    sheets=len(selected), rows=0, cells=0, formulas=0,
                    explicit_blank_cells=0, native_nonapplicable_cells=0, zero_cells=0,
                    independently_checked_precinct_labels=0)
                with zipfile.ZipFile(io.BytesIO(workbook_body)) as workbook_zip:
                    for table in selected:
                        source = ET.fromstring(workbook_zip.read(table["member"]))
                        native_rows = source.findall("{" + NS + "}sheetData/{" + NS + "}row")
                        if [(int(row.attrib["r"]), [cell.attrib["r"] for cell in
                                row.findall("{" + NS + "}c")]) for row in native_rows] != [
                                (row["row"], [cell["address"] for cell in row["cells"]])
                                for row in table["rows"]]:
                            raise ValueError("Native row/cell inventory changed")
                        report["rows"] += len(table["rows"])
                for data_only in (True, False):
                    workbook = openpyxl.load_workbook(io.BytesIO(workbook_body),
                        read_only=True, data_only=data_only, keep_links=False)
                    try:
                        for table in selected:
                            native_cells = {cell["address"]: cell
                                for row in table["rows"] for cell in row["cells"]}
                            worksheet = workbook[table["name"]]
                            worksheet.reset_dimensions()
                            checked = set()
                            for row in worksheet.iter_rows():
                                for cell in row:
                                    address = getattr(cell, "coordinate", None)
                                    if address not in native_cells:
                                        if cell.value is not None:
                                            raise ValueError("An independent nonblank cell was omitted")
                                        continue
                                    native = native_cells[address]
                                    checked.add(address)
                                    if not data_only:
                                        if native["formula"] is not None and native["formula"]["text"] is not None:
                                            if cell.value != "=" + native["formula"]["text"]:
                                                raise ValueError("Native formula text changed")
                                        continue
                                    actual, expected = cell.value, native["value"]
                                    if isinstance(actual, (datetime, time, timedelta)):
                                        same = actual == from_excel(float(native["cached_literal"]), workbook.epoch)
                                    elif type(actual) in (int, float) and native["storage_type"] == "n":
                                        same = Decimal(str(actual)) == Decimal(native["cached_literal"])
                                    else:
                                        same = actual == expected and type(actual) is type(expected)
                                    if not same:
                                        raise ValueError("Independent cached value differs: " +
                                            member + " / " + table["name"] + " / " + address)
                                    report["cells"] += 1
                                    report["formulas"] += native["formula"] is not None
                                    report["explicit_blank_cells"] += expected is None
                                    report["native_nonapplicable_cells"] += expected == "-"
                                    report["zero_cells"] += type(expected) is int and expected == 0
                                    if (member == "2026 County General PbP - OFFICIAL.xlsx"
                                            and address.startswith("A") and address[1:].isdigit()
                                            and isinstance(actual, datetime)):
                                        query_rows = queries["wy-precinct-house"]["rows"]
                                        matches = [item for item in query_rows if item["county"] == table["name"]
                                            and item["precinct_native_value"] == expected]
                                        code = cell.number_format
                                        label = actual.strftime("%m-%d") if code == r"mm\-dd" else (
                                            f"{actual.month}-{actual.day}" if code == r"m\-d" else None)
                                        if len(matches) != 1 or matches[0]["precinct"] != label:
                                            raise ValueError("Independent native display-label derivation differs")
                                        report["independently_checked_precinct_labels"] += 1
                            if checked != set(native_cells):
                                raise ValueError("An explicit native cell escaped independent verification")
                    finally:
                        workbook.close()
                reports.append(report)
    return dict(contract="participation.native_product_independent_verification.v1",
        status="passed", source_count_repairs=0, executed_formulas=0,
        all_native_records_and_cells_verified=True, reports=reports)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh independent verification output")
    result = verify(json.loads(args.recipe.read_bytes()), args.sources, args.compiled)
    args.output.write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
