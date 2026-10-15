# Bank lending and carbon intensity

Joint work with **Givi Melkadze and Giseong Kim**.

The project examines the carbon composition of syndicated lending during financial crises. This selection builds a bank–firm–quarter panel and demonstrates stock and extensive-margin specifications.

## Run order

From this directory, after placing the required inputs under `data/`:

```sh
python python/01_clean_loans.py
python python/02_match_emissions.py
python python/03_build_panel.py
python python/04_export_stata.py
```

Then, in Stata 19 or newer with this directory as the working directory:

```stata
do stata/estimate_crisis.do
```

The Python stages write Parquet panels, CSV exports, and `.dta` files into `output/`. The Stata script estimates log positive balances and the indicator for a positive balance, with lender-clustered errors and three fixed-effect structures. It compares gray and brown borrowers against green borrowers.

## Input contract

- `data/raw/dealscan_1996_2019.csv`: source column names are listed in `python/config.py` as `RAW_COLS`. The file contains lender-level origination records, reported lender shares, loan amounts, dates, countries, and industry codes.
- `data/emissions/`: the four project-specific tables `exio_US_report_average_2000_2015.csv`, `exio_US_report_average_2000_2015_2digit_SIC.csv`, `exio_EU_GB_report_average_2000_2015_3digit_SIC.csv`, and `exio_EU_GB_report_average_2000_2015_2digit_SIC.csv`. These are prepared crosswalk outputs, not raw EXIOBASE downloads. Lookup columns are defined in `02_match_emissions.py`.
- `data/crosswalk/sic_nace.xlsx`: columns `sic` and `nace2_by_NAICS`.

The source data are not included. Sample definitions and paths are centralized in `python/config.py`.

## Design choices

Reported shares are normalized when all lenders report. Unreported syndicates are split equally; partially reported syndicates retain reported shares and divide the remainder. `PARTIAL_RULE = "drop"` provides a sensitivity option.

Emissions matching prefers three-digit SIC, with a two-digit fallback and an explicit match flag. Subsidiary amounts are combined at the parent-lender/facility level before counting facilities. The panel includes zero-balance quarters for observed bank–firm pairs and tracks originations using the original activation quarter.

Balances follow an active-until-maturity convention. They do not incorporate repayments, prepayments, or secondary sales. Loan history begins in 1996, so early reported balances remain left-censored. Country and industry coverage, borrower-name consistency, and industry-level emissions proxies also limit interpretation. A rectangular observed-pair panel is not the universe of possible lending relationships.

The tests exercise all four Python stages with artificial loans, verify share allocation and facility counts, and round-trip Stata quarterly dates. No research-data regression results are distributed in this release.
