"""Reproduce source-snapshot diagnostics without promoting incomplete House endpoints."""

import argparse
import csv
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


CATEGORIES = ("D", "R", "O", "blank")
FORBIDDEN_CLAIMS = (
    "candidate_votes_are_ballots_or_turnout",
    "count_differences_identify_transferred_voters",
    "full_state_model_endpoint_or_behavioral_eligibility_promoted",
    "independent_boundary_stability_or_statewide_vector_qualified",
    "published_candidate_percent_denominators_independently_qualified",
    "source_models_weights_fits_or_113_existing_versions_changed",
)
SOURCE_FIELDS = {
    "contract", "state_code", "district", "office", "election_date", "publication_date",
    "native_status", "candidate_names", "party_labels_are_explicit_native_first_choice_markers",
    "snapshots", "tabulation_original", "qualification",
    "raw_publisher_html_private_person_records_or_histories_included",
}
SNAPSHOT_FIELDS = {
    "id", "label", "counts", "native_percent_literals", "source_url", "source_urls", "source_pin",
    "source_snapshot", "native_count_clock", "source_round", "publication_date",
    "full_candidate_or_exhausted_accounting_vector_qualified",
}
QUALIFIED_FLAGS = (
    "new_major_party_aggregate_context_qualified",
    "final_other_or_blank_counts_not_supplied_not_zero",
    "source_partial_not_metadata_only_query_input",
)


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decimal(value):
    with localcontext() as context:
        context.prec = 80
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def rational(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator),
            "decimal": decimal(value)}


def count(value):
    require(value is None or type(value) is int and 0 <= value <= 9007199254740991,
            "Source count must be an integer or explicit unknown")
    return value


def fields(value, allowed, required, label):
    require(type(value) is dict and set(required) <= set(value) <= set(allowed),
            "Unexpected or incomplete " + label)


def text(value, label):
    require(type(value) is str and bool(value.strip()) and "\x00" not in value,
            "Invalid " + label)
    return value


def source_date(value):
    text(value, "publication/election date")
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "Invalid publication/election date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Invalid publication/election date") from error
    return value


def source_url(value):
    text(value, "source URL")
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None,
            "Invalid source URL")
    return value


def source_facts(data):
    fields(data, SOURCE_FIELDS, SOURCE_FIELDS, "public source payload")
    require(data["contract"] == "participation.maine_house_round_source_facts.v1",
            "Unsupported source-facts contract")
    require(data["raw_publisher_html_private_person_records_or_histories_included"] is False,
            "Unexpected or unqualified public source payload")
    require(data["party_labels_are_explicit_native_first_choice_markers"] is True,
            "Native candidate-party qualification changed")
    status = text(data["native_status"], "native status")
    require(status.lower().startswith("unofficial "), "Unofficial source status required")
    source_date(data["election_date"])
    source_date(data["publication_date"])
    require(data["publication_date"] >= data["election_date"], "Publication precedes election")
    qualification = data["qualification"]
    fields(qualification, {*FORBIDDEN_CLAIMS, *QUALIFIED_FLAGS, "reason"},
           {*FORBIDDEN_CLAIMS, *QUALIFIED_FLAGS, "reason"}, "source qualification")
    require(all(qualification.get(key) is True for key in QUALIFIED_FLAGS)
            and all(qualification.get(key) is False for key in FORBIDDEN_CLAIMS),
            "Source-context qualification or withholding changed")
    text(qualification["reason"], "qualification reason")
    fields(data["candidate_names"], ("D", "R"), ("D", "R"), "candidate names")
    for value in data["candidate_names"].values():
        text(value, "candidate name")
    state, district = data["state_code"], data["district"]
    require(type(state) is str and re.fullmatch(r"[A-Z]{2}", state)
            and type(district) is str and re.fullmatch(state + r"-\d{2}", district)
            and data["office"] == "house", "Invalid source contest scope")
    tabulation = data["tabulation_original"]
    fields(tabulation, ("url", "status", "stopped", "bytes", "sha256"),
           ("url", "status", "stopped", "bytes", "sha256"), "tabulation access")
    source_url(tabulation["url"])
    require(type(tabulation["status"]) is int and tabulation["status"] in (401, 403, 429)
            and tabulation["stopped"] is True
            and tabulation["bytes"] is None and tabulation["sha256"] is None,
            "Stopped, unacquired tabulation-original semantics changed")
    snapshots = data["snapshots"]
    require(type(snapshots) is list and len(snapshots) >= 2, "Two source snapshots required")
    canonical_snapshots = []
    for snapshot in snapshots:
        fields(snapshot, SNAPSHOT_FIELDS,
               ("id", "label", "counts", "native_percent_literals", "native_count_clock"),
               "source snapshot metadata")
        for key in ("id", "label"):
            text(snapshot[key], "snapshot " + key)
        for key in ("native_count_clock", "source_round", "source_snapshot"):
            if snapshot.get(key) is not None:
                text(snapshot[key], key)
        if "publication_date" in snapshot:
            source_date(snapshot["publication_date"])
            require(data["election_date"] <= snapshot["publication_date"] <= data["publication_date"],
                    "Snapshot publication outside source dates")
        require(("source_url" in snapshot) != ("source_urls" in snapshot),
                "Exactly one source URL representation required")
        if "source_url" in snapshot:
            source_url(snapshot["source_url"])
        else:
            urls = snapshot["source_urls"]
            require(type(urls) is list and bool(urls), "Source URLs must be a nonempty string list")
            for url in urls:
                source_url(url)
            require(len(set(urls)) == len(urls), "Duplicate source URLs")
        if "source_pin" in snapshot:
            source_pin = snapshot["source_pin"]
            fields(source_pin, ("bytes", "sha256"), ("bytes", "sha256"), "source pin")
            count(source_pin["bytes"])
            require(type(source_pin["bytes"]) is int and source_pin["bytes"] > 0
                    and type(source_pin["sha256"]) is str
                    and re.fullmatch(r"[a-f0-9]{64}", source_pin["sha256"]),
                    "Invalid source pin")
        for key in ("counts", "native_percent_literals"):
            fields(snapshot[key], CATEGORIES, CATEGORIES, key)
        if "full_candidate_or_exhausted_accounting_vector_qualified" in snapshot:
            require(snapshot["full_candidate_or_exhausted_accounting_vector_qualified"] is False,
                    "Final accounting qualification must remain withheld")
        canonical = {key: snapshot[key] for key in SNAPSHOT_FIELDS
                     if key in snapshot and key not in {
                         "counts", "native_percent_literals", "source_urls", "source_pin"}}
        for key in ("counts", "native_percent_literals"):
            canonical[key] = {category: snapshot[key][category] for category in CATEGORIES}
        if "source_urls" in snapshot:
            canonical["source_urls"] = list(snapshot["source_urls"])
        if "source_pin" in snapshot:
            canonical["source_pin"] = {key: snapshot["source_pin"][key] for key in ("bytes", "sha256")}
        canonical_snapshots.append(canonical)
    canonical = {key: data[key] for key in SOURCE_FIELDS
                 if key not in {"snapshots", "qualification", "candidate_names", "tabulation_original"}}
    canonical["snapshots"] = canonical_snapshots
    canonical["candidate_names"] = {key: data["candidate_names"][key] for key in ("D", "R")}
    canonical["qualification"] = {key: qualification[key]
                                for key in (*FORBIDDEN_CLAIMS, *QUALIFIED_FLAGS, "reason")}
    canonical["tabulation_original"] = {key: tabulation[key]
                                      for key in ("url", "status", "stopped", "bytes", "sha256")}
    return canonical


def calculate(data):
    data = source_facts(data)
    qualification = data["qualification"]
    state, district = data["state_code"], data["district"]
    snapshots = data["snapshots"]
    identifiers = [row["id"] for row in snapshots]
    require(len(set(identifiers)) == len(identifiers)
            and all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in identifiers),
            "Duplicate or malformed snapshot identity")
    source_rows, diagnostics, shares = [], [], {}
    for snapshot in snapshots:
        values = snapshot["counts"]
        require(set(values) == set(CATEGORIES), "Complete count/unknown category decisions required")
        for value in values.values():
            count(value)
        require(values["D"] is not None and values["R"] is not None
                and values["D"] + values["R"] > 0, "Positive reported D+R total required")
        if snapshot.get("full_candidate_or_exhausted_accounting_vector_qualified") is False:
            require(values["O"] is None and values["blank"] is None,
                    "Unreported final accounting must not be filled with zero")
        total = values["D"] + values["R"]
        share = Fraction(100 * values["D"], total)
        shares[snapshot["id"]] = share
        for category in CATEGORIES:
            literal = snapshot["native_percent_literals"][category]
            if literal is not None:
                require(isinstance(literal, str), "Native percentage literal must remain text")
                try:
                    percentage = Decimal(literal)
                except Exception as error:
                    raise ValueError("Invalid native percentage literal") from error
                require(percentage.is_finite() and 0 <= percentage <= 100,
                        "Invalid native percentage literal")
            source_rows.append({
                "state_code": state, "district": district, "snapshot_id": snapshot["id"],
                "category": category, "source_count": values[category],
                "count_status": "not_supplied" if values[category] is None else "reported",
                "native_percent_literal": literal,
                "native_count_clock": snapshot.get("native_count_clock"),
                "source_round": snapshot.get("source_round"),
                "publication_date": snapshot.get("publication_date"),
                "source_snapshot": snapshot.get("source_snapshot"),
                "source_urls": "|".join(snapshot.get("source_urls") or [snapshot.get("source_url", "")]),
                "source_sha256": snapshot.get("source_pin", {}).get("sha256"),
            })
        diagnostics.append({
            "snapshot_id": snapshot["id"], "reported_D_plus_R": total,
            "D_share_among_reported_D_R_percent": rational(share),
            "D_minus_R_margin_among_reported_D_R_pp": rational(2 * share - 100),
            "four_supplied_field_sum": sum(values.values())
                if all(value is not None for value in values.values()) else None,
            "unknown_categories": [key for key in CATEGORIES if values[key] is None],
            "native_percent_basis_qualified": False,
            "ballots_or_unique_people_inferred": False,
        })
    comparisons = []
    for earlier, later in itertools.combinations(snapshots, 2):
        delta = shares[later["id"]] - shares[earlier["id"]]
        comparisons.append({
            "earlier_snapshot": earlier["id"], "later_snapshot": later["id"],
            "D_reported_count_difference": later["counts"]["D"] - earlier["counts"]["D"],
            "R_reported_count_difference": later["counts"]["R"] - earlier["counts"]["R"],
            "D_share_among_reported_D_R_change_pp": rational(delta),
            "D_minus_R_margin_among_reported_D_R_change_pp": rational(2 * delta),
            "interpretation": "source_snapshot_contrast_on_explicit_D_R_normalization",
            "native_printed_percentages_subtracted": False,
            "matched_round_boundary_or_population_qualified": False,
            "individual_vote_transfers_or_behavior_identified": False,
        })
    return {
        "contract": "participation.house_round_source_context.v1",
        "state_code": state, "district": district, "office": "house",
        "election_date": data["election_date"], "source_rows": source_rows,
        "major_party_diagnostics": diagnostics, "source_snapshot_comparisons": comparisons,
        "qualification": qualification,
        "source_facts": data,
        "model_endpoint_update": False, "geographic_allocation": False,
        "source_extraction_replayed": False,
        "reproduction_scope": "complete_selected_numeric_facts_to_all_source_context_queries",
    }


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def outputs(data):
    result = calculate(data)
    diagnostic_rows = []
    for row in result["major_party_diagnostics"]:
        diagnostic_rows.append({
            "snapshot_id": row["snapshot_id"], "reported_D_plus_R": row["reported_D_plus_R"],
            "D_share_among_reported_D_R_percent": row["D_share_among_reported_D_R_percent"]["decimal"],
            "D_share_exact_numerator": row["D_share_among_reported_D_R_percent"]["numerator"],
            "D_share_exact_denominator": row["D_share_among_reported_D_R_percent"]["denominator"],
            "D_minus_R_margin_pp": row["D_minus_R_margin_among_reported_D_R_pp"]["decimal"],
            "four_supplied_field_sum": row["four_supplied_field_sum"],
            "unknown_categories": "|".join(row["unknown_categories"]),
        })
    comparison_rows = []
    for row in result["source_snapshot_comparisons"]:
        comparison_rows.append({
            "earlier_snapshot": row["earlier_snapshot"], "later_snapshot": row["later_snapshot"],
            "D_reported_count_difference": row["D_reported_count_difference"],
            "R_reported_count_difference": row["R_reported_count_difference"],
            "D_share_change_pp": row["D_share_among_reported_D_R_change_pp"]["decimal"],
            "D_share_change_exact_numerator": row["D_share_among_reported_D_R_change_pp"]["numerator"],
            "D_share_change_exact_denominator": row["D_share_among_reported_D_R_change_pp"]["denominator"],
            "D_minus_R_margin_change_pp": row["D_minus_R_margin_among_reported_D_R_change_pp"]["decimal"],
            "matched_round_boundary_or_population_qualified": False,
            "individual_vote_transfers_or_behavior_identified": False,
        })
    return {
        "complete-source-context.json": encoded(result),
        "complete-source-count-query.csv": csv_bytes(result["source_rows"]),
        "complete-major-party-diagnostics.csv": csv_bytes(diagnostic_rows),
        "complete-source-snapshot-comparisons.csv": csv_bytes(comparison_rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    body = args.input.read_bytes()
    require(hashlib.sha256(body).hexdigest() == args.expected_sha256, "Source input checksum mismatch")
    generated = outputs(json.loads(body))
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in generated.items():
        with (args.output / name).open("xb") as stream:
            stream.write(value)
    print(json.dumps({"passed": True, "outputs": len(generated),
                      "model_endpoint_update": False, "source_extraction_replayed": False}))


if __name__ == "__main__":
    main()
