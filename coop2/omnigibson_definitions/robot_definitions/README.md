# Robot definitions

This folder contains the portable OmniGibson `RobotDefinition` YAML files for:

- `v4_jackal` — carrier / push base
- `v4_ridgeback_ur5` — mobile UR5 arm base
- `v4_crazyflie_cf2x` — kinematic drone base
- `v4_fanuc_crx10ial` — fixed checkpoint arm

The bundle intentionally does not include robot USD files.  They are large,
version-dependent binary assets and were the reason the earlier USDA package
was not portable.  Install/import the official robot source assets into the
local BEHAVIOR dataset, then copy these YAML definitions to that local dataset.
V4 suction cups, cargo plate, task scale, and action policies are task
semantics rather than silently embedded USD edits.
