# Iman Ahmadi Naeeni

PhD student in Economics · Georgia State University  
Andrew Young School of Policy Studies

I study energy economics, electricity markets, and banking. My research examines how large electricity loads, carbon policy, and financial conditions affect prices and the allocation of credit.

This repository contains selected Python and Stata workflows from my ongoing research. Each project describes the question, the data it requires, and the choices behind the analysis.

## Research projects

| Project | Research question | Code to explore |
|---|---|---|
| [Data centers and electricity markets](projects/data-centers-electricity) | How do large electricity loads relate to congestion and regional price differences? | Hourly ERCOT panel construction, unit conversions, and fixed-effect regressions |
| [Bank lending and carbon intensity](projects/climate-credit) | How does the composition of syndicated lending change during financial crises? | Lender-share allocation, emissions matching, quarterly loan panels, and Stata estimation |
| [Financing the electricity sector](projects/electricity-finance) | How can syndicated-loan records measure financing activity in the electricity sector? | Facility deduplication, industry classification, measurement audits, and descriptive summaries |
| [Carbon costs and electricity offers](projects/carbon-pass-through) | How are carbon costs reflected in generators' electricity offers? | Daily offer samples, earlier-period exposure proxies, multiway fixed effects, and independent coefficient verification |

The lending and carbon-intensity project is joint work with **Givi Melkadze and Giseong Kim**. The electricity-finance project is a separate exploratory study.

## Methods and tools

- **Python:** pandas and NumPy for data construction; statsmodels for estimation; PyArrow for columnar storage.
- **Stata:** panel estimation, multiple absorbed fixed effects, clustered inference, and specification comparisons.
- **Research data:** electricity-market records, loan facilities, industry crosswalks, and emissions measures.
- **Reproducibility:** explicit sample definitions, merge checks, data-quality audits, and synthetic-data tests.

## Getting started

Use Python 3.10 or newer. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

On Windows, activate the environment with `.venv\Scripts\activate`. The Stata scripts require **Stata 19 or newer** for native absorption of multiple fixed effects. They do not install packages.

The tests generate artificial records in temporary directories. They run without the research datasets. To run a research workflow, follow its project README and supply the listed inputs locally. Generated files belong in each project's ignored `output/` directory.

An optional [Stata smoke test](VALIDATION.md) runs both estimation workflows on artificial panels and compares the offer-model coefficients with an independent Python calculation.

## Scope

These are selected code releases from work in progress, not complete paper replication packages. No empirical findings are claimed by the synthetic examples. The original research datasets, proprietary extracts, draft papers, and internal notes are not distributed here. [Data access and limitations](DATA_ACCESS.md) and [release changes](CHANGES.md) document the boundaries of this release.

Contact: [GitHub profile](https://github.com/ImanAhmadin96)
