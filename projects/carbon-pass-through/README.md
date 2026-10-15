# Carbon costs and electricity offers

This project studies whether generators' offers incorporate carbon-allowance costs in ISO New England. The selected workflow constructs daily samples and compares the sensitivity of fuel and carbon coefficients to fixed effects and trends.

## Run

From this directory:

```sh
python python/build_offer_pilot.py
```

In Stata 19 or newer, with this directory as the working directory:

```stata
do stata/estimate_offers.do
```

Then verify the point estimates independently:

```sh
python python/verify_estimates.py
```

The Python verifier uses alternating within-group projections and least squares. It checks coefficients only; it does not verify Stata's standard errors.

## Required local inputs

- `data/clean/offers_unit_hour_YYYY.csv.gz`, for each year 2019–2026: `date`, `hour`, `masked_asset_id`, `econ_max`, `mw_offered`, `unit_status`, `price_qw`, `price_at_median_mw`.
- `data/clean/rggi_secondary_daily.csv`: `date`, `price_ff`, `price_vw`.
- `data/clean/prices_daily.csv.gz`: `date`, `heating_oil_ny`.
- `data/gas_basis/algonquin_citygate_daily_v2.csv`: `date`, `algonquin_spot`.
- `data/clean/inferred_exposure_by_asset.csv`: `masked_asset_id`, `fuel_inferred`, `implied_hr`, `fit_r2`.

These are previously cleaned research inputs. Preparing them from the raw archives is outside this selection. Files for 2025–2026 are audited; the estimation samples use 2021–2024.

## Interpretation

The legacy sample uses existing inferred exposures. A comparison sample uses lagged prices and a coverage screen. A third sample trains fuel/heat-rate proxies in 2019–2020 before evaluating offers in 2021–2024. The code retains the source thresholds: at least 20 eligible hourly records per day, prices no more than seven calendar days old, at least 200 training days, and at least 400 evaluation days per asset.

Estimated heat rates and fuel classifications are proxies, not verified identities or physical exposure. Earlier-period training avoids direct reuse of evaluation outcomes but does not establish exogeneity. Carbon coefficients are sensitive to trends and fixed effects; the workflow should not be read as established causal pass-through.

Daily averages retain repeated local-clock records. A final hourly design would need a parser that preserves UTC offsets. Synthetic tests check the independent within estimator against explicit dummy-variable regression; they do not validate raw archive parsing or the empirical identification strategy.
