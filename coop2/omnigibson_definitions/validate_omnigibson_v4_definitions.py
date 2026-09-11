#!/usr/bin/env python3
"""Validate generated V4 OmniGibson scene definitions without Isaac Sim."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GENERATED = HERE / "generated"


def main() -> int:
    files = sorted(GENERATED.glob("S*-V4-*.og_scene.json"))
    errors: list[str] = []
    if len(files) != 12:
        errors.append(f"expected 12 task files, found {len(files)}")
    for path in files:
        data = json.loads(path.read_text())
        env = data["omnigibson_environment_config"]
        if env["scene"]["type"] != "InteractiveTraversableScene":
            errors.append(f"{path.name}: scene type is not InteractiveTraversableScene")
        if env["robots"]:
            errors.append(f"{path.name}: native robots must remain empty until custom definitions are registered")
        source = data["generated_from"]
        for key in ("task_design", "behavior_scene_state", "behavior_bddl_binding", "task_bddl_problem", "isaac_staging_scene"):
            if not (REPO / source[key]).exists():
                errors.append(f"{path.name}: missing {key}: {source[key]}")
        if not data["v4_task_semantics"]["routes"]:
            errors.append(f"{path.name}: no V4 routes")
    if errors:
        print("V4_OG_DEFINITION_VALID=False")
        print("\n".join(errors))
        return 1
    print(f"V4_OG_DEFINITION_VALID=True files={len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
