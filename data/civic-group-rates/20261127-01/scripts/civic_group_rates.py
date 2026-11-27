"""Release rounded broad-group model rates, never new counts or weight primitives."""

import argparse
from collections import defaultdict
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile

from scripts.fit_norc_house_model import CHEP_SHA, DEMOGRAPHICS, group_for, native


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def aggregate(records):
    cells = defaultdict(lambda: [0, 0, Decimal(0), Decimal(0)])
    cases, states = 0, set()
    for row in records:
        weight = Decimal(row["CHEP_WEIGHT"])
        outcome = native(row["LIKELYVOTER"])
        if not weight.is_finite() or weight <= 0 or outcome not in (1, 2):
            raise ValueError("Keep the qualified positive-weight binary native model")
        normalized = {key: "unknown" if native(row[key]) in (77, 88, 98, 99)
                      else str(native(row[key])) for key in DEMOGRAPHICS}
        groups = [("overall", "all")] + [(key, group_for(normalized, key)) for key in DEMOGRAPHICS]
        for dimension, group in groups:
            cell = cells[row["P_STATE"], dimension, group]
            cell[0] += 1
            cell[1] += outcome == 1
            cell[2] += weight
            cell[3] += weight if outcome == 1 else 0
        states.add(row["P_STATE"])
        cases += 1
    return cells, cases, states


def build(cells, reference):
    output, recovered = [], 0
    with localcontext() as context:
        context.prec = 80
        for prior in reference["groups"]:
            code, dimension, group = (prior[key] for key in ("state_code", "dimension", "group"))
            n, voters, weight, voter_weight = cells.get((code, dimension, group), (0, 0, Decimal(0), Decimal(0)))
            eligible = (code != "DC" and dimension != "GENDER3" and group != "unknown"
                        and n >= 100 and min(voters, n - voters) >= 30)
            rate = None
            if eligible:
                exact = 100 * voter_weight / weight
                if prior["modeled_voter_pct"] is not None and (
                        n != prior["n"] or abs(exact - Decimal(prior["modeled_voter_pct"])) > Decimal("1e-20")):
                    raise ValueError("A previously published native group no longer reconciles")
                rate = exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                recovered += prior["modeled_voter_pct"] is None
            elif prior["modeled_voter_pct"] is not None:
                raise ValueError("A previously supported group disappeared")
            output.append(dict(year=2026, state_code=code, dimension=dimension, group=group, label=prior["label"],
                disposition="selected_broad_source_model" if eligible else "no_dc_source_sample" if code == "DC"
                else "held_cross_dimension_disclosure" if dimension == "GENDER3"
                else "held_source_support_or_complementary_disclosure",
                modeled_voter_pct=str(rate) if eligible else None,
                modeled_nonvoter_pct=str(Decimal(100) - rate) if eligible else None,
                n=None, source_weight_concentration_effective_n=None,
                population_representativeness_qualified=False, administratively_observed_turnout=False,
                design_confidence_interval=None, eligible_or_registered_group_population=None,
                estimated_group_participants=None, measured_staying_home=None, local_allocation=False))
    return dict(schema="civic-state-demographics-v2", year=2026,
        status="source_weighted_modeled_participation_not_observed_turnout",
        source_csv_sha256=CHEP_SHA, codebook_sha256=reference["codebook_sha256"],
        field_period=None, weight_target_and_calibration=None,
        publication=dict(format="rounded_rates_without_new_count_or_weight_primitives", resolution_pp="0.1",
            minimum_source_cases=100, minimum_each_model_class=30,
            new_subgroup_counts_or_weights_exported=False, standalone_unknown_categories_released=False,
            gender3_released=False, old_exact_disclosure_exports_unchanged=True),
        groups=output, newly_supported_rate_only_groups=recovered,
        notes=["The native LIKELYVOTER classes are modeled, not completed voting or confirmed staying home.",
               "Each percentage uses all CHEP source weight within its own group, not all voters or the population.",
               "All rates are rounded to 0.1 percentage point; no new subgroup counts or weight primitives are released.",
               "Broad groups need at least 100 source records and 30 in each native model class.",
               "Standalone unknown categories, GENDER3, small groups and D.C. remain unavailable.",
               "A rounded rate is not a new confidence interval, population validation or local allocation."])


def export(source, reference_path, output):
    if output.exists():
        raise ValueError("Use a fresh destination; do not overwrite an existing scientific product")
    if hashlib.sha256(source.read_bytes()).hexdigest() != CHEP_SHA:
        raise ValueError("Use the exact supplied, qualified source; do not substitute a newer-looking file")
    reference = json.loads(reference_path.read_bytes())
    if reference.get("schema") != "civic-state-demographics-v1" or len(reference["groups"]) != 1530:
        raise ValueError("The complete original public query is required")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        cells, cases, states = aggregate(csv.DictReader(stream))
    if cases != 113020 or len(states) != 50 or "DC" in states:
        raise ValueError("Changed supplied source coverage")
    result = build(cells, reference)
    rows = result["groups"]
    summary = dict(source_cases=cases, source_states=len(states), complete_queries=len(rows),
        supported_rates=sum(row["modeled_voter_pct"] is not None for row in rows),
        newly_supported_rate_only_groups=result["newly_supported_rate_only_groups"],
        resolution_pp="0.1", new_subgroup_counts_or_weights_exported=False,
        source_sha256=CHEP_SHA, observed_turnout=False)
    csv_stream = io.StringIO(newline="")
    writer = csv.DictWriter(csv_stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    root = Path(__file__).parents[1]
    files = {"viewer-data.json": encoded(result), "summary.json": encoded(summary),
        "complete-state-demographic-query.csv": csv_stream.getvalue().encode(),
        "inputs/previous-public-query.json": reference_path.read_bytes(),
        **{name: (root / name).read_bytes() for name in (
            "scripts/civic_group_rates.py", "scripts/verify_civic_group_rates.py", "scripts/fit_norc_house_model.py",
            "tests/test_civic_group_rates.py")},
        "README.txt": ("Rounded native 2026 LIKELYVOTER shares; not observed completed turnout.\n"
            "All 1,530 queries, including unavailable categories; no new subgroup counts or weights.\n"
            "Original private respondent data are deliberately not redistributed.\n"
            "To independently repeat the source reduction, use the user-supplied civichealth_datafile.csv\n"
            "with SHA256 " + CHEP_SHA + ". No other file is silently substituted.\n"
            "python3 -m scripts.civic_group_rates --source /private/civichealth_datafile.csv "
            "--reference inputs/previous-public-query.json --output reproduced\n"
            "python3 -m scripts.verify_civic_group_rates --source /private/civichealth_datafile.csv --product reproduced\n"
            "python3 -m unittest discover -s tests -p test_civic_group_rates.py\n").encode()}
    files["checksums.json"] = encoded({name: dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                                     for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        path = output / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w") as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16; archive.writestr(info, body)
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.source, args.reference, args.output)
