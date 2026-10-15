"""Run both Stata workflows on synthetic panels in a temporary directory."""

from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def make_fixture(project, rng):
    output = project / "output"
    output.mkdir(parents=True)
    if project.name == "climate-credit":
        lender, firm, quarter = np.meshgrid(
            np.arange(8), np.arange(15), np.arange(180, 200), indexing="ij"
        )
        lender, firm, quarter = lender.ravel(), firm.ravel(), quarter.ravel()
        data = pd.DataFrame(
            {
                "lender_parent_name": [f"Synthetic Bank {x}" for x in lender],
                "borrower_name": [f"Synthetic Firm {x}" for x in firm],
                "yq": quarter,
                "clpar": np.where(lender < 4, "USA", "GBR"),
                "sector": "b",
                "emissioncategory": np.array(["green", "gray", "brown"])[firm % 3],
                "outstand": np.where(
                    rng.random(len(quarter)) < 0.15,
                    0,
                    rng.lognormal(3, 0.5, len(quarter)),
                ),
            }
        )
        data.to_stata(
            output / "dealscan_exio_EU_USA_2000_2019.dta",
            write_index=False,
            version=118,
        )
        return "estimate_crisis.do"
    unit, day = np.meshgrid(np.arange(1, 9), np.arange(120), indexing="ij")
    unit, day = unit.ravel(), day.ravel()
    data = pd.DataFrame(
        {
            "uid": unit,
            "day": day,
            "trend": day / 365.25,
            "yearmonth": day // 30,
            "hr": 6 + unit * 0.2,
            "fuel": rng.normal(size=len(unit)),
            "carbon": rng.normal(size=len(unit)),
        }
    )
    data["y"] = (
        0.8 * data.fuel
        + 1.2 * data.carbon
        + unit
        + day * 0.1
        + rng.normal(size=len(data))
    )
    for sample in ["legacy_qw", "comparable_mid", "prior_training_mid"]:
        data.to_csv(output / f"{sample}.csv", index=False)
    return "estimate_offers.do"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stata", required=True, help="Path to a licensed Stata 19+ executable"
    )
    args = parser.parse_args()
    executable = shutil.which(args.stata)
    if not executable:
        raise FileNotFoundError(args.stata)
    with tempfile.TemporaryDirectory() as directory:
        rng = np.random.default_rng(91)
        for name in ["climate-credit", "carbon-pass-through"]:
            project = Path(directory) / name
            shutil.copytree(ROOT / "projects" / name / "stata", project / "stata")
            script = make_fixture(project, rng)
            (project / "check.do").write_text(
                f'do "stata/{script}"\n'
                'file open done using "complete.txt", write replace\n'
                'file write done "complete"\nfile close done\n'
            )
            process = subprocess.Popen(
                [executable, "-b", "do", "check.do"], cwd=project
            )
            deadline = time.monotonic() + 60
            while not (project / "complete.txt").exists():
                if time.monotonic() > deadline:
                    process.terminate()
                    raise RuntimeError(
                        f"{name}: Stata did not complete within 60 seconds"
                    )
                log = project / "check.log"
                if process.poll() is not None and log.exists():
                    # A failed do-file ends before the completion marker.
                    import re

                    if re.search(r"^r\(\d+\);", log.read_text(errors="replace"), re.M):
                        raise RuntimeError(f"{name}: Stata reported an error")
                time.sleep(0.1)
            process.wait(timeout=10)
            if name == "climate-credit":
                results = pd.read_csv(project / "output/crisis_results.csv")
                if len(results) != 6 or not np.isfinite(results.brown_se).all():
                    raise AssertionError("Expected six finite crisis model results")
            else:
                subprocess.run(
                    [
                        sys.executable,
                        str(
                            ROOT
                            / "projects/carbon-pass-through/python/verify_estimates.py"
                        ),
                        "--directory",
                        str(project / "output"),
                    ],
                    check=True,
                )
            print(f"{name}: synthetic Stata checks passed")


if __name__ == "__main__":
    main()
