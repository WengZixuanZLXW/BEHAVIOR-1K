#!/usr/bin/env python3
"""Register the locally imported V4 robots with this BEHAVIOR installation.

The official importer writes USD assets under the local
``omnigibson-robot-assets`` dataset.  OmniGibson additionally discovers a
robot through ``models/<model>/<model>.yaml``.  This installer creates those
small definition files from versioned templates in this repository.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "robot_definitions"
DEFAULT_DATASET = HERE.parents[2] / "vendor" / "BEHAVIOR-1K" / "datasets" / "omnigibson-robot-assets"
MODELS = ("v4_jackal", "v4_ridgeback_ur5", "v4_fanuc_crx10ial", "v4_crazyflie_cf2x")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(os.environ.get("OG_ROBOT_ASSET_DATASET", DEFAULT_DATASET)))
    parser.add_argument("--model", choices=MODELS + ("all",), default="all")
    args = parser.parse_args()
    selected = MODELS if args.model == "all" else (args.model,)

    for model in selected:
        usd = args.dataset / "objects" / "robot" / model / "usd" / f"{model}.usda"
        if not usd.is_file():
            raise FileNotFoundError(f"Missing imported USD for {model}: {usd}. Run import_official_v4_robots.sh first.")
        target = args.dataset / "models" / model / f"{model}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / f"{model}.yaml", target)
        print(f"V4_OG_ROBOT_REGISTERED={model}:{target}")


if __name__ == "__main__":
    main()
