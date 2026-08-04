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


def get_origin_dimensions(project_config: dict, asset_type: str = "image") -> tuple[int, int]:
    """Get origin (pre-upscale) dimensions from aigc config fields."""
    aigc_cfg = project_config.get("aigc", {})
    if asset_type == "video":
        return (
            aigc_cfg.get("origin_video_width", 1280),
            aigc_cfg.get("origin_video_height", 720),
        )
    return (
        aigc_cfg.get("origin_image_width", 1280),
        aigc_cfg.get("origin_image_height", 720),
    )


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

    from lib.net import download_file
    download_file(file_url, output_path)

    return output_path


def iter_asset_refs(video_struct: dict):
    """Yield (ref, asset_type, is_aigc) for every asset holder.

    A MediaSection scene (media_list non-empty) holds its assets on the item
    dicts, not on the scene — those are yielded per item; ordinary scenes yield
    themselves. `ref` is the dict whose origin_asset_path/asset_path get
    updated, so write-backs always land on the right place.
    """
    for story in video_struct.get("stories", []):
        for section in story.get("section_list", []):
            for scene in section.get("scene_list", []):
                media_list = scene.get("media_list") or []
                if media_list:
                    for item in media_list:
                        yield item, item.get("type", "image"), item.get("asset_generation_method") == "aigc"
                else:
                    yield scene, scene.get("type", "image"), scene.get("is_aigc_scene", False)


def collect_scenes_to_upscale(video_struct: dict) -> list[dict]:
    """Collect all AIGC assets (scenes or media_list items) that have origin_asset_path but no asset_path."""
    scenes = []
    for scene_ref, asset_type, is_aigc in iter_asset_refs(video_struct):
        origin = scene_ref.get("origin_asset_path", "")
        asset = scene_ref.get("asset_path", "")
        if origin and not asset and is_aigc:
            scenes.append({
                "scene_id": scene_ref.get("id", ""),
                "origin_asset_path": origin,
                "type": asset_type,
                "scene_ref": scene_ref,
            })
    return scenes


def main() -> None:
    parser = argparse.ArgumentParser(description="Upscale AIGC assets")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent upscale workers")
    parser.add_argument("--timeout", type=int, default=300, help="Per-task timeout (seconds)")
    parser.add_argument("--force", action="store_true", help="Re-upscale even if asset_path exists")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config, args.video_struct)

    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)

    target_w, target_h = get_target_dimensions(project_config)
    img_ow, img_oh = get_origin_dimensions(project_config, "image")
    vid_ow, vid_oh = get_origin_dimensions(project_config, "video")
    img_mag = calculate_magnification(img_ow, img_oh, target_w, target_h)
    vid_mag = calculate_magnification(vid_ow, vid_oh, target_w, target_h)

    # Check if upscale is needed for either type
    if img_mag <= 1.0 and vid_mag <= 1.0:
        print(json.dumps({
            "status": "ok",
            "msg": "No upscale needed (origin dimensions >= target for both image and video)",
            "data": {"image_magnification": img_mag, "video_magnification": vid_mag},
        }, ensure_ascii=False, indent=2))
        return

    # Collect scenes
    scenes = collect_scenes_to_upscale(video_struct)
    if args.force:
        # Include assets that already have asset_path
        for scene_ref, asset_type, is_aigc in iter_asset_refs(video_struct):
            origin = scene_ref.get("origin_asset_path", "")
            if origin and is_aigc:
                already_in = any(s["scene_id"] == scene_ref.get("id") for s in scenes)
                if not already_in:
                    scenes.append({
                        "scene_id": scene_ref.get("id", ""),
                        "origin_asset_path": origin,
                        "type": asset_type,
                        "scene_ref": scene_ref,
                    })

    if not scenes:
        print(json.dumps({
            "status": "ok",
            "msg": "No scenes to upscale",
            "data": {},
        }, ensure_ascii=False, indent=2))
        return

    print(f"Upscaling {len(scenes)} scene(s), image={img_mag}x, video={vid_mag}x...", file=sys.stderr)

    errors = []

    def do_upscale(scene_info: dict) -> dict:
        origin = scene_info["origin_asset_path"]
        asset_type = scene_info["type"]
        # Output: same dir, filename without origin_ prefix
        origin_p = Path(origin)
        output_name = origin_p.name.replace("origin_", "")
        output_path = str(origin_p.parent / output_name)

        # Per-type magnification
        mag = vid_mag if asset_type == "video" else img_mag
        if mag <= 1.0:
            # No upscale needed for this asset type — copy origin as asset
            import shutil
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, output_path)
            return {"scene_id": scene_info["scene_id"], "path": output_path, "error": None, "skipped": True}

        # Skip if upscaled output already exists
        if not args.force and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            return {"scene_id": scene_info["scene_id"], "path": output_path, "error": None, "skipped": True}

        try:
            result_path = upscale_asset(
                origin_path=origin,
                output_path=output_path,
                asset_type=asset_type,
                magnification=mag,
                timeout=args.timeout,
            )
            return {"scene_id": scene_info["scene_id"], "path": result_path, "error": None}
        except Exception as e:
            return {"scene_id": scene_info["scene_id"], "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(do_upscale, s): s for s in scenes}
        upscaled = 0
        skipped = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result.get("error"):
                errors.append(result)
                print(f"  ERROR {result['scene_id']}: {result['error']}", file=sys.stderr)
            elif result.get("skipped"):
                skipped += 1
                print(f"  SKIP {result['scene_id']} (already exists)", file=sys.stderr)
                # Still update video_struct from disk
                for s in scenes:
                    if s["scene_id"] == result["scene_id"]:
                        s["scene_ref"]["asset_path"] = result["path"]
                        break
            else:
                upscaled += 1
                # Update video_struct
                for s in scenes:
                    if s["scene_id"] == result["scene_id"]:
                        s["scene_ref"]["asset_path"] = result["path"]
                        break

    print(f"  Upscale: {upscaled} new, {skipped} skipped", file=sys.stderr)

    # 视频素材压缩已移除:本地渲染在 render.py 渲染前压缩,
    # 分布式渲染在 remotion-render 节点解压后压缩(见 render.py / server.py)

    # Save updated video_struct
    save_yaml(video_struct, args.video_struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"Upscale completed with {len(errors)} error(s)",
            "data": {"upscaled": upscaled, "skipped": skipped, "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"Upscaled {upscaled} asset(s) ({skipped} skipped), image={img_mag}x, video={vid_mag}x",
            "data": {"upscaled": upscaled, "skipped": skipped, "image_magnification": img_mag, "video_magnification": vid_mag},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
