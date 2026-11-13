"""Bind reviewed native statistical blocks to count-only canonical observations."""

import copy
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
import gzip
import json

from scripts.native_products import query, statistical_units
try:
    from scripts.participation_intake.contract import (
        IntakeError, VERSION, encoded, observation_id, pin, validate_all)
except ModuleNotFoundError as error:
    if error.name not in ("scripts.participation_intake", "scripts.participation_intake.contract"):
        raise
    from participation_intake.contract import (
        IntakeError, VERSION, encoded, observation_id, pin, validate_all)


def worksheet_clock(product, declaration):
    tables = [t for t in product["tables"] if t["name"] == declaration["table"]
              and t.get("workbook") == declaration.get("workbook")]
    cells = [c for t in tables for r in t["rows"] for c in r["cells"]
             if c["address"] == declaration["cell"]]
    if len(tables) != 1 or len(cells) != 1:
        raise IntakeError("native_statistics", "Native clock cell is missing or ambiguous")
    cell, table = cells[0], tables[0]
    style = table["workbook_cell_formats"][int(cell["attributes"]["s"])]
    number_format = table["workbook_number_formats"].get(style["numFmtId"])
    if (cell["formula"] is not None or cell["storage_type"] != "n"
            or number_format != declaration["number_format"]
            or not all(token in number_format.lower() for token in ("y", "h", "s"))):
        raise IntakeError("native_statistics", "Unreviewed native Excel clock format")
    serial = Decimal(cell["cached_literal"])
    date1904 = table["workbook_properties"].get("date1904", "0")
    if date1904 not in ("0", "1", "false", "true") or not serial.is_finite() or serial < 61:
        raise IntakeError("native_statistics", "Unqualified Excel clock date system")
    epoch = datetime(1904, 1, 1) if date1904 in ("1", "true") else datetime(1899, 12, 30)
    milliseconds = int((serial * 86400000).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    decoded = (epoch + timedelta(milliseconds=milliseconds)).isoformat(timespec="milliseconds")
    return dict(literal=decoded + " (decoded Excel cache; timezone not supplied)", timezone=None,
                qualification="decoded_native_worksheet_cache_not_printed_text",
                cell=declaration["cell"], cached_literal=cell["cached_literal"],
                number_format=number_format, date_system="1904" if epoch.year == 1904 else "1900")


def observations(spec, inputs):
    declaration = spec["format"]["native_statistics"]
    if (declaration["contract"] != "participation.native_statistical_counts.v1"
            or not declaration.get("measure_review_evidence")
            or spec["measure"]["kind"] != "participation_reported"
            or spec["measure"]["mode"] != "source_defined"):
        raise IntakeError("native_statistics", "Statistical counts require an explicit count-only measure review")
    recipe = json.loads(inputs[declaration["recipe_input"]])
    if recipe["contract"] != "participation.native_product_recipe.v1":
        raise IntakeError("native_statistics", "Native query recipe changed")
    if set(declaration["products"]) != {p["id"] for p in recipe["products"]}:
        raise IntakeError("native_statistics", "Complete reviewed product inventory changed")
    rows, parents, native_units = [], [], set()
    for product_spec in recipe["products"]:
        config = declaration["products"][product_spec["id"]]
        body = inputs[config["facts_input"]]
        product = json.loads(gzip.decompress(body) if config.get("compression") == "gzip" else body)
        if (product["contract"] != "participation.native_factual_tables.v1"
                or any(product["source"][key] != product_spec[key] for key in
                       ("id", "url", "pin", "state_code", "election_year",
                        "retrieved_at_utc", "native_updated_at", "redistribution"))
                or product_spec["state_code"] != spec["geography"]["state_code"]
                or product_spec["election_year"] != spec["election"]["year"]):
            raise IntakeError("native_statistics", "Native source and registered election differ")
        selections = [q for q in recipe["queries"] if q["id"] == config["query"]]
        if len(selections) != 1 or selections[0]["product"] != product_spec["id"]:
            raise IntakeError("native_statistics", "Native statistical query is absent or ambiguous")
        selection = selections[0]
        grouping = config["grouping"]
        header_tables = [table for table in product["tables"]
            if table["name"] in selection["tables"] and table.get("workbook") == selection.get("workbook")]
        election = config["election_header"]
        headers = [cell["value"] for table in header_tables for row in table["rows"] for cell in row["cells"]
                   if cell["address"] == election["cell"]]
        if (len(headers) != 1 or headers[0] != election["literal"]
                or election["date_literal"] not in headers[0]
                or datetime.strptime(election["date_literal"], election["date_format"]).date().isoformat()
                    != spec["election"]["date"]):
            raise IntakeError("native_statistics", "Native statistical election header differs from the declared election")
        column = selection["fields"][grouping["fields"]["cast"]]
        header = selection.get("require", {}).get(str(config["header_row"]), {}).get(column)
        if header != config["native_measure_header"] or not column.isalpha() or not column.isupper():
            raise IntakeError("native_statistics", "A reviewed physical statistical count column is required")
        blocks = statistical_units(query(product, selection), grouping)
        if len(blocks["units"]) != config["expected_units"]:
            raise IntakeError("native_statistics", "Reviewed native unit inventory changed")
        clock = worksheet_clock(product, config["clock"])
        for unit in blocks["units"]:
            if unit["unit"] in native_units:
                raise IntakeError("native_statistics", "Native source frames have overlapping literal units")
            native_units.add(unit["unit"])
            key = product_spec["id"] + ":" + str(unit["source_rows"][0]["row"])
            rows.append(make_observation(spec, key, unit["cast"], product["source"], clock,
                dict(native_unit=unit, native_parent=blocks["parent"],
                     agreeing_native_parent_copies=blocks["agreeing_native_parent_copies"],
                     source_product=product_spec["id"], native_clock=clock),
                dict(query=config["query"], source_rows=unit["source_rows"])))
        parents.append(dict(source=product["source"], parent=blocks["parent"],
                            clock=clock, native_units=[u["unit"] for u in blocks["units"]]))
    composite = declaration.get("composite")
    if composite is not None:
        if (not composite.get("disjoint_scope_review_evidence")
                or not composite.get("different_clock_review_evidence") or len(parents) < 2):
            raise IntakeError("native_statistics", "A composite requires reviewed disjoint source frames and clocks")
        source = dict(id=spec["id"], url=composite["source_url"],
            pin=pin(encoded([p["source"] for p in parents])),
            retrieved_at_utc=None, derived_source_parents=True)
        clock = dict(literal="; ".join(p["source"]["id"] + ": " + p["clock"]["literal"] for p in parents),
            timezone=None, qualification="separate_native_report_clocks_not_a_common_snapshot")
        rows.append(make_observation(spec, composite["identity"], sum(p["parent"]["cast"] for p in parents),
            source, clock, dict(derived_from_native_parents=parents, native_county_parent=False,
                unique_people_qualified=False, native_registered_denominator_not_summed=True),
            dict(derived_native_parents=[p["source"]["id"] for p in parents])))
    if set(spec["view"]["identities"]) != {row["geography"]["id"] for row in rows}:
        raise IntakeError("native_statistics", "Reviewed display inventory differs from every native unit")
    return validate_all(rows)


def make_observation(spec, identity, value, source, clock, native, selector):
    binding = copy.deepcopy(spec["view"]["identities"].get(identity))
    if not binding:
        raise IntakeError("native_statistics", "Native unit lacks an explicit reviewed identity")
    geography = binding.pop("canonical_geography")
    if geography["id"] != identity or geography["state_code"] != spec["geography"]["state_code"]:
        raise IntakeError("native_statistics", "Reviewed identity belongs to another source or jurisdiction")
    view = dict(spec["view"].get("constants", {}), **binding)
    view.update(year=spec["election"]["year"], state_code=geography["state_code"], ballots=value,
        denominator=None, denominator_basis="electorate_not_qualified", reported_pct=None,
        source_url=source["url"],
        source_update_label=clock["literal"], source_update_timezone=None,
        participation_measure_literal=spec["measure"]["literal"], native_record=native)
    if geography["level"] != "county" and (
            view.get("maps_approved") is not False or geography["join"]["status"] == "approved"):
        raise IntakeError("native_statistics", "Native reporting labels do not qualify precinct geometry")
    return dict(contract=VERSION, id=observation_id(spec["id"], spec["election"]["id"], identity,
            spec["measure"]["id"], spec["measure"]["mode"]),
        election=copy.deepcopy(spec["election"]), geography=geography, measure=copy.deepcopy(spec["measure"]),
        count=dict(value=value, literal=value, status="reported"), denominator=None,
        source_clock=clock, reporting_status=dict(literal=spec["reporting_status"],
            reported_units=None, total_units=None, complete=None),
        source=dict(id=spec["id"], url=source["url"], input_sha256=source["pin"]["sha256"],
            selector=selector, classification="public_aggregate", fields=copy.deepcopy(view)),
        quality=dict(conflicts=copy.deepcopy(spec.get("conflicts", [])), notes=list(spec["notes"])), view=view)
