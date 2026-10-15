"""Match borrowers to project-specific EXIOBASE tables.

Prefer three-digit SIC matches, then two-digit matches. Keep the match level."""

import os
import numpy as np
import pandas as pd
from config import OUT, EXIO_DIR, EXIO_EU_REGIONS

VALUE_COLS = {
    "emission intensity": "emissionintensity",
    "emission category": "emissioncategory",
    "direct_emissions_ton": "direct_emissions_ton",
    "embodied_intensity_ton_per_$": "embodied_intensity",
    "direct_emissions_per_value_added_ton_per_$": "direct_emis_per_va",
    "gross_output": "gross_output",
    "value_added": "value_added",
}


def load(fname, has_region):
    df = pd.read_csv(os.path.join(EXIO_DIR, fname))
    df = df.rename(columns=VALUE_COLS)
    df["sic_key"] = pd.to_numeric(df["SIC Code"], errors="coerce")
    df = df[df["sic_key"].notna()]
    df["sic_key"] = df["sic_key"].astype(int)
    cols = ["sic_key"] + [v for v in VALUE_COLS.values() if v in df.columns]
    if has_region:
        df["region"] = df["region"].astype(str).str.strip().str.upper()
        cols = ["region"] + cols
        if df.duplicated(["region", "sic_key"]).any():
            raise ValueError(f"Duplicate country-SIC keys in {fname}")
    else:
        if df.duplicated(["sic_key"]).any():
            raise ValueError(f"Duplicate SIC keys in {fname}")
    return df[cols]


print("STAGE 2 — merging EXIOBASE emissions\n")
us3 = load("exio_US_report_average_2000_2015.csv", False)
us2 = load("exio_US_report_average_2000_2015_2digit_SIC.csv", False)
eu3 = load("exio_EU_GB_report_average_2000_2015_3digit_SIC.csv", True)
eu2 = load("exio_EU_GB_report_average_2000_2015_2digit_SIC.csv", True)
print(f"  US  3-digit rows {len(us3):>6,}   2-digit rows {len(us2):>6,}")
print(
    f"  EU  3-digit rows {len(eu3):>6,}   2-digit rows {len(eu2):>6,}"
    f"   ({eu3.region.nunique()} regions)"
)

df = pd.read_parquet(os.path.join(OUT, "tranches.parquet"))
print(f"  tranche rows     {len(df):>6,}")

VALS = [v for v in VALUE_COLS.values()]
for c in VALS:
    df[c] = (
        np.nan
        if c != "emissioncategory"
        else pd.Series(pd.NA, index=df.index, dtype="object")
    )
df["emis_match"] = "none"


def apply_match(mask, table, left_keys, right_keys, label):
    """Fill emission columns for rows in `mask` that match `table`."""
    if mask.sum() == 0:
        return 0
    sub = df.loc[mask, left_keys].copy()
    sub["_row"] = df.index[mask]
    m = sub.merge(
        table,
        left_on=left_keys,
        right_on=right_keys,
        how="inner",
        validate="many_to_one",
    )
    if len(m) == 0:
        return 0
    idx = m["_row"].values
    for c in VALS:
        if c in m.columns:
            df.loc[idx, c] = m[c].values
    df.loc[idx, "emis_match"] = label
    return len(m)


is_us = df["cborrow"].eq("USA")
is_eu = df["cborrow"].isin(EXIO_EU_REGIONS)
print(
    f"\n  borrowers in USA {int(is_us.sum()):>9,} | in EXIOBASE EU {int(is_eu.sum()):>9,}"
    f" | elsewhere {int((~is_us & ~is_eu).sum()):>9,}"
)

# --- pass 1: three-digit SIC -----------------------------------------------
n = apply_match(is_us, us3, ["sic3"], ["sic_key"], "us_3digit")
print(f"\n  US  matched at 3 digits {n:>9,}")
n = apply_match(is_eu, eu3, ["cborrow", "sic3"], ["region", "sic_key"], "eu_3digit")
print(f"  EU  matched at 3 digits {n:>9,}")

# --- pass 2: two-digit fallback for whatever is still unmatched ------------
todo = df["emis_match"].eq("none")
n = apply_match(is_us & todo, us2, ["sic2"], ["sic_key"], "us_2digit")
print(f"  US  matched at 2 digits {n:>9,}  (fallback)")
todo = df["emis_match"].eq("none")
n = apply_match(
    is_eu & todo, eu2, ["cborrow", "sic2"], ["region", "sic_key"], "eu_2digit"
)
print(f"  EU  matched at 2 digits {n:>9,}  (fallback)")

print("\n  match level:")
vc = df["emis_match"].value_counts()
for k, v in vc.items():
    print(f"    {k:<12} {v:>10,}  ({100*v/len(df):5.1f}%)")
have = df["emissionintensity"].notna()
print(f"\n  rows with emissions      {int(have.sum()):>10,} ({100*have.mean():5.1f}%)")
print(
    f"  of US rows               {100*df.loc[is_us,'emissionintensity'].notna().mean():5.1f}%"
)
print(
    f"  of EXIOBASE-EU rows      {100*df.loc[is_eu,'emissionintensity'].notna().mean():5.1f}%"
)
print("\n  category shares (rows with emissions):")
cc = df.loc[have, "emissioncategory"].astype(str).str.strip().str.lower().value_counts()
for k, v in cc.items():
    print(f"    {k:<8} {v:>10,}  ({100*v/have.sum():5.1f}%)")

# unmatched SICs worth knowing about
un = df.loc[(is_us | is_eu) & ~have, "sic2"].value_counts().head(8)
if len(un):
    print("\n  most common 2-digit SIC still unmatched:")
    for k, v in un.items():
        print(f"    sic2 {int(k):<4} {v:>9,}")

path = os.path.join(OUT, "tranches_emis.parquet")
df.to_parquet(path, index=False)
print(f"\nwrote {path}")
