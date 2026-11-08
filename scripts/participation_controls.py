"""Compare participation controls and conditional current-register model scenarios."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile


EVIDENCE = {
    "nc-2026-reported-ballots-20261106": ("NC", "state", "reported_cast_ballots", "active_and_inactive_registered_voters"),
    "ga-2026-reported-ballots-20261107": ("GA", "state", "reported_cast_ballots", "unqualified_missing_county_denominators"),
    "co-2026-returned-processed-20261105": ("CO", "state", "returned_processed_ballots", "eligible_registered_including_election_day_preregistrants"),
    "fl-duval-2026-reported-ballots-20261107": ("FL", "county", "reported_cast_ballots", "county_registered_source_definition"),
    "nv-clark-2026-reported-ballots-20261106": ("NV", "county", "reported_cast_ballots", "county_current_registered_result_frame"),
    "oh-butler-2026-recorded-credit-20261107": ("OH", "county", "current_record_participation_credits", "current_county_registration_records"),
    "tx-harris-2026-counted-ballots-20261104": ("TX", "county", "counted_ballots", "county_registered_source_definition"),
    "ca-2026-native-voter-turnout-20261106": ("CA", "state", "native_voterTurnout_not_qualified_ballots", "native_totalRegisteredVoters_definition_unqualified"),
}
REGISTERED = {
    "registered_voters_source_definition", "active_and_inactive_registered_voters",
    "active_registered_voters", "eligible_registered_including_election_day_preregistrants",
    "native_totalRegisteredVoters_definition_unqualified",
}
HOUSE_OFFICE = "U.S. House district contests aggregated within state"
INPUTS = {
    "civic-selected-aggregates.json", "uf-turnout.json", "reviewed-2026-observations.json",
    "published-reporting-controls.json", "published-reporting-complete-snapshot.zip",
    "house-state-party-totals.csv.gz",
}


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows):
    if not rows:
        raise ValueError("Missing complete output query")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def controls(reporting, evidence):
    result = []
    for row in reporting:
        if row["denominator_basis"] not in REGISTERED | {"eligible_voters_source_estimate"}:
            raise ValueError("Unreviewed reporting denominator")
        result.append(dict(
            id="reporting-" + row["state_code"], state_code=row["state_code"], year=2026,
            geographic_level="state", geography=row["state"], source_family=row["source_url"],
            measure="reported_cast_ballots", native_measure="ballots",
            numerator=row["ballots"], denominator=row["denominator"],
            denominator_basis=row["denominator_basis"], denominator_label=row["denominator_basis"],
            source_time_label=row["source_update_label"], source_url=row["source_url"],
            native_status=row["status"], source_kind="published_reporting_snapshot",
            selected_state_reference=False, disposition="pending_scope_review",
        ))
    for row in evidence["observations"]:
        if row["id"] not in EVIDENCE:
            raise ValueError("New observation requires an explicit measure/geography contract")
        state, level, measure, basis = EVIDENCE[row["id"]]
        if level == "state" and not row["scope"].startswith("statewide"):
            raise ValueError("Reviewed statewide source changed scope")
        result.append(dict(
            id=row["id"], state_code=state, year=2026, geographic_level=level,
            geography=row["jurisdiction"], source_family=row["source_url"], measure=measure,
            native_measure=row["measure"], numerator=row["numerator"], denominator=row["denominator"],
            denominator_basis=basis, denominator_label=row["denominator_label"],
            source_time_label=row["source_time_label"], source_url=row["source_url"],
            native_status=row["status"], source_kind="reviewed_public_observation",
            selected_state_reference=False, disposition="pending_scope_review",
        ))
    families = defaultdict(list)
    for row in result:
        if row["geographic_level"] != "state":
            row["disposition"] = "county_only_no_state_survey_allocation"
            continue
        families[row["state_code"], row["source_family"], row["measure"]].append(row)
    for rows in families.values():
        if len({(r["numerator"], r["denominator"]) for r in rows}) != 1:
            for row in rows:
                row["disposition"] = "different_snapshots_same_family_no_automatic_selection"
            continue
        ordered = sorted(rows, key=lambda row: (row["source_kind"] != "published_reporting_snapshot", row["id"]))
        ordered[0]["selected_state_reference"] = True
        ordered[0]["disposition"] = "selected_state_reference_not_independent_validation"
        for row in ordered[1:]:
            row["disposition"] = "same_source_same_counts_duplicate_not_added"
    states = Counter(row["state_code"] for row in result if row["selected_state_reference"])
    if any(n > 1 for n in states.values()):
        raise ValueError("Multiple distinct state controls require explicit selection")
    return result


def build(civic, uf, reporting, evidence, house):
    observed = controls(reporting, evidence)
    references = {row["state_code"]: row for row in observed if row["selected_state_reference"]}
    survey = {row["scope"]: row for row in civic["participation"]
              if row["dimension"] == "overall" and row["scope"] != "POOLED_SOURCE"}
    estimates = {row["STATE_ABV"]: row for row in uf if row["geographic_level"] == "state"}
    if len(survey) != 50 or "DC" in survey or len(estimates) != 51:
        raise ValueError("Changed registered-source or UF state/D.C. coverage")
    if any(row["ballots_status"] != "estimate" or row["year"] != 2026 for row in uf):
        raise ValueError("Changed UF estimate/year contract")
    house_votes = Counter()
    for row in house:
        if row["year"] != "2026" or row["office"] != HOUSE_OFFICE:
            raise ValueError("Changed House election/office scope")
        value = int(row["votes"])
        if value < 0:
            raise ValueError("Invalid literal House candidate count")
        house_votes[row["state_code"]] += value
    states, scenarios = [], []
    with localcontext() as context:
        context.prec = 80
        for state in sorted(estimates):
            source, control = survey.get(state), references.get(state)
            estimate = estimates[state]
            voter = nonvoter = None
            if source:
                total = Decimal(source["weight"])
                v, n = Decimal(source["modeled_voter_weight"]), Decimal(source["modeled_nonvoter_weight"])
                if total <= 0 or min(v, n) < 0 or v + n != total:
                    raise ValueError("Changed full Civic binary model denominator")
                voter, nonvoter = v / total, n / total
            registered = (control["denominator"] if control and
                          control["denominator_basis"] in REGISTERED else None)
            if registered is not None and (type(registered) is not int or registered <= 0):
                raise ValueError("Invalid native registration denominator")
            cast = (control["numerator"] if control and control["measure"] == "reported_cast_ballots"
                    else None)
            rate = str(100 * Decimal(cast) / registered) if cast is not None and registered else None
            common = dict(
                year=2026, state_code=state, civic_source_n=source["n"] if source else None,
                civic_modeled_voter_pct=str(100 * voter) if voter is not None else None,
                civic_modeled_nonvoter_pct=str(100 * nonvoter) if nonvoter is not None else None,
                civic_weight_target_qualified=False, civic_field_period_qualified=False,
                control_id=control["id"] if control else None,
                control_measure=control["measure"] if control else None,
                control_native_numerator=control["numerator"] if control else None,
                control_registered_denominator=registered,
                control_denominator_basis=control["denominator_basis"] if control else None,
                control_native_time=control["source_time_label"] if control else None,
                control_source_url=control["source_url"] if control else None,
                reported_cast_ballots=cast, reported_ballots_per_native_registered_denominator_pct=rate,
                uf_ballots_estimate=estimate["TOTAL_BALLOTS_COUNTED"],
                uf_ballots_status=estimate["ballots_status"], uf_vep_estimate=estimate["VEP"],
                uf_vep_turnout_estimate=estimate["VEP_TURNOUT_RATE"],
                uf_vep_is_not_a_registered_denominator=True,
                house_candidate_vote_sum_context=house_votes.get(state),
                house_votes_are_not_ballots_or_unique_voters=True,
                conditional_registered_frame_scenario_available=registered is not None and source is not None,
                original_coalition_population_count=None, death_component=None,
                migration_component=None, eligibility_component=None,
            )
            states.append(common)
            if registered is not None and source is not None:
                expected_voters, expected_nonvoters = registered * voter, registered * nonvoter
                if abs(expected_voters + expected_nonvoters - registered) > Decimal("1e-60"):
                    raise ValueError("Conditional current-register partition failed")
                scenarios.append(dict(
                    year=2026, state_code=state, control_id=control["id"],
                    control_measure=control["measure"], control_native_status=control["native_status"],
                    native_registered_denominator=registered,
                    native_denominator_basis=control["denominator_basis"],
                    source_time_label=control["source_time_label"], source_url=control["source_url"],
                    civic_source_n=source["n"], civic_weight=source["weight"],
                    civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(expected_voters),
                    conditional_modeled_nonvoter_count=str(expected_nonvoters),
                    reported_cast_ballot_measure_control=cast,
                    reported_cast_minus_conditional_modeled_voter_count=(
                        str(Decimal(cast)-expected_voters) if cast is not None else None),
                    assumption="native registered denominator is exchangeable with this source-weighted survey propensity",
                    scenario_units="native_registered_denominator_units_not_administratively_observed_people",
                    assumption_validated=False, survey_weight_target_qualified=False,
                    same_frame_and_cutoff_independently_qualified=False,
                    bridge_outcome_calibration_applied=False,
                    model_nonvoter_is_administratively_observed_staying_home=False,
                    original_coalition_population_count=None, death_component=None,
                    migration_component=None, eligibility_component=None,
                ))
    summary = dict(
        status="conditional_current_registered_frame_scenarios_not_observed_voter_counts",
        state_and_dc_query_rows=len(states), native_control_query_rows=len(observed),
        selected_state_control_rows=len(references),
        exact_same_source_duplicates_not_added=sum(
            r["disposition"] == "same_source_same_counts_duplicate_not_added" for r in observed),
        county_controls_retained_not_allocated=sum(r["geographic_level"] == "county" for r in observed),
        conditional_registered_frame_scenarios=len(scenarios),
        scenarios_with_reported_cast_ballot_comparison=sum(
            r["reported_cast_ballot_measure_control"] is not None for r in scenarios),
        scenario_states=[r["state_code"] for r in scenarios],
        official_cast_control_states=[r["state_code"] for r in states if r["reported_cast_ballots"] is not None],
        notes=[
            "R*p and R*(1-p) are explicit conditional current-register scenarios, not observed people staying home.",
            "Civic weight target/calibration and field period remain unqualified; exchangeability to each native registration frame is not validated.",
            "No new bridge outcome calibration is applied; this does not establish that the original source weights were uncalibrated or independently validated.",
            "Active, all-registered, eligible/pre-registered and source-undefined registration frames are not silently harmonized.",
            "Reported state cast-ballot controls are unofficial/incomplete-count snapshots, not certified final turnout.",
            "Colorado returned/processed and California source-labeled voterTurnout do not become cast-ballot controls.",
            "The duplicate North Carolina source is retained but never added twice.",
            "County-only controls remain separate; no state survey estimate is allocated to a county.",
            "UF initial ballot/VEP estimates remain estimates. VEP is not used as a registered denominator.",
            "House candidate vote sums are office-specific context, not ballots or unique voters.",
            "Missing registered controls remain null, including North Dakota's unsupplied eligible denominator.",
            "D.C. has no allocated Civic survey estimate. No national population bridge is constructed.",
            "No original-coalition, eligibility, death or migration quantities are inferred; unknowns remain null.",
            "Arithmetic discrepancies remain visible; no outcome fitting, partisan reweighting or confidence interval is applied.",
        ])
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(observed),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "summary.json": json_bytes(summary),
    }, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    manifest = json.loads((inputs / "source-manifest.json").read_bytes())
    if set(manifest["inputs"]) != INPUTS or manifest.get("original_raw_survey_or_voter_records_included") is not False:
        raise ValueError("Unapproved or nonpublic aggregate input set")
    native = {}
    for name, receipt in manifest["inputs"].items():
        if Path(name).name != name:
            raise ValueError("Unqualified aggregate input path")
        content = (inputs / name).read_bytes()
        if len(content) != receipt["bytes"] or hashlib.sha256(content).hexdigest() != receipt["sha256"]:
            raise ValueError("Changed frozen public aggregate input")
        native[name] = content
    with gzip.open(io.BytesIO(native["house-state-party-totals.csv.gz"]), "rt", newline="") as stream:
        house = list(csv.DictReader(stream))
    files, summary = build(
        json.loads(native["civic-selected-aggregates.json"]), json.loads(native["uf-turnout.json"]),
        json.loads(native["published-reporting-controls.json"]),
        json.loads(native["reviewed-2026-observations.json"]), house)
    files.update({"inputs/" + name: content for name, content in native.items()})
    files["inputs/source-manifest.json"] = json_bytes(manifest)
    files["scripts/participation_controls.py"] = Path(__file__).read_bytes()
    files["tests/test_participation_controls.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_participation_controls.py").read_bytes()
    files["README.txt"] = (
        "Current registered-frame conditional participation scenarios, not observed staying home.\n"
        "All permitted aggregate inputs, complete state/native-control/scenario queries, code and tests included.\n"
        "No raw respondents, voter identifiers, original-coalition populations or county allocations.\n"
        "From the unpacked complete archive, without packages/network:\n"
        "  python3 -m unittest discover -s tests -p test_participation_controls.py\n"
        "  python3 -m scripts.participation_controls --inputs inputs --output reproduced\n"
        "Read all frame, cutoff, measure and conditional-assumption qualifications in summary.json.\n"
    ).encode()
    files["checksums.json"] = json_bytes({
        name: dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        for name, content in sorted(files.items())})
    output.mkdir(parents=True)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps({key: value for key, value in summary.items() if key != "notes"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
