#!/usr/bin/env python3
"""Launch one exported V4 scene using the official OmniGibson API.

The exported ``*.og_scene.json`` is a V4 wrapper, not an OmniGibson YAML
configuration.  This launcher extracts its ``omnigibson_environment_config``
and passes that dictionary directly to ``og.Environment(configs=...)``.

The V4 BDDL is registered locally with ``register_v4_behavior_activities.py``
and is loaded through the standard official ``BehaviorTask(activity_name=...)``
path.  ``--scene-only`` is available for inspecting a scene without sampling a
task.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[2]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "definition",
        nargs="?",
        type=Path,
        default=THIS_DIR / "generated" / "S1-V4-HH.og_scene.json",
        help="V4 exported JSON definition (default: S1-V4-HH)",
    )
    parser.add_argument("--headless", action="store_true", help="Load, step three frames, then exit.")
    parser.add_argument("--short-exec", action="store_true", help="GUI: close after 100 frames.")
    parser.add_argument(
        "--scene-only",
        action="store_true",
        help="Use DummyTask only; skip official BehaviorTask / BDDL sampling.",
    )
    parser.add_argument(
        "--with-base-robots",
        action="store_true",
        help="Instantiate the locally registered official-source robot bases from the V4 staging transforms.",
    )
    parser.add_argument(
        "--robot",
        action="append",
        default=[],
        help="Instantiate one named V4 staging robot; implies --with-base-robots and may be repeated.",
    )
    return parser.parse_args()


def load_v4_config(definition_path: Path, scene_only: bool) -> tuple[dict, dict]:
    definition_path = definition_path.resolve()
    with definition_path.open(encoding="utf-8") as stream:
        definition = json.load(stream)
    if definition.get("$schema") != "v4-omnigibson-scene-definition/v1":
        raise ValueError(f"Not a V4 OmniGibson definition: {definition_path}")

    config = copy.deepcopy(definition["omnigibson_environment_config"])
    if scene_only:
        config["task"] = {"type": "DummyTask"}
    config.setdefault("robots", [])
    config.setdefault("objects", [])
    return definition, config


def add_registered_base_robots(definition: dict, config: dict, requested_names: list[str]) -> list[str]:
    """Translate V4 staging transforms into safe OG base-robot load configs.

    This deliberately loads only registered upstream bases. V4-specific suction
    cups, cargo plates, scale edits and task policies are not silently claimed
    to exist in OmniGibson.
    """
    instances = definition.get("custom_robot_import", {}).get("instances_from_isaac_staging_scene", [])
    available = {item["name"] for item in instances}
    unknown = sorted(set(requested_names) - available)
    if unknown:
        raise ValueError(f"Unknown V4 staging robot(s): {unknown}. Available: {sorted(available)}")

    selected = [item for item in instances if not requested_names or item["name"] in requested_names]
    config["robots"] = []
    for item in selected:
        role = item["role"]
        config["robots"].append(
            {
                "name": item["name"],
                "model": item["omnigibson_base_model"],
                "position": item["position"],
                "orientation": item["orientation_wxyz"],
                "scale": item["scale"],
                # Fixed OG base for the stationary FANUC and visual / kinematic
                # Crazyflie. Mobile bases remain free.
                "fixed_base": role in {"checkpoint_arm", "drone"},
                "obs_modalities": [],
            }
        )
    return [item["name"] for item in selected]


def main():
    args = parse_args()
    definition, config = load_v4_config(args.definition, args.scene_only)
    loaded_robot_names: list[str] = []
    if args.with_base_robots or args.robot:
        loaded_robot_names = add_registered_base_robots(definition, config, args.robot)
    bddl_ref = definition["generated_from"].get("task_bddl_problem")
    bddl_path = (REPO_ROOT / bddl_ref).resolve() if bddl_ref else None
    if bddl_path and not bddl_path.is_file():
        raise FileNotFoundError(f"Referenced V4 BDDL is missing: {bddl_path}")

    # These must be set before importing / creating the environment.
    if args.headless:
        os.environ["OMNIGIBSON_HEADLESS"] = "1"

    import omnigibson as og
    from omnigibson.macros import gm
    from omnigibson.utils.bddl_utils import get_behavior_activities

    gm.ENABLE_OBJECT_STATES = True
    gm.HEADLESS = args.headless
    print(f"V4_OG_DEFINITION={args.definition.resolve()}", flush=True)
    print(f"V4_OG_SCENE={config['scene'].get('scene_model')}", flush=True)
    print(f"V4_OG_BDDL_METADATA={bddl_path}", flush=True)
    if args.scene_only:
        print("V4_OG_TASK_MODE=DummyTask (--scene-only)", flush=True)
    else:
        activity = config["task"]["activity_name"]
        if activity not in get_behavior_activities():
            raise RuntimeError(
                f"V4 activity '{activity}' is not registered in this BEHAVIOR installation. "
                "Run omnigibson_definitions/register_v4_behavior_activities.py in behavior51 first."
            )
        print(
            f"V4_OG_TASK_MODE=BehaviorTask activity={activity} definition="
            f"{config['task'].get('activity_definition_id', 0)} online_sampling=True",
            flush=True,
        )
    print(f"V4_OG_CUSTOM_ROBOTS={len(config['robots'])} names={loaded_robot_names}", flush=True)

    env = og.Environment(configs=config)
    try:
        if args.headless:
            for _ in range(3):
                env.step([])
            print("V4_OG_HEADLESS_LOAD_OK=True", flush=True)
            return

        import omnigibson.lazy as lazy
        from omnigibson.utils.ui_utils import KeyboardEventHandler

        og.sim.enable_viewer_camera_teleoperation()
        KeyboardEventHandler.initialize()
        KeyboardEventHandler.add_keyboard_callback(
            key=lazy.carb.input.KeyboardInput.ESCAPE,
            callback_fn=lambda: og.shutdown(),
        )
        print("V4_OG_GUI_READY=True (use mouse to inspect; press Esc or close the window to exit)", flush=True)
        max_steps = 100 if args.short_exec else -1
        steps = 0
        while steps != max_steps:
            env.step([])
            steps += 1
    finally:
        og.shutdown()


if __name__ == "__main__":
    main()
