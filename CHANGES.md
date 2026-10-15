# Portfolio release notes

This release selects substantive workflows from four research folders. It removes machine-specific paths, separates code from generated output, standardizes formatting, and adds input documentation. Original working files remain separate.

## Changes affecting computation

- **Loan cleaning:** recompute lender-tranche duplicate counts after preferring records with reported shares. The source used the pre-filter count and could discard a resolved duplicate. Reject negative shares and partial reported shares above 100% instead of silently allocating an invalid total.
- **Emissions matching:** reject duplicate keys in the emissions lookup tables instead of selecting the first record. Use a many-to-one merge check.
- **Panel exports:** retain facility counts and export `yq` as a Stata quarterly date (`%tq`). The source export omitted counts and did not specify quarterly-date conversion.
- **ERCOT regressions:** use the same complete-case sample for the model and cluster labels, including all regressors and the selected outcome. Report the actual cluster count and reject a rank-deficient design.
- **Electricity-sector classification:** parse explicit true/false override flags, including header-only override files.
- **Stata crisis models:** extract the stock and extensive-margin specifications into a portable Stata 19 script. Use native multiple-effect absorption, preserve the source country windows and pre-crisis lender screen, and report the equality test for gray and brown interactions. This is a selected specification set, not the full historical estimation suite.
- **Offer verification:** extract the independent within transformation from the field-paper diagnostics. Verify coefficients against the Stata results without requiring the unrelated figure and CEMS inputs.

The unit conventions, source sample windows, and exploratory nature of the selected analyses are retained. Changes have not been validated as numerically identical to historical paper estimates. Full-data replication is outside this release's verification scope.

## Source selection

| Project | Research code used |
|---|---|
| Data centers and electricity | `code/build_panel.py`, `code/regression.py` |
| Climate and credit | The `Stata/new dataset/rebuild` configuration, cleaning, matching, count-panel and export stages; selected specifications from `codes/GL2_crisis.do` |
| Electricity finance | `analysis/profile_dealscan.py`, `analysis/analyze_dealscan.py` |
| Carbon pass-through | `proposal_v5/analysis/build_offer_pilot.py`, `run_stata_offer_pilot.do`, and the within-estimator logic in `verify_and_plot.py` |

Other versions, exploratory branches, drafts, and datasets are not part of this code selection. Source filenames describe provenance, not files that the public scripts require at runtime.
