"""Check Stata offer coefficients with an independent within transformation."""

from pathlib import Path
import argparse

import numpy as np
import pandas as pd


def residualize(values, groups, trend=None, tolerance=1e-9, max_iterations=10000):
    """Project out group effects and, optionally, group-specific linear trends.

    Groups are contiguous integer codes starting at zero. Trend is a pair of
    group codes and times centered within those groups. Alternating projections
    accommodate unbalanced panels without constructing a dummy-variable matrix.
    """
    z = np.asarray(values, dtype=float).copy()
    if z.ndim != 2 or len(z) == 0 or not np.isfinite(z).all():
        raise ValueError("Expected a nonempty, finite two-dimensional matrix.")
    for group in groups:
        if len(group) != len(z) or not np.array_equal(
            np.unique(group), np.arange(len(np.unique(group)))
        ):
            raise ValueError(
                "Group codes must be contiguous integers starting at zero."
            )
    z -= z.mean(axis=0)
    for iteration in range(max_iterations):
        previous = z.copy()
        for group in groups:
            counts = np.bincount(group)
            means = np.column_stack(
                [
                    np.bincount(group, weights=z[:, j]) / counts
                    for j in range(z.shape[1])
                ]
            )
            z -= means[group]
        if trend is not None:
            group, time = trend
            denominator = np.bincount(group, weights=time * time)
            slopes = np.column_stack(
                [
                    np.bincount(group, weights=time * z[:, j])
                    / np.maximum(denominator, 1e-30)
                    for j in range(z.shape[1])
                ]
            )
            z -= slopes[group] * time[:, None]
        if np.max(np.abs(z - previous)) < tolerance:
            return z, iteration + 1
    raise RuntimeError("Fixed-effect absorption did not converge.")


def verify(sample, specification, expected):
    data = sample.copy()
    if specification == "hr6to9":
        data = data[data.hr.between(6, 9)].copy()
    uid = pd.Categorical(data.uid).codes
    day = pd.Categorical(data.day).codes
    groups, trend = [uid, day], None
    if specification == "trends":
        time = data.trend.to_numpy().copy()
        time -= pd.Series(time).groupby(uid).transform("mean").to_numpy()
        trend = uid, time
    elif specification == "unit_yearmonth":
        groups = [
            pd.factorize(pd.MultiIndex.from_arrays([data.uid, data.yearmonth]))[0],
            day,
        ]
    elif specification not in {"baseline", "hr6to9"}:
        raise ValueError(f"Unknown specification: {specification}")
    transformed, iterations = residualize(data[["y", "fuel", "carbon"]], groups, trend)
    y, x = transformed[:, 0], transformed[:, 1:]
    if np.linalg.matrix_rank(x) < 2:
        raise ValueError("Fuel and carbon effects are not separately identified.")
    coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
    error = np.max(np.abs(coefficients - np.asarray(expected, dtype=float)))
    if error > 1e-5:
        raise AssertionError(f"Python and Stata coefficients differ by {error:.6g}")
    return {"observations": len(data), "iterations": iterations, "max_error": error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path(__file__).resolve().parents[1] / "output"
    )
    directory = parser.parse_args().directory
    results = pd.read_csv(directory / "stata_offer_results.csv")
    checks = []
    for row in results[results.covariance == "twoway"].itertuples():
        data = pd.read_csv(directory / f"{row.sample}.csv")
        check = verify(data, row.specification, [row.fuel_b, row.carbon_b])
        checks.append(
            {"sample": row.sample, "specification": row.specification, **check}
        )
    if not checks:
        raise ValueError("No two-way clustered Stata results to verify.")
    pd.DataFrame(checks).to_csv(directory / "independent_verification.csv", index=False)
    print(pd.DataFrame(checks).to_string(index=False))


if __name__ == "__main__":
    main()
