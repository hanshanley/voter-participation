import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from scripts.historical_precinct_qualification import (
    CONTRACT,
    GIS_FIELDS,
    INPUT_CONTRACT,
    MEDSL_2016_FIELDS,
    MEDSL_2022_FIELDS,
    MEDSL_2024_FIELDS,
    OFFICIAL_FIELDS,
    OPENELECTIONS_FIELDS,
    TABULAR_FIELDS,
    alabama_observation,
    build,
    integration_descriptor,
    official_pair_key,
    pin_bytes,
    pin_file,
    read_decisions,
)
from scripts.participation_intake.contract import STATES


YEARS = (2016, 2018, 2020, 2022, 2024)


def csv_gzip(fields, rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(text.getvalue().encode(), mtime=0)


def packet(path, members):
    checksums = {name: pin_bytes(body) for name, body in members.items()}
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
        archive.writestr("checksums.json", json.dumps(checksums, sort_keys=True))
    return path.read_bytes()


def blank(fields, **values):
    row = {field: "" for field in fields}
    row.update(values)
    return row


def coverage_source(state, year, source_id, scope, rows=0, ballot=0, **extra):
    return {
        "state_code": state, "year": year, "source_id": source_id, "scope": scope,
        "provenance": "fixture", "compiled_query_available": True,
        "parsed_rows_or_cells": rows, "native_ballot_field_rows": ballot, **extra,
    }


def decisions():
    special = {
        ("AL", 2016): [coverage_source(
            "AL", 2016, "medsl_2016",
            "federal_office_partitions_native_modes_stages_specials_retained", 1)],
        ("AL", 2018): [
            coverage_source(
                "AL", 2018, "official_historical_state_products",
                "native_wide_cells_long_returns_and_separate_unmerged_supplemental_grids",
                8, 4),
            coverage_source(
                "AL", 2018, "openelections_statewide",
                "statewide_filename_geographic_completeness_unqualified", 1),
            coverage_source(
                "AL", 2018, "openelections_supplement",
                "county_partition_geography_unqualified", 1),
        ],
        ("NC", 2018): [coverage_source(
            "NC", 2018, "official_nc_historical_archive",
            "candidate_returns_precinct_and_administrative_units_not_precinct_sorted", 1)],
        ("MD", 2018): [
            coverage_source(
                "MD", 2018, "mggg_md2018-election-day",
                "publisher_merged_election_day_only_no_early_absentee_provisional", 1),
            coverage_source(
                "MD", 2018, "mggg_md2018-publisher-allocated",
                "publisher_allocated_early_absentee_provisional_plus_election_day", 1),
        ],
        ("VA", 2018): [coverage_source(
            "VA", 2018, "mggg_va2018-publisher-compiled",
            "publisher_compiled_party_totals_ballot_modes_and_allocation_unqualified", 1)],
        ("VA", 2020): [coverage_source(
            "VA", 2020, "mggg_va2020_native_csv",
            "native_candidate_units_with_separate_absentee_provisional_and_multiseat_races_no_downward_allocation",
            1)],
        ("AK", 2022): [coverage_source(
            "AK", 2022, "held_medsl_2022",
            "selected_house_native_rows_delegate_and_reconciliation_holds_separate", 1)],
        ("AK", 2024): [coverage_source(
            "AK", 2024, "held_medsl_2024",
            "selected_federal_rows_all_native_modes_stages_specials_retained", 1)],
    }
    rows = []
    for year in YEARS:
        for state in sorted(STATES):
            sources = special.get((state, year), [coverage_source(
                state, year, "existing_nyt_presidential_layer",
                "partial_presidential_candidate_layer_not_turnout_or_longitudinal_crosswalk",
                existing_geometry_source=True)])
            rows.append({
                "year": year, "state_code": state, "source_products_present": True,
                "compiled_query_available": True,
                "source_ids": ";".join(source["source_id"] for source in sources),
                "source_scopes": ";".join(sorted({source["scope"] for source in sources})),
                "parsed_native_rows_or_cells": sum(source["parsed_rows_or_cells"]
                                                   for source in sources),
                "native_ballot_field_rows": sum(source["native_ballot_field_rows"]
                                                for source in sources),
                "ballot_rows_are_not_participant_totals": True,
                "existing_presidential_geometry_source":
                    any(source.get("existing_geometry_source") for source in sources),
                "newly_approved_geometry_joins": False,
                "complete_precinct_coverage_qualified": False,
                "group_turnout_qualified": False,
                "individual_transitions_identified": False,
                "disposition": "source_present_scope_and_completeness_still_require_qualification",
                "sources_json": json.dumps(sources, sort_keys=True, separators=(",", ":")),
            })
    return rows


def official_row(number, unit, measure, count, status="reported"):
    label = {
        "ballots_cast": "BALLOTS CAST - TOTAL",
        "registration_stock": "REGISTERED VOTERS - TOTAL",
    }[measure]
    fields = {
        "contest": label, "party": "", "candidate": label.title(), "unit": unit,
        "cell_type": 2, "value": count if count != "" else "",
    }
    return blank(
        OFFICIAL_FIELDS, year="2018", state_code="AL", county_literal="Autauga",
        unit_literal=unit, unit_kind="native_precinct_label_unjoined",
        office_literal=label, candidate_literal=label.title(), measure=measure,
        count_literal=count, count_status=status, source_sha256="b" * 64,
        source_member="2018-General-Autauga.xls", source_table="Precinct Results",
        source_row=str(number), source_column="4",
        source_fields_json=json.dumps(fields),
        qualification="native_cells_not_summed;registration_zeros_not_qualified_denominators;no_geometry_or_rates",
    )


def official_sources():
    return {
        "b" * 64: {
            "year": 2018, "state_code": "AL",
            "url": "https://example.test/2018-Official-General-Precinct-Results.zip",
            "acquisition": {"acquired": True, "sha256": "b" * 64},
        }
    }


def fixture(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    decisions_path = tmp_path / "decisions.csv"
    values = decisions()
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(values[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(values)
    decisions_path.write_text(stream.getvalue())

    medsl = blank(
        MEDSL_2016_FIELDS, year="2016", stage="gen", special="FALSE",
        state_postal="AL", county_fips="01001", jurisdiction="Autauga",
        precinct="A", candidate="Example", office="US President", mode="total",
        votes="9", source_partition="president", source_row="2",
        vote_count_status="reported", general_non_special="true",
        analysis_qualification="literal_candidate_return_not_ballots",
    )
    oe = blank(
        OPENELECTIONS_FIELDS, year="2018", state_code="AL",
        source_commit="a" * 40, source_file="2018/20181106__al__general__precinct.csv",
        source_row="2", county="Autauga", precinct="A", office="President",
        candidate="Example", votes="9", vote_count_status="reported",
        measure="native_candidate_or_question_votes", row_width_status="exact",
        transport_encoding="utf-8-sig",
        native_fields_json=json.dumps({
            "columns": ["county", "precinct", "office", "candidate", "votes"],
            "values": ["Autauga", "A", "President", "Example", "9"],
        }), qualification="native_modes_not_added_to_totals",
    )
    official = [
        official_row(2, "A", "ballots_cast", "0"),
        official_row(3, "A", "registration_stock", "10"),
        official_row(4, "B", "ballots_cast", "5"),
        official_row(5, "B", "registration_stock", "0"),
        official_row(6, "C", "ballots_cast", "7"),
        official_row(7, "C", "registration_stock", "", "unknown"),
        official_row(8, "D", "ballots_cast", "11"),
        official_row(9, "D", "registration_stock", "10"),
    ]
    tabular = blank(
        TABULAR_FIELDS, year="2020", state_code="VA", source_url="https://example.test/va",
        source_member="VA/2020/VA-2020-precincts.csv", source_row="2",
        county="PITTSYLVANIA COUNTY", unit="# AB", office="US President",
        candidate="Example", votes="7", vote_count_status="reported",
        measure="native_candidate_or_question_votes",
        native_fields_json=json.dumps({"columns": ["votes"], "values": ["7"]}),
        qualification="native_modes_not_summed;literal_unit_flag_not_geometry",
    )
    nc = dict(tabular, year="2018", state_code="NC",
              source_member="results_pct_20181106.txt", county="ALAMANCE", unit="064")
    gis_rows = [
        blank(
            GIS_FIELDS, year="2018", state_code=state, source_id=source_id,
            source_row="1", source_scope=scope,
            election_fields_json=json.dumps({"SEN18D": 1}),
            native_attributes_json=json.dumps({"fields": [], "values": []}),
            native_raw_fields_json=json.dumps({"columns": [], "values": []}),
            qualification="publisher_compiled_source;geometry_not_approved",
        )
        for state, source_id, scope in (
            ("MD", "md2018-election-day",
             "publisher_merged_election_day_only_no_early_absentee_provisional"),
            ("MD", "md2018-publisher-allocated",
             "publisher_allocated_early_absentee_provisional_plus_election_day"),
            ("VA", "va2018-publisher-compiled",
             "publisher_compiled_party_totals_ballot_modes_and_allocation_unqualified"),
        )
    ]
    held22 = blank(
        MEDSL_2022_FIELDS, precinct="A", office="US HOUSE", mode="TOTAL", votes="4",
        county_name="Example", county_fips="02013", candidate="Example",
        dataverse="HOUSE", year="2022", stage="GEN", special="FALSE",
        state_po="AK", source_unit_kind="precinct", mode_included="true",
        qualification_status="selected",
    )
    held24 = blank(
        MEDSL_2024_FIELDS, precinct="A", office="US PRESIDENT", mode="TOTAL", votes="5",
        county_name="Example", county_fips="02013", candidate="Example",
        dataverse="PRESIDENT", year="2024", stage="GEN", special="FALSE",
        state_po="AK", source_unit_kind="precinct", scope_selected="true",
        mode_included="true", mode_disposition="selected",
    )

    packet_members = {
        "medsl": {
            "queries/complete-source-row-query.csv.gz":
                csv_gzip(MEDSL_2016_FIELDS, [medsl]),
        },
        "statewide": {
            "queries/complete-source-row-query.csv.gz":
                csv_gzip(OPENELECTIONS_FIELDS, [oe]),
        },
        "supplements": {
            "queries/complete-source-row-query.csv.gz":
                csv_gzip(OPENELECTIONS_FIELDS, [oe]),
        },
        "official": {
            "queries/complete-source-cell-query.csv.gz":
                csv_gzip(OFFICIAL_FIELDS, official),
            "originals/product-provenance.json":
                json.dumps(list(official_sources().values())).encode(),
        },
        "mggg": {
            "queries/derived-csv/complete-native-row-query.csv.gz":
                csv_gzip(TABULAR_FIELDS, [tabular]),
            "queries/derived-gis/md2018-election-day.csv.gz":
                csv_gzip(GIS_FIELDS, [gis_rows[0]]),
            "queries/derived-gis/md2018-publisher-allocated.csv.gz":
                csv_gzip(GIS_FIELDS, [gis_rows[1]]),
            "queries/derived-gis/va2018-publisher-compiled.csv.gz":
                csv_gzip(GIS_FIELDS, [gis_rows[2]]),
        },
        "nc": {
            "queries/complete-native-row-query.csv.gz":
                csv_gzip(TABULAR_FIELDS, [nc]),
        },
    }
    packet_descriptors = []
    definitions = [
        ("medsl", "medsl-2016", "medsl-2016", "originals/medsl.zip",
         ["queries/complete-source-row-query.csv.gz"]),
        ("statewide", "openelections-statewide", "openelections-statewide",
         "originals/statewide.zip", ["queries/complete-source-row-query.csv.gz"]),
        ("supplements", "openelections-supplements", "openelections-supplements",
         "originals/supplements.zip", ["queries/complete-source-row-query.csv.gz"]),
        ("official", "official-state", "official-state", "originals/official.zip",
         ["queries/complete-source-cell-query.csv.gz"]),
        ("mggg", "mggg-complements", "mggg-complements", "originals/mggg.zip",
         ["queries/derived-csv/complete-native-row-query.csv.gz"]),
        ("nc", "north-carolina-2018", "north-carolina-2018", "originals/nc.zip",
         ["queries/complete-native-row-query.csv.gz"]),
    ]
    component_bytes = {}
    for file_id, packet_id, kind, authority_member, query_members in definitions:
        path = tmp_path / f"renamed-{file_id}.bin"
        component_bytes[authority_member] = packet(path, packet_members[file_id])
        descriptor = {
            "id": packet_id, "kind": kind, "path": str(path),
            "authority_member": authority_member, "query_members": query_members,
            **pin_file(path),
        }
        if kind == "official-state":
            descriptor["provenance_member"] = "originals/product-provenance.json"
        if kind == "mggg-complements":
            descriptor["gis_query_members"] = [
                "queries/derived-gis/md2018-election-day.csv.gz",
                "queries/derived-gis/md2018-publisher-allocated.csv.gz",
                "queries/derived-gis/va2018-publisher-compiled.csv.gz",
            ]
        packet_descriptors.append(descriptor)

    held22_body = csv_gzip(MEDSL_2022_FIELDS, [held22])
    held24_body = csv_gzip(MEDSL_2024_FIELDS, [held24])
    authority_members = {
        **component_bytes,
        "queries/coverage/all-255-state-year-decisions.csv": decisions_path.read_bytes(),
        "queries/held-medsl-2022/selected-house-raw-rows.csv.gz": held22_body,
        "queries/held-medsl-2024/query-raw-federal-rows.csv.gz": held24_body,
    }
    authority_path = tmp_path / "authority.bin"
    authority_checksums = {name: pin_bytes(body) for name, body in authority_members.items()}
    with zipfile.ZipFile(authority_path, "w") as archive:
        for name, body in authority_members.items():
            archive.writestr(name, body)
        archive.writestr("checksums.json", json.dumps(authority_checksums, sort_keys=True))
    inputs = {
        "contract": INPUT_CONTRACT,
        "decisions": {
            "path": str(decisions_path),
            "authority_member": "queries/coverage/all-255-state-year-decisions.csv",
            **pin_file(decisions_path),
        },
        "authority": {"path": str(authority_path), **pin_file(authority_path)},
        "packets": packet_descriptors,
        "archive_queries": [
            {
                "id": "held-medsl-2022", "kind": "held-medsl-2022",
                "member": "queries/held-medsl-2022/selected-house-raw-rows.csv.gz",
                **pin_bytes(held22_body),
            },
            {
                "id": "held-medsl-2024", "kind": "held-medsl-2024",
                "member": "queries/held-medsl-2024/query-raw-federal-rows.csv.gz",
                **pin_bytes(held24_body),
            },
        ],
    }
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, sort_keys=True, indent=2) + "\n")
    return inputs_path


def test_full_fixture_streams_all_declared_rows_and_is_deterministic(tmp_path):
    inputs = fixture(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    first_summary = build(inputs, first)
    second_summary = build(inputs, second)
    assert first_summary == second_summary
    assert first_summary["state_year_decisions"] == 255
    assert first_summary["all_declared_numerical_source_rows_streamed"] is True
    assert first_summary["qualified_observations"] == 1
    assert first_summary["held_participation_pairs"] == 3
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()}
    assert integration_descriptor(first)["qualified_observations"] == 1
    products = list(csv.DictReader(
        (first / "state-year-product-qualifications.csv").open()))
    md = [row for row in products if row["state_code"] == "MD" and
          row["year"] == "2018" and row["product_kind"] == "declared_coverage_source"]
    assert len(md) == 2
    assert len({row["boundary_disposition"] for row in md}) == 2


@pytest.mark.parametrize("mutation", [
    "wrong_labels", "primary", "wrong_year", "missing_identity",
    "unsafe_integer", "hidden_native_value",
])
def test_official_pair_mutations_are_held(mutation):
    ballot = official_row(2, "A", "ballots_cast", "5")
    registration = official_row(3, "A", "registration_stock", "10")
    if mutation == "wrong_labels":
        ballot["office_literal"] = ballot["candidate_literal"] = "US Senate"
        fields = json.loads(ballot["source_fields_json"])
        fields["contest"] = fields["candidate"] = "US Senate"
        ballot["source_fields_json"] = json.dumps(fields)
    elif mutation == "primary":
        ballot["source_member"] = registration["source_member"] = "2018-Primary-Autauga.xls"
    elif mutation == "wrong_year":
        ballot["year"] = registration["year"] = "2099"
        ballot["source_member"] = registration["source_member"] = "2099-General-Autauga.xls"
    elif mutation == "missing_identity":
        ballot["county_literal"] = registration["county_literal"] = ""
        ballot["unit_literal"] = registration["unit_literal"] = ""
    elif mutation == "unsafe_integer":
        registration["count_literal"] = str(2**53 + 1)
        fields = json.loads(registration["source_fields_json"])
        fields["value"] = str(2**53 + 1)
        registration["source_fields_json"] = json.dumps(fields)
    else:
        fields = json.loads(ballot["source_fields_json"])
        fields["value"] = "6"
        ballot["source_fields_json"] = json.dumps(fields)
    key = official_pair_key(ballot)
    value, hold = alabama_observation(
        key, {"ballots_cast": [ballot], "registration_stock": [registration]},
        official_sources())
    assert value is None
    assert hold["hold_reason"] == "official_row_guard_failed"


def test_duplicate_measure_rows_are_held_with_distinct_selectors():
    ballot = official_row(2, "A", "ballots_cast", "5")
    duplicate = dict(ballot, source_row="20")
    registration = official_row(3, "A", "registration_stock", "10")
    value, hold = alabama_observation(
        official_pair_key(ballot),
        {"ballots_cast": [ballot, duplicate], "registration_stock": [registration]},
        official_sources())
    assert value is None
    assert hold["hold_reason"] == "ambiguous_duplicate_measure_rows"
    assert len(hold["duplicate_selectors"]["ballots_cast"]) == 2


def test_arbitrary_51_code_ledger_is_rejected(tmp_path):
    values = decisions()
    values[0]["state_code"] = "ZZ"
    sources = json.loads(values[0]["sources_json"])
    sources[0]["state_code"] = "ZZ"
    values[0]["sources_json"] = json.dumps(sources)
    path = tmp_path / "bad.csv"
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(values[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(values)
    path.write_text(stream.getvalue())
    with pytest.raises(ValueError, match="exact canonical"):
        read_decisions(path, pin_file(path))


def test_descriptor_rejects_tampered_claim_totals_and_duplicate_ids(tmp_path):
    inputs = fixture(tmp_path)
    output = tmp_path / "result"
    build(inputs, output)
    summary = json.loads((output / "summary.json").read_text())
    summary["qualified_observations"] += 1
    (output / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    manifest = json.loads((output / "manifest.json").read_text())
    manifest["files"]["summary.json"] = pin_file(output / "summary.json")
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="contents differ"):
        integration_descriptor(output)

    clean = tmp_path / "clean"
    build(inputs, clean)
    sidecar = clean / "qualified-participation-observations.jsonl.gz"
    rows = gzip.decompress(sidecar.read_bytes()).splitlines()
    sidecar.write_bytes(gzip.compress(b"\n".join(rows + rows) + b"\n", mtime=0))
    summary = json.loads((clean / "summary.json").read_text())
    summary["qualified_observations"] = 2
    (clean / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    manifest = json.loads((clean / "manifest.json").read_text())
    manifest["files"]["summary.json"] = pin_file(clean / "summary.json")
    manifest["files"][sidecar.name] = pin_file(sidecar)
    (clean / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="identifiers"):
        integration_descriptor(clean)

    native = tmp_path / "native"
    build(inputs, native)
    sidecar = native / "qualified-participation-observations.jsonl.gz"
    row = json.loads(gzip.decompress(sidecar.read_bytes()))
    row["numerator"]["native_fields"]["value"] = "999"
    sidecar.write_bytes(gzip.compress(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        mtime=0))
    manifest = json.loads((native / "manifest.json").read_text())
    manifest["files"][sidecar.name] = pin_file(sidecar)
    (native / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="native value differs"):
        integration_descriptor(native)


def test_packet_identity_is_pin_and_authority_not_basename(tmp_path):
    inputs = fixture(tmp_path)
    build(inputs, tmp_path / "renamed-ok")
    spec = json.loads(inputs.read_text())
    packet_path = Path(spec["packets"][0]["path"])
    packet_path.write_bytes(packet_path.read_bytes() + b"x")
    with pytest.raises(ValueError, match="reviewed pin"):
        build(inputs, tmp_path / "tampered")
