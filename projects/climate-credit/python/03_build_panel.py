"""Build quarterly loan balances, facility counts, and origination counts.

Subsidiary amounts are summed within parent-facility cells before counting.
Balances follow the source convention: active through the maturity quarter."""

import os, gc
import numpy as np
import pandas as pd
from config import OUT, PANEL_START, PANEL_END, BURN_IN_FROM, SIC_NACE

print("STAGE 3 — building the panel\n")
df = pd.read_parquet(os.path.join(OUT, "tranches_emis.parquet"))
print(f"  tranche rows {len(df):,}")

# Same definition as the previous cleaning code: NACE-based, with financials
# identified from the SIC range.
nace = pd.read_excel(SIC_NACE)[["sic", "nace2_by_NAICS"]].dropna()
nace["sic"] = pd.to_numeric(nace["sic"], errors="coerce")
nace = nace.dropna().drop_duplicates(subset="sic")
nace["sic"] = nace["sic"].astype(int)
df = df.merge(
    nace.rename(columns={"nace2_by_NAICS": "nace"}),
    left_on="sic",
    right_on="sic",
    how="left",
)
df.loc[df["nace"].isna() & df["sic"].between(111, 191), "nace"] = 1
df.loc[df["nace"].isna() & df["sic"].eq(8999), "nace"] = 96

df["sector"] = "g"
b = df["nace"].between(1, 39.99) | df["nace"].between(49, 53.99)
df.loc[b, "sector"] = "b"
df.loc[df["sic"].between(6000, 6411), "sector"] = "f"
print(
    "  sector shares:",
    {k: f"{100*v/len(df):.1f}%" for k, v in df["sector"].value_counts().items()},
)

# One row per borrower. Borrowers whose SIC or country is inconsistent across
# records are dropped, exactly as the previous code did.
firm_cols = [
    "borrower_name",
    "cborrow",
    "sic",
    "sic2",
    "sic3",
    "sector",
    "emissionintensity",
    "emissioncategory",
    "emis_match",
    "direct_emissions_ton",
    "embodied_intensity",
]
firms = df[firm_cols].drop_duplicates(subset="borrower_name", keep="first")
nsic = df.groupby("borrower_name", observed=True)["sic"].nunique()
ncty = df.groupby("borrower_name", observed=True)["cborrow"].nunique()
bad = set(nsic[nsic > 1].index) | set(ncty[ncty > 1].index)
firms = firms[~firms["borrower_name"].isin(bad)]
df = df[~df["borrower_name"].isin(bad)]
print(f"  borrowers with inconsistent SIC or country dropped: {len(bad):,}")
print(f"  borrowers kept: {len(firms):,}")

# Check facility dates before combining subsidiary lender shares.
chk = df.groupby("LPC_Tranche_ID", observed=True).agg(
    na=("yq_active", "nunique"),
    nm=("yq_maturity", "nunique"),
    nb=("borrower_name", "nunique"),
)
bad_tr = int(((chk.na > 1) | (chk.nm > 1) | (chk.nb > 1)).sum())
assert bad_tr == 0, f"{bad_tr} tranches have inconsistent dates/borrower"
print(f"  tranche dates consistent: {len(chk):,} tranche ids, 0 violations")
del chk

n0 = len(df)
_agg = {
    c: "first"
    for c in df.columns
    if c not in ("lender_parent_name", "borrower_name", "LPC_Tranche_ID", "amount")
}
_agg["amount"] = "sum"
df = df.groupby(
    ["lender_parent_name", "borrower_name", "LPC_Tranche_ID"],
    observed=True,
    as_index=False,
    sort=False,
).agg(_agg)
print(
    f"  parent-subsidiary duplicate rows collapsed: {n0 - len(df):,}"
    f"  ->  {len(df):,} pair-facility rows"
)

q0 = pd.Period(f"{BURN_IN_FROM}Q1", "Q").ordinal
qS = pd.Period(f"{PANEL_START}Q1", "Q").ordinal
qE = pd.Period(f"{PANEL_END}Q4", "Q").ordinal

a_orig = pd.PeriodIndex(df["yq_active"], freq="Q").astype("int64").values
m = pd.PeriodIndex(df["yq_maturity"], freq="Q").astype("int64").values
a = np.maximum(a_orig, q0)
m = np.minimum(m, qE)
alive = m - a + 1
ok = alive > 0
print(f"  tranches alive in window: {int(ok.sum()):,}")

pair_codes, pair_uniques = pd.factorize(
    pd.Series(list(zip(df["lender_parent_name"], df["borrower_name"])))
)
pc = pair_codes[ok]
aa = a[ok]
nn = alive[ok]
if not ok.any():
    raise ValueError("No facilities overlap the panel window.")
amt = df["amount"].values[ok]

rep_pair = np.repeat(pc, nn)
rep_amt = np.repeat(amt, nn)
offsets = np.concatenate([np.arange(k) for k in nn])
rep_q = np.repeat(aa, nn) + offsets
print(f"  expanded pair-quarter rows: {len(rep_q):,}")

# Sum balances and count facilities separately.
sparse = (
    pd.DataFrame({"pair": rep_pair, "q": rep_q, "outstand": rep_amt})
    .groupby(["pair", "q"], observed=True, sort=False)
    .agg(outstand=("outstand", "sum"), n_out=("outstand", "size"))
    .reset_index()
)
del rep_pair, rep_amt, rep_q, offsets
gc.collect()
print(f"  distinct pair-quarters with a balance: {len(sparse):,}")

# Facilities ORIGINATED in the quarter. Dated on the unclipped activation
# quarter, so a tranche that started before the burn-in is not miscounted as
# new in the first quarter of the window.
newc = (
    pd.DataFrame({"pair": pc, "q": a_orig[ok]})
    .groupby(["pair", "q"], observed=True, sort=False)
    .size()
    .rename("n_new")
    .reset_index()
)
sparse = sparse.merge(newc, on=["pair", "q"], how="left")
sparse["n_new"] = sparse["n_new"].fillna(0)
sparse["n_out"] = sparse["n_out"].astype("int32")
sparse["n_new"] = sparse["n_new"].astype("int32")
del newc
gc.collect()
print(
    f"  facilities per active pair-quarter: mean "
    f"{sparse['n_out'].mean():.2f}, median {sparse['n_out'].median():.0f}, "
    f"max {sparse['n_out'].max()}"
)
print(f"  pair-quarters with an origination: " f"{int((sparse['n_new'] > 0).sum()):,}")

pairs = pd.DataFrame(
    list(pair_uniques), columns=["lender_parent_name", "borrower_name"]
)
pairs["pair"] = np.arange(len(pairs))
lend = df[["lender_parent_name", "clpar"]].drop_duplicates(subset="lender_parent_name")
pairs = pairs.merge(lend, on="lender_parent_name", how="left")
print(f"  distinct bank-firm pairs: {len(pairs):,}")


def decorate(t):
    t = t.merge(pairs, on="pair", how="left").merge(
        firms, on="borrower_name", how="left"
    )
    t["yq"] = pd.PeriodIndex.from_ordinals(t["q"].values, freq="Q").to_timestamp()
    return t.drop(columns=["pair", "q"])


sp = decorate(sparse[sparse["q"].between(qS, qE)].copy())
sp.to_parquet(os.path.join(OUT, "panel_sparse.parquet"), index=False)
print(f"\n  wrote panel_sparse.parquet  {len(sp):,} rows")
del sp
gc.collect()

# Every pair appears in every quarter of the reported window, with zeros where
# it has no balance — the same construction as the current dataset, so the
# extensive-margin regressions can be run unchanged.
import pyarrow as pa, pyarrow.parquet as pq

sparse = sparse.set_index(["pair", "q"])[["outstand", "n_out", "n_new"]]
allp = pairs["pair"].values
writer = None
rect_path = os.path.join(OUT, "panel.parquet")
total = 0
for qq in range(qS, qE + 1):
    blk = pd.DataFrame({"pair": allp, "q": qq})
    key = pd.MultiIndex.from_arrays([blk["pair"].values, blk["q"].values])
    sub = sparse.reindex(key)
    blk["outstand"] = sub["outstand"].fillna(0.0).values
    blk["n_out"] = sub["n_out"].fillna(0).astype("int32").values
    blk["n_new"] = sub["n_new"].fillna(0).astype("int32").values
    del sub
    blk = decorate(blk)
    tbl = pa.Table.from_pandas(blk, preserve_index=False)
    if writer is None:
        writer = pq.ParquetWriter(rect_path, tbl.schema, compression="snappy")
    writer.write_table(tbl)
    total += len(blk)
    del blk, tbl
if writer is not None:
    writer.close()
print(
    f"  wrote panel.parquet         {total:,} rows "
    f"({len(allp):,} pairs x {qE-qS+1} quarters)"
)
print(
    f"\n  panel window {PANEL_START}Q1 - {PANEL_END}Q4 "
    f"(history from {BURN_IN_FROM}Q1 used to build stocks)"
)
