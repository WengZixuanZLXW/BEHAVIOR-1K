# V4 OmniGibson scene definitions

This directory exports the twelve V4 tasks into portable JSON definitions.
They preserve the relationship between the BEHAVIOR/OmniGibson scene, the
task BDDL problem, BDDL runtime bindings, V4 package flow, checkpoints,
destinations, markers, and the robot instances authored in the matching Isaac
staging scene. Scene-state references resolve against the new
`vendor/BEHAVIOR-1K/datasets/behavior-1k-assets` installation; the prior
`COHERENT/OmniGibson/...` location is retained only as historical provenance.

Generate and validate them from the repository root:

```bash
python3 custom_task_suite/push_pull_arm_v4/omnigibson_definitions/generate_omnigibson_v4_definitions.py
python3 custom_task_suite/push_pull_arm_v4/omnigibson_definitions/validate_omnigibson_v4_definitions.py
```

## Register the V4 BDDL as official local BEHAVIOR activities

This is now implemented.  Run it once for each local BEHAVIOR / BDDL
installation (and again after reinstalling or updating BEHAVIOR):

```bash
OMNI_KIT_ACCEPT_EULA=YES conda run --no-capture-output -n behavior51 python \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/register_v4_behavior_activities.py
```

It registers twelve official local activities, one per V4 task.  For example,
`S1-V4-LL` becomes `v4_s1_v4_ll` definition `0`; it is then discovered by the
standard `get_behavior_activities()` and loaded by
`BehaviorTask(activity_name="v4_s1_v4_ll", activity_definition_id=0)`.
The source V4 BDDL files remain unchanged.  The generated, BEHAVIOR-compatible
`problem0.bddl` copies live under the active BDDL package's
`activity_definitions/`; the local registration manifest is
[`behavior_activity_manifest.json`](behavior_activity_manifest.json).

The registry copy normalizes two BEHAVIOR taxonomy constraints only:

- V4's symbolic `floor.n.01_target_N` becomes a legal, separate
  `floor.n.01_5N` BDDL instance.
- `ottoman.n.01` is represented as BEHAVIOR's supported `stool.n.01` synset.

Verify without rewriting the registered files:

```bash
OMNI_KIT_ACCEPT_EULA=YES conda run --no-capture-output -n behavior51 python \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/register_v4_behavior_activities.py \
  --verify-only
```

The output is in `generated/`:

- `S{1,2,3}-V4-{LL,LH,HL,HH}.og_scene.json` — one definition per task.
- `index.json` — the twelve-task index.

## Launch S1-V4-HH with the official BEHAVIOR / OmniGibson installation

Use the supplied launcher from the repository root:

```bash
bash custom_task_suite/push_pull_arm_v4/omnigibson_definitions/launch_s1_v4_hh_og.sh
```

Append `--with-base-robots` (or `--robot <staging-name>`) after registering
the local robot assets to include the official robot bases.

It uses the official `behavior51` environment (BEHAVIOR-1K v3.9.2 / Isaac Sim
5.1.0) and the standard OmniGibson call
`og.Environment(configs=<dict>)`. After registration it loads the official
`BehaviorTask` for this V4 BDDL activity, rather than a scene-only dummy task.
It opens the real `Merom_1_int` OG scene behind `S1-V4-HH`; press `Esc` or
close Isaac Sim when finished. A quick non-GUI verification is available with:

```bash
bash custom_task_suite/push_pull_arm_v4/omnigibson_definitions/launch_s1_v4_hh_og.sh --headless
```

To open another V4 definition, call the Python launcher with its JSON file:

```bash
OMNI_KIT_ACCEPT_EULA=YES conda run --no-capture-output -n behavior51 python \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/launch_v4_og_scene.py \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/generated/S2-V4-LL.og_scene.json
```

To inspect a registered robot base at its V4 staging transform, add
`--with-base-robots`. Use `--robot` to limit the load while testing:

```bash
OMNI_KIT_ACCEPT_EULA=YES conda run --no-capture-output -n behavior51 python \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/launch_v4_og_scene.py \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/generated/S1-V4-HH.og_scene.json \
  --with-base-robots --robot jackal_s1_m5
```

This loader instantiates the registered official base model at the authored
V4 transform. It intentionally does not claim that V4-only suction, cargo
plates, scale edits, or action policies are present.

Important: the outer `*.og_scene.json` is V4 metadata plus an embedded OG
config, so it cannot be passed directly to `og.Environment` as a filename.
The official `BehaviorTask` accepts a registered BEHAVIOR `activity_name` /
definition ID rather than an arbitrary BDDL filename; the registration command
above performs that bridge. Add `--scene-only` to the launcher only when you
explicitly want a `DummyTask` scene inspection.

Do **not** use `python -m omnigibson.examples.environments.behavior_env_demo
--config_filename ...` here.  In BEHAVIOR-1K v3.9.2 that demo does not accept
or consume `--config_filename`; it always runs its bundled
`r1pro_behavior.yaml`.  The V4 launcher above uses the same official
`og.Environment(configs=...)` API, but passes the correct registered V4 task
and scene configuration.

## What is directly loadable

`omnigibson_environment_config` is an OmniGibson-style environment config.
It loads the original OG scene (`Merom_1_int`, `Beechwood_0_int`, or
`Beechwood_1_int`) and names the exact BDDL problem under
`task.predefined_problem`. The original BEHAVIOR scene-state JSON and the V4
BDDL binding are recorded under `generated_from` so that the object instances
remain traceable.

## Custom robot boundary

The checked official [OmniGibson robot/import documentation](https://behavior.stanford.edu/omnigibson/robots.html#importing)
uses the newer data-driven custom robot workflow: a robot USD plus a
`RobotDefinition` YAML registered in the OmniGibson dataset. The local
`behavior51` environment now uses BEHAVIOR-1K v3.9.2 and Isaac Sim 5.1.0, so it
supports this workflow.

The four official-source bases have now been imported and registered locally:

| V4 role | OmniGibson model | Imported capability | Not part of upstream import |
| --- | --- | --- | --- |
| carrier car | `v4_jackal` | four wheel joints / locomotion | cargo plate, V4 task policy |
| movable arm | `v4_ridgeback_ur5` | wheel joints + UR5 arm | suction cup, V4 base-lock policy |
| fixed arm | `v4_fanuc_crx10ial` | six FANUC joints | suction cup / gripper |
| drone | `v4_crazyflie_cf2x` | visual, kinematic asset | rotor physics and suction cup |

Recreate the local installation after cloning the repository or installing a
new BEHAVIOR environment:

```bash
bash custom_task_suite/push_pull_arm_v4/omnigibson_definitions/import_official_v4_robots.sh all
python3 custom_task_suite/push_pull_arm_v4/omnigibson_definitions/install_v4_robot_definitions.py
OMNI_KIT_ACCEPT_EULA=YES conda run --no-capture-output -n behavior51 python \
  custom_task_suite/push_pull_arm_v4/omnigibson_definitions/verify_v4_robot_definitions.py
```

The versioned templates are in `robot_definitions/`; the generated USD assets
and large source clones are deliberately local and ignored by Git. The importer
never edits upstream robot checkouts: it resolves copies of the URDF/xacro
inputs under `robot_import/`.

The exported task JSON still leaves `omnigibson_environment_config.robots`
empty intentionally. It records exact V4 roles, transforms and V4-only
extensions in `custom_robot_import.instances_from_isaac_staging_scene`, rather
than silently replacing the task design with default OG robots. Once the V4
suction cups / cargo plate are authored as OG extensions, use the registered
model names above to populate that list.

The URDF / xacro source cache needed for this official importer is documented
in [`robot_sources/README.md`](robot_sources/README.md). Its large source
trees remain local and are intentionally excluded from Git.

The JSON is already the task/scene source of truth; the remaining work is the
one-time robot import layer, not manual re-authoring of twelve tasks.

`role_coverage` is included in every export. It exposes any difference between
the robot roles required by the task packages and the physical robots actually
authored in its Isaac staging USDA. In particular, do not silently treat a
standard Jackal visual as the designed pull-car suction robot: register the
pull-car USD separately when that role is required.

## Mass contract

All twelve source tasks use the same mass contract: LL/HL boxes are `0.008 kg`
(8 g), while LH/HH boxes are `0.020 kg` (20 g). The exporter copies this value
unchanged from `tasks.modified.json` into each generated definition.
