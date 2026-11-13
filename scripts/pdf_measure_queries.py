"""Export every measured PDF cell with its original status, frame and provenance."""

import argparse
import csv
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
