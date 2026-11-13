"""Summarize already-published model variants without refitting or identifying flows."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics


PROFILES = ("original", "attenuated", "full")
FAMILIES = ("accepted_ridge_multinomial", "histogram_gradient_boosting", "extra_randomized_trees")
METRICS = ("switching", "exit", "entry", "modeled_nonparticipation",
    "other_choice", "unresolved", "total", "retaining")
STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), allow_nan=False)+"\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def values(row, group=None):
    point = row["point"] if group is None else group
    contributions = point["contributions_pp"]
    result = {key: contributions[key] for key in
        ("switching", "exit", "entry", "other_choice", "unresolved")}
    result["modeled_nonparticipation"] = point["net_participation_pp"]
    result["total"] = point["total_change_pp"] if group is None else point["total_contribution_pp"]
    gross = row.get("gross_outcomes") if group is None else group.get("gross_outcomes")
    result["retaining"] = gross.get("retaining") if gross else None
    return result


def summarize(models, source_pins):
    if set(models) != set(PROFILES) or set(source_pins) != set(PROFILES):
        raise ValueError("All three pinned association profiles are required")
    variants = []
    for profile in PROFILES:
        data = models[profile]
        if (data.get("contract") != "participation.house_model_families.v1"
                or set(data.get("families", {})) != set(FAMILIES)):
            raise ValueError("The complete three-family aggregate product is required")
        for family in FAMILIES:
            model = data["families"][family]
            rows = {row["state_code"]: row for row in model["rows"]}
            if len(model["rows"]) != 50 or set(rows) != STATES:
                raise ValueError("Every variant must retain all 50 distinct state decisions")
            if (model.get("model_units_are_people") is not False
                    or model.get("current_party_totals_used_in_source_model_training") is not False):
                raise ValueError("Source-model population and training qualifications changed")
            variants.append((profile+"|"+family, rows))
    baseline = variants[0][1]
    output, witness = [], []
    for code in sorted(STATES):
        original = baseline[code]
        qualified = original["source_comparison_available"]
        if type(qualified) is not bool:
            raise ValueError("State qualification must remain explicit")
        groups = {item["dimension"]+"|"+item["group"]: item for item in original["groups"]}
        if len(groups) != len(original["groups"]):
            raise ValueError("Duplicate demographic source identities")
        grouped_variants = {}
        for identifier, rows in variants:
            row = rows[code]
            other = {item["dimension"]+"|"+item["group"]: item for item in row["groups"]}
            if (row["source_comparison_available"] is not qualified
                    or row["reported_comparison"] != original["reported_comparison"]
                    or set(other) != set(groups)
                    or len(other) != len(row["groups"])):
                raise ValueError("Variant source endpoints, qualifications or groups disagree")
            if any(type(other[key]["available"]) is not bool
                    or other[key]["available"] is not groups[key]["available"] for key in groups):
                raise ValueError("Variant demographic disclosure masks disagree")
            grouped_variants[identifier] = other
        scopes = {}
        for key in ("", *sorted(groups)):
            supported = qualified and (not key or groups[key]["available"])
            reason = None if supported else (
                original["reported_comparison"].get("reason") if not qualified
                else groups[key].get("reason") or "Source demographic group is withheld")
            metrics = {metric: None for metric in METRICS}
            matrix = {identifier: {metric: None for metric in METRICS} for identifier, _ in variants}
            if supported:
                matrix = {identifier: values(rows[code], grouped_variants[identifier][key] if key else None)
                    for identifier, rows in variants}
                for metric in METRICS:
                    entries = [matrix[identifier][metric] for identifier, _ in variants]
                    if all(finite(value) for value in entries):
                        metrics[metric] = dict(minimum=min(entries), maximum=max(entries),
                            default=entries[0], variants=9)
            for metric in METRICS:
                for identifier, _ in variants:
                    value = matrix[identifier][metric]
                    available = supported and finite(value)
                    witness.append(dict(state_code=code, group=key, metric=metric,
                        variant=identifier, available=available,
                        value_json=json.dumps(value if available else None, allow_nan=False),
                        reason=reason if not supported else None if available else "Metric unavailable"))
            scopes[key] = dict(available=supported, reason=reason, metrics=metrics)
        comparison = original["reported_comparison"]
        output.append(dict(state_code=code, qualified=qualified,
            reason=None if qualified else comparison.get("reason"),
            endpoint=dict(snapshot=comparison.get("current_snapshot"),
                native_clock=comparison.get("current_native_clock"),
                counting_complete_independently_qualified=comparison.get(
                    "current_counting_complete_independently_qualified"),
                source_coverage_certified=comparison.get("source_coverage_certified")),
            scopes=scopes))
    widths = {metric: [row["scopes"][""]["metrics"][metric]["maximum"]
        - row["scopes"][""]["metrics"][metric]["minimum"] for row in output
        if row["qualified"] and row["scopes"][""]["metrics"][metric] is not None]
        for metric in ("switching", "modeled_nonparticipation", "entry", "other_choice")}
    result = dict(contract="participation.house_model_sensitivity.v1",
        source_pins=source_pins, profiles=list(PROFILES), families=list(FAMILIES),
        default_variant=variants[0][0], variant_count=9,
        contribution_units="statewide_D_minus_R_margin_percentage_points",
        retaining_units="fraction_of_model_assigned_prior_DR_mass",
        group_ranges_are_not_group_vote_shares=True, confidence_intervals=None,
        not_all_model_survey_transport_or_endpoint_uncertainty=True,
        source_fits_reproduced=False, fitted_aggregate_projection_replay_only=True,
        new_models_or_weights_or_source_counts=False,
        summary=dict(states=50, qualified_states=sum(row["qualified"] for row in output),
            held_states=sum(not row["qualified"] for row in output),
            group_decisions=sum(len(row["scopes"])-1 for row in output),
            supported_group_decisions=sum(scope["available"] for row in output
                for key, scope in row["scopes"].items() if key),
            statewide_spread_margin_pp={metric: dict(median=statistics.median(values) if values else None,
                maximum=max(values) if values else None, states_with_complete_variants=len(values))
                for metric, values in widths.items()}),
        rows=output)
    return result, witness


def build(inputs, output):
    inputs, output = Path(inputs), Path(output)
    if output.exists():
        raise ValueError("Never overwrite a source-pinned sensitivity publication")
    metadata = json.loads((inputs/"inputs.json").read_bytes())
    models, pins = {}, {}
    for profile in PROFILES:
        entry = metadata[profile]
        filename = entry["file"]
        if Path(filename).name != filename:
            raise ValueError("A source input must be an explicit package member")
        if not re.fullmatch(r"https://raw\.githubusercontent\.com/hanshanley/voter-participation/"
                r"[a-f0-9]{40}/data/house-official-source-update/[a-zA-Z0-9-]+/viewer-"
                + profile+r"\.json", entry["url"]):
            raise ValueError("A published immutable aggregate source URL is required")
        body = (inputs/filename).read_bytes()
        if pin(body) != {key: entry[key] for key in ("bytes", "sha256")}:
            raise ValueError("Published aggregate input bytes differ")
        models[profile] = json.loads(body)
        pins[profile] = {key: entry[key] for key in ("url", "bytes", "sha256")}
    result, witness = summarize(models, pins)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=("state_code", "group", "metric", "variant",
        "available", "value_json", "reason"),
        lineterminator="\n")
    writer.writeheader()
    writer.writerows(witness)
    output.mkdir(parents=True)
    body = encoded(result)
    (output/"sensitivity.json").write_bytes(body)
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, compresslevel=9, mtime=0) as gzip_stream:
        gzip_stream.write(body)
    (output/"sensitivity.json.gz").write_bytes(compressed.getvalue())
    (output/"complete-nine-variant-query.csv").write_text(stream.getvalue(), encoding="utf-8")
    (output/"manifest.json").write_bytes(encoded(dict(
        input_layer="three published fitted aggregate profile products",
        source_pins=pins, source_fits_reproduced=False,
        files={name: pin((output/name).read_bytes()) for name in
            ("sensitivity.json", "sensitivity.json.gz", "complete-nine-variant-query.csv")})))
    return result["summary"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.inputs, args.output), sort_keys=True))
