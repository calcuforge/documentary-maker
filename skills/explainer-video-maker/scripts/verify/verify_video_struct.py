#!/usr/bin/env python3
"""
Validate video_struct.yaml structure and business rules.

Key validations:
- is_aigc_scene=true → workflows and type must not be empty
- is_aigc_scene=false → data and text must not BOTH be empty
- percent values within each narration unit must sum to 100
- All IDs must be globally unique
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

        narration_list = story.get("narration_list", [])
        if not narration_list:
            errors.append(f"{prefix}: 'narration_list' is empty")

        for ni, narration in enumerate(narration_list):
            narration_id = narration.get("id", "")
            n_prefix = f"{prefix}.narration_list[{ni}]"

            if not narration_id:
                errors.append(f"{n_prefix}: 'id' is required")
            elif narration_id in narration_ids:
                errors.append(f"{n_prefix}: duplicate narration id '{narration_id}'")
            narration_ids.add(narration_id)

            if not narration.get("content"):
                errors.append(f"{n_prefix}: 'content' (narration text) is required")

            scene_list = narration.get("scene_list", [])
            if not scene_list:
                errors.append(f"{n_prefix}: 'scene_list' is empty")

            # Check percent sum
            percent_sum = sum(s.get("percent", 0) for s in scene_list)
            if scene_list and percent_sum != 100:
                errors.append(f"{n_prefix}: scene percent values sum to {percent_sum}, expected 100")

            for sci, scene in enumerate(scene_list):
                scene_id = scene.get("id", "")
                s_prefix = f"{n_prefix}.scene_list[{sci}]"

                if not scene_id:
                    errors.append(f"{s_prefix}: 'id' is required")
                elif scene_id in scene_ids:
                    errors.append(f"{s_prefix}: duplicate scene id '{scene_id}'")
                scene_ids.add(scene_id)

                # Percent validation
                percent = scene.get("percent")
                if percent is None:
                    errors.append(f"{s_prefix}: 'percent' is required")
                elif not isinstance(percent, (int, float)) or percent <= 0 or percent > 100:
                    errors.append(f"{s_prefix}: 'percent' must be 1-100, got {percent}")

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
