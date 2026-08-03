#!/usr/bin/env python3
"""
Validate video_tasks.yaml against video_struct.yaml.

Checks:
- All AIGC scenes in video_struct have corresponding tasks
- dependent_task field references valid ordinals
- ordinal values are globally unique
- workflow_code is valid (checked via comfyui-scheduler if available)
- payload is valid JSON
- task_group_ordinal is sequential and unique

Usage:
    python verify_video_tasks.py --video-tasks /abs/path/video_tasks.yaml \
                                 --video-struct /abs/path/video_struct.yaml

Exit codes: 0 = valid, 1 = errors, 2 = warnings only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml

# Known valid workflow codes (from comfyui-scheduler/doc/workflow.md)
KNOWN_WORKFLOW_CODES = [
    "index_tts_2",
    "ltx2.3_flf2v_int8",
    "ltx2.3_i2v_int8",
    "ltx2.3_t2v_int8",
    "nvidia_rtx_image_upscale",
    "nvidia_rtx_video_upscale",
    "qwen3_tts_voice_design",
    "qwen_image_edit_2511_int8_step4",
    "wan2.2_svi2pro_vbvr_int8",
    "z_image_fp16",
]


def check_workflow_code_valid(code: str) -> bool | None:
    """Check if workflow code exists. Returns None if comfyui-scheduler unavailable."""
    if not shutil.which("comfyui-scheduler"):
        return None
    try:
        result = subprocess.run(
            ["comfyui-scheduler", "run", "-w", code, "-i", "{}"],
            capture_output=True, text=True, timeout=15,
        )
        # If it says "Workflow not found", it's invalid
        combined = result.stdout + result.stderr
        if "not found" in combined.lower() or "unknown" in combined.lower():
            return False
        # Other errors (missing inputs) mean the workflow exists
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def collect_aigc_scenes(video_struct: dict) -> set[str]:
    """Collect scene IDs (and MediaSection media_list item IDs) that require AIGC.

    Tasks may reference either a scene id or an aigc media_list item id; both
    are collected so coverage checks accept item-level tasks.
    """
    aigc_scenes = set()
    for story in video_struct.get("stories", []):
        for section in story.get("section_list", []):
            for scene in section.get("scene_list", []):
                if scene.get("is_aigc_scene", False):
                    aigc_scenes.add(scene.get("id", ""))
                for item in scene.get("media_list") or []:
                    if item.get("asset_generation_method") == "aigc":
                        aigc_scenes.add(item.get("id", ""))
    return aigc_scenes


def validate(tasks: dict, video_struct: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    task_groups = tasks.get("task_group_list", [])
    if not task_groups:
        errors.append("[task_group_list] is empty or missing")
        return errors, warnings

    # Collect all AIGC scenes from video_struct
    aigc_scenes = collect_aigc_scenes(video_struct)
    covered_scenes = set()

    # Track ordinals
    all_ordinals = set()
    group_ordinals = set()

    for gi, group in enumerate(task_groups):
        g_prefix = f"task_group_list[{gi}]"

        # Group ordinal
        group_ord = group.get("task_group_ordinal")
        if group_ord is None:
            errors.append(f"{g_prefix}: 'task_group_ordinal' is required")
        elif group_ord in group_ordinals:
            errors.append(f"{g_prefix}: duplicate task_group_ordinal {group_ord}")
        else:
            group_ordinals.add(group_ord)

        # Workflow code
        workflow_code = group.get("workflow_code", "")
        if not workflow_code:
            errors.append(f"{g_prefix}: 'workflow_code' is required")
        elif workflow_code not in KNOWN_WORKFLOW_CODES:
            # Try live check
            valid = check_workflow_code_valid(workflow_code)
            if valid is False:
                errors.append(f"{g_prefix}: workflow_code '{workflow_code}' not found in comfyui-scheduler")
            elif valid is None:
                warnings.append(f"{g_prefix}: workflow_code '{workflow_code}' not in known list (comfyui-scheduler unavailable for live check)")

        group_tasks = group.get("tasks", [])
        if not group_tasks:
            errors.append(f"{g_prefix}: 'tasks' list is empty")

        for ti, task in enumerate(group_tasks):
            t_prefix = f"{g_prefix}.tasks[{ti}]"

            # Ordinal
            ordinal = task.get("ordinal")
            if ordinal is None:
                errors.append(f"{t_prefix}: 'ordinal' is required")
            elif ordinal in all_ordinals:
                errors.append(f"{t_prefix}: duplicate ordinal {ordinal}")
            else:
                all_ordinals.add(ordinal)

            # Scene ID
            scene_id = task.get("scene_id", "")
            if not scene_id:
                errors.append(f"{t_prefix}: 'scene_id' is required")
            else:
                covered_scenes.add(scene_id)
                if scene_id not in aigc_scenes:
                    warnings.append(f"{t_prefix}: scene_id '{scene_id}' is not an AIGC scene in video_struct")

            # Payload
            payload = task.get("payload", "")
            if not payload:
                errors.append(f"{t_prefix}: 'payload' is required")
            elif isinstance(payload, str):
                try:
                    json.loads(payload)
                except json.JSONDecodeError as e:
                    errors.append(f"{t_prefix}: invalid JSON in payload: {e}")

            # Dependent task
            dep = task.get("dependent_task", 0)
            if dep and dep != 0:
                if dep not in all_ordinals and dep >= (ordinal or 0):
                    errors.append(f"{t_prefix}: dependent_task {dep} must reference a previously defined ordinal")

    # Check coverage: all AIGC scenes should have tasks
    uncovered = aigc_scenes - covered_scenes
    if uncovered:
        errors.append(f"AIGC scenes without tasks: {sorted(uncovered)}")

    # Check group ordinal ordering
    sorted_ords = sorted(group_ordinals)
    if sorted_ords and sorted_ords != list(range(1, len(sorted_ords) + 1)):
        warnings.append(f"task_group_ordinal values {sorted_ords} are not sequential from 1")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate video_tasks.yaml")
    parser.add_argument("--video-tasks", required=True, help="Path to video_tasks.yaml (absolute)")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_tasks, args.video_struct)

    tasks = load_yaml(args.video_tasks)
    video_struct = load_yaml(args.video_struct)

    errors, warnings = validate(tasks, video_struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"video_tasks.yaml has {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"video_tasks.yaml is valid with {len(warnings)} warning(s)",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "video_tasks.yaml is valid",
            "data": {},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
