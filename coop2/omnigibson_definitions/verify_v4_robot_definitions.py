#!/usr/bin/env python3
"""Verify that V4 official-source robot imports are discoverable by OmniGibson.

This is intentionally a fast schema / path check. It does not open a scene or
claim that the V4-only suction, cargo plate, or task actions are installed.
"""
from __future__ import annotations


MODELS = ("v4_jackal", "v4_ridgeback_ur5", "v4_fanuc_crx10ial", "v4_crazyflie_cf2x")


def main() -> None:
    from omnigibson.robots import REGISTERED_ROBOTS
    from omnigibson.robots.robot import Robot

    for model in MODELS:
        if model not in REGISTERED_ROBOTS:
            raise RuntimeError(f"{model} is not registered; run install_v4_robot_definitions.py")
        robot = Robot(name=f"verify_{model}", model=model)
        if not robot.usd_path or not __import__("pathlib").Path(robot.usd_path).is_file():
            raise RuntimeError(f"{model} has no readable imported USD: {robot.usd_path}")
        print(
            f"V4_OG_ROBOT_DEFINITION_OK={model} "
            f"locomotion={robot.is_locomotion} manipulation={robot.is_manipulation}"
        )


if __name__ == "__main__":
    main()
