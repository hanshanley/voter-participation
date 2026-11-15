"""Qualify every retained historical query product without inventing turnout."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

from scripts.historical_native_counts import DATES, native_count, project
from scripts.participation_intake.contract import STATES


CONTRACT = "participation.historical_precinct_qualification.v2"
INPUT_CONTRACT = "participation.historical_precinct_qualification_inputs.v1"
YEARS = (2016, 2018, 2020, 2022, 2024)
SAFE_MAX = 2**53 - 1
PACKET_KINDS = {
    "medsl-2016", "openelections-statewide", "openelections-supplements",
    "official-state", "mggg-complements", "north-carolina-2018",
}
ARCHIVE_QUERY_KINDS = {"held-medsl-2022", "held-medsl-2024"}
OFFICIAL_TOTAL_LABELS = {
    "ballots_cast": "ballots cast - total",
    "registration_stock": "registered voters - total",
}
OFFICIAL_REQUIRED_QUALIFICATIONS = {
    "native_cells_not_summed",
    "registration_zeros_not_qualified_denominators",
    "no_geometry_or_rates",
}
PRODUCT_FIELDS = [
    "state_code", "year", "product_id", "product_kind", "source_id", "source_scope",
    "packet_id", "query_member", "native_rows", "reported_rows", "unknown_rows",
    "suppressed_rows", "negative_correction_rows", "candidate_rows", "ballot_rows",
    "registration_rows", "county_identity", "county_literals", "office_literals",
    "election_stage", "election_mode", "native_reporting_unit_identity",
    "explicit_ballot_field_availability", "denominator_frame_compatibility",
    "compatible_candidate_office_comparison", "qualified_participation_counts",
    "qualified_participation_rates", "geometry_qualified", "boundary_disposition",
    "query_materialization_status", "row_logical_sha256", "disposition",
]


MEDSL_2016_FIELDS = [
    "year", "stage", "special", "state", "state_postal", "state_fips", "state_icpsr",
    "county_name", "county_fips", "county_ansi", "county_lat", "county_long",
    "jurisdiction", "precinct", "candidate", "candidate_normalized", "office",
    "district", "writein", "party", "mode", "votes", "candidate_opensecrets",
    "candidate_wikidata", "candidate_party", "candidate_last", "candidate_first",
    "candidate_middle", "candidate_full", "candidate_suffix", "candidate_nickname",
    "candidate_fec", "candidate_fec_name", "candidate_google", "candidate_govtrack",
    "candidate_icpsr", "candidate_maplight", "source_partition", "source_row",
    "vote_count_status", "general_non_special", "analysis_qualification",
]
OPENELECTIONS_FIELDS = [
    "year", "state_code", "source_commit", "source_file", "source_row", "county",
    "precinct", "office", "district", "candidate", "party", "votes",
    "vote_count_status", "measure", "row_width_status", "transport_encoding",
    "native_fields_json", "qualification",
]
TABULAR_FIELDS = [
    "year", "state_code", "source_url", "source_member", "source_row", "county",
    "unit", "office", "candidate", "party", "votes", "vote_count_status", "measure",
    "native_fields_json", "qualification",
]
GIS_FIELDS = [
    "year", "state_code", "source_id", "source_row", "source_scope",
    "election_fields_json", "native_attributes_json", "native_raw_fields_json",
    "qualification",
]
OFFICIAL_FIELDS = [
    "year", "state_code", "county_literal", "unit_literal", "unit_kind",
    "office_literal", "candidate_literal", "party_literal", "measure", "count_literal",
    "count_status", "source_sha256", "source_member", "source_table", "source_row",
    "source_column", "source_fields_json", "qualification",
]
MEDSL_2022_FIELDS = [
    "precinct", "office", "party_detailed", "party_simplified", "mode", "votes",
    "county_name", "county_fips", "jurisdiction_name", "jurisdiction_fips",
    "candidate", "district", "dataverse", "year", "stage", "state", "special",
    "writein", "state_po", "state_fips", "state_cen", "state_ic", "date",
    "readme_check", "magnitude", "source_archive", "source_member",
    "source_row_number", "source_unit_kind", "mode_included", "qualification_status",
    "qualification_reasons",
]
MEDSL_2024_FIELDS = [
    "precinct", "office", "party_detailed", "party_simplified", "mode", "votes",
    "county_name", "county_fips", "jurisdiction_name", "jurisdiction_fips",
    "candidate", "district", "dataverse", "year", "stage", "state", "special",
    "writein", "state_po", "state_fips", "state_cen", "state_ic", "date",
    "magnitude", "source_archive", "source_member", "source_row_number",
    "source_unit_kind", "scope_selected", "scope_exclusion_reasons", "mode_included",
    "mode_disposition", "row_qualification_reasons",
]


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def pin_bytes(body):
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def pin_file(path):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for body in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(body)
            size += len(body)
    return {"bytes": size, "sha256": digest.hexdigest()}


def require_pin(actual, expected, label):
    wanted = {key: expected[key] for key in ("bytes", "sha256")}
    if actual != wanted:
        raise ValueError(label + " differs from its reviewed pin")


def normalized(value):
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def truth(value):
    return normalized(value) in {"true", "yes", "1", "included", "selected"}


def safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe archive member path")
    return str(path)


def logical_row(digest, row):
    digest.update(json.dumps(row, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":")).encode())
    digest.update(b"\n")


class DigestReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size=-1):
        body = self.stream.read(size)
        self.digest.update(body)
        self.size += len(body)
        return body

    def readable(self):
        return True

    def close(self):
        self.stream.close()

    def verify(self, expected, label):
        require_pin({"bytes": self.size, "sha256": self.digest.hexdigest()}, expected, label)


def verified_csv_rows(archive, member, expected_pin, expected_fields):
    member = safe_relative(member)
    with archive.open(member) as source:
        checked = DigestReader(source)
        with gzip.GzipFile(fileobj=checked) as compressed, \
                io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
            reader = csv.DictReader(text)
            if reader.fieldnames != expected_fields:
                raise ValueError("Reviewed query schema changed: " + member)
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Historical query row width changed: " + member)
                yield row
        checked.verify(expected_pin, member)


def verified_member(archive, member, expected_pin):
    body = archive.read(safe_relative(member))
    require_pin(pin_bytes(body), expected_pin, member)
    return body


def archive_checksums(archive):
    checksums = json.loads(archive.read("checksums.json"))
    if not isinstance(checksums, dict):
        raise ValueError("Packet checksums are not a member map")
    return checksums


def boundary_disposition(scope, state, year):
    if scope == "native_town_not_assumed_precinct":
        return "native_town_identity_only_not_a_universal_precinct"
    if scope == "native_ward_not_assumed_precinct":
        return "native_ward_identity_only_not_a_universal_precinct"
    if scope == "county_partition_geography_unqualified" and state == "NJ" and year == 2020:
        return "partial_13_county_partition_distinct_no_statewide_completeness"
    if scope == "publisher_merged_election_day_only_no_early_absentee_provisional":
        return "md_election_day_only_variant_distinct_no_cross_variant_merge"
    if scope == "publisher_allocated_early_absentee_provisional_plus_election_day":
        return "md_publisher_allocated_variant_distinct_not_observed_election_day"
    if "supplemental_grids" in scope:
        return "kansas_long_table_and_supplemental_grids_separate_no_false_merge"
    if state == "VA" and year == 2020:
        return "virginia_native_candidate_and_administrative_units_explicit_no_downward_allocation"
    if "publisher_compiled_party_totals" in scope:
        return "virginia_publisher_compiled_party_totals_modes_and_allocation_unqualified"
    if "partial_presidential_candidate_layer" in scope:
        return "existing_presidential_geometry_is_candidate_context_not_turnout_or_longitudinal_identity"
    return "native_source_identity_only_no_geometry_or_cross_year_boundary_join"


def read_decisions(path, expected_pin):
    body = Path(path).read_bytes()
    require_pin(pin_bytes(body), expected_pin, "Historical 255-decision ledger")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))
    keys = [(row["state_code"], int(row["year"])) for row in rows]
    expected = [(state, year) for year in YEARS for state in sorted(STATES)]
    if keys != expected:
        raise ValueError("Historical scope must be the exact canonical 51 states x five years")
    if len(rows) != 255 or any(not row["sources_json"] for row in rows):
        raise ValueError("Every canonical state/year decision must retain source evidence")
    for row in rows:
        sources = json.loads(row["sources_json"])
        if not isinstance(sources, list) or not sources:
            raise ValueError("Every state/year requires at least one selected source")
        for source in sources:
            if source["state_code"] != row["state_code"] or int(source["year"]) != int(row["year"]):
                raise ValueError("Coverage source identity differs from its state/year decision")
    return body, rows


def load_inputs(specification):
    specification = Path(specification)
    spec = json.loads(specification.read_bytes())
    if spec.get("contract") != INPUT_CONTRACT:
        raise ValueError("Unreviewed historical qualification input contract")
    decisions = dict(spec["decisions"])
    authority = dict(spec["authority"])
    packets = list(spec["packets"])
    archive_queries = list(spec["archive_queries"])
    if len({row["id"] for row in packets + archive_queries}) != len(packets) + len(archive_queries):
        raise ValueError("Historical input identifiers must be unique")
    if {row["kind"] for row in packets} != PACKET_KINDS:
        raise ValueError("All six reviewed component packet kinds are required")
    if {row["kind"] for row in archive_queries} != ARCHIVE_QUERY_KINDS:
        raise ValueError("Both held MEDSL query families are required")
    for row in packets:
        row["path"] = Path(row["path"])
        require_pin(pin_file(row["path"]), row, "Component packet " + row["id"])
    authority["path"] = Path(authority["path"])
    require_pin(pin_file(authority["path"]), authority, "Complete historical authority archive")
    decisions["path"] = Path(decisions["path"])
    return spec, decisions, authority, packets, archive_queries


def validate_authority(decisions, authority, packets, archive_queries):
    with zipfile.ZipFile(authority["path"]) as archive:
        checksums = archive_checksums(archive)
        decision_member = safe_relative(decisions["authority_member"])
        if checksums.get(decision_member) != {key: decisions[key] for key in ("bytes", "sha256")}:
            raise ValueError("Authority decision member pin differs")
        authority_decisions = verified_member(archive, decision_member, checksums[decision_member])
        if authority_decisions != decisions["path"].read_bytes():
            raise ValueError("Canonical and authority decision ledgers differ")
        for packet in packets:
            member = safe_relative(packet["authority_member"])
            expected = checksums.get(member)
            if expected is None:
                raise ValueError("Component packet is absent from authority checksums")
            require_pin({key: packet[key] for key in ("bytes", "sha256")}, expected,
                        "Component packet authority")
        for query in archive_queries:
            member = safe_relative(query["member"])
            expected = checksums.get(member)
            if expected is None:
                raise ValueError("Held query is absent from authority checksums")
            require_pin({key: query[key] for key in ("bytes", "sha256")}, expected,
                        "Held query authority")
        return checksums


def new_product(state, year, product_id, kind, source_id, scope, packet_id, member):
    return {
        "state_code": state, "year": int(year), "product_id": product_id,
        "product_kind": kind, "source_id": source_id, "source_scope": scope,
        "packet_id": packet_id, "query_member": member, "native_rows": 0,
        "statuses": Counter(), "measures": Counter(), "county_literals": set(),
        "county_missing": 0, "offices": set(), "stages": set(), "modes": set(),
        "candidate_comparable_rows": 0, "logical": hashlib.sha256(),
    }


def finish_product(product, qualified=0):
    measures = product["measures"]
    ballot_rows = measures["ballots_cast"] + measures["native_ballots_cast"]
    registration_rows = measures["registration_stock"] + measures["native_registration_stock"]
    candidate_rows = sum(value for key, value in measures.items()
                         if key not in {"ballots_cast", "native_ballots_cast",
                                       "registration_stock", "native_registration_stock"})
    if product["county_missing"]:
        county_identity = "missing_or_ambiguous_held_no_crosswalk"
    elif product["product_kind"].startswith("medsl"):
        county_identity = "native_county_or_jurisdiction_identifier_no_boundary_join"
    else:
        county_identity = "native_literal_only_no_fips_crosswalk"
    if qualified:
        denominator = "registered_voters_total_same_general_election_product_and_native_unit"
        disposition = "qualified_native_participation_observations_and_explicit_holds"
    elif ballot_rows or registration_rows:
        denominator = "held_source_stock_or_mode_pairing_not_reviewed_for_rates"
        disposition = "explicit_administrative_cells_rate_held"
    else:
        denominator = "none"
        disposition = "candidate_office_comparison_only_not_participation"
    return {
        "state_code": product["state_code"], "year": product["year"],
        "product_id": product["product_id"], "product_kind": product["product_kind"],
        "source_id": product["source_id"], "source_scope": product["source_scope"],
        "packet_id": product["packet_id"], "query_member": product["query_member"],
        "native_rows": product["native_rows"],
        "reported_rows": product["statuses"]["reported"],
        "unknown_rows": product["statuses"]["unknown"],
        "suppressed_rows": product["statuses"]["suppressed"],
        "negative_correction_rows": product["statuses"]["negative_correction"],
        "candidate_rows": candidate_rows, "ballot_rows": ballot_rows,
        "registration_rows": registration_rows, "county_identity": county_identity,
        "county_literals": len(product["county_literals"]),
        "office_literals": len(product["offices"]),
        "election_stage": ";".join(sorted(product["stages"])) or "source_stage_preserved",
        "election_mode": ";".join(sorted(product["modes"])) or "native_modes_preserved_not_summed",
        "native_reporting_unit_identity": "source_specific_native_unit_no_crosswalk",
        "explicit_ballot_field_availability":
            "source_labeled_ballot_cells" if ballot_rows else "none_candidate_votes_not_ballots",
        "denominator_frame_compatibility": denominator,
        "compatible_candidate_office_comparison":
            "within_exact_product_stage_office_mode_and_native_unit_only"
            if product["candidate_comparable_rows"] else "none",
        "qualified_participation_counts": qualified,
        "qualified_participation_rates": qualified,
        "geometry_qualified": False,
        "boundary_disposition":
            "same_native_workbook_member_table_county_and_unit_identity_no_geometry_join"
            if qualified else boundary_disposition(
                product["source_scope"], product["state_code"], product["year"]),
        "query_materialization_status": "readable_query_streamed_and_checksum_verified",
        "row_logical_sha256": product["logical"].hexdigest(),
        "disposition": disposition,
    }


def add_common(product, row, status, measure, county, office, stage, mode,
               candidate_comparable):
    product["native_rows"] += 1
    product["statuses"][status] += 1
    product["measures"][measure] += 1
    county = str(county).strip()
    if county:
        product["county_literals"].add(county)
    else:
        product["county_missing"] += 1
    office = str(office).strip()
    if office:
        product["offices"].add(office)
    if stage:
        product["stages"].add(str(stage))
    if mode:
        product["modes"].add(str(mode))
    product["candidate_comparable_rows"] += bool(candidate_comparable)
    logical_row(product["logical"], row)


def stream_medsl_2016(packet):
    member = packet["query_members"][0]
    products = {}
    observed = Counter()
    with zipfile.ZipFile(packet["path"]) as archive:
        checksums = archive_checksums(archive)
        for row in verified_csv_rows(archive, member, checksums[member], MEDSL_2016_FIELDS):
            state, year, partition = row["state_postal"], int(row["year"]), row["source_partition"]
            if year != 2016 or state not in STATES:
                raise ValueError("MEDSL 2016 query election identity changed")
            key = (state, partition)
            product = products.setdefault(key, new_product(
                state, year, f"medsl2016:{state}:{partition}", "medsl_2016_partition",
                "medsl_2016", "federal_office_partition", packet["id"], member))
            add_common(product, row, row["vote_count_status"], "candidate_return",
                       row["county_fips"], row["office"], row["stage"], row["mode"],
                       truth(row["general_non_special"]) and row["vote_count_status"] == "reported")
            observed[(state, year, "medsl_2016")] += 1
    return list(products.values()), observed


def stream_openelections(packet):
    member = packet["query_members"][0]
    source_id = ("openelections_statewide" if packet["kind"] == "openelections-statewide"
                 else "openelections_supplement")
    products = {}
    observed = Counter()
    with zipfile.ZipFile(packet["path"]) as archive:
        checksums = archive_checksums(archive)
        for row in verified_csv_rows(archive, member, checksums[member], OPENELECTIONS_FIELDS):
            state, year, source_file = row["state_code"], int(row["year"]), row["source_file"]
            if year not in {2018, 2020} or state not in STATES or \
                    "__general" not in Path(source_file).name.casefold():
                raise ValueError("OpenElections reviewed general-election identity changed")
            key = (state, year, source_file)
            product = products.setdefault(key, new_product(
                state, year, f"{packet['id']}:{state}:{year}:{source_file}",
                "openelections_query_file", source_id, "native_file_rows",
                packet["id"], member))
            add_common(product, row, row["vote_count_status"], row["measure"],
                       row["county"], row["office"], "general_inferred_from_reviewed_filename",
                       "native_fields_preserved_not_summed",
                       row["measure"] == "native_candidate_or_question_votes" and
                       row["vote_count_status"] == "reported" and bool(row["office"].strip()))
            observed[(state, year, source_id)] += 1
    return list(products.values()), observed


def official_pair_key(row):
    return (
        row["state_code"], row["year"], row["source_sha256"], row["source_member"],
        row["source_table"], row["county_literal"], row["unit_literal"],
    )


def selector(row):
    return {key: row[key] for key in
            ("source_sha256", "source_member", "source_table", "source_row", "source_column")}


def hold_base(key):
    return {
        "contract": CONTRACT, "state_code": key[0], "year": int(key[1]),
        "product_id": f"official:{key[0]}:{key[1]}:{key[2]}",
        "county_literal": key[5], "native_reporting_unit": key[6],
        "geometry_qualified": False,
        "boundary_disposition":
            "native_source_identity_only_no_geometry_or_cross_year_boundary_join",
        "disposition": "held",
    }


def official_row_guard(row, sources):
    if row["state_code"] != "AL":
        raise ValueError("Only Alabama official administrative pairs are rate candidates")
    if row["measure"] not in OFFICIAL_TOTAL_LABELS:
        raise ValueError("Official row is not a reviewed total measure")
    projected = project(row, "official-state", sources)
    if projected is None:
        raise ValueError("Official administrative row was not projected")
    expected = OFFICIAL_TOTAL_LABELS[row["measure"]]
    fields = json.loads(row["source_fields_json"])
    required = {"contest", "candidate", "unit", "value"}
    if not required.issubset(fields):
        raise ValueError("Official native fields omit reviewed identity/value fields")
    if any(normalized(value) != expected for value in (
            row["office_literal"], row["candidate_literal"],
            fields["contest"], fields["candidate"])):
        raise ValueError("Official total labels differ from native total labels")
    if str(fields["unit"]) != row["unit_literal"]:
        raise ValueError("Official native unit differs from compiled unit")
    if not row["county_literal"].strip() or not row["unit_literal"].strip() or \
            not row["source_table"].strip():
        raise ValueError("Official native county/unit/table identity is empty")
    if row["unit_kind"] not in {
            "native_precinct_label_unjoined", "pooled_administrative_unit", "parent_total"}:
        raise ValueError("Official native unit kind is unreviewed")
    flags = set(row["qualification"].split(";"))
    if not OFFICIAL_REQUIRED_QUALIFICATIONS.issubset(flags):
        raise ValueError("Official source qualification flags changed")
    return projected


def alabama_observation(key, pair, sources):
    base = hold_base(key)
    if set(pair) - {"ballots_cast", "registration_stock"}:
        return None, dict(base, hold_reason="unreviewed_pair_measure")
    if any(len(rows) != 1 for rows in pair.values()):
        return None, dict(base, hold_reason="ambiguous_duplicate_measure_rows",
                          duplicate_selectors={
                              measure: [selector(row) for row in rows]
                              for measure, rows in sorted(pair.items()) if len(rows) != 1})
    if set(pair) != {"ballots_cast", "registration_stock"}:
        return None, dict(base, hold_reason="missing_explicit_pair_component")
    ballot, registration = pair["ballots_cast"][0], pair["registration_stock"][0]
    if selector(ballot) == selector(registration):
        return None, dict(base, hold_reason="pair_components_share_source_selector")
    try:
        projected_ballot = official_row_guard(ballot, sources)
        projected_registration = official_row_guard(registration, sources)
    except (ValueError, KeyError, TypeError) as error:
        return None, dict(base, hold_reason="official_row_guard_failed", detail=str(error),
                          numerator_selector=selector(ballot),
                          denominator_selector=selector(registration))
    if any(projected_ballot[key_name] != projected_registration[key_name]
           for key_name in ("year", "state_code", "county_literal", "unit_literal", "unit_kind",
                            "snapshot_id")):
        return None, dict(base, hold_reason="pair_identity_or_product_mismatch")
    numerator = projected_ballot["count"]["value"]
    denominator = projected_registration["count"]["value"]
    observation = {
        **base, "id": hashlib.sha256(encoded(list(key))).hexdigest()[:32],
        "election_stage": "general", "election_mode": "all_methods_total_source_label",
        "geography_type": "native_reporting_unit",
        "native_unit_identity_qualified": True,
        "boundary_disposition":
            "same_native_workbook_member_table_county_and_unit_identity_no_geometry_join",
        "population_frame": "registered_voters_total_same_native_unit",
        "participation_measure": "ballots_cast_total_source_labeled",
        "repeated_cross_section_not_person_panel": True,
        "individual_staying_home_first_vote_or_switching_identified": False,
        "numerator": {
            "value": numerator, "literal": ballot["count_literal"],
            "status": projected_ballot["count"]["status"],
            "measure_literal": projected_ballot["measure_literal"],
            "native_category": projected_ballot["native_category"],
            "source_selector": selector(ballot),
            "native_fields": projected_ballot["source"]["native_fields"],
            "original_qualification": projected_ballot["source"]["original_qualification"],
            "unit_kind": projected_ballot["unit_kind"],
        },
        "denominator": {
            "value": denominator, "literal": registration["count_literal"],
            "status": projected_registration["count"]["status"],
            "population": "registered_voters",
            "measure_literal": projected_registration["measure_literal"],
            "native_category": projected_registration["native_category"],
            "source_selector": selector(registration),
            "native_fields": projected_registration["source"]["native_fields"],
            "original_qualification": projected_registration["source"]["original_qualification"],
            "unit_kind": projected_registration["unit_kind"],
        },
    }
    if numerator is None or denominator is None:
        return None, dict(observation, disposition="held",
                          hold_reason="unknown_or_withheld_numerator_or_denominator")
    if not isinstance(numerator, int) or not isinstance(denominator, int) or \
            isinstance(numerator, bool) or isinstance(denominator, bool) or \
            not (0 <= numerator <= SAFE_MAX and 0 <= denominator <= SAFE_MAX):
        return None, dict(observation, disposition="held", hold_reason="unsafe_exact_count")
    if denominator == 0:
        return None, dict(observation, disposition="held", hold_reason="zero_denominator")
    if numerator > denominator:
        return None, dict(observation, disposition="held",
                          hold_reason="numerator_exceeds_same_unit_registered_denominator")
    rate = Decimal(numerator) / Decimal(denominator)
    return dict(observation, disposition="qualified", count=numerator,
                rate_numerator=numerator, rate_denominator=denominator,
                rate_decimal=format(rate.quantize(Decimal("0.000000000001")), "f")), None


def stream_official(packet):
    member = packet["query_members"][0]
    products = {}
    observed = Counter()
    pairs = defaultdict(lambda: defaultdict(list))
    with zipfile.ZipFile(packet["path"]) as archive:
        checksums = archive_checksums(archive)
        provenance_member = packet["provenance_member"]
        provenance = json.loads(verified_member(
            archive, provenance_member, checksums[provenance_member]))
        sources = {row["acquisition"]["sha256"]: row for row in provenance
                   if row["acquisition"]["acquired"]}
        for row in verified_csv_rows(archive, member, checksums[member], OFFICIAL_FIELDS):
            state, year, source_sha = row["state_code"], int(row["year"]), row["source_sha256"]
            if state not in STATES or year not in {2018, 2020} or source_sha not in sources:
                raise ValueError("Official query source/election identity changed")
            key = (state, year, source_sha)
            product = products.setdefault(key, new_product(
                state, year, f"official:{state}:{year}:{source_sha}",
                "official_state_product", "official_historical_state_products",
                "native_state_product", packet["id"], member))
            add_common(product, row, row["count_status"], row["measure"],
                       row["county_literal"], row["office_literal"], "general",
                       "native_cells_preserved_not_summed",
                       row["measure"] in {"candidate_or_question_votes",
                                          "native_contest_or_administrative_value"} and
                       row["count_status"] == "reported")
            observed[(state, year, "official_historical_state_products")] += 1
            if state == "AL" and row["measure"] in OFFICIAL_TOTAL_LABELS:
                pairs[official_pair_key(row)][row["measure"]].append(row)
    qualified, held = [], []
    qualified_by_product = Counter()
    for key in sorted(pairs):
        result, hold = alabama_observation(key, pairs[key], sources)
        if result is not None:
            qualified.append(result)
            qualified_by_product[(key[0], int(key[1]), key[2])] += 1
        else:
            held.append(hold)
    finished = [finish_product(product, qualified_by_product[key])
                for key, product in products.items()]
    return finished, observed, qualified, held


def stream_tabular(packet, source_id):
    member = packet["query_members"][0]
    products = {}
    observed = Counter()
    with zipfile.ZipFile(packet["path"]) as archive:
        checksums = archive_checksums(archive)
        for row in verified_csv_rows(archive, member, checksums[member], TABULAR_FIELDS):
            state, year = row["state_code"], int(row["year"])
            if state not in STATES or year not in {2018, 2020}:
                raise ValueError("Tabular historical query election identity changed")
            source_member = row["source_member"]
            key = (state, year, source_member)
            product = products.setdefault(key, new_product(
                state, year, f"{packet['id']}:{state}:{year}:{source_member}",
                "native_tabular_query", source_id, "native_tabular_candidate_units",
                packet["id"], member))
            add_common(product, row, row["vote_count_status"], row["measure"],
                       row["county"], row["office"], "general_from_reviewed_recipe",
                       "native_modes_preserved_not_summed",
                       row["measure"] == "native_candidate_or_question_votes" and
                       row["vote_count_status"] == "reported")
            observed[(state, year, source_id)] += 1
    return list(products.values()), observed


def stream_gis(packet):
    products = []
    observed = Counter()
    source_map = {
        "md2018-election-day": "mggg_md2018-election-day",
        "md2018-publisher-allocated": "mggg_md2018-publisher-allocated",
        "va2018-publisher-compiled": "mggg_va2018-publisher-compiled",
    }
    with zipfile.ZipFile(packet["path"]) as archive:
        checksums = archive_checksums(archive)
        for member in packet["gis_query_members"]:
            product = None
            for row in verified_csv_rows(archive, member, checksums[member], GIS_FIELDS):
                state, year, native_source = row["state_code"], int(row["year"]), row["source_id"]
                source_id = source_map.get(native_source)
                if source_id is None or year != 2018 or state not in {"MD", "VA"}:
                    raise ValueError("MGGG GIS source identity changed")
                if product is None:
                    product = new_product(
                        state, year, f"mggg:{native_source}", "mggg_gis_attribute_product",
                        source_id, row["source_scope"], packet["id"], member)
                fields = json.loads(row["election_fields_json"])
                add_common(product, row, "reported", "publisher_compiled_candidate_fields",
                           "", ";".join(sorted(fields)), "general",
                           "publisher_compiled_or_allocated_modes_preserved",
                           bool(fields))
                observed[(state, year, source_id)] += 1
            if product is None:
                raise ValueError("Reviewed MGGG GIS query is empty")
            products.append(product)
    return products, observed


def stream_held_query(authority, authority_checksums, query):
    products = {}
    observed = Counter()
    member = query["member"]
    expected_fields = MEDSL_2022_FIELDS if query["kind"] == "held-medsl-2022" \
        else MEDSL_2024_FIELDS
    year = 2022 if query["kind"] == "held-medsl-2022" else 2024
    source_id = "held_medsl_2022" if year == 2022 else "held_medsl_2024"
    with zipfile.ZipFile(authority["path"]) as archive:
        for row in verified_csv_rows(archive, member, authority_checksums[member], expected_fields):
            state = row["state_po"]
            if state not in STATES or int(row["year"]) != year:
                raise ValueError("Held MEDSL query election identity changed")
            product = products.setdefault(state, new_product(
                state, year, f"{source_id}:{state}", f"medsl_{year}_state_product",
                source_id, "selected_native_federal_rows", query["id"], member))
            status = ("reported" if re.fullmatch(r"\d+", row["votes"]) else
                      "negative_correction" if re.fullmatch(r"-\d+", row["votes"])
                      else "unknown")
            comparable = row["stage"].casefold() == "gen" and \
                row["special"].casefold() == "false" and status == "reported" and \
                truth(row["mode_included"])
            add_common(product, row, status, "candidate_return", row["county_fips"],
                       row["office"], row["stage"], row["mode"], comparable)
            observed[(state, year, source_id)] += 1
    return list(products.values()), observed


def coverage_products(decisions, observed):
    products = []
    geometry = 0
    declared_numerical_rows = 0
    for decision in decisions:
        state, year = decision["state_code"], int(decision["year"])
        for index, source in enumerate(json.loads(decision["sources_json"])):
            source_id = source["source_id"]
            expected = int(source.get("parsed_rows_or_cells", 0))
            actual = observed[(state, year, source_id)]
            if source_id == "existing_nyt_presidential_layer":
                if expected != 0 or actual != 0 or not source.get("existing_geometry_source"):
                    raise ValueError("Geometry-only historical source changed meaning")
                status = "geometry_presence_only_no_numerical_query_rows"
                disposition = "candidate_geometry_context_only_not_participation"
                geometry += 1
            else:
                if actual != expected:
                    raise ValueError(
                        f"Compiled query row count differs for {state} {year} {source_id}: "
                        f"{actual} != {expected}")
                status = "readable_query_streamed_exact_declared_rows"
                disposition = "consumed_by_query_product_qualification"
                declared_numerical_rows += expected
            products.append({
                "state_code": state, "year": year,
                "product_id": f"coverage:{state}:{year}:{source_id}:{index + 1}",
                "product_kind": "declared_coverage_source", "source_id": source_id,
                "source_scope": source["scope"], "packet_id": "", "query_member": "",
                "native_rows": expected, "reported_rows": "", "unknown_rows": "",
                "suppressed_rows": "", "negative_correction_rows": "",
                "candidate_rows": "", "ballot_rows": int(source.get("native_ballot_field_rows", 0)),
                "registration_rows": "", "county_identity": "declared_scope_no_crosswalk",
                "county_literals": "", "office_literals": "",
                "election_stage": "source_declared_preserved",
                "election_mode": "native_modes_preserved_not_summed",
                "native_reporting_unit_identity": source["scope"],
                "explicit_ballot_field_availability":
                    "present_not_automatically_participant_total"
                    if source.get("native_ballot_field_rows", 0) else "none_declared",
                "denominator_frame_compatibility": "not_established_by_source_presence",
                "compatible_candidate_office_comparison":
                    "source_specific_only" if expected else "none",
                "qualified_participation_counts": 0, "qualified_participation_rates": 0,
                "geometry_qualified": False,
                "boundary_disposition": boundary_disposition(source["scope"], state, year),
                "query_materialization_status": status, "row_logical_sha256": "",
                "disposition": disposition,
            })
    return products, declared_numerical_rows, geometry


def compressed_json_lines(rows):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0,
                       compresslevel=6) as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":")).encode() + b"\n")
    return output.getvalue()


def write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_observation(row):
    required = {
        "id", "contract", "state_code", "year", "numerator", "denominator",
        "rate_numerator", "rate_denominator", "rate_decimal",
    }
    if not required.issubset(row) or row["contract"] != CONTRACT or row["state_code"] != "AL":
        raise ValueError("Qualified observation contract or identity changed")
    numerator, denominator = row["rate_numerator"], row["rate_denominator"]
    if any(isinstance(value, bool) or not isinstance(value, int) or
           not 0 <= value <= SAFE_MAX for value in (numerator, denominator)):
        raise ValueError("Qualified observation contains an unsafe count")
    if denominator == 0 or numerator > denominator or \
            row["numerator"]["value"] != numerator or row["denominator"]["value"] != denominator:
        raise ValueError("Qualified observation fraction is inconsistent")
    if not row["county_literal"].strip() or not row["native_reporting_unit"].strip() or \
            int(row["year"]) not in DATES:
        raise ValueError("Qualified observation native identity is incomplete")
    if row["numerator"]["source_selector"] == row["denominator"]["source_selector"]:
        raise ValueError("Qualified observation pair selectors are not distinct")
    expected = format((Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.000000000001")), "f")
    if row["rate_decimal"] != expected:
        raise ValueError("Qualified observation decimal differs from its exact fraction")
    for role, expected_label in (
            ("numerator", OFFICIAL_TOTAL_LABELS["ballots_cast"]),
            ("denominator", OFFICIAL_TOTAL_LABELS["registration_stock"])):
        value = row[role]
        fields = value["native_fields"]
        if normalized(value["measure_literal"]) != expected_label or \
                normalized(value["native_category"]) != expected_label or \
                normalized(fields["contest"]) != expected_label or \
                normalized(fields["candidate"]) != expected_label:
            raise ValueError("Qualified observation native total labels changed")
        if str(fields["unit"]) != row["native_reporting_unit"]:
            raise ValueError("Qualified observation native unit changed")
        try:
            equivalent = Decimal(str(fields["value"]).replace(",", "")) == value["value"]
        except Exception as error:
            raise ValueError("Qualified observation native value is invalid") from error
        if not equivalent:
            raise ValueError("Qualified observation native value differs from its count")
        if not OFFICIAL_REQUIRED_QUALIFICATIONS.issubset(
                set(value["original_qualification"].split(";"))):
            raise ValueError("Qualified observation source qualifications changed")


def integration_descriptor(output, expected=None):
    output = Path(output)
    summary_path, manifest_path = output / "summary.json", output / "manifest.json"
    if expected is not None:
        require_pin(pin_file(summary_path), expected["summary"], "Qualification summary")
        require_pin(pin_file(manifest_path), expected["manifest"], "Qualification manifest")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("contract") != CONTRACT:
        raise ValueError("Qualification manifest contract changed")
    for name, file_expected in manifest["files"].items():
        require_pin(pin_file(output / name), file_expected, "Qualification output " + name)
    summary = json.loads(summary_path.read_bytes())
    if summary.get("contract") != CONTRACT or summary.get("state_year_decisions") != 255:
        raise ValueError("Qualification summary contract or scope changed")
    qualified = []
    with gzip.open(output / "qualified-participation-observations.jsonl.gz",
                   "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            validate_observation(row)
            qualified.append(row)
    if len({row["id"] for row in qualified}) != len(qualified):
        raise ValueError("Qualified observation identifiers are not unique")
    held = []
    with gzip.open(output / "held-participation-pairs.jsonl.gz",
                   "rt", encoding="utf-8") as stream:
        held = [json.loads(line) for line in stream]
    reasons = Counter(row["hold_reason"] for row in held)
    if len(qualified) != summary["qualified_observations"] or \
            len(held) != summary["held_participation_pairs"] or \
            dict(sorted(reasons.items())) != summary["held_pair_reasons"]:
        raise ValueError("Qualification sidecar contents differ from summary claims")
    state_year = list(csv.DictReader(
        (output / "state-year-qualifications.csv").open(encoding="utf-8", newline="")))
    products = list(csv.DictReader(
        (output / "state-year-product-qualifications.csv").open(encoding="utf-8", newline="")))
    if len(state_year) != 255 or sum(int(row["qualified_participation_observations"])
                                     for row in state_year) != len(qualified) or \
            sum(int(row["qualified_participation_rates"] or 0)
                for row in products if row["product_kind"] != "declared_coverage_source") != \
            len(qualified):
        raise ValueError("Qualification tabular outputs disagree with sidecars")
    result = {
        "contract": CONTRACT, "qualified_observations": len(qualified),
        "held_pairs": len(held), "candidate_votes_used_as_ballots": False,
        "person_panel_or_individual_transition_claimed": False,
        "summary": pin_file(summary_path), "manifest": pin_file(manifest_path),
        "qualified_sidecar": pin_file(
            output / "qualified-participation-observations.jsonl.gz"),
        "held_sidecar": pin_file(output / "held-participation-pairs.jsonl.gz"),
        "state_year": pin_file(output / "state-year-qualifications.csv"),
        "products": pin_file(output / "state-year-product-qualifications.csv"),
    }
    if expected is not None:
        for key in ("qualified_sidecar", "held_sidecar"):
            require_pin(result[key], expected[key], "Qualification " + key)
    return result


def iter_integrated_observations(dataset_output):
    dataset_output = Path(dataset_output)
    index = json.loads((dataset_output / "index.json").read_bytes())
    descriptor = index.get("historical_precinct_qualification")
    if not descriptor:
        raise ValueError("Historical dataset has no configured precinct qualification")
    relative = PurePosixPath(descriptor["file"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe integrated qualification path")
    path = dataset_output / str(relative)
    require_pin(pin_file(path), descriptor["qualified_sidecar"],
                "Integrated qualification sidecar")
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            validate_observation(row)
            if row["id"] in seen:
                raise ValueError("Integrated qualification contains duplicate identifiers")
            seen.add(row["id"])
            yield row
    if len(seen) != descriptor["qualified_observations"]:
        raise ValueError("Integrated qualification count differs from index")


def build(specification, output):
    specification, output = Path(specification), Path(output)
    if output.exists():
        raise ValueError("Use a new historical qualification output directory")
    spec, decisions_spec, authority, packets, archive_queries = load_inputs(specification)
    decision_body, decisions = read_decisions(decisions_spec["path"], decisions_spec)
    authority_checksums = validate_authority(
        decisions_spec, authority, packets, archive_queries)
    query_products = []
    observed = Counter()
    qualified, held = [], []
    streamed_by_input = Counter()
    for packet in packets:
        if packet["kind"] == "medsl-2016":
            products, counts = stream_medsl_2016(packet)
        elif packet["kind"].startswith("openelections-"):
            products, counts = stream_openelections(packet)
        elif packet["kind"] == "official-state":
            products, counts, qualified, held = stream_official(packet)
        elif packet["kind"] == "north-carolina-2018":
            products, counts = stream_tabular(packet, "official_nc_historical_archive")
        else:
            csv_products, csv_counts = stream_tabular(packet, "mggg_va2020_native_csv")
            gis_products, gis_counts = stream_gis(packet)
            products, counts = csv_products + gis_products, csv_counts + gis_counts
        query_products.extend(products)
        observed.update(counts)
        streamed_by_input[packet["id"]] += sum(product["native_rows"] for product in products)
    with zipfile.ZipFile(authority["path"]) as authority_archive:
        for query in archive_queries:
            products, counts = stream_held_query(authority, authority_checksums, query)
            query_products.extend(products)
            observed.update(counts)
            streamed_by_input[query["id"]] += sum(product["native_rows"] for product in products)
    declared, declared_rows, geometry_products = coverage_products(decisions, observed)
    query_products = [row if isinstance(row, dict) and "row_logical_sha256" in row
                      else finish_product(row) for row in query_products]
    streamed_rows = sum(int(row["native_rows"]) for row in query_products)
    if streamed_rows != declared_rows:
        raise ValueError("Streamed query rows do not reconcile to all declared numerical sources")
    products = sorted(declared + query_products,
                      key=lambda row: (row["year"], row["state_code"], row["product_id"]))
    scope_products = defaultdict(list)
    for row in products:
        scope_products[(row["state_code"], int(row["year"]))].append(row)
    state_year_rows = []
    for decision in decisions:
        state, year = decision["state_code"], int(decision["year"])
        scoped = scope_products[(state, year)]
        query = [row for row in scoped if row["product_kind"] != "declared_coverage_source"]
        qualified_n = sum(int(row["qualified_participation_rates"]) for row in query)
        held_n = sum(row["state_code"] == state and int(row["year"]) == year for row in held)
        state_year_rows.append({
            "year": year, "state_code": state,
            "source_products_present": decision["source_products_present"],
            "compiled_query_available": decision["compiled_query_available"],
            "source_ids": decision["source_ids"], "source_scopes": decision["source_scopes"],
            "declared_rows_or_cells": decision["parsed_native_rows_or_cells"],
            "query_rows_streamed": sum(int(row["native_rows"]) for row in query),
            "query_products_streamed": len(query),
            "candidate_comparison_products":
                sum(row["compatible_candidate_office_comparison"] != "none" for row in query),
            "qualified_participation_observations": qualified_n,
            "held_participation_pairs": held_n,
            "turnout_rate_qualified": str(qualified_n > 0).lower(),
            "geometry_qualified": "false", "cross_year_identity_qualified": "false",
            "individual_transitions_identified": "false",
            "disposition": ("qualified_native_rate_at_exact_source_unit_no_geometry"
                            if qualified_n else "participation_rate_held"),
        })
    output.mkdir(parents=True)
    (output / "input-state-year-decisions.csv").write_bytes(decision_body)
    write_csv(output / "state-year-product-qualifications.csv", products, PRODUCT_FIELDS)
    write_csv(output / "state-year-qualifications.csv", state_year_rows,
              list(state_year_rows[0]))
    qualified_body = compressed_json_lines(qualified)
    held_body = compressed_json_lines(held)
    (output / "qualified-participation-observations.jsonl.gz").write_bytes(qualified_body)
    (output / "held-participation-pairs.jsonl.gz").write_bytes(held_body)
    held_reasons = Counter(row["hold_reason"] for row in held)
    summary = {
        "contract": CONTRACT, "state_year_decisions": len(state_year_rows),
        "declared_coverage_products": len(declared),
        "geometry_context_only_products": geometry_products,
        "streamed_query_products": len(query_products),
        "streamed_query_rows": streamed_rows,
        "streamed_rows_by_input": dict(sorted(streamed_by_input.items())),
        "all_declared_numerical_source_rows_streamed": True,
        "qualified_observations": len(qualified),
        "held_participation_pairs": len(held),
        "held_pair_reasons": dict(sorted(held_reasons.items())),
        "qualified_states": sorted({row["state_code"] for row in qualified}),
        "candidate_votes_used_as_ballots": False,
        "native_modes_or_totals_summed": False,
        "county_fips_or_boundary_crosswalk_guessed": False,
        "repeated_cross_sections_treated_as_person_panel": False,
        "individual_staying_home_first_vote_or_switching_inferred": False,
        "complete_255_precinct_turnout_claimed": False,
        "geometry_or_cross_year_boundary_qualified": False,
        "inputs": {
            "specification": pin_file(specification),
            "decisions": pin_file(decisions_spec["path"]),
            "authority": pin_file(authority["path"]),
            "packets": {row["id"]: pin_file(row["path"]) for row in packets},
        },
    }
    (output / "summary.json").write_bytes(encoded(summary))
    files = {path.name: pin_file(path) for path in sorted(output.iterdir())
             if path.is_file() and path.name != "manifest.json"}
    manifest = {
        "contract": CONTRACT, "code": pin_file(Path(__file__)),
        "input_specification": pin_file(specification), "files": files,
    }
    (output / "manifest.json").write_bytes(encoded(manifest))
    integration_descriptor(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.inputs, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
