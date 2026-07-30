#!/usr/bin/env python3
"""
Validate video_struct.yaml structure and business rules.

Structure hierarchy: stories → scene_list → scene, with a nested `narration`
property on each scene (1 scene corresponds to exactly 1 narration).

Key validations:
- is_aigc_scene=true → workflows and type must not be empty
- is_aigc_scene=false → data and text must not BOTH be empty
- each scene has a narration with a non-empty content
- narration content must not exceed MAX_NARRATION_CHARS (50) characters
- All IDs (story / scene / narration) must be globally unique
- remotion_component must be a valid component name

Usage:
    python verify_video_struct.py --video-struct /abs/path/video_struct.yaml

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

VALID_COMPONENTS = [
    "QuoteBlock", "FeatureGrid", "IconCard", "ComparisonCard",
    "StatCounter", "DataBar", "Timeline", "FlowChart",
    "CodeBlock", "DataTable", "DiagramReveal", "AnimationDemo",
    "AssetImage", "AssetVideo",
]

VALID_SCENE_TYPES = ["image", "video", "none"]
VALID_WORKFLOW_TYPES = [
    "text_to_image", "text_to_video", "image_to_video",
    "image_to_image", "first_last_frame_to_video",
]

# A single narration must not exceed this many characters.
MAX_NARRATION_CHARS = 50


def validate(struct: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    stories = struct.get("stories", [])
    if not stories:
        errors.append("[stories] list is empty or missing")
        return errors, warnings

    # Track global IDs
    story_ids = set()
    narration_ids = set()
    scene_ids = set()

    for si, story in enumerate(stories):
        story_id = story.get("id", "")
        prefix = f"stories[{si}]"

        if not story_id:
            errors.append(f"{prefix}: 'id' is required")
        elif story_id in story_ids:
            errors.append(f"{prefix}: duplicate story id '{story_id}'")
        story_ids.add(story_id)

        if not story.get("name"):
            warnings.append(f"{prefix}: 'name' is empty")

        scene_list = story.get("scene_list", [])
        if not scene_list:
            errors.append(f"{prefix}: 'scene_list' is empty")

        for sci, scene in enumerate(scene_list):
            scene_id = scene.get("id", "")
            s_prefix = f"{prefix}.scene_list[{sci}]"

            if not scene_id:
                errors.append(f"{s_prefix}: 'id' is required")
            elif scene_id in scene_ids:
                errors.append(f"{s_prefix}: duplicate scene id '{scene_id}'")
            scene_ids.add(scene_id)

            # Component validation
            component = scene.get("remotion_component", "")
            if not component:
                errors.append(f"{s_prefix}: 'remotion_component' is required")
            elif component not in VALID_COMPONENTS:
                errors.append(f"{s_prefix}: invalid remotion_component '{component}'. Valid: {VALID_COMPONENTS}")

            # AIGC vs non-AIGC validation
            is_aigc = scene.get("is_aigc_scene", False)

            if is_aigc:
                # AIGC scene: workflows and type required
                scene_type = scene.get("type", "")
                if not scene_type or scene_type == "none":
                    errors.append(f"{s_prefix}: is_aigc_scene=true but 'type' is empty/none")
                elif scene_type not in VALID_SCENE_TYPES:
                    errors.append(f"{s_prefix}: invalid type '{scene_type}'. Valid: {VALID_SCENE_TYPES}")

                workflows = scene.get("workflows", [])
                if not workflows:
                    errors.append(f"{s_prefix}: is_aigc_scene=true but 'workflows' is empty")
                else:
                    for wi, wf in enumerate(workflows):
                        wt = wf.get("workflow_type", "")
                        if not wt:
                            errors.append(f"{s_prefix}.workflows[{wi}]: 'workflow_type' is required")
                        elif wt not in VALID_WORKFLOW_TYPES:
                            errors.append(f"{s_prefix}.workflows[{wi}]: invalid workflow_type '{wt}'. Valid: {VALID_WORKFLOW_TYPES}")

                if not scene.get("visual_content"):
                    warnings.append(f"{s_prefix}: 'visual_content' is empty (recommended for AIGC scenes)")
            else:
                # Non-AIGC scene: data and text must not both be empty
                data = scene.get("data", "")
                text = scene.get("text", "")
                if not data and not text:
                    errors.append(f"{s_prefix}: is_aigc_scene=false but both 'data' and 'text' are empty")

            # Narration validation — each scene carries exactly one narration
            narration = scene.get("narration")
            n_prefix = f"{s_prefix}.narration"
            if not isinstance(narration, dict):
                errors.append(f"{n_prefix}: is required (each scene must carry one narration)")
            else:
                narration_id = narration.get("id", "")
                if not narration_id:
                    errors.append(f"{n_prefix}: 'id' is required")
                elif narration_id in narration_ids:
                    errors.append(f"{n_prefix}: duplicate narration id '{narration_id}'")
                narration_ids.add(narration_id)

                content = narration.get("content", "")
                if not content:
                    errors.append(f"{n_prefix}: 'content' (narration text) is required")
                elif len(content) > MAX_NARRATION_CHARS:
                    errors.append(
                        f"{n_prefix}: 'content' is {len(content)} chars, "
                        f"exceeds the {MAX_NARRATION_CHARS}-character limit"
                    )

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate video_struct.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    struct = load_yaml(args.video_struct)
    errors, warnings = validate(struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"video_struct.yaml has {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"video_struct.yaml is valid with {len(warnings)} warning(s)",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "video_struct.yaml is valid",
            "data": {},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
