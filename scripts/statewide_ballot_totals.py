"""Reviewed direct statewide ballot parents, independent of congressional choices."""

import copy
import csv
import gzip
import io
import json

from scripts import protected_official_wyoming
from scripts.participation_intake.contract import (
    VERSION, count, encoded, observation_id, pin, validate,
)


CONTRACT = "participation.reviewed_statewide_ballot_parent.v1"
PROFILES = {
    "WY": {
        "state": "Wyoming",
        "source_id": "wy-sos-direct-statewide-ballots-20261103",
        "feed": protected_official_wyoming.IDENTITY,
        "url": protected_official_wyoming.URL,
        "workbook": protected_official_wyoming.WORKBOOK,
        "sheet": "Statewide Total Ballots Cast",
        "cell": "B28",
        "county_rows": 23,
        "initial_shard": {
            "bytes": 102767,
            "sha256": "bc20d19bf2e516a45feb2f0af613708f6be295050305168ea05c2eeab5170c9c",
        },
    },
}
NOTES = [
    "Direct native statewide Total Ballots Cast cell, checked against every county parent; "
    "not a sum of candidate votes or an allocation to local areas.",
    "No matched registration, VAP, CVAP, VEP or demographic denominator is supplied here; "
    "no turnout rate or unique-voter count is qualified.",
    "The workbook filename says OFFICIAL. A native count-update clock, reporting-completion "
    "counter and separate certification evidence are not supplied.",
    "Existing mail activity, county and precinct observations remain separate and are not added.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=6, mtime=0))
    body[9] = 3
    return bytes(body)


def identity(code):
    return observation_id(PROFILES[code]["source_id"], code + "-2026-11-03-general",
                          code + "-native-statewide-total", "native-total-ballots-cast",
                          "all_methods")


def native_summary(code, entry):
    profile = PROFILES[code]
    require(isinstance(entry, dict) and entry.get("status") == "reported"
            and isinstance(entry.get("data"), dict),
            "Statewide ballot parent needs reported native evidence")
    data = entry["data"]
    facts = data.get("native_facts")
    require(code == "WY" and protected_official_wyoming.from_facts(facts) == data,
            "Statewide ballot parent differs from its complete native facts")
    original = entry.get("source")
    require(original == {"url": profile["url"], **facts["original"]},
            "Statewide ballot original pin or URL changed")
    controls = data["races"][0]["native_contest_controls"]
    return {
        "contract": CONTRACT,
        "source": copy.deepcopy(original),
        "query_pin": pin(encoded(facts)),
        "workbook": profile["workbook"], "sheet": profile["sheet"], "cell": profile["cell"],
        "ballots": controls["ballots"],
        "counties": [{key: row[key] for key in ("county", "physical_row", "ballots")}
                     for row in controls["counties"]],
    }


def observation(code, summary, retained=False):
    profile = PROFILES[code]
    require(isinstance(summary, dict) and set(summary) == {
        "contract", "source", "query_pin", "workbook", "sheet", "cell", "ballots", "counties",
    }, "Malformed reviewed statewide ballot summary")
    require(summary["contract"] == CONTRACT and all(
        summary[key] == profile[key] for key in ("workbook", "sheet", "cell")
    ), "Statewide ballot physical parent changed")
    source = summary["source"]
    for selected in (source, summary["query_pin"]):
        require(isinstance(selected, dict) and type(selected.get("bytes")) is int
                and selected["bytes"] > 0
                and isinstance(selected.get("sha256"), str)
                and len(selected["sha256"]) == 64
                and all(char in "0123456789abcdef" for char in selected["sha256"]),
                "Statewide ballot source or query pin is missing")
    require(set(source) == {"url", "bytes", "sha256"} and source["url"] == profile["url"],
            "Statewide ballot source identity changed")
    counties = summary["counties"]
    require(isinstance(counties, list) and len(counties) == profile["county_rows"],
            "Statewide ballot county controls are incomplete")
    require(all(isinstance(row, dict) and set(row) == {"county", "physical_row", "ballots"}
                and isinstance(row["county"], str) and row["county"]
                and type(row["physical_row"]) is int for row in counties)
            and len({row["county"] for row in counties}) == len(counties)
            and [row["physical_row"] for row in counties] == list(range(5, 28)),
            "Statewide ballot county identity or physical rows changed")
    total = summary["ballots"]
    require(type(total) is int and count(total) == total
            and all(type(row["ballots"]) is int and count(row["ballots"]) == row["ballots"]
                    for row in counties)
            and sum(row["ballots"] for row in counties) == total,
            "Statewide ballot controls do not reconcile")
    status = "retained_after_failure" if retained else "reported"
    view = {
        "state": profile["state"], "state_code": code, "year": 2026,
        "geography_level": "statewide", "mode": "official", "status": status,
        "ballots": total, "denominator": None, "denominator_basis": "electorate_not_supplied",
        "reported_pct": None, "validated_pct": None, "published_pct": None,
        "native_printed_pct": None, "source_date": None, "source_update_label": None,
        "source_update_timezone": None, "source_status_literal": None,
        "reported_units": None, "total_units": None,
        "source_url": source["url"], "source_sha256": source["sha256"],
        "complete_download_url": None, "automatic_source_refresh": True,
        "participation_measure_kind": "ballots_cast",
        "participation_measure_literal": "Total Ballots Cast",
        "participation_measure_label": "Native statewide ballots cast",
        "cast_ballot_count_qualified": True, "unique_voter_count_qualified": False,
        "maps_approved": False, "quality": list(NOTES),
        "source_reporting_label": " ".join(NOTES),
        "statewide_ballot_parent": copy.deepcopy(summary),
    }
    row = {
        "contract": VERSION, "id": identity(code),
        "election": {"id": code + "-2026-11-03-general", "year": 2026,
                     "date": "2026-11-03", "type": "general", "qualification": "native"},
        "geography": {
            "id": code + "-native-statewide-total", "name": profile["state"],
            "state_code": code, "level": "state", "parent_id": None,
            "join": {"status": "nongeographic", "reference_id": None,
                     "feature_key": None, "evidence": None},
        },
        "measure": {"id": "native-total-ballots-cast", "literal": "Total Ballots Cast",
                    "kind": "ballots_cast", "mode": "all_methods", "unit": "ballots"},
        "count": {"value": total, "literal": total, "status": "reported"},
        "denominator": None,
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {"literal": None, "reported_units": None,
                             "total_units": None, "complete": None},
        "source": {"id": profile["source_id"], "url": source["url"],
                   "input_sha256": source["sha256"],
                   "selector": {key: profile[key] for key in ("workbook", "sheet", "cell")},
                   "classification": "public_aggregate", "fields": copy.deepcopy(view)},
        "quality": {"conflicts": [], "notes": list(NOTES)}, "view": view,
    }
    return validate(row)


def validate_existing(code, row):
    view = row.get("view", {})
    require(view.get("status") in ("reported", "retained_after_failure"),
            "Statewide ballot retained status changed")
    expected = observation(code, view.get("statewide_ballot_parent"),
                           view["status"] == "retained_after_failure")
    require(row == expected, "Existing statewide ballot observation changed")


def reviewed_addition(code, old, new, previous_pin):
    if code not in PROFILES or previous_pin != PROFILES[code]["initial_shard"]:
        return False
    selected = identity(code)
    if selected in old or set(new) != set(old) | {selected}:
        return False
    try:
        validate_existing(code, new[selected])
    except (ValueError, KeyError, TypeError):
        return False
    return all(old[key] == new[key] for key in old)


def project(files, snapshot):
    result = dict(files)
    index = json.loads(files["index.json"])
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    original_current = copy.deepcopy(current)
    require(index.get("contract") == "participation.count_index.v1" and index.get("year") == 2026
            and current.get("contract") == "participation.current_snapshot.v1",
            "Wrong statewide ballot count input contract")
    changes = []
    feeds = snapshot.get("congress", {}).get("official_candidate_evidence", {})
    for code, profile in PROFILES.items():
        declaration = index["states"][code]
        path = declaration["file"]
        require(pin(result[path]) == {key: declaration[key] for key in ("bytes", "sha256")},
                "Statewide ballot canonical shard pin changed")
        shard = json.loads(gzip.decompress(result[path]))
        require(shard.get("state_code") == code and shard.get("year") == 2026
                and shard.get("contract") == "participation.count_snapshot.v1",
                "Wrong statewide ballot state inventory")
        rows = {row["id"]: row for row in shard["records"]}
        require(len(rows) == len(shard["records"]), "Duplicate statewide ballot observation")
        selected = identity(code)
        previous = rows.get(selected)
        if previous is not None:
            validate_existing(code, previous)
        entry = feeds.get(profile["feed"])
        if not isinstance(entry, dict) or entry.get("status") != "reported":
            if previous is None:
                continue
            row = observation(code, previous["view"]["statewide_ballot_parent"], retained=True)
        else:
            row = observation(code, native_summary(code, entry))
            if previous is not None:
                before = previous["view"]["statewide_ballot_parent"]
                after = row["view"]["statewide_ballot_parent"]
                require(before["source"]["sha256"] != after["source"]["sha256"] or before == after,
                        "Unchanged statewide ballot original has different native facts")
        reporting = current["snapshot"]["reporting"]
        mirrors = [item for item in reporting if item["state_code"] == code]
        require(len(mirrors) <= 1 and (not mirrors or previous is not None
                and mirrors[0] == previous["view"]), "Statewide ballot display preimage changed")
        if previous is None:
            require(pin(result[path]) == profile["initial_shard"],
                    "Unreviewed initial statewide ballot inventory")
            shard["records"].append(row)
        else:
            shard["records"] = [row if item["id"] == selected else item for item in shard["records"]]
        if mirrors:
            reporting[reporting.index(mirrors[0])] = copy.deepcopy(row["view"])
        else:
            reporting.append(copy.deepcopy(row["view"]))
        if row != previous:
            result[path] = compressed(shard)
            declaration.update(pin(result[path]), records=len(shard["records"]))
            if code in index.get("coverage", {}):
                records = shard["records"]
                index["coverage"][code].update(
                    records=len(records),
                    reported=sum(item["count"]["status"] == "reported" for item in records),
                    unknown=sum(item["count"]["status"] == "unknown" for item in records),
                    withheld=sum(item["count"]["status"] == "withheld" for item in records),
                    zeros=sum(item["count"]["value"] == 0 for item in records),
                    qualified_fractions=sum(bool(item["denominator"] and item["denominator"]["qualified"])
                                            for item in records))
            changes.append({"state_code": code, "id": selected,
                            "previous": previous["count"]["value"] if previous else None,
                            "current": row["count"]["value"], "source_status": row["view"]["status"]})
    if changes:
        result["index.json"] = encoded(index)
    if current != original_current:
        result["current.json.gz"] = compressed(current)
    return result, changes


def exports(files):
    current = json.loads(gzip.decompress(files["current.json.gz"]))
    rows = [row for row in current["snapshot"]["reporting"]
            if "statewide_ballot_parent" in row]
    fields = ("state_code", "year", "ballots", "status", "denominator", "validated_pct",
              "source_update_label", "source_update_timezone", "source_url", "source_sha256")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: row[key] for key in fields} for row in rows)
    return {
        "participation/native-statewide-ballot-totals.csv": output.getvalue().encode(),
        "participation/native-statewide-ballot-totals.json.gz": compressed({
            "contract": CONTRACT, "rows": rows, "limitations": list(NOTES),
        }),
    }
