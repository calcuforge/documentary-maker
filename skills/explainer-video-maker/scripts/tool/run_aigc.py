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
import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml

# Matches $taskN dependency placeholders inside a payload JSON string.
# \d+ is greedy and bounded by non-digits, so $task1 never collides with $task10.
PLACEHOLDER_RE = re.compile(r"\$task(\d+)")


def find_scene_context(video_struct: dict, scene_id: str) -> dict | None:
    """Find the story_id and narration_id for a given scene_id.

    Narration lives on the section (section.narration); each section maps to 1-N
    scenes. MediaSection scenes also accept a media_list item id (e.g.
    "scene3a-1"); the returned `scene` is then the item dict, so the caller's
    origin_asset_path write-back lands on the item.
    """
    for story in video_struct.get("stories", []):
        for section in story.get("section_list", []):
            narration = section.get("narration") or {}
            for scene in section.get("scene_list", []):
                if scene.get("id") == scene_id:
                    return {
                        "story_id": story.get("id", ""),
                        "narration_id": narration.get("id", ""),
                        "scene": scene,
                    }
                for item in scene.get("media_list") or []:
                    if item.get("id") == scene_id:
                        return {
                            "story_id": story.get("id", ""),
                            "narration_id": narration.get("id", ""),
                            "scene": item,
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

    from lib.video import make_faststart

    # Non-faststart mp4s (moov atom at EOF) make Remotion time out fetching frames
    # via HTTP range requests — re-mux to faststart (stream copy, lossless).
    if output_path.lower().endswith(".mp4") and not make_faststart(output_path):
        print(f"    WARNING: faststart re-mux failed for {output_path}", file=sys.stderr)

    return output_path


def collect_retry_set(task_groups: list[dict], retry_ordinals: list[int]) -> set[int]:
    """Build the full set of ordinals to re-execute.

    Includes the requested ordinals plus all transitive dependents
    (tasks whose dependent_task chain leads back to a retried task).
    """
    # Build dependency map: ordinal -> dependent_task
    all_tasks = []
    for group in task_groups:
        all_tasks.extend(group.get("tasks", []))

    retry_set = set(retry_ordinals)

    # Iteratively find dependents until no new ones are found
    changed = True
    while changed:
        changed = False
        for task in all_tasks:
            ordinal = task.get("ordinal", 0)
            dep = task.get("dependent_task", 0)
            if dep in retry_set and ordinal not in retry_set:
                retry_set.add(ordinal)
                changed = True

    return retry_set


def validate_placeholders(task_groups: list[dict]) -> list[str]:
    """Pre-flight check: every $taskN placeholder must reference a task in an
    EARLIER group.

    Groups run sequentially (each fully completes before the next starts), so only
    earlier groups' outputs are available when a task executes. Returns error
    messages; empty list = all placeholders resolvable.
    """
    ordinal_group: dict[int, int] = {}
    for group in task_groups:
        gord = group.get("task_group_ordinal", 0)
        for task in group.get("tasks", []):
            ordinal_group[task.get("ordinal", 0)] = gord

    errors: list[str] = []
    for group in task_groups:
        gord = group.get("task_group_ordinal", 0)
        for task in group.get("tasks", []):
            ordinal = task.get("ordinal", 0)
            payload = task.get("payload", "{}")
            payload_str = payload if isinstance(payload, str) else json.dumps(payload)
            for m in PLACEHOLDER_RE.finditer(payload_str):
                dep = int(m.group(1))
                dep_group = ordinal_group.get(dep)
                if dep_group is None:
                    errors.append(
                        f"task {ordinal}: $task{dep} references a non-existent task ordinal"
                    )
                elif dep_group >= gord:
                    errors.append(
                        f"task {ordinal}: $task{dep} runs in group {dep_group}, not earlier "
                        f"than this task's group {gord} — dependencies must be in an earlier group"
                    )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute AIGC tasks via comfyui-scheduler")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--video-tasks", required=True, help="Path to video_tasks.yaml (absolute)")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent tasks per group")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Per-task subprocess timeout in seconds (default 30min)")
    parser.add_argument("--total-timeout", type=int, default=7200,
                        help="Total script wall-clock timeout in seconds (default 2h)")
    parser.add_argument("--force", action="store_true", help="Force re-execute all tasks even if output exists")
    parser.add_argument("--retry", default="",
                        help="Comma-separated task ordinals to retry (e.g., '1,3'). "
                             "Dependent tasks are automatically included.")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config, args.video_struct, args.video_tasks)

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

    # Pre-flight: reject unresolved $taskN placeholders BEFORE calling
    # comfyui-scheduler, so we never waste a run on an unresolvable dependency.
    placeholder_errors = validate_placeholders(task_groups)
    if placeholder_errors:
        print(json.dumps({
            "status": "error",
            "msg": f"video_tasks.yaml has {len(placeholder_errors)} unresolved $taskN placeholder(s)",
            "data": {"errors": placeholder_errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Handle --retry: delete origin files for retry tasks + dependents
    retry_ordinals: list[int] = []
    if args.retry:
        retry_ordinals = [int(x.strip()) for x in args.retry.split(",") if x.strip()]

    retry_set: set[int] = set()
    if retry_ordinals:
        retry_set = collect_retry_set(task_groups, retry_ordinals)
        # Delete origin files so the skip logic will re-execute them
        deleted = 0
        for group in task_groups:
            workflow_code = group.get("workflow_code", "")
            for task in group.get("tasks", []):
                if task.get("ordinal") not in retry_set:
                    continue
                scene_id = task.get("scene_id", "")
                ctx = find_scene_context(video_struct, scene_id)
                if not ctx:
                    continue
                ext = get_extension_for_workflow(workflow_code)
                origin_file = video_dir / "stories" / ctx["story_id"] / ctx["narration_id"] / "scenes" / f"origin_{scene_id}.{ext}"
                if origin_file.exists():
                    origin_file.unlink()
                    deleted += 1
        extra = retry_set - set(retry_ordinals)
        print(f"Retry mode: {len(retry_ordinals)} requested + {len(extra)} dependent(s) = {len(retry_set)} task(s) to re-execute", file=sys.stderr)
        if extra:
            print(f"  Auto-included dependents: {sorted(extra)}", file=sys.stderr)
        print(f"  Deleted {deleted} existing origin file(s)", file=sys.stderr)

    # Track task outputs: ordinal -> output file path
    task_outputs: dict[int, str] = {}
    errors = []
    total_tasks = sum(len(g.get("tasks", [])) for g in task_groups)
    completed = 0
    struct_changed = False

    import time
    started_at = time.time()

    print(f"Executing {total_tasks} AIGC tasks in {len(task_groups)} group(s)...", file=sys.stderr)

    for group in task_groups:
        # Check total timeout before starting each group
        elapsed = time.time() - started_at
        if elapsed > args.total_timeout:
            print(f"  Total timeout ({args.total_timeout}s) exceeded after {elapsed:.0f}s — stopping", file=sys.stderr)
            break
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

            # Replace ALL $taskN placeholders with the producing task's output path.
            # Groups run strictly in ascending task_group_ordinal order and each group
            # fully completes before the next starts, so by the time group 2+ executes,
            # task_outputs holds every earlier task's artifact path.
            #
            # Placeholders sit inside JSON string values, so the substituted path must
            # be JSON-escaped (Windows paths carry backslashes that would otherwise form
            # invalid \escapes and break json.loads). Resolve against task_outputs rather
            # than the task's own dependent_task, so a payload may reference any number
            # of dependencies.
            payload_json = json.dumps(payload, ensure_ascii=False)
            missing: list[int] = []

            def _sub(match: re.Match[str]) -> str:
                dep_ordinal = int(match.group(1))
                dep_path = task_outputs.get(dep_ordinal)
                if dep_path is None:
                    missing.append(dep_ordinal)
                    return match.group(0)
                # json.dumps(...)[1:-1] -> escaped content safe to embed in a JSON string
                return json.dumps(dep_path, ensure_ascii=False)[1:-1]

            payload_json = PLACEHOLDER_RE.sub(_sub, payload_json)
            if missing:
                return {
                    "ordinal": ordinal,
                    "error": f"Unresolved $taskN placeholder(s) {sorted(set(missing))}: "
                             f"no output recorded (dependency not executed or failed)",
                }
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
                    # Update video_struct origin_asset_path (skip if unchanged)
                    ctx = find_scene_context(video_struct, result["scene_id"])
                    if ctx and ctx["scene"].get("origin_asset_path") != result["path"]:
                        ctx["scene"]["origin_asset_path"] = result["path"]
                        struct_changed = True

        print(f"  Group {group_ordinal}: {completed} new, {skipped} skipped", file=sys.stderr)

    # Save updated video_struct only if something changed
    if struct_changed:
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
