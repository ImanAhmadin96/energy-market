* Run from projects/carbon-pass-through after python/build_offer_pilot.py.
version 19
clear all
set more off
capture log close
log using "output/stata_offer_pilot.log", text replace
local out "output"
postfile results str28 sample str18 specification str12 covariance long n double fuel_b fuel_se carbon_b carbon_se df using "`out'/stata_offer_results.dta", replace
foreach sample in legacy_qw comparable_mid prior_training_mid {
    import delimited "`out'/`sample'.csv", clear
    isid uid day
    local specifications "baseline trends"
    if "`sample'" == "legacy_qw" local specifications "baseline trends hr6to9"
    if "`sample'" == "prior_training_mid" local specifications "baseline trends unit_yearmonth"
    foreach spec of local specifications {
        preserve
        local extra ""
        local absorb "uid day"
        if "`spec'" == "trends" local extra "i.uid#c.trend"
        if "`spec'" == "hr6to9" keep if inrange(hr,6,9)
        if "`spec'" == "unit_yearmonth" {
            egen uidym=group(uid yearmonth)
            local absorb "uidym day"
        }
        foreach cov in unit date twoway {
            local cluster "uid"
            if "`cov'" == "date" local cluster "day"
            if "`cov'" == "twoway" local cluster "uid day"
            noisily display "MODEL: `sample' `spec' `cov'"
            areg y fuel carbon `extra', absorb(`absorb') vce(cluster `cluster')
            post results ("`sample'") ("`spec'") ("`cov'") (e(N)) (_b[fuel]) (_se[fuel]) (_b[carbon]) (_se[carbon]) (e(df_r))
        }
        restore
    }
}
postclose results
use "`out'/stata_offer_results.dta", clear
export delimited using "`out'/stata_offer_results.csv", replace
log close
