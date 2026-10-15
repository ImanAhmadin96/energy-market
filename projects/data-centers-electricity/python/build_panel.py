"""Build an hourly ERCOT hub-price, generation, load, and facility panel.

See the project README for inputs, units, and daylight-saving conventions."""

import pandas as pd
import numpy as np
import glob
import zipfile
import os
import re
from contextlib import ExitStack

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")
KEEP_SP = [
    "HB_WEST",
    "HB_NORTH",
    "HB_PAN",
    "HB_HOUSTON",
    "HB_HUBAVG",
    "LZ_WEST",
    "LZ_NORTH",
]


# ---------------- 1. RTM prices: 15-min -> hourly, wide by settlement point ----------------
def load_prices():
    with ExitStack() as stack:
        frames = []
        for f in sorted(
            glob.glob(os.path.join(BASE, "ercot/prices/*RTMLZHBSPP*.xlsx"))
        ):
            year = re.search(r"(20\d\d)", os.path.basename(f)).group(1)
            xl = stack.enter_context(pd.ExcelFile(f))
            for sh in xl.sheet_names:
                d = xl.parse(sh)
                d = d[d["Settlement Point Name"].isin(KEEP_SP)]
                if d.empty:
                    continue
                d["date"] = pd.to_datetime(d["Delivery Date"], format="%m/%d/%Y")
                # Delivery Hour is hour-ending 1..24; hour-beginning = hour-1
                d["hour"] = d["Delivery Hour"].astype(int) - 1
                # skip DST repeated hour duplicates (keep standard-time rows only)
                d = d[d["Repeated Hour Flag"] != "Y"]
                h = (
                    d.groupby(["date", "hour", "Settlement Point Name"])[
                        "Settlement Point Price"
                    ]
                    .mean()
                    .unstack("Settlement Point Name")
                )
                frames.append(h)
            print(
                f"  prices {year}: done ({len(frames)} month-sheets cumulative)",
                flush=True,
            )
        px = pd.concat(frames).sort_index()
        px.index = pd.to_datetime(
            [
                f"{d} {h:02d}:00"
                for d, h in zip(
                    px.index.get_level_values(0).strftime("%Y-%m-%d"),
                    px.index.get_level_values(1),
                )
            ]
        )
        px.index.name = "ts"
        return px


# ---------------- 2. Wind & solar hourly ----------------
def load_windsolar():
    with ExitStack() as stack:
        parts = []
        # (a) PG7-126-M hourly workbooks, 2023-2025
        for f in sorted(
            glob.glob(
                os.path.join(
                    BASE, "ercot/wind_solar/ERCOT_*_Hourly_WindSolar_Output.xlsx"
                )
            )
        ):
            xl = stack.enter_context(pd.ExcelFile(f))
            w = xl.parse("Wind Data")
            s = xl.parse("Solar Data")
            w = w.rename(
                columns={
                    "Time (Hour-Ending)": "te",
                    "ERCOT.WIND.GEN": "wind_mw",
                    "ERCOT.LOAD": "ercot_load_pg7",
                }
            )
            scol = [
                c
                for c in s.columns
                if "PVGR.GEN" in str(c) or "SOLAR" in str(c).upper()
            ]
            s = s.rename(columns={"Time (Hour-Ending)": "te", scol[0]: "solar_mw"})
            m = pd.merge(
                w[["te", "wind_mw"]], s[["te", "solar_mw"]], on="te", how="outer"
            )
            m["ts"] = pd.to_datetime(m["te"]) - pd.Timedelta(
                hours=1
            )  # hour-ending -> hour-beginning
            parts.append(m[["ts", "wind_mw", "solar_mw"]])
            print(f"  wind/solar PG7 {os.path.basename(f)}: {len(m)} h", flush=True)
        pg7 = pd.concat(parts)

        # (b) IntGenbyFuel 15-min workbooks for 2021, 2022 (from the archive zip) and 2026
        def parse_intgen(xlobj, year):
            rows = []
            for sh in xlobj.sheet_names:
                if sh.lower() in ("disclaimer", "summary") or sh.startswith("data_"):
                    continue
                d = xlobj.parse(sh)
                fuel_col = [
                    c
                    for c in d.columns
                    if str(c).strip().lower() in ("fuel", "fuel type")
                ]
                if not fuel_col:
                    continue
                fc = fuel_col[0]
                date_col = [c for c in d.columns if "date" in str(c).lower()][0]
                ivals = [
                    c for c in d.columns if re.match(r"^\d{1,2}:\d{2}$", str(c).strip())
                ]
                d = d[d[fc].astype(str).str.strip().str.lower().isin(["wind", "solar"])]
                m = d.melt(
                    id_vars=[date_col, fc],
                    value_vars=ivals,
                    var_name="ival",
                    value_name="mwh",
                )
                m["mins"] = m["ival"].map(
                    lambda x: int(str(x).split(":")[0]) * 60 + int(str(x).split(":")[1])
                )
                # labels are interval-ENDING, 0:15 .. 23:45 then '0:00' meaning 24:00 (end of day)
                m.loc[m["mins"] == 0, "mins"] = 1440
                m["hour"] = ((m["mins"] - 15) // 60).astype(int)
                m["date"] = pd.to_datetime(m[date_col])
                # values are MWh per 15-min interval, so the hourly sum equals average MW over the hour
                g = m.groupby(["date", "hour", fc])["mwh"].sum().unstack(fc)
                rows.append(g)
            out = pd.concat(rows).sort_index()
            out.index = pd.to_datetime(
                [
                    f"{d} {h:02d}:00"
                    for d, h in zip(
                        out.index.get_level_values(0).strftime("%Y-%m-%d"),
                        out.index.get_level_values(1),
                    )
                ]
            )
            out = out.rename(columns=lambda c: str(c).strip().lower())
            out = out.rename(columns={"wind": "wind_mw", "solar": "solar_mw"})
            print(f"  IntGenbyFuel {year}: {len(out)} h", flush=True)
            return out[["wind_mw", "solar_mw"]].reset_index(names="ts")

        z = stack.enter_context(
            zipfile.ZipFile(
                os.path.join(BASE, "ercot/wind_solar/FuelMixReport_PreviousYears.zip")
            )
        )
        ig = []
        for year in ("2021", "2022"):
            name = [
                n for n in z.namelist() if year in n and n.endswith((".xlsx", ".xls"))
            ]
            if name:
                ig.append(
                    parse_intgen(
                        stack.enter_context(
                            pd.ExcelFile(stack.enter_context(z.open(name[0])))
                        ),
                        year,
                    )
                )
        f26 = glob.glob(os.path.join(BASE, "ercot/wind_solar/IntGenbyFuel2026*.xlsx"))
        if f26:
            ig.append(parse_intgen(stack.enter_context(pd.ExcelFile(f26[0])), "2026"))
        intgen = pd.concat(ig)

        # Compare the overlapping 2023 wind series; this is a diagnostic, not a test.
        z23 = [n for n in z.namelist() if "2023" in n and n.endswith((".xlsx", ".xls"))]
        if z23:
            chk = parse_intgen(
                stack.enter_context(pd.ExcelFile(stack.enter_context(z.open(z23[0])))),
                "2023-check",
            )
            j = pd.merge(pg7, chk, on="ts", suffixes=("_pg7", "_ig"))
            if len(j) > 1000:
                corr = j["wind_mw_pg7"].corr(j["wind_mw_ig"])
                print(
                    f"  CROSS-CHECK 2023 wind, PG7 vs IntGen: corr={corr:.4f}, "
                    f"mean diff={np.mean(j.wind_mw_pg7 - j.wind_mw_ig):.1f} MW",
                    flush=True,
                )

        ws = (
            pd.concat(
                [
                    intgen[intgen.ts < "2023-01-01"],
                    pg7,
                    intgen[intgen.ts >= "2026-01-01"],
                ]
            )
            .drop_duplicates("ts")
            .set_index("ts")
            .sort_index()
        )
        return ws


# ---------------- 3. Load by weather zone ----------------
def load_native():
    with ExitStack() as stack:
        parts = []
        for f in sorted(glob.glob(os.path.join(BASE, "ercot/load/Native_Load_*.zip"))):
            z = stack.enter_context(zipfile.ZipFile(f))
            inner = [n for n in z.namelist() if n.endswith((".xlsx", ".xls", ".csv"))][
                0
            ]
            d = (
                pd.read_excel(stack.enter_context(z.open(inner)))
                if not inner.endswith(".csv")
                else pd.read_csv(stack.enter_context(z.open(inner)))
            )
            hc = d.columns[0]
            he = d[hc].astype(str).str.replace(" DST", "", regex=False)
            # 'MM/DD/YYYY 24:00' -> next day 00:00
            is24 = he.str.contains(" 24:00")
            he = he.str.replace(" 24:00", " 00:00")
            ts = pd.to_datetime(he, errors="coerce")
            ts = ts + pd.to_timedelta(is24.astype(int), unit="D")
            d["ts"] = ts - pd.Timedelta(hours=1)  # hour-ending -> hour-beginning
            d = d.dropna(subset=["ts"]).drop_duplicates("ts")
            d = d.rename(columns={"FWEST": "load_fwest_mw", "ERCOT": "load_ercot_mw"})
            parts.append(d[["ts", "load_fwest_mw", "load_ercot_mw"]])
            print(f"  load {os.path.basename(f)}: {len(d)} h", flush=True)
        return pd.concat(parts).drop_duplicates("ts").set_index("ts").sort_index()


# ---------------- 4. Facility exposure from the tracker ----------------
# West Texas / Panhandle (ERCOT West + Far West weather zones): the upstream side of the
# historically binding West-to-East export constraints. Classification is by city and is
# audit-able in facilities_ercot_classified.csv.
WEST_CITIES = {
    "abilene",
    "childress",
    "odessa",
    "midland",
    "san angelo",
    "big spring",
    "sweetwater",
    "lubbock",
    "snyder",
    "colorado city",
    "monahans",
    "pecos",
    "fort stockton",
    "andrews",
    "plainview",
    "vernon",
    "quanah",
    "stanton",
    "mccamey",
    "rankin",
    "garden city",
    "brownfield",
    "levelland",
}


def load_facilities():
    g = pd.read_csv(os.path.join(BASE, "processed/datacenters_geocoded.csv"))
    tx = g[g["market_approx"].astype(str).str.contains("ERCOT", na=False)].copy()
    tx = tx[tx["Operational"].notna()]
    q = tx["Operational"].astype(str).str.extract(r"(\d{4})\s*Q(\d)")
    tx["op_month"] = pd.to_datetime(
        q[0]
        + "-"
        + ((q[1].astype(float) - 1) * 3 + 1).astype("Int64").astype(str)
        + "-01"
    )
    tx["mw"] = pd.to_numeric(tx["IT Power Live (MW)"], errors="coerce").fillna(0)
    tx["is_crypto"] = tx["Type"].astype(str).str.lower().eq("crypto") | tx[
        "Company"
    ].astype(str).str.lower().str.contains(
        "iren|riot|terawulf|cipher|bitdeer|core scientific|marathon|mara ", na=False
    )
    tx["is_west"] = tx["City"].astype(str).str.strip().str.lower().isin(WEST_CITIES)
    tx[
        [
            "Name",
            "Company",
            "City",
            "Type",
            "Category",
            "Operational",
            "mw",
            "is_west",
            "is_crypto",
        ]
    ].sort_values("mw", ascending=False).to_csv(
        os.path.join(OUT, "facilities_ercot_classified.csv"), index=False
    )
    months = pd.date_range("2021-01-01", "2026-06-01", freq="MS")
    exp = pd.DataFrame(index=months)
    for name, mask in [
        ("upfirm", tx.is_west & ~tx.is_crypto),
        ("upcrypto", tx.is_west & tx.is_crypto),
        ("downfirm", ~tx.is_west & ~tx.is_crypto),
        ("downcrypto", ~tx.is_west & tx.is_crypto),
    ]:
        sub = tx[mask]
        exp[f"cap_{name}_mw"] = [sub.loc[sub.op_month <= m, "mw"].sum() for m in months]
    print(
        "  facilities: ERCOT classified counts:",
        {
            k: int(v)
            for k, v in tx.groupby(tx.is_west.map({True: "west", False: "down"}))
            .size()
            .items()
        },
        "| crypto:",
        int(tx.is_crypto.sum()),
        flush=True,
    )
    return exp


def main():
    os.makedirs(OUT, exist_ok=True)
    print("1) prices...", flush=True)
    px = load_prices()
    print("2) wind/solar...", flush=True)
    ws = load_windsolar()
    print("3) load...", flush=True)
    ld = load_native()
    print("4) facilities...", flush=True)
    exp = load_facilities()
    panel = px.join(ws, how="inner").join(ld, how="left")
    panel["month"] = panel.index.to_period("M").to_timestamp()
    panel = panel.join(exp, on="month")
    panel["spread_wn"] = panel["HB_WEST"] - panel["HB_NORTH"]
    if "HB_PAN" in panel.columns:
        panel["spread_pn"] = panel["HB_PAN"] - panel["HB_NORTH"]
    panel.to_csv(os.path.join(OUT, "panel_hourly.csv"))
    print(f"PANEL: {len(panel)} hours, {panel.index.min()} .. {panel.index.max()}")
    print(
        panel[
            [
                "HB_WEST",
                "HB_NORTH",
                "wind_mw",
                "solar_mw",
                "load_ercot_mw",
                "cap_upfirm_mw",
                "cap_upcrypto_mw",
                "cap_downfirm_mw",
            ]
        ]
        .describe()
        .round(1)
        .to_string()
    )


if __name__ == "__main__":
    main()
