"""Apply separately reviewed observation additions without weakening refresh guards."""

import copy

from scripts.participation_intake.contract import IntakeError, digest, encoded, pin, validate_all


COUNTY_QUALIFIERS = ("state_code", "county_id", "county", "geography_level", "county_fips",
    "reference_municipality_key", "source_administration_id", "source_mode", "denominator_basis",
    "participation_measure_kind", "participation_measure_literal", "participation_measure_label",
    "cast_ballot_count_qualified", "unique_voter_count_qualified")


def append_reviewed(state, source, baseline_pin):
    binding = source.get("addition")
    rows = source["rows"]
    if (not isinstance(binding, dict)
            or binding.get("contract") != "participation.reviewed_count_addition.v1"
            or not binding.get("source_scope_review_evidence")
            or binding.get("baseline_shard") != baseline_pin
            or source["baseline_source_ids"] or not rows):
        raise IntakeError("addition_scope", "New observations require a pinned, separately reviewed addition")
    validate_all(rows)
    by_id = {row["id"]: row for row in rows}
    if binding.get("records") != {key: pin(encoded(row)) for key, row in by_id.items()}:
        raise IntakeError("addition_scope", "Every added observation must match the complete reviewed inventory")
    if set(by_id) & {row["id"] for row in state["records"]}:
        raise IntakeError("addition_scope", "Additions cannot overwrite existing observations")
    for row in rows:
        view = row["view"]
        if (row["geography"]["level"] == "county" and view.get("maps_approved")
                and not binding.get("county_reference")):
            raise IntakeError("addition_scope", "Mapped county additions require a reviewed native reference binding")
        if (row["geography"]["state_code"] != state["state_code"]
                or row["election"]["year"] != state["year"]
                or row["denominator"] is not None or view.get("denominator") is not None
                or view.get("reported_pct") is not None or view["ballots"] != row["count"]["value"]
                or (view.get("source_update_label") or None) != row["source_clock"]["literal"]):
            raise IntakeError("addition_scope", "An addition cannot qualify rates or alter count/clock mirrors")
    if set(binding.get("views", {})) != set(state["views"]):
        raise IntakeError("addition_scope", "Every existing mode needs an explicit reviewed binding")
    existing = {row["id"]: row for row in state["records"]}
    result, selected = copy.deepcopy(state), set()
    for mode, frame in result["views"].items():
        declaration = binding["views"][mode]
        if set(declaration) != {"counties", "precincts", "nongeographic"}:
            raise IntakeError("addition_scope", "Every display partition needs an explicit reviewed binding")
        for partition, selection in declaration.items():
            new = selection["append"]
            if (selection["before"] != frame[partition] or not isinstance(new, list)
                    or len(new) != len(set(new)) or any(key not in by_id for key in new)
                    or new and not frame["qualified"]):
                raise IntakeError("addition_scope", "A display addition cannot replace existing selections")
            for key in new:
                row = by_id[key]
                level = row["geography"]["level"]
                if (partition == "counties" and level not in
                        ("county", "county_equivalent", "municipality", "election_administration")
                        or partition == "precincts" and level not in ("precinct", "ward", "reporting_unit")
                        or partition == "nongeographic" and level != "nongeographic"
                        or mode in ("in_person_early", "mail_returned") and row["measure"]["mode"] != mode):
                    raise IntakeError("addition_scope", "New observations cannot substitute geographic or mode scopes")
            if partition == "counties":
                prior_names = {
                    existing[key]["view"].get("county")
                    for key in frame[partition]
                    if existing[key]["geography"]["level"] == "county"
                }
                new_names = [
                    by_id[key]["view"].get("county")
                    for key in new
                    if by_id[key]["geography"]["level"] == "county"
                ]
                if (len(new_names) != len(set(new_names))
                        or prior_names & set(new_names)):
                    raise IntakeError(
                        "addition_scope",
                        "A county addition cannot duplicate an exact selected county name",
                    )
            def identity(row):
                view = row["view"]
                return (view.get("county_id"), view.get("unit_key") if partition == "precincts"
                        else row["geography"]["id"] if partition == "nongeographic" else None)
            prior = {identity(existing[key]) for key in frame[partition]}
            identities = [identity(by_id[key]) for key in new]
            if len(identities) != len(set(identities)) or prior & set(identities):
                raise IntakeError("addition_scope", "New sources cannot silently shadow selected display identities")
            frame[partition].extend(new)
            selected.update(new)
    if selected != set(by_id):
        raise IntakeError("addition_scope", "Every new observation needs a reviewed access path")
    result["records"].extend(copy.deepcopy(rows))
    return result, len(rows)


def append_county_references(description, files, index, sources):
    updated, changed = copy.deepcopy(index), 0
    for source in sources:
        review = (source.get("addition") or {}).get("county_reference")
        if review is None:
            continue
        if (review.get("contract") != "participation.reviewed_county_reference_addition.v1"
                or not review.get("review_evidence")
                or review.get("baseline_index") != pin(files[description["index"]["file"]])):
            raise IntakeError("addition_scope", "County reference additions require the exact reviewed native index")
        rows = {row["id"]: row for row in source["rows"]}
        modes = {mode: selection["counties"]["append"]
                 for mode, selection in source["addition"]["views"].items()
                 if selection["counties"]["append"]}
        if not modes or set(review.get("modes", {})) != set(modes):
            raise IntakeError("addition_scope", "Every added county mode needs an explicit reference review")
        code = source["spec"]["geography"]["state_code"]
        for mode, identities in modes.items():
            binding = updated.get("county_bindings", {}).get(code, {}).get(mode)
            declaration = review["modes"][mode]
            if (not binding or declaration.get("before") != pin(encoded(binding))
                    or declaration.get("append") != identities):
                raise IntakeError("addition_scope", "An existing complete county reference binding must be preserved")
            county_ids = {row["county_id"] for row in binding["rows"]}
            feature_keys = {row["feature_key"] for row in binding["rows"]}
            for identity in identities:
                row = rows[identity]
                validate_all([row])
                view, geography = row["view"], row["geography"]
                key = geography["join"]["feature_key"]
                reference = view.get("reference_geometry", {})
                scope = binding.get("feature_scopes", {}).get(key)
                if (geography["level"] != "county" or geography["state_code"] != code
                        or geography["join"]["status"] != "approved"
                        or view.get("maps_approved") is not True
                        or row["denominator"] is not None or view.get("reported_pct") is not None
                        or view.get("county_id") in county_ids or key in feature_keys
                        or key not in binding["feature_keys"]
                        or scope != dict(state_code=code, name=view.get("county"),
                            boundary_year=reference.get("boundary_year"))
                        or reference.get("sha256") != binding["sha256"]
                        or not str(reference.get("url", "")).startswith("https://")
                        or view.get("county_fips") != key):
                    raise IntakeError("addition_scope", "New county reference identity, source scope or rate differs")
                binding["rows"].append(dict(county_id=view["county_id"], feature_key=key,
                    qualifier={name: view.get(name) for name in COUNTY_QUALIFIERS}))
                county_ids.add(view["county_id"])
                feature_keys.add(key)
                changed += 1
    if not changed:
        return description, files, 0
    result = dict(files, **{description["index"]["file"]: encoded(updated)})
    pins = {name: pin(body) for name, body in sorted(result.items())}
    descriptor = dict(description, files=pins,
        index=dict(file=description["index"]["file"], **pins[description["index"]["file"]]),
        version=digest(encoded(dict(files=pins, contract=description["record_contract"]))),
        complete_download=None)
    return descriptor, result, changed
