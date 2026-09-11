#!/usr/bin/env python3
"""Register the twelve V4 BDDL problems as local official BEHAVIOR activities.

Run this script inside the ``behavior51`` environment.  BEHAVIOR discovers an
activity by finding ``activity_definitions/<activity>/problem0.bddl`` in the
installed :mod:`bddl` package.  The source V4 files remain the repository
source of truth; this tool writes a small BEHAVIOR-compatible copy with only
the problem / domain identifiers adapted for the official ``behavior-1k``
domain.

Registration is local to a BEHAVIOR installation.  Re-run after creating a
new environment or updating / reinstalling the BDDL package.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import bddl.config
from bddl.activity import Conditions, get_all_activities


HERE = Path(__file__).resolve().parent
V4_ROOT = HERE.parent
BDDL_SOURCE = V4_ROOT / "bddl"
MANIFEST = HERE / "behavior_activity_manifest.json"


def activity_name(source: Path) -> str:
    """Return a stable, valid local BEHAVIOR activity name for one V4 task."""
    return "v4_" + source.stem.lower().replace("-", "_")


def behavior_problem_text(source: Path, activity: str) -> str:
    """Adapt only identifiers required by the official BEHAVIOR registry."""
    text = source.read_text(encoding="utf-8")
    text, n_problem = re.subn(
        r"\(define\s+\(problem\s+[^)]+\)",
        f"(define (problem {activity}-0)",
        text,
        count=1,
    )
    text, n_domain = re.subn(r"\(:domain\s+[^)]+\)", "(:domain behavior-1k)", text, count=1)
    # ``floor.n.01_target_1`` was a useful V4 symbolic marker but it is not a
    # legal BDDL instance: the final underscore segment is interpreted as the
    # instance number, leaving the invalid synset ``floor.n.01_target``.  Keep
    # the source BDDL untouched and give every virtual target a non-conflicting
    # regular floor instance number in the registered BEHAVIOR copy.
    text = re.sub(
        r"floor\.n\.01_target_(\d+)",
        lambda match: f"floor.n.01_{50 + int(match.group(1))}",
        text,
    )
    # The BEHAVIOR taxonomy has no ``ottoman.n.01`` synset.  The staged OG
    # object retains its original runtime name; at BDDL level the compatible
    # official support-surface synset is ``stool.n.01``.
    text = text.replace("ottoman.n.01", "stool.n.01")
    # BehaviorTask always adds its first OG robot to the scope as
    # ``agent.n.01_1``.  The V4 BDDL originally described task objects only,
    # so declare that standard BEHAVIOR agent explicitly to keep its scope and
    # parsed BDDL object table consistent.
    text, n_agent = re.subn(
        r"\(:objects\s*\n",
        "(:objects\n  agent.n.01_1 - agent.n.01\n",
        text,
        count=1,
    )
    if n_agent != 1:
        raise ValueError(f"{source} has no :objects declaration")
    if n_problem != 1 or n_domain != 1:
        raise ValueError(f"{source} is not a supported BDDL problem definition")
    return text


def register(source: Path, root: Path) -> dict[str, str]:
    activity = activity_name(source)
    target_dir = root / activity
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "problem0.bddl"
    target.write_text(behavior_problem_text(source, activity), encoding="utf-8")
    # Parse through the same BDDL loader BEHAVIOR uses before declaring success.
    conditions = Conditions(activity, 0, "behavior-1k")
    return {
        "activity_name": activity,
        "activity_definition_id": "0",
        "source_bddl": str(source),
        "registered_problem": str(target),
        "object_synsets": ",".join(sorted(conditions.parsed_objects)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activity-root",
        type=Path,
        default=Path(bddl.config.ACTIVITY_CONFIGS_PATH),
        help="Override BDDL activity_definitions root (default: installed BDDL package).",
    )
    parser.add_argument("--verify-only", action="store_true", help="Do not write; verify registered V4 activities.")
    args = parser.parse_args()

    sources = sorted(BDDL_SOURCE.glob("S*-V4-*.bddl"))
    if len(sources) != 12:
        raise RuntimeError(f"Expected 12 V4 BDDL files under {BDDL_SOURCE}, found {len(sources)}")
    root = args.activity_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"BDDL activity root does not exist: {root}")

    rows: list[dict[str, str]] = []
    for source in sources:
        name = activity_name(source)
        if args.verify_only:
            Conditions(name, 0, "behavior-1k")
            row = {
                "activity_name": name,
                "activity_definition_id": "0",
                "source_bddl": str(source),
                "registered_problem": str(root / name / "problem0.bddl"),
            }
        else:
            row = register(source, root)
        rows.append(row)
        print(f"V4_BEHAVIOR_ACTIVITY_OK={name} problem0.bddl", flush=True)

    visible = set(get_all_activities())
    missing = [row["activity_name"] for row in rows if row["activity_name"] not in visible]
    if missing:
        raise RuntimeError(f"Registered activities are not discoverable: {missing}")
    if not args.verify_only:
        MANIFEST.write_text(
            json.dumps(
                {
                    "schema": "v4-behavior-activity-registration/v1",
                    "bddl_activity_root": str(root),
                    "activities": rows,
                    "note": "Generated BDDL copies are local installation state; re-run this script after updating BEHAVIOR/BDDL.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"V4_BEHAVIOR_ACTIVITY_REGISTRY_OK=True count={len(rows)} root={root}", flush=True)


if __name__ == "__main__":
    main()
