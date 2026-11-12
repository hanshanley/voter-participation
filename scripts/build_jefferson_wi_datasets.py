"""Extend accepted count/binding snapshots only with reconciled Jefferson WI facts."""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

from review_jefferson_wi_participation import encoded

TAG = "participation-wisconsin-jefferson-counts-20261112-01"
RELEASE = "https://github.com/hanshanley/margin_of_error/releases/download/"+TAG+"/"
MODES = ("available", "official", "uf_vep", "uf_vap")


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=9, mtime=0))
    body[9] = 3
    return bytes(body)


def build(query, accepted_counts, accepted_native, original_reference):
    old_count = json.loads(gzip.decompress((accepted_counts/"states/WI.json.gz").read_bytes()))
    old_index = json.loads((accepted_counts/"index.json").read_bytes())
    old_native = json.loads((accepted_native/"index.json").read_bytes())
    counts, index, native = copy.deepcopy(old_count), copy.deepcopy(old_index), copy.deepcopy(old_native)
    if query["state_code"] != "WI" or query["county"] != "Jefferson County" or query["county_reference_fips"] != "55055":
        raise ValueError("Wrong county source")
    geometry = json.loads(gzip.decompress(original_reference))
    match = [feature for feature in geometry["features"] if feature["properties"]["key"] == "55055"]
    if (len(match) != 1 or match[0]["properties"]["name"] != "Jefferson County"
            or match[0]["properties"]["state_code"] != "WI" or len(geometry["features"]) != 72):
        raise ValueError("Contextual county identity does not match the native source")
    reference = next(row["view"]["reference_geometry"] for row in counts["records"] if row["view"].get("reference_geometry"))
    if pin(original_reference)["sha256"] != reference["sha256"]:
        raise ValueError("Accepted county reference checksum differs")
    county_id = "reviewed:WI:Jefferson County"
    notes = [
        "Complete native 32-row Ballots Cast and Registered Voters inventories sum to the separately printed county totals.",
        "Source header says Official Results but retains an unofficial-until-canvass disclaimer; certification is not independently established.",
        "Native 32-of-32 reporting is retained alongside the warning that 100% can refer to only one machine; final/all-machine or all-mode completeness is not inferred.",
        "Same-report registrations have no separately established reference date; any county fraction is a conditional registered-snapshot fraction, not VEP/VAP/CVAP or unique-person turnout.",
        "Native reporting labels can combine noncontiguous wards and are never split into invented precincts or allocated to polygons.",
        "The literal source clock has no declared timezone; no UTC, receipt-clock or election-day-registration adjustment is substituted.",
    ]
    base = dict(year=2026, state_code="WI", county="Jefferson County", county_id=county_id,
        county_fips="55055", source_url=query["source_url"], source_update_label=query["source_update_label"],
        source_update_timezone=None, source_mode="source_defined_native_report",
        source_status_literal="Native Official Results header; unofficial-until-canvass and machine-completeness disclaimers retained",
        reported_units=query["reported_units"], total_units=query["total_units"],
        participation_measure_kind="native_reported_ballots_cast",
        participation_measure_literal="Ballots Cast", participation_measure_label="Native Ballots Cast (county report snapshot)",
        cast_ballot_count_qualified=True, unique_voter_count_qualified=False,
        denominator_basis="native_registered_voters_same_report_snapshot",
        complete_download_url=RELEASE+"complete-analysis.zip", quality=notes,
        native_record=dict(native_fips="", native_update_literal=query["source_update_label"],
            county_scope="Number of votes reflect Jefferson County only",
            official_header=query["native_header_official_results"],
            unofficial_disclaimer=query["native_unofficial_until_canvass_disclaimer"],
            machine_disclaimer=query["native_machine_completeness_disclaimer"]))

    def observation(view, key, level, qualified):
        row = dict(contract="participation.observation.v1",
            id=hashlib.sha256(encoded([query["source_sha256"], key, "Ballots Cast", 2026])).hexdigest()[:32],
            election=dict(id="jefferson-wi-11032026-native-report", year=2026, date="2026-11-03",
                          type="general", qualification="native"),
            geography=dict(id=key, name=view.get("precinct", view["county"]), state_code="WI", level=level,
                parent_id=None if level == "county" else county_id,
                join=dict(status="approved" if level == "county" else "unreviewed",
                    reference_id=reference["sha256"] if level == "county" else None,
                    feature_key="55055" if level == "county" else None,
                    evidence="Literal Jefferson County WI source matched to the accepted full72-county Census context; no precinct-boundary approval."
                    if level == "county" else "Native ward grouping retained; no geographic boundary join approved.")),
            measure=dict(id="native-ballots-cast", literal="Ballots Cast", kind="ballots_cast",
                         mode="source_defined", unit="source_reported_ballots"),
            count=dict(value=view["ballots"], status="reported", literal=view["ballots"]),
            denominator=dict(value=view["denominator"], literal="Registered Voters",
                             basis=base["denominator_basis"], qualified=qualified),
            source_clock=dict(literal=query["source_update_label"], timezone=None, qualification="native_literal_timezone_not_declared"),
            reporting_status=dict(literal="Precincts Reporting 32 of 32 for 100%; single-machine disclaimer retained",
                                  reported_units=32, total_units=32, complete=None),
            source=dict(id="jefferson-wi-native-20261112", url=query["source_url"],
                        input_sha256=query["source_sha256"], classification="public_aggregate",
                        selector=dict(table="Registered Voters / Ballots Cast", unit=key), fields=copy.deepcopy(view)),
            quality=dict(notes=notes, conflicts=[], native_conflict_status="status_disclaimers_retained_not_repaired"),
            view=view)
        return row

    county_view = dict(base, geography_level="county", ballots=query["ballots"],
        denominator=query["registered"], reported_pct=query["same_report_registration_fraction_percent"],
        reference_geometry=reference)
    county = observation(county_view, county_id, "county", True)
    if county_id in {row["view"].get("county_id") for row in old_count["records"]}:
        raise ValueError("Jefferson observation already exists; do not duplicate")
    counts["records"].append(county)
    reporting = []
    for unit in query["reporting_units"]:
        properties = dict(key=unit["unit_key"], year=2026, state_code="WI", county="Jefferson County",
            county_id=county_id, precinct=unit["reporting_unit"],
            reporting_unit_kind="native_ward_group", source_split_label="Jefferson County portion only",
            ballots=unit["ballots"], registered=unit["registered"], denominator=unit["registered"],
            reported_pct=None, native_printed_pct=unit["native_printed_percent"],
            basis="Literal source ward-group ballot statistics; registrations retained but no precinct rate or map qualified.",
            quality_flags=notes, source_update_label=query["source_update_label"])
        view = dict(base)
        view.update(properties)
        view.update(geography_level="reporting_unit", unit_key=unit["unit_key"],
                    ballots=unit["ballots"], denominator=unit["registered"], reported_pct=None)
        view["precinct"] = unit["reporting_unit"]
        row = observation(view, unit["unit_key"], "reporting_unit", False)
        counts["records"].append(row)
        reporting.append(dict(properties=properties, observation=row))
    for mode in MODES:
        counts["views"][mode]["counties"].append(county["id"])
        counts["views"][mode]["precincts"].extend(row["observation"]["id"] for row in reporting)
    if counts["records"][:len(old_count["records"])] != old_count["records"]:
        raise ValueError("Accepted observations changed")
    by_id = {row["id"]: row for row in counts["records"]}
    declaration = index["states"]["WI"]
    declaration["records"] = len(counts["records"])
    for mode in MODES:
        frame = counts["views"][mode]
        for partition in ("counties", "precincts"):
            chosen = [by_id[key] for key in frame[partition]]
            declaration["views"][mode][partition] = len(chosen)
            declaration["views"][mode]["dispositions"][partition] = dict(
                reported=sum(row["count"]["status"] == "reported" for row in chosen),
                unknown=sum(row["count"]["status"] == "unknown" for row in chosen),
                withheld=sum(row["count"]["status"] == "withheld" for row in chosen),
                qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"]) for row in chosen),
                geography_levels=sorted({row["geography"]["level"] for row in chosen}))
    index["coverage"]["WI"] = dict(records=len(counts["records"]),
        reported=sum(row["count"]["status"] == "reported" for row in counts["records"]),
        zeros=sum(row["count"]["value"] == 0 for row in counts["records"]),
        unknown=sum(row["count"]["status"] == "unknown" for row in counts["records"]),
        withheld=sum(row["count"]["status"] == "withheld" for row in counts["records"]),
        qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"]) for row in counts["records"]))
    index["new_native_review"] = "jefferson-wi-20261112-01"
    wi_body = compressed(counts)
    declaration.update(pin(wi_body))
    template = copy.deepcopy(native["county_bindings"]["WI"]["in_person_early"])
    qualifier_keys = tuple(template["rows"][0]["qualifier"])
    for mode in MODES:
        binding = copy.deepcopy(template)
        binding["embedded_reference_required"] = False
        binding["rows"] = []
        for key in counts["views"][mode]["counties"]:
            view = by_id[key]["view"]
            matching = [feature for feature in geometry["features"]
                        if feature["properties"]["name"].replace(" County", "") == view["county"].replace(" County", "")]
            if len(matching) != 1:
                raise ValueError("County identity is not unique in the complete accepted reference")
            binding["rows"].append(dict(county_id=view["county_id"],
                feature_key=matching[0]["properties"]["key"],
                qualifier={key: view.get(key) for key in qualifier_keys}))
        native["county_bindings"]["WI"][mode] = binding
    table_body = compressed(dict(contract="participation.reporting_units.v1", state_code="WI", records=reporting))
    native["reporting_tables"]["WI"] = dict(file="tables/WI.json.gz", **pin(table_body), rows=32,
        eligible_modes=list(MODES), coverage=dict(source_rows=32, fractions=0, reported=32, unknown=0, withheld=0))
    native["reporting_sources"]["WI"] = dict(rows=32, scope="Jefferson County only; not statewide Wisconsin coverage",
        source_update_label=query["source_update_label"],
        geometry_note="32 literal source ward groups; no precinct polygons or split-ward allocation approved.",
        complete_download_url=RELEASE+"complete-analysis.zip", data_url=RELEASE+"reporting-unit-participation.json.gz")
    native["additional_native_review"] = "jefferson-wi-20261112-01"
    native["county_frame_checks"] += len(MODES)
    changes = {"counts": {"states/WI.json.gz": wi_body, "index.json": encoded(index)},
               "native": {"tables/WI.json.gz": table_body, "index.json": encoded(native)}}
    flat = compressed([row["properties"] for row in reporting])
    return changes, flat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("query", "accepted-counts", "accepted-native", "county-reference", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh complete dataset output")
    query = json.loads(args.query.read_bytes())
    changes, flat = build(query, args.accepted_counts, args.accepted_native, args.county_reference.read_bytes())
    for family, old in (("counts", args.accepted_counts), ("native", args.accepted_native)):
        descriptor = json.loads((old/"dataset.json").read_bytes())
        root = args.output/family
        root.mkdir(parents=True)
        for name, metadata in descriptor["files"].items():
            body = (old/name).read_bytes()
            if pin(body) != metadata:
                raise ValueError("Accepted full runtime input changed")
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(changes[family].get(name, body))
        for name, body in changes[family].items():
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        files = {str(path.relative_to(root)): pin(path.read_bytes()) for path in root.rglob("*") if path.is_file()}
        descriptor.update(files=files, index=dict(file="index.json", **files["index.json"]),
            version=pin(encoded(dict(files=files, contract=descriptor["record_contract"])))["sha256"],
            complete_download=None)
        (root/"dataset.json").write_bytes(encoded(descriptor))
    (args.output/"reporting-unit-participation.json.gz").write_bytes(flat)
    print(json.dumps(dict(status="compiled_jefferson_county_and32_reporting_units",
        unchanged_state_files=50, new_county_observations=1, new_reporting_unit_observations=32)))


if __name__ == "__main__":
    main()
