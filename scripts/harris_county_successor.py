"""Connect the held Harris counted-ballot snapshot without replacing its source facts."""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

TAG = "participation-harris-county-counts-20261112-01"
RELEASE = "https://github.com/hanshanley/margin_of_error/releases/download/"+TAG+"/"
MODES = ("available", "official", "uf_vep", "uf_vap")
SOURCE_SHA = "64d92c0f8787191e42d3889caf60ecc5e56a7f1e2a8fdfd406152afcdc60f7b3"


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def compressed(value):
    body = bytearray(gzip.compress(encoded(value), compresslevel=9, mtime=0))
    body[9] = 3
    return bytes(body)


def qualify(source):
    if (source["source"]["sha256"] != SOURCE_SHA or source["source"]["bytes"] != 29813
            or source["election"]["date"] != "2026-11-03"
            or source["jurisdiction"]["state"] != "TX" or source["jurisdiction"]["county"] != "Harris"
            or source["source"]["status_native"] != "Preliminary Election Reconciliation - Unofficial Totals"):
        raise ValueError("Wrong pinned native county, election or source")
    measures = source["measures"]
    if len(measures) != 13:
        raise ValueError("The complete native query must contain thirteen rows")
    values = {}
    for row in measures:
        key = (row["category"], row["mode"])
        if key in values or type(row["count"]) is not int:
            raise ValueError("Duplicate or noninteger native count")
        if row["count"] < 0 and key != ("reconciliation", "difference"):
            raise ValueError("Negative ballot count, not the signed native reconciliation")
        values[key] = row["count"]
    roster = values["voters", "total"]
    counted = values["counted_ballots", "total"]
    pending = values["rejected_or_pending", "total"]
    difference = values["reconciliation", "difference"]
    if (values["voters", "in_person"]+values["voters", "by_mail"] != roster
            or values["counted_ballots", "in_person"]+values["counted_ballots", "mail"] != counted
            or values["rejected_or_pending", "provisional"]+values["rejected_or_pending", "mail"] != pending
            or roster-pending-counted != difference
            or source["counted_ballots"]["count"] != counted
            or source["primary_participation_observation"]["count"] != roster
            or source["denominator"]["count"] != values["denominator", "registered_voters"]):
        raise ValueError("Native systems or component totals disagree with the complete factual query")
    return dict(counted=counted, roster=roster, registered=values["denominator", "registered_voters"],
        pending=pending, signed_native_difference=difference,
        literal_counted_label=source["counted_ballots"]["native_label"],
        report_date=source["source"]["report_date_native"], report_time=source["source"]["report_time_native"],
        timezone=source["source"]["timezone_native"], all13_native_measures=measures,
        precinct_geometry_approved=False, denominator_qualified=False, first_ever_or_population_claim=False)


def build(source, old_counts, old_native, reference_body):
    facts = qualify(source)
    geometry = json.loads(gzip.decompress(reference_body))
    matches = [f for f in geometry["features"] if f["properties"]["key"] == "48201"]
    if len(geometry["features"]) != 254 or len(matches) != 1 or matches[0]["properties"]["name"] != "Harris County":
        raise ValueError("Harris is not uniquely identified by the complete accepted county reference")
    state = copy.deepcopy(json.loads(gzip.decompress((old_counts/"states/TX.json.gz").read_bytes())))
    index = copy.deepcopy(json.loads((old_counts/"index.json").read_bytes()))
    native = copy.deepcopy(json.loads((old_native/"index.json").read_bytes()))
    reference = next(row["view"]["reference_geometry"] for row in state["records"]
                     if row["view"].get("reference_geometry"))
    if reference["sha256"] != pin(reference_body)["sha256"]:
        raise ValueError("Accepted reference bytes differ")
    county_id = "reviewed:TX:Harris County"
    if any(row["view"].get("county_id") == county_id for row in state["records"]):
        raise ValueError("Harris successor already exists")
    notes = [
        "Harris County only. Literal counted ballots are not the separate election-roster voter total.",
        "Counted ballots 1,392,280 = 1,345,094 in person + 47,186 mail; roster voters remain separately 1,393,495.",
        "Native C-F-I reconciliation is -4,085; rejected/pending 5,300 and possible-addition fields are not added to counted ballots.",
        "November 4, 2026 report is preliminary and unofficial; no finality, certified count or unique-person qualification.",
        "Registered Voters 2,761,770 has undeclared status/cutoff scope; no new registered, VEP, VAP or CVAP rate is qualified.",
        "Source supplies a report date but no report time or timezone; HTTP Last-Modified is not substituted.",
        "48201 is contextual Census identity, not a FIPS field printed in the native report. No precinct or demographic allocation.",
        "Best available now prioritizes this native county snapshot; all earlier county early/mail observations remain in their separate modes.",
    ]
    view = dict(year=2026, state_code="TX", county="Harris County", county_id=county_id,
        county_fips="48201", geography_level="county", review_id="harris-held-native-20261112-01",
        ballots=facts["counted"], denominator=facts["registered"], reported_pct=None,
        denominator_basis="native_registered_voters_status_and_cutoff_unqualified",
        participation_measure_kind="native_counted_ballots", participation_measure_literal=facts["literal_counted_label"],
        participation_measure_label="Native counted ballots (preliminary reconciliation)",
        cast_ballot_count_qualified=False, unique_voter_count_qualified=False,
        source_mode="source_defined_native_reconciliation", source_url=source["source"]["url"],
        source_update_label=facts["report_date"], source_update_timezone=None,
        source_status_literal=source["source"]["status_native"],
        source_reporting_label="County reconciliation only; no precinct-reporting or final-completeness status inferred.",
        native_printed_pct=None, reported_units=None, total_units=None, maps_approved=True,
        reference_geometry=reference, complete_download_url=RELEASE+"complete-analysis.zip",
        quality=notes, native_record=dict(source_county="Harris", native_fips=None,
            report_date=facts["report_date"], report_time=None, timezone=None,
            full_native_measures=source["measures"], source_header_status=source["source"]["status_native"]))
    row = dict(contract="participation.observation.v1",
        id=hashlib.sha256(encoded([SOURCE_SHA, "Harris", facts["literal_counted_label"]])).hexdigest()[:32],
        election=dict(id="harris-2026-general-special-reconciliation", year=2026, date="2026-11-03",
                      type="general_and_special", qualification="native"),
        geography=dict(id=county_id, name="Harris", level="county", state_code="TX", parent_id=None,
            join=dict(status="approved", reference_id=reference["sha256"], feature_key="48201",
                      evidence="Literal Harris, Texas county report matched to unchanged complete254-county Census context.")),
        measure=dict(id="native-counted-ballots", literal=facts["literal_counted_label"],
                     kind="participation_reported", mode="source_defined", unit="source_reported_counted_ballots"),
        count=dict(value=facts["counted"], status="reported", literal=facts["counted"]),
        denominator=dict(value=facts["registered"], literal="Registered Voters",
                         basis=view["denominator_basis"], qualified=False),
        source_clock=dict(literal=facts["report_date"], timezone=None, qualification="native_date_only"),
        reporting_status=dict(literal=source["source"]["status_native"],
                              reported_units=None, total_units=None, complete=None),
        source=dict(id="harris-preliminary-reconciliation-20261104", url=source["source"]["url"],
                    input_sha256=SOURCE_SHA, classification="public_aggregate",
                    selector=dict(field=facts["literal_counted_label"]), fields=copy.deepcopy(view)),
        quality=dict(notes=notes, conflicts=[dict(code="native_roster_rejected_counted_disagreement",
            native_difference=facts["signed_native_difference"], repaired=False)]), view=view)
    old_records = copy.deepcopy(state["records"])
    state["records"].append(row)
    added_frames = 0
    template = native["county_bindings"]["TX"]["in_person_early"]
    keys = tuple(template["rows"][0]["qualifier"])
    for mode in MODES:
        frame = state["views"][mode]
        frame["counties"] = [row["id"]]
        frame["qualified"] = True
        frame.pop("unavailable_note", None)
        binding = copy.deepcopy(template)
        binding["embedded_reference_required"] = True
        binding["rows"] = [dict(county_id=county_id, feature_key="48201",
                               qualifier={key: view.get(key) for key in keys})]
        added_frames += mode not in native["county_bindings"]["TX"]
        native["county_bindings"]["TX"][mode] = binding
        declaration = index["states"]["TX"]["views"][mode]
        declaration["counties"] = 1
        declaration["dispositions"]["counties"] = dict(reported=1, unknown=0, withheld=0,
            qualified_fractions=0, geography_levels=["county"])
    assert state["records"][:-1] == old_records
    native["county_frame_checks"] += added_frames
    native["harris_county_review"] = "held-native-20261112-01"
    body = compressed(state)
    index["states"]["TX"].update(pin(body), records=len(state["records"]))
    index["coverage"]["TX"] = dict(records=len(state["records"]),
        reported=sum(row["count"]["status"] == "reported" for row in state["records"]),
        zeros=sum(row["count"]["value"] == 0 for row in state["records"]),
        unknown=sum(row["count"]["status"] == "unknown" for row in state["records"]),
        withheld=sum(row["count"]["status"] == "withheld" for row in state["records"]),
        qualified_fractions=sum(bool(row["denominator"] and row["denominator"]["qualified"]) for row in state["records"]))
    index["harris_county_review"] = "held-native-20261112-01"
    return {"counts": {"states/TX.json.gz": body, "index.json": encoded(index)},
            "native": {"index.json": encoded(native)}}, facts


def compile_datasets(source_path, old_counts, old_native, reference, output):
    if output.exists():
        raise ValueError("Use a fresh complete output")
    changes, facts = build(json.loads(source_path.read_bytes()), old_counts, old_native, reference.read_bytes())
    for family, old in (("counts", old_counts), ("native", old_native)):
        descriptor = json.loads((old/"dataset.json").read_bytes())
        root = output/family
        root.mkdir(parents=True)
        for name, metadata in descriptor["files"].items():
            body = (old/name).read_bytes()
            if pin(body) != metadata:
                raise ValueError("Changed accepted baseline")
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(changes[family].get(name, body))
        files = {str(path.relative_to(root)): pin(path.read_bytes()) for path in root.rglob("*") if path.is_file()}
        descriptor.update(files=files, index=dict(file="index.json", **files["index.json"]),
            version=pin(encoded(dict(files=files, contract=descriptor["record_contract"])))["sha256"],
            complete_download=None)
        (root/"dataset.json").write_bytes(encoded(descriptor))
    (output/"complete-harris-query.json").write_bytes(encoded(facts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "counts", "native", "reference", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args()
    compile_datasets(args.source, args.counts, args.native, args.reference, args.output)
    print(json.dumps(dict(status="compiled_held_harris_native_count", new_county_observations=1,
                          unchanged_state_shards=50, early_mail_frames_preserved=True)))


if __name__ == "__main__":
    main()
