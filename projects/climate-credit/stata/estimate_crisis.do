* Exploratory stock and extensive-margin specifications.
* Run from projects/climate-credit after the Python build and export.
* This project is joint work with Givi Melkadze and Giseong Kim.
version 19
clear all
set more off
set varabbrev off
capture log close
log using "output/crisis_models.log", text replace
use "output/dealscan_exio_EU_USA_2000_2019.dta", clear
isid lender_parent_name borrower_name yq
format yq %tq
drop if lower(trim(sector)) == "f"

generate byte category = .
replace category = 1 if lower(trim(emissioncategory)) == "green"
replace category = 2 if inlist(lower(trim(emissioncategory)), "gray", "grey")
replace category = 3 if lower(trim(emissioncategory)) == "brown"
drop if missing(category)
label define categories 1 "Green" 2 "Gray" 3 "Brown"
label values category categories
generate byte active = outstand > 0 if !missing(outstand)
generate double log_balance = ln(outstand) if outstand > 0
egen long lender = group(lender_parent_name)
egen long borrower = group(borrower_name)
egen long relationship = group(lender borrower)

* Restrict lenders using distinct borrowers active before the crisis.
bysort lender borrower: egen byte pre_active = max(active == 1 & inrange(yq,yq(2006,1),yq(2007,2)))
egen byte pair_tag = tag(lender borrower)
generate byte eligible = pair_tag * pre_active
bysort lender: egen long pre_borrowers = total(eligible)
keep if pre_borrowers >= 5

* Country windows retained from the source analysis.
generate byte crisis = 0
replace crisis = 1 if clpar == "USA" & inrange(yq,yq(2007,3),yq(2009,2))
replace crisis = 1 if inlist(clpar,"AUT","DEU","FRA","NLD","DNK","SWE","ITA") & inrange(yq,yq(2008,3),yq(2009,4))
replace crisis = 1 if inlist(clpar,"GRC","ESP","PRT","IRL","BEL","HUN","LVA","LUX","SVN") & inrange(yq,yq(2008,3),yq(2012,4))
replace crisis = 1 if clpar == "GBR" & inrange(yq,yq(2008,3),yq(2011,4))
egen long borrower_quarter = group(borrower yq)

postfile models str16 outcome str24 effects long observations double gray_b gray_se brown_b brown_se equal_p using "output/crisis_results.dta", replace
foreach outcome in log_balance active {
    foreach specification in additive relationship demand {
        local effects "lender borrower yq"
        if "`specification'" == "relationship" local effects "relationship yq"
        if "`specification'" == "demand" local effects "relationship borrower_quarter"
        areg `outcome' i.crisis 1.crisis#2.category 1.crisis#3.category, absorb(`effects') vce(cluster lender)
        if _se[1.crisis#2.category] == 0 | _se[1.crisis#3.category] == 0 {
            display as error "An interaction is omitted; inspect identification before reporting."
            exit 459
        }
        test 1.crisis#2.category = 1.crisis#3.category
        post models ("`outcome'") ("`specification'") (e(N)) (_b[1.crisis#2.category]) (_se[1.crisis#2.category]) (_b[1.crisis#3.category]) (_se[1.crisis#3.category]) (r(p))
    }
}
postclose models
use "output/crisis_results.dta", clear
export delimited using "output/crisis_results.csv", replace
log close
