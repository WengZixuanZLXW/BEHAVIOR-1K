#!/usr/bin/env bash
# Run the official BEHAVIOR / OmniGibson URDF importer for prepared V4 inputs.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
NAME="${1:-all}"

python3 "$SCRIPT_DIR/prepare_official_robot_imports.py"
export OMNI_KIT_ACCEPT_EULA=YES

import_one() {
  local robot_name="$1"
  local usd_path="${REPO_ROOT}/vendor/BEHAVIOR-1K/datasets/omnigibson-robot-assets/objects/robot/${robot_name}/usd/${robot_name}.usda"
  if [[ -s "$usd_path" ]]; then
    echo "V4_OG_ROBOT_IMPORT_SKIPPED_ALREADY_PRESENT=${robot_name}:${usd_path}"
    return 0
  fi
  conda run --no-capture-output -n behavior51 python \
    -m omnigibson.examples.robots.import_custom_robot \
    --config "$SCRIPT_DIR/robot_import/import_configs/${robot_name}.yaml"
}

if [[ "$NAME" == "all" ]]; then
  for robot in v4_jackal v4_ridgeback_ur5 v4_crazyflie_cf2x v4_fanuc_crx10ial; do import_one "$robot"; done
else
  import_one "$NAME"
fi
