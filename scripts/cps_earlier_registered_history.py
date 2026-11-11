"""Four historical CPS snapshots and same-election-type arithmetic, not cohort change."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .cps_state_groups import GROUPS, STATE_CODES, csv_bytes, json_bytes
from .extract_cps_earlier_history import registry


INPUT_SHA = "732c5f6da480e7bbcb10ce99fedb8b84c830475914b895ea2e07c8a7e1a8c220"
SELECTIONS = [("overall", "All"), *[(d, g) for d, groups in GROUPS.items() for g in groups]]
CLASSES = ("registration_supported", "reported_not_registered", "registration_unknown")


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def pct(n, d):
    return number(Fraction(100 * n, d)) if d else None


def read_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode())))


def common(year, state, dimension, group, tally):
    r, c = tally["registration_supported_units"], tally["citizen_units"]
    return dict(year=year, state_fips=state, state_code=STATE_CODES[state], dimension=dimension, group=group,
        election_type="midterm" if year in (2018, 2022) else "presidential",
        citizen_sample_n=tally["citizen_n"], citizen_weight_units=c,
        citizen_voted_weight_units=tally["citizen_yes_units"], citizen_nonvoted_weight_units=tally["citizen_no_units"],
        citizen_unknown_voting_weight_units=c - tally["citizen_yes_units"] - tally["citizen_no_units"],
        registration_supported_n=tally["registration_supported_n"], registration_supported_weight_units=r,
        routed_reported_voter_n=tally["routed_voter_n"], explicitly_registered_n=tally["explicit_registered_n"],
        excluded_unknown_registration_n=tally["registration_unknown_n"],
        excluded_unknown_registration_weight_units=tally["registration_unknown_units"],
        reported_voted_weight_units=tally["registered_yes_units"], reported_nonvoted_weight_units=tally["registered_no_units"],
        unknown_voting_weight_units=r - tally["registered_yes_units"] - tally["registered_no_units"],
        registered_frame_voting_pct=pct(tally["registered_yes_units"], r),
        citizen_frame_voting_pct=pct(tally["citizen_yes_units"], c),
        registration_supported_share_of_citizen_weight_pct=pct(r, c),
        registered_frame_disposition="source_registration_supported_conditional_estimate" if r else "no_registration_supported_source_cases",
        raw_registered_cases_under30_diagnostic=0 < tally["registration_supported_n"] < 30,
        native_response_scheme="1018char_no_PR_SUPINT_PES1at1001_PES2at1003" if year < 2022
                               else "1020char_PR_SUPINT_present_PES1at1003_PES2at1005",
        native2018_question_literal_date_placeholder=year == 2018,
        unknown_response_subclasses_harmonized=False, administrative_registry_population_count=None,
        legally_eligible_population=None, observed_staying_home=None, design_confidence_interval=None,
        projected_2026_turnout=False, local_allocation=False)


def build_earlier(pairs):
    tallies, seen, dispositions = defaultdict(Counter), set(), []
    for row in pairs:
        year, state, dimension, group = int(row["year"]), row["state_fips"], row["dimension"], row["group"]
        voted, registered, n, units = (int(row[f]) for f in ("voted", "registered", "sample_n", "weight_units"))
        identity = year, state, dimension, group, voted, registered
        if (year not in (2018, 2020) or state not in STATE_CODES or (dimension, group) not in SELECTIONS
                or identity in seen or n <= 0 or units <= 0):
            raise ValueError("Invalid or duplicate earlier coarse native pair")
        seen.add(identity)
        registration = registry(voted, registered)
        outcome = "yes" if voted == 1 else "no" if voted == 2 else "unknown"
        tally = tallies[year, state, dimension, group]
        for field, amount in (("citizen_n", n), ("citizen_units", units),
                              ("citizen_" + outcome + "_units", units),
                              (registration + "_n", n), (registration + "_units", units)):
            tally[field] += amount
        if registration == "registration_supported":
            tally["registered_" + outcome + "_units"] += units
            tally["routed_voter_n" if voted == 1 else "explicit_registered_n"] += n
        dispositions.append(dict(**row, derived_registration_class=registration,
            native_voting_response={1: "yes", 2: "no", -1: "not_in_universe", -2: "dont_know",
                                    -3: "refused", -9: "no_response_noninterview_not_separately_identified"}[voted],
            PRSUPINT_present=False, noninterview_flag_invented=False,
            unknown_registration_or_voting_imputed=False))
    estimates, margins, partitions = [], [], []
    for year in (2018, 2020):
        for state in STATE_CODES:
            overall = tallies[year, state, "overall", "All"]
            for dimension, groups in GROUPS.items():
                for field in sorted(overall):
                    total = sum(tallies[year, state, dimension, group][field] for group in groups)
                    if total != overall[field]:
                        raise ValueError("Earlier native exclusive demographic partition failed")
                    partitions.append(dict(year=year, state_code=STATE_CODES[state], dimension=dimension,
                        field=field, exclusive_group_sum=total, state_total=overall[field], reconciled=True))
            for dimension, group in SELECTIONS:
                tally = tallies[year, state, dimension, group]
                if sum(tally[cl + "_units"] for cl in CLASSES) != tally["citizen_units"]:
                    raise ValueError("Earlier native registration partition failed")
                estimates.append(common(year, state, dimension, group, tally))
                for cl in CLASSES:
                    margins.append(dict(year=year, state_fips=state, state_code=STATE_CODES[state],
                        dimension=dimension, group=group, registration_class=cl,
                        sample_n=tally[cl + "_n"], weight_units=tally[cl + "_units"],
                        unknown_status_imputed=False))
    return estimates, margins, partitions, dispositions


def late_projection(registered, citizens):
    lookup = {(int(r["year"]), r["state_fips"], r["dimension"], r["group"]): r for r in citizens}
    out = []
    for row in registered:
        key = int(row["year"]), row["state_fips"], row["dimension"], row["group"]
        native = lookup[key]
        tally = Counter({field: int(row[source]) for field, source in (
            ("citizen_n", "citizen_sample_n"), ("citizen_units", "citizen_weight_units"),
            ("registration_supported_n", "registration_supported_n"),
            ("registration_supported_units", "registration_supported_weight_units"),
            ("routed_voter_n", "routed_reported_voter_n"), ("explicit_registered_n", "explicitly_registered_n"),
            ("registration_unknown_n", "excluded_unknown_registration_n"),
            ("registration_unknown_units", "excluded_unknown_registration_weight_units"),
            ("registered_yes_units", "reported_voted_weight_units"),
            ("registered_no_units", "reported_nonvoted_weight_units"))})
        for field, source in (("citizen_yes_units", "reported_voter_weight_units"),
                              ("citizen_no_units", "reported_nonvoter_weight_units")):
            tally[field] = int(native[source])
        converted = common(*key, tally)
        if (converted["registered_frame_voting_pct"] or "") != row["reported_voting_within_source_registration_pct"]:
            raise ValueError("Projection changed an accepted later registration-frame rate")
        if (converted["citizen_frame_voting_pct"] or "") != native["reported_voting_pct"]:
            raise ValueError("Projection changed an accepted later citizen-frame rate")
        out.append(converted)
    if len(out) != 1734 or len(lookup) != 1734:
        raise ValueError("Incomplete accepted later snapshots")
    return out


def comparisons(estimates):
    index = {(r["year"], r["state_fips"], r["dimension"], r["group"]): r for r in estimates}
    if len(index) != 3468:
        raise ValueError("Incomplete four-year source frame query")
    out = []
    for a, b in ((2018, 2022), (2020, 2024)):
        for state in STATE_CODES:
            for dimension, group in SELECTIONS:
                before, after = index[a, state, dimension, group], index[b, state, dimension, group]
                record = dict(from_year=a, to_year=b, state_fips=state, state_code=STATE_CODES[state],
                    dimension=dimension, group=group, election_type="midterm" if a == 2018 else "presidential",
                    from_registered_cases=before["registration_supported_n"], to_registered_cases=after["registration_supported_n"],
                    sparse_registered_endpoint_diagnostic=before["raw_registered_cases_under30_diagnostic"] or after["raw_registered_cases_under30_diagnostic"])
                for frame in ("registered", "citizen"):
                    field = frame + "_frame_voting_pct"
                    one, two = before[field], after[field]
                    record.update({frame + "_from_source_pct": one, frame + "_to_source_pct": two,
                        frame + "_source_percentage_point_difference":
                            number(Fraction(two) - Fraction(one)) if one is not None and two is not None else None,
                        frame + "_comparison_disposition": "source_snapshot_arithmetic_only" if one is not None and two is not None
                            else "held_no_source_frame_at_one_or_both_endpoints"})
                record.update(unknown_response_subclasses_harmonized=False, definitions_and_weight_targets_harmonized=False,
                    matched_person_panel=False, causal_or_administratively_observed_turnout_change=False,
                    retention_or_new_voter_population=None, deaths=None, migration=None, eligibility=None,
                    design_confidence_interval=None, local_allocation=False)
                out.append(record)
    return out


def build(inputs):
    body = (inputs / "complete-earlier-cps-sufficient-inputs.zip").read_bytes()
    if hashlib.sha256(body).hexdigest() != INPUT_SHA:
        raise ValueError("Changed complete historical sufficient inputs")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        manifest = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(manifest) | {"checksums.json"}:
            raise ValueError("Changed complete input inventory")
        for name, metadata in manifest.items():
            raw = archive.read(name)
            if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        early, margins, partitions, pairs = build_earlier(read_csv(archive.read("complete-earlier-coarse-response-pairs.csv")))
        prior = archive.read("complete-accepted-2022-2024-analysis.zip")
    with zipfile.ZipFile(io.BytesIO(prior)) as previous:
        preserved = previous.read("complete-state-registered-group-query.csv")
        with zipfile.ZipFile(io.BytesIO(previous.read("inputs/complete-cps-registration-sufficient-inputs.zip"))) as old_inputs:
            citizens = read_csv(old_inputs.read("previous-citizen-group-query.csv"))
            with zipfile.ZipFile(io.BytesIO(old_inputs.read("complete-cps-native-state-references.zip"))) as references:
                native = read_csv(references.read("complete-state-year-population-pairs.csv"))
    estimates = early + late_projection(read_csv(preserved), citizens)
    native_index = {(int(r["year"]), r["reference_state_code"]): r for r in native if r["population_frame"] == "cvap"}
    checks = []
    for row in early:
        if row["dimension"] != "overall":
            continue
        reference = native_index[row["year"], row["state_code"]]
        for measure, source_field, native_field in (
            ("voted", "citizen_frame_voting_pct", "reported_voted_pct"),
            ("registered", "registration_supported_share_of_citizen_weight_pct", "reported_registered_pct")):
            one, two = row[source_field], reference[native_field]
            checks.append(dict(year=row["year"], state_code=row["state_code"], measure=measure,
                reconstructed_source_pct=one, native_CPS_published_pct=two,
                source_minus_native_pp=number(Fraction(one) - Fraction(two)) if one is not None and two else None,
                source_common_CPS_not_independent_administrative_validation=True, discrepancy_repaired=False))
    changes = comparisons(estimates)
    qualification = dict(new_years=[2018, 2020], reused_years=[2022, 2024],
        native_1018char_older_layout_PES1at1001_PES2at1003_used=True,
        absent_PR_SUPINT_not_invented_and_minus9_not_relabelled_supplement_noninterview=True,
        native2018_literal_question_date_placeholder_preserved_not_replaced=True,
        unknown_registration_separate_and_registered_frame_vote_unknowns_in_full_denominator=True,
        later_2022_2024_original_registered_query_bytes_and_rates_preserved=True,
        same_type_comparisons_are_source_arithmetic_not_harmonized_population_change=True,
        exact_decimal_arithmetic_not_sampling_precision=True,
        ND_source_registration_supported_frame_not_an_administrative_registry=True,
        no_respondent_identifiers_or_raw_public_microdata_redistributed=True,
        no_2026_projection_legal_eligibility_staying_home_new_returning_cohort_population_or_fake_CI=True,
        current_native27_prior_models_releases_stopped_routes_and_website_unchanged=True)
    summary = dict(years=[2018, 2020, 2022, 2024], states_and_dc=51, new_earlier_queries=len(early),
        complete_four_year_queries=len(estimates), same_type_comparison_decisions=len(changes),
        new_earlier_coarse_pairs=len(pairs), new_earlier_registration_class_rows=len(margins),
        earlier_exclusive_partition_checks=len(partitions), earlier_native_CPS_comparisons=len(checks),
        supported_earlier_registered_frames=sum(r["registration_supported_weight_units"] > 0 for r in early),
        absent_earlier_registered_frames=sum(r["registration_supported_weight_units"] == 0 for r in early),
        earlier_sparse_registered_under30_diagnostics=sum(r["raw_registered_cases_under30_diagnostic"] for r in early),
        held_registered_comparisons=sum(r["registered_source_percentage_point_difference"] is None for r in changes),
        held_citizen_comparisons=sum(r["citizen_source_percentage_point_difference"] is None for r in changes),
        accepted_later_queries_preserved=1734, no_2026_projection_or_new_website_view=True)
    return {
        "complete-four-year-participation-query.csv": csv_bytes(estimates),
        "complete-same-type-participation-comparisons.csv": csv_bytes(changes),
        "complete-earlier-response-pair-query.csv": csv_bytes(pairs),
        "complete-earlier-registration-margins.csv": csv_bytes(margins),
        "complete-earlier-exclusive-partitions.csv": csv_bytes(partitions),
        "complete-earlier-native-CPS-comparisons.csv": csv_bytes(checks),
        "preserved-2022-2024-registration-query.csv": preserved,
        "source-qualification.json": json_bytes(qualification),
        "summary.json": json_bytes(summary)}


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    name = "complete-earlier-cps-sufficient-inputs.zip"
    files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("cps_earlier_registered_history.py", "extract_cps_earlier_history.py",
                 "cps_state_groups.py", "cps.py", "download.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_cps_earlier_registered_history.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "All-state2018/2020 new CPS citizen/registration-supported snapshots;2022/2024 accepted queries reused EXACT.\n"
        "Earlier records1018characters/PES1at1001/PES2at1003, NO PRSUPINT. Native-9 not assigned noninterview.\n"
        "2018question literalNovember X,XXXX retained; year/month from native records/index, no invented questiondate.\n"
        "Registration-supported=PES1votedyes ORPES2registeredyes, NOTvalidated registry/eligibility; NDnotanadminregistry.\n"
        "Unknownregistration separate; voteunknowns within registeredframe remaininfull denominator.\n"
        "Same-type2018to2022midterm/2020to2024presidential differences are source arithmetic, NOTharmonized change,\n"
        "samepeople/retention/newvoters/causalchange/deaths/migration/2026projections/localallocation/fakeCI.\n"
        "Complete coarse sufficient inputs/native codebooks/reference originals/receipts/code/tests/allqueries/checksums.\n"
        "No rawsurvey records/identifiers/privatefinecells redistributed; original public microarchives heldlocal.\n"
        "python3 -m unittest discover -s tests -p test_cps_earlier_registered_history.py\n"
        "python3 -m scripts.cps_earlier_registered_history --inputs inputs --output reproduced\n").encode()
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
