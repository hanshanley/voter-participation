"""Verify every native percentage, state decision and conditional derived quantity."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile


FACTS_SHA = "cba411fe5615782c92886973356ab68ac8334ad0bf41894f4ee4a140ddb56a9b"
PARENT_SHA = "8513403246f0030782dff6006c18bb3498cf14b6c4fef8ec3c94ad330463e51f"


def verify(inputs, output):
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(message)

    def pinned(body):
        return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())

    manifest = json.loads((inputs / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        require(pinned((inputs / name).read_bytes()) == expected, "Sufficient numerical input differs")
    require(pinned((inputs / "native-facts.json").read_bytes())["sha256"] == FACTS_SHA, "Native facts differ")
    require(pinned((inputs / "predecessor-science.zip").read_bytes())["sha256"] == PARENT_SHA, "Whole predecessor differs")
    with zipfile.ZipFile(inputs / "predecessor-science.zip") as archive:
        for name, expected in json.loads(archive.read("checksums.json")).items():
            require(pinned(archive.read(name)) == expected, "Predecessor member differs")
    facts = json.loads((inputs / "native-facts.json").read_bytes())
    native_proof = json.loads((inputs / "native-verification.json").read_bytes())
    require(native_proof["facts_sha256"] == FACTS_SHA
        and native_proof["independent_numeric_cells"] == 663, "Independent source audit differs")
    states = json.loads((inputs / "state-codes.json").read_bytes())
    result = json.loads((output / "complete-result.json").read_bytes())
    require(result["contract"] == "participation.mevp_state_participation.v1", "Result contract differs")
    require(result["methods_field_end"] == "2026-11-03"
        and result["pdf_field_end"] == "2026-11-02", "Source clock conflict repaired")
    require(result["source_frame"] == "mixed_reported_and_certain_intended_participants_not_all_eligible_residents",
        "Current participant source frame relabeled")
    require(result["policy"] == json.loads((inputs / "policy.json").read_bytes()), "Policy differs")
    for flag in ("threshold_is_design_precision", "pool_source_groups", "renormalize_history_bins",
            "convert_percentages_to_respondent_counts", "derive_union_of_multiresponse_experiences",
            "state_population_transport", "absence_or_turnout_identified", "first_ever_voter_identified",
            "individual_retention_identified", "harmonize_racial_groups", "design_intervals_supplied",
            "demographic_local_allocation", "frontend_activation"):
        require(result["policy"][flag] is False, "Unqualified policy promotion")
    require(result["policy"]["raw_column_n_minimum"] == 100, "Support diagnostic differs")
    by_name = {value: key for key, value in states.items()}
    profiles = {row["source_key"]: row for row in result["profiles"]}
    columns = result["source_column_decisions"]
    require(len(profiles) == len(result["profiles"]) == 16 and len(columns) == 51,
        "Incomplete or duplicate source profile/column inventory")
    selected, ordinal = {}, 0
    expected_profile_csv = []
    for table in facts["tables"]:
        for index, banner in enumerate(table["columns"]):
            column = columns[ordinal]
            ordinal += 1
            key = f"{table['group']}:{index}"
            scope = "US" if index == 0 else by_name.get(banner)
            kind = "national" if index == 0 else "state" if scope else "context_only"
            n = table["raw_respondent_n"][index]
            history = {name: values[index] for name, values in table["history_pct"].items()}
            experience = {name: values[index] for name, values in table["experience_pct"].items()}
            status = "excluded_multistate_or_partisan_context" if scope is None else (
                "held_raw_source_support" if n < 100 else "native_reported_participant_profile")
            require(column == dict(source_key=key, source_group=table["group"], native_banner=banner,
                scope=scope, scope_kind=kind, raw_respondent_n=n, disposition=status,
                history_pct=history, experience_pct=experience, source_url=table["source_url"],
                source_sha256=table["source_sha256"], source_page=1), "Native column value, key or scope differs")
            for value in [n, *history.values(), *experience.values()]:
                require(type(value) is int and value >= 0, "Native value or observed zero changed")
            profile = profiles.get(key)
            if status != "native_reported_participant_profile":
                require(profile is None, "Excluded or small source frame promoted")
                continue
            require(profile is not None, "Supported direct source column lost")
            require(profile["source_group"] == table["group"] and profile["scope"] == scope
                and profile["scope_kind"] == kind and profile["raw_respondent_n"] == n
                and profile["history_pct"] == history and profile["experience_pct"] == experience,
                "Native reported profile differs")
            require(profile["first_2026_pct"] == history["first_2026"], "First-November source rate differs")
            require(profile["reported_prior_bin_sum_pct"] == history["first_2024"] +
                history["first_2022"] + history["first_2020_or_earlier"], "Prior-bin source sum differs")
            require(profile["reported_first_2024_or_2026_sum_pct"] == history["first_2024"] +
                history["first_2026"], "Recent-bin source sum differs")
            require(profile["reported_first_2022_or_later_sum_pct"] ==
                sum(history[name] for name in ("first_2022", "first_2024", "first_2026")), "Recent source sum differs")
            require(profile["printed_history_sum_pct"] == sum(history.values())
                and profile["signed_unallocated_rounding_or_response_pp"] == 100 - sum(history.values()),
                "Source bins renormalized or residual repaired")
            require(profile["state_minus_own_national_first_2026_pp"] == (
                history["first_2026"] - table["history_pct"]["first_2026"][0] if kind == "state" else None),
                "Nested-source contrast differs")
            require(profile["sample_population"] == "reported_early_voters_or_certain_election_day_intenders"
                and profile["percent_not_respondent_counts"] is True, "Survey percentages relabeled counts or population")
            for flag in ("completed_voting_verified", "independent_replication", "native_group_harmonized", "local_allocation"):
                require(profile[flag] is False, "Unqualified participation claim")
            for value in ("turnout_or_absence_estimate", "first_ever_voter_estimate",
                    "individual_retention", "design_confidence_interval", "any_experience_union_pct",
                    "eligible_population", "deaths", "migration"):
                require(profile[value] is None, "Invented absence, counts, precision or multiresponse union")
            selected[scope, table["group"]] = profile
            expected_profile_csv.append(profile)
    queries = result["state_group_decisions"]
    require(len(queries) == 255 and len(states) == 51, "Incomplete state/DC-by-source-group grid")
    expected_keys = [(state, table["group"]) for state in sorted(states) for table in facts["tables"]]
    require([(row["state_code"], row["source_group"]) for row in queries] == expected_keys, "Missing or duplicate grid decision")
    for row in queries:
        expected = selected.get((row["state_code"], row["source_group"]))
        require(row["state_name"] == states[row["state_code"]] and row["profile"] == expected,
            "Absent state/group invented or source profile changed")
        require(row["disposition"] == ("native_reported_participant_profile" if expected else
            "not_supplied_by_held_state_column"), "State availability differs")
    summary = result["summary"]
    require(summary == json.loads((output / "summary.json").read_bytes()), "Summary export differs")
    require(summary == dict(source_documents=5, complete_source_columns=51, complete_native_numeric_cells=663,
        selected_source_profiles=16, national_profiles=5, state_group_profiles=11, complete_state_group_queries=255,
        missing_state_group_queries=244, context_columns_excluded=35, source_states=["AZ", "CA", "FL", "MI", "TX"],
        corrected_source_counts=0, reconstructed_missing_profiles=0, new_confidence_intervals=0,
        population_turnout_estimates=0, frontend_activation=False), "Numerical inventory differs")
    for name, expected in (("complete-participant-profiles.csv", result["profiles"]),
            ("complete-source-column-decisions.csv", columns)):
        with (output / name).open(newline="") as stream:
            actual = list(csv.DictReader(stream))
        require(len(actual) == len(expected), "Full source/profile CSV truncated")
        for item, source in zip(actual, expected):
            flat = {key: value for key, value in source.items() if key not in ("history_pct", "experience_pct")}
            flat.update({"history_" + key: value for key, value in source["history_pct"].items()})
            flat.update({"experience_" + key: value for key, value in source["experience_pct"].items()})
            require(item == {key: "" if value is None else str(value) for key, value in flat.items()},
                "Full profile/source CSV field differs")
    with (output / "complete-state-group-decisions.csv").open(newline="") as stream:
        actual = list(csv.DictReader(stream))
    require(len(actual) == 255, "State query CSV truncated")
    for item, row in zip(actual, queries):
        profile = row["profile"]
        expected = {key: value for key, value in row.items() if key != "profile"}
        expected.update({key: profile[key] if profile else None for key in
            ("source_key", "raw_respondent_n", "first_2026_pct", "reported_prior_bin_sum_pct")})
        require(item == {key: "" if value is None else str(value) for key, value in expected.items()}, "State query field differs")
    holds = json.loads((inputs / "access-holds.json").read_bytes())
    require(len(holds["routes"]) == 6 and all(row["http_status"] == 403 and row["bytes"] == 17
        and row["retry_attempts"] == 0 for row in holds["routes"]), "Source-specific access holds changed")
    require(holds["blocked_new_state_originals_acquired"] is False
        and holds["alternate_client_cache_or_mirror_used"] is False, "Blocked-route recovery falsely claimed")
    return dict(status="passed_independent_mevp_participation_profiles", checks=checks,
        native_numeric_cells=663, source_columns=51, native_state_group_profiles=11,
        native_national_profiles=5, complete_state_group_decisions=255,
        missing_state_group_cells=244, no_population_turnout_absence_or_first_ever_claim=True,
        all_native_bins_and_residuals_preserved=True, all_multiresponse_experiences_uncombined=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "output", "proof"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    proof = verify(args.inputs, args.output)
    with args.proof.open("x") as handle:
        json.dump(proof, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
