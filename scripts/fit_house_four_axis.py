"""Fit only new conditional heads; enumerate all future administrative possibilities."""

import argparse
from fractions import Fraction
import gzip
import hashlib
import json
import os
from pathlib import Path

import house_four_axis as joint_model
import house_pair_oof as parent
import house_fixed_copula as projector


def digest(body):
    return hashlib.sha256(body).hexdigest()


def references(prepared):
    output = []
    for cohort, outcomes in joint_model.OUTCOMES.items():
        cells = {key: dict(n=0, weight=Fraction(0)) for key in outcomes}
        for target, weights in zip(prepared["target"], prepared["weights"]):
            weight = parent.native.weight(weights[0])
            selected = (target[0] == 0 and target[2] < 2) if cohort == "previous_voter_major" else target[0] == 1
            if weight is not None and selected:
                cell = cells[outcomes[joint_model.observed_coarse(target, cohort)]]
                cell["n"] += 1
                cell["weight"] += Fraction(weight)
        available = min(cell["n"] for cell in cells.values()) >= 30
        output.append(dict(cohort=cohort, available=available, minimum_each_cell=30,
            reason=None if available else "whole_coarse_table_support_hold",
            cells={key: dict(n=value["n"], weight=str(value["weight"])) for key, value in cells.items()} if available else None,
            source_code_transport_conditional=True, population_validation=False,
            no_native_fine_or_state_cells=True))
    return output


def run(args, policy, prepared):
    import numpy as np
    from sklearn.feature_extraction import DictVectorizer
    targets = np.asarray(prepared["target"], dtype=int)
    splits = np.asarray(prepared["folds"])
    admin_target = targets[:, 0]*3+targets[:, 1]
    house_target = targets[:, 2]*5+targets[:, 3]
    rows, forecasts, diagnostics = [], [], []
    fresh, reused, old_heads = 0, 0, 0
    previous_rows = json.loads(args.parent_sufficient.read_bytes())["rows"]
    previous_rows = {(row["weight_frame"], row["model"], row["fold"]): row for row in previous_rows}
    for column, frame in enumerate(parent.native.WEIGHTS):
        weights = np.asarray([float(parent.native.weight(row[column]) or 0) for row in prepared["weights"]])
        forecasts_full = {level+"_"+model: np.full((len(targets), 9, 30), np.nan)
                          for level in ("history", "demographic") for model in joint_model.MODELS}
        for level in ("history", "demographic"):
            source = prepared[level+"_features"]
            for fold in range(5):
                train = np.flatnonzero((splits != fold) & (weights > 0))
                test = np.flatnonzero((splits == fold) & (weights > 0))
                vectorizer = DictVectorizer(sparse=True)
                matrix_train = vectorizer.fit_transform(joint_model.augmented(source[i], int(admin_target[i])) for i in train)
                test_features = joint_model.hypothetical_features([source[i] for i in test])
                matrix_test = vectorizer.transform(test_features)
                metadata = json.dumps(dict(policy_sha256=digest(args.policy.read_bytes()), frame=frame, level=level, fold=fold,
                    train_indices_sha256=digest(train.tobytes()), test_indices_sha256=digest(test.tobytes()),
                    hypothetical_case_indices_sha256=digest(np.repeat(test, 9).tobytes()),
                    hypothetical_admin_pairs_sha256=digest(np.tile(np.arange(9), len(test)).tobytes()),
                    vocabulary_sha256=digest("\n".join(vectorizer.get_feature_names_out()).encode()),
                    native_training_weights_sha256=digest(weights[train].tobytes())), sort_keys=True)
                values, hit = parent.cached_head(args.private/"heads"/f"{frame}-{fold}-{level}.npz",
                    matrix_train, matrix_test, house_target[train], weights[train], 30, metadata)
                fresh += int(not hit)
                reused += int(hit)
                margins = {}
                for head, classes in (("admin", 9), ("house", 30)):
                    path = args.parent_private/"heads"/f"{frame}-{fold}-{level}-{head}.npz"
                    with np.load(path, allow_pickle=False) as archive:
                        binding = json.loads(str(archive["metadata"]))
                        margins[head] = archive["probabilities"].copy()
                    if (binding["policy_sha256"] != policy["parent_policy_sha256"]
                            or binding["test_indices_sha256"] != digest(test.tobytes())
                            or margins[head].shape != (len(test), classes)):
                        raise ValueError("Accepted paired-head binding differs; do not refit")
                    old_heads += 1
                predictions, report = joint_model.joints(margins["admin"], margins["house"], values.reshape(len(test), 9, 30))
                diagnostics.append(dict(weight_frame=frame, level=level, fold=fold, **report))
                baseline = previous_rows[frame, "paired_"+level, fold]
                for model, probabilities in predictions.items():
                    forecasts_full[level+"_"+model][test] = probabilities
                    queries, coarse = joint_model.scored_queries(probabilities, targets[test], weights[test])
                    for row in queries:
                        rows.append(dict(weight_frame=frame, level=level, fold=fold, model=model, **row))
                    if model == "independent_pairs":
                        full = next(row for row in queries if row["cohort"] == "full_four_axis")
                        if not np.isclose(float(full["nll_sum"]), float(baseline["admin_nll_sum"])+float(baseline["house_nll_sum"]),
                                          atol=1e-9, rtol=5e-13):
                            raise ValueError("Accepted independent-pairs baseline changed")
                    if column == 0:
                        forecasts.extend(dict(weight_frame=frame, level=level, fold=fold, model=model, **row) for row in coarse)
                print(json.dumps(dict(frame=frame, level=level, fold=fold,
                    status="new_conditional_head_and_all270_forecasts_complete", **report)), flush=True)
        parent.secure_npz(args.private/f"forecasts-{frame}.npz", target=targets, folds=splits, weights=weights, **forecasts_full)
    result = dict(contract="participation.house_four_axis_sufficient.v1", source_rows=6175,
        policy_sha256=digest(args.policy.read_bytes()), rows=rows, forecasts=forecasts, diagnostics=diagnostics,
        references=references(prepared), source_code_transport_conditional=True, population_validation=False,
        current2026_model_or_nonparticipation_parameter_changed=False, native_persons_predictions_or_fine_cells_exported=False)
    (args.private/"public-sufficient-candidate.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    receipt = dict(status="complete_new_four_axis_conditional_fit", new_conditional_heads=fresh,
        previously_new_heads_reused=reused, accepted_paired_heads_reused=old_heads, accepted_fits_repeated=0,
        score_queries=len(rows), source_predictive_queries=len(forecasts), policy_sha256=digest(args.policy.read_bytes()),
        sufficient_sha256=digest((args.private/"public-sufficient-candidate.json").read_bytes()))
    (args.private/"fitting-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("policy", "parent-private", "parent-sufficient", "private"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    policy = json.loads(args.policy.read_bytes())
    for path, key in ((Path(__file__), "driver_sha256"), (Path(joint_model.__file__), "core_sha256"),
                      (Path(parent.__file__), "parent_fitter_sha256"), (Path(projector.__file__), "projector_sha256"),
                      (Path(__file__).resolve().parents[1]/"tests/test_house_four_axis.py", "tests_sha256"),
                      (args.parent_private/"prepared.json.gz", "prepared_sha256"), (args.parent_sufficient, "parent_sufficient_sha256")):
        if digest(path.read_bytes()) != policy[key]:
            raise ValueError("Frozen experiment source/code binding differs")
    if (args.private/"fitting-receipt.json").exists():
        raise ValueError("Completed successful fits must be reused, not repeated")
    if Path(__file__).resolve().parents[1] in args.private.resolve().parents:
        raise ValueError("Native fits and predictions must stay outside the repository")
    prepared = json.loads(gzip.decompress((args.parent_private/"prepared.json.gz").read_bytes()))
    if prepared["policy_sha256"] != policy["parent_policy_sha256"]:
        raise ValueError("Accepted prepared-case policy differs")
    args.private.mkdir(parents=True, mode=0o700, exist_ok=True)
    (args.private/"heads").mkdir(mode=0o700, exist_ok=True)
    run(args, policy, prepared)


if __name__ == "__main__":
    main()
