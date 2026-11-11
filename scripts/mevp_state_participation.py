"""Source-defined participant history/experience profiles, never population turnout."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


FACTS_SHA = "cba411fe5615782c92886973356ab68ac8334ad0bf41894f4ee4a140ddb56a9b"
PARENT_SHA = "8513403246f0030782dff6006c18bb3498cf14b6c4fef8ec3c94ad330463e51f"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def load_inputs(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts or pin((root / name).read_bytes()) != expected:
            raise ValueError("Changed complete permitted input")
    if (pin((root / "native-facts.json").read_bytes())["sha256"] != FACTS_SHA
            or pin((root / "predecessor-science.zip").read_bytes())["sha256"] != PARENT_SHA):
        raise ValueError("Changed accepted source facts or predecessor")
    with zipfile.ZipFile(root / "predecessor-science.zip") as archive:
        for name, expected in json.loads(archive.read("checksums.json")).items():
            if pin(archive.read(name)) != expected:
                raise ValueError("Changed complete predecessor member")
    names = ("native-facts.json", "state-codes.json", "methodology.json", "policy.json")
    return tuple(json.loads((root / name).read_bytes()) for name in names)


def validate_policy(policy):
    if (policy["contract"] != "participation.mevp_state_profile_policy.v1"
            or policy["raw_column_n_minimum"] != 100
            or policy["select_only_native_national_or_state_columns"] is not True
            or any(policy[key] is not False for key in (
                "threshold_is_design_precision", "pool_source_groups", "renormalize_history_bins",
                "convert_percentages_to_respondent_counts", "derive_union_of_multiresponse_experiences",
                "state_population_transport", "absence_or_turnout_identified",
                "first_ever_voter_identified", "individual_retention_identified", "harmonize_racial_groups",
                "design_intervals_supplied", "demographic_local_allocation", "frontend_activation"))):
        raise ValueError("Unsupported participant-profile policy")


def build(facts, states, methods, policy):
    validate_policy(policy)
    if (len(states) != 51 or "DC" not in states
            or not methods["source_qualifications"]["includes_certain_intended_election_day_voters"]
            or methods["source_qualifications"]["administrative_turnout_or_choice_validation_supplied"] is not False):
        raise ValueError("Changed state inventory or source universe")
    by_name = {name: code for code, name in states.items()}
    profiles, columns, selected, supplied_states = [], [], {}, set()
    source_groups = [table["group"] for table in facts["tables"]]
    if len(set(source_groups)) != 5:
        raise ValueError("Incomplete native group inventory")
    for table in facts["tables"]:
        width = len(table["columns"])
        if (len(set(table["columns"])) != width or len(table["raw_respondent_n"]) != width
                or table["columns"][0] != table["native_group_label"]
                or any(len(row) != width or any(type(value) is not int or not 0 <= value <= 100 for value in row)
                    for family in ("history_pct", "experience_pct") for row in table[family].values())):
            raise ValueError("Incomplete native source column/percentage table")
        for index, banner in enumerate(table["columns"]):
            n = table["raw_respondent_n"][index]
            if type(n) is not int or n <= 0:
                raise ValueError("Invalid source respondent base")
            scope = "US" if index == 0 else by_name.get(banner)
            kind = "national" if index == 0 else "state" if scope else "context_only"
            if kind == "state":
                supplied_states.add((scope, table["group"]))
            disposition = ("excluded_multistate_or_partisan_context" if scope is None else
                "held_raw_source_support" if n < policy["raw_column_n_minimum"] else
                "native_reported_participant_profile")
            history = {key: values[index] for key, values in table["history_pct"].items()}
            experience = {key: values[index] for key, values in table["experience_pct"].items()}
            key = f"{table['group']}:{index}"
            columns.append(dict(source_key=key, source_group=table["group"], native_banner=banner,
                scope=scope, scope_kind=kind, raw_respondent_n=n, disposition=disposition,
                history_pct=history, experience_pct=experience, source_url=table["source_url"],
                source_sha256=table["source_sha256"], source_page=table["source_page"]))
            if disposition != "native_reported_participant_profile":
                continue
            total = sum(history.values())
            profile = dict(source_key=key, source_group=table["group"], scope=scope, scope_kind=kind,
                raw_respondent_n=n, history_pct=history, experience_pct=experience,
                first_2026_pct=history["first_2026"],
                reported_prior_bin_sum_pct=history["first_2024"] + history["first_2022"] + history["first_2020_or_earlier"],
                reported_first_2024_or_2026_sum_pct=history["first_2024"] + history["first_2026"],
                reported_first_2022_or_later_sum_pct=history["first_2022"] + history["first_2024"] + history["first_2026"],
                printed_history_sum_pct=total, signed_unallocated_rounding_or_response_pp=100 - total,
                state_minus_own_national_first_2026_pp=history["first_2026"] - table["history_pct"]["first_2026"][0]
                    if kind == "state" else None,
                sample_population="reported_early_voters_or_certain_election_day_intenders",
                percent_not_respondent_counts=True, completed_voting_verified=False,
                turnout_or_absence_estimate=None, first_ever_voter_estimate=None,
                individual_retention=None, design_confidence_interval=None,
                eligible_population=None, deaths=None, migration=None,
                any_experience_union_pct=None, independent_replication=False,
                native_group_harmonized=False, local_allocation=False)
            if (scope, table["group"]) in selected:
                raise ValueError("Duplicate native source profile")
            selected[scope, table["group"]] = profile
            profiles.append(profile)
    decisions = []
    for state, name in sorted(states.items()):
        for group in source_groups:
            row = selected.get((state, group))
            decisions.append(dict(state_code=state, state_name=name, source_group=group,
                disposition="native_reported_participant_profile" if row else "held_raw_source_support"
                    if (state, group) in supplied_states else "not_supplied_by_held_state_column",
                profile=row))
    summary = dict(source_documents=len(facts["tables"]), complete_source_columns=len(columns),
        complete_native_numeric_cells=sum(len(table["columns"]) * (
            1 + len(table["history_pct"]) + len(table["experience_pct"])) for table in facts["tables"]),
        selected_source_profiles=len(profiles), national_profiles=sum(row["scope_kind"] == "national" for row in profiles),
        state_group_profiles=sum(row["scope_kind"] == "state" for row in profiles),
        complete_state_group_queries=len(decisions), missing_state_group_queries=sum(row["profile"] is None for row in decisions),
        context_columns_excluded=sum(row["scope"] is None for row in columns),
        source_states=sorted({row["scope"] for row in profiles if row["scope_kind"] == "state"}),
        corrected_source_counts=0, reconstructed_missing_profiles=0,
        new_confidence_intervals=0, population_turnout_estimates=0, frontend_activation=False)
    return dict(contract="participation.mevp_state_participation.v1",
        source_frame="mixed_reported_and_certain_intended_participants_not_all_eligible_residents",
        methods_field_end=methods["methods_field_end"], pdf_field_end=methods["pdf_field_end"],
        policy=policy, profiles=profiles, state_group_decisions=decisions,
        source_column_decisions=columns, summary=summary)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def profile_row(row):
    return {**{key: value for key, value in row.items() if key not in ("history_pct", "experience_pct")},
        **{"history_" + key: value for key, value in row["history_pct"].items()},
        **{"experience_" + key: value for key, value in row["experience_pct"].items()}}


def result_files(result):
    profiles = [profile_row(row) for row in result["profiles"]]
    columns = [profile_row(row) for row in result["source_column_decisions"]]
    queries = []
    for row in result["state_group_decisions"]:
        profile = row["profile"]
        queries.append({key: value for key, value in row.items() if key != "profile"} | dict(
            source_key=profile["source_key"] if profile else None,
            raw_respondent_n=profile["raw_respondent_n"] if profile else None,
            first_2026_pct=profile["first_2026_pct"] if profile else None,
            reported_prior_bin_sum_pct=profile["reported_prior_bin_sum_pct"] if profile else None))
    return {"complete-result.json": encoded(result), "summary.json": encoded(result["summary"]),
        "complete-participant-profiles.csv": csv_bytes(profiles),
        "complete-state-group-decisions.csv": csv_bytes(queries),
        "complete-source-column-decisions.csv": csv_bytes(columns)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output directory")
    result = build(*load_inputs(args.inputs))
    args.output.mkdir(parents=True)
    for name, body in result_files(result).items():
        (args.output / name).write_bytes(body)
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
