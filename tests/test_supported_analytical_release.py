import copy
import gzip

import pytest

from scripts import norc_house_model as model, supported_analytical_release as release
from scripts.participation_intake.contract import encoded, pin


def modeled_row():
    joint = [
        [.18, .04, .01, .02, 0],
        [.02, .16, .01, .03, .01],
        [.01, .01, .04, .01, 0],
        [.04, .02, .01, .30, .01],
        [0, .01, 0, .01, .04],
    ]
    return {"joint": joint, "point": model.accounting(joint)}


def test_explanation_accounts_keep_denominator_alternative_and_shared_state_group_scale():
    row = modeled_row()
    result = release.mechanisms(row, row)
    assert abs(result["accounting_residual_pp"]) < 1e-8
    assert result["numerator_component_pp"] + result["denominator_component_pp"] == pytest.approx(
        row["point"]["total_change_pp"])
    group = {"joint": [[value * .3 for value in values] for values in row["joint"]],
             "contributions_pp": {key: value * .3 for key, value in
                                  row["point"]["contributions_pp"].items()},
             "total_contribution_pp": row["point"]["total_change_pp"] * .3}
    small = release.mechanisms(group, row)
    assert small["numerator_component_pp"] == pytest.approx(result["numerator_component_pp"] * .3)
    assert small["denominator_component_pp"] == pytest.approx(result["denominator_component_pp"] * .3)
    assert small["numerator_denominator_is_alternative_partition_not_additional_mechanisms"]
    group["contributions_pp"]["switching"] += .01
    with pytest.raises(ValueError, match="accounting"):
        release.mechanisms(group, row)


def count_row(identity, *, qualified=True, unknown=False):
    return {
        "id": identity, "election": {"year": 2026},
        "geography": {"id": identity, "level": "county", "name": identity},
        "measure": {"literal": "Ballots Cast", "kind": "ballots_cast",
                    "unit": "source_reported_count", "mode": "source_defined"},
        "count": {"status": "unknown" if unknown else "reported",
                  "value": None if unknown else 0},
        "denominator": {"value": 100, "basis": "same_report_registered", "qualified": qualified},
        "source_clock": {"literal": None, "timezone": None},
        "source": {"url": "https://official.test/report", "input_sha256": "a" * 64},
    }


def test_guard_matrix_separates_frozen_models_and_preserves_every_evidence_reason():
    other = "npr:house:NE:1:regular:general:not_ranked:aggregate_other_not_reconciled_to_retained_minor_candidate_mass"
    stage = "Stage or RCV round not qualified: NE-01"
    unknown = "new_guard"
    frozen, active = release.house_model_guard_matrix([
        {"state_code": "NE", "decision": "held_retain_last_good", "behaviorally_qualified": True,
         "congressional_analytical_status": {"automatic_update_eligible": False, "holds": [other, stage, unknown]}},
        {"state_code": "RI", "decision": "retained_fresh_unchanged", "behaviorally_qualified": True,
         "congressional_analytical_status": {"automatic_update_eligible": True, "holds": []}},
    ])
    assert frozen["previously_qualified_model_frozen"]
    assert frozen["other_write_in_holds"] == [other]
    assert frozen["election_stage_holds"] == [stage]
    assert frozen["unclassified_holds"] == [unknown]
    assert frozen["all_holds"] == [other, stage, unknown]
    assert active["automatically_refreshable"] and not active["previously_qualified_model_frozen"]


def test_admin_export_preserves_zero_unknown_and_unqualified_context_as_distinct():
    rows = [count_row("zero"), count_row("unknown", unknown=True),
            count_row("context", qualified=False)]
    files = {"index.json": encoded({"states": {"NJ": {"file": "NJ.json.gz"}}}),
             "NJ.json.gz": gzip.compress(encoded({"records": rows}))}
    zero, unknown, context = release.administrative(files)
    assert zero["source_count"] == zero["compatible_source_fraction_pct"] == 0
    assert unknown["source_count"] is unknown["compatible_source_fraction_pct"] is None
    assert context["registered_or_other_denominator"] == 100
    assert context["compatible_source_fraction_pct"] is None
    assert unknown["source_count_clock"] is None
    assert context["rate_omission_reason"]


def test_administrative_coverage_keeps_partial_modes_and_reporting_units_separate():
    def row(level, kind="ballots_cast", mode="all_methods", status="reported", rate=None):
        return {"state_code": "ME", "geography_level": level, "measure_kind": kind,
                "mode": mode, "count_status": status, "compatible_source_fraction_pct": rate}

    states = release.administrative_coverage([
        row("state", rate=0),
        row("state", "returned", "mail_returned", rate=15),
        row("county_equivalent", "cards_cast", "source_defined"),
        row("county", status="unknown"),
        row("precinct", status="withheld"),
        row("reporting_unit", rate=20),
    ])
    by_state = {state["state_code"]: state for state in states}
    assert len(states) == len(by_state) == 51
    me = by_state["ME"]
    assert me["statewide_reported_records"] == 2
    assert me["statewide_early_or_returned_records"] == 1
    assert me["statewide_election_participation_count_records"] == 1
    assert me["statewide_election_participation_rate_records"] == 1
    assert me["county_or_equivalent_election_participation_count_records"] == 1
    assert me["county_or_equivalent_election_participation_rate_records"] == 0
    assert me["county_or_equivalent_unknown_records"] == 1
    assert me["precinct_withheld_records"] == 1
    assert me["precinct_election_participation_rate_records"] == 0
    assert me["other_geography_election_participation_rate_records"] == 1
    assert by_state["DC"]["statewide_reported_records"] == 0


def test_recorded_unopposed_change_is_descriptive_not_promoted_to_qualified_swing():
    estimates = {"artifacts": {"house/recorded-states.json.gz": {"content": {"states": [{
        "state_code": "VT", "previous": {"D": 0, "R": 100, "O": 20},
        "current": {"D": 25, "R": 75, "O": 30}, "source_update_labels": [],
        "fresh_reported_inventory": True,
    }]}}}}
    models = {"VT": {
        "source_comparison_available": False,
        "reported_comparison": {"reason": "Named major-party coverage changed"},
        "contest_comparability": {"coverage_changed_districts": ["VT-AL"]},
    }}
    row, = release.recorded_states(estimates, models)
    assert row["previous_D_minus_R_margin_pp"] == -100
    assert row["raw_recorded_margin_change_pp"] == 50
    assert row["qualified_margin_change_pp"] is None
    assert row["current_O"] == 30
    assert abs(row["accounting_residual_pp"]) < 1e-8
    assert row["candidate_votes_are_not_ballots_or_turnout"]


def test_count_handoff_does_not_turn_county_fraction_into_a_state_model_update():
    record = {
        "observation_id": "cape", "state_code": "NJ", "geography_level": "county",
        "compatible_source_fraction_pct": 55.19, "denominator_basis": "native_registered_voters",
        "source_count_clock": "11/12/2026 03:34PM",
    }
    effect, = release.change_effects(
        [{"observation_id": "cape", "previous": 42442, "current": 42442}], [record])
    assert effect["source_capture_refreshed"] and not effect["numerical_count_changed"]
    assert effect["compatible_participation_rate_updated"]
    assert not effect["conditional_model_updated_by_this_count"]
    assert "local/reporting-unit" in effect["missing_model_prerequisite"]
    assert not effect["recorded_electoral_comparison_updated_by_this_count"]
    reused, = release.change_effects(
        [{"observation_id": "cape", "previous": 42442, "current": 42442}], [record], {"walworth"})
    assert not reused["source_capture_refreshed"]
    assert not reused["compatible_participation_rate_updated"]
    assert reused["compatible_participation_rate_available"]
    retained, = release.change_effects([{"observation_id": "cape", "previous": 42442,
        "current": 42442, "source_status": "retained_after_failure"}], [record])
    assert not retained["source_capture_refreshed"]


def test_statewide_only_refresh_does_not_refresh_reused_local_observations():
    snapshot = {
        "collection_scope": {"mode": "selected_registered_source_refresh",
                             "source_ids": ["UF-national-turnout"]},
        "uf_turnout": {"status": "reported"},
        "granular_sources": {"local": {"data": {"updates": [{"id": "county"}]}}},
    }
    selected = release.selected_local_observation_ids(snapshot)
    assert selected == set()
    effect, = release.change_effects(
        [{"observation_id": "county", "previous": 0, "current": 0}],
        [{"observation_id": "county", "state_code": "ME", "geography_level": "county",
          "compatible_source_fraction_pct": None, "denominator_basis": None,
          "source_count_clock": None}], selected)
    assert not effect["source_capture_refreshed"]
    snapshot["collection_scope"]["source_ids"].append("local")
    assert release.selected_local_observation_ids(snapshot) == {"county"}
    snapshot["collection_scope"]["source_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="Selected local source missing"):
        release.selected_local_observation_ids(snapshot)
    snapshot["collection_scope"]["source_ids"] = ["UF-national-turnout"]
    del snapshot["uf_turnout"]
    with pytest.raises(ValueError, match="Selected statewide turnout source missing"):
        release.selected_local_observation_ids(snapshot)
    snapshot.pop("collection_scope")
    assert release.selected_local_observation_ids(snapshot) is None


def test_official_candidate_refresh_is_not_mislabeled_as_local_participation():
    from scripts.results_official_congress import CONTRACT, IDENTITY

    data = {"contract": CONTRACT, "participation_observation_qualified": False,
            "provider_other_equivalence_qualified": False, "conditional_model_eligible": False}
    snapshot = {
        "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": [IDENTITY]},
        "congress": {"official_candidate_evidence": {IDENTITY: {"data": data}}},
        "granular_sources": {"local": {"data": {"updates": [{"id": "county"}]}}},
    }
    assert release.selected_local_observation_ids(snapshot) == set()
    snapshot["collection_scope"]["source_ids"].append("local")
    assert release.selected_local_observation_ids(snapshot) == {"county"}
    for key in ("participation_observation_qualified", "provider_other_equivalence_qualified",
                "conditional_model_eligible"):
        data[key] = True
        with pytest.raises(ValueError, match="official candidate evidence missing or promoted"):
            release.selected_local_observation_ids(snapshot)
        data[key] = False
    data["contract"] = "unreviewed"
    with pytest.raises(ValueError, match="official candidate evidence missing or promoted"):
        release.selected_local_observation_ids(snapshot)
    snapshot["congress"]["official_candidate_evidence"].clear()
    with pytest.raises(ValueError, match="official candidate evidence missing or promoted"):
        release.selected_local_observation_ids(snapshot)


def test_scoped_administrative_refresh_attributes_only_matching_reported_counts():
    import json

    from scripts import philadelphia_divisions, results_pdf_county_parent, results_turnout_history

    mt = results_turnout_history.MT_FEED
    oh = results_turnout_history.OH_FEED
    phl = results_pdf_county_parent.PHILADELPHIA_FEED
    geo = philadelphia_divisions.FEED
    snapshot = {
        "collection_scope": {"mode": "selected_registered_source_refresh", "source_ids": [geo, mt, oh]},
        "granular_sources": {
            mt: {"status": "reported", "data": {"complete_native_query": {}}},
            oh: {"status": "retained_after_failure", "data": None},
            geo: {"status": "reported", "data": {"features": []}},
            phl: {"status": "reported", "data": {"complete_native_query": {}}},
        },
    }
    counts = {"index.json": json.dumps({"states": {
        state: {"file": state + ".json.gz"} for state in ("MT", "OH", "PA")
    }}).encode()}
    for state, rows in {"MT": [("state", mt)], "OH": [("ohio", oh), ("cuyahoga", "other")],
                        "PA": [("philadelphia", phl), ("elsewhere", "other")]}.items():
        counts[state + ".json.gz"] = release.compressed(json.dumps({"records": [
            {"id": identity, "source": {"id": source}} for identity, source in rows
        ]}).encode())
    assert release.selected_local_observation_ids(snapshot, counts) == {"state"}
    snapshot["collection_scope"]["source_ids"].append(phl)
    snapshot["granular_sources"][oh]["status"] = "reported"
    assert release.selected_local_observation_ids(snapshot, counts) == {"state", "ohio", "philadelphia"}


def test_held_group_and_frozen_source_tampering_do_not_become_numerical_outputs():
    held = {"contributions_pp": None, "total_contribution_pp": None}
    assert all(value is None for value in release.mechanisms(held, modeled_row()).values())
    body = b'{"published":"source"}\n'
    review = {"frozen_inputs": {"history": {"body": body.decode(), "pin": pin(body)}}}
    assert release.input_body(review, "history") == body
    tampered = copy.deepcopy(review)
    tampered["frozen_inputs"]["history"]["body"] = "{}"
    with pytest.raises(ValueError, match="input changed"):
        release.input_body(tampered, "history")


def test_existing_other_offices_keep_missing_other_counts_clocks_and_accounting_holds():
    source = {"rows": [{
        "id": "AL-senate", "state_code": "AL", "office": "senate",
        "reported_comparison": {"previous": {"D": 40, "R": 60},
            "current": {"D": 50, "R": 50, "O": 3}, "reported_change_pp": 20,
            "baseline_year": 2020, "current_native_clock": None},
        "point": {"components_pp": {"switching": 10, "nonparticipation": 5,
                                    "entry": 4, "other_choice": 1}},
    }]}
    body = encoded(source)
    review = {"frozen_inputs": {"existing_other_office_models": {
        "pin": pin(body), "body": body.decode()}}}
    row, = release.other_offices(review)
    assert row["previous_O"] is None and row["current_O"] == 3
    assert row["current_source_clock"] is None and row["accounting_residual_pp"] == 0
    source["rows"][0]["point"]["components_pp"]["switching"] += 1
    body = encoded(source)
    review["frozen_inputs"]["existing_other_office_models"] = {"pin": pin(body), "body": body.decode()}
    with pytest.raises(ValueError, match="accounting"):
        release.other_offices(review)
