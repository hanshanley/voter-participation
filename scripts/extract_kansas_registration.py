"""Freeze an independent openpyxl view of every native workbook cell."""

import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .kansas_register import WORKBOOK_SHA


def extract(workbook, output):
    import openpyxl

    if hashlib.sha256(workbook.read_bytes()).hexdigest() != WORKBOOK_SHA or output.exists():
        raise ValueError("Changed original workbook or existing independent extraction")
    native = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    cells = []
    for sheet in native:
        for row_number, row in enumerate(sheet.iter_rows(), 1):
            for column, cell in enumerate(row, 1):
                value = cell.value
                kind = "blank"
                if isinstance(value, datetime):
                    if cell.number_format != "mm-dd-yy" or value.time() != datetime.min.time():
                        raise ValueError("Unreviewed independent source date/time")
                    kind, value = "date", value.date().isoformat()
                elif isinstance(value, str):
                    kind = "text"
                elif value is not None:
                    kind, value = "number", format(Decimal(str(value)).normalize(), "f")
                address = openpyxl.utils.get_column_letter(column) + str(row_number)
                cells.append(dict(sheet=sheet.title, cell=address, kind=kind, value=value))
    native.close()
    output.mkdir()
    body = (json.dumps(cells, indent=2) + "\n").encode()
    (output / "openpyxl-cells.json").write_bytes(body)
    receipt = dict(workbook_sha256=WORKBOOK_SHA, openpyxl_version=openpyxl.__version__, cells=len(cells),
                   canonical_snapshot_sha256=hashlib.sha256(body).hexdigest(),
                   data_only_cached_values_no_formula_execution=True)
    (output / "extraction-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.workbook, args.output)
