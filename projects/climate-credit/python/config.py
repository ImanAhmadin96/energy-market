"""Paths and sample definitions for the loan-panel build."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "data/raw/dealscan_1996_2019.csv"
EXIO_DIR = ROOT / "data/emissions"
SIC_NACE = ROOT / "data/crosswalk/sic_nace.xlsx"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

# Earlier quarters use observed loan history from 1996 and remain left-censored.
# Changing the reporting start does not recover loans originated before 1996.
PANEL_START = 2000
PANEL_END = 2019
BURN_IN_FROM = 1996
# Keep reported shares and split the remainder among unreported lenders.
PARTIAL_RULE = "prorata"  # alternatively "drop"

EU28 = [
    "AUT",
    "BEL",
    "BGR",
    "HRV",
    "CYP",
    "CZE",
    "DNK",
    "EST",
    "FIN",
    "FRA",
    "DEU",
    "GRC",
    "HUN",
    "IRL",
    "ITA",
    "LVA",
    "LTU",
    "LUX",
    "MLT",
    "NLD",
    "POL",
    "PRT",
    "ROU",
    "SVK",
    "SVN",
    "ESP",
    "SWE",
    "GBR",
]
# Advanced economies kept on BOTH sides of the loan, matching the previous code.
AE = EU28 + ["NOR", "USA", "AUS", "CAN", "JPN", "NZL"]

# Government and public-administration SIC codes are excluded, as before.
GOV_SIC = (9100, 9729)

# Regions covered by the project-specific European emissions tables.
EXIO_EU_REGIONS = [
    "AUT",
    "BEL",
    "BGR",
    "CYP",
    "CZE",
    "DEU",
    "DNK",
    "ESP",
    "EST",
    "FIN",
    "FRA",
    "GBR",
    "GRC",
    "HRV",
    "HUN",
    "IRL",
    "ITA",
    "LTU",
    "LUX",
    "LVA",
    "MLT",
    "NLD",
    "POL",
    "PRT",
    "ROU",
    "SVK",
    "SVN",
    "SWE",
]

# 4. COUNTRY NAME -> ISO3
# Built from the exact spellings that appear in this file, matched exactly (not
# by substring) so that e.g. "Netherlands Antilles" is never read as NLD.
COUNTRY_ISO3 = {
    "United States": "USA",
    "United Kingdom": "GBR",
    "Canada": "CAN",
    "Japan": "JPN",
    "Australia": "AUS",
    "New Zealand": "NZL",
    "Austria": "AUT",
    "Belgium": "BEL",
    "Bulgaria": "BGR",
    "Croatia": "HRV",
    "Cyprus": "CYP",
    "Czech Republic": "CZE",
    "Denmark": "DNK",
    "Estonia": "EST",
    "Finland": "FIN",
    "France": "FRA",
    "Germany": "DEU",
    "Greece": "GRC",
    "Hungary": "HUN",
    "Ireland": "IRL",
    "Italy": "ITA",
    "Latvia": "LVA",
    "Lithuania": "LTU",
    "Luxembourg": "LUX",
    "Malta": "MLT",
    "Netherlands": "NLD",
    "Poland": "POL",
    "Portugal": "PRT",
    "Romania": "ROU",
    "Slovakia": "SVK",
    "Slovenia": "SVN",
    "Spain": "ESP",
    "Sweden": "SWE",
    "Norway": "NOR",
    "Switzerland": "CHE",
}

# 5. POLICY DATES (for the regressions that follow, not the build)
# EU ETS Phase I begins 2005Q1 for the EU-25; Bulgaria and Romania join 2007Q1.
ETS_START = {c: "2005Q1" for c in EXIO_EU_REGIONS}
ETS_START.update({"BGR": "2007Q1", "ROU": "2007Q1", "HRV": "2013Q1"})

RAW_COLS = [
    "Lender_Parent_Name",
    "Lender_Parent_Operating_Country",
    "Borrower_Name",
    "Country",
    "SIC_Code",
    "Lender_Share",
    "Tranche_Amount_Converted",
    "Tranche_Active_Date",
    "Tranche_Maturity_Date",
    "LPC_Deal_ID",
    "LPC_Tranche_ID",
    "Tranche_O_A",
    "Lender_Id",
]
