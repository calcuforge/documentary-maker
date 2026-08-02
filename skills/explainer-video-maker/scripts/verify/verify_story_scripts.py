#!/usr/bin/env python3
"""
Validate total narration script length — Step 5 gate.

Every story in video_struct.yaml must have a narration script file at
    {video_dir}/stories/{story_id}/script.md
The COMBINED character count (trimmed) across ALL chapter scripts must reach
content.min_story_chars × <number of chapters> (default 500 per chapter).
There is no per-chapter minimum.

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

    total_chars = 0
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

        total_chars += len(script_path.read_text(encoding="utf-8").strip())

    # Total length across ALL chapters: no per-chapter minimum.
    expected = min_chars * len(stories)
    if total_chars < expected:
        errors.append(
            f"Total narration is {total_chars} chars across {len(stories)} chapter(s), "
            f"below the {expected} minimum "
            f"(content.min_story_chars={min_chars} × {len(stories)} chapters)"
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

    story_count = len(struct.get("stories", []))
    expected_total = min_chars * story_count

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
            "msg": f"All chapter scripts meet the total {expected_total}-character minimum",
            "data": {"stories": story_count, "min_story_chars": min_chars, "expected_total": expected_total},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
