"""Summarize electricity-sector loan facilities and classification sensitivity.

Amounts are nominal USD millions. First-observed facilities need not be new credit."""

from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
u = pd.read_pickle(OUT / "us_versions.pkl")
KEY = ["LPC_Deal_ID", "LPC_Tranche_ID", "Tranche_Active_Date"]
NUM = [
    "Tranche_Amount_Converted",
    "League_Table_Amount_Converted",
    "New_Money_Converted",
    "Deal_Amount_Converted",
]
for col in NUM:
    u[col] = pd.to_numeric(u[col], errors="coerce").astype(float)
for col in ["Tranche_Active_Date", "Deal_Active_Date", "Deal_Input_Date"]:
    u[col] = pd.to_datetime(u[col], errors="coerce")
u["sic"] = u.SIC_Code.str.extract(r"^(\d+)")[0].fillna("")
u["naics"] = u.NAIC.str.extract(r"^(\d+)")[0].fillna("")
u["core"] = u.sic.isin(["4911", "4931"])
u["broad"] = u.sic.isin(["4911", "4931", "4939"])
u["strict"] = u.sic.eq("4911")
u["all_utilities"] = u.sic.str.startswith("49")
u["naics_electric"] = u.naics.str.startswith("2211")
# Transparent sensitivity screen, not a fully validated company classification.
# These flags intentionally err on excluding ambiguous projects from the supplier
# screen. Store the reason for every excluded record so it can be reviewed.
u["flag_data_center"] = u.Project_Finance.str.contains(
    "Data Center", case=False, na=False
) | u.Borrower_Name.str.contains(
    r"Data\s*Cent(?:er|re)|\bQTS\b|\bAbilene DC\b|\bRowan\b", case=False, na=False
)
u["flag_nonpower_project"] = u.Project_Finance.str.contains(
    "Pipelines|Gas/Oil|Telecommunications", case=False, na=False
) | u.Borrower_Name.str.contains(
    r"\bLNG\b|\bRGLNG\b|Afforestation", case=False, na=False
)
u["flag_equipment_or_fuel"] = u.Borrower_Name.str.contains(
    r"^Eaton Corp$|^GE Vernova|^Hanwha Q Cells|^Sprague Operating Resources|^Symmetry Energy Solutions",
    case=False,
    na=False,
)
u["screen_reason"] = [
    "; ".join(
        t
        for flag, t in [
            (a, "Data-center label/name or ambiguous related project"),
            (b, "Non-electric project label or LNG/afforestation name"),
            (c, "Equipment manufacturer or fuel supplier name"),
        ]
        if flag
    )
    for a, b, c in zip(
        u.flag_data_center, u.flag_nonpower_project, u.flag_equipment_or_fuel
    )
]
overrides = pd.read_csv(
    ROOT / "data/borrower_classification_overrides.csv", dtype={"Borrower_Id": "string"}
).set_index("Borrower_Id")
assert overrides.index.is_unique
if (
    not overrides.verified_power_entity.astype(str)
    .str.lower()
    .isin(["true", "false"])
    .all()
):
    raise ValueError("verified_power_entity must contain true or false")
verified = overrides.verified_power_entity.astype(str).str.lower().eq("true")
u["verified_power_entity"] = u.Borrower_Id.map(verified).eq(True)
u["classification_evidence"] = u.Borrower_Id.map(overrides.evidence)
u["classification_source"] = u.Borrower_Id.map(overrides.source_url)
# A name flag is not a verified exclusion: documented generation takes precedence.
u.loc[u.verified_power_entity, "screen_reason"] = ""
u["screened"] = u.core & u.screen_reason.eq("")
u["electric_project_screened"] = u.screened & u.Project_Finance.str.startswith(
    "Electric", na=False
)

# Retain an audit of conflicts. Same-date lender duplicates collapse to one event.
# If an event has conflicting numerical values, use the maximum nonmissing value,
# report the affected records, and also report lower-bound sensitivity.
conf = u.groupby(KEY, dropna=False)[NUM + ["Phase", "Borrower_Id", "SIC_Code"]].nunique(
    dropna=True
)
conf = conf[conf.gt(1).any(axis=1)]
conf.to_csv(OUT / "event_conflict_counts.csv")
if len(conf):
    u.merge(conf.reset_index()[KEY], on=KEY).sort_values(KEY).to_csv(
        OUT / "event_conflict_records.csv", index=False
    )
phase_rank = {"Closed": 4, "No Further Info": 3, "In Process": 2, "Cancelled": 1}
u["_phase_rank"] = u.Phase.map(phase_rank).fillna(0)
events = (
    u.sort_values(KEY + ["_phase_rank"], kind="stable")
    .drop_duplicates(KEY, keep="last")
    .copy()
)
maxes = u.groupby(KEY)[NUM].max().reset_index()
mins = (
    u.groupby(KEY)[NUM].min().reset_index().rename(columns={c: c + "_min" for c in NUM})
)
events = (
    events.drop(columns=NUM)
    .merge(maxes, on=KEY, validate="one_to_one")
    .merge(mins, on=KEY, validate="one_to_one")
)
events["year"] = events.Tranche_Active_Date.dt.year
events["quarter"] = events.Tranche_Active_Date.dt.to_period("Q").astype(str)
events["half"] = events.Tranche_Active_Date.dt.month.le(6)
events["facility_type"] = np.select(
    [
        events.Tranche_Type.str.contains("Revolver", case=False, na=False),
        events.Tranche_Type.str.contains("Letter of Credit", case=False, na=False),
        events.Tranche_Type.str.contains("Bridge", case=False, na=False),
        events.Tranche_Type.str.contains("Term", case=False, na=False),
    ],
    ["Revolver", "Letter of credit", "Bridge", "Term loan"],
    default="Other",
)
events["use_group"] = np.select(
    [
        events.Primary_Purpose.eq("Project Finance").fillna(False),
        events.Primary_Purpose.eq("Capital expenditure").fillna(False),
        events.Primary_Purpose.str.contains(
            "Acquisition|Buyout|Merger|Takeover", case=False, na=False
        ),
        events.Primary_Purpose.str.contains("Refinanc", case=False, na=False),
    ],
    [
        "Project finance",
        "Capital expenditure",
        "Acquisition / buyout",
        "Explicit refinancing",
    ],
    default="Other purposes",
)
events["first_observed"] = ~events.sort_values(
    KEY[:2] + ["Tranche_Active_Date"]
).duplicated(KEY[:2])
events["closed"] = events.Phase.eq("Closed")
first = events[events.first_observed & events.closed].copy()
closed = events[events.closed].copy()
assert not events.duplicated(KEY).any()
assert not first.duplicated(KEY[:2]).any()
assert events.Tranche_Active_Date.between("2019-01-01", "2026-06-30").all()
assert not (first.Tranche_Amount_Converted.dropna() < 0).any()
events[events.broad].sort_values(KEY).to_csv(
    OUT / "electricity_facility_events.csv", index=False
)
first[first.broad].sort_values(["year", "Borrower_Name"]).to_csv(
    OUT / "electricity_first_observed_facilities.csv", index=False
)


def summarise(df, group):
    z = df.groupby(group, dropna=False).agg(
        facilities=("LPC_Tranche_ID", "size"),
        deals=("LPC_Deal_ID", "nunique"),
        borrowers=("Borrower_Id", "nunique"),
        usd_millions=("Tranche_Amount_Converted", lambda x: x.sum(min_count=1)),
        amount_observed=("Tranche_Amount_Converted", "count"),
        median_usd_millions=("Tranche_Amount_Converted", "median"),
        mean_usd_millions=("Tranche_Amount_Converted", "mean"),
        league_usd_millions=(
            "League_Table_Amount_Converted",
            lambda x: x.sum(min_count=1),
        ),
        reported_new_money_usd_millions=(
            "New_Money_Converted",
            lambda x: x.sum(min_count=1),
        ),
        new_money_observed=("New_Money_Converted", "count"),
    )
    z["amount_missing"] = z.facilities - z.amount_observed
    z["amount_coverage_pct"] = 100 * z.amount_observed / z.facilities
    z["usd_billions"] = z.usd_millions / 1000
    z["period_status"] = [
        (
            "Jan–Jun only"
            if (
                int(str(v[0] if isinstance(v, tuple) else v)[0:4]) == 2026
                and group != "quarter"
            )
            else "Full quarter" if group == "quarter" else "Full year"
        )
        for v in z.index
    ]
    return z


annual = []
quarterly = []
h1 = []
for name, mask in [
    ("Core electricity", first.core),
    ("Screened electricity", first.screened),
    ("Screened explicitly electric projects", first.electric_project_screened),
    ("Electric only SIC 4911", first.strict),
    ("Expanded electricity SIC 4911 4931 4939", first.broad),
    ("All utilities SIC 49", first.all_utilities),
    ("NAICS electric power 2211", first.naics_electric),
    ("Other US sectors", ~first.core),
    ("All US sectors", pd.Series(True, index=first.index)),
]:
    d = first[mask]
    for holder, group, sub in [
        (annual, "year", d),
        (quarterly, "quarter", d),
        (h1, "year", d[d.half]),
    ]:
        s = summarise(sub, group).reset_index()
        s.insert(0, "sample", name)
        if holder is h1:
            s["period_status"] = "Jan–Jun only"
        holder.append(s)
annual = pd.concat(annual, ignore_index=True)
quarterly = pd.concat(quarterly, ignore_index=True)
h1 = pd.concat(h1, ignore_index=True)
annual.to_csv(OUT / "annual_summary.csv", index=False)
quarterly.to_csv(OUT / "quarterly_summary.csv", index=False)
h1.to_csv(OUT / "first_half_summary.csv", index=False)
core = first[first.core].copy()
screened = core[core.screened].copy()
core[~core.screened].to_csv(OUT / "classification_review_exclusions.csv", index=False)
full = core[core.year.le(2025)]
segments = []
for samplename, sampleframe in [
    ("Core electricity", core),
    ("Screened electricity", screened),
]:
    for field in [
        "facility_type",
        "use_group",
        "SIC_Code",
        "Project_Finance",
        "State_Province",
    ]:
        s = summarise(sampleframe, ["year", field]).reset_index()
        s["dimension"] = field
        s["sample"] = samplename
        s = s.rename(columns={field: "category"})
        segments.append(s)
pd.concat(segments, ignore_index=True).to_csv(OUT / "sector_breakdown.csv", index=False)
top = (
    core.groupby(["year", "Borrower_Id", "Borrower_Name"], dropna=False)
    .agg(
        facilities=("LPC_Tranche_ID", "size"),
        usd_millions=("Tranche_Amount_Converted", lambda x: x.sum(min_count=1)),
    )
    .reset_index()
    .sort_values(["year", "usd_millions"], ascending=[True, False])
)
top.to_csv(OUT / "borrower_year_amounts.csv", index=False)

rob = []
for name, d in [
    ("Main: first observed, closed", core),
    ("Screened electricity", screened),
    (
        "Screened electricity, excluding letters of credit",
        screened[screened.facility_type.ne("Letter of credit")],
    ),
    (
        "Screened electricity, project finance",
        screened[screened.use_group.eq("Project finance")],
    ),
    (
        "Screened electricity, other than project finance",
        screened[screened.use_group.ne("Project finance")],
    ),
    (
        "First observed, excluding cancelled/on-hold/hung/pre-mandate",
        events[
            events.core
            & events.first_observed
            & ~events.Phase.isin(["Cancelled", "On-Hold", "Hung", "Pre-Mandate"])
        ],
    ),
    ("All dated events, closed (includes repeat facilities)", closed[closed.core]),
    (
        "Positive league amount events, closed",
        closed[closed.core & closed.League_Table_Amount_Converted.gt(0)],
    ),
    (
        "First observed, closed, exclude letters of credit",
        core[core.facility_type.ne("Letter of credit")],
    ),
    (
        "First observed, closed, project finance",
        core[core.use_group.eq("Project finance")],
    ),
    (
        "First observed, closed, other than project finance",
        core[core.use_group.ne("Project finance")],
    ),
]:
    s = summarise(d, "year").reset_index()
    s.insert(0, "definition", name)
    rob.append(s)
pd.concat(rob, ignore_index=True).to_csv(
    OUT / "measurement_sensitivity.csv", index=False
)
quality = {
    "us_unique_dated_events": len(events),
    "us_first_observed_closed": len(first),
    "core_first_observed_closed": len(core),
    "core_unique_borrowers": int(core.Borrower_Id.nunique()),
    "core_unique_deals": int(core.LPC_Deal_ID.nunique()),
    "event_conflicts_all_us": len(conf),
    "event_conflicts_core": int(
        events[events.core].merge(conf.reset_index()[KEY], on=KEY).shape[0]
    ),
    "core_missing_amounts": int(core.Tranche_Amount_Converted.isna().sum()),
    "core_missing_refinancing_flag_pct": float(
        100 * core.Tranche_Refinancing.isna().mean()
    ),
    "core_missing_state_pct": float(100 * core.State_Province.isna().mean()),
    "core_missing_naics_pct": float(100 * core.NAIC.isna().mean()),
    "core_non_usd_facilities": int(
        (~core.Tranche_Currency.isin(["U.S. Dollar", "US Dollar"])).sum()
    ),
    "core_first_date_after_deal_date": int(
        core.Tranche_Active_Date.gt(core.Deal_Active_Date).sum()
    ),
    "core_phase_first_observed": events[events.core & events.first_observed]
    .Phase.value_counts(dropna=False)
    .to_dict(),
    "core_top5_borrower_share_by_year": {
        str(y): float(d.head(5).usd_millions.sum() / d.usd_millions.sum())
        for y, d in top.groupby("year")
    },
    "comparison_amount_conflict_spread_usd_millions": float(
        (first.Tranche_Amount_Converted - first.Tranche_Amount_Converted_min).sum()
    ),
    "core_new_money_nonmissing_pct": float(
        100 * core.New_Money_Converted.notna().mean()
    ),
    "screened_facilities": len(screened),
    "screened_borrowers": int(screened.Borrower_Id.nunique()),
    "screen_excluded_facilities": len(core) - len(screened),
    "screen_excluded_borrowers": int(core[~core.screened].Borrower_Id.nunique()),
}
(OUT / "quality_audit.json").write_text(json.dumps(quality, indent=2, default=str))
print(
    "\nANNUAL CORE\n",
    annual[annual["sample"].eq("Core electricity")].to_string(index=False),
)
print("\nH1 CORE\n", h1[h1["sample"].eq("Core electricity")].to_string(index=False))
print(
    "\nSENSITIVITY\n",
    pd.concat(rob)
    .pivot(index="year", columns="definition", values="usd_billions")
    .round(2)
    .to_string(),
)
print("\nQUALITY\n", json.dumps(quality, indent=2, default=str))
print("\nTOP 2025\n", top[top.year.eq(2025)].head(12).to_string(index=False))
