"""Public coarse 2026 Civic model shares, not observed demographic turnout."""

import argparse
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile


INPUT_SHA = "625419f16e886ed4c7cb72992558ad62e31226b2c4a1e44e9e1c471b2d75863a"
STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
GROUPS = {
    "overall": ("all",),
    "AGE6": ("18_29", "30_49", "50_64", "65_plus", "unknown"),
    "EDUC": ("high_school_or_less", "some_college", "college_postgraduate", "unknown"),
    "SEX": ("male", "female", "unknown"),
    "GENDER3": ("male", "female", "other_unknown"),
    "RACETH5": ("white", "black", "hispanic", "asian_pacific", "other_unknown"),
    "INCOME": ("under_25000", "25000_49999", "50000_74999", "75000_99999", "100000_plus", "unknown"),
    "RUCC": ("urban_county", "suburban_county", "rural_county"),
}
WEIGHTS = ("weight", "weight_squared", "modeled_voter_weight", "modeled_nonvoter_weight")
FLAGS = ("population_representativeness_qualified", "administratively_observed_turnout",
         "original_cohort_population", "local_allocation")
UNAVAILABLE = ("design_confidence_interval", "eligible_or_registered_group_population")
ROW_FIELDS = {"year", "state_code", "dimension", "group", "label", "disposition",
              "n", *WEIGHTS, "native_model_voter_cases", "native_model_nonvoter_cases", *FLAGS, *UNAVAILABLE}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def decimal(value):
    if not isinstance(value, str):
        raise ValueError("Use exact source decimal strings, not rounded numeric inputs")
    amount = Decimal(value)
    if not amount.is_finite():
        raise ValueError("Nonfinite source weight")
    return amount


def build(snapshot):
    if (snapshot["status"] != "coarse_source_weighted_2026_model_not_observed_turnout"
            or snapshot["year"] != 2026 or snapshot["states_present"] != 50
            or snapshot["dc_present"] is not False or snapshot["raw_source_rows"] != 113020
            or snapshot["field_period"] is not None or snapshot["weight_target_and_calibration"] is not None):
        raise ValueError("Unqualified source frame or population certification")
    qualification = snapshot["qualification"]
    for key in ("complementary_suppression", "no_private_fine_cells_raw_records_or_candidate_choice_tables",
                "cross_state_complementary_suppression_preserves_prior_pooled_aggregates",
                "native_race_code_88_never_exported_separately",
                "native_GENDER3_withheld_to_avoid_small_category_and_cross_sex_difference_disclosure",
                "unknown_demographics_retained_in_overall_denominator",
                "no_CPS_category_harmonization_or_2024_to_2026_projection"):
        if qualification[key] is not True:
            raise ValueError("Changed disclosure or source-category qualification")
    expected = {(state, dimension, group) for state in STATES
                for dimension, groups in GROUPS.items() for group in groups}
    identities, rows = set(), []
    with localcontext() as context:
        context.prec = 80
        for source in snapshot["groups"]:
            key = source["state_code"], source["dimension"], source["group"]
            if set(source) != ROW_FIELDS or key not in expected or key in identities or source["year"] != 2026:
                raise ValueError("Unexpected or duplicate public state group")
            identities.add(key)
            if any(source[key] is not False for key in FLAGS) or any(source[key] is not None for key in UNAVAILABLE):
                raise ValueError("Observed turnout, confidence interval or population fabrication")
            selected = source["disposition"] == "selected_broad_source_model"
            row = {key: source[key] for key in ("year", "state_code", "dimension", "group", "label", "disposition", "n")}
            if selected:
                if source["state_code"] == "DC" or source["dimension"] == "GENDER3" or source["group"] == "unknown":
                    raise ValueError("Absent D.C. or private unknown-category estimate")
                voter_n, nonvoter_n = source["native_model_voter_cases"], source["native_model_nonvoter_cases"]
                if (type(source["n"]) is not int or source["n"] < 100
                        or any(type(value) is not int or value < 30 for value in (voter_n, nonvoter_n))
                        or voter_n + nonvoter_n != source["n"]):
                    raise ValueError("Unsupported source/model-class sample")
                weight, squared, voter, nonvoter = (decimal(source[key]) for key in WEIGHTS)
                if min(weight, squared) <= 0 or min(voter, nonvoter) < 0 or voter + nonvoter != weight:
                    raise ValueError("Full source-group denominator does not reconcile")
                if weight * weight / squared > source["n"] + Decimal("1e-20"):
                    raise ValueError("Weight concentration exceeds the source case count")
                row.update(
                    modeled_voter_pct=str(100 * voter / weight),
                    modeled_nonvoter_pct=str(100 * nonvoter / weight),
                    source_weight_concentration_effective_n=str(weight * weight / squared))
            else:
                if source["disposition"] not in {
                        "no_dc_source_sample", "held_source_support_or_complementary_disclosure",
                        "held_cross_dimension_disclosure"}:
                    raise ValueError("Unknown source holding")
                if ((source["state_code"] == "DC") != (source["disposition"] == "no_dc_source_sample")
                        or source["state_code"] != "DC" and (
                            (source["dimension"] == "GENDER3") !=
                            (source["disposition"] == "held_cross_dimension_disclosure"))
                        or any(source[key] is not None for key in ("n", *WEIGHTS,
                            "native_model_voter_cases", "native_model_nonvoter_cases"))):
                    raise ValueError("Private held-cell statistics must remain absent")
                row.update(modeled_voter_pct=None, modeled_nonvoter_pct=None,
                           source_weight_concentration_effective_n=None)
            row.update(
                population_representativeness_qualified=False, administratively_observed_turnout=False,
                design_confidence_interval=None, eligible_or_registered_group_population=None,
                estimated_group_participants=None, measured_staying_home=None, local_allocation=False)
            rows.append(row)
    if identities != expected:
        raise ValueError("Incomplete 51-jurisdiction public query")
    if sum(row["dimension"] == "overall" and row["modeled_voter_pct"] is not None for row in rows) != 50:
        raise ValueError("Missing source statewide model")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    result = dict(
        schema="civic-state-demographics-v1", year=2026,
        status="source_weighted_modeled_participation_not_observed_turnout",
        source_csv_sha256=snapshot["original_csv_sha256"], codebook_sha256=snapshot["codebook_sha256"],
        field_period=None, weight_target_and_calibration=None, qualification=qualification,
        groups=rows, notes=snapshot["notes"])
    summary = dict(year=2026, jurisdictions=51, survey_states=50, dc_sample=False,
                   complete_group_queries=len(rows),
                   selected_source_estimates=sum(row["modeled_voter_pct"] is not None for row in rows),
                   held_queries=sum(row["modeled_voter_pct"] is None for row in rows),
                   source_weight_units_are_people=False, administrative_turnout_validation=False,
                   notes=snapshot["notes"])
    return {
        "complete-state-demographic-query.csv": stream.getvalue().encode(),
        "viewer-data.json": encoded(result), "summary.json": encoded(summary),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite an existing public analysis")
    raw = (inputs / "selected-inputs.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError("Changed qualified public sufficient inputs")
    files = build(json.loads(raw))
    files["inputs/selected-inputs.json"] = raw
    files["inputs/public-accounting-checks.json"] = (inputs / "public-accounting-checks.json").read_bytes()
    files["scripts/civic_state_groups.py"] = Path(__file__).read_bytes()
    files["tests/test_civic_state_groups.py"] = Path(__file__).parents[1].joinpath("tests/test_civic_state_groups.py").read_bytes()
    files["README.txt"] = (
        "2026 source-weighted Civic model shares, not observed demographic turnout.\n"
        "All 51 jurisdictions and complete group-query decisions; D.C. has no sample.\n"
        "Complete permitted sufficient inputs, queries, code and tests included.\n"
        "Unknowns stay in the statewide frame; private sparse and complementary groups are held.\n"
        "python3 -m unittest discover -s tests -p test_civic_state_groups.py\n"
        "python3 -m scripts.civic_state_groups --inputs inputs --output reproduced\n"
    ).encode()
    files["checksums.json"] = encoded({
        name: dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        for name, content in sorted(files.items())})
    output.mkdir(parents=True)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps(json.loads(files["summary.json"]), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
