import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.automatic_estimates import (
    bind_publication, build, load_rolling_seed, load_rolling_seed_bytes,
    load_seed, render_artifacts,
)
from scripts import automatic_estimates, norc_house_model
from scripts.current_source_reconciliation import (
    BRIDGE_CONTRACT, ELECTION_DATE, EVIDENCE_CONTRACT, PROPOSAL_CONTRACT,
    STATE_CODES, canonical_sha256,
)


ROOT = Path(__file__).resolve().parents[1]


class AutomaticEstimateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = load_seed(ROOT / "data/results-intake/model-seed")

    def snapshot(self, seed=None):
        seed = seed or self.seed
        return {
            "contract": "participation.automatic_results_snapshot.v1",
            "election_date": "2026-11-03",
            "house_candidates": [
                dict(
                    row,
                    status="accepted_snapshot_not_refreshed",
                    source=None,
                    source_update_label=None,
                )
                for row in seed["accepted_candidates"]
            ],
            "house_states": [],
            "source_status": [],
            "participation_observations": [],
        }

    def report_state(self, snapshot, state, delta=0, guard=None):
        changed = False
        for row in snapshot["house_candidates"]:
            if row["state_code"] != state:
                continue
            row["status"] = "reported"
            row["source"] = {
                "url": "fixture://complete-state/" + state,
                "automatic_estimates_official_scope": guard,
            }
            row["source_update_label"] = "fixture-complete-1"
            if delta and row["party"] == "Democratic" and not changed:
                row["votes"] = str(int(row["votes"]) + delta)
                changed = True

    def state_decision(self, result, state):
        return next(
            row for row in result["decisions"]["states"]
            if row["state_code"] == state
        )

    def artifact_model(self, result, profile, family):
        return result["artifacts"][
            "house/{}/{}/complete-result.json.gz".format(profile, family)
        ]["content"]

    def synthetic_participation_seed(self, extra_scenario=False):
        display = {
            "contract": "participation.registered_control_display.v2",
            "states": [
                {
                    "state_code": state,
                    "control_id": "control-" + state,
                    "control_denominator_basis": "active_registered_voters",
                    "control_registered_denominator": "1000",
                    "control_native_time": None,
                    "control_source_url": "fixture://accepted",
                }
                for state in STATE_CODES
            ],
            "scenarios": [{
                "state_code": "OR",
                "control_id": "control-OR",
                "native_denominator_basis": "active_registered_voters",
                "native_registered_denominator": "1000",
                "conditional_modeled_voter_count": "600",
                "conditional_modeled_nonvoter_count": "400",
                "source_time_label": None,
                "source_url": "fixture://accepted",
            }],
        }
        if extra_scenario:
            display["scenarios"].append({
                **display["scenarios"][0],
                "control_id": "legacy-OR",
            })
        states = [state for state in STATE_CODES if state != "DC"]
        return {
            "participation_state_controls": display,
            "qualification": {
                "qualified_state_codes": states[:33],
                "held_state_codes": states[33:],
            },
        }

    def synthetic_participation_snapshot(self):
        return {
            "contract": "participation.automatic_results_snapshot.v1",
            "election_date": ELECTION_DATE,
            "participation_observations": [],
        }

    def cross_source_update(
        self, numerator="7", denominator="10", proposal_id="proposal-OR-01",
        observation_control="control-OR", target_control="control-OR",
        source_population="active_registered_voters",
    ):
        source_domain = {
            "election_date": ELECTION_DATE,
            "election_year": 2026,
            "geography": "state:OR",
            "population": source_population,
            "office_endpoint": "all_method_participation",
            "ballot_stage": "counted_all_methods",
        }
        target_domain = {
            **source_domain,
            "population": "active_registered_voters",
        }
        proposal = {
            "contract": PROPOSAL_CONTRACT,
            "proposal_id": proposal_id,
            "state_code": "OR",
            "kind": "cross_source_registered_probability",
            "source_role": "point_estimate_joint_bridge",
            "operation": "replace_registered_probability",
            "target_control_id": target_control,
            "bridge_id": "bridge-OR-01",
            "source_domain": source_domain,
            "target_domain": target_domain,
            "probability_numerator": numerator,
            "probability_denominator": denominator,
        }
        evidence = {
            "contract": EVIDENCE_CONTRACT,
            "evidence_id": "evidence-OR-01",
            "state_code": "OR",
            "target_control_id": target_control,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "operation": proposal["operation"],
            "sufficient_aggregate_joint_counts": True,
            "source_provenance": {
                "source_id": "fixture-reviewed-joint",
                "source_url": "fixture://reviewed-joint",
                "source_clock": "2026-11-04T00:00:00Z",
                "source_artifact_sha256": "b" * 64,
            },
            "joint_counts": {
                "participation_numerator": numerator,
                "population_denominator": denominator,
                "nonparticipant_complement": str(
                    int(denominator) - int(numerator)
                ),
            },
        }
        bridge = {
            "contract": BRIDGE_CONTRACT,
            "bridge_id": proposal["bridge_id"],
            "review_status": "approved",
            "review_scope": (
                "same_election_year_geography_population_endpoint_stage_joint"
            ),
            "reviewed_by": "fixture-reviewer",
            "reviewed_at": "synthetic-fixture-not-observed-time",
            "joint_population_observed": True,
            "supports_point_estimate_update": True,
            "supports_proposal_ids": [proposal_id],
            "proposal_sha256": canonical_sha256(proposal),
            "evidence_id": evidence["evidence_id"],
            "evidence_sha256": canonical_sha256(evidence),
            "target_control_id": target_control,
            "probability_numerator": numerator,
            "probability_denominator": denominator,
            "source_domain": source_domain,
            "target_domain": target_domain,
        }
        observation = {
            "state_code": "OR",
            "channel": "OR-fixture-joint-bridge",
            "status": "reported",
            "estimate_update": proposal,
            "observation": {
                "ballots": 500,
                "denominator": 1000,
                "denominator_basis": "active_registered_voters",
                "control_id": observation_control,
                "source_update_label": "fixture-joint-bridge",
                "source_url": "fixture://current",
                "estimate_domain": target_domain,
            },
        }
        return observation, bridge, evidence

    def test_real_accepted_seed_unchanged_reuses_every_state_and_query(self):
        result = build(self.snapshot(), self.seed)
        self.assertEqual(result["decisions"]["summary"]["changed_behavioral"], 0)
        self.assertEqual(result["decisions"]["summary"]["retained"], 50)
        for key, scenario in result["scenarios"].items():
            self.assertEqual(scenario["recomputed_states"], [])
            actual = self.artifact_model(result, *key.split("/"))
            self.assertEqual(actual, self.seed["scenarios"][key]["accepted_result"])

    def test_private_runtime_engine_is_exact_accepted_source(self):
        body = (ROOT / "scripts/norc_house_model.py").read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "b7492aa770436e88b734eb92701319cc109356cc4c254a1d0564a628316952cc",
        )

    def test_complete_supported_change_updates_all_nine_and_preserves_other_states(self):
        snapshot = self.snapshot()
        self.report_state(snapshot, "AR", delta=1000)
        result = build(snapshot, self.seed)
        self.assertEqual(result["decisions"]["summary"]["changed_behavioral"], 1)
        self.assertEqual(
            self.state_decision(result, "AR")["decision"],
            "changed_recompute_behavioral",
        )
        for key, scenario in result["scenarios"].items():
            self.assertEqual(scenario["recomputed_states"], ["AR"])
            old = self.seed["scenarios"][key]["accepted_result"]
            new = self.artifact_model(result, *key.split("/"))
            self.assertEqual(
                new["automatic_estimate_update"]["changed_states"],
                new["endpoint_update"]["changed_states"],
            )
            old_rows = {row["state_code"]: row for row in old["rows"]}
            new_rows = {row["state_code"]: row for row in new["rows"]}
            self.assertNotEqual(new_rows["AR"]["point"], old_rows["AR"]["point"])
            self.assertNotEqual(
                new_rows["AR"]["reported_comparison"]["current"],
                old_rows["AR"]["reported_comparison"]["current"],
            )
            self.assertEqual(new_rows["AZ"], old_rows["AZ"])
            for field in (
                "complete_assumption_cases",
                "complete_seed_cases",
                "complete_demographic_seed_cases",
            ):
                retained_old = [
                    row for row in old[field] if row["state_code"] != "AR"
                ]
                retained_new = [
                    row for row in new[field] if row["state_code"] != "AR"
                ]
                self.assertEqual(retained_new, retained_old)
        viewer = result["artifacts"]["house/viewer-original.json.gz"]["content"]
        row = next(
            row for row in viewer["state_comparisons"]
            if row["family"] == "accepted_ridge_multinomial"
            and row["state_code"] == "AR"
        )
        self.assertNotEqual(
            row["observed_margin_change_pp"],
            next(
                value for value in self.seed["profile_viewers"]["original"][
                    "state_comparisons"
                ]
                if value["family"] == "accepted_ridge_multinomial"
                and value["state_code"] == "AR"
            )["observed_margin_change_pp"],
        )

    def test_held_state_can_change_recorded_counts_but_never_behavioral_mask(self):
        snapshot = self.snapshot()
        self.report_state(snapshot, "AL", delta=500)
        result = build(snapshot, self.seed)
        self.assertEqual(
            self.state_decision(result, "AL")["decision"],
            "changed_recorded_behavioral_hold_preserved",
        )
        self.assertEqual(result["decisions"]["summary"]["changed_behavioral"], 0)
        recorded = result["artifacts"]["house/recorded-states.json.gz"]["content"]
        state = next(row for row in recorded["states"] if row["state_code"] == "AL")
        self.assertTrue(state["fresh_reported_inventory"])
        for key in result["scenarios"]:
            self.assertEqual(
                self.artifact_model(result, *key.split("/")),
                self.seed["scenarios"][key]["accepted_result"],
            )

    def test_partial_unknown_blocked_and_official_replacement_hold_without_aborting(self):
        snapshot = self.snapshot()
        first_ar = next(
            row for row in snapshot["house_candidates"] if row["state_code"] == "AR"
        )
        first_ar["status"] = "reported"
        first_ar["votes"] = str(int(first_ar["votes"]) + 100)
        first_ar["source"] = {"url": "fixture://partial"}
        first_ar["source_update_label"] = "partial"
        snapshot["source_status"].append({
            "source": "house-AZ-01", "status": "blocked_403", "error": "blocked_403"
        })
        self.report_state(snapshot, "HI", delta=100)
        result = build(snapshot, self.seed)
        self.assertEqual(
            self.state_decision(result, "AR")["decision"], "held_retain_last_good"
        )
        self.assertEqual(
            self.state_decision(result, "AZ")["decision"], "held_retain_last_good"
        )
        hi = self.state_decision(result, "HI")
        self.assertEqual(hi["decision"], "held_retain_last_good")
        self.assertIn("official_HI_WY", hi["reason"])
        self.assertEqual(result["decisions"]["summary"]["changed_behavioral"], 0)
        self.assertEqual(
            self.state_decision(result, "CO")["decision"],
            "retained_accepted_snapshot",
        )

    def test_official_guard_allows_same_scope_but_not_provider_replacement(self):
        snapshot = self.snapshot()
        guard = self.seed["official_source_guards"]["HI"]["guard_sha256"]
        self.report_state(snapshot, "HI", delta=100, guard=guard)
        result = build(snapshot, self.seed)
        self.assertEqual(
            self.state_decision(result, "HI")["decision"],
            "changed_recompute_behavioral",
        )
        self.assertTrue(
            self.state_decision(result, "HI")["accepted_official_scope_preserved"]
        )

    def test_real_version35_changed_R_uses_frozen_probability_and_retains_all_scenarios(self):
        snapshot = self.snapshot()
        snapshot["participation_observations"] = [{
            "state_code": "OR",
            "channel": "OR-official",
            "status": "reported",
            "source": {"url": "fixture://oregon-registered-frame"},
            "observation": {
                "ballots": 1992500,
                "denominator": 3109133,
                "denominator_basis": "active_registered_voters",
                "control_id": "reporting-OR",
                "source_update_label": None,
            },
        }]
        result = build(snapshot, self.seed)
        display = result["participation"]
        decisions = display["automatic_update"]["decisions"]
        self.assertEqual(len(display["states"]), 51)
        self.assertEqual(len(display["scenarios"]), 34)
        self.assertEqual(
            decisions[0]["decision"],
            "compatible_registered_frame_R_times_p_changed",
        )
        self.assertEqual(decisions[0]["registered_denominator_difference"], "10")
        self.assertFalse(decisions[0]["native_clock_supplied"])
        self.assertTrue(
            decisions[0]["source_weights_probabilities_and_fits_unchanged"]
        )
        old = next(
            row for row in self.seed["participation_state_controls"]["scenarios"]
            if row["control_id"] == "reporting-OR"
        )
        new = next(
            row for row in display["scenarios"]
            if row["control_id"] == "reporting-OR"
        )
        self.assertEqual(new["native_registered_denominator"], "3109133")
        self.assertIsNone(new["source_time_label"])
        self.assertEqual(
            float(new["conditional_modeled_voter_count"]) / 3109133,
            float(old["conditional_modeled_voter_count"]) / 3109123,
        )
        self.assertEqual(
            [
                row for row in display["scenarios"]
                if row["control_id"] != "reporting-OR"
            ],
            [
                row for row in self.seed["participation_state_controls"]["scenarios"]
                if row["control_id"] != "reporting-OR"
            ],
        )
        self.assertFalse(display["automatic_update"][
            "unsupported_local_or_demographic_estimates_created"
        ])

    def test_same_R_native_count_change_retains_exact_NC_projection(self):
        snapshot = self.snapshot()
        snapshot["participation_observations"] = [{
            "state_code": "NC",
            "channel": "NC-official",
            "status": "reported",
            "observation": {
                "ballots": 4243000,
                "denominator": 7885046,
                "denominator_basis": "active_and_inactive_registered_voters",
                "control_id": "reporting-NC",
                "source_update_label": "fixture-native-clock",
            },
        }]
        result = build(snapshot, self.seed)
        display = result["participation"]
        decision = display["automatic_update"]["decisions"][0]
        self.assertEqual(
            decision["decision"],
            "compatible_registered_frame_R_times_p_retained",
        )
        old = next(
            row for row in self.seed["participation_state_controls"]["scenarios"]
            if row["control_id"] == "reporting-NC"
        )
        new = next(
            row for row in display["scenarios"]
            if row["control_id"] == "reporting-NC"
        )
        self.assertEqual(
            new["conditional_modeled_voter_count"],
            old["conditional_modeled_voter_count"],
        )
        self.assertEqual(
            new["conditional_modeled_nonvoter_count"],
            old["conditional_modeled_nonvoter_count"],
        )

    def test_pinned_sufficient_evidence_is_qualified_but_held_for_v1_consumer(self):
        seed = self.synthetic_participation_seed()
        observation, bridge, evidence = self.cross_source_update()
        snapshot = self.synthetic_participation_snapshot()
        snapshot["participation_observations"] = [observation]
        snapshot["reviewed_joint_bridges"] = [bridge]
        snapshot["reviewed_joint_evidence"] = [evidence]
        result = automatic_estimates._participation(snapshot, seed)
        updated = result["scenarios"][0]
        self.assertEqual(updated["conditional_modeled_voter_count"], "600")
        self.assertEqual(updated["conditional_modeled_nonvoter_count"], "400")
        decision = result["automatic_update"]["decisions"][0]
        self.assertEqual(
            decision["decision"],
            "native_registered_reference_only",
        )
        self.assertEqual(
            decision["qualification"]["disposition"],
            "qualified_reviewed_joint_bridge",
        )
        self.assertEqual(
            decision["gate_subreason"],
            "requires_versioned_probability_consumer_contract",
        )
        self.assertEqual(
            result["automatic_update"]["qualified_cross_source_proposals_held"], 1
        )

    def test_wrong_observation_target_is_held_without_mutation(self):
        seed = self.synthetic_participation_seed(extra_scenario=True)
        observation, bridge, evidence = self.cross_source_update(
            observation_control="legacy-OR"
        )
        snapshot = self.synthetic_participation_snapshot()
        snapshot["participation_observations"] = [observation]
        snapshot["reviewed_joint_bridges"] = [bridge]
        snapshot["reviewed_joint_evidence"] = [evidence]
        result = automatic_estimates._participation(snapshot, seed)
        self.assertEqual(
            result["automatic_update"]["decisions"][0]["gate_subreason"],
            "held_observation_target_control_mismatch",
        )
        self.assertEqual(result["scenarios"], seed["participation_state_controls"][
            "scenarios"
        ])

    def test_duplicate_proposal_identity_holds_both_but_legacy_update_continues(self):
        seed = self.synthetic_participation_seed(extra_scenario=True)
        valid, bridge, evidence = self.cross_source_update()
        invalid, _, _ = self.cross_source_update(
            source_population="current_voters"
        )
        legacy = {
            "state_code": "OR",
            "channel": "legacy",
            "status": "reported",
            "observation": {
                "ballots": 500,
                "denominator": 1001,
                "denominator_basis": "active_registered_voters",
                "control_id": "legacy-OR",
                "source_url": "fixture://legacy",
            },
        }
        snapshot = self.synthetic_participation_snapshot()
        snapshot["participation_observations"] = [invalid, valid, legacy]
        snapshot["reviewed_joint_bridges"] = [bridge]
        snapshot["reviewed_joint_evidence"] = [evidence]
        result = automatic_estimates._participation(snapshot, seed)
        self.assertEqual(
            [row["qualification"]["disposition"]
             for row in result["automatic_update"]["decisions"][:2]],
            ["held_duplicate_proposal_identity"] * 2,
        )
        self.assertEqual(
            result["automatic_update"]["decisions"][2]["decision"],
            "compatible_registered_frame_R_times_p_changed",
        )
        legacy_result = next(
            row for row in result["scenarios"] if row["control_id"] == "legacy-OR"
        )
        target_result = next(
            row for row in result["scenarios"] if row["control_id"] == "control-OR"
        )
        self.assertEqual(legacy_result["native_registered_denominator"], "1001")
        self.assertEqual(target_result["conditional_modeled_voter_count"], "600")

    def test_malformed_proposal_is_held_not_exception(self):
        seed = self.synthetic_participation_seed()
        snapshot = self.synthetic_participation_snapshot()
        malformed = {
            "state_code": "OR",
            "channel": "malformed",
            "status": "reported",
            "estimate_update": [],
            "observation": {
                "denominator": 1000,
                "denominator_basis": "active_registered_voters",
                "control_id": "control-OR",
            },
        }
        snapshot["participation_observations"] = [malformed]
        result = automatic_estimates._participation(snapshot, seed)
        self.assertEqual(
            result["automatic_update"]["decisions"][0]["qualification"][
                "disposition"
            ],
            "held_invalid_proposal",
        )

    def test_zero_probability_qualifies_but_v1_estimator_keeps_frozen_probability(self):
        seed = self.synthetic_participation_seed()
        zero, bridge, evidence = self.cross_source_update("0", "10")
        snapshot = self.synthetic_participation_snapshot()
        snapshot["participation_observations"] = [zero]
        snapshot["reviewed_joint_bridges"] = [bridge]
        snapshot["reviewed_joint_evidence"] = [evidence]
        result = automatic_estimates._participation(snapshot, seed)
        self.assertEqual(result["scenarios"][0]["conditional_modeled_voter_count"], "600")
        self.assertEqual(
            result["automatic_update"]["decisions"][0]["gate_subreason"],
            "requires_versioned_probability_consumer_contract",
        )

        retained, bridge, evidence = self.cross_source_update("3", "5")
        snapshot["participation_observations"] = [retained]
        snapshot["reviewed_joint_bridges"] = [bridge]
        snapshot["reviewed_joint_evidence"] = [evidence]
        result = automatic_estimates._participation(snapshot, seed)
        update = result["automatic_update"]
        self.assertEqual(
            update["decisions"][0]["decision"],
            "native_registered_reference_only",
        )
        self.assertEqual(update["qualified_cross_source_proposals_held"], 1)
        self.assertEqual(update["changed_registered_frames"], 0)
        self.assertEqual(update["fresh_jurisdictions"], [])

    def test_rolling_seed_retains_run1_through_failure_then_accepts_run3(self):
        with patch(
            "scripts.automatic_estimates.accepted_model.build",
            wraps=norc_house_model.build,
        ) as engine:
            original = build(self.snapshot(), self.seed)
            seed0 = load_rolling_seed(
                original["artifacts"]["rolling/next-seed.json.gz"]["content"]
            )
            run1_snapshot = self.snapshot(seed0)
            self.report_state(run1_snapshot, "AR", delta=1000)
            run1_snapshot["participation_observations"] = [{
                "state_code": "OR",
                "channel": "OR-official",
                "status": "reported",
                "observation": {
                    "ballots": 1992500,
                    "denominator": 3109133,
                    "denominator_basis": "active_registered_voters",
                    "control_id": "reporting-OR",
                    "source_update_label": "run1",
                },
            }]
            run1 = build(run1_snapshot, seed0)
            seed1 = load_rolling_seed(
                run1["artifacts"]["rolling/next-seed.json.gz"]["content"]
            )
            run2_snapshot = self.snapshot(seed1)
            for row in run2_snapshot["house_candidates"]:
                if row["state_code"] == "AR":
                    row["status"] = "retained_after_failure"
                    row["source"] = {"url": "fixture://failed-run2"}
            run2_snapshot["source_status"] = [{
                "source": "house-AR-01",
                "status": "retained_after_failure",
                "error": "blocked_503",
            }]
            run2 = build(run2_snapshot, seed1)
            seed2 = load_rolling_seed(
                run2["artifacts"]["rolling/next-seed.json.gz"]["content"]
            )
            run3_snapshot = self.snapshot(seed2)
            self.report_state(run3_snapshot, "AR", delta=1000)
            run3 = build(run3_snapshot, seed2)
        self.assertEqual(engine.call_count, 18)
        self.assertEqual(
            self.state_decision(run2, "AR")["decision"],
            "held_retain_last_good",
        )
        for key in run1["scenarios"]:
            run1_model = self.artifact_model(run1, *key.split("/"))
            run2_model = self.artifact_model(run2, *key.split("/"))
            run3_model = self.artifact_model(run3, *key.split("/"))
            self.assertEqual(run2_model, run1_model)
            self.assertEqual(
                run2_model["automatic_estimate_update"]["changed_states"], ["AR"]
            )
            profile, family = key.split("/")
            self.assertEqual(
                run2["artifacts"]["house/viewer-" + profile + ".json.gz"]["content"][
                    "families"
                ][family]["automatic_estimate_update"],
                run1_model["automatic_estimate_update"],
            )
            by_state1 = {row["state_code"]: row for row in run1_model["rows"]}
            by_state3 = {row["state_code"]: row for row in run3_model["rows"]}
            self.assertNotEqual(by_state3["AR"]["point"], by_state1["AR"]["point"])
            self.assertEqual(by_state3["AZ"], by_state1["AZ"])
        or2 = next(
            row for row in run2["participation"]["scenarios"]
            if row["control_id"] == "reporting-OR"
        )
        or3 = next(
            row for row in run3["participation"]["scenarios"]
            if row["control_id"] == "reporting-OR"
        )
        self.assertEqual(or2["native_registered_denominator"], "3109133")
        self.assertEqual(or3, or2)
        ar_seed2 = next(
            row for row in seed2["accepted_candidates"]
            if row["state_code"] == "AR"
            and row["district"] == "AR-01"
            and row["name"] == "Terri Yarbrough Green"
        )
        self.assertEqual(ar_seed2["votes"], "61144")

    def test_retained_automatic_endpoint_repairs_missing_family_receipt_without_refit(self):
        snapshot = self.snapshot()
        self.report_state(snapshot, "AR", delta=1000)
        first = build(snapshot, self.seed)
        seed = load_rolling_seed(
            first["artifacts"]["rolling/next-seed.json.gz"]["content"]
        )
        for scenario in seed["scenarios"].values():
            scenario["accepted_result"].pop("automatic_estimate_update", None)
        with patch(
            "scripts.automatic_estimates.accepted_model.build",
            side_effect=AssertionError("Unchanged endpoints must not be reconditioned"),
        ):
            repaired = build(self.snapshot(seed), seed)
            following = build(
                self.snapshot(repaired["artifacts"]["rolling/next-seed.json.gz"]["content"]),
                repaired["artifacts"]["rolling/next-seed.json.gz"]["content"],
            )
        self.assertEqual(repaired["decisions"]["summary"]["changed_behavioral"], 0)
        for key in first["scenarios"]:
            profile, family = key.split("/")
            model = self.artifact_model(repaired, profile, family)
            self.assertEqual(model, self.artifact_model(first, profile, family))
            self.assertEqual(model, self.artifact_model(following, profile, family))
            self.assertEqual(model["automatic_estimate_update"]["changed_states"], ["AR"])
            self.assertEqual(
                repaired["artifacts"]["house/viewer-" + profile + ".json.gz"]["content"][
                    "families"
                ][family]["automatic_estimate_update"],
                model["automatic_estimate_update"],
            )
        broken_seed = copy.deepcopy(
            repaired["artifacts"]["rolling/next-seed.json.gz"]["content"]
        )
        next(iter(broken_seed["scenarios"].values()))[
            "accepted_result"
        ]["automatic_estimate_update"]["changed_states"] = []
        with self.assertRaisesRegex(ValueError, "receipt contradicts"):
            build(self.snapshot(broken_seed), broken_seed)

    def test_descriptor_pins_controls_and_rendered_accounting(self):
        result = build(self.snapshot(), self.seed)
        sources = result["house_sources"]
        self.assertEqual(len(sources["descriptors"]), 9)
        self.assertEqual(set(sources["controls"]), {"original", "attenuated", "full"})
        self.assertEqual(len(sources["qualification"]["qualified_state_codes"]), 33)
        self.assertEqual(len(sources["qualification"]["held_state_codes"]), 17)
        self.assertEqual(
            result["artifacts"]["house/sensitivity.json.gz"]["content"]["variant_count"],
            9,
        )
        self.assertEqual(
            result["artifacts"]["house/sensitivity.json.gz"]["content"]["summary"][
                "qualified_states"
            ],
            33,
        )
        self.assertIn("", sources["shared_max_abs_margin"])
        self.assertEqual(
            result["artifacts"][
                "participation/registered-control-display.json.gz"
            ]["content"]["contract"],
            "participation.registered_control_display.v2",
        )
        rendered = render_artifacts(result)
        self.assertEqual(set(rendered), set(result["artifacts"]))
        for path, body in rendered.items():
            self.assertEqual(body[9], 3)
            self.assertEqual(
                hashlib.sha256(body).hexdigest(),
                result["artifacts"][path]["sha256"],
            )
        for key, descriptor in sources["descriptors"].items():
            self.assertEqual(descriptor["control_key"], key)
            self.assertEqual(
                descriptor["qualification_mask_sha256"],
                sources["qualification"]["mask_sha256"],
            )
            self.assertTrue(descriptor["existing_17_behavioral_holds_preserved"])
            self.assertTrue(descriptor["official_HI_WY_scope_guarded"])
        rolling = load_rolling_seed_bytes(
            rendered["rolling/next-seed.json.gz"],
            sources["next_seed"],
        )
        self.assertEqual(rolling["contract"], "participation.automatic_estimates_seed.v1")
        bound = bind_publication(
            result,
            "https://raw.githubusercontent.com/example/repo/" + "a" * 40
            + "/data/automatic/" + sources["version"],
            {
                "url": "https://example.invalid/complete-results.zip",
                "bytes": 123,
                "sha256": "b" * 64,
                "media_type": "application/zip",
            },
        )
        self.assertTrue(bound["house_sources"]["publication_bound"])
        self.assertTrue(
            bound["house_sources"]["profile_viewers"]["original"][
                "viewer_data"
            ]["url"].endswith("/house/viewer-original.json.gz")
        )


if __name__ == "__main__":
    unittest.main()
