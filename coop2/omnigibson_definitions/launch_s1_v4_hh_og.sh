#!/usr/bin/env bash
# Official BEHAVIOR / OmniGibson 5.1 launcher for the V4 S1-HH scene.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

export OMNI_KIT_ACCEPT_EULA=YES
exec conda run --no-capture-output -n behavior51 python \
  "$SCRIPT_DIR/launch_v4_og_scene.py" \
  "$SCRIPT_DIR/generated/S1-V4-HH.og_scene.json" "$@"
