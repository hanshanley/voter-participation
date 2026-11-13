"""Build explicit within-report arithmetic checks, never a statewide total."""

import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded
from scripts.native_reconciliation import reconcile


ADMINISTRATIVE = "unofficial_administrative_measures_not_candidate_returns"
CONTEST = "unofficial_contest_choices_and_vote_accounting"


def build(grids):
    queries, checks, excluded, groups = {}, [], [], {}
    for product in grids["products"]:
        for table in product["tables"]:
            table_query = product["source"]["id"] + "::" + table["id"]
            local = []
            for record in table["rows"]:
                row = {field: cell["value"] for field, cell in record["cells"].items()}
                row["source_record_id"] = table["id"] + ":" + str(record["row"])
                local.append(row)
            if not local or table_query in queries:
                raise ValueError("Empty or repeated source-qualified factual table")
            queries[table_query] = dict(rows=local)
            if table["source_role"] == ADMINISTRATIVE:
                fields = tuple(sorted(field for field in record["cells"] if field != "native_unit"))
                annotations = table["source_annotations"]
                key = encoded([product["source"]["id"], annotations.get("native_header_clock_literals"),
                    annotations.get("native_table_clock_literal"), fields]).decode()
                group = groups.setdefault(key, dict(source_id=product["source"]["id"],
                    rows=[], tables=[], annotations=annotations, fields=fields))
                group["rows"].extend(local)
                group["tables"].append(table["id"])
            elif table["source_role"] == CONTEST:
                labels = defaultdict(list)
                for row in local:
                    labels[row["native_unit"]].append(row)
                required = ["Total Votes Cast", "Overvotes", "Undervotes", "Contest Totals"]
                if any(len(labels[label]) != 1 for label in required):
                    raise ValueError("Contest accounting labels are absent or ambiguous")
                total_index = next(i for i, row in enumerate(local)
                    if row["native_unit"] == "Total Votes Cast")
                choices = [row["source_record_id"] for row in local[:total_index]]
                if not choices:
                    raise ValueError("A contest cannot silently lose all native choices")
                def term(records, fields):
                    return dict(query=table_query, where=dict(source_record_id=records), fields=fields)
                for field in record["cells"]:
                    if field == "native_unit":
                        continue
                    checks.append(dict(id=table_query + ":choices:" + field,
                        left=[term(choices, [field])],
                        right=[term([labels["Total Votes Cast"][0]["source_record_id"]], [field])],
                        policy="record_discrepancy"))
                    checks.append(dict(id=table_query + ":accounting:" + field,
                        left=[term([labels[label][0]["source_record_id"] for label in required[:3]], [field])],
                        right=[term([labels["Contest Totals"][0]["source_record_id"]], [field])],
                        policy="record_discrepancy"))
                modes = ["early_voting", "election_day", "mail_in", "provisional", "emergency", "state_fed"]
                for row in local:
                    checks.append(dict(id=table_query + ":" + row["source_record_id"] + ":mode_sum",
                        left=[term([row["source_record_id"]], modes)],
                        right=[term([row["source_record_id"]], ["total"])],
                        policy="record_discrepancy"))
    observations = []
    duplicate_controls = []
    for number, group in enumerate(groups.values(), 1):
        query_id = "native-administrative-report-" + str(number)
        queries[query_id] = dict(rows=group["rows"])
        county_rows = [row for row in group["rows"] if row["native_unit"].endswith(" County")]
        if not county_rows:
            raise ValueError("The reviewed administrative scope has no literal county control")
        county = county_rows[0]
        fields = group["fields"]
        if any(any(row[field] != county[field] for field in ("native_unit", *fields))
                for row in county_rows):
            raise ValueError("Repeated same-scope county controls disagree")
        references = [row["source_record_id"] for row in county_rows]
        observations.append(dict(query=query_id, source_id=group["source_id"],
            county={key: value for key, value in county.items() if key != "source_record_id"},
            source_records=references, source_tables=group["tables"],
            source_annotations=group["annotations"]))
        if len(references) > 1:
            duplicate_controls.append(dict(query=query_id, native_unit=county["native_unit"],
                equality_checked_fields=list(fields), source_records=references))
        for control in group["rows"]:
            if "TOTALS" not in control["native_unit"]:
                continue
            for field in fields:
                left, right = control[field], county[field]
                if type(left) is not int or type(right) is not int or left < 0 or right < 0:
                    excluded.append(dict(query=query_id, source_record_id=control["source_record_id"],
                        measure=field, control_value=left, county_value=right,
                        reason="missing_or_nonnegative_count_not_qualified"))
                    continue
                checks.append(dict(id=query_id + ":" + control["source_record_id"] + ":" + field,
                    left=[dict(query=query_id,
                        where=dict(source_record_id=[control["source_record_id"]]), fields=[field])],
                    right=[dict(query=query_id, where=dict(source_record_id=references),
                        fields=[field], operation="unique")], policy="record_discrepancy"))
    return dict(queries=queries, checks=checks, observations=observations,
        excluded_comparisons=excluded, equality_checked_repeated_controls=duplicate_controls,
        source_count_repairs=0, latest_by_filename_or_page_order_inferred=False,
        statewide_totals_or_disjoint_municipal_scopes_inferred=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grids", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    body = args.grids.read_bytes()
    if args.grids.suffix == ".gz":
        body = gzip.decompress(body)
    result = build(json.loads(body))
    result["reconciliation"] = reconcile(result["queries"], result["checks"])
    args.output.write_bytes(encoded(result))
    print(json.dumps(dict(checks=len(result["checks"]),
        discrepancies=result["reconciliation"]["discrepancies"],
        excluded_comparisons=len(result["excluded_comparisons"]),
        county_observations=len(result["observations"]),
        equality_checked_repeated_controls=len(result["equality_checked_repeated_controls"]))))


if __name__ == "__main__":
    main()
