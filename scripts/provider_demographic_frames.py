"""Source-native partial demographic compositions, never group turnout rates."""

import argparse
from collections import Counter
import csv
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .extract_provider_demographic_capture import CAP_FIELDS, DIMENSIONS, MODES, SNAPSHOT, SNAPSHOT_SHA, STATES, encoded


INPUT_SHA = "67fc9fa8c61be1bffcba0f433b8710ca5e0f04c2d86ad18a2e36ff24e3a7d6f5"


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Missing or invalid native nonnegative integer count")
    return value


def percentage(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def analyze(capture, components):
    if (capture["schema"] != "provider-demographic-capture-v1"
            or capture["source_snapshot_id"] != SNAPSHOT
            or capture["source_snapshot_sha256"] != SNAPSHOT_SHA
            or set(capture["jurisdictions"]) != set(STATES)):
        raise ValueError("Incomplete or changed qualified all-state/DC capture")
    datasets = capture["datasets"]
    captured_date = date.fromisoformat(capture["source_retrieved_at"][:10])
    capabilities, parents, parent_rows = {}, {}, []
    for state in STATES:
        capability = datasets.get(state + "-capabilities")
        if capability is None or capability["state"] != state or capability["kind"] != "capabilities":
            raise ValueError("Missing complete source capability assessment")
        capabilities[state] = capability.get("data") if capability["status"] == "reported" else None
        if capability["status"] == "reported" and not capabilities[state]:
            raise ValueError("Missing reported source capability data")
        if capabilities[state] and capabilities[state]["state"] != state:
            raise ValueError("Changed native capability state identity")
        for mode in MODES:
            key = state + "-" + mode
            entry = datasets.get(key)
            data = entry.get("data") if entry and entry["status"] == "reported" else None
            total, source_date, number = None, None, None
            if data is not None:
                native = components.get(key)
                if (entry["state"] != state or entry["kind"] != mode or native is None
                        or native["native_state"] != state or native["native_category"] != mode
                        or native["native_source_date"] != data["date"]):
                    raise ValueError("Changed native mode identity/date")
                values = [integer(value) for value in native["native_count_components"]]
                total = integer(data["total"])
                if not values or sum(values) != total:
                    raise ValueError("Anonymous native mode components disagree with reused source reduction")
                source_date, number = data["date"], len(values)
                parents[key] = dict(total=total, date=source_date, quality=data["quality"])
            parent_rows.append(dict(state_code=state, mode_native=mode,
                disposition="reported_source_mode_parent" if data is not None else "not_captured_current_source_mode_parent",
                native_source_date=source_date, native_source_count_total=total,
                native_component_count=number, native_components_sum=total,
                source_url=entry["source"]["url"] if entry else None,
                source_retrieved_at=entry["source"]["retrieved_at"] if entry else None,
                source_full_body_sha256=entry["source"]["sha256"] if entry else None,
                original_mode_reduction_reused=True, party_labels_and_county_regions_excluded=True,
                accepted_cast_or_unique_people_qualified=False, registered_population_denominator=None,
                group_turnout_pct=None, national_pooling=False))
    scopes, groups = [], []
    for state in STATES:
        for mode in MODES:
            capability = capabilities[state]
            category = capability["categories"].get(mode) if capability else None
            for dimension in DIMENSIONS:
                key = state + "-" + mode + "-" + dimension
                entry = datasets.get(key)
                claimed = category.get(CAP_FIELDS[dimension]) if category is not None else None
                data = entry.get("data") if entry and entry["status"] == "reported" else None
                if capability is None:
                    reason = "provider_capability_not_reported_current_capture"
                elif category is None:
                    reason = "mode_category_not_provided_by_assessed_source"
                elif claimed is not True:
                    reason = "dimension_not_provided_by_assessed_source"
                elif data is None:
                    reason = "no_usable_current_demographic_response"
                elif not data.get("date"):
                    reason = "held_missing_native_source_date"
                elif date.fromisoformat(data["date"]) > captured_date:
                    reason = "held_source_date_after_capture"
                elif integer(data["total"]) == 0:
                    reason = "held_zero_native_frame_no_composition_or_turnout_inference"
                else:
                    reason = "selected_own_demographic_frame_arithmetic"
                if data is not None and claimed is not True:
                    raise ValueError("Captured demographic response contradicts source capability")
                selected = reason == "selected_own_demographic_frame_arithmetic"
                row = dict(state_code=state, state=capture["jurisdictions"][state], mode_native=mode,
                    dimension_native=dimension,
                    provider_capability_status=datasets[state + "-capabilities"]["status"],
                    provider_capability_http_status=datasets[state + "-capabilities"]["source"]["http_status"],
                    provider_mode_category_declared=category is not None if capability else None,
                    provider_dimension_declared=claimed, disposition=reason,
                    source_snapshot_id=SNAPSHOT,
                    native_source_date=data.get("date") if data else None,
                    source_url=entry["source"]["url"] if entry else None,
                    source_retrieved_at=entry["source"]["retrieved_at"] if entry else None,
                    source_full_body_sha256=entry["source"]["sha256"] if entry else None,
                    native_demographic_total=None, native_group_count_sum=None, native_group_labels=None,
                    mode_parent_source_date=None, mode_parent_native_total=None,
                    demographic_minus_mode_total=None, same_date_and_arithmetic_parent_match=False,
                    composition_denominator_basis="own_native_demographic_response_total_not_mode_or_population",
                    independent_official_administrative_validation=False,
                    native_accepted_cast_or_unique_people_qualified=False,
                    frame_or_population_coverage_equivalence_validated=False,
                    native_group_definitions_harmonized=False, modes_or_dimensions_added=False,
                    matched_registered_or_eligible_population_denominator=None,
                    group_turnout_pct=None, allmode_turnout_pct=None, survey_model_projection=False,
                    individual_retention_or_switching=False, source_discrepancy_imputed_as_unknown_group=False,
                    national_pooling=False, local_allocation=False, design_confidence_interval=None)
                source_groups = []
                if selected:
                    if entry["state"] != state or entry["kind"] != mode + "-" + dimension:
                        raise ValueError("Changed captured demographic identity")
                    source_groups = data["groups"]
                    labels = [value["group"] for value in source_groups]
                    if (not labels or any(not isinstance(value, str) or not value.strip() for value in labels)
                            or len(set(labels)) != len(labels)):
                        raise ValueError("Missing or duplicate native demographic group label")
                    counts = [integer(value["ballots"]) for value in source_groups]
                    total = integer(data["total"])
                    if sum(counts) != total:
                        raise ValueError("Native demographic counts disagree with own source total; no renormalization")
                    row.update(native_demographic_total=total, native_group_count_sum=sum(counts),
                               native_group_labels=len(labels))
                    parent = parents.get(state + "-" + mode)
                    if parent:
                        row.update(mode_parent_source_date=parent["date"], mode_parent_native_total=parent["total"],
                            demographic_minus_mode_total=total - parent["total"],
                            same_date_and_arithmetic_parent_match=data["date"] == parent["date"] and total == parent["total"])
                    fractions = [Fraction(value, total) * 100 for value in counts]
                    if sum(fractions) != 100:
                        raise ValueError("Full source-frame composition does not reconcile")
                    for source_group, fraction in zip(source_groups, fractions):
                        group = dict(row)
                        group.update(group_label_native=source_group["group"],
                            native_group_count=source_group["ballots"],
                            within_own_demographic_frame_pct=percentage(fraction))
                        groups.append(group)
                else:
                    group = dict(row)
                    group.update(group_label_native=None, native_group_count=None,
                                 within_own_demographic_frame_pct=None)
                    groups.append(group)
                scopes.append(row)
    selected = [row for row in scopes if row["disposition"] == "selected_own_demographic_frame_arithmetic"]
    positive_groups = [row for row in groups if row["native_group_count"] is not None]
    qualification = dict(provider="CivicAPI early-vote aggregate feed, not the supplied Civic survey",
        source_snapshot_id=SNAPSHOT, source_capture_date=captured_date.isoformat(),
        collector_election_context_date=capture["collector_election_context_date"],
        independent_native_election_id_qualified=False,
        all51_jurisdictions_two_modes_four_dimensions_assessed=True,
        within_own_source_frame_composition_not_group_turnout=True,
        native_labels_unknowns_zero_counts_and_full_source_denominators_retained=True,
        mode_parent_date_total_discrepancies_not_repaired_or_imputed_as_people=True,
        equal_date_and_total_not_proof_of_frame_or_population_equivalence=True,
        provider_counts_not_independent_official_administrative_validation=True,
        received_mail_not_qualified_accepted_or_cast=True, inperson_counts_not_certified_unique_people=True,
        no_mode_dimension_state_pooling_or_native_group_harmonization=True,
        no_survey_projection_causal_retention_switching_or_local_allocation=True,
        matched_group_registered_or_eligible_population_denominator=None,
        group_turnout_pct=None, full_election_turnout_pct=None, design_confidence_interval=None,
        existing_reduced_captures_reused_no_acquisition_or_collector_campaign_rerun=True,
        original_native25_control_package_and_all_survey_models_unchanged=True,
        official_state403_routes_stay_stopped_no_provider_substitution_for_official_benchmarks=True,
        party_labels_colors_county_regions_web_bodies_and_personal_records_excluded=True,
        new_website_view=False)
    return {
        "complete-provider-frame-query.csv": csv_bytes(scopes),
        "complete-provider-group-compositions.csv": csv_bytes(groups),
        "complete-mode-parent-accounting.csv": csv_bytes(parent_rows),
        "source-qualification.json": encoded(qualification),
        "summary.json": encoded(dict(schema="provider-demographic-frame-arithmetic-v1",
            complete_scope_decisions=len(scopes), complete_group_query_rows=len(groups),
            selected_native_demographic_views=len(selected), selected_native_group_counts=len(positive_groups),
            supported_source_states=len({row["state_code"] for row in selected}),
            mode_parent_query_rows=len(parent_rows), source_mode_parents=len(parents),
            reported_capability_states=sum(value is not None for value in capabilities.values()),
            not_reported_capability_states=sum(value is None for value in capabilities.values()),
            source_demographic_total_differs_from_mode_parent=sum(
                row["demographic_minus_mode_total"] not in (None, 0) for row in selected),
            same_date_and_arithmetic_parent_match_views=sum(row["same_date_and_arithmetic_parent_match"] for row in selected),
            disposition_counts=dict(Counter(row["disposition"] for row in scopes)),
            no_group_turnout_rate_survey_projection_or_new_website_view=True)),
    }


def build(inputs):
    body = (inputs / "complete-provider-capture-inputs.zip").read_bytes()
    if hashlib.sha256(body).hexdigest() != INPUT_SHA:
        raise ValueError("Changed complete qualified sufficient source capture")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        checksums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(checksums) | {"checksums.json"}:
            raise ValueError("Incomplete sufficient capture inventory")
        for name, metadata in checksums.items():
            value = archive.read(name)
            if len(value) != metadata["bytes"] or hashlib.sha256(value).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed preserved sufficient aggregate input")
        capture = json.loads(archive.read("qualified-capture.json"))
        components = json.loads(archive.read("native-mode-parent-components.json"))
    return analyze(capture, components)


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    name = "complete-provider-capture-inputs.zip"
    files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("provider_demographic_frames.py", "extract_provider_demographic_capture.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_provider_demographic_frames.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Provider source-native partial demographic counts and own-frame compositions, NOTgroup turnout.\n"
        "All51jurisdictions x2modes x4native dimensions and every supported/held decision included.\n"
        "Denominator is each native demographic response total, NOTmode total/registered/eligible population.\n"
        "KeepUnknown/Undesignated/zero groups/nativeage-race-gender labels; NOharmonization or nationalpool.\n"
        "Modeparent date/total differences are explicit, NOTrepaired or imputed as unknown people.\n"
        "Equal dates/totals doNOTprove equal frames, accepted/cast ballots, uniquepeople or complete coverage.\n"
        "CivicAPI count feed is NOTthe suppliedCivic survey; no survey/model/population projection or fakeCI.\n"
        "Already-held parsed captures reused; no acquisition or completed collector campaign rerun.\n"
        "Complete rawcapability/demographicresponses, sufficient unlabeledmodecomponents and source receipts\n"
        "are nested in inputs; countyregions/partylabels/colors/webbodies/personalrecords excluded.\n"
        "Existing controls25/survey models/website/source403holds unchanged. Research downloads only.\n"
        "python3 -m unittest discover -s tests -p test_provider_demographic_frames.py\n"
        "python3 -m scripts.provider_demographic_frames --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                                     for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
