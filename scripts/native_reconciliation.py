"""Reconcile declared factual-query aggregates, retaining signed discrepancies."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.native_products import encoded, integer, pin


def aggregates(queries, terms, keys):
    results = defaultdict(list)
    for term in terms:
        if set(term) - {"query", "where", "exclude", "fields", "operation"}:
            raise ValueError("Unknown reconciliation selection option")
        rows = [row for row in queries[term["query"]]["rows"] if all(
            row[field] in allowed for field, allowed in term.get("where", {}).items())
            and all(row[field] not in excluded
                for field, excluded in term.get("exclude", {}).items())]
        if not rows:
            raise ValueError("A reconciliation input selection is empty")
        groups = defaultdict(list)
        for row in rows:
            groups[tuple(row[field] for field in keys)].append(row)
        for key, local in groups.items():
            operation = term.get("operation", "sum")
            if operation == "count":
                value = len(local)
            elif operation == "sum":
                value = sum(integer(row[field]) for row in local for field in term["fields"])
            elif operation == "unique":
                values = {integer(row[field]) for row in local for field in term["fields"]}
                if len(values) != 1:
                    raise ValueError("A repeated source control disagrees")
                value = values.pop()
            else:
                raise ValueError("Unknown reconciliation operation")
            results[key].append(value)
    return {key: sum(values) for key, values in results.items()}


def reconcile(queries, checks):
    expanded = []
    for check in checks:
        if "each_field" not in check:
            expanded.append(check)
            continue
        for field in check["each_field"]:
            item = dict(check, id=check["id"] + ":" + field)
            for side in ("left", "right"):
                item[side] = [dict(term, fields=[
                    field if name == "$field" else name for name in term["fields"]])
                    for term in check[side]]
            expanded.append(item)
    result, identities = [], set()
    for check in expanded:
        if check.get("policy", "require_match") not in ("require_match", "record_discrepancy"):
            raise ValueError("Unknown reconciliation requirement policy")
        if check["id"] in identities:
            raise ValueError("Repeated reconciliation identity")
        identities.add(check["id"])
        keys = check.get("keys", [])
        left = aggregates(queries, check["left"], keys)
        right = aggregates(queries, check["right"], keys)
        rows = []
        for key in sorted(set(left) | set(right), key=lambda item: encoded(item)):
            before, after = left.get(key), right.get(key)
            matched = before is not None and after is not None and before == after
            rows.append(dict(dimensions=dict(zip(keys, key)), left=before, right=after,
                signed_left_minus_right=before-after if before is not None and after is not None else None,
                status="matched" if matched else "discrepancy"))
        passed = all(row["status"] == "matched" for row in rows)
        result.append(dict(id=check["id"], status="matched" if passed else "discrepancy",
            policy=check.get("policy", "require_match"), rows=rows))
    return dict(contract="participation.native_reconciliation.v1", checks=result,
        required_checks_passed=all(check["status"] == "matched" for check in result
            if check["policy"] == "require_match"),
        discrepancies=sum(row["status"] == "discrepancy" for check in result for row in check["rows"]),
        source_count_repairs=0, unique_voter_turnout_inferred=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh reconciliation output")
    bodies = args.queries.read_bytes(), args.checks.read_bytes()
    result = reconcile(json.loads(bodies[0])["queries"], json.loads(bodies[1])["checks"])
    result["input_pins"] = dict(queries=pin(bodies[0]), checks=pin(bodies[1]))
    args.output.write_bytes(encoded(result))
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, sort_keys=True))
    if not result["required_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
