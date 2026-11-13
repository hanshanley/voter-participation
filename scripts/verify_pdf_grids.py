"""Independently decode every projected cell using pdfminer/pdfplumber."""

import argparse
import gzip
import io
import json
from pathlib import Path
import re
import sys

import fitz
import pdfplumber
from pdfplumber.utils import extract_text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_pdf import independent_reading_matrix
from scripts.native_products import encoded, pin


def independent_literal(page, box):
    left, top, right, bottom = box
    chars = [char for char in page.chars if (
        left <= (char["x0"] + char["x1"]) / 2 < right
        and top <= (char["top"] + char["bottom"]) / 2 < bottom)]
    return extract_text(chars, x_tolerance=1, y_tolerance=2).strip()


def verify(recipe, compiled, source_root):
    if (recipe["contract"] != "participation.reviewed_pdf_grids.v1"
            or compiled["contract"] != "participation.reviewed_pdf_factual_grids.v1"):
        raise ValueError("Unreviewed source/projection contract")
    if [source["id"] for source in recipe["sources"]] != [
            product["source"]["id"] for product in compiled["products"]]:
        raise ValueError("Source inventory differs")
    comparisons = dict(headers=0, labels=0, numeric_cells=0, blanks=0, native_negative_values=0)
    failures = []
    for source, product in zip(recipe["sources"], compiled["products"]):
        body = (source_root / source["filename"]).read_bytes()
        if pin(body) != source["pin"]:
            raise ValueError("Source pin changed")
        if [grid["id"] for grid in source["grids"]] != [
                grid["id"] for grid in product["tables"]]:
            raise ValueError("Projected grid inventory differs")
        with pdfplumber.open(io.BytesIO(body)) as document, fitz.open(
                stream=body, filetype="pdf") as geometry:
            if len(document.pages) != source["expected_pages"]:
                raise ValueError("Independent source page inventory differs")
            for spec, table in zip(source["grids"], product["tables"]):
                page = document.pages[spec["page"] - 1]
                inverse = ~independent_reading_matrix(geometry[spec["page"] - 1], page)
                for requirement in spec["require"]:
                    box = list(fitz.Rect(requirement["reading_bbox"]) * inverse)
                    literal = independent_literal(page, box)
                    comparisons["headers"] += 1
                    if "".join(literal.split()) != "".join(requirement["decoded_text"].split()):
                        failures.append(dict(source=source["id"], table=table["id"],
                            kind="header", expected=requirement["decoded_text"], actual=literal))
                if len(spec["rows"]) != len(table["rows"]):
                    raise ValueError("Projected row inventory differs")
                for number, (row_band, row) in enumerate(zip(spec["rows"], table["rows"]), 1):
                    if set(row["cells"]) != {field["id"] for field in spec["fields"]}:
                        raise ValueError("Projected field inventory differs")
                    for field in spec["fields"]:
                        expected = row["cells"][field["id"]]
                        declared = [field["band"][0], row_band[0], field["band"][1], row_band[1]]
                        if expected["reading_bbox"] != declared:
                            raise ValueError("Projected cell left its reviewed rectangle")
                        box = list(fitz.Rect(declared) * inverse)
                        literal = independent_literal(page, box)
                        if field["kind"] == "literal":
                            comparisons["labels"] += 1
                            agrees = "".join(literal.split()) == "".join(expected["decoded_text"].split())
                        else:
                            comparisons["numeric_cells"] += 1
                            comparisons["blanks"] += literal == ""
                            sign = "-?" if field.get("allow_negative") else ""
                            if literal == "":
                                actual, status = None, "blank"
                            elif literal in ("-", "\u2014"):
                                actual, status = None, "native_nonapplicability"
                            elif re.fullmatch(sign + r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", literal):
                                actual, status = int(literal.replace(",", "")), "reported"
                                comparisons["native_negative_values"] += actual < 0
                            else:
                                actual, status = literal, "not_one_count"
                            agrees = actual == expected["value"] and status == expected["native_status"]
                        if not agrees:
                            failures.append(dict(source=source["id"], table=table["id"],
                                row=number, field=field["id"], expected=expected, actual=literal))
    return dict(contract="participation.independent_pdf_cell_verification.v1",
        passed=not failures, comparisons=comparisons, failures=failures,
        numeric_decoder="pdfminer.six via pdfplumber; not primary MuPDF characters",
        shared_geometry_only="Reviewed rectangles and reader-frame transformation",
        whitespace_only_layout_differences_allowed_for_labels=True,
        numeric_blank_zero_sign_and_nonapplicability_compared=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    body = args.grids.read_bytes()
    if args.grids.suffix == ".gz":
        body = gzip.decompress(body)
    result = verify(json.loads(args.recipe.read_text()), json.loads(body), args.source_root)
    args.output.write_bytes(encoded(result))
    print(json.dumps({key: value for key, value in result.items() if key != "failures"}))
    if not result["passed"]:
        raise SystemExit("Independent cell decoding disagrees; no qualification")


if __name__ == "__main__":
    main()
