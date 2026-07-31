#!/usr/bin/env python3
"""
Validate remotion_sections.yaml for completeness and correctness.

Nested structure:
  stories[].section_list[] → {audio, scene_list[]}
  scene_list[].scene[] → {total_frame, remotion_component, remotion_data, scene_id}

Checks:
- Required top-level fields: resolution, orientation, fps, theme, subtitle, stories
- Each narration section has audio and scene_list
- Each scene has: total_frame (positive), remotion_component (valid), remotion_data (valid JSON)
- Subtitle start/end frames are consistent

Usage:
    python verify_remotion_sections.py --remotion-sections /abs/path/remotion_sections.yaml

Exit codes: 0 = valid, 1 = errors, 2 = warnings only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml

VALID_COMPONENTS = [
    "QuoteBlock", "FeatureGrid", "IconCard", "ComparisonCard",
    "StatCounter", "DataBar", "Timeline", "FlowChart",
    "CodeBlock", "DataTable", "DiagramReveal", "AnimationDemo",
    "AssetImage", "AssetVideo", "KenBurnsImage",
]

VALID_RESOLUTIONS = ["1080P", "4K", "1080p", "4k"]
VALID_ORIENTATIONS = ["horizontal", "vertical"]
VALID_TRANSITIONS = ["fade", "slide", "wipe", "none"]


def validate(config: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    # Top-level fields
    resolution = config.get("resolution", "")
    if not resolution:
        errors.append("[resolution] is required")
    elif resolution not in VALID_RESOLUTIONS:
        errors.append(f"[resolution] invalid '{resolution}'. Valid: {VALID_RESOLUTIONS}")

    orientation = config.get("orientation", "")
    if not orientation:
        errors.append("[orientation] is required")
    elif orientation not in VALID_ORIENTATIONS:
        errors.append(f"[orientation] invalid '{orientation}'. Valid: {VALID_ORIENTATIONS}")

    fps = config.get("fps")
    if fps is None:
        errors.append("[fps] is required")
    elif not isinstance(fps, (int, float)) or fps <= 0:
        errors.append(f"[fps] must be positive, got {fps}")

    # Theme
    theme = config.get("theme", {})
    if not theme:
        errors.append("[theme] section is missing")
    else:
        transition = theme.get("transition_type", "")
        if transition and transition not in VALID_TRANSITIONS:
            errors.append(f"[theme.transition_type] invalid '{transition}'")

    # Subtitle
    subtitle = config.get("subtitle", {})
    if not subtitle:
        warnings.append("[subtitle] section is missing")
    else:
        sub_list = subtitle.get("list", [])
        for i, sub in enumerate(sub_list):
            if not sub.get("text"):
                warnings.append(f"[subtitle.list[{i}]] text is empty")
            start = sub.get("start_frame")
            end = sub.get("end_frame")
            if start is not None and end is not None:
                if start > end:
                    errors.append(f"[subtitle.list[{i}]] start_frame ({start}) > end_frame ({end})")

    # Stories — nested structure: section_list[].{audio, scene_list[]}
    stories = config.get("stories", [])
    if not stories:
        errors.append("[stories] list is empty or missing")
        return errors, warnings

    total_scenes = 0
    for si, story in enumerate(stories):
        s_prefix = f"stories[{si}]"

        if not story.get("story_id"):
            errors.append(f"{s_prefix}: 'story_id' is required")
        if not story.get("story_name"):
            warnings.append(f"{s_prefix}: 'story_name' is empty")

        section_list = story.get("section_list", [])
        if not section_list:
            errors.append(f"{s_prefix}: 'section_list' is empty")

        for sci, section in enumerate(section_list):
            sec_prefix = f"{s_prefix}.section_list[{sci}]"

            # audio (narration-level)
            audio = section.get("audio", "")
            if not audio:
                warnings.append(f"{sec_prefix}: 'audio' path is empty")

            # scene_list
            scene_list = section.get("scene_list", [])
            if not scene_list:
                errors.append(f"{sec_prefix}: 'scene_list' is empty or missing")
                continue

            for scni, scene in enumerate(scene_list):
                total_scenes += 1
                scn_prefix = f"{sec_prefix}.scene_list[{scni}]"

                # total_frame
                total_frame = scene.get("total_frame")
                if total_frame is None:
                    errors.append(f"{scn_prefix}: 'total_frame' is required")
                elif not isinstance(total_frame, (int, float)) or total_frame <= 0:
                    errors.append(f"{scn_prefix}: 'total_frame' must be positive, got {total_frame}")

                # remotion_component
                component = scene.get("remotion_component", "")
                if not component:
                    errors.append(f"{scn_prefix}: 'remotion_component' is required")
                elif component not in VALID_COMPONENTS:
                    errors.append(f"{scn_prefix}: invalid component '{component}'. Valid: {VALID_COMPONENTS}")

                # remotion_data
                remotion_data = scene.get("remotion_data", "")
                if not remotion_data:
                    warnings.append(f"{scn_prefix}: 'remotion_data' is empty")
                elif isinstance(remotion_data, str):
                    try:
                        parsed = json.loads(remotion_data)
                        if not parsed:
                            warnings.append(f"{scn_prefix}: 'remotion_data' is empty JSON '{{}}'")
                    except json.JSONDecodeError as e:
                        errors.append(f"{scn_prefix}: invalid JSON in remotion_data: {e}")

                # scene_id
                if not scene.get("scene_id"):
                    warnings.append(f"{scn_prefix}: 'scene_id' is empty")

    if total_scenes == 0:
        errors.append("No scenes found in any story")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate remotion_sections.yaml")
    parser.add_argument("--remotion-sections", required=True, help="Path to remotion_sections.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.remotion_sections)

    config = load_yaml(args.remotion_sections)
    errors, warnings = validate(config)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"remotion_sections.yaml has {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"remotion_sections.yaml valid with {len(warnings)} warning(s)",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "remotion_sections.yaml is valid",
            "data": {},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
