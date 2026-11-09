"""Coarse historical state VoteCast model shares, not administrative turnout."""

import argparse
from collections import Counter
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile


YEARS = ("2018", "2020", "2022", "2024")
STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
WEIGHTS = ("FINALVOTE_STATE_WEIGHT", "POLLCLOSE_STATE_WEIGHT")
KEYS = ("year", "weight_field", "state_code", "dimension", "group")
STATISTICS = ("n", "positive_weight_n", "weight", "modeled_voter_weight",
              "modeled_nonvoter_weight", "model_unknown_weight")
MASSES = STATISTICS[2:]
BASELINE_SHA = "dbab5b50a99882780ae8febe76f564acebc3b1acaf7ef23f3b21aa0693a58190"
INPUT_SHA = "50cf9caa47a5a0bd0785e940acb7f17e8274f4741cc0c1d7a70307eae248fc06"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def groups(year):
    return {
        "overall": ("all",),
        "AGE65": tuple(map(str, range(1, 7))) + ("99",),
        "EDUC": ("1", "2", "3", "4", "99"),
        "INCOME": ("1", "2", "3", "4", "5", "99"),
        "SEX" if year == "2018" else "GENDER":
            ("1", "2", "99") if year == "2018" else ("1", "2", "3", "99"),
        "RACETH5": ("1", "2", "3", "4", "5", "88", "99"),
    }


def inference(year, state):
    if year == "2022" and state in {"DE", "WV"}:
        return "withheld_publisher_national_only_state"
    if year == "2018":
        return "source_descriptive_only_publisher_reports_47_state_estimates"
    return "publisher_state_weight_descriptive_not_administrative_turnout"


def select_private(waves, prior):
    """Select from verified aggregate caches; never read native respondent files."""
    index = {}
    for year in YEARS:
        for source in waves[year]:
            key = year, source["weight_field"], source["scope"], source["dimension"], source["group"]
            if source["year"] != year or key in index:
                raise ValueError("Changed or duplicate cached wave aggregate")
            index[key] = source
    requested = [(year, weight, state, dimension, group)
                 for year in YEARS for weight in WEIGHTS for state in STATES
                 for dimension, labels in groups(year).items() for group in labels]
    status = {}
    for key in requested:
        year, weight, state, dimension, group = key
        source = index.get(key)
        if state == "DC":
            reason = "no_dc_source_sample"
        elif year == "2022" and state in {"DE", "WV"}:
            reason = "publisher_national_only_state_inference_withheld"
        elif year == "2022" and dimension == "RACETH5":
            reason = "documented_dimension_absent_in_release"
        elif group in {"88", "99"}:
            reason = "unknown_or_disclosure_removed_not_exported_separately"
        elif source is None or int(source["n"]) == 0:
            reason = "held_source_support_or_complementary_disclosure"
        elif Decimal(source["weight"]) <= 0 or int(source["positive_weight_n"]) < 500:
            reason = "held_source_support_or_complementary_disclosure"
        else:
            reason = "selected_broad_source_model"
        status[key] = reason

    def hide(key):
        changed = False
        year, _, state, dimension, group = key
        for weight in WEIGHTS:
            other = year, weight, state, dimension, group
            if status.get(other) == "selected_broad_source_model":
                status[other] = "held_source_support_or_complementary_disclosure"
                changed = True
        return changed

    for key in requested:
        if status[key] != "selected_broad_source_model":
            hide(key)
    partitions = []
    for year in YEARS:
        for weight in WEIGHTS:
            for state in STATES:
                for dimension in groups(year):
                    if dimension == "overall":
                        continue
                    members = [key for key, row in index.items()
                               if key[:4] == (year, weight, state, dimension) and int(row["n"]) > 0]
                    if members:
                        partitions.append(members)
            for dimension, labels in groups(year).items():
                if dimension == "overall":
                    continue
                for group in labels:
                    members = [(year, weight, state, dimension, group) for state in STATES
                               if (year, weight, state, dimension, group) in index
                               and int(index[year, weight, state, dimension, group]["n"]) > 0]
                    if members:
                        partitions.append(members)
    # Counts in the prior national release and state overalls stay exposed.
    # Synchronize both weight-stage masks so one stage cannot reveal the other's N.
    while True:
        changed = False
        for members in partitions:
            withheld = [key for key in members if status.get(key) != "selected_broad_source_model"]
            exposed = [key for key in members if status.get(key) == "selected_broad_source_model"]
            if len(withheld) == 1 and exposed:
                chosen = max(exposed, key=lambda key: (int(index[key]["n"]), key))
                changed = hide(chosen) or changed
        if not changed:
            break
    rows = []
    for key in requested:
        year, weight, state, dimension, group = key
        source = index.get(key)
        selected = status[key] == "selected_broad_source_model"
        row = dict(zip(KEYS, key), native_labels=source["native_labels"] if source else None,
                   disposition=status[key], inference_status=inference(year, state))
        for field in STATISTICS:
            row[field] = (int(source[field]) if field in STATISTICS[:2] else source[field]) if selected else None
        rows.append(row)
    audit = dict(
        checked_private_partitions=len(partitions),
        positive_singleton_partitions_remaining=sum(
            sum(status.get(key) != "selected_broad_source_model" for key in members) == 1
            and any(status.get(key) == "selected_broad_source_model" for key in members)
            for members in partitions),
        both_weight_stage_masks_identical=all(
            (status[year, WEIGHTS[0], state, dimension, group] == "selected_broad_source_model")
            == (status[year, WEIGHTS[1], state, dimension, group] == "selected_broad_source_model")
            for year in YEARS for state in STATES
            for dimension, labels in groups(year).items() for group in labels),
    )
    if audit["positive_singleton_partitions_remaining"] or not audit["both_weight_stage_masks_identical"]:
        raise ValueError("Unresolved positive-cell complementary disclosure")
    return dict(schema="ap-state-demographics-v1", source_registered_frame_not_population=True,
        provenance=prior["provenance"], rows=rows,
        qualification=dict(
            native_source_aggregate_verification_reused_not_rerun=True,
            prior_public_overall_and_national_package_preserved=True,
            complementary_suppression_within_and_across_states=True,
            both_native_weight_stage_masks_synchronized=True,
            unknown_and_removed_codes_retained_only_in_full_denominators=True,
            no_raw_respondents_private_fine_cells_or_party_choice_tables=True,
            no_harmonization_or_cps_civic_projection=True,
            no_per_model_class_case_support_claim=True,
            support_threshold_not_precision_or_anonymity_guarantee=True,
            design_confidence_interval=None, registered_or_eligible_group_population=None,
            administrative_turnout_validation=False, source_weight_units_are_people=False),
        disclosure_audit=audit)


def build(snapshot):
    if set(snapshot) != {"schema", "source_registered_frame_not_population", "provenance",
                         "rows", "qualification", "disclosure_audit"}:
        raise ValueError("Unapproved fields in public sufficient input")
    for source in snapshot["provenance"]:
        if set(source) != {"year", "native_rows", "native_csv_sha256",
                           "verified_aggregate_sha256", "independent_native_checks"}:
            raise ValueError("Unapproved source provenance")
    if sorted(row["year"] for row in snapshot["provenance"]) != list(YEARS):
        raise ValueError("Incomplete original four-wave verification provenance")
    qualification = snapshot["qualification"]
    expected_true = {
        "native_source_aggregate_verification_reused_not_rerun",
        "prior_public_overall_and_national_package_preserved",
        "complementary_suppression_within_and_across_states",
        "both_native_weight_stage_masks_synchronized",
        "unknown_and_removed_codes_retained_only_in_full_denominators",
        "no_raw_respondents_private_fine_cells_or_party_choice_tables",
        "no_harmonization_or_cps_civic_projection", "no_per_model_class_case_support_claim",
        "support_threshold_not_precision_or_anonymity_guarantee",
    }
    if (snapshot["schema"] != "ap-state-demographics-v1"
            or snapshot["source_registered_frame_not_population"] is not True
            or any(qualification[field] is not True for field in expected_true)
            or any(qualification[field] is not None for field in (
                "design_confidence_interval", "registered_or_eligible_group_population"))
            or qualification["administrative_turnout_validation"] is not False
            or qualification["source_weight_units_are_people"] is not False):
        raise ValueError("Changed source, disclosure or population qualification")
    expected = {(year, weight, state, dimension, group)
                for year in YEARS for weight in WEIGHTS for state in STATES
                for dimension, labels in groups(year).items() for group in labels}
    seen, rows, selected_masks = set(), [], {}
    permitted_holds = {
        "no_dc_source_sample", "publisher_national_only_state_inference_withheld",
        "documented_dimension_absent_in_release", "unknown_or_disclosure_removed_not_exported_separately",
        "no_observed_source_group", "held_source_support_or_complementary_disclosure",
    }
    with localcontext() as context:
        context.prec = 80
        for source in snapshot["rows"]:
            key = tuple(source[field] for field in KEYS)
            if (set(source) != set(KEYS) | set(STATISTICS) | {"native_labels", "disposition", "inference_status"}
                    or key not in expected or key in seen):
                raise ValueError("Unexpected or duplicate complete state/group query")
            seen.add(key)
            year, weight, state, dimension, group = key
            if source["inference_status"] != inference(year, state):
                raise ValueError("Changed native state inference qualification")
            selected = source["disposition"] == "selected_broad_source_model"
            selected_masks[key] = selected
            row = dict(source)
            if selected:
                if (state == "DC" or year == "2022" and (state in {"DE", "WV"} or dimension == "RACETH5")
                        or group in {"88", "99"}):
                    raise ValueError("Absent, removed or withheld source group selected")
                if (type(source["n"]) is not int or type(source["positive_weight_n"]) is not int
                        or not 500 <= source["positive_weight_n"] <= source["n"]):
                    raise ValueError("Unsupported broad positive-weight source sample")
                if any(not isinstance(source[field], str) for field in MASSES):
                    raise ValueError("Exact source decimal strings required")
                masses = {field: Decimal(source[field]) for field in MASSES}
                if (any(not value.is_finite() or value < 0 for value in masses.values())
                        or masses["weight"] <= 0
                        or sum(masses[field] for field in MASSES[1:]) != masses["weight"]):
                    raise ValueError("Full source-group model denominator does not reconcile")
                row.update(
                    modeled_voter_pct=str(100 * masses["modeled_voter_weight"] / masses["weight"]),
                    modeled_nonvoter_pct=str(100 * masses["modeled_nonvoter_weight"] / masses["weight"]),
                    modeled_unknown_pct=str(100 * masses["model_unknown_weight"] / masses["weight"]))
            else:
                if (source["disposition"] not in permitted_holds
                        or any(source[field] is not None for field in STATISTICS)
                        or (state == "DC") != (source["disposition"] == "no_dc_source_sample")):
                    raise ValueError("Held-cell statistics must remain absent")
                row.update(modeled_voter_pct=None, modeled_nonvoter_pct=None, modeled_unknown_pct=None)
            row.update(
                source_registered_survey_frame=True, administratively_observed_turnout=False,
                design_confidence_interval=None, registered_or_eligible_group_population=None,
                source_weight_units_are_people=False, observed_staying_home=False,
                local_allocation=False, native_model_class_case_support_available=False,
                pollclose_and_final_not_independent_samples=True,
                cross_year_native_categories_harmonized=False)
            rows.append(row)
    if seen != expected:
        raise ValueError("Incomplete 51-jurisdiction four-wave query")
    if any(selected_masks[year, WEIGHTS[0], state, dimension, group]
           != selected_masks[year, WEIGHTS[1], state, dimension, group]
           for year in YEARS for state in STATES
           for dimension, labels in groups(year).items() for group in labels):
        raise ValueError("Different-stage mask can disclose the other stage's N")
    audit = snapshot["disclosure_audit"]
    if audit["positive_singleton_partitions_remaining"] != 0 or audit["both_weight_stage_masks_identical"] is not True:
        raise ValueError("Unresolved positive-cell complementary disclosure")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    summary = dict(schema=snapshot["schema"], source="AP/NORC VoteCast",
        years=list(YEARS), jurisdictions=51, native_source_states=50, dc_source_sample=False,
        complete_query_decisions=len(rows),
        selected_source_estimates=sum(row["disposition"] == "selected_broad_source_model" for row in rows),
        selected_nonoverall_estimates=sum(row["disposition"] == "selected_broad_source_model"
                                         and row["dimension"] != "overall" for row in rows),
        disposition_counts=dict(Counter(row["disposition"] for row in rows)),
        source_weight_units_are_people=False, administrative_turnout_validation=False,
        original_reductions_and_native_verification_reused=True,
        per_model_class_case_support_available=False, design_confidence_interval=None,
        native_categories_not_harmonized=True, no_new_website_view=True)
    return {"complete-state-demographic-query.csv": stream.getvalue().encode(),
            "summary.json": encoded(summary), "source-qualification.json": encoded(qualification)}


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    raw = (inputs / "selected-inputs.json").read_bytes()
    baseline = (inputs / "prior-complete-ap-analysis.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA or hashlib.sha256(baseline).hexdigest() != BASELINE_SHA:
        raise ValueError("Changed qualified sufficient inputs or prior complete release")
    files = build(json.loads(raw))
    for name in ("selected-inputs.json", "prior-complete-ap-analysis.zip", "original-verification.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    files["scripts/ap_state_groups.py"] = Path(__file__).read_bytes()
    files["tests/test_ap_state_groups.py"] = Path(__file__).parents[1].joinpath("tests/test_ap_state_groups.py").read_bytes()
    files["README.txt"] = (
        "Coarse historical state AP/NORC VoteCast model shares: 2018/2020/2022/2024.\n"
        "Registered survey source frames, NOT administrative demographic turnout.\n"
        "Poll-close/final state weights are separate views of the same sample, not independent samples.\n"
        "2018 state rows are descriptive: publisher reports 47 inference states despite all 50 sampled.\n"
        "2022 DE/WV state inference is held. RACETH5 was not released in 2022; no substitute crosswalk.\n"
        "D.C. has no source sample. Native age, SEX/GENDER, income and race labels are not harmonized.\n"
        "Positive-weight support minimum 500 is not a precision or anonymity guarantee.\n"
        "Per-model-class case counts are absent from the cached aggregates; none are claimed.\n"
        "Unknown/removed groups stay in full denominators, not recovered or redistributed.\n"
        "Positive-cell complementary holds apply within/across states and across weight-stage masks.\n"
        "Complete permitted selected aggregate inputs, all held-query decisions, prior full AP package,\n"
        "original native-verification provenance, maintained code, tests, results and checksums included.\n"
        "No raw respondents, private fine cells, party-choice tables, population counts or fake intervals.\n"
        "No cross-study/causal turnout trend, fixed cohort, observed staying home or local allocation.\n"
        "python3 -m unittest discover -s tests -p test_ap_state_groups.py\n"
        "python3 -m scripts.ap_state_groups --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                     for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
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
