#!/usr/bin/env python3
"""
Upscale AIGC assets using NVIDIA RTX upscale workflows via comfyui-scheduler.

Reads video_struct.yaml, finds scenes with origin_asset_path set, and upscales
them to the target resolution using nvidia_rtx_image_upscale or
nvidia_rtx_video_upscale workflows.

Output files are saved alongside the origin files (without origin_ prefix).
Updates video_struct.yaml asset_path for each scene.

Usage:
    python run_upscale.py --project-config /abs/path/project_config.yaml \
                          --video-struct /abs/path/video_struct.yaml
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


def get_target_dimensions(project_config: dict) -> tuple[int, int]:
    """Get target width x height from project config."""
    video_cfg = project_config.get("video", {})
    orientation = video_cfg.get("orientation", "horizontal")
    resolution = video_cfg.get("resolution", "1080p")

    if resolution == "4k":
        if orientation == "vertical":
            return 2160, 3840
        return 3840, 2160
    else:  # 1080p
        if orientation == "vertical":
            return 1080, 1920
        return 1920, 1080


def get_origin_dimensions(project_config: dict) -> tuple[int, int]:
    """Get origin (pre-upscale) dimensions based on quality_tier."""
    aigc_cfg = project_config.get("aigc", {})
    quality_tier = aigc_cfg.get("quality_tier", "speed")
    video_cfg = project_config.get("video", {})
    orientation = video_cfg.get("orientation", "horizontal")

    if quality_tier == "speed":
        # image 1280x720, video 854x480
        if orientation == "vertical":
            return 720, 1280
        return 1280, 720
    else:  # quality
        # image 1920x1080, video 1280x720
        if orientation == "vertical":
            return 1080, 1920
        return 1920, 1080


def calculate_magnification(
    origin_w: int, origin_h: int,
    target_w: int, target_h: int,
) -> float:
    """Calculate the upscale magnification factor."""
    mag_w = target_w / origin_w if origin_w > 0 else 1.0
    mag_h = target_h / origin_h if origin_h > 0 else 1.0
    return round(max(mag_w, mag_h), 2)


def upscale_asset(
    origin_path: str,
    output_path: str,
    asset_type: str,
    magnification: float,
    timeout: int = 300,
) -> str:
    """Upscale a single asset via comfyui-scheduler."""
    if asset_type == "video":
        workflow = "nvidia_rtx_video_upscale"
        payload = {"video_file": origin_path, "magnification": magnification}
    else:
        workflow = "nvidia_rtx_image_upscale"
        payload = {"image_file": origin_path, "magnification": magnification}

    inputs_json = json.dumps(payload, ensure_ascii=False)
    cmd = ["comfyui-scheduler", "run", "-w", workflow, "-i", inputs_json]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Upscale timed out: {origin_path}")
    except FileNotFoundError:
        raise RuntimeError("comfyui-scheduler not found on PATH")

    if result.returncode != 0:
        raise RuntimeError(f"Upscale failed: {result.stderr or result.stdout[:300]}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON: {result.stdout[:200]}")

    if output.get("status") != "ok":
        raise RuntimeError(f"Upscale error: {output.get('msg', 'unknown')}")

    files = output.get("data", {}).get("files", [])
    if not files:
        raise RuntimeError("No output files from upscale")

    file_url = files[0].get("url", "")
    if not file_url:
        raise RuntimeError("No URL in upscale output")

    import requests
    resp = requests.get(file_url, timeout=120)
    resp.raise_for_status()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    return output_path


def collect_scenes_to_upscale(video_struct: dict) -> list[dict]:
    """Collect all AIGC scenes that have origin_asset_path but no asset_path."""
    scenes = []
    for story in video_struct.get("stories", []):
        for narration in story.get("narration_list", []):
            for scene in narration.get("scene_list", []):
                origin = scene.get("origin_asset_path", "")
                asset = scene.get("asset_path", "")
                if origin and not asset and scene.get("is_aigc_scene", False):
                    scenes.append({
                        "scene_id": scene.get("id", ""),
                        "origin_asset_path": origin,
                        "type": scene.get("type", "image"),
                        "scene_ref": scene,
                    })
    return scenes


def main() -> None:
    parser = argparse.ArgumentParser(description="Upscale AIGC assets")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent upscale workers")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout (seconds)")
    parser.add_argument("--force", action="store_true", help="Re-upscale even if asset_path exists")
    args = parser.parse_args()

    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)

    target_w, target_h = get_target_dimensions(project_config)
    origin_w, origin_h = get_origin_dimensions(project_config)
    magnification = calculate_magnification(origin_w, origin_h, target_w, target_h)

    # Check if upscale is needed (origin == target means skip)
    if magnification <= 1.0:
        print(json.dumps({
            "status": "ok",
            "msg": "No upscale needed (origin dimensions >= target)",
            "data": {"magnification": magnification},
        }, ensure_ascii=False, indent=2))
        return

    # Collect scenes
    scenes = collect_scenes_to_upscale(video_struct)
    if args.force:
        # Include scenes that already have asset_path
        for story in video_struct.get("stories", []):
            for narration in story.get("narration_list", []):
                for scene in narration.get("scene_list", []):
                    origin = scene.get("origin_asset_path", "")
                    if origin and scene.get("is_aigc_scene", False):
                        already_in = any(s["scene_id"] == scene.get("id") for s in scenes)
                        if not already_in:
                            scenes.append({
                                "scene_id": scene.get("id", ""),
                                "origin_asset_path": origin,
                                "type": scene.get("type", "image"),
                                "scene_ref": scene,
                            })

    if not scenes:
        print(json.dumps({
            "status": "ok",
            "msg": "No scenes to upscale",
            "data": {},
        }, ensure_ascii=False, indent=2))
        return

    print(f"Upscaling {len(scenes)} scene(s), magnification={magnification}x...", file=sys.stderr)

    errors = []
    completed = 0

    def do_upscale(scene_info: dict) -> dict:
        origin = scene_info["origin_asset_path"]
        # Output: same dir, filename without origin_ prefix
        origin_p = Path(origin)
        output_name = origin_p.name.replace("origin_", "")
        output_path = str(origin_p.parent / output_name)

        try:
            result_path = upscale_asset(
                origin_path=origin,
                output_path=output_path,
                asset_type=scene_info["type"],
                magnification=magnification,
                timeout=args.timeout,
            )
            return {"scene_id": scene_info["scene_id"], "path": result_path, "error": None}
        except Exception as e:
            return {"scene_id": scene_info["scene_id"], "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(do_upscale, s): s for s in scenes}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result.get("error"):
                errors.append(result)
                print(f"  ERROR {result['scene_id']}: {result['error']}", file=sys.stderr)
            else:
                completed += 1
                # Update video_struct
                for s in scenes:
                    if s["scene_id"] == result["scene_id"]:
                        s["scene_ref"]["asset_path"] = result["path"]
                        break

    # Save updated video_struct
    save_yaml(video_struct, args.video_struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"Upscale completed with {len(errors)} error(s)",
            "data": {"completed": completed, "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"Upscaled {completed} asset(s) at {magnification}x",
            "data": {"completed": completed, "magnification": magnification},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
