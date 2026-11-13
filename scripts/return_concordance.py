"""Replay complete recorded-count/rounded-share diagnostics without promoting endpoints."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import gzip
import io
import json
from pathlib import Path
import re
import zipfile

from scripts.house_panel import integer, party


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    import hashlib
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def percentage(value):
    if isinstance(value, bool):
        raise ValueError("A boolean is not a percentage")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError("Not a finite percentage") from error
    if not 0 <= result <= 100:
        raise ValueError("Percentage outside [0,100]")
    return result


def bounds(value, places, upstream_places=None):
    if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 6:
        raise ValueError("Explicit reviewed rounding precision is required")
    value = percentage(value)
    if (value * 10 ** places).denominator != 1:
        raise ValueError("A source share exceeds its declared rounding precision")
    half_step = Fraction(1, 2 * 10 ** places)
    if upstream_places is not None:
        if (isinstance(upstream_places, bool) or not isinstance(upstream_places, int)
                or not places < upstream_places <= 6):
            raise ValueError("Upstream rounding must have explicit finer precision")
        half_step += Fraction(1, 2 * 10 ** upstream_places)
    # Closed bounds conservatively retain either tie convention, not a match claim.
    return max(0, value - half_step), min(100, value + half_step)


def decimal(value):
    with localcontext() as context:
        context.prec = 60
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def identity(unit_id, state, state_codes):
    if (not re.fullmatch(r"[0-9]{5}", unit_id)
            or state_codes.get(unit_id[:2]) != state):
        raise ValueError("Unit identity does not match the declared native state")


def index_source(document, recipe):
    rows = document[recipe["collection"]]
    if document["count"] != len(rows):
        raise ValueError("Source inventory differs from its declared count")
    fields = recipe["identity"]
    for key, row in rows.items():
        if row[fields["id"]] != key:
            raise ValueError("Source key differs from the native unit identity")
        identity(key, row[fields["state"]], document["state_fips_to_postal"])
        for period in recipe["periods"]:
            native = row.get(period["key"])
            if native is None:
                continue
            integer(native[period["count"]])
            for field in period["parties"].values():
                bounds(native[field], period["decimal_places"], period.get("upstream_decimal_places"))
    return rows


def candidate_checks(reference, candidates, state_codes, fields):
    counts = defaultdict(Counter)
    identities = set()
    for row in candidates:
        key = (row["state_code"], row["county_fips"], row["district"],
               row["name"], row["party"])
        if key in identities:
            raise ValueError("Repeated native county/district candidate")
        identities.add(key)
        if row["year"] != "2026" or row["office"] != "U.S. House":
            raise ValueError("Reference candidate election scope changed")
        identity(row["county_fips"], row["state_code"], state_codes)
        counts[row["county_fips"]][party(row["party"])] += integer(row["votes"])
    checks = []
    for key, row in sorted(reference.items()):
        if key not in counts:
            raise ValueError("A reference county has no native candidate rows")
        expected = {group: integer(row[fields[group]]) for group in "DRO"}
        total = integer(row[fields["total"]])
        if sum(expected.values()) != total or any(
                counts[key][group] != expected[group] for group in "DRO"):
            raise ValueError("Exact reference differs from complete native candidate counts")
        checks.append(dict(unit_id=key, state_code=row[fields["state"]],
                           total=total, party_counts=expected,
                           native_candidate_sums_match=True))
    if set(counts) != set(reference):
        raise ValueError("Native candidate county inventory changed")
    return checks


def build(current, previous, reference_rows, candidates, recipe):
    periods = recipe["periods"]
    if (len(periods) != 2 or periods[0]["key"] == periods[1]["key"]
            or recipe["reference_period"] != periods[1]["key"]
            or any(set(p["parties"]) != {"D", "R"} for p in periods)):
        raise ValueError("Two distinct ordered D/R periods with the current reference are required")
    new, old = (index_source(source, recipe) for source in (current, previous))
    if current["state_fips_to_postal"] != previous["state_fips_to_postal"]:
        raise ValueError("Source state-identity frame changed")
    fields = recipe["reference"]
    reference = {}
    for row in reference_rows:
        if (row["year"] != str(recipe["reference_year"])
                or row["contest"] != recipe["reference_contest"]):
            raise ValueError("Reference year or contest scope changed")
        key = row[fields["id"]]
        identity(key, row[fields["state"]], current["state_fips_to_postal"])
        if key in reference:
            raise ValueError("Repeated reference county")
        reference[key] = row
    checks = candidate_checks(reference, candidates, current["state_fips_to_postal"], fields)
    selected = next(p for p in recipe["periods"] if p["key"] == recipe["reference_period"])
    ids = recipe["identity"]
    queries, changes = [], []
    for key in sorted(set(new) | set(old) | set(reference)):
        source, prior, ref = new.get(key), old.get(key), reference.get(key)
        state = (source or prior or {}).get(ids["state"]) or ref[fields["state"]]
        if ref and ref[fields["state"]] != state:
            raise ValueError("Reference and source state identities disagree")
        native = source.get(selected["key"]) if source else None
        earlier = prior.get(selected["key"]) if prior else None
        field_changes = {}
        for period in recipe["periods"]:
            a = prior.get(period["key"]) if prior else None
            b = source.get(period["key"]) if source else None
            missing = object()
            field_changes[period["key"]] = sorted(
                field for field in set(a or {}) | set(b or {})
                if (a or {}).get(field, missing) != (b or {}).get(field, missing))
        count_changed = ((native is None) != (earlier is None) or
                         native is not None and earlier is not None
                         and native[selected["count"]] != earlier[selected["count"]])
        selected_changes = field_changes[selected["key"]]
        change_kind = ("contest_total_changed" if count_changed else
                       "reporting_fields_only" if selected_changes and
                       set(selected_changes) <= set(recipe["reporting_fields"]) else
                       "same_total_nonreporting_fields_changed" if selected_changes else
                       "unchanged")
        if source or prior:
            changes.append(dict(unit_id=key, state_code=state,
                                changed_fields=field_changes,
                                selected_change_kind=change_kind,
                                selected_contest_total_changed=count_changed))
        query = dict(
            unit_id=key, state_code=state,
            unit_name=(source or prior or {}).get(ids["name"]) or ref[fields["name"]],
            native_current_periods={p["key"]: source.get(p["key"]) if source else None
                                    for p in recipe["periods"]},
            native_previous_periods={p["key"]: prior.get(p["key"]) if prior else None
                                     for p in recipe["periods"]},
            reference_native_row=ref,
            changed_fields=field_changes,
            selected_change_kind=change_kind,
            selected_contest_total_changed=count_changed,
            geography_hold=recipe["geographic_holds"].get(state),
            rounded_party_checks={}, source_minus_reference_contest_votes=None,
            source_descriptive_margin_change_interval_pp=None,
            source_descriptive_margin_change_holds=[],
            independent_validation=False, eligible_as_model_endpoint=False,
            measured_turnout=None, individual_switching=None, observed_staying_home=None)
        if native is not None and ref is not None:
            query["source_minus_reference_contest_votes"] = (
                integer(native[selected["count"]]) - integer(ref[fields["total"]]))
        if query["geography_hold"]:
            status = "geography_held"
        elif native is None:
            status = "secondary_result_missing"
        elif ref is None:
            status = "reference_unit_missing"
        elif integer(native[selected["count"]]) == 0:
            status = "secondary_zero_contest_total"
        elif integer(ref[fields["total"]]) == 0:
            status = "reference_zero_contest_total"
        else:
            denominator = integer(ref[fields["total"]])
            for group, field in selected["parties"].items():
                low, high = bounds(native[field], selected["decimal_places"],
                                   selected.get("upstream_decimal_places"))
                exact = Fraction(100 * integer(ref[fields[group]]), denominator)
                query["rounded_party_checks"][group] = dict(
                    source_native_percent=native[field],
                    source_lower_percent=decimal(low), source_upper_percent=decimal(high),
                    reference_exact_percent_fraction=str(exact),
                    reference_inside_closed_rounding_interval=low <= exact <= high)
            status = ("contest_total_difference"
                      if query["source_minus_reference_contest_votes"] != 0
                      else "rounded_party_share_difference"
                      if not all(c["reference_inside_closed_rounding_interval"]
                                 for c in query["rounded_party_checks"].values())
                      else "arithmetic_compatible_not_independent_validation")
        query["comparison_status"] = status
        margin_intervals = []
        holds = query["source_descriptive_margin_change_holds"]
        if query["geography_hold"]:
            holds.append("geographic_frame_not_qualified")
        for period in recipe["periods"]:
            row = query["native_current_periods"][period["key"]]
            if row is None:
                holds.append("missing_" + period["key"])
                continue
            if not integer(row[period["count"]]):
                holds.append("zero_contest_total_" + period["key"])
            if (row.get(period["one_party"]) or
                    any(percentage(row[field]) == 0 for field in period["parties"].values())):
                holds.append("one_major_party_or_zero_reported_share_" + period["key"])
            d, r = (bounds(row[period["parties"][group]], period["decimal_places"],
                           period.get("upstream_decimal_places"))
                    for group in "DR")
            margin_intervals.append((d[0] - r[1], d[1] - r[0]))
        if not holds and len(margin_intervals) == 2:
            before, after = margin_intervals
            query["source_descriptive_margin_change_interval_pp"] = dict(
                lower=decimal(after[0] - before[1]),
                upper=decimal(after[1] - before[0]),
                denominator="all selected-contest votes; not two-party share",
                preference_or_population_comparability_qualified=False)
        queries.append(query)
    states = []
    for state in sorted({q["state_code"] for q in queries}):
        rows = [q for q in queries if q["state_code"] == state]
        states.append(dict(state_code=state, unit_queries=len(rows),
                           comparison_status_counts=dict(sorted(Counter(
                               q["comparison_status"] for q in rows).items())),
                           changed_contest_totals=sum(q["selected_contest_total_changed"] for q in rows),
                           changed_selected_records=sum(
                               bool(q["changed_fields"][selected["key"]]) for q in rows),
                           qualified_new_model_endpoints=0))
    summary = dict(
        source_current_records=len(new), source_previous_records=len(old),
        reference_records=len(reference), complete_union_queries=len(queries),
        same_identity_source_reference_records=len(set(new) & set(reference)),
        source_only_units=len(set(new) - set(reference)),
        reference_only_units=len(set(reference) - set(new)),
        current_source_period_presence={
            p["key"]: sum(q["native_current_periods"][p["key"]] is not None for q in queries)
            for p in recipe["periods"]},
        paired_current_source_records=sum(
            all(q["native_current_periods"][p["key"]] is not None for p in recipe["periods"])
            for q in queries),
        reference_states=len({r[fields["state"]] for r in reference_rows}),
        complete_reference_candidate_checks=len(checks), state_queries=len(states),
        comparison_status_counts=dict(sorted(Counter(q["comparison_status"] for q in queries).items())),
        changed_selected_records=sum(bool(q["changed_fields"][selected["key"]]) for q in queries),
        changed_selected_contest_totals=sum(q["selected_contest_total_changed"] for q in queries),
        source_change_kind_counts=dict(sorted(Counter(
            q["selected_change_kind"] for q in queries if q["selected_change_kind"] != "unchanged").items())),
        changed_contest_total_states=[s["state_code"] for s in states if s["changed_contest_totals"]],
        new_exact_candidate_counts_inferred=0, new_ballot_or_participation_observations=0,
        new_model_endpoints_qualified=0, official_endpoint_precedence_changed=False,
        survey_fits_weights_or_behavioral_masks_changed=False,
        source_agreement_is_not_independent_validation=True,
        state_sums_of_rounded_party_counts_performed=False)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(queries[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                     for k, v in q.items()} for q in queries)
    return {
        "county-concordance.json": encoded(queries),
        "county-concordance.csv": stream.getvalue().encode(),
        "state-queries.json": encoded(states),
        "source-changes.json": encoded(changes),
        "reference-candidate-checks.json": encoded(checks),
        "summary.json": encoded(summary),
    }, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Use a fresh output directory")
    manifest_body = (inputs / "source-manifest.json").read_bytes()
    manifest = json.loads(manifest_body)
    bodies = {}
    for name, metadata in manifest["inputs"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "inputs":
            raise ValueError("Input must be an explicit relative packet member")
        body = (inputs / relative).read_bytes()
        if pin(body) != metadata:
            raise ValueError("Changed complete-package input: " + name)
        bodies[name] = body
    def content(role):
        name = manifest["roles"][role]
        body = bodies[name]
        return gzip.decompress(body) if name.endswith(".gz") else body
    def rows(role):
        return list(csv.DictReader(io.StringIO(content(role).decode("utf-8"))))
    files, summary = build(
        json.loads(content("source_current")), json.loads(content("source_previous")),
        rows("reference"), rows("reference_candidates"), json.loads(content("recipe")))
    files.update(bodies)
    files["source-manifest.json"] = manifest_body
    for name in ("scripts/return_concordance.py", "scripts/house_panel.py",
                 "tests/test_return_concordance.py", "tests/test_house_panel.py"):
        files[name] = Path(__file__).parents[1].joinpath(name).read_bytes()
    files["README.txt"] = (
        "Recorded-count / rounded-share diagnostics, not updated model endpoints or turnout.\n"
        "All source units, reference-only units, held records, native fields, exact reference\n"
        "candidate rows, district controls, receipts, recipe, code and tests are included.\n"
        "Original publisher prose/application code and respondent/person rows are excluded.\n"
        "Share intervals are conservative closed rounding intervals, not exact vote recovery.\n"
        "Reviewed upstream rounding adds uncertainty; two-then-one-decimal history is not\n"
        "treated as a single one-decimal rounding operation. Mixed origins use the wider bound.\n"
        "County identity equality and arithmetic agreement do not qualify source/party/round\n"
        "or geographic comparability. No state party sums or model promotion occurs.\n"
        "From a fresh full extraction, offline using only the Python standard library:\n"
        "  python3 -S -m unittest discover -s tests -p 'test_*.py'\n"
        "  python3 -S -m scripts.return_concordance --inputs . --output /new/replay\n"
        "Compare all six complete output files byte-for-byte, not only summary.json.\n"
    ).encode()
    files["checksums.json"] = encoded({name: pin(body) for name, body in sorted(files.items())})
    output.mkdir(parents=True)
    for name, body in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w",
                         compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.inputs, args.output), indent=2, sort_keys=True))
