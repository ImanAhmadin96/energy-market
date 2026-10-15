"""Clean origination records and allocate lender shares.

Outputs one lender-tranche row per retained record and prints sample attrition."""

import os, re, sys
import numpy as np
import pandas as pd
from config import (
    RAW_CSV,
    OUT,
    RAW_COLS,
    COUNTRY_ISO3,
    AE,
    GOV_SIC,
    PARTIAL_RULE,
    BURN_IN_FROM,
    PANEL_END,
)


def step(msg, df, prev=None):
    n = len(df)
    d = f"   (-{prev - n:,})" if prev is not None else ""
    print(f"  {msg:<52} {n:>10,}{d}")
    return n


print("STAGE 1 — cleaning Dealscan\n")

print("reading (chunked, origination rows only)...")
chunks = []
for ch in pd.read_csv(
    RAW_CSV,
    usecols=RAW_COLS,
    dtype=str,
    chunksize=400_000,
    encoding="utf-8",
    encoding_errors="replace",
    low_memory=False,
):
    chunks.append(ch[ch["Tranche_O_A"] == "Origination"])
df = pd.concat(chunks, ignore_index=True)
del chunks
prev = step("origination rows", df)

df["active"] = pd.to_datetime(df["Tranche_Active_Date"], errors="coerce")
df["maturity"] = pd.to_datetime(df["Tranche_Maturity_Date"], errors="coerce")
df = df[df["active"].notna() & df["maturity"].notna()]
prev = step("with both active and maturity dates", df, prev)

df = df[df["maturity"] >= df["active"]]
prev = step("maturity not before activation", df, prev)

df = df.drop_duplicates()
prev = step("after dropping exact duplicate rows", df, prev)

# Among multiple records of the same tranche, keep the earliest activation year
df["ayear"] = df["active"].dt.year
key = ["LPC_Deal_ID", "LPC_Tranche_ID"]
df["minyear"] = df.groupby(key, observed=True)["ayear"].transform("min")
df = df[df["ayear"] == df["minyear"]].drop(columns=["minyear"])
prev = step("earliest activation year per tranche", df, prev)

# A lender should appear once per tranche. Where it does not, prefer the record
# carrying a reported share; if duplicates survive, drop the whole tranche —
# the same conservative rule the previous code used.
df["ndup"] = df.groupby(key + ["Lender_Id"], observed=True)["Lender_Id"].transform(
    "size"
)
has_share = df["Lender_Share"].notna() & (df["Lender_Share"] != "N/A")
df = df[(df["ndup"] == 1) | ((df["ndup"] > 1) & has_share)]
df["ndup"] = df.groupby(key + ["Lender_Id"], observed=True)["Lender_Id"].transform(
    "size"
)
df["maxdup"] = df.groupby(key, observed=True)["ndup"].transform("max")
df = df[df["maxdup"] == 1].drop(columns=["ndup", "maxdup"])
prev = step("one record per lender per tranche", df, prev)

df["amount"] = pd.to_numeric(df["Tranche_Amount_Converted"], errors="coerce")
df = df[df["amount"].notna() & (df["amount"] > 0)]
prev = step("with a positive converted tranche amount", df, prev)

# share_raw is the reported percentage; missing where Dealscan gives "N/A".
df["share_raw"] = pd.to_numeric(df["Lender_Share"], errors="coerce")
g = df.groupby(key, observed=True)["share_raw"]
df["n_lender"] = g.transform("size")
df["n_known"] = g.transform("count")
df["sum_known"] = g.transform("sum").fillna(0.0)

if (df["share_raw"].dropna() < 0).any():
    raise ValueError("Negative lender shares require source review.")
partial = (df["n_known"] > 0) & (df["n_known"] < df["n_lender"])
if (df.loc[partial, "sum_known"] > 100.000001).any():
    raise ValueError("Partial syndicate shares exceed 100%; review the source.")
share = pd.Series(np.nan, index=df.index)

# (a) every lender reports: rescale so the tranche sums to one
m = df["n_known"] == df["n_lender"]
share[m] = df.loc[m, "share_raw"] / df.loc[m, "sum_known"].replace(0, np.nan)

# (b) nobody reports: split equally
m = df["n_known"] == 0
share[m] = 1.0 / df.loc[m, "n_lender"]

# (c) some report: honour them, split the remainder equally among the rest
m = (df["n_known"] > 0) & (df["n_known"] < df["n_lender"])
if PARTIAL_RULE == "prorata":
    tot = (df.loc[m, "sum_known"] / 100.0).clip(upper=1.0)
    rest = (1.0 - tot) / (df.loc[m, "n_lender"] - df.loc[m, "n_known"])
    share[m] = np.where(
        df.loc[m, "share_raw"].notna(),
        df.loc[m, "share_raw"] / 100.0,
        rest.clip(lower=0.0),
    )
    print(
        f"  partial-share tranches allocated pro rata "
        f"({int(m.sum()):,} lender-rows kept)"
    )
elif PARTIAL_RULE == "drop":
    print(f"  partial-share tranches dropped ({int(m.sum()):,} lender-rows)")

else:
    raise ValueError("PARTIAL_RULE must be prorata or drop")

df["share"] = share
df = df[df["share"].notna() & (df["share"] > 0)]
prev = step("with an allocated share", df, prev)

df["lender_amount"] = df["amount"] * df["share"]

sic = df["SIC_Code"].fillna("").str.extract(r"^\s*(\d+)", expand=False)
df["sic"] = pd.to_numeric(sic, errors="coerce")
df = df[df["sic"].notna()]
prev = step("with a numeric SIC code", df, prev)

# 4-digit codes give sic3 = first three digits, sic2 = first two. 3-digit codes
# are already at the 3-digit level, so sic3 is the code itself.
s = df["sic"].astype(int).astype(str)
df["sic3"] = np.where(s.str.len() >= 4, s.str[:3], s.str.zfill(3)).astype(int)
df["sic2"] = np.where(s.str.len() >= 4, s.str[:2], s.str[:2]).astype(int)

df = df[~df["sic"].between(*GOV_SIC)]
prev = step("after removing government SIC codes", df, prev)

df["cborrow"] = df["Country"].map(COUNTRY_ISO3)
df["clpar"] = df["Lender_Parent_Operating_Country"].map(COUNTRY_ISO3)
df = df[df["cborrow"].notna() & df["clpar"].notna()]
prev = step("with both countries mapped to ISO3", df, prev)

df = df[df["cborrow"].isin(AE) & df["clpar"].isin(AE)]
prev = step("advanced-economy bank AND firm", df, prev)

df["yq_active"] = df["active"].dt.to_period("Q")
df["yq_maturity"] = df["maturity"].dt.to_period("Q")
lo = pd.Period(f"{BURN_IN_FROM}Q1", "Q")
hi = pd.Period(f"{PANEL_END}Q4", "Q")
df = df[(df["yq_maturity"] >= lo) & (df["yq_active"] <= hi)]
prev = step(f"alive at some point in {BURN_IN_FROM}Q1-{PANEL_END}Q4", df, prev)

df = df[
    (df["Lender_Parent_Name"].notna())
    & (df["Lender_Parent_Name"] != "")
    & (df["Borrower_Name"].notna())
    & (df["Borrower_Name"] != "")
]
prev = step("with both names present", df, prev)

keep = [
    "Lender_Parent_Name",
    "clpar",
    "Borrower_Name",
    "cborrow",
    "sic",
    "sic2",
    "sic3",
    "lender_amount",
    "yq_active",
    "yq_maturity",
    "LPC_Deal_ID",
    "LPC_Tranche_ID",
]
out = df[keep].rename(
    columns={
        "Lender_Parent_Name": "lender_parent_name",
        "Borrower_Name": "borrower_name",
        "lender_amount": "amount",
    }
)
out["yq_active"] = out["yq_active"].astype(str)
out["yq_maturity"] = out["yq_maturity"].astype(str)
path = os.path.join(OUT, "tranches.parquet")
out.to_parquet(path, index=False)

print(f"\n  distinct lenders   {out.lender_parent_name.nunique():>9,}")
print(f"  distinct borrowers {out.borrower_name.nunique():>9,}")
print(f"  distinct tranches  {out.LPC_Tranche_ID.nunique():>9,}")
print(f"  activation years   {out.yq_active.min()} .. {out.yq_active.max()}")
print(f"\nwrote {path}")
