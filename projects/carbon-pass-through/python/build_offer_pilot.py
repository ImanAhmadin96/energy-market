"""Prepare daily offer-price samples and estimate earlier-period fuel proxies.

Fuel labels and heat rates are statistical proxies, not physical unit identities."""

from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
C = ROOT / "data/clean"
OUT.mkdir(parents=True, exist_ok=True)
calendar = pd.date_range("2019-01-01", "2024-12-31")
cal = pd.DataFrame(index=calendar)
gas = (
    pd.read_csv(
        ROOT / "data/gas_basis/algonquin_citygate_daily_v2.csv", parse_dates=["date"]
    )
    .set_index("date")
    .algonquin_spot
)
sec = pd.read_csv(C / "rggi_secondary_daily.csv", parse_dates=["date"]).set_index(
    "date"
)
oil = (
    pd.read_csv(
        C / "prices_daily.csv.gz",
        usecols=["date", "heating_oil_ny"],
        parse_dates=["date"],
    )
    .set_index("date")
    .heating_oil_ny
)
cal["gas0"] = gas.reindex(calendar).ffill()
cal["tau0"] = sec.price_ff.reindex(calendar).ffill()
for name, s in [("gas", gas), ("tau", sec.price_vw), ("oil", oil)]:
    v = s.reindex(calendar)
    dated = pd.Series(calendar, index=calendar).where(v.notna()).shift(1).ffill()
    cal[name + "1"] = v.shift(1).ffill()
    cal[name + "_age"] = (pd.Series(calendar, index=calendar) - dated).dt.days
cal["date"] = cal.index
frames = []
audit = []
ids = {}
for y in range(2019, 2027):
    p = C / f"offers_unit_hour_{y}.csv.gz"
    use = [
        "date",
        "hour",
        "masked_asset_id",
        "econ_max",
        "mw_offered",
        "unit_status",
        "price_qw",
        "price_at_median_mw",
    ]
    d = pd.read_csv(p, usecols=use, parse_dates=["date"])
    ids[y] = set(map(int, d.masked_asset_id.unique()))
    dup = d.duplicated(["masked_asset_id", "date", "hour"])
    audit.append(
        {
            "year": y,
            "records": len(d),
            "assets": len(ids[y]),
            "dates": d.date.nunique(),
            "first": str(d.date.min().date()),
            "last": str(d.date.max().date()),
            "duplicate_local_asset_date_hour": int(dup.sum()),
        }
    )
    if y > 2024:
        continue
    d = d[
        (d.unit_status == "ECONOMIC") & (d.econ_max > 0) & np.isfinite(d.price_qw)
    ].copy()
    d["mid_ok"] = (
        abs(d.mw_offered - d.econ_max) <= np.maximum(0.1, 0.01 * d.econ_max)
    ) & np.isfinite(d.price_at_median_mw)
    d["mid"] = d.price_at_median_mw.where(d.mid_ok)
    g = (
        d.groupby(["masked_asset_id", "date"])
        .agg(
            qw=("price_qw", "mean"),
            mid=("mid", "mean"),
            mid_hours=("mid", "count"),
            records=("qw" if "qw" in d else "price_qw", "size"),
            econ_max=("econ_max", "mean"),
        )
        .reset_index()
    )
    frames.append(g)
    print(y, len(d), len(g), flush=True)
all_days = pd.concat(frames, ignore_index=True).merge(
    cal, on="date", how="left", validate="m:1"
)
inf = pd.read_csv(C / "inferred_exposure_by_asset.csv")
legacy = inf[inf.fuel_inferred == "gas"].copy()
legacy["hr"] = legacy.implied_hr
# Original mixed-fuel primary labels are predictions, not identities.
full = all_days.merge(
    legacy[["masked_asset_id", "hr", "fit_r2"]], on="masked_asset_id", validate="m:1"
)
full = full[full.date.dt.year.between(2021, 2024)].copy()


def keep400(d):
    return d[d.groupby("masked_asset_id").date.transform("count") >= 400].copy()


def write(d, name, outcome, gcol, tcol):
    d = keep400(d.dropna(subset=[outcome, gcol, tcol, "hr"]))
    d["y"] = d[outcome]
    d["fuel"] = d.hr * d[gcol]
    d["carbon"] = d.hr * 0.0594 * d[tcol]
    d["uid"] = pd.Categorical(d.masked_asset_id).codes + 1
    d["day"] = (d.date - pd.Timestamp("1960-01-01")).dt.days
    d["trend"] = (d.date - pd.Timestamp("2021-01-01")).dt.days / 365.25
    d["month"] = d.date.dt.month
    d["yearmonth"] = d.date.dt.year * 12 + d.month
    d = d.sort_values(["uid", "day"])
    assert not d.duplicated(["uid", "day"]).any()
    cols = [
        "masked_asset_id",
        "uid",
        "day",
        "date",
        "trend",
        "month",
        "yearmonth",
        "hr",
        "fit_r2",
        "y",
        "fuel",
        "carbon",
        "mid_hours",
        "records",
        "econ_max",
    ]
    d[cols].to_csv(OUT / f"{name}.csv", index=False)
    return {
        "name": name,
        "n": len(d),
        "units": d.uid.nunique(),
        "dates": d.day.nunique(),
        "median_fit_r2": d.drop_duplicates("uid").fit_r2.median(),
        "mean_offer": d.y.mean(),
        "min_offer": d.y.min(),
        "max_offer": d.y.max(),
    }


info = [write(full, "legacy_qw", "qw", "gas0", "tau0")]
mid = full[(full.mid_hours >= 20) & (full.gas_age <= 7) & (full.tau_age <= 7)]
info.append(write(mid, "comparable_mid", "mid", "gas1", "tau1"))
tr = all_days[
    (all_days.date.dt.year <= 2020)
    & (all_days.mid_hours >= 20)
    & (all_days.gas_age <= 7)
    & (all_days.oil_age <= 7)
].dropna(subset=["mid", "gas1", "oil1"])
rows = []
for a, g in tr.groupby("masked_asset_id"):
    if len(g) < 200:
        continue
    rec = {
        "masked_asset_id": a,
        "training_days": len(g),
        "training_last_date": str(g.date.max().date()),
    }
    best = None
    for f, col, scale in [("gas", "gas1", 1), ("oil", "oil1", 1 / 0.139)]:
        x = g[col].to_numpy() * scale
        y = g.mid.to_numpy()
        X = np.column_stack([np.ones(len(g)), x])
        b = np.linalg.lstsq(X, y, rcond=None)[0]
        den = np.sum((y - y.mean()) ** 2)
        r2 = 1 - np.sum((y - X @ b) ** 2) / den if den > 0 else 0
        rec["hr_" + f] = b[1]
        rec["r2_" + f] = r2
        if 5 <= b[1] <= 20 and r2 >= 0.1 and (best is None or r2 > best[2]):
            best = (f, b[1], r2)
    rec.update(
        fuel_inferred=best[0] if best else "unclassified",
        hr=best[1] if best else np.nan,
        fit_r2=best[2] if best else np.nan,
    )
    rows.append(rec)
trained = pd.DataFrame(rows)
trained.to_csv(OUT / "exposure_trained_2019_2020.csv", index=False)
ev = all_days[
    (all_days.date.dt.year.between(2021, 2024))
    & (all_days.mid_hours >= 20)
    & (all_days.gas_age <= 7)
    & (all_days.tau_age <= 7)
].merge(
    trained.loc[trained.fuel_inferred == "gas", ["masked_asset_id", "hr", "fit_r2"]],
    on="masked_asset_id",
    validate="m:1",
)
info.append(write(ev, "prior_training_mid", "mid", "gas1", "tau1"))
auditout = {
    "archive_by_year": audit,
    "archive_records": sum(x["records"] for x in audit),
    "archive_assets": len(set.union(*ids.values())),
    "baseline_2020_full_year_overlap": {
        str(y): len(ids[2020] & ids[y]) / len(ids[2020]) for y in range(2021, 2027)
    },
    "legacy_gas_assets": len(legacy),
    "training_classifications": trained.fuel_inferred.value_counts().to_dict(),
    "samples": info,
}
(OUT / "data_audit.json").write_text(
    json.dumps(
        auditout,
        indent=2,
        default=lambda o: int(o) if isinstance(o, np.integer) else float(o),
    )
)
print(json.dumps(auditout, indent=2, default=float))
