# V4 robot import sources (local cache)

These source trees are inputs for the official BEHAVIOR / OmniGibson
`import_custom_robot` URDF importer. They are deliberately ignored by Git:
the FANUC visual/collision mesh source is approximately 614 MB. Re-clone them
locally when preparing a portable robot-import build.

| V4 role | Local folder | Source | Pinned clone revision | Import input |
| --- | --- | --- | --- | --- |
| Jackal carrier | `jackal/` | `https://github.com/jackal/jackal.git` | `4ddf9b5` | `jackal_description/urdf/jackal.urdf.xacro` |
| Ridgeback-UR5 movable arm | `ridgeback_manipulation/` | `https://github.com/ridgeback/ridgeback_manipulation.git` | `748d284` | `ridgeback_ur_description/urdf/ridgeback_ur5_description.urdf.xacro` plus its UR dependency |
| Ridgeback base dependency | `ridgeback_base/` | `https://github.com/ridgeback/ridgeback.git` | local clone | `ridgeback_description/urdf/ridgeback.urdf.xacro` |
| Legacy UR5 xacro dependency | `ur_description_ros1/` | `https://github.com/ros-industrial/universal_robot.git` (`melodic-devel`) | local clone | `ur_description/urdf/inc/ur5_macro.xacro` |
| Crazyflie | `crazyswarm2/` | `https://github.com/IMRCLab/crazyswarm2.git` | `fcf51e2` | `crazyflie_description/urdf/crazyflie_description.urdf` |
| FANUC CRX10iA/L | `fanuc_description/` | `https://github.com/FANUC-CORPORATION/fanuc_description.git` | `fb40c98` | `fanuc_crx_description/robot/crx10ia_l.urdf.xacro` |

Recreate the cache from repository root:

```bash
SRC=custom_task_suite/push_pull_arm_v4/omnigibson_definitions/robot_sources
git clone --depth 1 https://github.com/jackal/jackal.git "$SRC/jackal"
git clone --depth 1 --recurse-submodules https://github.com/ridgeback/ridgeback_manipulation.git "$SRC/ridgeback_manipulation"
git clone --depth 1 https://github.com/ridgeback/ridgeback.git "$SRC/ridgeback_base"
git clone --depth 1 --branch melodic-devel https://github.com/ros-industrial/universal_robot.git "$SRC/ur_description_ros1"
git clone --depth 1 https://github.com/IMRCLab/crazyswarm2.git "$SRC/crazyswarm2"
git clone --depth 1 https://github.com/FANUC-CORPORATION/fanuc_description.git "$SRC/fanuc_description"
```

## Import status

The local cache has been converted through BEHAVIOR's official
`import_custom_robot` workflow. The generated USD assets are installed in the
local `omnigibson-robot-assets` dataset; they are intentionally not committed.
The repeatable conversion is:

```bash
bash custom_task_suite/push_pull_arm_v4/omnigibson_definitions/import_official_v4_robots.sh all
python3 custom_task_suite/push_pull_arm_v4/omnigibson_definitions/install_v4_robot_definitions.py
```

The preparer resolves ROS xacro dependencies, changes only generated URDF
copies from `package://` mesh URIs to local paths, and removes duplicate legacy
ROS-control transmissions from Ridgeback's generated URDF. Upstream source
checkouts remain unchanged. Existing completed USD imports are skipped.

The import creates these OmniGibson model names:

- `v4_jackal` — wheel-joint locomotion definition.
- `v4_ridgeback_ur5` — wheel-joint base plus UR5 arm definition.
- `v4_fanuc_crx10ial` — six-axis fixed arm definition, no gripper yet.
- `v4_crazyflie_cf2x` — visual / kinematic drone asset; V4 controls its flight
  by pose updates rather than native rotor physics.

These are upstream robot geometry and joint graphs. They do **not** reproduce
the V4 suction cup, Jackal cargo plate, V4 scale changes, or V4 task actions;
those remain explicit V4 extensions to attach after loading the official base
robot.
