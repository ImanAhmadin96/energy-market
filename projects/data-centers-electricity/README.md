# Data centers and electricity markets

This project studies how large electricity loads relate to congestion, renewable generation, and regional electricity prices. The broader research considers ERCOT and PJM. This code selection covers an exploratory ERCOT hub-level workflow.

## Workflow

1. `python/build_panel.py` aggregates settlement prices to hours, aligns wind, solar, and native load, and constructs monthly facility-capacity measures.
2. `python/estimate_spreads.py` estimates West–North hub spreads on wind interacted with upstream firm, upstream crypto, and downstream firm capacity. It includes hour and month effects and clusters errors by month.

From this project directory:

```sh
python python/build_panel.py
python python/estimate_spreads.py
```

Output goes to `output/`. The estimator also accepts `--input` and `--output` paths.

## Required local files

Under `data/`:

```text
ercot/prices/*RTMLZHBSPP*.xlsx
ercot/wind_solar/ERCOT_*_Hourly_WindSolar_Output.xlsx
ercot/wind_solar/FuelMixReport_PreviousYears.zip
ercot/wind_solar/IntGenbyFuel2026*.xlsx
ercot/load/Native_Load_*.zip
processed/datacenters_geocoded.csv
```

The tracker needs `market_approx`, `Operational` (such as `2023Q1`), `IT Power Live (MW)`, `Type`, `Company`, `City`, `Name`, and `Category`. Tracker data are not included. The parser expects the archived ERCOT workbook layouts used by the research; it is not a downloader for current API responses.

## Measurement and interpretation

- Settlement prices are averaged across the quarter-hour records. Generation in the interval fuel workbooks is MWh per interval: summing four intervals yields average MW over the hour. Regression variables are then expressed in GW.
- The selected legacy pipeline uses local clock hours, excludes repeated-hour price records, and deduplicates load timestamps. It is not a UTC-preserving treatment of daylight-saving transitions.
- Facility locations are classified using cities, and operational quarters are assigned to their first month. The 2021–June 2026 capacity window is fixed in the source. Missing capacity is treated as zero by the inherited tracker transformation.
- The model is a coarse-geography association, not the facility-level causal design of the broader project. It includes a sample excluding January–February 2021 and a sample starting in 2023.

The tests check interval-unit aggregation and regression sample alignment on artificial data. They do not establish full raw-data coverage or validate the facility classifications.
