"""Reconcile reviewed native reporting parts without inferring geographic joins."""

from collections import defaultdict
from decimal import Decimal


STATISTICS = {
    "native_registration_ballot_reported_turnout_statistics",
    "unofficial_registration_ballot_reported_turnout_statistics",
}


def build(grids, recipe):
    if (grids["contract"] != "participation.reviewed_pdf_factual_grids.v1"
            or recipe["contract"] != "participation.reviewed_pdf_group_queries.v1"):
        raise ValueError("Reviewed factual grids and grouping recipe are required")
    products = [item for item in grids["products"] if item["source"]["id"] == recipe["source_id"]]
    if len(products) != 1:
        raise ValueError("Native product identity is ambiguous")
    tables = products[0]["tables"]
    identifiers = recipe["part_tables"] + recipe["summary_tables"]
    selected = {table["id"]: table for table in tables if table["id"] in identifiers}
    if (len(set(identifiers)) != len(identifiers) or set(selected) != set(identifiers)
            or sum(table["id"] in identifiers for table in tables) != len(identifiers)
            or any(table["source_role"] not in STATISTICS for table in selected.values())):
        raise ValueError("Native statistical table inventory changed")
    normalize = (lambda value: " ".join(value.split())) if recipe.get(
        "reading_whitespace_normalized") else (lambda value: value)
    measures = recipe["count_fields"]
    nonempty = recipe["part_nonempty_fields"]
    result = {name: dict(rows=[]) for name in
        ("parts", "parent_controls", "summary_parents", "summary_total", "grouped_units")}
    parent, closed, identities, rate_checks = None, set(), set(), []
    for identifier in identifiers:
        table = selected[identifier]
        for record in table["rows"]:
            identity = (identifier, record["row"])
            if identity in identities:
                raise ValueError("Repeated native factual row")
            identities.add(identity)
            cells = {key: cell["value"] for key, cell in record["cells"].items()}
            name = normalize(cells["native_unit"])
            reference = dict(table=identifier, row=record["row"], page=table["source_page"])
            if identifier in recipe["part_tables"]:
                if (all(cells[field] is None for field in measures)
                        and all(cells[field] in (None, "") for field in nonempty)):
                    if not name or parent is not None:
                        raise ValueError("Native parent header appeared before the previous control")
                    parent = name
                    continue
                if parent is None:
                    raise ValueError("Native reporting part has no declared parent header")
                if name == parent + recipe["parent_total_suffix"]:
                    if parent in closed:
                        raise ValueError("Repeated native parent control")
                    closed.add(parent)
                    destination = "parent_controls"
                elif all(cells[field] not in (None, "") for field in nonempty):
                    destination = "parts"
                else:
                    raise ValueError("Unclassified native reporting row")
                native_parent = parent
            else:
                destination = "summary_total" if name == recipe["summary_total_label"] else "summary_parents"
                native_parent = name
            if any(type(cells[field]) is not int for field in measures):
                raise ValueError("Unknown native count cannot become a group total")
            output = dict(cells, native_unit=name, native_unit_literal=cells["native_unit"],
                parent=native_parent, source_ref=reference)
            result[destination]["rows"].append(output)
            for rate in recipe.get("percentages", []):
                literal = cells[rate["field"]]
                denominator, numerator = cells[rate["denominator"]], cells[rate["numerator"]]
                check = dict(source_ref=reference, field=rate["field"], native_literal=literal,
                    numerator=numerator, denominator=denominator)
                if denominator <= 0 or numerator < 0 or numerator > denominator:
                    check.update(status="unqualified_native_fraction")
                else:
                    if not isinstance(literal, str) or not literal.endswith("%"):
                        raise ValueError("Native percentage literal changed")
                    printed = Decimal(literal[:-1])
                    exact = Decimal(100) * numerator / denominator
                    tolerance = Decimal("0.5") * Decimal(10) ** printed.as_tuple().exponent
                    check.update(exact_percent=str(exact), signed_printed_minus_exact_pp=str(printed-exact),
                        native_precision_tolerance_pp=str(tolerance),
                        status="matched" if abs(printed-exact) <= tolerance else "discrepancy")
                rate_checks.append(check)
            if destination == "parent_controls":
                parent = None
    summaries = result["summary_parents"]["rows"]
    if (parent is not None or len(result["summary_total"]["rows"]) != 1
            or len(summaries) != len(closed) or {row["parent"] for row in summaries} != closed
            or {row["parent"] for row in result["parts"]["rows"]} != closed):
        raise ValueError("Native parent and summary inventories do not reconcile")
    groups = defaultdict(list)
    part_identities = set()
    for row in result["parts"]["rows"]:
        identity = (row["parent"], row["native_unit"], *(normalize(row[name]) for name in nonempty))
        if identity in part_identities:
            raise ValueError("Native reporting-part identity is ambiguous")
        part_identities.add(identity)
        groups[(row["parent"], row["native_unit"])].append(row)
    for (native_parent, name), rows in sorted(groups.items()):
        result["grouped_units"]["rows"].append(dict(
            {field: sum(row[field] for row in rows) for field in measures},
            native_unit=name, parent=native_parent, source_parts=len(rows),
            source_refs=[row["source_ref"] for row in rows],
            source_method="sum_of_reviewed_native_reporting_parts_not_precinct_join"))
    for name, expected in recipe["expected_rows"].items():
        if len(result[name]["rows"]) != expected:
            raise ValueError("Reviewed reporting-group inventory changed: " + name)
    checks = []
    for left, right, keys in (
            ("parts", "parent_controls", ["parent"]),
            ("parent_controls", "summary_parents", ["parent"]),
            ("summary_parents", "summary_total", []),
            ("grouped_units", "summary_total", [])):
        checks.append(dict(id=left + "-to-" + right, keys=keys, each_field=measures,
            left=[dict(query=left, fields=["$field"])],
            right=[dict(query=right, fields=["$field"])]))
    return dict(contract="participation.complete_pdf_group_queries.v1",
        queries=result, checks=checks, native_rate_checks=rate_checks,
        source_count_repairs=0, automatic_geographic_or_model_qualification=False)
