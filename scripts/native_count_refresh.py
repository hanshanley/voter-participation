"""Prepare same-source record refreshes; the routine rechecks all original facts."""

import argparse
import copy
from decimal import Decimal
import gzip
import json
from pathlib import Path

from scripts.native_products import encoded, pin
from scripts.participation_intake.adapters import field, verify_native_reproduction
from scripts.participation_intake.contract import validate_all


def prepare_rows(originals, recipe, queries, review):
    required = {"contract", "state_code", "year", "source_id", "county_query", "state_query",
        "identity_fields", "count_field", "denominator_field", "reported_units_field",
        "total_units_field", "clock_field", "published_pct_field", "scope_review", "notes", "release_tag",
        "refresh_current_reporting"}
    if (set(review) != required or review["contract"] != "participation.native_count_refresh.v1"
            or not review["scope_review"].strip() or type(review["refresh_current_reporting"]) is not bool):
        raise ValueError("An explicit same-source record review is required")
    sources = [p for p in recipe["products"] if p["id"] == review["source_id"]]
    if (len(sources) != 1 or sources[0]["kind"] not in ("json_records", "delimited")
            or sources[0]["state_code"] != review["state_code"]
            or sources[0]["election_year"] != review["year"]):
        raise ValueError("A reviewed native record source and election are required")
    source = sources[0]
    selected = queries[review["county_query"]]
    control = queries[review["state_query"]]
    roles = {role: review[role + "_field"] for role in (
        "count", "denominator", "reported_units", "total_units", "clock", "published_pct")}
    count_roles = [roles[role] for role in ("count", "denominator", "reported_units", "total_units")]
    if (selected["product"] != source["id"] or control["product"] != source["id"]
            or len(set(count_roles)) != len(count_roles)
            or not set(count_roles) <= set(selected["count_fields"])
            or not set(count_roles) <= set(control["count_fields"])
            or len(control["rows"]) != 1 or not originals):
        raise ValueError("Separate complete county and state statistical queries are required")
    identities = review["identity_fields"]
    if not identities:
        raise ValueError("Exact source identity fields are required")
    old_keys = [tuple(field(row, path) for path in identities.values()) for row in originals]
    native_keys = [tuple(row[key] for key in identities) for row in selected["rows"]]
    if (len(set(old_keys)) != len(old_keys) or len(set(native_keys)) != len(native_keys)
            or set(old_keys) != set(native_keys)):
        raise ValueError("Exact complete source identities differ; no aliases or partial replacement")
    total = control["rows"][0]
    state_refs = {json.dumps(ref, sort_keys=True) for ref in total["source_rows"]}
    if any(state_refs & {json.dumps(ref, sort_keys=True) for ref in row["source_rows"]}
            for row in selected["rows"]):
        raise ValueError("A county record is not a separate native state control")
    for role in count_roles:
        if sum(row[role] for row in selected["rows"]) != total[role]:
            raise ValueError("Native county/state statistical controls do not reconcile")
    definitions = [q for q in recipe["queries"] if q["id"] == review["county_query"]]
    state_definitions = [q for q in recipe["queries"] if q["id"] == review["state_query"]]
    if len(definitions) != 1 or len(state_definitions) != 1:
        raise ValueError("Complete native county and state query definitions are required")
    definition = definitions[0]
    base_url = ("https://github.com/hanshanley/margin_of_error/releases/download/"
        + review["release_tag"] + "/")
    by_key = dict(zip(native_keys, selected["rows"]))
    rows, bindings = [], []
    for previous, identity in zip(originals, old_keys):
        native = by_key[identity]
        row = copy.deepcopy(previous)
        count, registered = native[roles["count"]], native[roles["denominator"]]
        if (row["election"]["year"] != review["year"]
                or row["geography"]["state_code"] != review["state_code"]
                or row["view"]["source_url"] != source["url"]
                or row["denominator"] is None or row["denominator"]["value"] != registered
                or row["source_clock"]["timezone"] is not None
                or registered <= 0 or count > registered or row["quality"]["conflicts"]):
            raise ValueError("A changed registered frame, source, timezone or conflict needs separate review")
        pct = native[roles["published_pct"]]
        if not isinstance(pct, str) or not pct.endswith("%"):
            raise ValueError("A native printed fraction is required")
        published = Decimal(pct[:-1])
        exact = Decimal(100 * count) / registered
        if not published.is_finite() or not 0 <= published <= 100 or abs(exact - published) > Decimal(".015"):
            raise ValueError("Native printed fraction disagrees with statistical count fields")
        clock = native[roles["clock"]]
        if clock is not None and (not isinstance(clock, str) or not clock):
            raise ValueError("Native clock must remain its literal or unknown")
        row["count"].update(value=count, literal=count, status="reported")
        row["source_clock"].update(literal=clock, timezone=None,
            qualification="native_result_literal_timezone_not_supplied")
        reported, units = native[roles["reported_units"]], native[roles["total_units"]]
        if reported > units:
            raise ValueError("Native reported units exceed the declared total")
        row["reporting_status"].update(reported_units=reported, total_units=units, complete=reported == units)
        row["quality"]["notes"] = list(review["notes"])
        row["quality"]["native_conflict_status"] = "new_native_snapshot_prior_baseline_retained"
        row["view"].update(ballots=count, denominator=registered,
            reported_pct=round(100 * count / registered, 3) if previous["view"]["reported_pct"] is not None else None,
            reported_units=reported, total_units=units, source_update_label=clock,
            source_url=source["url"], source_sha256=source["pin"]["sha256"],
            source_retrieved_at=source["retrieved_at_utc"], quality=list(review["notes"]),
            complete_download_url=base_url + "complete-analysis.zip",
            native_record=dict(query=native, original_pin=source["pin"],
                legacy_identity_not_native_record_address=True,
                source_timezone=None, counts_repaired=False),
            native_state_reference=copy.deepcopy(total))
        selector = dict(zip(identities, identity))
        row["source"].update(url=source["url"], input_sha256=source["pin"]["sha256"],
            selector=dict(native_query=review["county_query"], native_record=selector,
                source_rows=native["source_rows"]), fields=copy.deepcopy(row["view"]))
        rows.append(row)
        def binding(role):
            measure = roles[role]
            return dict(input="facts-" + source["id"], compression="gzip",
                query_recipe_input="recipe", native_query_id=review["county_query"],
                source_id=source["id"], source_role="native_registration_ballot_reported_turnout_statistics",
                native_record=selector, measure=measure,
                native_measure_header=definition["fields"][measure],
                same_measure_review_evidence=review["scope_review"],
                accepted_measure_literal=row["measure"]["literal"], record=dict(id=row["id"]))
        for path in ("count.value", "count.literal", "view.ballots", "source.fields.ballots"):
            bindings.append(dict(binding("count"), path=path, parse="count"))
        for role in ("count", "denominator", "reported_units", "total_units"):
            for prefix in ("view", "source.fields"):
                bindings.append(dict(binding(role),
                    path=prefix + ".native_record.query." + roles[role], parse="count"))
        for role, paths in (
                ("denominator", ("denominator.value", "view.denominator", "source.fields.denominator")),
                ("reported_units", ("reporting_status.reported_units", "view.reported_units", "source.fields.reported_units")),
                ("total_units", ("reporting_status.total_units", "view.total_units", "source.fields.total_units"))):
            bindings.extend(dict(binding(role), path=path, parse="count") for path in paths)
        for path in ("source_clock.literal", "view.source_update_label", "source.fields.source_update_label",
                "view.native_record.query." + roles["clock"],
                "source.fields.native_record.query." + roles["clock"]):
            bindings.append(dict(binding("count"), path=path, value_scope="row",
                value_path=roles["clock"], parse="literal"))
        for path, native_path in (
                ("source.input_sha256", "pin.sha256"), ("view.source_sha256", "pin.sha256"),
                ("source.fields.source_sha256", "pin.sha256"), ("source.url", "url"),
                ("view.source_url", "url"), ("source.fields.source_url", "url"),
                ("view.source_retrieved_at", "retrieved_at_utc"),
                ("source.fields.source_retrieved_at", "retrieved_at_utc")):
            bindings.append(dict(binding("count"), path=path, value_scope="source",
                value_path=native_path, parse="literal"))
        for role in ("count", "denominator", "reported_units", "total_units", "clock", "published_pct"):
            common = binding(role if role in ("count", "denominator", "reported_units", "total_units") else "count")
            common.update(native_query_id=review["state_query"],
                native_record={key: total[key] for key in identities},
                native_measure_header=state_definitions[0]["fields"][common["measure"]])
            for prefix in ("view", "source.fields"):
                item = dict(common, path=prefix + ".native_state_reference." + roles[role])
                if role in ("clock", "published_pct"):
                    item.update(value_scope="row", value_path=roles[role], parse="literal")
                else:
                    item["parse"] = "count"
                bindings.append(item)
    validate_all(rows)
    return rows, bindings


def prepare(review_path, baseline, source_root, output):
    from scripts.participation_batch import baseline_files

    if output.exists():
        raise ValueError("Use a fresh reviewed preparation directory")
    review = json.loads(review_path.read_bytes())
    description, files, index = baseline_files(baseline)
    state = json.loads(gzip.decompress(files[index["states"][review["state_code"]]["file"]]))
    selected = set(state["views"]["official"]["counties"])
    originals = [row for row in state["records"] if row["id"] in selected]
    recipe_body = (source_root / "recipe").read_bytes()
    recipe = json.loads(recipe_body)
    query_body = gzip.decompress((source_root / "controls").read_bytes())
    queries = json.loads(query_body)["queries"]
    rows, bindings = prepare_rows(originals, recipe, queries, review)
    base = ("https://github.com/hanshanley/margin_of_error/releases/download/"
        + review["release_tag"] + "/")
    inputs, reproduction = {}, {}

    def add(name, body, url=None, filename=None):
        if Path(name).name != name or name in inputs:
            raise ValueError("Native preparation input identity is unsafe or duplicated")
        inputs[name] = (body, dict(url=url or base + (filename or name),
            allowed_hosts=([url.split("/")[2]] if url else
                ["github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"]),
            pin=pin(body), publication="original"))

    add("recipe", recipe_body, filename="complete-native-query-recipe.json")
    add("controls", gzip.compress(query_body, mtime=0), filename="complete-native-queries.json.gz")
    for product in recipe["products"]:
        name = product["path"]
        add(name, (source_root / name).read_bytes(), url=product["url"])
        factual = "facts-" + product["id"]
        add(factual, (source_root / factual).read_bytes(),
            filename=product["id"] + ".factual-tables.json.gz")
        reproduction[product["id"]] = dict(original=name, facts=factual, compression="gzip")
    add("preparation-review", review_path.read_bytes(), filename="preparation-review.json")
    add("preparation", Path(__file__).read_bytes(), filename="prepare-native-count-refresh.py")
    add("snapshot", encoded(dict(
        contract="participation.reviewed_canonical_refresh.v1",
        state_code=review["state_code"], year=review["year"], rows=rows)),
        filename="reviewed-count-observations.json")
    spec = dict(id="reviewed-native-record-refresh", adapter="canonical_json",
        classification="public_aggregate", primary_input="snapshot",
        expected_rows=len(rows), inputs={name: declaration for name, (_, declaration) in inputs.items()},
        election=originals[0]["election"],
        geography=dict(state_code=review["state_code"], level=originals[0]["geography"]["level"]),
        source_clock=dict(literal=None, timezone=None), notes=review["notes"],
        review_evidence=review["scope_review"],
        format=dict(items_path="rows", assert_fields=dict(
            contract="participation.reviewed_canonical_refresh.v1",
            state_code=review["state_code"], year=review["year"]), fact_bindings=bindings,
            native_reproduction=dict(recipe_input="recipe", products=reproduction,
                queries_input="controls", queries_compression="gzip")))
    if review["refresh_current_reporting"]:
        spec["format"]["current_reporting"] = dict(query_id=review["state_query"],
            reference_path="view.native_state_reference",
            fields={role: review[role + "_field"] for role in (
                "count", "denominator", "reported_units", "total_units", "clock", "published_pct")})
    verify_native_reproduction(spec, {name: body for name, (body, _) in inputs.items()})
    registry = dict(contract="participation.routine_batch.v1",
        baseline_version=description["version"], source_scope=review["scope_review"],
        sources=[dict(id="counts", spec=spec,
            baseline_source_ids=sorted({row["source"]["id"] for row in originals}))])
    supplied = output / "supplied/counts"
    supplied.mkdir(parents=True)
    for name, (body, _) in inputs.items():
        (supplied / name).write_bytes(body)
    (output / "registry.json").write_bytes(encoded(registry))
    return dict(prepared=True, jurisdictions=51, reviewed_rows=len(rows),
        original_products=len(recipe["products"]), complete_queries=len(recipe["queries"]),
        source_requests=0, geographic_or_registered_frame_promotion=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.review, args.baseline, args.source_root, args.output), sort_keys=True))
