"""Compile pinned native factual grids and declarative queries without networking."""

import argparse
from datetime import datetime, timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import native_tabular as tabular


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def unpack(spec, body):
    if pin(body) != spec["pin"]:
        raise ValueError("Changed pinned native product: " + spec["id"])
    if spec["kind"] == "delimited":
        table = tabular.delimited(body, **spec["reader"])
        if len(table["rows"]) != spec["expected_rows"]:
            raise ValueError("Native record inventory changed")
        tables = [dict(kind="delimited", **table)]
    elif spec["kind"] == "json_records":
        table = tabular.json_records(body, **spec["reader"])
        if len(table["rows"]) != spec["expected_rows"]:
            raise ValueError("Native JSON record inventory changed")
        tables = [dict(kind="json_records", **table)]
    elif spec["kind"] == "xlsx":
        workbook = tabular.xlsx(body)
        if [table["name"] for table in workbook] != spec["sheets"]:
            raise ValueError("Native worksheet inventory changed")
        tables = [dict(kind="worksheet", **table) for table in workbook]
    elif spec["kind"] == "xlsx_zip":
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if sorted(archive.namelist()) != sorted(spec["members"]):
                raise ValueError("Native workbook inventory changed")
            tables = []
            for name, sheet_names in spec["members"].items():
                workbook = tabular.xlsx(archive.read(name))
                if [table["name"] for table in workbook] != sheet_names:
                    raise ValueError("Native worksheet inventory changed")
                tables.extend(dict(kind="worksheet", workbook=name, **table)
                    for table in workbook)
    else:
        raise ValueError("Undeclared native reader")
    return dict(contract="participation.native_factual_tables.v1",
        source={key: spec[key] for key in ("id", "url", "pin", "state_code",
            "election_year", "retrieved_at_utc", "native_updated_at", "redistribution")},
        qualification="Native facts only; no automatic geographic, turnout, or model qualification.",
        tables=tables)


def integer(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise ValueError("An absent/nonapplicable/negative value is not a recorded count")


def displayed_cell(table, cells, selector):
    if isinstance(selector, str):
        return cells.get(selector, {}).get("value")
    cell = cells.get(selector["column"], {})
    value = cell.get("value")
    if value is None or isinstance(value, str):
        return value
    if selector["display"] != "excel_month_day" or type(value) is not int:
        raise ValueError("Unqualified native display conversion")
    style = int(cell["attributes"].get("s", "0"))
    number_format = table["workbook_cell_formats"][style]["numFmtId"]
    code = table["workbook_number_formats"].get(number_format)
    if code not in (r"mm\-dd", r"m\-d"):
        return value
    if value < 1:
        raise ValueError("Unqualified native month-day serial")
    date1904 = table["workbook_properties"].get("date1904", "0")
    if date1904 not in ("0", "1", "false", "true"):
        raise ValueError("Unknown native workbook date system")
    if date1904 in ("1", "true"):
        epoch = datetime(1904, 1, 1)
    else:
        if value == 60:
            raise ValueError("Fictional Excel leap day cannot be a native precinct label")
        epoch = datetime(1899, 12, 31) if value < 60 else datetime(1899, 12, 30)
    date = epoch + timedelta(days=value)
    return date.strftime("%m-%d") if code == r"mm\-dd" else f"{date.month}-{date.day}"


def query(product, spec):
    selected = [table for table in product["tables"] if (
        spec.get("workbook") == table.get("workbook")
        and (not spec.get("tables") or table.get("name") in spec["tables"]))]
    if not selected or (spec.get("tables") and
            [table.get("name") for table in selected] != spec["tables"]):
        raise ValueError("Query table inventory differs")
    output = []
    for table in selected:
        if table["kind"] in ("delimited", "json_records"):
            indices = {field: tabular.column(table, label)
                for field, label in spec["fields"].items()}
            source_rows = [(row["row"], {field: row["values"][index]
                for field, index in indices.items()}) for row in table["rows"]]
        else:
            for number, columns in spec.get("require", {}).items():
                actual = tabular.values(table, int(number))
                if any(actual.get(column) != expected for column, expected in columns.items()):
                    raise ValueError("Declared worksheet header changed")
            source_rows = []
            for row in table["rows"]:
                if not spec.get("first_row", 1) <= row["row"] <= spec.get("last_row", float("inf")):
                    continue
                cells = {re.sub(r"[0-9]+$", "", cell["address"]): cell for cell in row["cells"]}
                source_rows.append((row["row"], {
                    field: (table["name"] if selector == "$table" else
                        displayed_cell(table, cells, selector))
                    for field, selector in spec["fields"].items()}))
        for number, fields in source_rows:
            if any(fields[field] not in allowed for field, allowed in spec.get("where", {}).items()):
                continue
            if any(fields[field] in excluded for field, excluded in spec.get("exclude", {}).items()):
                continue
            for field in spec.get("counts", []):
                fields[field] = integer(fields[field])
            reference = dict(table=table.get("name"), workbook=table.get("workbook"))
            reference["record_index" if table["kind"] == "json_records" else "row"] = number
            output.append(dict(**fields, source_rows=[reference]))
    keys, result = {}, []
    for row in output:
        key = tuple(row[field] for field in spec["keys"])
        if key in keys:
            if not spec.get("deduplicate"):
                raise ValueError("Repeated native query key")
            previous = keys[key]
            if {k: v for k, v in row.items() if k != "source_rows"} != {
                    k: v for k, v in previous.items() if k != "source_rows"}:
                raise ValueError("Repeated native unit disagrees")
            previous["source_rows"].extend(row["source_rows"])
        else:
            keys[key] = row
            result.append(row)
    if not result:
        raise ValueError("A declared query cannot silently become empty")
    return dict(id=spec["id"], product=spec["product"],
        count_fields=spec.get("counts", []), rows=result)


def compile_products(recipe, source_root, output):
    if recipe["contract"] != "participation.native_product_recipe.v1":
        raise ValueError("Unsupported native recipe")
    if output.exists():
        raise ValueError("Use a fresh output directory")
    ids = [row["id"] for row in recipe["products"]]
    query_ids = [row["id"] for row in recipe["queries"]]
    if (len(set(ids)) != len(ids) or len(set(query_ids)) != len(query_ids)
            or any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) for name in ids + query_ids)):
        raise ValueError("Ambiguous or unsafe product/query identity")
    for spec in recipe["products"]:
        path = PurePosixPath(spec["path"])
        if (path.is_absolute() or ".." in path.parts or "\\" in spec["path"]
                or not (source_root / spec["path"]).resolve().is_relative_to(source_root.resolve())):
            raise ValueError("Native input must remain within the supplied source root")
        body = (source_root / spec["path"]).read_bytes()
        if pin(body) != spec["pin"]:
            raise ValueError("Changed pinned native product: " + spec["id"])
    output.mkdir(parents=True)
    products, queries = {}, {}
    for spec in recipe["products"]:
        product = unpack(spec, (source_root / spec["path"]).read_bytes())
        body = gzip.compress(encoded(product), mtime=0)
        name = spec["id"] + ".factual-tables.json.gz"
        (output / name).write_bytes(body)
        products[name] = pin(body)
        for selection in recipe["queries"]:
            if selection["product"] == spec["id"]:
                queries[selection["id"]] = query(product, selection)
    if set(queries) != set(query_ids):
        raise ValueError("A declared query refers to an absent product")
    body = encoded(dict(contract="participation.native_queries.v1", queries=queries))
    (output / "complete-queries.json").write_bytes(body)
    products["complete-queries.json"] = pin(body)
    manifest = dict(contract="participation.native_product_compilation.v1",
        recipe_pin=pin(encoded(recipe)), outputs=products,
        source_acquisitions=0, source_count_repairs=0,
        automatic_geographic_or_turnout_qualification=False)
    (output / "manifest.json").write_bytes(encoded(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compile_products(json.loads(args.recipe.read_bytes()), args.sources, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
