"""Freeze sufficient already-held provider aggregates; do not acquire or rerun collection."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile


SNAPSHOT = "20261109T083731Z"
SNAPSHOT_SHA = "4bcec0e7a6af3395c6e142148c5102a0f8621c77469baa690316bc56e9b34c62"
STATES = tuple("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
MODES = ("inperson", "returned")
DIMENSIONS = ("age_range", "gender", "race", "ethnicity")
CAP_FIELDS = dict(age_range="age", gender="gender", race="race", ethnicity="ethnicity")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def freeze(root, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed sufficient-input freeze")
    path = root / "public/data/nationwide" / SNAPSHOT / "snapshot.json"
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != SNAPSHOT_SHA:
        raise ValueError("Changed pinned already-collected source snapshot")
    snapshot = json.loads(body)
    jurisdictions = {row["state_code"]: row["state"] for row in snapshot["coverage"]}
    if set(jurisdictions) != set(STATES):
        raise ValueError("Incomplete captured all-state/DC assessment")
    datasets, components, files = {}, {}, {}
    source = root / "data/raw/nationwide" / SNAPSHOT
    for key, entry in snapshot["datasets"].items():
        if entry["kind"] == "official":
            continue
        state, kind = entry["state"], entry["kind"]
        if state not in STATES or not (kind == "capabilities" or kind in MODES
                                      or any(kind == mode + "-" + dimension for mode in MODES for dimension in DIMENSIONS)):
            raise ValueError("Unexpected captured source kind")
        original = (source / entry["source"]["file"]).read_bytes()
        if (len(original) != entry["source"]["bytes"]
                or hashlib.sha256(original).hexdigest() != entry["source"]["sha256"]):
            raise ValueError("Changed original captured public aggregate")
        saved = copy.deepcopy(entry)
        if kind in MODES:
            data = saved.get("data")
            if data is not None:
                saved["data"] = {name: data[name] for name in ("date", "total", "quality")}
                native = json.loads(original)
                components[key] = dict(native_state=native["state"], native_category=native["category"],
                    native_source_date=native["snapshot_date"], native_election_name=native.get("election_name"),
                    native_parent_field="statewide_total", native_component_count_field="votes",
                    native_count_components=[value["votes"] for value in native["statewide_total"].values()],
                    component_labels_colors_and_county_regions_excluded=True,
                    original_full_body_bytes=len(original), original_full_body_sha256=hashlib.sha256(original).hexdigest())
        else:
            files["raw/" + entry["source"]["file"]] = original
        datasets[key] = saved
    if any(state + "-capabilities" not in datasets for state in STATES):
        raise ValueError("Missing complete source capability assessment")
    capture = dict(schema="provider-demographic-capture-v1", source_snapshot_id=SNAPSHOT,
        source_snapshot_sha256=SNAPSHOT_SHA, source_snapshot_bytes=len(body),
        source_repository_commit="857054041fb02bf5681cfd612a20d35a8b4a719f",
        source_retrieved_at=snapshot["retrieved_at"], collector_election_context_date=snapshot["election_date"],
        election_context_not_independent_native_election_id=True,
        jurisdictions=jurisdictions, datasets=datasets,
        already_reviewed_reduced_mode_and_demographic_captures_reused=True,
        no_new_acquisition_or_completed_collector_campaign_rerun=True,
        county_regions_party_labels_colors_web_bodies_and_personal_records_excluded=True)
    files["qualified-capture.json"] = encoded(capture)
    files["native-mode-parent-components.json"] = encoded(components)
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                                     for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    with zipfile.ZipFile(output / "complete-provider-capture-inputs.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    result = output / "complete-provider-capture-inputs.zip"
    print(json.dumps(dict(bytes=result.stat().st_size, sha256=hashlib.sha256(result.read_bytes()).hexdigest(),
        members=len(files), datasets=len(datasets), raw_demographic_and_capability_files=len(files) - 3,
        anonymous_native_mode_parent_vectors=len(components)), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    freeze(args.source_root, args.output)
