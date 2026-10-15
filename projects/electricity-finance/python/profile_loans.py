"""Profile syndicated loans."""

from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / "data/raw/dealscan.csv"
COLS = [
    "Borrower_Name",
    "Borrower_Id",
    "Additional_Borrowers",
    "Ticker",
    "State_Province",
    "Country",
    "Broad_Industry_Group",
    "Major_Industry_Group",
    "SIC_Code",
    "NAIC",
    "Borrower_Type",
    "Parent",
    "Organization_Type",
    "LPC_Deal_ID",
    "Deal_Amount_Converted",
    "Deal_Active_Date",
    "Deal_Input_Date",
    "Deal_Purpose",
    "Project_Finance",
    "Phase",
    "Deal_Active",
    "Deal_Refinancing",
    "LPC_Tranche_ID",
    "Tranche_Type",
    "Tranche_Active_Date",
    "Tranche_Maturity_Date",
    "Tranche_Amount",
    "Tranche_Amount_Converted",
    "League_Table_Amount_Converted",
    "Tranche_Currency",
    "Market_Segment",
    "Primary_Purpose",
    "Secondary_Purpose",
    "Tranche_Refinancing",
    "Tranche_Active",
    "Tenor_Maturity",
    "Closed_Date",
    "Completion_Date",
    "Launch_Date",
    "New_Money_Converted",
    "All_In_Spread_Drawn_bps",
    "Number_of_Lenders",
    "CAPEX_Initial_USD",
    "CAPEX_Final_USD",
]
parts = []
total = 0
usrows = 0
datecounts = []
countries = []
for i, c in enumerate(pd.read_csv(SRC, usecols=COLS, dtype="string", chunksize=50000)):
    total += len(c)
    datecounts.append(
        c.groupby(["Deal_Active_Date", "Tranche_Active_Date"], dropna=False).size()
    )
    countries.append(c.Country.value_counts(dropna=False))
    u = c[c.Country.eq("United States")].copy()
    usrows += len(u)
    parts.append(u.drop_duplicates())
    print(f"chunk {i+1}: {total:,} rows; {usrows:,} US rows", flush=True)
u = pd.concat(parts, ignore_index=True).drop_duplicates()
u.to_pickle(OUT / "us_versions.pkl")
audit = {
    "source_rows": total,
    "us_source_rows": usrows,
    "us_distinct_selected_records": len(u),
    "us_unique_tranches": u.LPC_Tranche_ID.nunique(),
    "us_unique_deals": u.LPC_Deal_ID.nunique(),
    "us_unique_borrowers": u.Borrower_Id.nunique(),
}
for col in ["Deal_Active_Date", "Tranche_Active_Date", "Deal_Input_Date"]:
    d = pd.to_datetime(u[col], errors="coerce")
    audit[col] = {
        "min": str(d.min()),
        "max": str(d.max()),
        "missing": int(d.isna().sum()),
        "years": d.dt.year.value_counts().sort_index().to_dict(),
    }
(OUT / "profile.json").write_text(json.dumps(audit, indent=2))
pd.concat(datecounts).groupby(level=[0, 1], dropna=False).sum().to_csv(
    OUT / "source_date_coverage.csv"
)
pd.concat(countries).groupby(level=0, dropna=False).sum().to_csv(
    OUT / "source_country_coverage.csv"
)
u.groupby(["SIC_Code", "NAIC"], dropna=False).agg(
    records=("LPC_Tranche_ID", "size"),
    tranches=("LPC_Tranche_ID", "nunique"),
    borrowers=("Borrower_Id", "nunique"),
).sort_values("tranches", ascending=False).to_csv(OUT / "industry_profile.csv")
print(json.dumps(audit, indent=2))
print(
    "\nUTILITY INDUSTRIES\n",
    u[
        u.SIC_Code.str.startswith("49", na=False)
        | u.NAIC.str.startswith("221", na=False)
    ]
    .groupby(["SIC_Code", "NAIC"], dropna=False)
    .agg(tranches=("LPC_Tranche_ID", "nunique"), borrowers=("Borrower_Id", "nunique"))
    .to_string(),
)
print("\nPHASES\n", u.Phase.value_counts(dropna=False).to_string())
