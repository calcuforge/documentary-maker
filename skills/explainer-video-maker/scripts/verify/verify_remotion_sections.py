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
VALID_CODECS = ["h264", "h265", "hevc", "vp8", "vp9", "av1", "prores"]


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

    codec = config.get("codec", "")
    if codec and codec.lower() not in VALID_CODECS:
        errors.append(f"[codec] invalid '{codec}'. Valid: {VALID_CODECS}")
    crf = config.get("crf")
    if crf is not None:
        if not isinstance(crf, (int, float)) or not (0 <= crf <= 51):
            errors.append(f"[crf] must be 0-51, got '{crf}'")
    timeout_ms = config.get("timeout_ms")
    if timeout_ms is not None:
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
            errors.append(f"[timeout_ms] must be a positive integer, got '{timeout_ms}'")

    # Theme
    theme = config.get("theme", {})
    if not theme:
        errors.append("[theme] section is missing")
    else:
        transition = theme.get("transition_type", "")
        if transition and transition not in VALID_TRANSITIONS:
            errors.append(f"[theme.transition_type] invalid '{transition}'")

    # BGM (optional top-level block emitted by generate_remotion_sections.py)
    bgm = config.get("bgm", {})
    if bgm:
        if not bgm.get("audio"):
            errors.append("[bgm.audio] is required when a bgm block is present")
        volume = bgm.get("volume")
        if volume is not None:
            if not isinstance(volume, (int, float)) or not (0 <= volume <= 0.3):
                errors.append(f"[bgm.volume] must be 0-0.3, got '{volume}'")
        loop = bgm.get("loop")
        if loop is not None and not isinstance(loop, bool):
            errors.append(f"[bgm.loop] must be a boolean, got '{loop}'")

    # Subtitle
    subtitle = config.get("subtitle", {})
    sub_list: list[dict] = []
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
            scene_index = sub.get("scene_index")
            if scene_index is not None:
                if isinstance(scene_index, bool) or not isinstance(scene_index, int) or scene_index < 0:
                    errors.append(f"[subtitle.list[{i}]] scene_index must be a non-negative integer, got '{scene_index}'")

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

            # volume (narration audio multiplier)
            volume = section.get("volume")
            if volume is not None:
                if not isinstance(volume, (int, float)) or not (0 <= volume <= 1.0):
                    errors.append(f"{sec_prefix}: 'volume' must be 0-1.0, got '{volume}'")

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
    else:
        for i, sub in enumerate(sub_list):
            scene_index = sub.get("scene_index")
            if scene_index is not None and scene_index >= total_scenes:
                warnings.append(f"[subtitle.list[{i}]] scene_index {scene_index} out of range (only {total_scenes} scenes)")

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
