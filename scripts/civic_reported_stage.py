"""Coarse native already-voted responses, not administrative turnout."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .extract_civic_reported_stage import LABELS, STAGES, supported


INPUT_SHA = "cc4ee3c532c50df2e6c3c83b615f40472c9cae7ffe40256a8c05d82b6f423888"
PUBLIC_PARENT_SHA = "625419f16e886ed4c7cb72992558ad62e31226b2c4a1e44e9e1c471b2d75863a"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def build_profiles(snapshot, public):
    if (snapshot["year"] != 2026 or snapshot["raw_source_rows"] != 113020
            or snapshot["source_states"] != 50 or snapshot["dc_present"] is not False
            or snapshot["field_period"] is not None or snapshot["weight_target_and_calibration"] is not None
            or snapshot["native_LVB_labels"] != LABELS or snapshot["already_voted_codes"] != ["5"]
            or snapshot["opaque_other_codes"] != ["1", "2", "3", "4", "99"]):
        raise ValueError("Keep native responses, unknown timing and unqualified source population separate")
    if not all(snapshot["qualification"].values()):
        raise ValueError("Changed source/disclosure/interpretation qualification")
    parents = {(r["state_code"], r["dimension"], r["group"]): r for r in public["groups"]
               if r["dimension"] in ("overall", "AGE6")}
    source = {(r["state_code"], r["dimension"], r["group"]): r for r in snapshot["profiles"]}
    if len(parents) != 306 or len(source) != len(snapshot["profiles"]) or set(source) != set(parents):
        raise ValueError("Incomplete or duplicate 306-profile query")
    profiles, cells, selected = [], [], {}
    for key, parent in parents.items():
        row = source[key]
        allowed = row["disposition"] == "selected_coarse_reported_stage"
        if set(row["stages"]) != set(STAGES):
            raise ValueError("Incomplete coarse stage inventory")
        values = None
        if allowed:
            values = {}
            for stage in STAGES:
                cell = row["stages"][stage]
                n, weight = cell["n"], Fraction(cell["weight"])
                if type(n) is not int or n < 0 or weight < 0 or bool(n) != bool(weight):
                    raise ValueError("Invalid observed stage count/weight; zero is not missing")
                values[stage] = dict(n=n, weight=weight)
            if not supported(parent, values):
                raise ValueError("Unsupported stage table or legacy marginal difference")
            selected[key] = values
        else:
            if row["disposition"] not in ("no_dc_source_sample", "held_source_support_or_complementary_disclosure"):
                raise ValueError("Unknown source holding")
            if ((key[0] == "DC") != (row["disposition"] == "no_dc_source_sample")
                    or any(v is not None for cell in row["stages"].values() for v in cell.values())):
                raise ValueError("Held stage counts and weights must remain absent")
        percentages = {stage: number(100 * values[stage]["weight"] / Fraction(parent["weight"])) if allowed else None
                       for stage in STAGES}
        profiles.append(dict(year=2026, state_code=key[0], dimension=key[1], group=key[2],
            label=parent["label"], source_parent_disposition=parent["disposition"],
            source_parent_n=parent["n"], source_parent_weight=parent["weight"],
            disposition=row["disposition"], already_voted_response_pct=percentages["already_voted"],
            other_or_unresolved_response_pct=percentages["other_or_unresolved"],
            field_period=None, weight_target_and_calibration=None,
            already_response_administratively_verified=False, other_is_nonvoter_class=False,
            observed_staying_home=None, population_count=None, design_confidence_interval=None,
            native_LVB_model_joint_inferred=False, local_probability_allocated=False))
        for stage in STAGES:
            cells.append(dict(year=2026, state_code=key[0], dimension=key[1], group=key[2],
                stage=stage, disposition=row["disposition"],
                source_stage_n=values[stage]["n"] if allowed else None,
                source_stage_weight=number(values[stage]["weight"]) if allowed else None,
                source_parent_n=parent["n"], source_parent_weight=parent["weight"],
                source_weighted_stage_pct=percentages[stage],
                native_codes="5" if stage == "already_voted" else "1|2|3|4|99",
                other_includes_future_intention_nonintention_unknown=stage == "other_or_unresolved",
                already_response_administratively_verified=False, other_is_nonvoter_class=False,
                field_period=None, design_confidence_interval=None, population_count=None))
    accounting = []
    for key, values in selected.items():
        accounting.append(dict(state_code=key[0], dimension=key[1], group=key[2], check="complete_source_parent",
            parent_n=parents[key]["n"], released_child_n=sum(v["n"] for v in values.values()),
            parent_weight=parents[key]["weight"], released_child_weight=number(sum(
                (v["weight"] for v in values.values()), Fraction(0))),
            positive_small_unreleased_residual=False, no_individual_model_joint_inferred=True))
    for state in sorted({key[0] for key in selected}):
        overall = state, "overall", "all"
        if overall not in selected:
            continue
        children = [key for key in selected if key[0] == state and key[1] == "AGE6"]
        remaining = {stage: selected[overall][stage]["n"] - sum(selected[key][stage]["n"] for key in children)
                     for stage in STAGES}
        total = sum(remaining.values())
        if any(value < 0 or 0 < value < 30 for value in remaining.values()) or 0 < total < 100:
            raise ValueError("Unsafe age complement; do not recover small held stages")
        accounting.append(dict(state_code=state, dimension="AGE6", group="unreleased_age_bundle",
            check="public_age_complement_support", parent_n=parents[overall]["n"],
            released_child_n=sum(sum(v["n"] for v in selected[key].values()) for key in children),
            parent_weight=parents[overall]["weight"], released_child_weight=None,
            positive_small_unreleased_residual=False, no_individual_model_joint_inferred=True))
    return profiles, cells, accounting


def build(inputs):
    raw = (inputs / "complete-reported-stage-sufficient-inputs.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError("Changed qualified public-safe source inputs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        sums = json.loads(archive.read("checksums.json"))
        if set(archive.namelist()) != set(sums) | {"checksums.json"}:
            raise ValueError("Changed complete input inventory")
        for name, metadata in sums.items():
            value = archive.read(name)
            if len(value) != metadata["bytes"] or hashlib.sha256(value).hexdigest() != metadata["sha256"]:
                raise ValueError("Changed sufficient factual input")
        parent_bytes = archive.read("public-civic-parents.json")
        if hashlib.sha256(parent_bytes).hexdigest() != PUBLIC_PARENT_SHA:
            raise ValueError("Changed accepted public source parents")
        snapshot, public = json.loads(archive.read("selected-stage-inputs.json")), json.loads(parent_bytes)
        profiles, stages, accounting = build_profiles(snapshot, public)
        preserved = archive.read("preserved-public-model-query.csv")
        access = archive.read("source-access-observations.json")
    selected = [r for r in profiles if r["disposition"] == "selected_coarse_reported_stage"]
    if (len(selected), sum(r["dimension"] == "overall" for r in selected),
            sum(r["dimension"] == "AGE6" for r in selected)) != (124, 46, 78):
        raise ValueError("Changed disclosure-qualified profile selection")
    summary = dict(complete_profile_decisions=306, complete_stage_cell_queries=612,
        supported_profiles=124, supported_overall_profiles=46, supported_age_profiles=78,
        supported_source_states=len({r["state_code"] for r in selected}), held_profiles=182,
        held_cell_statistics_not_recovered=True, prior1530_model_query_bytes_preserved=True,
        field_period=None, weight_target_and_calibration=None, pooled_stage_profile_published=False,
        already_response_administratively_verified=False, other_is_nonvoter_class=False,
        native_model_joint_inferred=False, new_website_view=False)
    qualification = dict(summary, source_csv_sha256=snapshot["source_csv_sha256"],
        codebook_sha256=snapshot["codebook_sha256"], qualification=snapshot["qualification"],
        prior_responses_all_aggregated_without_party_selection=True,
        source_already_voted_category="LVB5", other_native_codes=["1", "2", "3", "4", "99"],
        no_early_vote_curve_or_common_interview_cutoff=True, no_native_response1_2_3_4_99_masses_published=True,
        no_source_stage_model_individual_crossclassification_inferred=True,
        no_new_acquisition_or_original_raw_survey_reduction=True,
        private_fine_rows_identifiers_and_denied_app_bodies_excluded=True,
        existing_native28_age_transport_models_releases_stopped_routes_and_website_unchanged=True)
    return {"complete-reported-stage-profile-query.csv": csv_bytes(profiles),
        "complete-reported-stage-cell-query.csv": csv_bytes(stages),
        "complete-reported-stage-accounting.csv": csv_bytes(accounting),
        "preserved-public-model-query.csv": preserved,
        "source-access-observations.json": access,
        "source-qualification.json": encoded(qualification), "summary.json": encoded(summary)}


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    files = build(inputs)
    name = "complete-reported-stage-sufficient-inputs.zip"
    files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("civic_reported_stage.py", "extract_civic_reported_stage.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_civic_reported_stage.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "2026 native LVB5 Already voted response profiles, NOTadministrative turnout or a common-date early-vote curve.\n"
        "306 complete profile decisions/612stage cells:124profiles(46overall78age) across49source states;182holds.\n"
        "Other/unresolved includes native1/2FUTUREintention,3/4nonintention,99unknown; it is NOTnonvoting/stayinghome.\n"
        "Unknowns remain in full source denominators. No separate native1/2/3/4/99 masses or pooled/national profile.\n"
        "Old public-parent masks, n100parent/n30positivecell, legacy-marginal difference and age-complement guards.\n"
        "Whole held tables have NULLstage counts/weights. Parent statistics were already public; no fine cells recovered.\n"
        "All prior2024response categories summed; no party fitting or prior-voter cohort restriction.\n"
        "Field period/calibration unqualified; reported stage is not verified voting, legal eligibility or population count.\n"
        "No native LVB/model individual joint inferred, raw respondent identifiers/private fine rows or local allocation.\n"
        "Reuses verified held reduction, not original survey acquisition/reduction. All1530 oldmodel querybytes preserved.\n"
        "OHprimaryrelease/IAresultsindex returned403 and remainstopped; no cached count or denied body used/published.\n"
        "Complete safe numeric primitives, publicparents/masks, definitions, standard-librarycode/tests/everyquery/result.\n"
        "python3 -m unittest discover -s tests -p test_civic_reported_stage.py\n"
        "python3 -m scripts.civic_reported_stage --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
        for name, value in sorted(files.items())})
    output.mkdir(parents=True)
    for name, value in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
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
