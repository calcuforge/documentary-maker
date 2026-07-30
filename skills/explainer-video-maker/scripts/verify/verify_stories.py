#!/usr/bin/env python3
"""
Validate the chapter list (stories) in video_struct.yaml — Step 4 gate.

At this stage video_struct.yaml holds only the story skeleton (id + name);
the scene_list is designed later (Step 6), so it is NOT required here.

Checks:
- stories list is non-empty
- each story has a non-empty, globally unique id
- each story has a non-empty name

Usage:
    python verify_stories.py --video-struct /abs/path/video_struct.yaml

Exit codes: 0 = valid, 1 = errors found, 2 = warnings only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml


def validate(struct: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    stories = struct.get("stories", [])
    if not stories:
        errors.append("[stories] list is empty or missing")
        return errors, warnings

    story_ids = set()
    for si, story in enumerate(stories):
        prefix = f"stories[{si}]"
        story_id = story.get("id", "")

        if not story_id:
            errors.append(f"{prefix}: 'id' is required")
        elif story_id in story_ids:
            errors.append(f"{prefix}: duplicate story id '{story_id}'")
        story_ids.add(story_id)

        if not story.get("name"):
            warnings.append(f"{prefix}: 'name' is empty")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the chapter list in video_struct.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    struct = load_yaml(args.video_struct)
    errors, warnings = validate(struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"video_struct.yaml chapter list has {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"chapter list is valid with {len(warnings)} warning(s)",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "chapter list is valid",
            "data": {"stories": len(struct.get("stories", []))},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
