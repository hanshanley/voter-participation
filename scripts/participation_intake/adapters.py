"""Small direct CSV, JSON/API, PDF and native-statistics adapters."""

import csv
import gzip
import io
import json
import re

from .contract import IntakeError, VERSION, count, observation_id, validate_all


FORBIDDEN_FIELDS = {"candidatevotes", "candidatevotetotal", "totalvotes", "demvotes", "repvotes"}
PRIVATE_FIELDS = {"voterid", "ssn", "socialsecuritynumber", "birthdate", "dateofbirth",
                  "firstname", "lastname", "residentialaddress", "mailingaddress"}


def field(row, path, default=None):
    value = row
    for part in str(path).split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return default
    return value


def check_fields(row, count_field):
    names = {re.sub(r"[^a-z0-9]", "", str(key).lower()) for key in row}
    if names & PRIVATE_FIELDS:
        raise IntakeError("private_record_input", "This intake accepts public aggregate rows, not voter/person records")
    for value in row.values():
        if isinstance(value, dict):
            check_fields(value, count_field)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    check_fields(item, count_field)
    if re.sub(r"[^a-z0-9]", "", count_field.lower()) in FORBIDDEN_FIELDS:
        raise IntakeError("candidate_vote_substitution", "The selected count field is a candidate/contest vote total")


def make_row(spec, native, index, input_pin, clock, references):
    mapping = spec["columns"]
    check_fields(native, mapping["count"])
    identity_fields = mapping["geography_id"]
    parts = [field(native, name) for name in identity_fields] if isinstance(identity_fields, list) else [field(native, identity_fields)]
    if not parts or any(part is None or part == "" for part in parts):
        raise IntakeError("geographic_scope", "Source row has no declared geographic identity")
    geo_key = "|".join(str(part) for part in parts)
    lookup = references.get("identities", {}).get(geo_key)
    level = spec["geography"]["level"]
    geo = dict(id=lookup["id"] if lookup else geo_key,
        name=lookup["name"] if lookup else str(field(native, mapping.get("geography_name", ""), geo_key)),
        state_code=spec["geography"]["state_code"], level=level,
        parent_id=lookup.get("parent_id") if lookup else None,
        join=dict(status="approved" if lookup else "unreviewed",
            reference_id=lookup.get("reference_id") if lookup else None,
            feature_key=lookup.get("feature_key") if lookup else None,
            evidence=lookup.get("evidence") if lookup else None))
    reported_field = mapping.get("reported")
    missing = object()
    literal = field(native, mapping["count"], missing)
    if literal is missing:
        raise IntakeError("source_schema", "The registered count field is absent, not a reported unknown")
    if reported_field:
        flag = field(native, reported_field, missing)
        if flag is missing or str(flag) not in {
                str(mapping.get("reported_value", "1")), *map(str, mapping.get("unreported_values", ["0"]))}:
            raise IntakeError("source_schema", "Native reporting flag is missing or unrecognized")
        reported = str(flag) == str(mapping.get("reported_value", "1"))
    else:
        reported = literal not in (None, "")
    value = count(literal) if reported else None
    if reported and value is None:
        raise IntakeError("missing_reported_count", "Reported source flag has no numerical count")
    denominator_fields = mapping.get("denominator", [])
    denominator_fields = [denominator_fields] if isinstance(denominator_fields, str) else denominator_fields
    denominator_values = [count(field(native, name)) for name in denominator_fields]
    denominator = None
    if denominator_fields:
        supplied = reported and all(value is not None for value in denominator_values)
        denominator = dict(value=sum(denominator_values) if supplied else None,
            literal=spec["denominator"]["literal"], basis=spec["denominator"]["basis"], qualified=False)
    conflicts = []
    components = mapping.get("components", [])
    if reported and components:
        values = [count(field(native, name)) for name in components]
        if any(value is None for value in values):
            raise IntakeError("missing_component", "A declared native accounting component is absent")
        residual = value - sum(values)
        if residual:
            conflicts.append(dict(code="component_conflict", residual=residual, repaired=False))
    if value is not None and denominator and denominator["value"] is not None and value > denominator["value"]:
        conflicts.append(dict(code="electorate_excess", excess=value-denominator["value"], repaired=False))
    if denominator:
        denominator["qualified"] = (level in spec.get("rate_levels", []) and reported
            and denominator["value"] is not None and denominator["value"] > 0 and not conflicts)
    measure = dict(spec["measure"])
    row_id = observation_id(spec["id"], spec["election"]["id"], geo["id"], measure["id"], measure["mode"])
    return dict(contract=VERSION, id=row_id, election=dict(spec["election"]), geography=geo,
        measure=measure, count=dict(value=value, status="reported" if reported else "unknown", literal=literal),
        denominator=denominator, source_clock=dict(clock),
        reporting_status=dict(literal=spec.get("reporting_status"), reported_units=1 if reported else 0,
            total_units=1, complete=reported),
        source=dict(id=spec["id"], url=spec["inputs"][spec["primary_input"]]["url"],
            input_sha256=input_pin["sha256"], selector=dict(row=index),
            classification=spec["classification"], fields=native),
        quality=dict(conflicts=conflicts, notes=list(spec.get("notes", []))))


def delimited(spec, inputs):
    options = spec.get("format", {})
    try:
        text = inputs[spec["primary_input"]].decode(options.get("encoding", "utf-8-sig"))
        rows = list(csv.DictReader(io.StringIO(text), delimiter=options.get("delimiter", ","),
                                  fieldnames=options.get("fieldnames"), strict=True))
    except (UnicodeError, csv.Error) as error:
        raise IntakeError("source_schema", "Native delimited product could not be decoded completely") from error
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise IntakeError("source_schema", "Native delimited rows have missing or extra columns")
    return rows


def json_records(spec, inputs):
    try:
        body = inputs[spec["primary_input"]]
        if spec.get("format", {}).get("compression") == "gzip":
            body = gzip.decompress(body)
        data = json.loads(body)
    except (ValueError, UnicodeError, OSError, EOFError) as error:
        raise IntakeError("source_schema", "Native API/JSON product is not valid complete JSON") from error
    for path, expected in spec.get("format", {}).get("assert_fields", {}).items():
        if field(data, path) != expected:
            raise IntakeError("election_scope", "Native JSON election/product control changed: " + path)
    path = spec.get("format", {}).get("items_path")
    rows = field(data, path) if path else data
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise IntakeError("source_schema", "The declared API/JSON path must contain aggregate objects")
    return rows


def pdf_records(spec, inputs):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError as error:
        raise IntakeError("missing_pdf_reader", "The PDF adapter requires the existing pypdf parser") from error
    try:
        reader = PdfReader(io.BytesIO(inputs[spec["primary_input"]]))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, ValueError, UnicodeError) as error:
        raise IntakeError("source_schema", "Native PDF could not be extracted completely") from error
    options = spec["format"]
    text = "\n".join(pages)
    if not re.search(options["election_pattern"], text):
        raise IntakeError("election_scope", "Native PDF election header does not match the registered product")
    rows = [match.groupdict() for match in re.finditer(options["row_pattern"], text, re.MULTILINE)]
    if not rows:
        raise IntakeError("source_schema", "No native PDF rows match; missing extraction is not zero")
    return rows


ADAPTERS = {"csv": delimited, "json": json_records, "pdf": pdf_records}


def component_cells(binding, table, row):
    components = binding.get("components")
    if (binding.get("operation") != "component_sum"
            or binding.get("value_scope", "cell") != "cell" or binding.get("parse") != "count"
            or not binding.get("sum_review_evidence")
            or not binding.get("same_measure_review_evidence")
            or not isinstance(components, list) or len(components) < 2
            or any(not isinstance(item, dict) or not isinstance(item.get("measure"), str)
                   or not isinstance(item.get("native_header"), str) or not item["native_header"].strip()
                   for item in components)
            or len({item["measure"] for item in components}) != len(components)
            or "measure" in binding):
        raise IntakeError("source_fact_binding", "Component sums require distinct reviewed native count columns")
    cells = []
    for component in components:
        measure = component["measure"]
        if measure not in row["cells"]:
            raise IntakeError("source_fact_binding", "Native component cell is absent")
        cell = row["cells"][measure]
        requirements = table.get("native_requirements")
        if requirements is not None:
            index = component.get("header_requirement")
            if type(index) is not int or not 0 <= index < len(requirements):
                raise IntakeError("source_fact_binding", "Native component header selector is absent")
            header = requirements[index]
            value_box, header_box = cell.get("reading_bbox"), header.get("reading_bbox")
            if (not value_box or not header_box
                    or value_box[0] != header_box[0] or value_box[2] != header_box[2]
                    or header_box[3] > value_box[1]
                    or " ".join(header["decoded_text"].split())
                    != " ".join(component["native_header"].split())):
                raise IntakeError("source_fact_binding", "Native component header or physical column changed")
        else:
            annotations = table.get("source_annotations", {})
            image = annotations.get("reviewed_image_pin", {})
            method = "visually_reviewed_source_image_transcription"
            if (not binding.get("visual_header_review_evidence")
                    or annotations.get("source_method") != method or cell.get("source_method") != method
                    or not re.fullmatch(r"[a-f0-9]{64}", str(image.get("sha256", "")))
                    or type(image.get("bytes")) is not int or image["bytes"] <= 0):
                raise IntakeError("source_fact_binding", "Image components require the pinned explicit visual review")
        cells.append(cell)
    return cells


def factual_cells(binding, product):
    if "components" in binding and binding.get("operation") != "component_sum":
        raise IntakeError("source_fact_binding", "Component columns require their explicit sum operation")
    identifiers = binding.get("table_ids", [binding.get("table_id")])
    if (not identifiers or None in identifiers or len(set(identifiers)) != len(identifiers)
            or "table_ids" in binding and "table_id" in binding):
        raise IntakeError("source_fact_binding", "Native table selection must be explicit and unique")
    tables = [table for table in product["tables"] if table["id"] in identifiers]
    roles = (
            "unofficial_registration_ballot_reported_turnout_statistics",
            "native_registration_ballot_reported_turnout_statistics")
    if binding.get("administrative_measure_review_evidence"):
        roles += ("unofficial_administrative_measures_not_candidate_returns",)
    if (len(tables) != len(identifiers) or {table["id"] for table in tables} != set(identifiers)
            or any(table["source_role"] not in roles for table in tables)):
        raise IntakeError("source_fact_binding", "Participation updates require reviewed ballot statistics, not choices")
    scope = binding.get("value_scope", "cell")
    cells = []
    identities = set()
    if scope == "cell":
        normalize = (lambda value: " ".join(value.split())) if binding.get(
            "reading_whitespace_normalized") else (lambda value: value)
        required = binding.get("where_nonempty", [])
        for table in tables:
            for row in table["rows"]:
                if any(name not in row["cells"] for name in ["native_unit"] + required):
                    raise IntakeError("source_fact_binding", "Native row selector field is absent")
                if (normalize(row["cells"]["native_unit"]["value"]) == normalize(binding["native_unit"])
                        and all(row["cells"][name]["value"] not in (None, "") for name in required)):
                    if binding.get("operation") == "component_sum":
                        identity = (table["id"], row.get("row"))
                        if type(identity[1]) is not int or identities:
                            raise IntakeError("source_fact_binding", "Component sums require exactly one native parent row")
                        identities.add(identity)
                        cells.extend(component_cells(binding, table, row))
                        continue
                    if binding["measure"] not in row["cells"]:
                        raise IntakeError("source_fact_binding", "Native statistical cell is absent")
                    if binding.get("operation") == "sum":
                        identity = (table["id"], row.get("row"))
                        if type(identity[1]) is not int or identity in identities:
                            raise IntakeError("source_fact_binding", "Summed native rows need unique factual identities")
                        identities.add(identity)
                    cells.append(row["cells"][binding["measure"]])
    elif scope in ("source", "annotations"):
        containers = [product["source"]] if scope == "source" else [
            table["source_annotations"] for table in tables]
        for container in containers:
            missing = object()
            value = field(container, binding["value_path"], missing)
            if value is missing:
                raise IntakeError("source_fact_binding", "Native provenance or clock field is absent")
            cells.append(dict(value=value, native_status="literal"))
    else:
        raise IntakeError("source_fact_binding", "Unsupported factual value scope")
    return tables, cells


def native_query_cells(binding, product, spec, inputs, cache):
    from scripts.native_products import query
    from scripts.native_tabular import column as native_column, values

    recipe_name = binding.get("query_recipe_input")
    if recipe_name not in inputs or recipe_name not in spec["inputs"]:
        raise IntakeError("source_fact_binding", "A complete declared native query recipe is required")
    if (binding.get("source_role") not in (
            "unofficial_registration_ballot_reported_turnout_statistics",
            "native_registration_ballot_reported_turnout_statistics")
            or not binding.get("same_measure_review_evidence")
            or not isinstance(binding.get("native_measure_header"), str)):
        raise IntakeError("source_fact_binding", "Native table bindings need reviewed statistical measure equivalence")
    key = (binding["input"], recipe_name, binding.get("native_query_id"))
    if key not in cache:
        try:
            recipe = json.loads(inputs[recipe_name])
            if recipe["contract"] != "participation.native_product_recipe.v1":
                raise ValueError("Native query recipe contract changed")
            sources = [s for s in recipe["products"] if s["id"] == binding["source_id"]]
            queries = [q for q in recipe["queries"] if q["id"] == binding["native_query_id"]]
            source = product["source"]
            if (len(sources) != 1 or len(queries) != 1
                    or queries[0]["product"] != source["id"]
                    or any(source[name] != sources[0][name] for name in (
                        "id", "url", "pin", "state_code", "election_year",
                        "retrieved_at_utc", "native_updated_at"))
                    or source["state_code"] != spec["geography"]["state_code"]
                    or source["election_year"] != spec["election"]["year"]):
                raise ValueError("Native query source, election or jurisdiction changed")
            selected = queries[0]
            tables = [t for t in product["tables"] if t.get("workbook") == selected.get("workbook")
                      and (not selected.get("tables") or t["name"] in selected["tables"])]
            cache[key] = selected, tables, query(product, selected)
        except (KeyError, TypeError, ValueError) as error:
            raise IntakeError("source_fact_binding", "Native source/query agreement failed: " + str(error)) from error
    selected, tables, result = cache[key]
    measure = binding["measure"]
    column = selected["fields"].get(measure)
    header_row = binding.get("native_header_row")
    if measure not in result["count_fields"] or not isinstance(column, str):
        raise IntakeError("source_fact_binding", "A direct native statistical count column/header is required")
    table_views = []
    for table in tables:
        if table["kind"] in ("delimited", "json_records"):
            if header_row is not None or re.sub(r"[^a-z0-9]", "", column.lower()) in FORBIDDEN_FIELDS:
                raise IntakeError("source_fact_binding", "Native record fields are not worksheet or candidate columns")
            actual = table["header"][native_column(table, column)]
        else:
            if not re.fullmatch(r"[A-Z]+", column) or type(header_row) is not int or header_row <= 0:
                raise IntakeError("source_fact_binding", "A direct native statistical count column/header is required")
            actual = values(table, header_row).get(column)
            required = selected.get("require", {}).get(str(header_row), {}).get(column)
            if not isinstance(actual, str) or required != actual:
                raise IntakeError("source_fact_binding", "Native statistical header needs its complete recipe guard")
        table_views.append(dict(source_annotations=dict(native_column_headers={measure: actual})))
    selectors = binding.get("native_record", {})
    matches = [r for r in result["rows"] if selectors and all(
        field(r, path) == value for path, value in selectors.items())]
    if len(matches) != 1:
        raise IntakeError("source_fact_binding", "Native statistical query row is absent or ambiguous")
    scope = binding.get("value_scope", "cell")
    if scope == "cell":
        value = matches[0][measure]
    elif scope == "row":
        path = binding.get("value_path")
        field_column = selected["fields"].get(path)
        if (binding.get("parse", "literal") != "literal" or not isinstance(field_column, str)
                or not tables or any(table["kind"] not in ("delimited", "json_records") for table in tables)):
            raise IntakeError("source_fact_binding", "Native record literals require an exact non-count field")
        for table in tables:
            native_column(table, field_column)
        value = matches[0][path]
    elif scope == "source":
        missing = object()
        value = field(product["source"], binding["value_path"], missing)
        if value is missing:
            raise IntakeError("source_fact_binding", "Native source provenance field is absent")
    else:
        raise IntakeError("source_fact_binding", "Unsupported native query value scope")
    return table_views, [dict(value=value, native_status="reported" if scope == "cell" else "literal")]


def verify_fact_bindings(spec, rows, inputs):
    decoded, native_cache = {}, {}
    for binding in spec.get("format", {}).get("fact_bindings", []):
        name, compression = binding["input"], binding.get("compression")
        if name not in inputs or name not in spec["inputs"] or compression not in (None, "gzip"):
            raise IntakeError("source_fact_binding", "Undeclared factual input or compression")
        key = (name, compression)
        if key not in decoded:
            try:
                body = gzip.decompress(inputs[name]) if compression == "gzip" else inputs[name]
                decoded[key] = json.loads(body)
            except (ValueError, UnicodeError, OSError, EOFError) as error:
                raise IntakeError("source_fact_binding", "Factual grid is not complete declared JSON") from error
        data = decoded[key]
        if not isinstance(data, dict) or data.get("contract") not in (
                "participation.reviewed_pdf_factual_grids.v1", "participation.native_factual_tables.v1",
                "participation.selected_html_statistics.v1"):
            raise IntakeError("source_fact_binding", "Factual grid contract changed")
        native = data["contract"] == "participation.native_factual_tables.v1"
        html_statistics = data["contract"] == "participation.selected_html_statistics.v1"
        if binding.get("operation") == "component_sum" and (native or html_statistics):
            raise IntakeError("source_fact_binding", "Component sums require reviewed factual PDF columns")
        products = [data] if native or html_statistics else data.get("products")
        if not isinstance(products, list):
            raise IntakeError("source_fact_binding", "Factual product inventory changed")
        selected = [row for row in rows if binding["record"] and all(
            field(row, path) == value for path, value in binding["record"].items())]
        products = [product for product in products
            if product["source"]["id"] == binding["source_id"]]
        if len(selected) != 1 or len(products) != 1:
            raise IntakeError("source_fact_binding", "Canonical or native product identity is ambiguous")
        if html_statistics:
            from scripts.html_statistics import binding_cells
            try:
                tables, cells = binding_cells(binding, products[0], spec, inputs)
            except (KeyError, TypeError, ValueError) as error:
                raise IntakeError("source_fact_binding", str(error)) from error
        else:
            tables, cells = (native_query_cells(binding, products[0], spec, inputs, native_cache)
                             if native else factual_cells(binding, products[0]))
        scope = binding.get("value_scope", "cell")
        parse = binding.get("parse", "literal")
        operation = binding.get("operation", "unique")
        if operation in ("sum", "component_sum"):
            if scope != "cell" or parse != "count" or not binding.get("sum_review_evidence"):
                raise IntakeError("source_fact_binding", "Only explicitly reviewed statistical counts may be summed")
        elif operation != "unique":
            raise IntakeError("source_fact_binding", "Unsupported factual operation")
        ambiguous = len(cells) != 1 if scope == "cell" else (
            cells and any(cell["value"] != cells[0]["value"] for cell in cells))
        if not cells or operation == "unique" and ambiguous:
            raise IntakeError("source_fact_binding", "Native statistical cell is absent or ambiguous")
        if parse == "count":
            if scope != "cell":
                raise IntakeError("source_fact_binding", "Provenance metadata cannot authorize a statistical count")
            if any(cell["native_status"] not in ("reported", "literal") or count(cell["value"]) is None
                    for cell in cells):
                raise IntakeError("source_fact_binding", "Unknown factual cell cannot become a reported count")
            value = count(sum(count(cell["value"]) for cell in cells)) if operation in (
                "sum", "component_sum") else count(cells[0]["value"])
        elif parse == "literal":
            value = cells[0]["value"]
        else:
            raise IntakeError("source_fact_binding", "Unsupported factual conversion")
        row = selected[0]
        if binding["path"] in ("count.value", "count.literal", "view.ballots"):
            header = binding.get("native_measure_header")
            if operation == "component_sum":
                equivalent = (binding.get("same_measure_review_evidence")
                    and binding.get("accepted_measure_literal") == row["measure"]["literal"])
            elif header:
                equivalent = (binding.get("same_measure_review_evidence")
                    and binding.get("accepted_measure_literal") == row["measure"]["literal"]
                    and all(" ".join(table.get("source_annotations", {}).get(
                        "native_column_headers", {}).get(binding["measure"], "").split())
                        == " ".join(header.split()) for table in tables))
            else:
                equivalent = row["measure"]["literal"] == binding["native_unit"]
            if scope != "cell" or not equivalent:
                raise IntakeError("source_fact_binding", "Native numerator label differs from the accepted measure")
        missing = object()
        actual = field(row, binding["path"], missing)
        if actual is missing or type(actual) is not type(value) or actual != value:
            raise IntakeError("source_fact_binding", "Canonical value differs from its reviewed native fact")


def verify_native_reproduction(spec, inputs):
    declaration = spec.get("format", {}).get("native_reproduction")
    if declaration is None:
        return
    from scripts.native_products import encoded, pin, query, unpack

    def supplied(name, compression=None):
        if name not in inputs or name not in spec["inputs"] or compression not in (None, "gzip"):
            raise ValueError("A complete declared native input is required")
        return gzip.decompress(inputs[name]) if compression == "gzip" else inputs[name]

    try:
        recipe = json.loads(supplied(declaration["recipe_input"]))
        products, selections = recipe["products"], recipe["queries"]
        ids = [p["id"] for p in products]
        query_ids = [q["id"] for q in selections]
        if (recipe["contract"] != "participation.native_product_recipe.v1"
                or not ids or len(set(ids)) != len(ids)
                or not query_ids or len(set(query_ids)) != len(query_ids)
                or set(ids) != set(declaration["products"])
                or any(q["product"] not in ids for q in selections)):
            raise ValueError("Complete native product/query inventory changed")
        queries = {}
        for product_spec in products:
            names = declaration["products"][product_spec["id"]]
            original = names["original"]
            original_body = supplied(original)
            source = spec["inputs"][original]
            if (source.get("publication") != "original" or source["url"] != product_spec["url"]
                    or source["pin"] != product_spec["pin"] or pin(original_body) != source["pin"]
                    or product_spec["state_code"] != spec["geography"]["state_code"]
                    or product_spec["election_year"] != spec["election"]["year"]):
                raise ValueError("Native original permission, pin, source or election changed")
            product = unpack(product_spec, original_body)
            factual = supplied(names["facts"], names.get("compression"))
            if encoded(product) != factual:
                raise ValueError("Factual tables differ from their complete original")
            for selection in selections:
                if selection["product"] == product_spec["id"]:
                    queries[selection["id"]] = query(product, selection)
        expected = encoded(dict(contract="participation.native_queries.v1", queries=queries))
        if supplied(declaration["queries_input"], declaration.get("queries_compression")) != expected:
            raise ValueError("Complete native numerical queries differ from their originals")
    except (KeyError, TypeError, ValueError, UnicodeError, OSError, EOFError) as error:
        raise IntakeError("source_native_reproduction", str(error)) from error


def adapt(spec, inputs, input_pins, clock, references):
    name = spec["adapter"]
    if name == "canonical_json":
        if not spec.get("review_evidence"):
            raise IntakeError("unreviewed_canonical_input", "Reusing canonical observations needs explicit review evidence")
        rows = json_records(spec, inputs)
        selected = set(spec.get("format", {}).get("source_ids", []))
        if selected:
            rows = [row for row in rows if row.get("source", {}).get("id") in selected]
        if not rows or spec.get("expected_rows") is not None and len(rows) != spec["expected_rows"]:
            raise IntakeError("source_schema", "Canonical source inventory changed")
        for row in rows:
            check_fields(row, "")
            if (row["geography"]["state_code"] != spec["geography"]["state_code"]
                    or row["election"] != spec["election"]):
                raise IntakeError("election_scope", "Canonical observations differ from the registered jurisdiction/election")
        verify_native_reproduction(spec, inputs)
        verify_fact_bindings(spec, rows, inputs)
        return validate_all(rows)
    if name not in ADAPTERS:
        raise IntakeError("unknown_adapter", "Unregistered direct adapter: " + name)
    rows = ADAPTERS[name](spec, inputs)
    if not rows:
        raise IntakeError("source_schema", "An empty source product is not zero participation")
    if spec.get("expected_rows") is not None and len(rows) != spec["expected_rows"]:
        raise IntakeError("source_schema", "Native row inventory changed; no partial source silently accepted")
    return [make_row(spec, row, index, input_pins[spec["primary_input"]], clock, references)
            for index, row in enumerate(rows, 1)]
