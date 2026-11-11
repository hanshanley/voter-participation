import copy
import csv
import io
import json
import unittest

from scripts.adaptive_persistence import (
    choose_penalty, fit, global_index, inputs_from_simulation, predict_index, run,
)
from scripts.verify_adaptive_persistence import verify
from scripts.package_adaptive_persistence import query_members


def fixture():
    codes = ["AL", "FL", "GA", "TX", "CA", "OR", "NY", "PA"]
    factors = [0.5, 1.0, 2.0]
    grids, targets, groups = {}, [], []
    for i, code in enumerate(codes):
        for factor, value in zip(factors, [0.12, 0.08, 0.04]):
            grids[code + "|" + str(factor)] = dict(
                probabilities=[], analytic=dict(
                    synthetic_gross_switching_share_of_modeled_current_voters=value + i * .002,
                    modeled_nonvoter_share=.3 + i * .04))
        for office in ("senate", "governor"):
            targets.append(dict(id=code + "-" + office, state_code=code, office=office,
                target_fraction=.04 + (i % 3) * .04))
        for dimension, labels in (("AGE6", ("30_49", "65_plus")),
                                  ("RUCC", ("rural_county", "urban_county"))):
            for j, label in enumerate(labels):
                groups.append(dict(state_code=code, dimension=dimension, group=label,
                    disposition="selected_broad_source_model",
                    conditional_simulation=[dict(analytic=dict(
                        modeled_nonvoter_share=.2 + i * .02 + j * (.05 + i * .01)))]))
    spec = dict(models=dict(global_=[], nonvoter=["nonvoter"],
        age_rurality=["nonvoter", "age_gap", "rurality_gap"]),
        penalties=[.1, 10.0], minimum_training_states=2,
        age_contrast=["AGE6", "30_49", "65_plus"],
        rurality_contrast=["RUCC", "rural_county", "urban_county"],
        group_disposition="selected_broad_source_model",
        regions=dict(South=codes[:4], West=codes[4:6], Northeast=codes[6:]))
    spec["models"]["global"] = spec["models"].pop("global_")
    simulation = dict(complete_demographic_decisions=groups,
        persistence_calibration=dict(candidate_factors=factors, grid_kernels=grids,
            complete_poll_decisions=targets, heldout_predictions=[]))
    data = inputs_from_simulation(simulation, spec)
    for code in codes:
        index = global_index(data, [state for state in codes if state != code])
        for target in targets:
            if target["state_code"] == code:
                simulation["persistence_calibration"]["heldout_predictions"].append(dict(
                    id=target["id"], selected_factor=factors[index],
                    predicted_fraction=data["curves"][code][index]))
    return simulation, spec


class AdaptivePersistenceTests(unittest.TestCase):
    def test_outer_and_inner_folds_exclude_every_same_state_office(self):
        simulation, spec = fixture()
        result = run(simulation, spec)
        for fold in result["complete_outer_folds"]:
            outer = set(fold["heldout_states"])
            self.assertFalse(outer.intersection(fold["fit"]["training_states"]))
            for candidate in fold["inner_candidates"]:
                for inner in candidate["complete_inner_predictions"]:
                    self.assertNotIn(inner["heldout_state"], inner["training_states"])
                    self.assertFalse(outer.intersection(inner["training_states"]))
                    self.assertTrue(set(inner["eligible_training_states"]).issubset(inner["training_states"]))

    def test_heldout_targets_do_not_change_tuning_or_coefficients(self):
        simulation, spec = fixture()
        first = inputs_from_simulation(simulation, spec)
        changed = copy.deepcopy(simulation)
        for row in changed["persistence_calibration"]["complete_poll_decisions"]:
            if row["state_code"] == "AL":
                row["target_fraction"] = .99
        second = inputs_from_simulation(changed, spec)
        training = [code for code in first["targets"] if code != "AL"]
        names = spec["models"]["age_rurality"]
        a = choose_penalty(first, training, names, spec)
        b = choose_penalty(second, training, names, spec)
        self.assertEqual(a, b)
        model_a = fit(first, training, names, a[0], 2)
        model_b = fit(second, training, names, b[0], 2)
        self.assertEqual(model_a, model_b)
        self.assertEqual(predict_index(first, model_a, "AL"), predict_index(second, model_b, "AL"))
        with self.assertRaisesRegex(ValueError, "training state"):
            predict_index(first, model_a, training[0])

    def test_suppressed_group_remains_missing_and_uses_global_fallback(self):
        simulation, spec = fixture()
        group = next(row for row in simulation["complete_demographic_decisions"]
            if row["state_code"] == "AL" and row["group"] == "rural_county")
        group.update(disposition="held_source_support_or_complementary_disclosure", conditional_simulation=None)
        data = inputs_from_simulation(simulation, spec)
        self.assertNotIn("rurality_gap", data["features"]["AL"])
        model = fit(data, [code for code in data["targets"] if code != "AL"],
            spec["models"]["age_rurality"], .1, 2)
        index, disposition = predict_index(data, model, "AL")
        self.assertEqual(index, model["global_index"])
        self.assertEqual(disposition, "held_missing_or_suppressed_feature_global_fallback")

    def test_predictions_reuse_exact_cached_analytic_outputs_without_mutation(self):
        simulation, spec = fixture()
        before = copy.deepcopy(simulation)
        result = run(simulation, spec)
        self.assertEqual(simulation, before)
        for row in result["complete_heldout_predictions"]:
            kernel = simulation["persistence_calibration"]["grid_kernels"][row["exact_cached_coupling_key"]]
            self.assertEqual(row["analytic"], kernel["analytic"])
        self.assertFalse(result["automatic_ui_promotion"])
        self.assertFalse(result["missing_group_values_imputed"])

    def test_duplicate_office_tables_do_not_reweight_a_state(self):
        simulation, spec = fixture()
        first = inputs_from_simulation(simulation, spec)
        changed = copy.deepcopy(simulation)
        rows = changed["persistence_calibration"]["complete_poll_decisions"]
        rows.extend(copy.deepcopy(row) for row in list(rows) if row["state_code"] == "AL")
        second = inputs_from_simulation(changed, spec)
        self.assertEqual(global_index(first, list(first["targets"])),
            global_index(second, list(second["targets"])))
        self.assertEqual(first["losses"]["AL"], second["losses"]["AL"])

    def test_independent_checker_rejects_leaked_training_and_changed_coefficients(self):
        simulation, spec = fixture()
        result = run(simulation, spec)
        self.assertTrue(verify(simulation, result, spec)["same_state_and_region_leakage_rejected"])
        changed = copy.deepcopy(result)
        fold = changed["complete_outer_folds"][0]
        fold["fit"]["training_states"].append(fold["heldout_states"][0])
        with self.assertRaisesRegex(ValueError, "leakage"):
            verify(simulation, changed, spec)
        changed = copy.deepcopy(result)
        model = next(row["fit"] for row in changed["complete_outer_folds"]
            if row["fit"]["coefficients"])
        model["coefficients"][0] += 1
        with self.assertRaisesRegex(ValueError, "normal-equation"):
            verify(simulation, changed, spec)

    def test_independent_checker_rejects_tuning_and_cached_prediction_changes(self):
        simulation, spec = fixture()
        result = run(simulation, spec)
        changed = copy.deepcopy(result)
        fold = next(row for row in changed["complete_outer_folds"] if row["inner_candidates"])
        fold["inner_candidates"][0]["state_balanced_mse"] += .1
        with self.assertRaisesRegex(ValueError, "Tuning objective"):
            verify(simulation, changed, spec)
        changed = copy.deepcopy(result)
        changed["complete_heldout_predictions"][0]["predicted_fraction"] += .1
        with self.assertRaisesRegex(ValueError, "Cached gross"):
            verify(simulation, changed, spec)

    def test_independent_checker_rejects_changed_support_and_fallback_summaries(self):
        simulation, spec = fixture()
        result = run(simulation, spec)
        changes = [
            ("Metric support", lambda value: value["metrics"]["state"]["global"].update(states=0)),
            ("Maximum error", lambda value: value["metrics"]["state"]["global"].update(
                maximum_absolute_error_pp=999)),
            ("Fallback disposition", lambda value: value["feature_and_factor_coverage"]["state"][
                "global"].update(dispositions={})),
            ("Benchmark support", lambda value: value.update(qualified_source_states=[])),
            ("Feature source dispositions", lambda value: value["complete_feature_availability"][0].update(
                source_groups=[])),
        ]
        for message, change in changes:
            with self.subTest(message=message):
                changed = copy.deepcopy(result)
                change(changed)
                with self.assertRaisesRegex(ValueError, message):
                    verify(simulation, changed, spec)

    def test_complete_query_exports_keep_every_prediction_and_missing_feature_hold(self):
        simulation, spec = fixture()
        for kernel in simulation["persistence_calibration"]["grid_kernels"].values():
            kernel["analytic"]["components_pp"] = {"switching": .25}
        group = next(row for row in simulation["complete_demographic_decisions"]
            if row["state_code"] == "AL" and row["group"] == "rural_county")
        group.update(disposition="held_source_support_or_complementary_disclosure", conditional_simulation=None)
        result = run(simulation, spec)
        members = query_members(result)
        rows = list(csv.DictReader(io.StringIO(members["queries/complete-heldout-predictions.csv"].decode())))
        self.assertCountEqual([(row["block_type"], row["model"], row["id"]) for row in rows],
            [(row["block_type"], row["model"], row["id"]) for row in result["complete_heldout_predictions"]])
        features = list(csv.DictReader(io.StringIO(members["queries/complete-feature-availability.csv"].decode())))
        missing = next(row for row in features if row["state_code"] == "AL" and row["feature"] == "rurality_gap")
        self.assertEqual(missing["value"], "")
        self.assertEqual(missing["status"], "held_missing_or_suppressed_group")
        self.assertEqual(json.loads(missing["source_groups"])[0]["disposition"], group["disposition"])
        self.assertTrue(all(json.loads(row["components_pp"]) for row in rows))


if __name__ == "__main__":
    unittest.main()
