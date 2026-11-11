"""Same-election-type AP source-model contrasts, not measured turnout changes."""

import argparse
from collections import Counter
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .ap_state_groups import STATES, WEIGHTS, groups


PRIOR_SHA = "22caef437af4e8126bd611a1d3ae0f98d3bc8920d81b7dd0e3e70487029e2372"
PAIRS = (("2018", "2022", "midterm"), ("2020", "2024", "presidential"))
ARITHMETIC_DIMENSIONS = {"overall", "AGE65", "EDUC", "INCOME"}
MASSES = ("modeled_voter_weight", "modeled_nonvoter_weight", "model_unknown_weight")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def build(snapshot):
    if snapshot["schema"] != "ap-state-demographics-v1":
        raise ValueError("Changed prior qualified public source")
    index = {}
    for row in snapshot["rows"]:
        key = tuple(row[field] for field in ("year", "weight_field", "state_code", "dimension", "group"))
        if key in index:
            raise ValueError("Duplicate prior public source cell")
        index[key] = row
    expected_source = {(year, weight, state, dimension, group)
                       for year in ("2018", "2020", "2022", "2024") for weight in WEIGHTS for state in STATES
                       for dimension, labels in groups(year).items() for group in labels}
    if set(index) != expected_source:
        raise ValueError("Incomplete prior public query; no reconstruction of held cells")
    rows = []
    for earlier, later, election_type in PAIRS:
        before_groups, after_groups = groups(earlier), groups(later)
        for weight in WEIGHTS:
            for state in STATES:
                for dimension in sorted(set(before_groups) | set(after_groups)):
                    requested = sorted(set(before_groups.get(dimension, ())) | set(after_groups.get(dimension, ())))
                    for group in requested:
                        before = index.get((earlier, weight, state, dimension, group))
                        after = index.get((later, weight, state, dimension, group))
                        if state == "DC":
                            reason = "no_dc_source_sample"
                        elif dimension == "RACETH5":
                            reason = "held_race_membership_not_harmonized_or_dimension_absent"
                        elif dimension not in ARITHMETIC_DIMENSIONS:
                            reason = "held_native_sex_gender_measurement_not_matched"
                        elif group in {"88", "99"}:
                            reason = "held_unknown_or_disclosure_removed_source_group"
                        elif before is None or after is None:
                            reason = "held_native_dimension_or_group_not_matched"
                        elif any(row["disposition"] != "selected_broad_source_model" for row in (before, after)):
                            reason = "held_prior_source_support_inference_or_disclosure"
                        elif before["native_labels"] != after["native_labels"]:
                            reason = "held_native_label_changed"
                        else:
                            reason = "selected_same_type_source_model_arithmetic"
                        selected = reason == "selected_same_type_source_model_arithmetic"
                        row = dict(from_year=earlier, to_year=later, election_type=election_type,
                            state_code=state, weight_field=weight, dimension=dimension, group=group,
                            from_native_label=before["native_labels"] if before else None,
                            to_native_label=after["native_labels"] if after else None,
                            from_source_disposition=before["disposition"] if before else "native_dimension_not_present",
                            to_source_disposition=after["disposition"] if after else "native_dimension_not_present",
                            from_native_inference=before["inference_status"] if before else None,
                            to_native_inference=after["inference_status"] if after else None,
                            disposition=reason)
                        for prefix, endpoint in (("from", before), ("to", after)):
                            for field in ("n", "positive_weight_n", "weight", *MASSES):
                                row[prefix + "_" + field] = endpoint[field] if selected else None
                        changes = []
                        if selected:
                            for endpoint in (before, after):
                                if (endpoint["year"] not in (earlier, later) or type(endpoint["positive_weight_n"]) is not int
                                        or endpoint["positive_weight_n"] < 500 or endpoint["n"] < endpoint["positive_weight_n"]):
                                    raise ValueError("Changed prior supported public endpoint")
                                values = [Fraction(endpoint[field]) for field in ("weight", *MASSES)]
                                if values[0] <= 0 or min(values[1:]) < 0 or sum(values[1:]) != values[0]:
                                    raise ValueError("Changed full native group denominator")
                            changes = [100 * (Fraction(after[field]) / Fraction(after["weight"])
                                               - Fraction(before[field]) / Fraction(before["weight"]))
                                       for field in MASSES]
                            if sum(changes) != 0:
                                raise ValueError("Outcome-class share contrasts do not reconcile")
                        for position, field in enumerate(("modeled_voter_pp_contrast",
                                                         "modeled_nonvoter_pp_contrast",
                                                         "modeled_unknown_pp_contrast")):
                            row[field] = number(changes[position]) if selected else None
                        row.update(
                            same_election_type=True, native_definitions_harmonized=False,
                            survey_model_or_population_equivalence_validated=False,
                            observed_turnout_change=False, causal_effect=False,
                            individual_retention_or_switching=False, fixed_group_membership=False,
                            native_weight_stages_are_independent_samples=False,
                            income_independently_qualified_household_income=False,
                            design_confidence_interval=None, population_count_change=None,
                            observed_staying_home=None, local_allocation=False)
                        rows.append(row)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    qualification = dict(
        same_type_pairs=[dict(from_year=int(a), to_year=int(b), election_type=t) for a, b, t in PAIRS],
        exact_native_group_weights_not_rounded_display_percentages=True,
        only_both_already_public_supported_endpoints_used=True,
        no_new_private_cells_or_suppression_recovery=True,
        native_code_and_label_match_required_not_measurement_equivalence=True,
        sex_gender_and_race_contrasts_held_no_crosswalk=True,
        unknown_model_mass_retained_in_each_full_denominator=True,
        final_outcome_calibration_not_independent_turnout_validation=True,
        repeated_cross_sections_not_panel_or_fixed_group_cohort=True,
        native_2018_47_inference_state_and_2022_source_holds_preserved=True,
        old_native_reductions_and_qualified_source_campaigns_not_rerun=True,
        cross_study_cps_civic_projection=False, observed_turnout_change=False,
        model_equivalence_validated=False, population_validation=False,
        design_confidence_interval=None, local_allocation=False, new_website_view=False)
    summary = dict(schema="ap-same-type-state-model-contrasts-v1",
        complete_comparison_decisions=len(rows),
        selected_weight_view_contrasts=sum(row["disposition"] == "selected_same_type_source_model_arithmetic" for row in rows),
        selected_nonoverall_weight_view_contrasts=sum(row["disposition"] == "selected_same_type_source_model_arithmetic"
                                                    and row["dimension"] != "overall" for row in rows),
        disposition_counts=dict(Counter(row["disposition"] for row in rows)),
        pairs=qualification["same_type_pairs"], source_only_model_arithmetic_not_observed_turnout_change=True,
        new_private_source_or_raw_respondent_data=False, no_new_website_view=True)
    return {"complete-same-type-state-model-contrasts.csv": stream.getvalue().encode(),
            "source-qualification.json": encoded(qualification), "summary.json": encoded(summary)}


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    prior = (inputs / "prior-complete-ap-state-analysis.zip").read_bytes()
    if hashlib.sha256(prior).hexdigest() != PRIOR_SHA:
        raise ValueError("Changed complete qualified prior AP state package")
    with zipfile.ZipFile(io.BytesIO(prior)) as archive:
        snapshot = json.loads(archive.read("inputs/selected-inputs.json"))
        if archive.read("scripts/ap_state_groups.py") != Path(__file__).with_name("ap_state_groups.py").read_bytes():
            raise ValueError("Changed unchanged prior source definitions")
    files = build(snapshot)
    files["inputs/prior-complete-ap-state-analysis.zip"] = prior
    files["inputs/new-access-observations.json"] = (inputs / "new-access-observations.json").read_bytes()
    for name in ("ap_state_contrasts.py", "ap_state_groups.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_ap_state_contrasts.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Same-election-type AP/NORC source-model-share arithmetic, NOT observed turnout change.\n"
        "2018->2022 midterms and2020->2024 presidential elections; separate native state-weight stages.\n"
        "Only already-public supported endpoints, same native field/code/label. No held-cell statistics recovered.\n"
        "Age/education/income labels do not establish measurement, survey-model or population equivalence.\n"
        "SEX/GENDER and race contrasts held, no harmonization; 2022 missing RACETH5 remains absent.\n"
        "Full native weights and model unknowns retained, exact share-difference arithmetic; no fake intervals.\n"
        "Final-weight calibration is not validation. No individual retention/switching, fixed cohort,\n"
        "causal turnout trend, group-population change or cross-study CPS/Civic projection.\n"
        "Complete prior PUBLIC package, all comparisons/holds, code/tests/results/checksums are included.\n"
        "New MO/OH registration-source403 receipts are metadata only; no cached counts enter the analysis.\n"
        "python3 -m unittest discover -s tests -p test_ap_state_contrasts.py\n"
        "python3 -m scripts.ap_state_contrasts --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                     for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, body)
    print(files["summary.json"].decode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
