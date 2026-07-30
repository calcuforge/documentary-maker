#!/usr/bin/env python3
"""
Execute AIGC tasks from video_tasks.yaml using comfyui-scheduler.

Processes task groups in order (by task_group_ordinal). Within each group,
tasks are executed concurrently via comfyui-scheduler. After each group
completes, dependent_task placeholders ($taskN) in subsequent groups are
replaced with the actual output file paths.

Output files are saved to:
    {video_dir}/stories/{story_id}/{narration_id}/scenes/origin_{scene_id}.{ext}

Updates video_struct.yaml origin_asset_path for each scene.

Usage:
    python run_aigc.py --project-config /abs/path/project_config.yaml \
                       --video-struct /abs/path/video_struct.yaml \
                       --video-tasks /abs/path/video_tasks.yaml
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml


def find_scene_context(video_struct: dict, scene_id: str) -> dict | None:
    """Find the story_id and narration_id for a given scene_id."""
    for story in video_struct.get("stories", []):
        for narration in story.get("narration_list", []):
            for scene in narration.get("scene_list", []):
                if scene.get("id") == scene_id:
                    return {
                        "story_id": story.get("id", ""),
                        "narration_id": narration.get("id", ""),
                        "scene": scene,
                    }
    return None


def get_extension_for_workflow(workflow_code: str) -> str:
    """Determine output file extension based on workflow code."""
    video_workflows = ["ltx2.3_t2v_int8", "ltx2.3_i2v_int8", "ltx2.3_flf2v_int8", "wan2.2_svi2pro_vbvr_int8"]
    if workflow_code in video_workflows:
        return "mp4"
    return "png"


def run_single_task(
    workflow_code: str,
    payload: dict,
    output_path: str,
    timeout: int = 600,
) -> str:
    """Execute a single comfyui-scheduler task. Returns output file path."""
    inputs_json = json.dumps(payload, ensure_ascii=False)
    cmd = ["comfyui-scheduler", "run", "-w", workflow_code, "-i", inputs_json]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Task timed out after {timeout}s: workflow={workflow_code}")
    except FileNotFoundError:
        raise RuntimeError("comfyui-scheduler not found on PATH")

    if result.returncode != 0:
        raise RuntimeError(f"comfyui-scheduler failed: {result.stderr or result.stdout[:300]}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON output: {result.stdout[:200]}")

    if output.get("status") != "ok":
        raise RuntimeError(f"Workflow error: {output.get('msg', 'unknown')}")

    files = output.get("data", {}).get("files", [])
    if not files:
        raise RuntimeError("No output files from workflow")

    # Download the output file (supports http:// and file:// URLs)
    file_url = files[0].get("url", "")
    if not file_url:
        raise RuntimeError("No URL in output")

    from lib.net import download_file
    download_file(file_url, output_path)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute AIGC tasks via comfyui-scheduler")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml")
    parser.add_argument("--video-tasks", required=True, help="Path to video_tasks.yaml")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent tasks per group")
    parser.add_argument("--timeout", type=int, default=600, help="Per-task timeout (seconds)")
    parser.add_argument("--force", action="store_true", help="Force re-execute even if output already exists")
    args = parser.parse_args()

    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)
    video_tasks = load_yaml(args.video_tasks)

    video_dir = Path(args.video_struct).parent
    task_groups = video_tasks.get("task_group_list", [])

    if not task_groups:
        print(json.dumps({"status": "ok", "msg": "No task groups to execute", "data": {}}, ensure_ascii=False, indent=2))
        return

    # Sort groups by ordinal
    task_groups.sort(key=lambda g: g.get("task_group_ordinal", 0))

    # Track task outputs: ordinal -> output file path
    task_outputs: dict[int, str] = {}
    errors = []
    total_tasks = sum(len(g.get("tasks", [])) for g in task_groups)
    completed = 0

    print(f"Executing {total_tasks} AIGC tasks in {len(task_groups)} group(s)...", file=sys.stderr)

    for group in task_groups:
        workflow_code = group.get("workflow_code", "")
        tasks = group.get("tasks", [])
        group_ordinal = group.get("task_group_ordinal", 0)

        print(f"  Group {group_ordinal}: workflow={workflow_code}, tasks={len(tasks)}", file=sys.stderr)

        def execute_task(task: dict) -> dict:
            """Execute a single task within a group."""
            ordinal = task.get("ordinal", 0)
            scene_id = task.get("scene_id", "")
            payload_str = task.get("payload", "{}")

            # Parse payload and resolve dependencies
            try:
                payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
            except json.JSONDecodeError as e:
                return {"ordinal": ordinal, "error": f"Invalid payload JSON: {e}"}

            # Replace $taskN placeholders with actual paths
            dependent_task = task.get("dependent_task", 0)
            if dependent_task and dependent_task in task_outputs:
                dep_path = task_outputs[dependent_task]
                # Replace placeholder in payload string
                payload_json = json.dumps(payload, ensure_ascii=False)
                payload_json = payload_json.replace(f"$task{dependent_task}", dep_path)
                payload = json.loads(payload_json)

            # Determine output path
            ctx = find_scene_context(video_struct, scene_id)
            if not ctx:
                return {"ordinal": ordinal, "error": f"Scene not found: {scene_id}"}

            ext = get_extension_for_workflow(workflow_code)
            scenes_dir = video_dir / "stories" / ctx["story_id"] / ctx["narration_id"] / "scenes"
            output_path = str(scenes_dir / f"origin_{scene_id}.{ext}")

            # Skip if output already exists (resume after interruption)
            if not args.force and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                return {"ordinal": ordinal, "scene_id": scene_id, "path": output_path, "error": None, "skipped": True}

            try:
                result_path = run_single_task(workflow_code, payload, output_path, args.timeout)
                return {"ordinal": ordinal, "scene_id": scene_id, "path": result_path, "error": None, "skipped": False}
            except Exception as e:
                return {"ordinal": ordinal, "error": str(e)}

        # Execute tasks in this group concurrently
        group_results = []
        skipped = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(execute_task, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                group_results.append(result)
                if result.get("error"):
                    errors.append(result)
                    print(f"    ERROR task {result['ordinal']}: {result['error']}", file=sys.stderr)
                else:
                    task_outputs[result["ordinal"]] = result["path"]
                    if result.get("skipped"):
                        skipped += 1
                        print(f"    SKIP task {result['ordinal']} (already exists)", file=sys.stderr)
                    else:
                        completed += 1
                    # Update video_struct origin_asset_path
                    ctx = find_scene_context(video_struct, result["scene_id"])
                    if ctx:
                        ctx["scene"]["origin_asset_path"] = result["path"]

        print(f"  Group {group_ordinal}: {completed} new, {skipped} skipped", file=sys.stderr)

    # Save updated video_struct
    save_yaml(video_struct, args.video_struct)

    # Report
    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"AIGC completed with {len(errors)} error(s) out of {total_tasks} tasks",
            "data": {"completed": completed, "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"All {completed} AIGC tasks completed successfully",
            "data": {"completed": completed},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
