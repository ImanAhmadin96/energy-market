# Financing the electricity sector

An exploratory study of syndicated-loan activity in the electricity sector. This workflow distinguishes lender records, dated facility events, and first-observed facilities, then compares alternative electricity-sector definitions.

## Run

Place an authorized extract at `data/raw/dealscan.csv`. Required fields are listed in `COLS` in `python/profile_loans.py`.

Copy `data/borrower_classification_overrides.example.csv` to `data/borrower_classification_overrides.csv`. The template contains only a header. Add documented overrides if available; leaving it empty applies only the rule-based screen. `verified_power_entity` accepts `true` or `false`.

From this project directory:

```sh
python python/profile_loans.py
python python/analyze_loans.py
```

The first stage profiles the US sample and stores an intermediate pickle created locally by the workflow. The second writes annual, quarterly, first-half, sector, sensitivity, and data-quality outputs under `output/`.

## Measurement

Events are keyed by deal, tranche, and activation date. Duplicate lender rows are collapsed. Conflicting amounts are audited; the descriptive event value uses the maximum reported amount, with minimum-value sensitivity retained. The source window is January 2019–June 2026.

Industry definitions include electricity SIC codes 4911/4931, the expanded 4911/4931/4939 group, utilities SIC 49, and electric-power NAICS 2211. A separate name/project screen flags potentially non-electric activities. Evidence-backed overrides take precedence over name flags.

Converted amounts are nominal USD millions; reported totals in billions divide by 1,000. A first-observed facility is not necessarily a new origination, and a facility amount is not necessarily new money. The half-year comparison keeps 2026's partial coverage explicit. These are descriptive measurement choices, not estimates of the effect of data-center demand on lending.

Tests use invented borrowers and facilities to check duplicate-event accounting and amount-conflict handling. No borrower observations are included in the repository.
