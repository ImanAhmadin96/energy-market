# Validation

Verified on 15 October 2026 using Python 3.12 and StataNow 19.5.

## Automated Python checks

```sh
python -m unittest discover -s tests -v
```

Six tests cover:

1. Electricity-sector event conflicts, duplicate lender rows, repeat facilities, and partial-year labels.
2. Quarter-hour price aggregation and the MWh-to-average-MW convention.
3. Complete-case estimation with aligned monthly cluster labels.
4. All four loan-panel stages, including lender-share conservation, subsidiary consolidation, facility counts, origination timing, SIC fallback, zero quarters, and Stata date conversion.
5. Unbalanced-panel absorption against explicit dummy-variable regression.
6. Absorption of unit trends and two-way fixed effects.

## Stata checks

```sh
python tests/stata_smoke.py --stata /path/to/stata-mp
```

The script creates artificial panels in a temporary directory, runs both Stata workflows, checks the six crisis-model results, and independently verifies all eight offer-model point estimates. The offer workflow runs each specification with unit, date, and two-way clustered covariance choices.

These checks validate selected transformations and executable specifications. They do not reproduce paper estimates, validate data access, or establish causal identification. The complete offer-sample builder and full ERCOT raw-to-panel build have not been run on research data for this release. All original research folders remain outside the release's output locations.

Tested Python packages: NumPy 2.1.1, pandas 2.2.2, SciPy 1.14.1, statsmodels 0.14.4, PyArrow 24.0.0, openpyxl 3.1.5, and xlrd 2.0.2.
