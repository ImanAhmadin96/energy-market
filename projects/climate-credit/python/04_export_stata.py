"""Export European and EU-US samples with Stata quarterly dates."""

import os
import numpy as np
import pandas as pd
from config import OUT, PANEL_START, PANEL_END, EU28

KEEP = [
    "lender_parent_name",
    "clpar",
    "borrower_name",
    "cborrow",
    "sector",
    "yq",
    "outstand",
    "emissionintensity",
    "emissioncategory",
    "sic",
    "sic2",
    "sic3",
    "n_out",
    "n_new",
]
EU_US = EU28 + ["USA"]


def tidy(d):
    d = d[KEEP].copy()
    # Stata dislikes pandas NA in string columns; the current file uses ""
    d["emissioncategory"] = d["emissioncategory"].astype("object").fillna("")
    d["sector"] = d["sector"].astype("object").fillna("")
    for c in ["sic", "sic2", "sic3", "n_out", "n_new"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").astype("float64")
    d["outstand"] = d["outstand"].astype("float64")
    d["emissionintensity"] = d["emissionintensity"].astype("float64")
    return d


EXPORT_CSV = True  # gzip CSV is far smaller to move than .dta


def write(d, name):
    d = tidy(d)
    path = os.path.join(OUT, name)
    d.to_stata(path, write_index=False, version=117, convert_dates={"yq": "tq"})
    mb = os.path.getsize(path) / 1e6
    msg = f"    {name:<44} {len(d):>11,} rows   {mb:>7.0f} MB"
    if EXPORT_CSV:
        cpath = path.replace(".dta", ".csv.gz")
        d.to_csv(cpath, index=False, compression="gzip")
        msg += f"   + csv.gz {os.path.getsize(cpath)/1e6:>5.0f} MB"
    print(msg)


for tag, src in [("", "panel.parquet"), ("_sparse", "panel_sparse.parquet")]:
    print(f"\n  reading {src} ...")
    df = pd.read_parquet(os.path.join(OUT, src), columns=KEEP)
    df["clpar"] = df["clpar"].astype(str)
    df["cborrow"] = df["cborrow"].astype(str)

    m = df["clpar"].isin(EU_US) & df["cborrow"].isin(EU_US)
    write(df[m], f"dealscan_exio_EU_USA_{PANEL_START}_{PANEL_END}{tag}.dta")

    m = df["clpar"].isin(EU28) & df["cborrow"].isin(EU_US)
    write(df[m], f"dealscan_exio_EUROPE_{PANEL_START}_{PANEL_END}{tag}.dta")
    del df

print(f"\n  files are in {OUT}")
print("  point GL_GLOBALDTA at the EU_USA file and GL_EURODTA at the EUROPE file")
