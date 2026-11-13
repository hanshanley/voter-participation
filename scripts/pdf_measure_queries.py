"""Export every measured PDF cell with its original status, frame and provenance."""

import argparse
import csv
from decimal import Decimal
import gzip
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded, pin


def queries(grids):
    if grids["contract"] != "participation.reviewed_pdf_factual_grids.v1":
        raise ValueError("Unreviewed factual PDF grid contract")
    rows = []
    identities = set()
    for product in grids["products"]:
        source = product["source"]
        for table in product["tables"]:
            for record in table["rows"]:
                unit = record["cells"]["native_unit"]["value"]
                for measure, cell in sorted(record["cells"].items()):
                    if measure == "native_unit":
                        continue
                    identity = (source["id"], table["id"], record["row"], measure)
                    if identity in identities:
                        raise ValueError("A factual cell cannot appear twice in a complete query")
                    identities.add(identity)
                    rows.append(dict(source_id=source["id"], source_url=source["url"],
                        source_pin=source["pin"], table_id=table["id"],
                        page=table["source_page"], row=record["row"], native_unit=unit,
                        source_role=table["source_role"],
                        source_annotations=table.get("source_annotations", {}),
                        measure=measure, value=cell["value"], native_status=cell["native_status"],
                        reading_bbox=cell["reading_bbox"],
                        reading_text=cell.get("decoded_text", cell.get("reviewed_text")),
                        source_method=cell.get("source_method", "decoded_PDF_characters")))
    if not rows:
        raise ValueError("A complete factual query cannot be empty")
    return dict(contract="participation.complete_pdf_measure_queries.v1",
        rows=rows, source_count_repairs=0,
        absent_source_columns_not_synthesized_as_blank_or_zero=True,
        automatic_geographic_or_model_qualification=False)


def csv_body(result):
    stream = io.StringIO(newline="")
    columns = ["source_id", "table_id", "page", "row", "native_unit", "measure",
        "value_json", "native_status", "reading_text", "reading_bbox_json",
        "source_method", "source_role", "source_url", "source_sha256",
        "source_annotations_json"]
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in result["rows"]:
        output = {key: row[key] for key in columns if key in row}
        output.update(value_json=json.dumps(row["value"], ensure_ascii=True, allow_nan=False),
            reading_bbox_json=json.dumps(row["reading_bbox"], separators=(",", ":"), allow_nan=False),
            source_sha256=row["source_pin"]["sha256"],
            source_annotations_json=json.dumps(row["source_annotations"],
                sort_keys=True, separators=(",", ":"), allow_nan=False))
        writer.writerow(output)
    return stream.getvalue().encode()


def wide_queries(grids, recipe):
    if (grids["contract"] != "participation.reviewed_pdf_factual_grids.v1"
            or recipe["contract"] != "participation.reviewed_pdf_wide_queries.v1"):
        raise ValueError("Reviewed factual grids and wide-query recipe are required")
    queries = {}
    for selection in recipe["selections"]:
        if selection["id"] in queries:
            raise ValueError("Repeated wide-query identity")
        products = [item for item in grids["products"]
            if item["source"]["id"] == selection["source_id"]]
        if len(products) != 1:
            raise ValueError("Wide-query source identity is ambiguous")
        identifiers = selection["table_ids"]
        tables = {table["id"]: table for table in products[0]["tables"] if table["id"] in identifiers}
        if (not identifiers or len(set(identifiers)) != len(identifiers)
                or set(tables) != set(identifiers)
                or sum(table["id"] in identifiers for table in products[0]["tables"]) != len(identifiers)):
            raise ValueError("Wide-query table inventory differs")
        carry = selection.get("carry_forward", {})
        if carry and not selection.get("carry_review_evidence"):
            raise ValueError("Source-label carry requires explicit native grouping review")
        rows, remembered, identities = [], {}, set()
        for identifier in identifiers:
            table = tables[identifier]
            for record in table["rows"]:
                identity = (identifier, record["row"])
                if identity in identities:
                    raise ValueError("Repeated wide-query factual row")
                identities.add(identity)
                row = {name: cell["value"] for name, cell in record["cells"].items()}
                if {"source_rows", "derived_label_sources"} & (set(row) | set(carry)):
                    raise ValueError("Native or derived fields cannot replace query provenance")
                reference = dict(table=identifier, page=table["source_page"], row=record["row"])
                for target, source in carry.items():
                    if target in row or source not in row:
                        raise ValueError("Derived carry cannot overwrite or invent a native field")
                    if row[source] not in (None, ""):
                        remembered[target] = (row[source], reference)
                if any(row[name] not in allowed for name, allowed in selection.get("where", {}).items()):
                    continue
                if any(row[name] in excluded for name, excluded in selection.get("exclude", {}).items()):
                    continue
                if any(target not in remembered for target in carry):
                    raise ValueError("Native parent label is absent before a selected reporting row")
                for target in carry:
                    row[target] = remembered[target][0]
                if carry:
                    row["derived_label_sources"] = {target: remembered[target][1] for target in carry}
                if any(type(row[name]) is not int for name in selection.get("counts", [])):
                    raise ValueError("Unknown native count cannot be coerced in a wide query")
                rows.append(dict(row, source_rows=[reference]))
        if not rows or len(rows) != selection["expected_rows"]:
            raise ValueError("Reviewed wide-query row inventory differs")
        queries[selection["id"]] = dict(rows=rows)
    result = dict(contract="participation.complete_pdf_wide_queries.v1",
        queries=queries, checks=recipe["checks"], source_count_repairs=0,
        automatic_geographic_or_model_qualification=False)
    if recipe.get("percent_changes"):
        checks = []
        for definition in recipe["percent_changes"]:
            for row in queries[definition["query"]]["rows"]:
                current, previous = row[definition["current"]], row[definition["previous"]]
                literal = row[definition["printed"]]
                check = dict(source_rows=row["source_rows"], native_unit=row["native_unit"],
                    field=definition["printed"], current=current, previous=previous, native_literal=literal)
                if type(current) is not int or type(previous) is not int or current < 0 or previous <= 0:
                    check["status"] = "unqualified_native_percent_change"
                else:
                    if not isinstance(literal, str) or not literal.endswith("%"):
                        raise ValueError("Native percent-change literal changed")
                    printed = Decimal(literal[:-1])
                    exact = Decimal(100) * (current-previous) / previous
                    tolerance = Decimal("0.5") * Decimal(10) ** printed.as_tuple().exponent
                    check.update(exact_percent_change=str(exact),
                        signed_printed_minus_exact_pp=str(printed-exact),
                        native_precision_tolerance_pp=str(tolerance),
                        status="matched" if abs(printed-exact) <= tolerance else "discrepancy")
                checks.append(check)
        result["native_stock_percent_change_checks"] = checks
        result["registration_stock_changes_not_person_transitions"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete-query output directory")
    body = args.grids.read_bytes()
    if args.grids.suffix == ".gz":
        body = gzip.decompress(body)
    result = queries(json.loads(body))
    args.output.mkdir(parents=True)
    json_path, csv_path = args.output / "complete-queries.json.gz", args.output / "complete-queries.csv.gz"
    json_path.write_bytes(gzip.compress(encoded(result), mtime=0))
    csv_path.write_bytes(gzip.compress(csv_body(result), mtime=0))
    print(json.dumps(dict(rows=len(result["rows"]), files={
        path.name: pin(path.read_bytes()) for path in (json_path, csv_path)})))


if __name__ == "__main__":
    main()
