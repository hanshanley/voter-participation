"""Project explicit historical administrative cells without joining source frames."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import quote
import zipfile

from scripts.participation_intake.contract import STATES, count, digest, encoded, pin


CONTRACT = "participation.historical_native_counts.v1"
DATASET = "participation-historical-native-counts"
DATES = {2018: "20181106", 2020: "20201103"}
LABELS = {
    "ballots cast": "ballots_cast", "ballots cast - total": "ballots_cast",
    "ballots_cast": "ballots_cast", "registered voters": "registration_stock",
    "registered voters - total": "registration_stock",
}


def file_pin(path):
    checksum = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for body in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(body)
            size += len(body)
    return {"bytes": size, "sha256": checksum.hexdigest()}


def native_count(literal, status):
    upstream_status = None
    if status == "noninteger_native_literal" and re.fullmatch(
            r"\d{1,3}(?:,\d{3})+(?:\.0+)?", literal, re.ASCII):
        upstream_status, status = status, "reported"
    if status != "reported":
        return {"value": None, "status": "unknown" if status == "unknown" else "withheld",
                "literal": literal, "source_status": status}
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.0+)?", literal, re.ASCII):
        raise ValueError("A reported administrative count is not an exact nonnegative integer")
    try:
        value = Decimal(literal.replace(",", ""))
    except InvalidOperation as error:
        raise ValueError("Invalid reported administrative count") from error
    result = {"value": count(int(value)), "status": "reported", "literal": literal,
              "source_status": status}
    if upstream_status:
        result["source_status"] = "reported_comma_grouped_native_integer"
        result["upstream_source_status"] = upstream_status
    return result


def native_field(fields, aliases):
    matches = [index for index, name in enumerate(fields["columns"])
               if name.casefold().strip() in aliases]
    if len(matches) != 1 or matches[0] >= len(fields["values"]):
        raise ValueError("Ambiguous native administrative field")
    return fields["values"][matches[0]]


def project(row, collection, sources):
    official = collection == "official-state"
    selected = {"ballots_cast", "registration_stock"} if official else {
        "native_ballots_cast", "native_registration_stock"
    }
    if row["measure"] not in selected:
        return None
    year, state = int(row["year"]), row["state_code"]
    if year not in DATES or state not in STATES:
        raise ValueError("Unreviewed historical election or jurisdiction")
    fields = json.loads(row["source_fields_json" if official else "native_fields_json"])
    if official:
        source = sources[row["source_sha256"]]
        if source["year"] != year or source["state_code"] != state:
            raise ValueError("Official source election differs from its administrative row")
        filename = row["source_member"]
        if not re.fullmatch(str(year) + r"(?:-General-|_GENERAL_ELECTION-)[^/\\]+\.xls",
                            filename, re.IGNORECASE):
            raise ValueError("Unqualified historical general-election workbook")
        literal = row["office_literal"]
        raw_count, status = row["count_literal"], row["count_status"]
        native_literal = fields["contest"]
        native_value = fields["value"]
        county, unit, kind = row["county_literal"], row["unit_literal"], row["unit_kind"]
        category = row["candidate_literal"]
        selector = {key: row[key] for key in
                    ("source_member", "source_table", "source_row", "source_column")}
        source_sha, url = row["source_sha256"], source["url"]
        source_name = Path(url).name
        snapshot_key = [collection, state, year, source_sha]
        if "general" not in url.casefold():
            raise ValueError("Official historical product does not declare a general election")
    else:
        filename = row["source_file"]
        if not Path(filename).name.startswith(DATES[year] + "__") or \
                "__general" not in Path(filename).name.casefold():
            raise ValueError("Primary, special or mismatched historical source file")
        key = (state, year, row["source_commit"], filename)
        source = sources[key]
        source_sha = source["source"]["sha256"]
        literal, native_literal = row["office"], native_field(fields, {"office", "race"})
        raw_count, status = row["votes"], row["vote_count_status"]
        native_value = native_field(fields, {"votes", "total_votes"})
        county, unit, kind = row["county"], row["precinct"], "source_defined_unit_unjoined"
        category = row["candidate"]
        selector = {"source_file": filename, "source_row": row["source_row"]}
        url = ("https://raw.githubusercontent.com/openelections/openelections-data-"
               + state.lower() + "/" + row["source_commit"] + "/" + quote(filename, safe="/"))
        source_name = filename
        snapshot_key = [collection, state, year, row["source_commit"], filename, source_sha]
    measure = LABELS.get(str(native_literal).casefold().strip())
    if measure is None or LABELS.get(literal.casefold().strip()) != measure or \
            row["measure"].removeprefix("native_") != measure:
        raise ValueError("Candidate votes cannot become administrative participation")
    value = native_count(raw_count, status)
    if value["value"] is not None:
        try:
            equivalent = Decimal(str(native_value).replace(",", "")) == value["value"]
        except InvalidOperation:
            equivalent = False
        if not equivalent:
            raise ValueError("Native cell and canonical administrative value disagree")
    snapshot_id = digest(encoded(snapshot_key))[:32]
    identity = digest(encoded([snapshot_id, selector, measure]))[:32]
    return {
        "id": identity, "snapshot_id": snapshot_id, "year": year, "state_code": state,
        "county_literal": county, "unit_literal": unit, "unit_kind": kind,
        "measure": measure, "measure_literal": literal, "native_category": category,
        "count": value, "denominator": None, "rate": None,
        "geography_join": "unreviewed", "cross_year_identity_approved": False,
        "source": {"url": url, "name": source_name, "input_sha256": source_sha,
                   "selector": selector, "native_fields": fields,
                   "original_qualification": row["qualification"]},
    }


def compressed(value):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, filename="", mode="wb", compresslevel=6, mtime=0) as stream:
        stream.write(encoded(value))
    return output.getvalue()


def component_rows(path, collection):
    if collection not in {"official-state", "openelections-statewide", "openelections-supplements"}:
        raise ValueError("Unreviewed historical component class")
    with zipfile.ZipFile(path) as archive:
        query = ("queries/complete-source-cell-query.csv.gz" if collection == "official-state"
                 else "queries/complete-source-row-query.csv.gz")
        if collection == "official-state":
            products = json.loads(archive.read("originals/product-provenance.json"))
            sources = {row["acquisition"]["sha256"]: row for row in products
                       if row["acquisition"]["acquired"]}
        else:
            inventory = json.loads(archive.read("queries/complete-source-file-inventory.json"))
            sources = {(row["state_code"], row["year"], row["commit"], row["source_file"]): row
                       for row in inventory}
        with archive.open(query) as raw, gzip.GzipFile(fileobj=raw) as stream, \
                io.TextIOWrapper(stream, newline="") as text:
            for row in csv.DictReader(text):
                result = project(row, collection, sources)
                if result is not None:
                    yield result


def compile_dataset(specification, output):
    specification, output = Path(specification), Path(output)
    spec = json.loads(specification.read_bytes())
    if output.exists():
        raise ValueError("Use a new historical projection output directory")
    records = defaultdict(list)
    inputs = []
    seen = set()
    for source in spec["inputs"]:
        path = specification.parent / source["file"]
        if file_pin(path) != {key: source[key] for key in ("bytes", "sha256")}:
            raise ValueError("Pinned historical input component differs")
        inputs.append({key: value for key, value in source.items() if key != "file"})
        for row in component_rows(path, source["collection"]):
            if row["id"] in seen:
                raise ValueError("Duplicate historical source cell; alternatives are not silently merged")
            seen.add(row["id"])
            records[row["state_code"]].append(row)
    output.mkdir(parents=True)
    (output / "states").mkdir()
    states, decisions = {}, []
    for state in STATES:
        rows = sorted(records[state], key=lambda row: (row["year"], row["snapshot_id"], row["id"]))
        snapshots = {}
        for row in rows:
            snapshots.setdefault(row["snapshot_id"], {
                "id": row["snapshot_id"], "year": row["year"], "state_code": state,
                "name": row["source"]["name"], "source_url": row["source"]["url"],
                "input_sha256": row["source"]["input_sha256"], "count_clock": None,
                "timezone": None, "election_type": "general",
                "election_date_qualification": "previously_reviewed_general_source_selection",
                "additive_with_other_snapshots": False,
            })
        if rows:
            name = "states/" + state + ".json.gz"
            (output / name).write_bytes(compressed({
                "contract": CONTRACT, "state_code": state,
                "snapshots": list(snapshots.values()), "records": rows,
            }))
            states[state] = {"file": name, "records": len(rows),
                             "snapshots": list(snapshots.values())}
        for year in DATES:
            selected = [row for row in rows if row["year"] == year]
            counts = Counter(row["measure"] for row in selected)
            decisions.append({
                "state_code": state, "year": year, "source_cells": len(selected),
                "ballot_cells": counts["ballots_cast"], "registration_cells": counts["registration_stock"],
                "status": "explicit_administrative_cells" if selected else
                    "no_explicit_administrative_cells_in_selected_components",
                "turnout_rate_qualified": False, "geography_join_qualified": False,
            })
    index = {
        "contract": CONTRACT, "years": list(DATES), "jurisdictions": STATES,
        "states": states, "decisions": decisions, "inputs": inputs,
        "candidate_votes_used_as_ballots": False,
        "alternative_sources_or_modes_summed": False,
        "registration_stocks_are_denominators": False,
        "outside_projection_years_are_not_classified_as_missing": True,
    }
    (output / "index.json").write_bytes(encoded(index))
    files = {str(path.relative_to(output)): pin(path.read_bytes())
             for path in sorted(output.rglob("*")) if path.is_file()}
    description = {
        "contract": "participation.dataset.v1", "id": DATASET, "record_contract": CONTRACT,
        "version": digest(encoded({"files": files, "contract": CONTRACT})), "files": files,
        "index": {"file": "index.json", **files["index.json"]},
        "complete_download": spec.get("complete_download"),
    }
    (output / "dataset.json").write_bytes(encoded(description))
    return {"records": len(seen), "jurisdictions": len(STATES), "source_states": len(states),
            "decisions": len(decisions), "version": description["version"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compile_dataset(args.spec, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
