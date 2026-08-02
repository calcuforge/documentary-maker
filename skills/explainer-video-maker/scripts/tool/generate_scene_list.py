#!/usr/bin/env python3
"""
Generate the section_list (narration skeleton) in video_struct.yaml from each
chapter's script.md, which is written one narration per line (Step 5).

For every story in video_struct.yaml, reads stories/{story_id}/script.md and
turns each non-empty line into one SECTION carrying that line as its narration
(1 line = 1 narration = 1 section). Each section starts with a single default
scene (percentage: 100); the agent splits it into 1-N scenes and adjusts the
percentages (sum = 100 per narration) in Step 6. Scene display fields — intent,
remotion_component, is_aigc_scene, type, data, text, visual_content, workflows —
are left empty/default for the agent to fill.

Stories that already have a non-empty section_list are skipped unless --force is
given, so the tool is safe to re-run and works story-by-story.

Usage:
    python generate_scene_list.py --video-struct /abs/path/video_struct.yaml [--force]

Exit codes: 0 = ok, 1 = errors found, 2 = warnings only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml

SCRIPT_FILENAME = "script.md"


def parse_script_lines(script_path: Path) -> list[str]:
    """Return the narration lines from a script.md (one narration per line).

    Blank/whitespace-only lines are skipped. Every other line is a narration.
    """
    lines = []
    for raw in script_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    return lines


def id_generator(existing_ids: set[str], prefix: str):
    """Yield unused ids prefix1, prefix2, ... continuing past any existing ones."""
    nums = []
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for eid in existing_ids:
        m = pattern.match(eid or "")
        if m:
            nums.append(int(m.group(1)))
    n = (max(nums) + 1) if nums else 1
    while True:
        yield f"{prefix}{n}"
        n += 1


def build_default_scene(scene_id: str) -> dict:
    """Build a single default scene (percentage 100) — agent splits in Step 6."""
    return {
        "intent": "",  # agent fills (Step 6)
        "id": scene_id,
        "data": "",  # agent fills (Step 6)
        "text": "",  # agent fills (Step 6)
        "visual_content": "",  # agent fills (Step 6, AIGC scenes)
        "is_aigc_scene": False,  # agent decides (Step 6)
        "asset_generation_method": "none",
        "type": "none",  # agent decides (Step 6)
        "remotion_component": "",  # agent fills (Step 6)
        "origin_asset_path": "",
        "asset_path": "",
        "workflows": [],
        "percentage": 100,  # split by agent (Step 6); Σ per narration = 100
    }


def build_section(narration_id: str, content: str, scene_id: str) -> dict:
    """Build a section: one narration + a single default scene."""
    return {
        "narration": {
            "id": narration_id,
            "content": content,
            "total_frame": 0,  # auto-filled in Step 7 (TTS)
            "audio_path": "",  # auto-filled in Step 7 (TTS)
        },
        "scene_list": [build_default_scene(scene_id)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate section_list narration skeleton from per-chapter script.md"
    )
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate section_list even for stories that already have one")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    struct = load_yaml(args.video_struct)
    video_dir = Path(args.video_struct).parent
    stories = struct.get("stories", [])
    if not stories:
        print(json.dumps({
            "status": "error",
            "msg": "[stories] list is empty or missing — run Step 4 (design chapter list) first",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Collect existing ids so new ones stay globally unique.
    existing_scene_ids: set[str] = set()
    existing_narration_ids: set[str] = set()
    for story in stories:
        for section in story.get("section_list") or []:
            existing_narration_ids.add((section.get("narration") or {}).get("id", ""))
            for scene in section.get("scene_list") or []:
                existing_scene_ids.add(scene.get("id", ""))

    scene_ids = id_generator(existing_scene_ids, "scene")
    narration_ids = id_generator(existing_narration_ids, "narration")

    errors: list[str] = []
    warnings: list[str] = []
    generated_stories = 0
    generated_scenes = 0
    skipped_stories = 0

    for si, story in enumerate(stories):
        story_id = story.get("id", "")
        prefix = f"stories[{si}] ({story_id or '?'})"

        if not story_id:
            errors.append(f"{prefix}: missing story id, cannot locate script.md")
            continue

        if (story.get("section_list") or []) and not args.force:
            skipped_stories += 1
            continue

        script_path = video_dir / "stories" / story_id / SCRIPT_FILENAME
        if not script_path.exists():
            errors.append(f"{prefix}: script file not found: {script_path}")
            continue

        lines = parse_script_lines(script_path)
        if not lines:
            errors.append(f"{prefix}: no narration lines in {script_path}")
            continue

        sections = []
        for line in lines:
            sections.append(build_section(next(narration_ids), line, next(scene_ids)))

        story["section_list"] = sections
        generated_stories += 1
        generated_scenes += len(sections)

    if generated_stories > 0:
        save_yaml(struct, args.video_struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"generate_scene_list found {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings,
                     "generated_stories": generated_stories, "generated_scenes": generated_scenes},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"generated {generated_scenes} scene(s) across {generated_stories} story(ies) "
                   f"with {len(warnings)} warning(s)",
            "data": {"warnings": warnings,
                     "generated_stories": generated_stories, "generated_scenes": generated_scenes,
                     "skipped_stories": skipped_stories},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"generated {generated_scenes} scene(s) across {generated_stories} story(ies) "
                   f"({skipped_stories} story(ies) skipped, already had sections)",
            "data": {"generated_stories": generated_stories, "generated_scenes": generated_scenes,
                     "skipped_stories": skipped_stories},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
