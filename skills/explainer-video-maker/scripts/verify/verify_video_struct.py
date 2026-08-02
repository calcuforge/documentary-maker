#!/usr/bin/env python3
"""
Validate video_struct.yaml structure and business rules.

Structure hierarchy: stories → section_list → {narration, scene_list[]}. Each
section carries exactly one narration and 1-N scenes; each scene carries an
integer `percentage` (sum = 100 per narration) that splits the narration's frames.

Key validations:
- is_aigc_scene=true + asset_generation_method=aigc → workflows and type must not be empty
- is_aigc_scene=true + asset_generation_method=stock → type required, workflows may be empty
- is_aigc_scene=false → data and text must not BOTH be empty
- each section has a narration with a non-empty content (no length cap)
- each scene has an integer `percentage` 0-100; Σ percentage per narration = 100
- All IDs (story / scene / narration) must be globally unique
- remotion_component must be a valid component name
- the chapter script (stories/{story_id}/script.md) must equal all of that
  story's narration contents merged together (compared ignoring whitespace)

Usage:
    python verify_video_struct.py --video-struct /abs/path/video_struct.yaml

Exit codes: 0 = valid, 1 = errors found, 2 = warnings only.
"""

from __future__ import annotations

import argparse
import json
import re
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

VALID_SCENE_TYPES = ["image", "video", "none"]
VALID_WORKFLOW_TYPES = [
    "text_to_image", "text_to_video", "image_to_video",
    "image_to_image", "first_last_frame_to_video",
]

# Per-chapter narration script filename (written in Step 5).
SCRIPT_FILENAME = "script.md"


def _normalize(text: str) -> str:
    """Strip all whitespace so scripts and merged narrations compare regardless
    of paragraph/line formatting."""
    return re.sub(r"\s+", "", text or "")


def validate(struct: dict, video_dir: str | None = None) -> tuple[list[str], list[str]]:
    """Return (errors, warnings).

    If video_dir is given, also cross-checks that each story's chapter script
    (stories/{story_id}/script.md) equals its narration contents merged together.
    """
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

        section_list = story.get("section_list", [])
        if not section_list:
            errors.append(f"{prefix}: 'section_list' is empty")

        narration_contents = []  # in section order, for the script merge check
        for sei, section in enumerate(section_list):
            sec_prefix = f"{prefix}.section_list[{sei}]"

            # Narration validation — one narration per section
            narration = section.get("narration")
            n_prefix = f"{sec_prefix}.narration"
            if not isinstance(narration, dict):
                errors.append(f"{n_prefix}: is required (each section must carry one narration)")
            else:
                narration_id = narration.get("id", "")
                if not narration_id:
                    errors.append(f"{n_prefix}: 'id' is required")
                elif narration_id in narration_ids:
                    errors.append(f"{n_prefix}: duplicate narration id '{narration_id}'")
                narration_ids.add(narration_id)

                content = narration.get("content", "")
                narration_contents.append(content)
                if not content:
                    errors.append(f"{n_prefix}: 'content' (narration text) is required")

            scene_list = section.get("scene_list", [])
            if not scene_list:
                errors.append(f"{sec_prefix}: 'scene_list' is empty")

            section_percents: list[int] = []
            for scni, scene in enumerate(scene_list):
                scene_id = scene.get("id", "")
                scn_prefix = f"{sec_prefix}.scene_list[{scni}]"

                if not scene_id:
                    errors.append(f"{scn_prefix}: 'id' is required")
                elif scene_id in scene_ids:
                    errors.append(f"{scn_prefix}: duplicate scene id '{scene_id}'")
                scene_ids.add(scene_id)

                # Component validation
                component = scene.get("remotion_component", "")
                if not component:
                    errors.append(f"{scn_prefix}: 'remotion_component' is required")
                elif component not in VALID_COMPONENTS:
                    errors.append(f"{scn_prefix}: invalid remotion_component '{component}'. Valid: {VALID_COMPONENTS}")

                # AIGC vs non-AIGC validation
                is_aigc = scene.get("is_aigc_scene", False)

                if is_aigc:
                    scene_type = scene.get("type", "")
                    if not scene_type or scene_type == "none":
                        errors.append(f"{scn_prefix}: is_aigc_scene=true but 'type' is empty/none")
                    elif scene_type not in VALID_SCENE_TYPES:
                        errors.append(f"{scn_prefix}: invalid type '{scene_type}'. Valid: {VALID_SCENE_TYPES}")

                    gen_method = scene.get("asset_generation_method", "aigc")

                    if gen_method == "stock":
                        pass  # stock scenes: workflows not required (no ComfyUI)
                    else:
                        workflows = scene.get("workflows", [])
                        if not workflows:
                            errors.append(f"{scn_prefix}: is_aigc_scene=true (aigc) but 'workflows' is empty")
                        else:
                            for wi, wf in enumerate(workflows):
                                wt = wf.get("workflow_type", "")
                                if not wt:
                                    errors.append(f"{scn_prefix}.workflows[{wi}]: 'workflow_type' is required")
                                elif wt not in VALID_WORKFLOW_TYPES:
                                    errors.append(f"{scn_prefix}.workflows[{wi}]: invalid workflow_type '{wt}'. Valid: {VALID_WORKFLOW_TYPES}")

                    if not scene.get("visual_content"):
                        warnings.append(f"{scn_prefix}: 'visual_content' is empty (recommended for AIGC scenes)")
                else:
                    data = scene.get("data", "")
                    text = scene.get("text", "")
                    if not data and not text:
                        errors.append(f"{scn_prefix}: is_aigc_scene=false but both 'data' and 'text' are empty")

                # Percentage — frame share of the narration (Σ per section = 100)
                pct = scene.get("percentage")
                if pct is None:
                    errors.append(f"{scn_prefix}: 'percentage' is required (int 0-100; Σ per narration = 100)")
                elif isinstance(pct, bool) or not isinstance(pct, int) or not (0 <= pct <= 100):
                    errors.append(f"{scn_prefix}: 'percentage' must be an integer 0-100, got '{pct}'")
                else:
                    section_percents.append(pct)
                    if pct == 0:
                        warnings.append(f"{scn_prefix}: 'percentage' is 0 — scene gets 0 frames")

            if section_percents and sum(section_percents) != 100:
                errors.append(
                    f"{sec_prefix}: scene percentages sum to {sum(section_percents)}, must be 100"
                )

        # Cross-check: the chapter script must equal the merged narration contents.
        # (All narrations concatenated == script.md, compared ignoring whitespace.)
        if video_dir is not None and story_id and narration_contents:
            merged = "".join(narration_contents)
            script_path = Path(video_dir) / "stories" / story_id / SCRIPT_FILENAME
            if not script_path.exists():
                warnings.append(
                    f"{prefix}: chapter script not found ({script_path}); "
                    f"cannot verify narrations match the script"
                )
            elif _normalize(merged) != _normalize(script_path.read_text(encoding="utf-8")):
                errors.append(
                    f"{prefix}: merged narration contents do NOT equal the chapter script "
                    f"({script_path}). Concatenating all narrations must reproduce script.md exactly."
                )

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate video_struct.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    struct = load_yaml(args.video_struct)
    video_dir = str(Path(args.video_struct).parent)
    errors, warnings = validate(struct, video_dir)

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
