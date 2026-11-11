"""Compare participation controls and conditional current-register model scenarios."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile


EVIDENCE = {
    "nc-2026-reported-ballots-20261106": ("NC", "state", "reported_cast_ballots", "active_and_inactive_registered_voters"),
    "ga-2026-reported-ballots-20261107": ("GA", "state", "reported_cast_ballots", "unqualified_missing_county_denominators"),
    "co-2026-returned-processed-20261105": ("CO", "state", "returned_processed_ballots", "eligible_registered_including_election_day_preregistrants"),
    "fl-duval-2026-reported-ballots-20261107": ("FL", "county", "reported_cast_ballots", "county_registered_source_definition"),
    "nv-clark-2026-reported-ballots-20261106": ("NV", "county", "reported_cast_ballots", "county_current_registered_result_frame"),
    "oh-butler-2026-recorded-credit-20261107": ("OH", "county", "current_record_participation_credits", "current_county_registration_records"),
    "tx-harris-2026-counted-ballots-20261104": ("TX", "county", "counted_ballots", "county_registered_source_definition"),
    "ca-2026-native-voter-turnout-20261106": ("CA", "state", "native_voterTurnout_not_qualified_ballots", "native_totalRegisteredVoters_definition_unqualified"),
    "hi-2026-held-state-summary-report-3": ("HI", "state", "reported_cast_ballots", "registered_voters_source_definition"),
    "wy-2026-held-reconciled-county-ballots": ("WY", "state", "reported_cast_ballots", "registered_denominator_not_supplied"),
    "mn-2026-held-partial-precinct-statistics": ("MN", "partial_state_reporting_units", "reported_cast_ballots", "partial_precinct_registered_at_open_plus_election_day_registrations"),
    "vt-2026-held-municipal-registration": ("VT", "state", "native_municipal_Votes_Cast_not_qualified_ballots", "municipal_source_registered_voters_active_inactive_unspecified"),
    "id-2026-held-separate-ballot-report": ("ID", "state", "reported_cast_ballots", "unqualified_county_registration_disagreement"),
    "ri-2026-held-all-locality-ballots": ("RI", "state", "reported_cast_ballots", "native_state_totalVoters_registration_definition_unqualified"),
    "dc-2026-held-citywide-ballots": ("DC", "state", "reported_cast_ballots", "registered_voters_source_definition"),
    "fl-2026-held-statewide-eligible-active-register": (
        "FL", "state", "native_reported_participants_ballot_defined",
        "eligible_active_registered_voters_deadline_20261005_report_frame"),
}
REGISTERED = {
    "registered_voters_source_definition", "active_and_inactive_registered_voters",
    "active_registered_voters", "eligible_registered_including_election_day_preregistrants",
    "native_totalRegisteredVoters_definition_unqualified",
    "municipal_source_registered_voters_active_inactive_unspecified",
    "native_state_totalVoters_registration_definition_unqualified",
    "eligible_active_registered_voters_deadline_20261005_report_frame",
}
HOUSE_OFFICE = "U.S. House district contests aggregated within state"
INPUTS = {
    "civic-selected-aggregates.json", "uf-turnout.json", "reviewed-2026-observations.json",
    "published-reporting-controls.json", "published-reporting-complete-snapshot.zip",
    "house-state-party-totals.csv.gz",
}
HELD_INPUT = "held-precinct-participation-controls.zip"
ADDITIONAL_INPUTS = {"additional-reviewed-state-observations.json", "additional-state-control-sources.zip"}
FLORIDA_INPUT = "florida-complete-native-query.zip"


def florida_control(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        expected = {
            "source-qualification.json", "methods.json", "review-counties.py", "test_review_counties.py",
            "county-participation.csv", "statewide-participation.csv", "native-county-catalog.csv",
            "source-native-cells.csv", "audit.json", "checksums.json",
        }
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError("Changed complete Florida public numerical input set")
        native = {name: archive.read(name) for name in expected}
    checksums = json.loads(native["checksums.json"])["files"]
    if {row["path"] for row in checksums} != expected - {"checksums.json"}:
        raise ValueError("Incomplete Florida native checksums")
    for row in checksums:
        raw = native[row["path"]]
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("Changed Florida native input bytes")
    source = json.loads(native["source-qualification.json"])
    if (source["election_date"] != "2026-11-03"
            or source["source_as_of"] is not None or source["source_timezone"] is not None
            or any(source[key] is not False for key in
                   ("generic_turnout_approved", "county_fips_join_approved", "map_approved", "certified"))
            or source["headers"][1:4] != [
                "Voter Turnout", "Eligible Active Registered Voters", "Turnout Percentage"]
            or source["source_definition"]["native_registration_deadline_date"] != "2026-10-05"):
        raise ValueError("Changed Florida native frame, clock or approval contract")

    def rows(name):
        return list(csv.DictReader(io.StringIO(native[name].decode())))

    counties, statewide = rows("county-participation.csv"), rows("statewide-participation.csv")
    cells, catalog = rows("source-native-cells.csv"), rows("native-county-catalog.csv")
    source_rows = source["county_rows"] + [source["statewide_row"]]
    if (len(counties) != 67 or len(statewide) != 1 or len(cells) != 680 or len(catalog) != 67
            or len(source_rows) != 68 or statewide[0]["native_county"] != "TOTAL"
            or len({row["native_county"] for row in counties}) != 67
            or {row["county_literal"] for row in catalog} != {row["native_county"] for row in counties}):
        raise ValueError("Changed complete Florida county/state inventory")
    completion = []
    flag_fields = (
        "native_precincts_completed", "native_vote_by_mail_completed", "native_early_voting_completed",
        "native_provisional_completed", "native_10_day_overseas_completed",
    )
    for ordinal, (row, source_row) in enumerate(zip(counties + statewide, source_rows)):
        if len(source_row) != 10 or source_row[0]["text"] != row["native_county"]:
            raise ValueError("Changed Florida native row identity")
        participant, registered = (int(source_row[index]["text"].replace(",", "")) for index in (1, 2))
        if (participant != int(row["reported_participants"])
                or registered != int(row["eligible_active_registered_voters"])
                or registered <= 0 or not 0 <= participant <= registered
                or row["source_as_of"] or row["source_timezone"] or row["native_fips"]
                or row["analysis_rate_approved"] != "False" or row["map_approved"] != "False"):
            raise ValueError("Changed Florida native counts, missingness or approvals")
        with localcontext() as context:
            context.prec = 80
            percentage = 100 * Decimal(participant) / registered
            if percentage.quantize(Decimal(".01"), rounding=ROUND_HALF_UP) != Decimal(
                    source_row[3]["text"].rstrip("%")):
                raise ValueError("Florida native percentage/count disagreement")
        flags = []
        for column, cell in enumerate(source_row):
            frozen = cells[ordinal * 10 + column]
            if (int(frozen["source_row_ordinal"]) != ordinal or int(frozen["column_ordinal"]) != column
                    or frozen["literal_text"] != cell["text"]
                    or json.loads(frozen["native_span_classes"]) != cell["span_classes"]
                    or json.loads(frozen["declared_hrefs"]) != cell["hrefs"]):
                raise ValueError("Changed Florida native cell or status")
            if column >= 5:
                classes = cell["span_classes"]
                if ordinal < 67:
                    if classes not in ([["Y"]], [["N"]]):
                        raise ValueError("Invalid Florida literal completion flag")
                    flag = classes[0][0]
                else:
                    if classes not in ([], [[]]):
                        raise ValueError("Do not invent Florida statewide completion")
                    flag = None
                key = flag_fields[column - 5]
                if row[key] != (flag or ""):
                    raise ValueError("Changed Florida native completion query")
                flags.append(flag)
        if ordinal < 67:
            completion.append(dict(county=row["native_county"], flags=flags))
    total = statewide[0]
    numerator, denominator = int(total["reported_participants"]), int(total["eligible_active_registered_voters"])
    if (sum(int(row["reported_participants"]) for row in counties) != numerator
            or sum(int(row["eligible_active_registered_voters"]) for row in counties) != denominator):
        raise ValueError("Florida county sums differ from separate statewide total")
    with localcontext() as context:
        context.prec = 80
        rate = str(100 * Decimal(numerator) / denominator)
    reconciliation = dict(
        state_code="FL", year=2026, native_counties=67, native_cells=680,
        native_reported_participants=numerator, native_eligible_active_registered=denominator,
        native_turnout_percentage=total["native_turnout_percentage"],
        native_participants_per_eligible_active_registered_pct=rate,
        native_source_as_of=None, native_source_timezone=None,
        source_registration_definition=source["source_definition"],
        source_status=source["source_status"], county_completion_flags=completion,
        native_statewide_completion_flags=[None] * 5,
        county_sums_equal_separate_statewide_total=True,
        native_generic_turnout_approval=False, native_map_approval=False,
        participants_not_relabelled_as_generic_cast_ballot_counter=True,
        county_survey_allocations=0,
    )
    observation = dict(
        id="fl-2026-held-statewide-eligible-active-register", jurisdiction="Florida",
        scope="statewide separate native TOTAL; all 67 county sums reconcile",
        numerator=numerator, denominator=denominator,
        measure="native Voter Turnout reported participants; FAQ ballot definition retained",
        denominator_label="Eligible Active Registered Voters; source deadline October 5, 2026 at report generation",
        source_time_label="Native update time/timezone missing; held November 6 snapshot, not an as-of clock",
        source_url=source["source_url"], status=source["source_status"],
        scope_notes="Native statewide completion flags are blank; provisional/overseas county reporting unfinished."
        " Current-report registration frame is not final or independently matched to Civic."
        " Generic/map approval remains false; no county or demographic survey allocation.")
    return observation, reconciliation


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def csv_bytes(rows):
    if not rows:
        raise ValueError("Missing complete output query")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def held_controls(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        def load(name):
            raw = archive.read(name)
            return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)

        hi_audit = load("HI/audit.json")
        hi_pdf = load("HI/pdf-observations.json.gz")["histatewide.pdf"]
        hi_units = load("HI/participation.json.gz")
        text = gzip.decompress(archive.read("HI/originals/summary.txt.gz")).decode("utf-8-sig")
        hi_rows = list(csv.DictReader(io.StringIO(text.split("\n", 1)[1]), delimiter="\t"))
        wy_audit = load("WY/counts-review.json")
        wy_rows = list(csv.DictReader(io.StringIO(archive.read("WY/precinct-counts.csv").decode())))
        mn_audit = load("MN/participation-audit.json")
        mn_rows = list(csv.reader(io.StringIO(archive.read("MN/pctstats.txt").decode()), delimiter=";"))

    if hi_audit["year"] != 2026 or hi_audit["state_code"] != "HI" or hi_audit["source_certified"]:
        raise ValueError("Changed Hawaii held-election contract")
    hi_house = [row for row in hi_rows if row["Contest Title"] in
                {"U.S. Representative, Dist I", "U.S. Representative, Dist II"}]
    registration = {int(row["Registered Voters"]) for row in hi_house}
    contests = defaultdict(list)
    for row in hi_house:
        contests[row["Contest Title"]].append(row)
    if len(contests) != 2 or len(registration) != 1:
        raise ValueError("Hawaii statewide registration or House scope changed")
    hi_ballots = 0
    fields = [mode + " " + category for mode in ("Mail", "In-Person")
              for category in ("Blank Votes", "Over Votes", "Invalid Votes")]
    for rows in contests.values():
        accounting = {tuple(int(row[field]) for field in fields) for row in rows}
        if len(accounting) != 1 or len({row["Candidate ID"] for row in rows}) != len(rows):
            raise ValueError("Hawaii repeated accounting or candidate identity changed")
        if any(int(r["Total Votes"]) != int(r["Mail Votes"]) + int(r["In-Person Votes"]) for r in rows):
            raise ValueError("Hawaii native candidate mode counts differ")
        hi_ballots += sum(int(row["Total Votes"]) for row in rows) + sum(next(iter(accounting)))
    hi_registered = registration.pop()
    pdf_counts = hi_pdf["records"][0]["participation"]
    hi_unit_ballots = sum(row["ballots"] for row in hi_units)
    if (hi_ballots != pdf_counts["TOTAL TURNOUT"] or hi_registered != pdf_counts["TOTAL REGISTRATION"]
            or hi_ballots != hi_audit["source_summary_ballots"]
            or hi_unit_ballots != hi_audit["ballots"] or len(hi_units) != hi_audit["reporting_units"]
            or sum(row["registered"] for row in hi_units) != hi_registered):
        raise ValueError("Hawaii source-bound statewide/precinct reconciliation changed")

    wy_counties = defaultdict(int)
    wy_review = {row["county"]: row for row in wy_audit["counties"]}
    identities = set()
    for row in wy_rows:
        key = row["county"], row["precinct"]
        if (row["year"] != "2026" or row["state_code"] != "WY" or key in identities
                or row["registered_voters"] or row["turnout_rate"]
                or int(row["ballots"]) != sum(int(row[name]) for name in wy_audit["category_labels"])):
            raise ValueError("Wyoming native ballot scope or missing registration changed")
        identities.add(key)
        wy_counties[row["county"]] += int(row["ballots"])
    if (wy_audit["year"] != 2026 or wy_audit["state_code"] != "WY" or len(wy_counties) != 23
            or set(wy_counties) != set(wy_review) or len(wy_rows) != wy_audit["units"]
            or sum(wy_counties.values()) != wy_audit["statewide_ballots"]
            or any(total != wy_review[county]["printed_county_ballots"]
                   for county, total in wy_counties.items())):
        raise ValueError("Wyoming complete county/precinct ballot reconciliation changed")

    mn_reported = mn_ballots = mn_registered = mn_mismatches = 0
    identities = set()
    for row in mn_rows:
        if len(row) != 12 or row[0] != "MN" or row[4] not in {"0", "1"} or tuple(row[1:3]) in identities:
            raise ValueError("Minnesota held precinct identity/reporting contract changed")
        identities.add(tuple(row[1:3]))
        values = [int(value) for value in row[5:]]
        if min(values) < 0:
            raise ValueError("Minnesota missing/negative native statistics need explicit review")
        mn_registered += values[0] + values[1]
        mn_ballots += values[-1]
        mn_reported += row[4] == "1"
        mn_mismatches += values[-1] != sum(values[2:6])
    if (len(mn_rows) != mn_audit["rows"] or mn_reported == len(mn_rows)
            or mn_mismatches != mn_audit["ballot_mode_discrepancies"]):
        raise ValueError("Minnesota partial-reporting scope changed")

    reconciliation = dict(
        HI=dict(state_summary_ballots=hi_ballots, statewide_registered=hi_registered,
                native_unit_ballots=hi_unit_ballots, native_units=len(hi_units),
                unit_minus_summary_ballots=hi_unit_ballots-hi_ballots,
                precinct_rates_remain_withheld=True, registration_repeated_not_added=True),
        WY=dict(counties=len(wy_counties), native_units=len(wy_rows),
                statewide_ballots=sum(wy_counties.values()), registered_denominator=None,
                candidate_conflicts_retained=wy_audit["candidate_county_state_conflicts"]),
        MN=dict(native_units=len(mn_rows), reported_units=mn_reported,
                native_ballots_sum=mn_ballots, native_registered_sum=mn_registered,
                ballot_mode_discrepancies=mn_mismatches, statewide_control_qualified=False,
                native_update_time_supplied=False),
    )
    observations = []
    for identifier, jurisdiction, scope, numerator, denominator, clock, url, notes in [
        ("hi-2026-held-state-summary-report-3", "Hawaii", "statewide native summary",
         hi_ballots, hi_registered, hi_pdf["printed_on"],
         "https://elections.hawaii.gov/wp-content/results/2026%20General/histatewide.pdf",
         "REPORT 3, uncertified. Native unit ballots exceed the state summary by "
         + str(hi_unit_ballots-hi_ballots)
         + "; precinct registrations/rates remain unrepaired and withheld. State registration is repeated across contest rows, not added."),
        ("wy-2026-held-reconciled-county-ballots", "Wyoming", "statewide all 23 counties",
         sum(wy_counties.values()), None,
         "Held November 5, 2026 snapshot; county-native clocks retained, no common statewide clock qualified",
         "https://sos.wyo.gov/Elections/Docs/2026/2026GeneralResults.aspx",
         "Separate native ballots reconcile across all counties. Registration remains null; the Washakie candidate-category conflict is retained."),
        ("mn-2026-held-partial-precinct-statistics", "Minnesota", "partial statewide precinct statistics",
         mn_ballots, mn_registered,
         "Held 20261105-expansion-01 snapshot; no native update time supplied in the statistics file",
         "https://electionresultsfiles.sos.mn.gov/20261103/pctstats.txt",
         f"Only {mn_reported}/{len(mn_rows)} units flagged reported; {mn_mismatches} ballot-mode discrepancies."
         " Sums retain every native row, including zeros. Not statewide turnout or a state registration control."),
    ]:
        observations.append(dict(
            id=identifier, jurisdiction=jurisdiction, scope=scope, numerator=numerator, denominator=denominator,
            measure="native reported ballots", denominator_label=EVIDENCE[identifier][3],
            source_time_label=clock, source_url=url, status="unofficial_held_snapshot", scope_notes=notes))
    return observations, reconciliation


def controls(reporting, evidence):
    result = []
    for row in reporting:
        if row["denominator_basis"] not in REGISTERED | {"eligible_voters_source_estimate"}:
            raise ValueError("Unreviewed reporting denominator")
        result.append(dict(
            id="reporting-" + row["state_code"], state_code=row["state_code"], year=2026,
            geographic_level="state", geography=row["state"], source_family=row["source_url"],
            measure="reported_cast_ballots", native_measure="ballots",
            numerator=row["ballots"], denominator=row["denominator"],
            denominator_basis=row["denominator_basis"], denominator_label=row["denominator_basis"],
            source_time_label=row["source_update_label"], source_url=row["source_url"],
            native_status=row["status"], source_kind="published_reporting_snapshot",
            scope_notes="",
            selected_state_reference=False, disposition="pending_scope_review",
        ))
    for row in evidence["observations"]:
        if row["id"] not in EVIDENCE:
            raise ValueError("New observation requires an explicit measure/geography contract")
        state, level, measure, basis = EVIDENCE[row["id"]]
        if level == "state" and not row["scope"].startswith("statewide"):
            raise ValueError("Reviewed statewide source changed scope")
        result.append(dict(
            id=row["id"], state_code=state, year=2026, geographic_level=level,
            geography=row["jurisdiction"], source_family=row["source_url"], measure=measure,
            native_measure=row["measure"], numerator=row["numerator"], denominator=row["denominator"],
            denominator_basis=basis, denominator_label=row["denominator_label"],
            source_time_label=row["source_time_label"], source_url=row["source_url"],
            native_status=row["status"], source_kind="reviewed_public_observation",
            scope_notes=row.get("scope_notes", ""),
            selected_state_reference=False, disposition="pending_scope_review",
        ))
    families = defaultdict(list)
    for row in result:
        if row["geographic_level"] != "state":
            row["disposition"] = ("county_only_no_state_survey_allocation" if row["geographic_level"] == "county"
                                  else "partial_state_no_state_survey_allocation")
            continue
        families[row["state_code"], row["source_family"], row["measure"]].append(row)
    for rows in families.values():
        if len({(r["numerator"], r["denominator"]) for r in rows}) != 1:
            for row in rows:
                row["disposition"] = "different_snapshots_same_family_no_automatic_selection"
            continue
        ordered = sorted(rows, key=lambda row: (row["source_kind"] != "published_reporting_snapshot", row["id"]))
        ordered[0]["selected_state_reference"] = True
        ordered[0]["disposition"] = "selected_state_reference_not_independent_validation"
        for row in ordered[1:]:
            row["disposition"] = "same_source_same_counts_duplicate_not_added"
    states = Counter(row["state_code"] for row in result if row["selected_state_reference"])
    if any(n > 1 for n in states.values()):
        raise ValueError("Multiple distinct state controls require explicit selection")
    return result


def build(civic, uf, reporting, evidence, house):
    observed = controls(reporting, evidence)
    references = {row["state_code"]: row for row in observed if row["selected_state_reference"]}
    survey = {row["scope"]: row for row in civic["participation"]
              if row["dimension"] == "overall" and row["scope"] != "POOLED_SOURCE"}
    estimates = {row["STATE_ABV"]: row for row in uf if row["geographic_level"] == "state"}
    if len(survey) != 50 or "DC" in survey or len(estimates) != 51:
        raise ValueError("Changed registered-source or UF state/D.C. coverage")
    if any(row["ballots_status"] != "estimate" or row["year"] != 2026 for row in uf):
        raise ValueError("Changed UF estimate/year contract")
    house_votes = Counter()
    for row in house:
        if row["year"] != "2026" or row["office"] != HOUSE_OFFICE:
            raise ValueError("Changed House election/office scope")
        value = int(row["votes"])
        if value < 0:
            raise ValueError("Invalid literal House candidate count")
        house_votes[row["state_code"]] += value
    states, scenarios = [], []
    with localcontext() as context:
        context.prec = 80
        for state in sorted(estimates):
            source, control = survey.get(state), references.get(state)
            estimate = estimates[state]
            voter = nonvoter = None
            if source:
                total = Decimal(source["weight"])
                v, n = Decimal(source["modeled_voter_weight"]), Decimal(source["modeled_nonvoter_weight"])
                if total <= 0 or min(v, n) < 0 or v + n != total:
                    raise ValueError("Changed full Civic binary model denominator")
                voter, nonvoter = v / total, n / total
            registered = (control["denominator"] if control and
                          control["denominator_basis"] in REGISTERED else None)
            if registered is not None and (type(registered) is not int or registered <= 0):
                raise ValueError("Invalid native registration denominator")
            cast = (control["numerator"] if control and control["measure"] == "reported_cast_ballots"
                    else None)
            rate = str(100 * Decimal(cast) / registered) if cast is not None and registered else None
            common = dict(
                year=2026, state_code=state, civic_source_n=source["n"] if source else None,
                civic_modeled_voter_pct=str(100 * voter) if voter is not None else None,
                civic_modeled_nonvoter_pct=str(100 * nonvoter) if nonvoter is not None else None,
                civic_weight_target_qualified=False, civic_field_period_qualified=False,
                control_id=control["id"] if control else None,
                control_measure=control["measure"] if control else None,
                control_native_numerator=control["numerator"] if control else None,
                control_registered_denominator=registered,
                control_denominator_basis=control["denominator_basis"] if control else None,
                control_native_time=control["source_time_label"] if control else None,
                control_source_url=control["source_url"] if control else None,
                reported_cast_ballots=cast, reported_ballots_per_native_registered_denominator_pct=rate,
                uf_ballots_estimate=estimate["TOTAL_BALLOTS_COUNTED"],
                uf_ballots_status=estimate["ballots_status"], uf_vep_estimate=estimate["VEP"],
                uf_vep_turnout_estimate=estimate["VEP_TURNOUT_RATE"],
                uf_vep_is_not_a_registered_denominator=True,
                house_candidate_vote_sum_context=house_votes.get(state),
                house_votes_are_not_ballots_or_unique_voters=True,
                conditional_registered_frame_scenario_available=registered is not None and source is not None,
                original_coalition_population_count=None, death_component=None,
                migration_component=None, eligibility_component=None,
            )
            states.append(common)
            if registered is not None and source is not None:
                expected_voters, expected_nonvoters = registered * voter, registered * nonvoter
                if abs(expected_voters + expected_nonvoters - registered) > Decimal("1e-60"):
                    raise ValueError("Conditional current-register partition failed")
                scenarios.append(dict(
                    year=2026, state_code=state, control_id=control["id"],
                    control_measure=control["measure"], control_native_status=control["native_status"],
                    native_registered_denominator=registered,
                    native_denominator_basis=control["denominator_basis"],
                    source_time_label=control["source_time_label"], source_url=control["source_url"],
                    civic_source_n=source["n"], civic_weight=source["weight"],
                    civic_modeled_voter_weight=source["modeled_voter_weight"],
                    civic_modeled_nonvoter_weight=source["modeled_nonvoter_weight"],
                    conditional_modeled_voter_count=str(expected_voters),
                    conditional_modeled_nonvoter_count=str(expected_nonvoters),
                    reported_cast_ballot_measure_control=cast,
                    reported_cast_minus_conditional_modeled_voter_count=(
                        str(Decimal(cast)-expected_voters) if cast is not None else None),
                    assumption="native registered denominator is exchangeable with this source-weighted survey propensity",
                    scenario_units="native_registered_denominator_units_not_administratively_observed_people",
                    assumption_validated=False, survey_weight_target_qualified=False,
                    same_frame_and_cutoff_independently_qualified=False,
                    bridge_outcome_calibration_applied=False,
                    model_nonvoter_is_administratively_observed_staying_home=False,
                    original_coalition_population_count=None, death_component=None,
                    migration_component=None, eligibility_component=None,
                ))
    summary = dict(
        status="conditional_current_registered_frame_scenarios_not_observed_voter_counts",
        state_and_dc_query_rows=len(states), native_control_query_rows=len(observed),
        selected_state_control_rows=len(references),
        exact_same_source_duplicates_not_added=sum(
            r["disposition"] == "same_source_same_counts_duplicate_not_added" for r in observed),
        county_controls_retained_not_allocated=sum(r["geographic_level"] == "county" for r in observed),
        partial_state_controls_retained_not_allocated=sum(
            r["geographic_level"] == "partial_state_reporting_units" for r in observed),
        conditional_registered_frame_scenarios=len(scenarios),
        scenarios_with_reported_cast_ballot_comparison=sum(
            r["reported_cast_ballot_measure_control"] is not None for r in scenarios),
        scenario_states=[r["state_code"] for r in scenarios],
        official_cast_control_states=[r["state_code"] for r in states if r["reported_cast_ballots"] is not None],
        notes=[
            "R*p and R*(1-p) are explicit conditional current-register scenarios, not observed people staying home.",
            "Civic weight target/calibration and field period remain unqualified; exchangeability to each native registration frame is not validated.",
            "No new bridge outcome calibration is applied; this does not establish that the original source weights were uncalibrated or independently validated.",
            "Active, all-registered, eligible/pre-registered and source-undefined registration frames are not silently harmonized.",
            "Reported state cast-ballot controls are unofficial/incomplete-count snapshots, not certified final turnout.",
            "Colorado returned/processed and California source-labeled voterTurnout do not become cast-ballot controls.",
            "The duplicate North Carolina source is retained but never added twice.",
            "County-only controls remain separate; no state survey estimate is allocated to a county.",
            "Partial-state precinct statistics are retained separately, never used as statewide controls or survey allocation targets.",
            "Hawaii uses its declared statewide summary, not the differing native-unit ballot sum; precinct rates remain withheld.",
            "Wyoming's whole-state ballot count supplies no registration denominator or conditional population scenario.",
            "Vermont native Votes Cast remains distinct from qualified cast ballots; its source municipal registration frame is not harmonized.",
            "Idaho registration disagreements remain a denominator hold. Rhode Island uses its explicit parent registration total, not a repair of Federal-unit zero registration.",
            "D.C. citywide counts do not create a nonexistent Civic sample or conditional survey scenario.",
            "UF initial ballot/VEP estimates remain estimates. VEP is not used as a registered denominator.",
            "House candidate vote sums are office-specific context, not ballots or unique voters.",
            "Missing registered controls remain null, including North Dakota's unsupplied eligible denominator.",
            "D.C. has no allocated Civic survey estimate. No national population bridge is constructed.",
            "No original-coalition, eligibility, death or migration quantities are inferred; unknowns remain null.",
            "Arithmetic discrepancies remain visible; no outcome fitting, partisan reweighting or confidence interval is applied.",
        ])
    return {
        "complete-state-control-query.csv": csv_bytes(states),
        "complete-native-control-dispositions.csv": csv_bytes(observed),
        "complete-conditional-registered-scenarios.csv": csv_bytes(scenarios),
        "summary.json": json_bytes(summary),
    }, summary


def export(inputs, output):
    if output.exists():
        raise ValueError("Refusing to overwrite an existing analysis")
    manifest = json.loads((inputs / "source-manifest.json").read_bytes())
    if (set(manifest["inputs"]) not in (
            INPUTS, INPUTS | {HELD_INPUT}, INPUTS | {HELD_INPUT} | ADDITIONAL_INPUTS,
            INPUTS | {HELD_INPUT} | ADDITIONAL_INPUTS | {FLORIDA_INPUT})
            or manifest.get("original_raw_survey_or_voter_records_included") is not False):
        raise ValueError("Unapproved or nonpublic aggregate input set")
    native = {}
    for name, receipt in manifest["inputs"].items():
        if Path(name).name != name:
            raise ValueError("Unqualified aggregate input path")
        content = (inputs / name).read_bytes()
        if len(content) != receipt["bytes"] or hashlib.sha256(content).hexdigest() != receipt["sha256"]:
            raise ValueError("Changed frozen public aggregate input")
        native[name] = content
    with gzip.open(io.BytesIO(native["house-state-party-totals.csv.gz"]), "rt", newline="") as stream:
        house = list(csv.DictReader(stream))
    evidence = json.loads(native["reviewed-2026-observations.json"])
    reconciliation = None
    if HELD_INPUT in native:
        observations, reconciliation = held_controls(native[HELD_INPUT])
        evidence["observations"].extend(observations)
    additional = None
    if ADDITIONAL_INPUTS <= native.keys():
        additional = json.loads(native["additional-reviewed-state-observations.json"])
        if (additional.get("raw_individual_records_included") is not False
                or {r["id"] for r in additional["observations"]} != {
                    "vt-2026-held-municipal-registration", "id-2026-held-separate-ballot-report",
                    "ri-2026-held-all-locality-ballots", "dc-2026-held-citywide-ballots"}
                or len(additional["observations"]) != 4):
            raise ValueError("Changed additional reviewed state-control contract")
        evidence["observations"].extend(additional["observations"])
    florida = None
    if FLORIDA_INPUT in native:
        observation, florida = florida_control(native[FLORIDA_INPUT])
        evidence["observations"].append(observation)
    files, summary = build(
        json.loads(native["civic-selected-aggregates.json"]), json.loads(native["uf-turnout.json"]),
        json.loads(native["published-reporting-controls.json"]),
        evidence, house)
    if reconciliation is not None:
        files["complete-held-source-reconciliation.json"] = json_bytes(reconciliation)
    if additional is not None:
        files["complete-additional-state-source-reconciliation.json"] = json_bytes(additional["reconciliation"])
    if florida is not None:
        files["complete-florida-native-source-reconciliation.json"] = json_bytes(florida)
        scenario = next(row for row in csv.DictReader(io.StringIO(
            files["complete-conditional-registered-scenarios.csv"].decode())) if row["state_code"] == "FL")
        with localcontext() as context:
            context.prec = 80
            comparison = dict(
                year=2026, state_code="FL", control_id=scenario["control_id"],
                native_measure="Voter Turnout; source-defined reported participants",
                native_reported_participants=florida["native_reported_participants"],
                native_eligible_active_registered=florida["native_eligible_active_registered"],
                native_turnout_percentage=florida["native_turnout_percentage"],
                native_participants_per_eligible_active_registered_pct=(
                    florida["native_participants_per_eligible_active_registered_pct"]),
                native_source_as_of=None, native_source_timezone=None,
                native_registration_deadline="2026-10-05",
                native_statewide_completion_qualified=False,
                native_participants_are_generic_cast_ballot_counter=False,
                civic_source_n=scenario["civic_source_n"], civic_weight=scenario["civic_weight"],
                civic_modeled_voter_weight=scenario["civic_modeled_voter_weight"],
                civic_modeled_nonvoter_weight=scenario["civic_modeled_nonvoter_weight"],
                conditional_modeled_voter_count=scenario["conditional_modeled_voter_count"],
                conditional_modeled_nonvoter_count=scenario["conditional_modeled_nonvoter_count"],
                native_participants_minus_conditional_modeled_voter_count=str(
                    Decimal(florida["native_reported_participants"])
                    - Decimal(scenario["conditional_modeled_voter_count"])),
                assumption_validated=False, independent_population_validation=False,
                observed_staying_home=False, demographic_or_local_survey_allocation=False,
            )
        files["complete-florida-native-state-comparison.csv"] = csv_bytes([comparison])
        summary["florida_native_participant_comparison_rows"] = 1
        summary["notes"].append(
            "Florida's native Voter Turnout and eligible-active register are retained with "
            "the source October 5 deadline/report-generation frame, missing native clock and "
            "unfinished county ballot flags. Native participant/model comparison is separate "
            "from generic cast-ballot controls; no map, certification, group population or "
            "independent Civic-frame qualification is granted.")
        files["summary.json"] = json_bytes(summary)
    files.update({"inputs/" + name: content for name, content in native.items()})
    files["inputs/source-manifest.json"] = json_bytes(manifest)
    files["scripts/participation_controls.py"] = Path(__file__).read_bytes()
    files["tests/test_participation_controls.py"] = Path(__file__).parents[1].joinpath(
        "tests/test_participation_controls.py").read_bytes()
    files["README.txt"] = (
        "Current registered-frame conditional participation scenarios, not observed staying home.\n"
        "All permitted aggregate inputs, complete state/native-control/scenario queries, code and tests included.\n"
        "No raw respondents, voter identifiers, original-coalition populations or county allocations.\n"
        "From the unpacked complete archive, without packages/network:\n"
        "  python3 -m unittest discover -s tests -p test_participation_controls.py\n"
        "  python3 -m scripts.participation_controls --inputs inputs --output reproduced\n"
        "Read all frame, cutoff, measure and conditional-assumption qualifications in summary.json.\n"
    ).encode()
    files["checksums.json"] = json_bytes({
        name: dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        for name, content in sorted(files.items())})
    output.mkdir(parents=True)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with zipfile.ZipFile(output / "complete-analysis.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps({key: value for key, value in summary.items() if key != "notes"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.inputs, args.output)
