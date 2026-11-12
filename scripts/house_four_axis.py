"""Joint administrative/House responses without repairing contradictions."""

import math
from house_fixed_copula import project_batch

MODELS = ("independent_pairs", "conditional_house_given_admin", "fixed_pair_marginals")
COHORTS = ("full_four_axis", "marginal_house", "previous_voter_major_future15",
           "previous_nonvoter_future15", "previous_voter_major_known_future_admin",
           "previous_nonvoter_known_future_admin")
OUTCOMES = {
    "previous_voter_major": ("positive_same_major", "positive_changed_major",
        "positive_other_or_contest_nonvote", "positive_unknown_house",
        "explicit_nonvote_any_house", "unknown_history_any_house"),
    "previous_nonvoter": ("positive_any_house", "explicit_nonvote_any_house", "unknown_history_any_house")}


def augmented(features, admin_pair):
    allowed = {"p20", "age20", "educ20", "state20", "p20_age20", "p20_educ20"}
    if not set(features) <= allowed or "p20" not in features or admin_pair not in range(9):
        raise ValueError("Only accepted2020 predictors and a hypothetical admin-pair category are allowed")
    return dict(features, admin_pair=str(admin_pair), president_by_admin=features["p20"]+"|"+str(admin_pair))


def hypothetical_features(features):
    return [augmented(row, pair) for row in features for pair in range(9)]


def joints(admin, house, conditional):
    import numpy as np
    if (admin.ndim != 2 or admin.shape[1] != 9 or house.shape != (len(admin), 30)
            or conditional.shape != (len(admin), 9, 30)
            or any(not np.isfinite(x).all() or not (x > 0).all() for x in (admin, house, conditional))
            or max(np.max(abs(admin.sum(axis=1)-1)), np.max(abs(house.sum(axis=1)-1)),
                   np.max(abs(conditional.sum(axis=2)-1))) > 1e-12):
        raise ValueError("Complete positive normalized paired/conditional predictions are required")
    baseline = admin[:, :, None]*house[:, None, :]
    learned = admin[:, :, None]*conditional
    projected, iterations = project_batch(learned, admin, house, 1.)
    logarithm = np.log(projected)-np.log(learned)
    certificate = logarithm-logarithm[:, :, -1, None]-logarithm[:, -1, None, :]+logarithm[:, -1, -1, None, None]
    return dict(zip(MODELS, (baseline, learned, projected))), dict(
        projection_iterations=iterations,
        maximum_pair_marginal_error=max(float(np.max(abs(projected.sum(axis=2)-admin))),
                                        float(np.max(abs(projected.sum(axis=1)-house)))),
        maximum_dual_certificate_error=float(np.max(abs(certificate))))


def future_given_past(joint, previous_admin, previous_house):
    import numpy as np
    if (joint.shape != (len(previous_admin), 9, 30) or len(previous_house) != len(joint)
            or not np.isin(previous_admin, range(3)).all() or not np.isin(previous_house, range(6)).all()):
        raise ValueError("Only observed prior-year categories condition a future forecast")
    indices = ((previous_admin[:, None]*3+np.repeat(np.arange(3), 5))*30
               +previous_house[:, None]*5+np.tile(np.arange(5), 3))
    result = np.take_along_axis(joint.reshape(-1, 270), indices, axis=1)
    return result/result.sum(axis=1)[:, None]


def coarse_forecasts(future, previous_house, cohort):
    import numpy as np
    if future.shape != (len(previous_house), 15):
        raise ValueError("A complete15-category future probability is required")
    if cohort == "previous_nonvoter":
        return future.reshape(-1, 3, 5).sum(axis=2)
    if cohort != "previous_voter_major" or not np.isin(previous_house, (0, 1)).all():
        raise ValueError("The previous major-party cohort must be literal")
    index = np.arange(len(future))
    return np.column_stack((future[index, previous_house], future[index, 1-previous_house],
        future[:, 2]+future[:, 3], future[:, 4], future[:, 5:10].sum(axis=1), future[:, 10:15].sum(axis=1)))


def observed_coarse(row, cohort):
    if cohort == "previous_nonvoter":
        return row[1]
    if row[0] != 0 or row[2] not in (0, 1):
        raise ValueError("Changed prior-only source cohort")
    if row[1] == 1:
        return 4
    if row[1] == 2:
        return 5
    return 0 if row[3] == row[2] else 1 if row[3] < 2 else 2 if row[3] < 4 else 3


def scored_queries(joint, target, weights, minimum=30):
    import numpy as np
    from house_pair_oof import metrics
    future = future_given_past(joint, target[:, 0], target[:, 2])
    masks = {"previous_voter_major": (target[:, 0] == 0) & (target[:, 2] < 2),
             "previous_nonvoter": target[:, 0] == 1}
    pairs = joint.reshape(-1, 270)
    queries = [("full_four_axis", np.ones(len(target), dtype=bool), pairs,
                (target[:, 0]*3+target[:, 1])*30+target[:, 2]*5+target[:, 3]),
               ("marginal_house", np.ones(len(target), dtype=bool), joint.sum(axis=1), target[:, 2]*5+target[:, 3])]
    for cohort, mask in masks.items():
        queries.append((cohort+"_future15", mask, future, target[:, 1]*5+target[:, 3]))
        known = mask & (target[:, 1] < 2)
        binary = future.reshape(-1, 3, 5).sum(axis=2)[:, :2]
        binary = binary/binary.sum(axis=1)[:, None]
        queries.append((cohort+"_known_future_admin", known, binary, target[:, 1]))
    results = []
    for name, mask, probability, labels in queries:
        count = int(mask.sum())
        required = 100 if name in COHORTS[:2] else minimum
        record = dict(cohort=name, available=count >= required, n=count if count >= required else None,
                      reason=None if count >= required else "whole_cohort_support_hold")
        if record["available"]:
            record.update(weight_sum=format(math.fsum(map(float, weights[mask])), ".17g"),
                          **{key: format(value, ".17g") for key, value in metrics(probability[mask], labels[mask], weights[mask]).items()})
        else:
            record.update(weight_sum=None, nll_sum=None, brier_sum=None)
        results.append(record)
    forecasts = []
    for cohort, mask in masks.items():
        if int(mask.sum()) < minimum:
            continue
        probabilities = coarse_forecasts(future[mask], target[mask, 2], cohort)
        forecasts.append(dict(cohort=cohort, n=int(mask.sum()), weight_sum=format(math.fsum(map(float, weights[mask])), ".17g"),
            predictions={key: format(float(np.sum(weights[mask]*probabilities[:, j], dtype=np.float64)), ".17g")
                         for j, key in enumerate(OUTCOMES[cohort])}))
    return results, forecasts
