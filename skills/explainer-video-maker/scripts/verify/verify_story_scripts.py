#!/usr/bin/env python3
"""
Validate per-chapter narration scripts — Step 5 gate.

Each story in video_struct.yaml must have a narration script file at
    {video_dir}/stories/{story_id}/script.md
whose character count (trimmed) meets the project's content.min_story_chars
(default 500).

Usage:
    python verify_story_scripts.py --video-struct /abs/path/video_struct.yaml \
                                   --project-config /abs/path/project_config.yaml

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

SCRIPT_FILENAME = "script.md"
DEFAULT_MIN_CHARS = 500


def validate(struct: dict, min_chars: int, video_dir: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    stories = struct.get("stories", [])
    if not stories:
        errors.append("[stories] list is empty or missing")
        return errors, warnings

    for si, story in enumerate(stories):
        story_id = story.get("id", "")
        prefix = f"stories[{si}] ({story_id or '?'})"

        if not story_id:
            errors.append(f"{prefix}: 'id' is required, cannot locate script file")
            continue

        script_path = video_dir / "stories" / story_id / SCRIPT_FILENAME
        if not script_path.exists():
            errors.append(f"{prefix}: script file not found: {script_path}")
            continue

        content = script_path.read_text(encoding="utf-8")
        char_count = len(content.strip())
        if char_count < min_chars:
            errors.append(
                f"{prefix}: script is {char_count} chars, below the minimum "
                f"{min_chars} (content.min_story_chars): {script_path}"
            )

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate per-chapter narration scripts")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct, args.project_config)

    struct = load_yaml(args.video_struct)
    project_config = load_yaml(args.project_config)
    min_chars = project_config.get("content", {}).get("min_story_chars", DEFAULT_MIN_CHARS)

    video_dir = Path(args.video_struct).parent
    errors, warnings = validate(struct, min_chars, video_dir)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"chapter scripts have {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings, "min_story_chars": min_chars},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"chapter scripts are valid with {len(warnings)} warning(s)",
            "data": {"warnings": warnings, "min_story_chars": min_chars},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"All chapter scripts meet the {min_chars}-character minimum",
            "data": {"stories": len(struct.get("stories", [])), "min_story_chars": min_chars},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
