"""Accounting and estimator checks using only generated, artificial records."""

from pathlib import Path
import ast
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(project, name):
    result = subprocess.run(
        [sys.executable, str(project / "python" / name)],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def workbook(frame):
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    return buffer.getvalue()


class LoanPanelTests(unittest.TestCase):
    def test_pipeline_accounts_for_shares_facilities_and_quarters(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "climate-credit"
            shutil.copytree(ROOT / "projects/climate-credit/python", project / "python")
            raw = project / "data/raw"
            raw.mkdir(parents=True)
            rows = []

            def loan(tranche, lender, parent, share, amount, start, end, firm, sic):
                rows.append(
                    {
                        "Lender_Parent_Name": parent,
                        "Lender_Parent_Operating_Country": (
                            "United Kingdom" if parent == "Bank B" else "United States"
                        ),
                        "Borrower_Name": firm,
                        "Country": "United States",
                        "SIC_Code": sic,
                        "Lender_Share": share,
                        "Tranche_Amount_Converted": amount,
                        "Tranche_Active_Date": start,
                        "Tranche_Maturity_Date": end,
                        "LPC_Deal_ID": tranche,
                        "LPC_Tranche_ID": tranche,
                        "Tranche_O_A": "Origination",
                        "Lender_Id": lender,
                    }
                )

            loan(
                "T1",
                "A1",
                "Bank A",
                20,
                100,
                "1999-10-01",
                "2000-06-30",
                "Firm 1",
                "4911",
            )
            loan(
                "T1",
                "A2",
                "Bank A",
                30,
                100,
                "1999-10-01",
                "2000-06-30",
                "Firm 1",
                "4911",
            )
            loan(
                "T1",
                "B1",
                "Bank B",
                50,
                100,
                "1999-10-01",
                "2000-06-30",
                "Firm 1",
                "4911",
            )
            loan(
                "T2",
                "A1",
                "Bank A",
                None,
                200,
                "2000-04-01",
                "2000-12-31",
                "Firm 1",
                "4911",
            )
            loan(
                "T2",
                "B1",
                "Bank B",
                40,
                200,
                "2000-04-01",
                "2000-12-31",
                "Firm 1",
                "4911",
            )
            # Resolve a duplicate lender record using its reported-share version.
            loan(
                "T3",
                "A1",
                "Bank A",
                None,
                90,
                "2001-01-01",
                "2001-03-31",
                "Firm 2",
                "4922",
            )
            loan(
                "T3",
                "A1",
                "Bank A",
                100,
                90,
                "2001-01-01",
                "2001-03-31",
                "Firm 2",
                "4922",
            )
            pd.DataFrame(rows).to_csv(raw / "dealscan_1996_2019.csv", index=False)
            emissions = project / "data/emissions"
            emissions.mkdir()
            for filename, code, region in [
                ("exio_US_report_average_2000_2015.csv", 491, False),
                ("exio_US_report_average_2000_2015_2digit_SIC.csv", 49, False),
                ("exio_EU_GB_report_average_2000_2015_3digit_SIC.csv", 491, True),
                ("exio_EU_GB_report_average_2000_2015_2digit_SIC.csv", 49, True),
            ]:
                row = {
                    "SIC Code": code,
                    "emission intensity": 2.0,
                    "emission category": "brown",
                    "direct_emissions_ton": 20.0,
                    "embodied_intensity_ton_per_$": 3.0,
                    "direct_emissions_per_value_added_ton_per_$": 1.0,
                    "gross_output": 100.0,
                    "value_added": 20.0,
                }
                if region:
                    row["region"] = "GBR"
                pd.DataFrame([row]).to_csv(emissions / filename, index=False)
            crosswalk = project / "data/crosswalk"
            crosswalk.mkdir()
            pd.DataFrame({"sic": [4911, 4922], "nace2_by_NAICS": [35, 35]}).to_excel(
                crosswalk / "sic_nace.xlsx", index=False
            )
            for stage in [
                "01_clean_loans.py",
                "02_match_emissions.py",
                "03_build_panel.py",
                "04_export_stata.py",
            ]:
                run_script(project, stage)
            loans = pd.read_parquet(project / "output/tranches.parquet")
            self.assertEqual(
                loans.groupby("LPC_Tranche_ID").amount.sum().to_dict(),
                {"T1": 100.0, "T2": 200.0, "T3": 90.0},
            )
            matched = pd.read_parquet(project / "output/tranches_emis.parquet")
            self.assertEqual(
                matched.loc[matched.borrower_name == "Firm 2", "emis_match"].iloc[0],
                "us_2digit",
            )
            panel = pd.read_parquet(project / "output/panel.parquet")
            q2 = panel[
                (panel.yq == "2000-04-01")
                & (panel.lender_parent_name == "Bank A")
                & (panel.borrower_name == "Firm 1")
            ].iloc[0]
            self.assertAlmostEqual(q2.outstand, 170.0)
            self.assertEqual(q2.n_out, 2)  # two subsidiaries on T1 still count once
            self.assertEqual(q2.n_new, 1)
            first = panel[
                (panel.yq == "2000-01-01") & (panel.borrower_name == "Firm 1")
            ]
            self.assertTrue((first.n_new == 0).all())
            after = panel[
                (panel.yq == "2001-01-01") & (panel.borrower_name == "Firm 1")
            ]
            self.assertTrue((after.outstand == 0).all())
            dta = project / "output/dealscan_exio_EU_USA_2000_2019.dta"
            exported = pd.read_stata(dta)
            pd.testing.assert_series_equal(exported.yq, panel.yq, check_names=False)
            self.assertIn("n_out", exported)
            numeric = pd.read_stata(dta, convert_dates=False)
            self.assertEqual(numeric.yq.min(), 160)  # 2000Q1, relative to 1960Q1


class ElectricityFinanceTests(unittest.TestCase):
    def test_event_conflicts_and_repeat_facilities(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "electricity-finance"
            shutil.copytree(
                ROOT / "projects/electricity-finance/python", project / "python"
            )
            (project / "data").mkdir()
            shutil.copy(
                ROOT
                / "projects/electricity-finance/data/borrower_classification_overrides.example.csv",
                project / "data/borrower_classification_overrides.example.csv",
            )
            tree = ast.parse((project / "python/profile_loans.py").read_text())
            columns = next(
                ast.literal_eval(node.value)
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "COLS" for t in node.targets
                )
            )
            record = dict.fromkeys(columns, "")
            record.update(
                Borrower_Name="Synthetic Power",
                Borrower_Id="SYNTH1",
                Country="United States",
                SIC_Code="4911",
                NAIC="2211",
                LPC_Deal_ID="D1",
                LPC_Tranche_ID="T1",
                Phase="Closed",
                Tranche_Active_Date="2024-01-01",
                Deal_Active_Date="2024-01-01",
                Deal_Input_Date="2024-01-01",
                Tranche_Type="Term loan",
                Tranche_Currency="U.S. Dollar",
                Project_Finance="Electric Power",
                Primary_Purpose="Project Finance",
                Tranche_Amount_Converted="100",
                League_Table_Amount_Converted="100",
                Deal_Amount_Converted="100",
                New_Money_Converted="50",
                State_Province="Synthetic state",
            )
            rows = [
                record,
                record.copy(),
                {**record, "Tranche_Amount_Converted": "120"},
                {
                    **record,
                    "Tranche_Active_Date": "2025-01-01",
                    "Tranche_Amount_Converted": "150",
                },
                {
                    **record,
                    "LPC_Tranche_ID": "T2",
                    "Tranche_Active_Date": "2026-01-01",
                    "Tranche_Amount_Converted": "50",
                },
            ]
            (project / "data/raw").mkdir(parents=True)
            pd.DataFrame(rows).to_csv(project / "data/raw/dealscan.csv", index=False)
            shutil.copy(
                project / "data/borrower_classification_overrides.example.csv",
                project / "data/borrower_classification_overrides.csv",
            )
            run_script(project, "profile_loans.py")
            run_script(project, "analyze_loans.py")
            annual = pd.read_csv(project / "output/annual_summary.csv")
            core = annual[annual["sample"] == "Core electricity"].set_index("year")
            self.assertEqual(core.loc[2024, "usd_millions"], 120)
            self.assertNotIn(2025, core.index)
            self.assertEqual(core.loc[2026, "period_status"], "Jan–Jun only")
            events = pd.read_csv(project / "output/electricity_facility_events.csv")
            self.assertEqual(len(events), 3)


class ElectricityTests(unittest.TestCase):
    def test_price_average_and_generation_units(self):
        module = load_module(
            "ercot_build", "projects/data-centers-electricity/python/build_panel.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.BASE = str(root)
            prices = root / "ercot/prices"
            wind = root / "ercot/wind_solar"
            prices.mkdir(parents=True)
            wind.mkdir(parents=True)
            frame = pd.DataFrame(
                {
                    "Settlement Point Name": ["HB_WEST"] * 5,
                    "Delivery Date": ["01/01/2023"] * 5,
                    "Delivery Hour": [1] * 5,
                    "Repeated Hour Flag": ["N"] * 4 + ["Y"],
                    "Settlement Point Price": [10, 20, 30, 40, 999],
                }
            )
            frame.to_excel(prices / "RTMLZHBSPP_2023.xlsx", index=False)
            self.assertEqual(module.load_prices().HB_WEST.iloc[0], 25)
            with pd.ExcelWriter(
                wind / "ERCOT_2023_Hourly_WindSolar_Output.xlsx"
            ) as writer:
                pd.DataFrame(
                    {
                        "Time (Hour-Ending)": [pd.Timestamp("2023-01-01 01:00")],
                        "ERCOT.WIND.GEN": [1000],
                    }
                ).to_excel(writer, sheet_name="Wind Data", index=False)
                pd.DataFrame(
                    {
                        "Time (Hour-Ending)": [pd.Timestamp("2023-01-01 01:00")],
                        "ERCOT.PVGR.GEN": [500],
                    }
                ).to_excel(writer, sheet_name="Solar Data", index=False)
            with zipfile.ZipFile(
                wind / "FuelMixReport_PreviousYears.zip", "w"
            ) as archive:
                for year in [2021, 2022]:
                    frame = pd.DataFrame(
                        {
                            "Date": [f"{year}-01-01"] * 2,
                            "Fuel": ["Wind", "Solar"],
                            **{
                                hour: [250.0, 125.0]
                                for hour in ["0:15", "0:30", "0:45", "1:00"]
                            },
                        }
                    )
                    archive.writestr(f"IntGenbyFuel{year}.xlsx", workbook(frame))
            generated = module.load_windsolar()
            self.assertEqual(generated.loc["2021-01-01 00:00", "wind_mw"], 1000)
            self.assertEqual(generated.loc["2021-01-01 00:00", "solar_mw"], 500)

    def test_regression_drops_all_incomplete_rows_before_clustering(self):
        module = load_module(
            "ercot_estimate",
            "projects/data-centers-electricity/python/estimate_spreads.py",
        )
        rng = np.random.default_rng(17)
        index = pd.date_range("2023-01-01", periods=3000, freq="h")
        data = pd.DataFrame(
            {
                column: rng.uniform(100, 2000, len(index))
                for column in module.MW_COLUMNS
            },
            index=index,
        )
        data["spread_wn"] = rng.normal(size=len(index))
        data.loc[index[0], "solar_mw"] = np.nan
        result = module.estimate(module.prepare(data))
        self.assertTrue((result.observations == len(data) - 1).all())
        self.assertTrue(np.isfinite(result.standard_error).all())


class WithinEstimatorTests(unittest.TestCase):
    def test_matches_explicit_fixed_effect_regression(self):
        module = load_module(
            "offer_verify", "projects/carbon-pass-through/python/verify_estimates.py"
        )
        rng = np.random.default_rng(46)
        unit = np.repeat(np.arange(5), 30)
        day = np.tile(np.arange(30), 5)
        keep = rng.random(len(unit)) > 0.2  # unbalanced panel
        unit, day = unit[keep], day[keep]
        x = rng.normal(size=(len(unit), 2))
        y = x @ [0.8, 1.3] + unit * 4 + day * 0.2 + rng.normal(size=len(unit))
        transformed, _ = module.residualize(np.column_stack([y, x]), [unit, day])
        actual = np.linalg.lstsq(transformed[:, 1:], transformed[:, 0], rcond=None)[0]
        dummies = pd.concat(
            [pd.get_dummies(unit), pd.get_dummies(day)], axis=1
        ).to_numpy(float)
        expected = np.linalg.lstsq(np.column_stack([x, dummies]), y, rcond=None)[0][:2]
        np.testing.assert_allclose(actual, expected, atol=1e-8)

    def test_unit_trends_and_two_way_effects_are_absorbed(self):
        module = load_module(
            "offer_verify_trends",
            "projects/carbon-pass-through/python/verify_estimates.py",
        )
        unit = np.repeat(np.arange(4), 40)
        day = np.tile(np.arange(40), 4)
        time = day.astype(float) - 19.5
        values = (unit * 8 + day * 0.3 + unit * time).reshape(-1, 1)
        residual, _ = module.residualize(values, [unit, day], (unit, time))
        np.testing.assert_allclose(residual, 0, atol=1e-8)


if __name__ == "__main__":
    unittest.main()
