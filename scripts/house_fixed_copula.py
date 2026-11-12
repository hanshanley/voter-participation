"""Fixed-marginal D/R association kernels; no current-election fitting."""

import math


THETAS = (.25, .5, 1., 2., 4., 8., 16., 32., 64.)


def project_batch(prior, rows, columns, theta, tolerance=2e-12, max_iterations=20000):
    import numpy as np
    if not math.isfinite(theta) or theta <= 0:
        raise ValueError("A positive finite association multiplier is required")
    if (prior.ndim != 3 or rows.shape != prior.shape[:2] or
            columns.shape != (prior.shape[0], prior.shape[2]) or
            min(prior.shape[1:]) < 2 or not np.isfinite(prior).all() or
            not (prior > 0).all() or not (rows > 0).all() or not (columns > 0).all()):
        raise ValueError("Positive complete prior tables and native marginal shapes required")
    if np.max(abs(rows.sum(axis=1)-columns.sum(axis=1))) > tolerance:
        raise ValueError("Incompatible marginal totals")
    value = prior.copy()
    value[:, 0, 0] *= theta
    value[:, 1, 1] *= theta
    if theta == 1 and max(np.max(abs(value.sum(axis=2)-rows)),
                         np.max(abs(value.sum(axis=1)-columns))) <= tolerance:
        return value, 0
    for iteration in range(1, max_iterations+1):
        value *= (rows/value.sum(axis=2))[:, :, None]
        value *= (columns/value.sum(axis=1))[:, None, :]
        if max(np.max(abs(value.sum(axis=2)-rows)), np.max(abs(value.sum(axis=1)-columns))) <= tolerance:
            if not np.isfinite(value).all() or not (value > 0).all():
                raise ValueError("Invalid projected source probabilities")
            return value, iteration
    raise ValueError("Fixed-marginal association projection did not converge")


def couple(rows, columns, theta):
    return project_batch(rows[:, :, None]*columns[:, None, :], rows, columns, theta)


def select_theta(curve):
    if set(curve) != set(THETAS) or any(not math.isfinite(v) for v in curve.values()):
        raise ValueError("The complete prespecified calibration curve is required")
    best = min(curve.values())
    tied = [theta for theta in THETAS if curve[theta] <= best+1e-12]
    return min(tied, key=lambda theta: (abs(math.log(theta)), theta))


def metric(probabilities, target, weights):
    import numpy as np
    chosen = probabilities[np.arange(len(target)), target]
    return dict(nll_sum=float(np.sum(-np.log(chosen)*weights, dtype=np.float64)),
        brier_sum=float(np.sum(((probabilities*probabilities).sum(axis=1)-2*chosen+1)*weights, dtype=np.float64)))


def prediction_diagnostics(joint, rows, columns, theta):
    import numpy as np
    error = max(float(np.max(abs(joint.sum(axis=2)-rows))),
                float(np.max(abs(joint.sum(axis=1)-columns))))
    kernel = np.ones(joint.shape[1:])
    kernel[0, 0] = kernel[1, 1] = theta
    logarithm = np.log(joint/(rows[:, :, None]*columns[:, None, :]*kernel))
    certificate = logarithm-logarithm[:, :, -1, None]-logarithm[:, -1, None, :]+logarithm[:, -1, -1, None, None]
    return dict(maximum_case_marginal_error=error, maximum_dual_certificate_error=float(np.max(abs(certificate))))
