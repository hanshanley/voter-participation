"""Source classifications, not prior nonvoting, new voters or observed 2026 turnout."""

import argparse
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .extract_civic_history_classifications import PRIOR, CURRENT


STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
YEARS = (2022, 2024)
INPUT_SHA = "df455b054db8c6a21cf5388c693a640c21d3d49cf13a34a9027c7d74e91d9278"


def number(value):
    with localcontext() as context:
        context.prec = 80
        return str(Decimal(value.numerator) / value.denominator)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def select(tables, parents):
    if set(tables) != {(year, state) for year in YEARS for state in STATES if state != "DC"}:
        raise ValueError("Incomplete native current-state/retrospective-contest inventory")
    if set(parents) != set(STATES) - {"DC"}:
        raise ValueError("Changed complete accepted current source parents")
    selected, reason = {}, {}
    for year in YEARS:
        for state in STATES:
            identity = year, state
            if state == "DC":
                if identity in tables or state in parents:
                    raise ValueError("No D.C. source sample may be fabricated")
                selected[identity], reason[identity] = False, "no_dc_source_sample"
                continue
            table, parent = tables[identity], parents[state]
            if set(table) != {(p, c) for p in PRIOR for c in CURRENT}:
                raise ValueError("Incomplete coarse native table")
            if (sum(cell[0] for cell in table.values()) != parent["n"]
                    or sum((cell[1] for cell in table.values()), Fraction(0)) != Fraction(parent["weight"])):
                raise ValueError("Coarse table differs from accepted full current source frame")
            for destination, field in zip(CURRENT, ("modeled_voter_weight", "modeled_nonvoter_weight")):
                if sum((table[p, destination][1] for p in PRIOR), Fraction(0)) != Fraction(parent[field]):
                    raise ValueError("Current model class differs from accepted public parent")
            for n, weight in table.values():
                if n < 0 or weight < 0 or (n == 0) != (weight == 0):
                    raise ValueError("Invalid native case or weight; no imputation")
            supported = parent["n"] >= 100 and all(n == 0 or n >= 30 for n, _ in table.values())
            selected[identity] = supported
            reason[identity] = "selected_coarse_source_classification" if supported else "held_support_or_complementary_disclosure"
    for year in YEARS:
        held = [state for state in STATES if state != "DC" and not selected[year, state]]
        candidates = [state for state in STATES if state != "DC" and selected[year, state]]
        if len(held) == 1 and candidates:
            extra = max(candidates, key=lambda state: (parents[state]["n"], state))
            selected[year, extra] = False
            reason[year, extra] = "held_support_or_complementary_disclosure"
    return [dict(prior_year=year, current_year=2026, state_code=state,
        prior_office="house" if year == 2022 else "president", current_office="house",
        disposition=reason[year, state], source_n=parents[state]["n"] if selected[year, state] else None,
        cells=[dict(prior_block=p, current_model_class=c, n=tables[year, state][p, c][0],
                    weight=number(tables[year, state][p, c][1])) for p in PRIOR for c in CURRENT]
              if selected[year, state] else None)
        for year in YEARS for state in STATES]


def build(snapshot):
    if (snapshot["year"] != 2026 or snapshot["dc_sample"] is not False
            or snapshot["minimum_parent_n"] != 100 or snapshot["minimum_positive_coarse_cell_n"] != 30
            or snapshot["other_prior_block_is_not_inferred_nonvoting"] is not True):
        raise ValueError("Changed source frame, disclosure policy or unresolved response meaning")
    frames = snapshot["frames"]
    if {(f["prior_year"], f["state_code"]) for f in frames} != {(y, s) for y in YEARS for s in STATES} or len(frames) != 102:
        raise ValueError("Incomplete or duplicated jurisdiction/contest query")
    parents = {row["scope"]: row for row in snapshot["public_current_parents"]}
    if set(parents) != set(STATES) - {"DC"}:
        raise ValueError("Changed complete accepted current source parents")
    decisions, cells, rates, checks = [], [], [], []
    for frame in frames:
        year, state = frame["prior_year"], frame["state_code"]
        if (frame["current_year"] != 2026 or frame["current_office"] != "house"
                or frame["prior_office"] != ("house" if year == 2022 else "president")):
            raise ValueError("Do not harmonize different retrospective offices or years")
        supported = frame["disposition"] == "selected_coarse_source_classification"
        if not supported:
            if frame["source_n"] is not None or frame["cells"] is not None:
                raise ValueError("Held private statistics must remain NULL")
            if (state == "DC") != (frame["disposition"] == "no_dc_source_sample"):
                raise ValueError("Changed sample-absence/support disposition")
        else:
            if state == "DC" or type(frame["source_n"]) is not int or frame["source_n"] < 100:
                raise ValueError("Unsupported or absent source table")
            table = {(row["prior_block"], row["current_model_class"]): row for row in frame["cells"]}
            if len(frame["cells"]) != 4 or set(table) != {(p, c) for p in PRIOR for c in CURRENT}:
                raise ValueError("Incomplete coarse source cells")
            for row in table.values():
                if type(row["n"]) is not int or (0 < row["n"] < 30) or row["n"] < 0:
                    raise ValueError("Sparse positive cell must remain held")
                weight = Fraction(row["weight"])
                if weight < 0 or (row["n"] == 0) != (weight == 0):
                    raise ValueError("Changed genuine zero/unknown distinction")
            parent = parents[state]
            if sum(row["n"] for row in table.values()) != frame["source_n"] or frame["source_n"] != parent["n"]:
                raise ValueError("Native source case partition changed")
            if sum((Fraction(row["weight"]) for row in table.values()), Fraction(0)) != Fraction(parent["weight"]):
                raise ValueError("Native source weight partition changed")
            for c, field in zip(CURRENT, ("modeled_voter_weight", "modeled_nonvoter_weight")):
                if sum((Fraction(table[p, c]["weight"]) for p in PRIOR), Fraction(0)) != Fraction(parent[field]):
                    raise ValueError("Accepted current model parent changed")
        identity = {field: frame[field] for field in ("prior_year", "current_year", "state_code", "prior_office", "current_office")}
        identity["state_scope"] = "current_2026_source_state_not_verified_prior_residence"
        decisions.append(dict(**identity, disposition=frame["disposition"], source_n=frame["source_n"],
            field_period=None, weight_target_and_calibration=None, recalled_responses_are_prior_population=False,
            other_prior_block_is_not_inferred_nonvoting=True, original_cohort_population_validated=False))
        for p in PRIOR:
            denominator = sum((Fraction(table[p, c]["weight"]) for c in CURRENT), Fraction(0)) if supported else None
            yes = Fraction(table[p, CURRENT[0]]["weight"]) if supported else None
            rates.append(dict(**identity, prior_block=p, disposition=frame["disposition"],
                source_block_n=sum(table[p, c]["n"] for c in CURRENT) if supported else None,
                source_block_weight=number(denominator) if supported else None,
                conditional_modeled_participant_pct=number(100 * yes / denominator) if denominator else None,
                explicit_prior_nonvote_weight=None, unknown_prior_response_weight=None,
                source_weights_are_people=False, source_registration_or_eligibility_validated=False,
                new_or_returning_voter_population=None, observed_staying_home=None, design_confidence_interval=None))
            for c in CURRENT:
                row = table[p, c] if supported else None
                cells.append(dict(**identity, prior_block=p, current_model_class=c, disposition=frame["disposition"],
                    n=row["n"] if supported else None, source_weight=row["weight"] if supported else None,
                    pct_of_full_current_source_frame=number(100 * Fraction(row["weight"]) / Fraction(parents[state]["weight"])) if supported else None,
                    pct_within_prior_response_block=number(100 * Fraction(row["weight"]) / denominator) if denominator else None,
                    source_weight_units_not_people=True, current_model_not_reported_cast_ballots=True,
                    prior_nonvote_or_unknown_not_separately_identified=True, local_or_group_population_allocation=False))
        if state != "DC":
            checks.append(dict(prior_year=year, state_code=state, **{key: parents[state][key] for key in
                ("n", "weight", "modeled_voter_weight", "modeled_nonvoter_weight")},
                private_coarsening_matches_accepted_public_parent=True,
                current_source_model_reestimated=False))
    for year in YEARS:
        held = [frame for frame in frames if frame["prior_year"] == year and frame["state_code"] != "DC"
                and frame["disposition"] != "selected_coarse_source_classification"]
        if len(held) == 1:
            raise ValueError("Single positive state hold would expose a complementary table")
    return {
        "complete-classification-decisions.csv": csv_bytes(decisions),
        "complete-nonpartisan-classification-cells.csv": csv_bytes(cells),
        "complete-conditional-source-model-rates.csv": csv_bytes(rates),
        "complete-current-parent-preservation.csv": csv_bytes(checks),
        "source-qualification.json": encoded(dict(
            two_retrospective_contests_not_prior_population_or_original_cohort=True,
            no_prior_state_residence_or_historical_population_frame_imputed=True,
            other_candidate_choice_included_in_recalled_choice_block=True,
            explicit_nonvote_and_unknown_retained_together_as_opaque_other_response_not_recoded_as_nonvoters=True,
            no_unknown_mass_or_prior_nonvote_mass_individually_disclosed_or_imputed=True,
            current_candidate_choice_unknown_preserved_as_model_participant_when_native_model_class_is_voter=True,
            source_frame_and_calibration_qualification_unknown=True,
            no_new_returning_voters_staying_home_eligibility_deaths_migration_population_counts_or_fake_intervals=True,
            no_private_fine_cells_raw_records_or_party_choice_tables_redistributed=True,
            native_current27_all_prior_models_releases_stopped_routes_and_website_unchanged=True,
            new_York_HomeNoJS_actual403_route_stopped_no_cached_count_promotion=True)),
        "summary.json": encoded(dict(current_year=2026, prior_years=list(YEARS), jurisdictions=51, survey_states=50,
            complete_classification_decisions=102, complete_cell_queries=408, complete_conditional_rate_queries=204,
            selected_tables=sum(f["disposition"] == "selected_coarse_source_classification" for f in frames),
            held_tables=sum(f["disposition"] != "selected_coarse_source_classification" for f in frames),
            prior2022_selected_tables=sum(f["prior_year"] == 2022 and f["disposition"] == "selected_coarse_source_classification" for f in frames),
            prior2024_selected_tables=sum(f["prior_year"] == 2024 and f["disposition"] == "selected_coarse_source_classification" for f in frames),
            parent_preservation_rows=100, no_original_reduction_or_current_model_campaign_rerun=True,
            no_observed_turnout_or_new_website_view=True)),
    }


def export(inputs, output):
    if output.exists():
        raise ValueError("Do not overwrite a completed analysis")
    raw = (inputs / "selected-classification-inputs.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA:
        raise ValueError("Changed qualified sufficient public classifications")
    manifest = json.loads((inputs / "checksums.json").read_bytes())
    if set(manifest) != {"selected-classification-inputs.json", "source-access-observations.json"}:
        raise ValueError("Changed sufficient input inventory")
    for name, metadata in manifest.items():
        body = (inputs / name).read_bytes()
        if len(body) != metadata["bytes"] or hashlib.sha256(body).hexdigest() != metadata["sha256"]:
            raise ValueError("Changed sufficient input bytes")
    files = build(json.loads(raw))
    for name in (*manifest, "checksums.json"):
        files["inputs/" + name] = (inputs / name).read_bytes()
    for name in ("civic_history_classifications.py", "extract_civic_history_classifications.py"):
        files["scripts/" + name] = Path(__file__).with_name(name).read_bytes()
    name = "tests/test_civic_history_classifications.py"
    files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Nonpartisan retrospective-choice classifications vs2026native participation model, not observed turnout.\n"
        "2022House/2024President recalled candidate choice includesOthercandidate; opaque other/unresolved\n"
        "contains explicit no-prior-contest-vote AND unknown responses, NOTinferred prior nonvoters/newvoters.\n"
        "Unknown current candidate choice remains modelparticipant when native model saysvoter.\n"
        "n>=100 and every positive coarse cell>=30; completeholds NULL, genuine sourcezeros remainzero.\n"
        "All50acceptedcurrent parents preserved, D.C.absent, complementary stateholds respected.\n"
        "No original-private-reduction rerun, partychoice/finecells/rawrespondents/populationallocation/fakeCI.\n"
        "NYHomeNoJS403 stopped: no cached search count, client/cache/mirror or bypass.\n"
        "All permitted sufficient inputs, code, tests, completequeries/results/checksums are included.\n"
        "python3 -m unittest discover -s tests -p test_civic_history_classifications.py\n"
        "python3 -m scripts.civic_history_classifications --inputs inputs --output reproduced\n").encode()
    files["checksums.json"] = encoded({name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
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
