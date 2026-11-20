"""Complete public aggregate products for the existing explorer; no fitting or allocation."""

import csv
import gzip
import io
import json
import math
from collections import Counter

from scripts.nationwide import STATES
from scripts.participation_intake.contract import encoded, pin


CONTRACT = "participation.supported_analytical_release.v1"
REVIEW_CONTRACT = "participation.reviewed_analytical_eligibility.v1"
TERMS = ("switching", "exit", "entry", "other_choice", "unresolved")


def require(condition, message):
    if not condition:
        raise ValueError("Supported analytical release: " + message)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    columns = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(
            value, (list, dict)) else value for key, value in row.items()})
    return stream.getvalue().encode()


def compressed(body):
    result = bytearray(gzip.compress(body, compresslevel=9, mtime=0))
    result[9] = 3
    return bytes(result)


def decoded(files, name):
    body = files[name]
    return json.loads(gzip.decompress(body) if name.endswith(".gz") else body)


def input_body(review, key):
    item = review["frozen_inputs"][key]
    body = item["body"].encode()
    require(pin(body) == item["pin"], "accepted historical/model input changed: " + key)
    return body


def mechanisms(row, state_row):
    point = row.get("point", row)
    values = point.get("contributions_pp")
    target = point.get("total_change_pp", point.get("total_contribution_pp"))
    if values is None:
        return {key: None for key in (*TERMS, "accounting_residual_pp",
                                     "numerator_component_pp", "denominator_component_pp")}
    require(set(values) == set(TERMS) and all(math.isfinite(value) for value in values.values()),
            "modeled mechanisms are missing or nonfinite")
    residual = target - math.fsum(values.values())
    require(abs(residual) < 1e-7, "modeled mechanism accounting does not reconcile")
    state_joint = state_row["joint"]
    before = [math.fsum(values) for values in state_joint]
    after = [math.fsum(values[j] for values in state_joint) for j in range(5)]
    v0, v1 = sum(before[:2]), sum(after[:2])
    a0, a1 = before[0] - before[1], after[0] - after[1]
    require(min(v0, v1) > 0, "positive modeled D/R denominators are required")
    joint = row.get("joint", state_joint)
    local_before = [math.fsum(values) for values in joint]
    local_after = [math.fsum(values[j] for values in joint) for j in range(5)]
    numerator = 50 * (1 / v0 + 1 / v1) * (
        local_after[0] - local_after[1] - local_before[0] + local_before[1])
    denominator = -50 * (a0 + a1) / (v0 * v1) * (
        sum(local_after[:2]) - sum(local_before[:2]))
    require(abs(numerator + denominator - target) < 1e-7,
            "shared-state-scale numerator/denominator accounting differs")
    return {
        **values, "accounting_residual_pp": residual,
        "numerator_component_pp": numerator, "denominator_component_pp": denominator,
        "numerator_denominator_is_alternative_partition_not_additional_mechanisms": True,
    }


def administrative(files):
    from scripts import results_native_dc as dc
    from scripts.results_county_frame import SUMMIT_PREDECESSOR, SUSSEX_PREDECESSOR
    from scripts.results_pdf_county_parent import SUMMIT_FEED, SUSSEX_FEED
    from scripts.results_turnout_history import GA_FEED
    from scripts.statewide_ballot_totals import NC_BASELINE_ID, ND_BASELINE_ID, OR_BASELINE_ID, identity as statewide_id

    index = decoded(files, "index.json")
    rows = []
    for state, declaration in sorted(index["states"].items()):
        shard = decoded(files, declaration["file"])
        records = shard["records"]
        legacy = {"NC": NC_BASELINE_ID, "ND": ND_BASELINE_ID, "OR": OR_BASELINE_ID}
        successor = statewide_id(state) if state in legacy and any(
            record["id"] == statewide_id(state) for record in records) else None
        superseded = {legacy[state]: successor} if successor else {}
        reviewed = {"UT": (SUMMIT_FEED, SUMMIT_PREDECESSOR), "NJ": (SUSSEX_FEED, SUSSEX_PREDECESSOR)}
        if state in reviewed:
            feed, predecessor = reviewed[state]
            canvass = [record["id"] for record in records if record["source"].get("id") == feed]
            require(len(canvass) <= 1, f"Ambiguous {feed} countywide canvass")
            if canvass:
                superseded[predecessor] = canvass[0]
        if state == "GA":
            newer = {record["geography"]["name"]: record["id"] for record in records
                     if record["source"]["id"] == GA_FEED and record["geography"]["level"] == "county"}
            if newer:
                available = set(shard["views"]["available"]["counties"])
                older = {record["geography"]["name"]: record["id"] for record in records
                         if record["id"] in available and record["geography"]["level"] == "county"
                         and record["measure"]["literal"] == "ballotsCast"}
                require(len(older) == len(newer) == 159 and set(older) == set(newer),
                        "Georgia legacy county export does not match the reviewed successors")
                superseded.update({identity: newer[name] for name, identity in older.items()})
        for record in records:
            count, denominator = record["count"], record.get("denominator")
            view = record.get("view") or {}
            qualified = bool(denominator and denominator.get("qualified"))
            value = count.get("value") if count["status"] == "reported" else None
            stock = denominator.get("value") if denominator else None
            rate = 100 * value / stock if qualified and value is not None and stock else None
            rows.append({
                "observation_id": record["id"], "state_code": state,
                "year": record["election"]["year"], "geography_level": record["geography"]["level"],
                "geography_id": record["geography"]["id"], "geography": record["geography"]["name"],
                "also_covers_full_jurisdiction": state == "DC" and dc.citywide_view(record) is not None,
                "measure": record["measure"]["literal"], "measure_kind": record["measure"]["kind"],
                "unit": record["measure"]["unit"], "mode": record["measure"]["mode"],
                "count_status": count["status"], "source_count": value,
                "superseded_by_observation_id": superseded.get(record["id"]),
                "registered_or_other_denominator": stock,
                "denominator_basis": denominator.get("basis") if denominator else None,
                "denominator_qualified": qualified, "compatible_source_fraction_pct": rate,
                "source_count_clock": record["source_clock"]["literal"],
                "source_timezone": record["source_clock"].get("timezone"),
                "source_publication_label": view.get("source_publication_label"),
                "source_publication_timezone": view.get("source_publication_timezone"),
                "source_view_status": view.get("status"),
                "source_reporting_status": (record.get("reporting_status") or {}).get("literal"),
                "source_url": record["source"]["url"],
                "input_sha256": record["source"]["input_sha256"],
                "not_unique_people_unless_separately_qualified": True,
                "rate_omission_reason": None if rate is not None else (
                    "Numerator is not reported." if value is None else
                    "No positive denominator qualified for this exact source measure, mode and geography."),
            })
    return rows


def administrative_coverage(rows):
    """Count export records, not people or proof of complete geography."""
    levels = {
        "state": "statewide", "county": "county_or_equivalent",
        "county_equivalent": "county_or_equivalent", "precinct": "precinct",
    }
    # Keep the existing catch-all totals. The new columns break out two of its
    # subgroups without changing the historical interpretation of that field.
    detail_levels = ("municipality", "reporting_unit")
    columns = ("statewide", "county_or_equivalent", "precinct", "other_geography", *detail_levels)
    inventory = {code: Counter() for code in STATES}
    for row in rows:
        counts = inventory[row["state_code"]]
        level = levels.get(row["geography_level"], "other_geography")
        status = row["count_status"]
        covered = ("county_or_equivalent", "statewide") if row.get("also_covers_full_jurisdiction") else (level,)
        if level == "other_geography" and row["geography_level"] in detail_levels:
            covered += (row["geography_level"],)
        for scope in covered:
            if row.get("superseded_by_observation_id"):
                counts[f"{scope}_superseded_records"] += 1
                continue
            counts[f"{scope}_{status}_records"] += 1
            if status != "reported":
                continue
            if row["measure_kind"] in {"returned", "early_activity"} or row["mode"] in {
                "in_person_early", "mail_returned"
            }:
                counts[f"{scope}_early_or_returned_records"] += 1
                continue
            if row["measure_kind"] not in {
                "ballots_cast", "voters_reported", "cards_cast", "participation_reported"
            }:
                continue
            counts[f"{scope}_election_participation_count_records"] += 1
            if row["compatible_source_fraction_pct"] is not None:
                counts[f"{scope}_election_participation_rate_records"] += 1
    fields = ("reported", "unknown", "withheld", "superseded", "early_or_returned",
              "election_participation_count", "election_participation_rate")
    return [
        {"state_code": code, "state": STATES[code], "year": 2026,
         **{f"{level}_{field}_records": counts[f"{level}_{field}_records"]
            for level in columns for field in fields}}
        for code, counts in sorted(inventory.items())
    ]


def recorded_states(estimates, model_rows):
    source = estimates["artifacts"]["house/recorded-states.json.gz"]["content"]["states"]
    result = []
    for row in source:
        state = row["state_code"]
        model = model_rows[state]
        previous, current = row["previous"], row["current"]
        n0, n1 = previous["D"] + previous["R"], current["D"] + current["R"]
        a0, a1 = previous["D"] - previous["R"], current["D"] - current["R"]
        raw0, raw1 = (100 * a0 / n0 if n0 else None), (100 * a1 / n1 if n1 else None)
        change = raw1 - raw0 if raw0 is not None and raw1 is not None else None
        numerator = 50 * (1 / n0 + 1 / n1) * (a1 - a0) if n0 and n1 else None
        denominator = -50 * (a0 + a1) / (n0 * n1) * (n1 - n0) if n0 and n1 else None
        residual = change - numerator - denominator if change is not None else None
        require(residual is None or abs(residual) < 1e-8, "recorded change accounting differs")
        qualified = model["source_comparison_available"]
        comparison = model.get("contest_comparability") or {}
        result.append({
            "state_code": state, "office": "U.S. House", "previous_year": 2024, "current_year": 2026,
            **{"previous_" + party: previous[party] for party in "DRO"},
            **{"current_" + party: current[party] for party in "DRO"},
            "previous_D_two_party_share_pct": 100 * previous["D"] / n0 if n0 else None,
            "previous_R_two_party_share_pct": 100 * previous["R"] / n0 if n0 else None,
            "current_D_two_party_share_pct": 100 * current["D"] / n1 if n1 else None,
            "current_R_two_party_share_pct": 100 * current["R"] / n1 if n1 else None,
            "previous_D_minus_R_margin_pp": raw0, "current_D_minus_R_margin_pp": raw1,
            "raw_recorded_margin_change_pp": change,
            "qualified_comparison": qualified,
            "qualified_margin_change_pp": change if qualified else None,
            "hold_reason": None if qualified else model["reported_comparison"].get("reason"),
            "coverage_changed_districts": comparison.get("coverage_changed_districts", []),
            "missing_count_districts": comparison.get("missing_count_districts", []),
            "multiple_same_party_nominee_districts":
                comparison.get("multiple_same_party_nominee_districts", []),
            "source_update_labels": row["source_update_labels"],
            "fresh_reported_inventory": row["fresh_reported_inventory"],
            "recorded_numerator_component_pp": numerator,
            "recorded_two_party_denominator_component_pp": denominator,
            "accounting_residual_pp": residual,
            "candidate_votes_are_not_ballots_or_turnout": True,
            "raw_change_is_not_preference_or_individual_switching": True,
        })
    return result


def explanations(estimates):
    states, groups = [], []
    for key in estimates["scenarios"]:
        result = estimates["artifacts"]["house/" + key + "/complete-result.json.gz"]["content"]
        profile, family = key.split("/")
        for row in result["rows"]:
            qualified = row["source_comparison_available"]
            common = {
                "state_code": row["state_code"], "profile": profile, "family": family,
                "office": "U.S. House", "estimated_baseline_year": 2024, "current_year": 2026,
                "source_comparison_qualified": qualified,
                "model_role": "conditional_explanation_of_qualified_comparison" if qualified
                    else "prior_source_scenario_not_an_explanation_of_recorded_change",
                "hold_reason": None if qualified else row["reported_comparison"].get("reason"),
                "scale": "D_minus_R_two_party_margin_percentage_points",
                "modeled_not_observed_individual_behavior": True,
                "first_ever_voting_or_new_eligibility_measured": False, "local_allocation": False,
            }
            states.append({
                **common, **mechanisms(row, row),
                "previous_margin_pp": row["point"]["previous_margin_pp"],
                "current_margin_pp": row["point"]["current_margin_pp"],
                "modeled_margin_change_pp": row["point"]["total_change_pp"],
                "assumed_common_frame_units": row["assumed_accounting_frame_units"],
                "sensitivity_ranges_pp": row.get("sensitivity_ranges_pp"),
            })
            for group in row["groups"]:
                available = group["available"]
                groups.append({
                    **common, "dimension": group["dimension"], "group": group["group"],
                    "label": group["label"], "available": available,
                    "omission_reason": None if available else
                        "Withheld in the accepted fitted public demographic support/disclosure decision.",
                    **mechanisms(group, row),
                    "contribution_to_state_margin_change_pp": group["total_contribution_pp"],
                    "sensitivity_ranges_pp": group.get("sensitivity_ranges_pp"),
                    "dimensions_are_separate_partitions_not_additive_together": True,
                    "scale": "group_contribution_to_state_D_minus_R_margin_percentage_points",
                })
    return states, groups


def recorded_districts(review, estimates):
    previous = {row["district"]: row for row in review["previous_district_queries"]}
    candidates = estimates["artifacts"]["rolling/next-seed.json.gz"]["content"]["accepted_candidates"]
    current = {}
    for row in candidates:
        current.setdefault(row["district"], []).append(row)
    require(set(previous) == set(current) and len(current) == 435,
            "district endpoint inventory is incomplete")
    result = []
    for district, rows in sorted(current.items()):
        before = previous[district]["previous"]
        counts = {party: 0 for party in "DRO"}
        for row in rows:
            label = row["party"].strip().lower()
            party = "D" if label in ("democratic", "democrat", "dem") else (
                "R" if label in ("republican", "rep") else "O")
            value = row["votes"]
            require(not isinstance(value, bool) and str(value).isdigit(),
                    "missing district votes cannot become zero")
            counts[party] += int(value)
        old = {}
        for party in "DRO":
            native = [row for row in before["source_candidate_rows"] if row["group"] == party]
            old[party] = None if any(row["votes"] is None for row in native) else sum(
                row["votes"] for row in native)
        n0 = old["D"] + old["R"] if old["D"] is not None and old["R"] is not None else None
        n1 = counts["D"] + counts["R"]
        m0 = 100 * (old["D"] - old["R"]) / n0 if n0 else None
        m1 = 100 * (counts["D"] - counts["R"]) / n1 if n1 else None
        result.append({
            "state_code": district[:2], "district_source_id": district, "office": "U.S. House",
            "previous_year": 2024, "current_year": 2026,
            **{"previous_" + party: old[party] for party in "DRO"},
            **{"current_" + party: counts[party] for party in "DRO"},
            "previous_D_two_party_share_pct": 100 * old["D"] / n0 if n0 else None,
            "previous_R_two_party_share_pct": 100 * old["R"] / n0 if n0 else None,
            "current_D_two_party_share_pct": 100 * counts["D"] / n1 if n1 else None,
            "current_R_two_party_share_pct": 100 * counts["R"] / n1 if n1 else None,
            "previous_D_minus_R_margin_pp": m0, "current_D_minus_R_margin_pp": m1,
            "raw_recorded_margin_change_pp": m1 - m0 if m0 is not None and m1 is not None else None,
            "previous_named_major_party_presence": before["major_party_presence"],
            "previous_missing_major_party_counts": before["missing_major_party_counts"],
            "previous_literal_party_labels": sorted({label for row in before["source_candidate_rows"]
                                                    for label in row["literal_parties"]}),
            "current_literal_party_labels": sorted({row["party"] for row in rows}),
            "qualified_geographic_comparison": False,
            "hold_reason": "A shared district source ID does not independently establish cross-year "
                           "boundary or election-round compatibility; raw records are not a qualified map.",
            "candidate_votes_are_not_ballots_or_turnout": True,
            "absent_nominee_is_not_zero_voter_preference": True,
        })
    return result


def attach_district_map_decisions(districts, congressional_races):
    by_district = {}
    for race in congressional_races:
        district = race["baseline"].get("district")
        if (district and race["chamber"] == "house"
                and race["voting_house_seat"] and race["advertised"]):
            by_district.setdefault(district, []).append(race)
    for row in districts:
        candidates = by_district.get(row["district_source_id"], [])
        if len(candidates) != 1:
            row.update(
                map_comparison_status="ambiguous" if candidates else "unavailable",
                map_comparison_holds=["Multiple advertised map races for this district" if candidates
                                      else "No advertised map race with this historical district"],
            )
            continue
        race, = candidates
        baseline = race["baseline"]
        boundary = baseline.get("boundary_eligibility", {})
        source = race["source"]
        qualified = race["qualified_comparison"]
        previous = race["previous"]
        swing = race["qualified_margin_change_pp"]
        require(not qualified or (previous is not None and type(swing) in (int, float)
                                  and math.isfinite(swing) and not race["comparison_holds"]),
                "Qualified district map has no verified swing")
        row.update(
            map_comparison_status="qualified" if qualified else "held",
            map_comparison_race_id=race["id"],
            map_current_source_updated_at=race["source_updated_at"],
            map_current_source_url=source.get("url"),
            map_current_source_sha256=source.get("sha256"),
            map_previous_year=baseline.get("year"),
            map_previous_stage=baseline.get("stage"),
            map_current_stage=race["stage"],
            map_previous_D=previous["D"] if qualified else None,
            map_previous_R=previous["R"] if qualified else None,
            map_current_D=race["D"] if qualified else None,
            map_current_R=race["R"] if qualified else None,
            map_qualified_margin_change_pp=swing if qualified else None,
            map_comparison_holds=race["comparison_holds"],
            map_boundary_compatible=boundary.get("boundary_compatible"),
            map_boundary_method=boundary.get("method"),
            map_boundary_review_version=boundary.get("review_version"),
            map_boundary_holds=boundary.get("holds"),
        )


def change_effects(changes, records, selected_observation_ids=None):
    by_id = {row["observation_id"]: row for row in records}
    result = []
    for change in changes:
        identity = change.get("id") or change.get("observation_id")
        row = by_id.get(identity)
        if row is None:
            continue
        state_level = row["geography_level"] == "state"
        refreshed = (selected_observation_ids is None or identity in selected_observation_ids
                     ) and change.get("source_status", "reported") == "reported"
        count_changed = change.get("previous") != change.get("current")
        result.append({
            "observation_id": identity, "state_code": row["state_code"],
            "source_capture_refreshed": refreshed,
            "numerical_count_changed": count_changed,
            "compatible_participation_rate_updated": (
                row["compatible_source_fraction_pct"] is not None and (refreshed or count_changed)),
            "compatible_participation_rate_available": row["compatible_source_fraction_pct"] is not None,
            "recorded_electoral_comparison_updated_by_this_count": False,
            "conditional_model_updated_by_this_count": False,
            "missing_electoral_prerequisite": "Same-office D/R candidate endpoints and comparison-stage "
                "qualification; participation counts are not candidate votes.",
            "missing_model_prerequisite": (
                "Exact accepted statewide registered-frame control identity/basis, or a separately "
                "reviewed election/population/office/ballot-stage joint probability bridge."
                if state_level else
                "This is a local/reporting-unit count, not the statewide registered frame of R*p "
                "and not a matched demographic/cohort joint choice-and-participation table."),
            "rate_basis": row["denominator_basis"], "source_count_clock": row["source_count_clock"],
        })
    return result


def other_offices(review):
    source = json.loads(input_body(review, "existing_other_office_models"))
    rows = []
    for row in source["rows"]:
        if row["office"] == "house":
            continue
        comparison, point = row["reported_comparison"], row.get("point")
        previous, current = comparison.get("previous", {}), comparison.get("current", {})
        values = point["components_pp"] if point else {}
        target = comparison.get("reported_change_pp")
        residual = target - math.fsum(values.values()) if point else None
        require(residual is None or abs(residual) < 1e-7,
                "existing other-office mechanism accounting differs")
        counts = {}
        for prefix, endpoint in (("previous", previous), ("current", current)):
            counts.update({prefix + "_" + party: endpoint.get(party) for party in "DRO"})
            d, r = endpoint.get("D"), endpoint.get("R")
            total = d + r if d is not None and r is not None else None
            counts[prefix + "_D_two_party_share_pct"] = 100 * d / total if total else None
            counts[prefix + "_R_two_party_share_pct"] = 100 * r / total if total else None
            counts[prefix + "_D_minus_R_margin_pp"] = 100 * (d - r) / total if total else None
        rows.append({
            "id": row["id"], "state_code": row["state_code"], "office": row["office"],
            "previous_year": comparison.get("baseline_year"), "current_year": 2026,
            **counts, "raw_recorded_margin_change_pp": target,
            "raw_recorded_D_share_change_pp": target / 2 if target is not None else None,
            "existing_source_comparison_status": comparison.get("status"),
            "existing_conditional_model_available": point is not None,
            "hold_reason": row.get("reason") or comparison.get("reason"),
            "previous_source_url": comparison.get("baseline_source_url"),
            "current_source_url": comparison.get("current_source_url"),
            "current_source_clock": comparison.get("current_native_clock"),
            "current_native_round": comparison.get("current_round"),
            "source_comparison_qualification": comparison.get("qualification"),
            "source_stage": comparison.get("current_stage"),
            "literal_previous_candidate_facts": comparison.get("native_candidate_facts"),
            "modeled_switching_pp": values.get("switching"),
            "modeled_exit_or_contest_nonparticipation_pp": values.get("nonparticipation"),
            "modeled_entry_return_pp": values.get("entry"),
            "modeled_other_choice_pp": values.get("other_choice"),
            "unresolved_prior_category": row.get("outside_candidate_category"),
            "accounting_residual_pp": residual, "sensitivity_ranges_pp": row.get("ranges_pp"),
            "assumed_common_frame_units": point.get("assumed_common_frame_units") if point else None,
            "scale": "D_minus_R_two_party_margin_percentage_points",
            "source_snapshot_reused_not_newly_acquired": True,
            "qualification_not_upgraded_by_this_export": True,
            "not_observed_individual_behavior_or_measured_staying_home": True,
            "nonparticipation_definition": row.get("nonparticipation_definition"),
        })
    return rows


def selected_local_observation_ids(snapshot, counts=None):
    from scripts import (
        philadelphia_divisions, results_indiana_turnout, results_minnesota_turnout, results_nc_vote_history,
        results_pa_vote_history, results_pdf_county_parent,
        oregon_turnout_history, results_turnout_history, statewide_ballot_totals, washington_participation,
    )
    from scripts.national_turnout_release_watch import INDEXES as NATIONAL_RELEASE_INDEXES
    from scripts.results_uf_turnout import IDENTITY as UF_IDENTITY
    from scripts.results_official_congress import CONTRACT as OFFICIAL_CONTRACT, IDENTITIES as OFFICIAL_IDENTITIES

    scope = snapshot.get("collection_scope") or {}
    if scope.get("mode") != "selected_registered_source_refresh":
        return None
    administrative_sources = {
        results_turnout_history.GA_FEED: "GA",
        results_turnout_history.OH_FEED: "OH",
        results_turnout_history.MT_FEED: "MT",
        results_turnout_history.WV_FEED: "WV",
        results_turnout_history.ND_CANVASS_FEED: "ND",
        **{feed: state for feed, (state, _) in results_turnout_history.municipal_feeds().items()},
        **{statewide_ballot_totals.PROFILES[code]["feed"]: code
           for code in ("KS", "NJ", "TX", "VA", "WA")},
        results_pdf_county_parent.PHILADELPHIA_FEED: "PA",
        results_pdf_county_parent.SUMMIT_FEED: "UT",
        results_pdf_county_parent.SUSSEX_FEED: "NJ",
        results_pdf_county_parent.DOUGLAS_FEED: "WI",
        results_pdf_county_parent.OKTIBBEHA_FEED: "MS",
        results_pdf_county_parent.WOODFORD_FEED: "IL",
        results_pdf_county_parent.LAWRENCE_FEED: "IL",
    }
    selected = set()
    for identity in scope["source_ids"]:
        if identity == UF_IDENTITY:
            require(snapshot.get("uf_turnout") is not None, "Selected statewide turnout source missing")
            continue
        if identity in OFFICIAL_IDENTITIES:
            entry = (snapshot.get("congress") or {}).get("official_candidate_evidence", {}).get(identity)
            data = (entry or {}).get("data")
            if (data is None and entry and entry.get("status")
                    and entry["status"] == entry.get("error")
                    and entry["status"] not in ("reported", "retained_after_failure")):
                continue  # An explicitly unsuccessful first check is not a turnout observation.
            require(isinstance(data, dict) and data.get("contract") == OFFICIAL_CONTRACT
                    and data.get("participation_observation_qualified") is False
                    and data.get("provider_other_equivalence_qualified") is False
                    and data.get("conditional_model_eligible") is False,
                    "Selected official candidate evidence missing or promoted")
            continue
        entry = snapshot.get("granular_sources", {}).get(identity)
        require(entry is not None, "Selected local source missing: " + identity)
        if identity == results_indiana_turnout.FEEDS[2026]:
            if statewide_ballot_totals.indiana_summary(snapshot) is not None:
                selected.add(statewide_ballot_totals.identity("IN"))
            continue
        if (identity in (philadelphia_divisions.FEED, results_nc_vote_history.FEED,
                         results_turnout_history.CA_CURRENT_FEED, results_turnout_history.NC_HISTORY_FEED,
                         results_turnout_history.nebraska_county_reports.FEED,
                         results_turnout_history.WY_HISTORY_FEED, results_turnout_history.WY_CANVASS_FEED)
                or identity in results_indiana_turnout.FEEDS.values()
                or identity in NATIONAL_RELEASE_INDEXES
                or identity in oregon_turnout_history.URLS
                or identity == washington_participation.FEED
                or identity in results_turnout_history.COUNTY_ARCHIVES
                or identity in results_pa_vote_history.FEEDS.values()):
            continue  # These products do not update a canonical cast-ballot count.
        if identity == results_minnesota_turnout.IDENTITY:
            local = snapshot["granular_sources"].get(results_minnesota_turnout.LOCAL_IDENTITY, {})
            if entry["status"] == local.get("status") == "reported":
                selected.add(statewide_ballot_totals.identity("MN"))
            continue
        if identity == results_minnesota_turnout.LOCAL_IDENTITY and entry["status"] != "reported":
            continue
        if identity in administrative_sources:
            if entry["status"] == "reported" and counts is not None:
                state = administrative_sources[identity]
                source_id = (statewide_ballot_totals.PROFILES[state]["source_id"]
                             if state in {"KS", "NJ", "TX", "VA", "WA"} else identity)
                declaration = decoded(counts, "index.json")["states"][state]
                selected.update(row["id"] for row in decoded(counts, declaration["file"])["records"]
                                if row["source"]["id"] == source_id)
            continue
        data = entry.get("data")
        require(isinstance(data, dict) and isinstance(data.get("updates"), list),
                "Selected local source has no observation updates: " + identity)
        selected.update(update["id"] for update in data["updates"])
        if identity in (statewide_ballot_totals.OR_FEED, statewide_ballot_totals.NC_FEED) and entry["status"] == "reported":
            selected.add(statewide_ballot_totals.identity(identity[:2]))
    return selected


def house_model_guard_matrix(decisions):
    families = {
        "candidate_identity": ("unmatched_new_named_candidate", "unmatched_or_ambiguous_named_major_candidate:",
                               "Major-party candidate coverage changed:", "Multiple same-party nominees:",
                               "Candidate inventory changed"),
        "other_write_in": ("aggregate_other_", "ambiguous_aggregate_other", "write_in_"),
        "source_universe": ("current_source_", "Candidate counts missing:", "native_official_source_",
                            "official_precedence_source_", "protected_official_source_"),
        "election_stage": ("Stage or RCV round not qualified:", "current_stage_", "current_round_"),
        "geography": ("current_state_district_inventory_changed", "current_district_inventory_"),
        "denominator": ("historical_statewide_source_frame_differs", "current_denominator_"),
        "scientific_eligibility": ("frozen_scientific_hold:",),
    }
    for row in decisions:
        bridge = row.get("congressional_analytical_status") or {}
        qualified = row["behaviorally_qualified"]
        eligible = bridge.get("automatic_update_eligible")
        if eligible is None:
            eligible = qualified and row["decision"] in {
                "changed_recompute_behavioral", "retained_fresh_unchanged"}
        reasons = bridge.get("holds")
        if reasons is None:
            reasons = [row["reason"]] if row.get("reason") else []
        grouped = {family: [] for family in (*families, "unclassified")}
        for reason in reasons:
            prefix = reason
            if reason.startswith("npr:house:"):
                prefix = reason.split(":", 7)[-1]
            matched = [family for family, prefixes in families.items() if prefix.startswith(prefixes)]
            for family in matched or ["unclassified"]:
                grouped[family].append(reason)
        yield {
            "state_code": row["state_code"], "decision": row["decision"],
            "scientific_comparison_qualified": qualified, "automatically_refreshable": eligible,
            "previously_qualified_model_frozen": qualified and not eligible,
            **{family + "_holds": value for family, value in grouped.items()},
            "all_holds": reasons,
        }


def build(snapshot, count_files, seed, estimates, changes, *, congressional_races=None):
    from scripts import cps_archived_state_tables as archived_cps
    from scripts import cps_published_state_tables as published_cps
    from scripts import results_indiana_turnout, results_nc_vote_history, results_turnout_history

    review = seed["supported_release_review"]
    require(review.get("contract") == REVIEW_CONTRACT, "unreviewed eligibility document")
    require(review["qualification_mask_sha256"] == seed["qualification"]["mask_sha256"],
            "eligibility review does not match the active scientific gate")
    require(review["source_models_refitted"] is False, "release must reuse the fitted models")
    historical = input_body(review, "historical_survey_csv")
    cps = json.loads(input_body(review, "historical_state_demographics"))["rows"]
    civic_data = json.loads(input_body(review, "modeled_demographics"))
    civic = civic_data["groups"]
    admin = administrative(count_files)
    admin_coverage = administrative_coverage(admin)
    model_rows = {
        row["state_code"]: row for row in estimates["artifacts"][
            "house/attenuated/accepted_ridge_multinomial/complete-result.json.gz"]["content"]["rows"]
    }
    recorded = recorded_states(estimates, model_rows)
    districts = recorded_districts(review, estimates)
    if congressional_races is not None:
        attach_district_map_decisions(districts, congressional_races)
    modeled, groups = explanations(estimates)
    selected = selected_local_observation_ids(snapshot, count_files)
    effects = change_effects(changes, admin, selected)
    house_guards = list(house_model_guard_matrix(estimates["decisions"]["states"]))
    raw_files = {
        "participation-administrative.csv": csv_bytes(admin),
        "participation-administrative-coverage.csv": csv_bytes(admin_coverage),
        "participation-historical-survey.csv": historical,
        "participation-historical-state-demographics.csv": csv_bytes(cps),
        "participation-modeled-demographics-2026.csv": csv_bytes(civic),
        "electoral-recorded-and-qualified.csv": csv_bytes(recorded),
        "electoral-recorded-districts.csv": csv_bytes(districts),
        "modeled-explanations.csv": csv_bytes(modeled),
        "modeled-demographic-explanations.csv": csv_bytes(groups),
        "source-to-analysis-effects.csv": csv_bytes(effects),
        "house-eligibility-decisions.csv": csv_bytes(review["house_decisions"]),
        "house-model-guard-matrix.csv": csv_bytes(house_guards),
        "registration-control-decisions.csv": csv_bytes(review["registration_decisions"]),
        "scoped-source-dispositions.csv": csv_bytes(review["source_dispositions"]["decisions"]),
        "house-and-control-update-decisions.csv": csv_bytes([
            *({"channel": "recorded_house_and_conditional_model", **row}
              for row in estimates["decisions"]["states"]),
            *({"channel": "registered_frame_conditional_R_times_p", **row}
              for row in estimates["participation"]["automatic_update"]["decisions"]),
        ]),
    }
    nc_history = results_nc_vote_history.rows(snapshot.get("granular_sources", {}))
    if nc_history:
        raw_files["participation-nc-vote-history-age.csv"] = csv_bytes(nc_history)
    indiana_history = results_indiana_turnout.rows(snapshot.get("granular_sources", {}))
    if indiana_history:
        raw_files["participation-indiana-general-turnout-history.csv"] = csv_bytes(indiana_history)
    from scripts import oregon_turnout_history, retained_bulk_turnout, washington_participation

    historical_sources = retained_bulk_turnout.historical_entries(
        snapshot.get("granular_sources", {}), seed.get("retained_bulk_turnout"))
    washington_rows = washington_participation.exports(historical_sources)
    if washington_rows:
        raw_files[washington_participation.CSV] = csv_bytes(washington_rows)
    oregon_rows = list(oregon_turnout_history.exports(historical_sources))
    if oregon_rows:
        raw_files[oregon_turnout_history.CSV] = csv_bytes(oregon_rows)
    county_archives = results_turnout_history.county_archive_rows(historical_sources)
    if county_archives:
        raw_files[results_turnout_history.COUNTY_ARCHIVE_CSV] = csv_bytes(county_archives)
    colorado_units = results_turnout_history.county_archive_rows(
        snapshot.get("granular_sources", {}), colorado_precincts=True)
    if colorado_units:
        raw_files["participation-co-precinct-voting-statistics.csv"] = csv_bytes(colorado_units)
    minnesota_units = results_turnout_history.county_archive_rows(
        historical_sources, minnesota_precincts=True)
    if minnesota_units:
        raw_files[results_turnout_history.minnesota_precinct_history.CSV] = csv_bytes(minnesota_units)
    maryland = results_turnout_history.maryland_precinct_history
    maryland_units, maryland_groups = maryland.exports(
        snapshot.get("granular_sources", {}), seed.get("md_retained_history"))
    if maryland_units:
        raw_files[maryland.ROW_CSV] = csv_bytes(maryland_units)
        raw_files[maryland.GROUP_CSV] = csv_bytes(maryland_groups)
    current_ca = results_turnout_history.county_archive_rows(
        snapshot.get("granular_sources", {}), current_california=True)
    if current_ca:
        raw_files[results_turnout_history.CA_CURRENT_CSV] = csv_bytes(current_ca)
    current_ne = results_turnout_history.county_archive_rows(
        snapshot.get("granular_sources", {}), current_nebraska=True)
    if current_ne:
        raw_files[results_turnout_history.nebraska_canvass.CSV] = csv_bytes(current_ne)
    partial_ne = results_turnout_history.nebraska_county_reports
    county_reports = partial_ne.rows(snapshot.get("granular_sources", {}))
    if any(row.get("ballots") is not None for row in county_reports):
        raw_files[partial_ne.CSV] = csv_bytes(county_reports)
    cps_workbooks = seed.get("cps_published_state_workbooks")
    published_rows = published_cps.build(cps_workbooks) if cps_workbooks is not None else []
    if published_rows:
        raw_files[published_cps.CSV] = published_cps.csv_body(published_rows)
    archived_rows = archived_cps.build(cps_workbooks) if cps_workbooks is not None else []
    if archived_rows:
        raw_files[archived_cps.CSV] = published_cps.csv_body(archived_rows)
    overall_rows = published_cps.build_overall(cps_workbooks) if cps_workbooks is not None else []
    if overall_rows:
        raw_files[published_cps.OVERALL_CSV] = published_cps.overall_csv(overall_rows)
    files = {"release/" + name + ".gz": compressed(body) for name, body in raw_files.items()}
    media_types = {path: "text/csv" for path in files}
    retained_offices = []
    if "existing_other_office_models" in review["frozen_inputs"]:
        retained_offices = other_offices(review)
        name = "release/existing-senate-governor-counts-and-mechanisms.csv.gz"
        files[name] = compressed(csv_bytes(retained_offices))
        media_types[name] = "text/csv"
        name = "release/existing-senate-governor-complete-queries.json.gz"
        files[name] = compressed(input_body(review, "existing_other_office_models"))
        media_types[name] = "application/json"
    for year in (1996, 1998, 2002):
        key = f"historical_{year}_points"
        path = f"release/historical-{year}-complete-points.json.gz"
        files[path] = compressed(input_body(review, key))
        media_types[path] = "application/json"
    current_admin = [row for row in admin if not row["superseded_by_observation_id"]]
    rate_rows = [row for row in current_admin if row["compatible_source_fraction_pct"] is not None]
    coverage = {
        "administrative": {
            "source_observations": len(admin),
            "reported_source_observations": sum(row["count_status"] == "reported" for row in current_admin),
            "superseded_source_observations": len(admin) - len(current_admin),
            "compatible_rate_frames": len(rate_rows),
            "rate_states": sorted({row["state_code"] for row in rate_rows}),
            "statewide_rate_states": [row["state_code"] for row in admin_coverage
                                      if row["statewide_election_participation_rate_records"]],
            "rates_by_denominator_basis": dict(Counter(row["denominator_basis"] for row in rate_rows)),
            "records_are_not_unique_people_or_complete_geographic_coverage": True,
        },
        "historical_survey": {
            "native_query_cells": sum(1 for _ in csv.DictReader(io.StringIO(historical.decode()))),
            "state_demographic_query_cells": len(cps),
            "state_demographic_years": sorted({row["year"] for row in cps}),
            **({"published_state_tables": published_cps.summary(published_rows)} if published_rows else {}),
            **({"archived_state_tables": published_cps.summary(archived_rows)} if archived_rows else {}),
            **({"published_state_overall_history": published_cps.overall_summary(overall_rows)} if overall_rows else {}),
            "early_native_source_point_years_kept_as_separate_populations": [1996, 1998, 2002],
            "statewide_survey_rates_not_allocated_locally": True,
        },
        "modeled_demographic_participation": {
            "query_cells": len(civic),
            "supported_broad_source_cells": sum(
                row["disposition"] == "selected_broad_source_model" for row in civic),
            "holds": dict(Counter(row["disposition"] for row in civic
                                  if row["disposition"] != "selected_broad_source_model")),
            "field_period": civic_data["field_period"],
            "population_representativeness_qualified": False,
            "not_administratively_observed_turnout": True,
        },
        "electoral_comparisons": {
            "recorded_state_comparisons": len(recorded),
            "raw_district_source_id_comparisons": len(districts),
            "new_cross_year_district_map_qualifications": 0,
            **({"linked_district_map_status_counts": dict(Counter(
                row["map_comparison_status"] for row in districts)),
                "linked_qualified_district_map_comparisons": sum(
                    row["map_comparison_status"] == "qualified" for row in districts)}
               if congressional_races is not None else {}),
            "qualified_state_comparisons": sum(row["qualified_comparison"] for row in recorded),
            "held_states": [row["state_code"] for row in recorded if not row["qualified_comparison"]],
            "raw_recorded_changes_separate_from_qualified_comparisons": True,
        },
        "modeled_explanations": {
            "profile_family_state_scenarios": len(modeled),
            "qualified_comparison_explanations": sum(row["source_comparison_qualified"] for row in modeled),
            "prior_only_scenarios_not_observed_change_explanations":
                sum(not row["source_comparison_qualified"] for row in modeled),
            "demographic_query_cells": len(groups),
            "available_demographic_cells": sum(row["available"] for row in groups),
            "all_released_accounts_reconcile_on_stated_scale": True,
        },
        "house_model_automation": {
            "automatically_refreshable_states": sum(row["automatically_refreshable"] for row in house_guards),
            "previously_qualified_frozen_states": sum(row["previously_qualified_model_frozen"] for row in house_guards),
            "state_rows": len(house_guards),
            "qualification_unchanged": True,
        },
        "registered_controls": {
            "state_dispositions": len(estimates["participation"]["states"]),
            "conditional_scenarios": len(estimates["participation"]["scenarios"]),
            "states_with_scenarios": len({row["state_code"]
                                          for row in estimates["participation"]["scenarios"]}),
            "automatic_update": estimates["participation"]["automatic_update"],
        },
        "existing_other_offices": {
            "source_snapshots": len(retained_offices),
            "conditional_models_available": sum(
                row["existing_conditional_model_available"] for row in retained_offices),
            "office_counts": dict(Counter(row["office"] for row in retained_offices)),
            "original_scientific_qualifications_and_source_dates_preserved": True,
            "not_freshly_retrieved_or_newly_qualified": True,
        },
    }
    descriptor = {
        "contract": CONTRACT, "election_date": "2026-11-03",
        "review_version": review["version"], "input_checked_at": snapshot.get("checked_at"),
        "collection_scope": snapshot.get("collection_scope"),
        "coverage": coverage, "downloads": {
            path: {"path": path, "compression": "gzip", "media_type": media_types[path], **pin(body)}
            for path, body in files.items()},
        "unchanged_scientific_downloads": review["unchanged_scientific_downloads"],
        "no_new_fit_or_geographic_allocation": True,
    }
    files["release/coverage-and-eligibility.json"] = encoded(descriptor)
    return {"files": files, "descriptor": descriptor}
