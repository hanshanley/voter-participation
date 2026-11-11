"""Describe voting within documented CPS registration-supported respondent frames."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .cps import OUTCOMES, outcome
from .extract_cps_registered_groups import registration_class
from .cps_state_groups import GROUPS, STATE_CODES, csv_bytes, json_bytes


INPUT_SHA = "b7bbffa49c8586001dcda67fe1829f2f4e3a479212ef05c916431dfc8928c17c"
CLASSES = ("registration_supported", "reported_not_registered", "registration_unknown")
SELECTIONS = [("overall", "All"), *[(d, g) for d, groups in GROUPS.items() for g in groups]]


def pct(numerator, denominator):
    if not denominator:
        return None
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(100 * numerator) / denominator)


def read_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode())))


def build(pairs, baseline, references):
    tallies, seen, dispositions = defaultdict(Counter), set(), []
    for row in pairs:
        year, state, dimension, group = int(row["year"]), row["state_fips"], row["dimension"], row["group"]
        interview, voted, registered = (int(row[field]) for field in ("interview", "voted", "registered"))
        identity = year, state, dimension, group, interview, voted, registered
        if (year not in (2022, 2024) or state not in STATE_CODES or (dimension, group) not in SELECTIONS
                or identity in seen):
            raise ValueError("Invalid or duplicate coarse native response pair")
        seen.add(identity)
        n, units = int(row["sample_n"]), int(row["weight_units"])
        if n <= 0 or units <= 0:
            raise ValueError("Coarse native pairs require positive cases and exact weight units")
        registry, reason = registration_class(interview, voted, registered)
        status = outcome(dict(interview=interview, voted=voted))
        tally = tallies[year, state, dimension, group]
        for field, amount in (("citizen_n", n), ("citizen_units", units),
                              (registry + "_n", n), (registry + "_units", units),
                              ("citizen_" + status + "_n", n), ("citizen_" + status + "_units", units)):
            tally[field] += amount
        if registry == "registration_supported":
            tally["registered_" + status + "_n"] += n
            tally["registered_" + status + "_units"] += units
            tally[reason + "_n"] += n
            tally[reason + "_units"] += units
        dispositions.append(dict(**row, derived_registration_class=registry, native_routing_reason=reason,
            native_voting_outcome=status, raw_respondent_identifier_included=False))
    expected_baseline = {(int(row["year"]), row["state_fips"], row["dimension"], row["group"]): row for row in baseline}
    if baseline and (len(expected_baseline) != 1734 or len(baseline) != 1734):
        raise ValueError("Changed complete accepted citizen-frame query")
    reference = {(int(row["year"]), row["reference_state_code"]): row for row in references
                 if row["population_frame"] == "cvap" and row["year"] in ("2022", "2024")}
    estimates, margins, preserved, partitions, comparisons = [], [], [], [], []
    for year in (2022, 2024):
        for state, code in STATE_CODES.items():
            overall = tallies[year, state, "overall", "All"]
            for dimension, groups in GROUPS.items():
                for field in sorted(overall):
                    child = sum(tallies[year, state, dimension, group][field] for group in groups)
                    if child != overall[field]:
                        raise ValueError("Exclusive native registration/voting partition does not reconcile")
                    partitions.append(dict(year=year, state_code=code, dimension=dimension, field=field,
                        exclusive_group_sum=child, state_total=overall[field], reconciled=True))
            for dimension, group in SELECTIONS:
                key = year, state, dimension, group
                tally = tallies[key]
                if sum(tally[registry + "_units"] for registry in CLASSES) != tally["citizen_units"]:
                    raise ValueError("Registration classes do not partition full citizen weight")
                if sum(tally["registered_" + status + "_units"] for status in OUTCOMES) != tally["registration_supported_units"]:
                    raise ValueError("Voting classes do not partition registration-supported weight")
                old = expected_baseline.get(key)
                if baseline and old is None:
                    raise ValueError("Missing complete accepted citizen-frame identity")
                if old:
                    fields = {"sample_n": tally["citizen_n"], "citizen_weight_units": tally["citizen_units"],
                        "reported_voter_weight_units": tally["citizen_yes_units"],
                        "reported_nonvoter_weight_units": tally["citizen_no_units"],
                        "unknown_weight_units": tally["citizen_units"] - tally["citizen_yes_units"] - tally["citizen_no_units"]}
                    if any(int(old[field]) != value for field, value in fields.items()):
                        raise ValueError("New registration analysis changed accepted citizen-frame counts")
                    preserved.append(dict(year=year, state_code=code, dimension=dimension, group=group,
                        **fields, all_original_citizen_counts_and_units_preserved=True))
                total = tally["registration_supported_units"]
                yes, no = tally["registered_yes_units"], tally["registered_no_units"]
                unknown = total - yes - no
                identity = dict(year=year, state_fips=state, state_code=code, dimension=dimension, group=group)
                estimates.append(dict(**identity,
                    disposition="source_registration_supported_conditional_estimate" if total else "no_registration_supported_source_cases",
                    citizen_sample_n=tally["citizen_n"], citizen_weight_units=tally["citizen_units"],
                    registration_supported_n=tally["registration_supported_n"], registration_supported_weight_units=total,
                    routed_reported_voter_n=tally["reported_voter_registration_question_routed_out_n"],
                    explicitly_registered_n=tally["explicit_registration_yes_n"],
                    excluded_unknown_registration_n=tally["registration_unknown_n"],
                    excluded_unknown_registration_weight_units=tally["registration_unknown_units"],
                    reported_voted_weight_units=yes, reported_nonvoted_weight_units=no, unknown_voting_weight_units=unknown,
                    reported_voting_within_source_registration_pct=pct(yes, total),
                    reported_nonvoting_within_source_registration_pct=pct(no, total),
                    unknown_voting_within_source_registration_pct=pct(unknown, total),
                    known_voting_response_only_pct=pct(yes, yes + no),
                    raw_registered_case_count_under30_diagnostic=0 < tally["registration_supported_n"] < 30,
                    unknown_registration_imputed_to_registered=False, unknown_voting_imputed_to_nonvoting=False,
                    administrative_registry_population_count=None, administratively_observed_turnout=False,
                    registration_independently_validated=False, observed_staying_home=False,
                    projected_2026_turnout=False, local_allocation=False, design_confidence_interval=None,
                    **{status + "_n": tally["registered_" + status + "_n"] for status in OUTCOMES},
                    **{status + "_weight_units": tally["registered_" + status + "_units"] for status in OUTCOMES}))
                for registry in CLASSES:
                    margins.append(dict(**identity, registration_class=registry,
                        sample_n=tally[registry + "_n"], weight_units=tally[registry + "_units"],
                        within_full_citizen_weight_pct=pct(tally[registry + "_units"], tally["citizen_units"]),
                        missing_or_unknown_assigned=False))
                if dimension == "overall":
                    native = reference.get((year, code))
                    raw_pct = pct(total, tally["citizen_units"])
                    with localcontext() as context:
                        context.prec = 80
                        difference = str(Decimal(raw_pct) - Decimal(native["reported_registered_pct"])) if native and raw_pct else None
                    comparisons.append(dict(year=year, state_code=code, reconstructed_registration_supported_pct=raw_pct,
                        native_CPS_published_registered_pct=native["reported_registered_pct"] if native else None,
                        reconstructed_minus_native_pp=difference,
                        source_common_CPS_not_independent_administrative_validation=True, discrepancy_repaired=False))
    summary = dict(years=[2022, 2024], states_and_dc=51, complete_state_group_queries=len(estimates),
        supported_registered_frame_rows=sum(row["registration_supported_weight_units"] > 0 for row in estimates),
        absent_registered_frame_rows=sum(row["registration_supported_weight_units"] == 0 for row in estimates),
        sparse_registered_frame_under30_diagnostics=sum(row["raw_registered_case_count_under30_diagnostic"] for row in estimates),
        native_coarse_response_pair_rows=len(dispositions), registration_class_rows=len(margins),
        exact_citizen_baseline_preservation_rows=len(preserved), exclusive_partition_checks=len(partitions),
        native_CPS_registration_comparisons=len(comparisons),
        administrative_population_counts_or_2026_projections=0, new_website_view=False)
    return {
        "complete-state-registered-group-query.csv": csv_bytes(estimates),
        "complete-native-registration-margins.csv": csv_bytes(margins),
        "complete-coarse-pair-dispositions.csv": csv_bytes(dispositions),
        "complete-citizen-baseline-preservation.csv": csv_bytes(preserved) if preserved else b"year,state_code,dimension,group\n",
        "complete-exclusive-registration-partitions.csv": csv_bytes(partitions),
        "complete-native-CPS-registration-comparisons.csv": csv_bytes(comparisons),
        "source-qualification.json": json_bytes(dict(
            registration_supported_means_routed_reported_voters_OR_explicit_PES2_yes=True,
            not_all_frame_members_directly_answered_registration_question=True,
            complete_unknown_registration_and_registered_frame_voting_unknowns_retained=True,
            no_raw_respondent_identifiers_or_private_fine_cells_redistributed=True,
            citizen_baseline_1734_counts_and_weight_units_unchanged=len(preserved) == 1734,
            no_administrative_validation_legal_eligibility_staying_home_local_allocation_or_2026_projection=True,
            public_CPS_sparse_coarse_margins_diagnostic_not_design_precision_guarantee=True,
            Louisiana_context_only_unresolved_parish_environment_not_guessed=True,
            Nevada_HTTP200_challenge_not403_not_native_statistics_route_stopped=True,
            current_native27_prior_models_releases_access_holds_and_website_unchanged=True)),
        "summary.json": json_bytes(summary),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    raw = (inputs / "complete-cps-registration-sufficient-inputs.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError("Changed complete frozen sufficient inputs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(manifest) | {"checksums.json"}:
            raise ValueError("Changed complete sufficient input inventory")
        for name, metadata in manifest.items():
            body = archive.read(name)
            if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        with zipfile.ZipFile(io.BytesIO(archive.read("complete-cps-native-state-references.zip"))) as references:
            native = read_csv(references.read("complete-state-year-population-pairs.csv"))
        files = build(read_csv(archive.read("complete-coarse-native-response-pairs.csv")),
                      read_csv(archive.read("previous-citizen-group-query.csv")), native)
    files["inputs/complete-cps-registration-sufficient-inputs.zip"] = raw
    for name in ("cps_registered_groups.py", "extract_cps_registered_groups.py", "cps_state_groups.py", "cps.py", "download.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_cps_registered_groups.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "2022/2024 CPS registration-supported respondent-group frames, all50states andDC.\n"
        "Membership is PES1reportedvoted OR PES2explicitregistered, as documented in native routing.\n"
        "Routed-out PES2=-1 for voters is NOTnotregistered; noninterviews/unknownregistration stay separate.\n"
        "Registered-frame unknownvoting remains in the full denominator, not repaired as nonvoting.\n"
        "Self-report/sourceconditional estimates, NOTadministrative registration/turnout/legaleligibility/stayinghome.\n"
        "No2026projection/state-survey localallocation/fakeCI. Sparse counts are diagnostics, not precision guarantees.\n"
        "Complete safe coarse response-pair inputs, native Census codebooks/reference originals, code/tests/allqueries.\n"
        "No rawrespondents/identifiers/privatefinecells. Native public CPS originals stay local; all numeric sufficient inputs included.\n"
        "LAcontextonly/broken parishenvironment held; NV200challenge stopped, not403/zero/nativeinput.\n"
        "python3 -m unittest discover -s tests -p test_cps_registered_groups.py\n"
        "python3 -m scripts.cps_registered_groups --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = json_bytes({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                                        for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, value)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
