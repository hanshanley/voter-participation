"""Use official House endpoints without refitting NORC or repeating unchanged seeds."""

import copy
from fractions import Fraction

from scripts import house_clerk_endpoints as native
from scripts import norc_house_model as model


HOLDS = {
    "AK": "The leading current non-Republican nominee is natively Nonpartisan, not Democratic; no caucus/coalition reassignment or ordinary D/R comparison is inferred.",
    "ME": "Cross-year ranked-choice round compatibility is not qualified by the held current controls; continuing/exhausted ballots are not candidate votes.",
    "PA": "Current district controls omit candidate totals; partial reported sums do not become statewide endpoints.",
}
SOURCE = "https://clerk.house.gov/member_info/electionInfo/2024/statistics2024.pdf"


def margin(counts):
    return Fraction(100*(counts["D"]-counts["R"]), counts["D"]+counts["R"])


def comparisons(facts, recap, held, previous):
    if facts["source_pdf_sha256"] != "d4ba800fc17135b616ae556c92861080ab962d95916ace34b546c5aac824aec4":
        raise ValueError("Only the reviewed native House Clerk original is allowed")
    candidates = native.candidate_totals(facts["candidate_party_lines"])
    if candidates != facts["candidates"]:
        raise ValueError("Candidate grouping differs from complete source lines")
    controls = {r["state_code"]: r for r in held["return_controls"] if r["office"] == "house"}
    if set(controls) != set(native.STATES) or len(controls) != 50:
        raise ValueError("Every held House-state control must remain explicit")
    old = {r["state_code"]: r for r in previous["rows"]}
    if set(old) != set(native.STATES):
        raise ValueError("Every accepted source-state scenario must remain")
    outputs = []
    for state in sorted(native.STATES):
        control = controls[state]
        selected = [r for r in candidates if r["state_code"] == state]
        previous_counts = {k: sum(r["votes"] for r in selected
                                 if r["counted_as"] == k and r["votes"] is not None)
                           for k in "DRO"}
        nonnumeric = [r for r in selected if r["votes"] is None]
        for row in nonnumeric:
            if (row["district"], row["source_lines"][0]["native_count"]) not in (
                    ("FL-20", "(1)"), ("OK-03", "(1)")):
                raise ValueError("An unexplained missing count cannot supply an endpoint")
        accounting = [r for r in facts["excluded_noncandidate_accounting"] if r["state_code"] == state]
        if sum(previous_counts.values())+sum(r["votes"] for r in accounting) != recap[state]["Total"]["value"]:
            raise ValueError("Candidate and noncandidate source rows differ from printed parent")
        for key, labels, column in (("D", native.DEMOCRATIC, "Democratic"),
                                    ("R", native.REPUBLICAN, "Republican")):
            line_total = sum(r["votes"] for r in facts["candidate_party_lines"]
                             if r["state_code"] == state and r["literal_party"] in labels
                             and r["votes"] is not None)
            if recap[state][column]["value"] is not None and line_total != recap[state][column]["value"]:
                raise ValueError("Native major-party line column differs")
        current, missing = dict(D=0, R=0, O=0), []
        current_districts = set()
        for index, row in enumerate(control["full_candidate_control_rows"]):
            current_districts.add(row["district"])
            value = row["reported_district_votes"]
            if value == "":
                missing.append(index)
                continue
            if not isinstance(value, str) or not value.isdigit():
                raise ValueError("Held candidate counts must be nonnegative literal integers")
            label = row["literal_party"].strip().lower()
            party = "D" if label in ("democratic", "democrat", "dem") else (
                "R" if label in ("republican", "rep") else "O")
            current[party] += int(value)
        if current != control["current"] or missing != control["missing_candidate_control_indices"]:
            raise ValueError("The accepted current counts or missingness changed")
        districts = {r["district"] for r in selected}
        if districts != current_districts:
            raise ValueError("The full source district inventory does not reconcile")
        reason = HOLDS.get(state)
        if missing:
            reason = HOLDS["PA"] if state == "PA" else "Native current district candidate counts are missing."
        common = dict(
            state_code=state, previous_candidate_counts=previous_counts,
            current_reported_candidate_subtotal=current, candidate_counts_are_not_ballots=True,
            baseline_pdf_sha256=facts["source_pdf_sha256"], baseline_source_url=SOURCE,
            baseline_year=2024, baseline_stage="November 5 general-election source",
            baseline_office="house", source_districts=sorted(districts),
            candidate_affiliations_not_party_line_columns=True,
            explicit_same_nominee_fusion_lines_aggregated=True,
            nonnumeric_native_candidate_rows=nonnumeric,
            noncandidate_accounting_not_added_to_candidate_counts=accounting,
            current_source_snapshot=control["source_snapshot"],
            current_native_clock=control["source_native_clock"],
            current_counting_complete=None, independent_behavioral_validation=False)
        if reason:
            comparison = dict(status="unavailable", reason=reason,
                              reported_change_pp=None, baseline_alignment_pp=None,
                              other_and_unallocated_pp=None)
        else:
            if any(previous_counts[k] <= 0 or current[k] <= 0 for k in "DR"):
                raise ValueError("A meaningful positive D/R denominator is required")
            before, after = margin(previous_counts), margin(current)
            comparison = dict(status="reported_source_comparison",
                previous=previous_counts, current=current, baseline_year=2024,
                baseline_office="house", baseline_stage="general",
                baseline_source="House Clerk official 2024 candidate counts; explicit same-nominee party lines combined",
                baseline_source_url=SOURCE, source_scope="All source districts; reported candidate votes, not ballots or population turnout",
                scope=f"All {len(districts)} House districts; whole-state counts without county or precinct allocation",
                current_year=2026, current_native_clock=control["source_native_clock"],
                current_snapshot=control["source_snapshot"], current_source_scope=control["source_scope"],
                current_stage=control.get("source_election_scope"),
                current_round=control.get("source_round"),
                previous_margin_pp=float(before), current_margin_pp=float(after),
                reported_change_pp=float(after-before), margin_definition="100 * (D - R) / (D + R)",
                independent_validation=False, source_coverage_certified=False,
                qualification="Changed competition, unopposed no-ballot contests and reporting affect counts; model N is not observed staying home.",
                native_nonnumeric_counts_preserved=bool(nonnumeric),
                direct_state_baseline_not_county_reconstruction=True)
        prior_comparison = old[state]["reported_comparison"]
        common.update(reported_comparison=comparison,
            old_comparison_available=old[state]["source_comparison_available"],
            old_reported_change_pp=prior_comparison.get("reported_change_pp"),
            old_previous_counts=prior_comparison.get("previous"),
            status="qualified_source_comparison" if reason is None else "held_source_comparison")
        outputs.append(common)
    return dict(status="qualified_direct_state_House_endpoint_decisions",
                rows=outputs, states=50, qualified=sum(r["status"] == "qualified_source_comparison" for r in outputs),
                previous_source_model_refitted=False, source_raw_respondents_exported=False)


def build(priors, previous, endpoints):
    by_state = {r["state_code"]: r for r in endpoints["rows"]}
    accepted = dict(rows=[dict(office="house", state_code=state,
        reported_comparison=row["reported_comparison"]) for state, row in by_state.items()])
    changed = []
    for row in previous["rows"]:
        new = by_state[row["state_code"]]["reported_comparison"]
        old = row["reported_comparison"]
        signature = lambda r: (r["status"], r.get("previous"), r.get("current"))
        if signature(old) != signature(new):
            changed.append(row["state_code"])
    calculated = model.build(priors, accepted, state_codes=changed) if changed else None
    result = copy.deepcopy(previous)
    old_rows = {r["state_code"]: r for r in previous["rows"]}
    replacements = {r["state_code"]: r for r in calculated["rows"]} if calculated else {}
    if set(replacements) != set(changed):
        raise ValueError("Every changed endpoint must have a newly calculated state")
    for row in result["rows"]:
        state = row["state_code"]
        if state in replacements:
            row.clear()
            row.update(replacements[state])
        row["reported_comparison"] = by_state[state]["reported_comparison"]
        if state not in changed:
            for key, value in old_rows[state].items():
                if key != "reported_comparison" and row[key] != value:
                    raise ValueError("Unchanged state was recalculated or mutated")
    for key in ("complete_assumption_cases", "complete_seed_cases", "complete_demographic_seed_cases"):
        old = [r for r in previous[key] if r["state_code"] not in changed]
        new = calculated[key] if calculated else []
        result[key] = sorted(old+new, key=lambda r: (
            r["state_code"], r.get("frame_scale", 0), r.get("affinity", 0),
            r.get("seed", 0), r.get("dimension", "")))
    rows = result["rows"]
    if sum(r["source_comparison_available"] for r in rows) != endpoints["qualified"]:
        raise ValueError("Qualified source endpoints and model anchors differ")
    if (len(result["complete_seed_cases"]) != len(previous["complete_seed_cases"])
            or len(result["complete_demographic_seed_cases"]) != len(previous["complete_demographic_seed_cases"])):
        raise ValueError("The complete state and demographic seed inventories must remain")
    result["preconditioning_margin_MAE_pp"] = sum(
        abs(r["before_current_party_conditioning"]["prediction_error_observed_minus_predicted_pp"])
        for r in rows if r["source_comparison_available"])/sum(r["source_comparison_available"] for r in rows)
    result["summary"] = dict(states=50,
        return_anchored=sum(r["source_comparison_available"] for r in rows),
        assumption_cases=len(result["complete_assumption_cases"]),
        seeds=len(result["complete_seed_cases"]),
        synthetic_agents=10000*len(result["complete_seed_cases"]),
        demographic_partition_seed_cases=len(result["complete_demographic_seed_cases"]),
        demographic_partition_agent_draws=10000*len(result["complete_demographic_seed_cases"]),
        complete_group_decisions=sum(len(r["groups"]) for r in rows))
    result["endpoint_update"] = dict(
        source="House Clerk 2024; reviewed held 2026 district controls",
        original_model_source="8f74ee8e4521d21142e8ee275cc154cb2bbfbd80",
        source_model_refitted=False, changed_states=sorted(changed),
        unchanged_state_numerics_and_seeds_reused=True,
        frozen_current_snapshot="20261107T125502Z",
        candidate_affiliations_and_noncandidate_exclusions_explicit=True,
        all_fifty_endpoint_decisions=endpoints["rows"])
    return result
