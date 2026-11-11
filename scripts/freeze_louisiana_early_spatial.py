"""Freeze full accepted sufficient inputs, without repeating original reductions."""

import argparse
import importlib.util
import json
from pathlib import Path
import zipfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native-science", "runtime-science", "reference", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("spatial", Path(__file__).with_name("louisiana_early_spatial.py"))
    primary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(primary)
    predecessors = {}
    for path, name, sha in ((args.native_science, "complete-native-science.zip", primary.SOURCE_SCIENCE),
            (args.runtime_science, "complete-runtime-science.zip", primary.RUNTIME_SCIENCE)):
        predecessors[name] = primary.file_pin(path)
        if predecessors[name]["sha256"] != sha:
            raise ValueError("Changed complete accepted predecessor")
    if args.output.exists() or primary.file_pin(args.reference)["sha256"] != primary.REFERENCE_SHA:
        raise ValueError("Changed reference or nonfresh output")
    members = {}
    for path, selection in ((args.native_science, {
            "results/complete-result.json": "source-result.json",
            "inputs/native-facts.json": "source-native-facts.json",
            "inputs/independent-native.json": "source-independent-native.json"}),
            (args.runtime_science, {
            "runtime/counts/states/LA.json.gz": "counts-LA.json.gz",
            "runtime/counts/index.json": "counts-index.json",
            "runtime/counts/dataset.json": "counts-dataset.json",
            "runtime/native/index.json": "native-index.json",
            "runtime/native/dataset.json": "native-dataset.json"})):
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for name, destination in selection.items():
                body = archive.read(name)
                if primary.pin(body) != manifest["files"][name]:
                    raise ValueError("Changed full accepted source/runtime member")
                members[destination] = body
    members["LA-reference.geojson.gz"] = args.reference.read_bytes()
    members["policy.json"] = primary.encoded(dict(
        contract="participation.louisiana_early_spatial_policy.v1",
        binding="unique_native_parish_name_to_accepted_context_reference",
        native_codes_inferred_as_FIPS=False, counts_replaced=False, geometry_repaired=False,
        election_boundaries_certified=False, provider_method_or_clock_requalified=False,
        group_turnout_inferred=False, frontend_or_catalog_activation=False))
    members["provenance.json"] = primary.encoded(dict(
        native_science_release=442055936,
        native_science_tag="participation-louisiana-early-groups-20261111-01",
        runtime_science_tag="participation-utah-count-successors-20261111-01",
        source_url="https://electionstatistics.sos.la.gov/Data/Early_Voting_Statistics/statewide/2026_1103_StatewideStats.pdf",
        source_election_date="2026-11-03", source_filter_begin="1900-01-01",
        source_filter_end="2026-11-09", source_print_clock="11/10/2026 3:10:06 AM",
        source_print_timezone=None, provider_snapshot_label="2026-11-03",
        count_version=primary.COUNT_VERSION, native_version=primary.NATIVE_VERSION,
        reference_url="https://raw.githubusercontent.com/hanshanley/margin_of_error/6b6b96caed4fa4f7c66fd206a64bd709310a69f2/data/county-results/20261105-house-02/geometry/LA.geojson.gz",
        reference_sha256=primary.REFERENCE_SHA,
        reference_scope="unchanged unsimplified 2026 Census county context, not certified election boundaries",
        common_upstream_lineage_established=False, native_ABS_qualified_as_mail_returned=False,
        source_compositions_reused_without_reduction=True))
    manifest = dict(contract="participation.louisiana_early_spatial_inputs.v1",
        files={name: primary.pin(body) for name, body in sorted(members.items())},
        complete_predecessors=predecessors)
    args.output.mkdir(parents=True)
    for name, body in {**members, "manifest.json": primary.encoded(manifest)}.items():
        (args.output / name).write_bytes(body)
    primary.load_inputs(args.output)
    print(json.dumps(dict(status="frozen_complete_accepted_spatial_inputs",
        sufficient_files=len(members), complete_predecessors=predecessors), sort_keys=True))
