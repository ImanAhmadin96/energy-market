"""Estimate exploratory ERCOT spread regressions with monthly clustered errors."""

from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
MW_COLUMNS = [
    "wind_mw",
    "solar_mw",
    "load_ercot_mw",
    "cap_upfirm_mw",
    "cap_upcrypto_mw",
    "cap_downfirm_mw",
]
TERMS = [
    "w_x_upfirm",
    "w_x_upcrypto",
    "w_x_downfirm",
    "wind_gw",
    "solar_gw",
    "load_ercot_gw",
]


def prepare(panel):
    """Convert MW to GW and construct the source interaction terms."""
    data = panel.copy()
    data["hour"] = data.index.hour
    data["mos"] = data.index.to_period("M").astype(str)
    for column in MW_COLUMNS:
        data[column.replace("_mw", "_gw")] = data[column] / 1000
    for exposure in ["upfirm", "upcrypto", "downfirm"]:
        data[f"w_x_{exposure}"] = data.wind_gw * data[f"cap_{exposure}_gw"]
    return data


def estimate(data, outcome="spread_wn", label="full_sample"):
    """Use one complete-case sample for estimation and cluster labels."""
    sample = data.replace([np.inf, -np.inf], np.nan).dropna(
        subset=[outcome, *TERMS, "hour", "mos"]
    )
    if sample.mos.nunique() < 2:
        raise ValueError("At least two nonempty month clusters are required.")
    formula = f"{outcome} ~ " + " + ".join(TERMS) + " + C(hour) + C(mos)"
    model = smf.ols(formula, data=sample).fit(
        cov_type="cluster", cov_kwds={"groups": sample.mos}
    )
    if np.linalg.matrix_rank(model.model.exog) < model.model.exog.shape[1]:
        raise ValueError(
            f"{label}: design is rank deficient; check exposure variation."
        )
    return pd.DataFrame(
        {
            "term": TERMS,
            "coefficient": model.params[TERMS].to_numpy(),
            "standard_error": model.bse[TERMS].to_numpy(),
            "p_value": model.pvalues[TERMS].to_numpy(),
            "specification": label,
            "observations": int(model.nobs),
            "month_clusters": sample.mos.nunique(),
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "output/panel_hourly.csv")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/regression_results.csv"
    )
    args = parser.parse_args()
    data = prepare(pd.read_csv(args.input, index_col=0, parse_dates=True))
    specifications = [
        (data, "spread_wn", "full_sample"),
        (data.loc["2021-03-01":], "spread_wn", "exclude_jan_feb_2021"),
        (data.loc["2023-01-01":], "spread_wn", "from_2023"),
    ]
    if "spread_pn" in data and data.spread_pn.notna().sum() > 10000:
        specifications.append((data, "spread_pn", "panhandle_north"))
    results = pd.concat([estimate(d, y, label) for d, y, label in specifications])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output, index=False)
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()
