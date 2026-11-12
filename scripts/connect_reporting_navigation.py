"""Connect held source reporting rows to existing same-state county navigation."""

import argparse
import copy
import csv
import gzip
import io
import json
from pathlib import Path

from harris_county_successor import compressed, encoded, pin

STATES = {"AR": 2768, "AZ": 1763, "WY": 432}
MODES = ("available", "official", "uf_vep", "uf_vap")
TAG = "participation-held-reporting-navigation-20261112-01"
RELEASE = "https://github.com/hanshanley/margin_of_error/releases/download/"+TAG+"/"


def county_name(name):
    value = " ".join(name.casefold().split())
    return value[:-7] if value.endswith(" county") else value


def connect_row(record, parents, code):
    row = copy.deepcopy(record["observation"])
    properties = record["properties"]
    label = properties.get("county")
    if (row["geography"]["state_code"] != code or properties["state_code"] != code
            or properties["year"] != 2026 or row["election"]["year"] != 2026
            or row["geography"]["level"] != "reporting_unit"
            or row["geography"]["join"]["status"] != "unreviewed"
            or properties["ballots"] != row["count"]["value"]
            or properties["reported_pct"] is not None
            or row["denominator"] and row["denominator"]["qualified"]):
        raise ValueError("Held reporting source scope or count changed")
    matches = [parent for parent in parents if parent["geography"]["state_code"] == code
               and county_name(parent["view"]["county"]) == county_name(label)]
    if len(matches) != 1:
        raise ValueError("Native county name is not a unique same-state parent: "+label)
    parent = matches[0]
    original_view = copy.deepcopy(row["view"])
    view = row["view"]
    view.update(county_id=parent["view"]["county_id"], county=parent["view"]["county"],
        unit_key=properties["key"], unit=properties["precinct"], precinct=properties["precinct"],
        unit_kind=properties["reporting_unit_kind"],
        review_id="held-reporting-navigation-"+code+"-20261112-01",
        source_native_county_label=label, source_native_county_id=original_view.get("county_id"),
        source_status_literal=row["reporting_status"]["literal"],
        source_reporting_label="Held native reporting row; no finished counting or precinct-boundary certification inferred.",
        native_printed_pct=properties.get("native_printed_pct", properties.get("native_reported_pct")),
        denominator_basis=(row["denominator"] or {}).get("basis", "native_registration_scope_unqualified"),
        participation_measure_label="Native "+row["measure"]["literal"],
        complete_download_url=RELEASE+"complete-analysis.zip", maps_approved=False,
        geometry_withheld_reason="Native reporting row only; no precinct-boundary join is approved.",
        quality=list(original_view.get("quality") or row["quality"]["notes"]))
    row["geography"]["parent_id"] = parent["geography"]["id"]
    decision = dict(state_code=code, native_county_label=label, county_id=view["county_id"],
        parent_observation_id=parent["id"], observation_id=row["id"], unit_key=view["unit_key"],
        unit=view["unit"], unit_kind=view["unit_kind"], source_count=row["count"]["value"],
        source_status=row["count"]["status"], source_clock=row["source_clock"]["literal"],
        denominator_value=(row["denominator"] or {}).get("value"), analysis_rate=None,
        native_source_fields_preserved=True, precinct_boundary_approved=False)
    return row, decision


def build(baseline):
    counts = baseline/"counts"
    native = baseline/"native"
    index = json.loads((counts/"index.json").read_bytes())
    native_index = json.loads((native/"index.json").read_bytes())
    changes, decisions, summaries = {}, [], {}
    for code, size in STATES.items():
        declaration = index["states"][code]
        state = json.loads(gzip.decompress((counts/declaration["file"]).read_bytes()))
        before = copy.deepcopy(state)
        by_id = {row["id"]: row for row in state["records"]}
        parents = [by_id[key] for key in state["views"]["official"]["counties"]]
        source = native_index["reporting_tables"][code]
        raw = (native/source["file"]).read_bytes()
        if pin(raw) != {key: source[key] for key in ("bytes", "sha256")}:
            raise ValueError("Held complete table differs from accepted native pin")
        table = json.loads(gzip.decompress(raw))
        if (table["contract"] != "participation.reporting_units.v1" or table["state_code"] != code
                or source["rows"] != size or len(table["records"]) != size
                or set(source["eligible_modes"]) != set(MODES)):
            raise ValueError("Held complete reporting inventory or modes differ")
        additions = []
        for record in table["records"]:
            row, decision = connect_row(record, parents, code)
            if row["id"] in by_id:
                raise ValueError("Do not duplicate an existing source observation")
            by_id[row["id"]] = row
            additions.append(row)
            decisions.append(decision)
        if len({row["view"]["unit_key"] for row in additions}) != size:
            raise ValueError("Duplicate reporting-unit selector key")
        state["records"].extend(additions)
        for mode in MODES:
            frame = state["views"][mode]
            if (not frame["qualified"] or frame["precincts"]
                    or {by_id[key]["view"]["county_id"] for key in frame["counties"]}
                    != {parent["view"]["county_id"] for parent in parents}):
                raise ValueError("Wrong or previously connected county/mode scope")
            frame["precincts"] = [row["id"] for row in additions]
            declaration["views"][mode]["precincts"] = size
            declaration["views"][mode]["dispositions"]["precincts"] = dict(
                reported=sum(row["count"]["status"] == "reported" for row in additions),
                unknown=sum(row["count"]["status"] == "unknown" for row in additions),
                withheld=sum(row["count"]["status"] == "withheld" for row in additions),
                qualified_fractions=0, geography_levels=["reporting_unit"])
        if state["records"][:-size] != before["records"]:
            raise ValueError("Accepted county/early/mail observations changed")
        for mode in ("in_person_early", "mail_returned"):
            if state["views"][mode] != before["views"][mode]:
                raise ValueError("Held all-election reporting rows leaked into early/mail")
        body = compressed(state)
        changes[declaration["file"]] = body
        declaration.update(pin(body), records=len(state["records"]))
        index["coverage"][code] = dict(records=len(state["records"]),
            reported=sum(row["count"]["status"] == "reported" for row in state["records"]),
            zeros=sum(row["count"]["value"] == 0 for row in state["records"]),
            unknown=sum(row["count"]["status"] == "unknown" for row in state["records"]),
            withheld=sum(row["count"]["status"] == "withheld" for row in state["records"]),
            qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"]) for row in state["records"]))
        summaries[code] = dict(rows=size, county_parents=len(parents),
            reported=sum(row["count"]["status"] == "reported" for row in additions),
            unknown=sum(row["count"]["status"] == "unknown" for row in additions),
            true_zeros=sum(row["count"]["value"] == 0 for row in additions))
    index["held_reporting_navigation_review"] = TAG
    changes["index.json"] = encoded(index)
    return changes, decisions, summaries


def compile_datasets(baseline, output):
    if output.exists():
        raise ValueError("Use a fresh complete output")
    changes, decisions, summaries = build(baseline)
    descriptor = json.loads((baseline/"counts/dataset.json").read_bytes())
    root = output/"counts"
    root.mkdir(parents=True)
    for name, metadata in descriptor["files"].items():
        original = (baseline/"counts"/name).read_bytes()
        if pin(original) != metadata:
            raise ValueError("Changed accepted complete count input")
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(changes.get(name, original))
    files = {name: pin((root/name).read_bytes()) for name in descriptor["files"]}
    descriptor.update(files=files, index=dict(file="index.json", **files["index.json"]),
        version=pin(encoded(dict(files=files, contract=descriptor["record_contract"])))["sha256"],
        complete_download=None)
    (root/"dataset.json").write_bytes(encoded(descriptor))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(decisions[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(decisions)
    (output/"complete-navigation-query.csv").write_bytes(stream.getvalue().encode())
    (output/"complete-navigation-query.json").write_bytes(encoded(decisions))
    summary = dict(status="compiled_held_reporting_navigation", states=summaries,
        reporting_rows=len(decisions), county_parents=sum(row["county_parents"] for row in summaries.values()),
        new_numerical_observations=0, new_rates=0, new_precinct_polygons=0,
        all_native_tables_bindings_and_other48_state_shards_unchanged=True)
    (output/"summary.json").write_bytes(encoded(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compile_datasets(args.baseline, args.output)))
