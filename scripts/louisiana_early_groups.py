"""Compute complete native early-report compositions, not group turnout or full ballots."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path


PDF_SHA = "03662b5a09ee09ca57b6806e7ba97e52561317f540dbc6ddafeb56d33f164390"
FACTS_SHA = "205f430273d6e20747e6be96003e3c2755f07c66a28bab965b2c89fa9eb93dcb"
FIELDS = ("VOTES", "WHITE", "BLACK", "OTHER", "MALE", "FEMALE", "DEM", "REP",
    "NO PARTY", "OTH", "UOCAVA IN", "UOCAVA OUT", "INPER", "ABS", "ASST D", "ASST I")
DIMENSIONS = {"race": ("WHITE", "BLACK", "OTHER"), "sex": ("MALE", "FEMALE"),
    "native_method": ("INPER", "ABS"), "registration_affiliation": ("DEM", "REP", "NO PARTY", "OTH")}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def percent(count, total):
    if total == 0:
        return None
    with localcontext() as context:
        context.prec = 60
        return format(100 * Decimal(count) / Decimal(total), ".18f")


def policy_check(policy):
    if (policy["contract"] != "participation.louisiana_early_groups_policy.v1"
            or policy["year"] != 2026
            or policy["source_frame"] != "native_statewide_early_voting_statistical_report"
            or policy["composition_denominator"] != "own_native_VOTES_not_registered_population"
            or policy["composition_dimensions"] != ["race", "sex", "native_method"]
            or policy["accounting_dimensions"] != ["race", "sex", "registration_affiliation", "native_method"]
            or policy["printed_timezone"] is not None
            or any(policy[key] is not True for key in ("source_codes_not_FIPS",
                "residuals_are_unallocated_arithmetic_not_identified_classes",
                "native_ABS_not_relabelled_mail_returned", "affiliation_not_voting_behavior"))
            or any(policy[key] is not False for key in ("race_categories_harmonized",
                "race_sex_method_intersections_inferred", "UOCAVA_or_assistance_unions_inferred",
                "registration_denominators_supplied", "full_election_ballots_identified",
                "unique_people_identified", "source_counts_repaired", "new_CIs",
                "local_survey_allocation", "frontend_activation"))):
        raise ValueError("Unqualified change to native source scope")


def load_inputs(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    if manifest["contract"] != "participation.louisiana_early_inputs.v1":
        raise ValueError("Unknown frozen inputs")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or pin((root / name).read_bytes()) != expected:
            raise ValueError("Unsafe or changed sufficient input")
    if (pin((root / "native.pdf").read_bytes())["sha256"] != PDF_SHA
            or pin((root / "native-facts.json").read_bytes())["sha256"] != FACTS_SHA):
        raise ValueError("Changed original or complete native facts")
    facts = json.loads((root / "native-facts.json").read_bytes())
    native = json.loads((root / "independent-native.json").read_bytes())
    if (native["facts_sha256"] != FACTS_SHA or native["numeric_cells"] != 1040
            or native["status"] != "passed_independent_original_louisiana_early_cells"):
        raise ValueError("Missing complete independent original verification")
    policy = json.loads((root / "policy.json").read_bytes())
    policy_check(policy)
    codes = json.loads((root / "state-codes.json").read_bytes())
    if len(codes) != 51 or len(set(codes)) != 51 or "LA" not in codes or "DC" not in codes:
        raise ValueError("Changed complete state/DC coverage roster")
    return facts, policy, codes


def build(facts, policy, codes):
    policy_check(policy)
    if (facts["contract"] != "participation.louisiana_early_native_facts.v1"
            or facts["pdf_sha256"] != PDF_SHA or tuple(facts["fields"]) != FIELDS
            or facts["election_date"] != "2026-11-03" or facts["filter_begin_date"] != "1900-01-01"
            or facts["filter_end_date"] != "2026-11-09"
            or facts["print_clock_literal"] != "11/10/2026 3:10:06 AM" or facts["print_timezone"] is not None):
        raise ValueError("Changed native source identity, filter or clock")
    rows = facts["rows"]
    parents = [row for row in rows if row["scope_kind"] == "state_parent"]
    parishes = [row for row in rows if row["scope_kind"] == "parish"]
    if (len(rows) != 65 or len(parents) != 1 or len(parishes) != 64
            or parents[0]["native_label"] != "STATE TOTAL"
            or {row["native_code"] for row in parishes} != {f"{i:02}" for i in range(1, 65)}
            or len({row["source_key"] for row in rows}) != 65):
        raise ValueError("Incomplete or duplicated native row coverage")
    profiles, cells, composition, accounting, opaque = [], [], [], [], []
    for native in rows:
        counts = native["counts"]
        if set(counts) != set(FIELDS) or any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("Unknown, negative or substituted native count")
        base = dict(source_key=native["source_key"], native_label=native["native_label"],
            native_code=native["native_code"], scope_kind=native["scope_kind"], page=native["page"])
        total = counts["VOTES"]
        profiles.append(dict(**base, raw_counts=counts,
            source_frame=policy["source_frame"], source_votes=total,
            report_filter_begin=facts["filter_begin_date"], report_filter_end=facts["filter_end_date"],
            source_print_clock=facts["print_clock_literal"], source_print_timezone=None,
            geographic_FIPS=None, approved_map_reference=None,
            registered_population=None, group_turnout_rate=None, full_election_ballots=None,
            unique_voters=None, observed_staying_home=None, eligibility=None, deaths=None, migration=None,
            sampling_n=None, confidence_interval=None, race_categories_harmonized=False,
            race_sex_method_joint=None, UOCAVA_union=None, assistance_union=None,
            native_ABS_relabelled_mail_returned=False, local_survey_allocation=False))
        for field in FIELDS:
            cells.append(dict(**base, native_field=field, literal_count=counts[field]))
        for dimension in policy["accounting_dimensions"]:
            selected = DIMENSIONS[dimension]
            component_sum = sum(counts[field] for field in selected)
            residual = total - component_sum
            accounting.append(dict(**base, dimension=dimension, source_votes=total,
                native_component_sum=component_sum, signed_arithmetic_residual=residual,
                residual_pct_of_source_votes=percent(residual, total),
                residual_is_identified_source_category=False, source_repaired=False,
                observed_nonvoters=None, missing_population=None))
        for dimension in policy["composition_dimensions"]:
            for field in DIMENSIONS[dimension]:
                composition.append(dict(**base, dimension=dimension, native_group=field,
                    native_count=counts[field], own_source_votes=total,
                    source_composition_pct=percent(counts[field], total),
                    denominator="own_native_VOTES_not_registered_population",
                    disposition="source_composition_not_group_turnout" if total > 0 else "held_zero_native_denominator",
                    registered_group_denominator=None, group_turnout_rate=None,
                    confidence_interval=None, sampling_n=None, race_categories_harmonized=False,
                    inferred_individual_voting_choice=None, local_survey_allocation=False))
        for dimension, fields in (("UOCAVA", ("UOCAVA IN", "UOCAVA OUT")),
                ("ASST", ("ASST D", "ASST I"))):
            opaque.append(dict(**base, native_header=dimension,
                native_fields=list(fields), source_counts=[counts[field] for field in fields],
                category_meanings_qualified=False, disjoint_union_qualified=False, union_count=None,
                intersection_with_race_sex_or_method=None))
    parent = parents[0]
    parent_checks = []
    for field in FIELDS:
        summed = sum(row["counts"][field] for row in parishes)
        printed = parent["counts"][field]
        parent_checks.append(dict(native_field=field, parish_count=64, parish_sum=summed,
            printed_state_parent=printed, printed_minus_parish_sum=printed - summed,
            same_report_parent_matches_parish_sum=summed == printed, parent_reconstructed=False))
    coverage = [dict(state_code=code, source_family="Louisiana Statewide Early Voting Statistical Report",
        disposition="direct_source_state_parent" if code == "LA" else "not_supplied_by_this_state_source",
        native_VOTES=parent["counts"]["VOTES"] if code == "LA" else None,
        group_compositions_supplied=code == "LA", electorate_turnout_rate=None,
        national_allocation=False) for code in codes]
    state_accounting = {row["dimension"]: row["signed_arithmetic_residual"] for row in accounting
        if row["scope_kind"] == "state_parent"}
    summary = dict(source_documents=1, native_pages=2, native_rows=65, native_parishes=64,
        native_numeric_cells=len(cells), source_group_compositions=len(composition),
        complete_margin_accounting=len(accounting), literal_subset_decisions=len(opaque),
        complete_parent_column_checks=len(parent_checks),
        matching_parent_columns=sum(row["same_report_parent_matches_parish_sum"] for row in parent_checks),
        complete_state_coverage_decisions=len(coverage), source_absent_states=50,
        state_native_counts=parent["counts"], state_signed_accounting_residuals=state_accounting,
        native_zero_count_cells=sum(row["literal_count"] == 0 for row in cells),
        sex_residual_parish_count=sum(row["dimension"] == "sex" and row["scope_kind"] == "parish"
            and row["signed_arithmetic_residual"] != 0 for row in accounting),
        source_count_repairs=0, reconstructed_registration_denominators=0,
        derived_turnout_rates=0, new_intervals=0, frontend_activation=False)
    return dict(contract="participation.louisiana_early_group_compositions.v1",
        policy=policy, summary=summary, source_profiles=profiles, native_count_cells=cells,
        group_compositions=composition, margin_accounting=accounting,
        literal_subset_decisions=opaque, parent_column_comparisons=parent_checks, state_coverage=coverage)


def csv_bytes(rows):
    output = io.StringIO(newline="")
    flattened = []
    for row in rows:
        flattened.append({key: json.dumps(value, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list)) else value for key, value in row.items()})
    writer = csv.DictWriter(output, fieldnames=sorted(flattened[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(flattened)
    return output.getvalue().encode()


def result_files(result):
    names = ("source_profiles", "native_count_cells", "group_compositions", "margin_accounting",
        "literal_subset_decisions", "parent_column_comparisons", "state_coverage")
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
        **{"complete-" + name.replace("_", "-") + ".csv": csv_bytes(result[name]) for name in names}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output")
    result = build(*load_inputs(args.inputs))
    args.output.mkdir(parents=True)
    for name, body in result_files(result).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"], sort_keys=True))
