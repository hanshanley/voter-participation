"""Verify all source cells and composition/accounting queries independently with integers."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


def verify(inputs, output):
    checks = 0

    def check(value):
        nonlocal checks
        checks += 1
        if not value:
            raise ValueError(f"Independent Louisiana verification failed at check{checks}")

    def pct(count, total):
        if total == 0:
            return None
        sign = "-" if count < 0 else ""
        quotient, remainder = divmod(abs(count) * 100 * 10**18, total)
        if 2 * remainder > total or 2 * remainder == total and quotient % 2:
            quotient += 1
        whole, fraction = divmod(quotient, 10**18)
        return f"{sign}{whole}.{fraction:018}"

    native = json.loads((inputs / "independent-native.json").read_bytes())
    facts = json.loads((inputs / "native-facts.json").read_bytes())
    result = json.loads((output / "complete-result.json").read_bytes())
    check(hashlib.sha256((inputs / "native.pdf").read_bytes()).hexdigest()
        == "03662b5a09ee09ca57b6806e7ba97e52561317f540dbc6ddafeb56d33f164390")
    check(hashlib.sha256((inputs / "native-facts.json").read_bytes()).hexdigest()
        == "205f430273d6e20747e6be96003e3c2755f07c66a28bab965b2c89fa9eb93dcb")
    check(native["numeric_cells"] == 1040 and len(native["complete_independent_rows"]) == 65)
    original = {(row["page"], row["native_label"]): row["counts"] for row in native["complete_independent_rows"]}
    profiles = result["source_profiles"]
    check(len(profiles) == len(original) == 65)
    check(len(result["group_compositions"]) == 455 and len(result["native_count_cells"]) == 1040)
    check(len(result["margin_accounting"]) == 260 and len(result["literal_subset_decisions"]) == 130)
    cells = {(row["source_key"], row["native_field"]): row for row in result["native_count_cells"]}
    shares = {(row["source_key"], row["dimension"], row["native_group"]): row for row in result["group_compositions"]}
    accounting = {(row["source_key"], row["dimension"]): row for row in result["margin_accounting"]}
    opaque = {(row["source_key"], row["native_header"]): row for row in result["literal_subset_decisions"]}
    margins = {"race": ["WHITE", "BLACK", "OTHER"], "sex": ["MALE", "FEMALE"],
        "registration_affiliation": ["DEM", "REP", "NO PARTY", "OTH"], "native_method": ["INPER", "ABS"]}
    for row in profiles:
        counts = original[row["page"], row["native_label"]]
        check(row["raw_counts"] == counts)
        check(row["source_votes"] == counts["VOTES"])
        check(row["source_print_clock"] == "11/10/2026 3:10:06 AM" and row["source_print_timezone"] is None)
        check(row["report_filter_begin"] == "1900-01-01" and row["report_filter_end"] == "2026-11-09")
        for field in ("geographic_FIPS", "approved_map_reference", "registered_population", "group_turnout_rate",
                "full_election_ballots", "unique_voters", "observed_staying_home", "eligibility", "deaths",
                "migration", "sampling_n", "confidence_interval", "race_sex_method_joint", "UOCAVA_union", "assistance_union"):
            check(row[field] is None)
        check(row["race_categories_harmonized"] is row["native_ABS_relabelled_mail_returned"] is row["local_survey_allocation"] is False)
        for field, value in counts.items():
            check(type(value) is int and cells[row["source_key"], field]["literal_count"] == value)
        for dimension, labels in margins.items():
            subtotal = sum(counts[label] for label in labels)
            residual = counts["VOTES"] - subtotal
            audit = accounting[row["source_key"], dimension]
            check(audit["native_component_sum"] == subtotal and audit["signed_arithmetic_residual"] == residual)
            check(audit["residual_pct_of_source_votes"] == pct(residual, counts["VOTES"]))
            check(audit["residual_is_identified_source_category"] is audit["source_repaired"] is False)
            check(audit["observed_nonvoters"] is audit["missing_population"] is None)
            if dimension == "registration_affiliation":
                continue
            for label in labels:
                share = shares[row["source_key"], dimension, label]
                check(share["native_count"] == counts[label] and share["own_source_votes"] == counts["VOTES"])
                check(share["source_composition_pct"] == pct(counts[label], counts["VOTES"]))
                check(share["denominator"] == "own_native_VOTES_not_registered_population")
                for field in ("registered_group_denominator", "group_turnout_rate", "confidence_interval",
                        "sampling_n", "inferred_individual_voting_choice"):
                    check(share[field] is None)
                check(share["race_categories_harmonized"] is share["local_survey_allocation"] is False)
        for name, labels in (("UOCAVA", ["UOCAVA IN", "UOCAVA OUT"]), ("ASST", ["ASST D", "ASST I"])):
            decision = opaque[row["source_key"], name]
            check(decision["native_fields"] == labels and decision["source_counts"] == [counts[label] for label in labels])
            check(decision["category_meanings_qualified"] is decision["disjoint_union_qualified"] is False)
            check(decision["union_count"] is decision["intersection_with_race_sex_or_method"] is None)
    parents = [row for row in profiles if row["scope_kind"] == "state_parent"]
    parishes = [row for row in profiles if row["scope_kind"] == "parish"]
    check(len(parents) == 1 and len(parishes) == 64)
    check({row["native_code"] for row in parishes} == {f"{i:02}" for i in range(1, 65)})
    parent = parents[0]
    check(len(result["parent_column_comparisons"]) == 16)
    for comparison in result["parent_column_comparisons"]:
        field = comparison["native_field"]
        actual = sum(row["raw_counts"][field] for row in parishes)
        check(comparison["parish_sum"] == actual)
        check(comparison["printed_state_parent"] == parent["raw_counts"][field])
        check(comparison["printed_minus_parish_sum"] == parent["raw_counts"][field] - actual)
        check(comparison["same_report_parent_matches_parish_sum"] == (parent["raw_counts"][field] == actual))
        check(comparison["parent_reconstructed"] is False)
    check(parent["raw_counts"]["VOTES"] == 536190)
    check(accounting[parent["source_key"], "sex"]["signed_arithmetic_residual"] == 278)
    check(result["summary"]["matching_parent_columns"] == 16)
    coverage = result["state_coverage"]
    check(len(coverage) == 51 and len({row["state_code"] for row in coverage}) == 51)
    for row in coverage:
        check(row["native_VOTES"] == (536190 if row["state_code"] == "LA" else None))
        check(row["national_allocation"] is False and row["electorate_turnout_rate"] is None)
    check(sum(row["literal_count"] == 0 for row in result["native_count_cells"]) == 21)
    check(facts["print_timezone"] is None and facts["pdf_metadata_timezone_not_assigned_to_print_clock"])
    for name in ("source_profiles", "native_count_cells", "group_compositions", "margin_accounting",
            "literal_subset_decisions", "parent_column_comparisons", "state_coverage"):
        rows = [{key: json.dumps(value, sort_keys=True, separators=(",", ":"))
            if isinstance(value, (dict, list)) else value for key, value in row.items()} for row in result[name]]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        check((output / ("complete-" + name.replace("_", "-") + ".csv")).read_bytes() == stream.getvalue().encode())
    check(json.loads((output / "summary.json").read_bytes()) == result["summary"])
    holds = json.loads((inputs / "access-holds.json").read_bytes())
    check(holds["new_michigan_pdf"]["status"] == 403 and holds["new_michigan_pdf_route_stopped"])
    check(holds["alternate_client_cache_or_mirror"] is False)
    return dict(status="passed_independent_louisiana_early_group_queries", checks=checks,
        native_numeric_cells=1040, native_rows=65, parish_rows=64, group_compositions=455,
        margin_accounting_rows=260, opaque_subset_decisions=130, parent_column_checks=16,
        state_coverage_decisions=51, all_native_zeros_and_signed_residuals_preserved=True,
        own_frame_denominators_not_registration=True, no_group_turnout_or_full_election_inference=True,
        all_complete_query_bytes_checked=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "output", "proof"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.inputs, args.output)
    args.proof.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
