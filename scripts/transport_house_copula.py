"""Coherent postaggregation association stresses on permitted synthetic priors."""

import copy

from house_fixed_copula import project_batch


BACKOFF = (1., .5, .25, .125, 0.)


def partition_projection(original, state_target, theta, tolerance=2e-12, max_iterations=20000):
    import numpy as np
    before = original.sum(axis=2)
    after = original.sum(axis=1)
    masses = original.sum(axis=(1, 2))
    upper = np.minimum(before[:, :, None], after[:, None, :]).sum(axis=0)
    lower = np.maximum(0, before[:, :, None]+after[:, None, :]-masses[:, None, None]).sum(axis=0)
    if np.max(state_target-upper) > tolerance or np.max(lower-state_target) > tolerance:
        return None, dict(reason="fixed_group_margin_cell_bound", iterations=0)
    value = original.copy()
    value[:, 0, 0] *= theta
    value[:, 1, 1] *= theta
    for iteration in range(1, max_iterations+1):
        for axis, target in ((2, before), (1, after), (0, state_target)):
            totals = value.sum(axis=axis)
            if np.any((totals == 0) & (target > tolerance)):
                return None, dict(reason="source_support_constraint", iterations=iteration)
            factors = np.divide(target, totals, out=np.zeros_like(target), where=totals > 0)
            value *= np.expand_dims(factors, axis=axis)
        error = max(float(np.max(abs(value.sum(axis=2)-before))),
                    float(np.max(abs(value.sum(axis=1)-after))),
                    float(np.max(abs(value.sum(axis=0)-state_target))))
        if error <= tolerance:
            return value, dict(reason=None, iterations=iteration, maximum_constraint_error=error)
    return None, dict(reason="multiway_projection_not_converged", iterations=max_iterations)


def stress_state(state, requested_theta):
    import numpy as np
    if requested_theta < 1:
        raise ValueError("This declared transport is a positive-persistence stress only")
    original = np.asarray(state["prior_joint"], dtype=float)
    rows = original.sum(axis=1)[None, :]
    columns = original.sum(axis=0)[None, :]
    dimensions = sorted({group["dimension"] for group in state["groups"]})
    decisions = []
    for exponent in BACKOFF:
        theta = requested_theta**exponent
        if exponent == 0 or theta == 1:
            return copy.deepcopy(state), dict(requested_theta=requested_theta, effective_theta=1.,
                feasibility_exponent=exponent, changed=False, attempts=decisions,
                maximum_constraint_error=0., reason="exact_baseline_recovered")
        target, iterations = project_batch(original[None, :, :], rows, columns, theta)
        target = target[0]
        transformed = {}
        diagnostics = {}
        failed = None
        for dimension in dimensions:
            selected = [(i, group) for i, group in enumerate(state["groups"])
                        if group["dimension"] == dimension and group["available"]]
            matrices = np.asarray([group["prior_joint"] for i, group in selected], dtype=float)
            if np.max(abs(matrices.sum(axis=0)-original)) > 2e-10:
                raise ValueError("Accepted source demographic partition is incomplete")
            value, report = partition_projection(matrices, target, theta)
            diagnostics[dimension] = report
            if value is None:
                failed = dimension
                break
            transformed.update({i: matrix.tolist() for (i, group), matrix in zip(selected, value)})
        decisions.append(dict(exponent=exponent, theta=theta, state_projection_iterations=iterations,
                              failed_dimension=failed, partitions=diagnostics))
        if failed is not None:
            continue
        result = copy.deepcopy(state)
        result["prior_joint"] = target.tolist()
        for i, matrix in transformed.items():
            result["groups"][i]["prior_joint"] = matrix
        error = max(report["maximum_constraint_error"] for report in diagnostics.values())
        return result, dict(requested_theta=requested_theta, effective_theta=theta,
            feasibility_exponent=exponent, changed=True, attempts=decisions,
            maximum_constraint_error=error, reason="all_group_year_and_state_cell_margins_preserved")
    raise AssertionError("The exact accepted baseline must be feasible")


def stress_priors(priors, requested_theta, profile):
    result = copy.deepcopy(priors)
    decisions = {}
    for code, state in sorted(priors["states"].items()):
        transformed, decisions[code] = stress_state(state, requested_theta)
        result["states"][code] = transformed
    result["structural_association_stress"] = dict(profile=profile, requested_theta=requested_theta,
        historical_parameter_not_validated_for2026=True, applied_postaggregation_not_per_case=True,
        state_and_group_year_marginals_preserved=True, source_only_feasibility_backoff=list(BACKOFF),
        old_disclosure_mask_and_direct2022_scenario_unchanged=True, current_return_targets_used=False)
    return result, decisions
