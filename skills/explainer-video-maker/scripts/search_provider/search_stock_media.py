#!/usr/bin/env python3
"""
Search and download stock media (photos/videos) for scenes marked with
asset_generation_method: stock in video_struct.yaml.

Supported providers (API keys configured in project_config.yaml → stock_media.sources):
    pexels   — photos + videos
    pixabay  — photos + videos
    unsplash — photos only

Searches at the project's target resolution (video.resolution / orientation).
If no exact-resolution match exists, downloads the largest available asset;
the upscale step brings it to target resolution later.

Usage:
    python search_stock_media.py \
        --project-config /abs/path/project_config.yaml \
        --video-struct /abs/path/video_struct.yaml \
        [--force]

Exit codes: 0 = ok, 1 = errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml

# Provider names recognized in stock_media.sources[].provider
VALID_PROVIDERS = {"pexels", "pixabay", "unsplash"}

# Resolution presets: (width, height) for horizontal orientation
RESOLUTION_MAP = {
    "1080p": {"horizontal": (1920, 1080), "vertical": (1080, 1920)},
    "4k": {"horizontal": (3840, 2160), "vertical": (2160, 3840)},
}


def get_target_dims(project_config: dict) -> tuple[int, int]:
    """Return (width, height) for the project's target resolution."""
    video_cfg = project_config.get("video", {})
    res = video_cfg.get("resolution", "1080p").lower()
    orient = video_cfg.get("orientation", "horizontal")
    dims = RESOLUTION_MAP.get(res, RESOLUTION_MAP["1080p"])
    return dims.get(orient, (1920, 1080))


def get_configured_sources(project_config: dict) -> list[dict]:
    """Return list of configured source dicts from stock_media.sources.

    Each dict has 'provider' (str) and 'api_key' (str).
    Sources without an api_key are skipped with a warning.
    """
    stock_cfg = project_config.get("stock_media", {})
    sources = stock_cfg.get("sources", [])
    if not sources:
        return []
    result = []
    for s in sources:
        if not isinstance(s, dict):
            print(f"WARNING: invalid stock source entry (not a dict): {s}", file=sys.stderr)
            continue
        name = s.get("provider", "").lower()
        api_key = s.get("api_key", "")
        if name not in VALID_PROVIDERS:
            print(f"WARNING: unknown stock provider '{name}', skipping", file=sys.stderr)
            continue
        if not api_key:
            print(f"WARNING: {name} has no api_key configured, skipping", file=sys.stderr)
            continue
        result.append({"provider": name, "api_key": api_key})
    return result


# ---------------------------------------------------------------------------
# Provider search implementations
# ---------------------------------------------------------------------------

def search_pexels(query: str, media_type: str, target_w: int, target_h: int,
                  api_key: str, max_results: int = 5) -> list[dict]:
    """Search Pexels for photos or videos. Returns list of result dicts."""
    import requests

    headers = {"Authorization": api_key}
    results = []

    if media_type == "video":
        url = "https://api.pexels.com/videos/search"
        params = {
            "query": query,
            "per_page": max_results,
            "size": "large" if target_w <= 1920 else "4k",
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for v in data.get("videos", []):
                # Pick the best quality video file
                files = v.get("video_files", [])
                best = max(files, key=lambda f: f.get("width", 0) * f.get("height", 0)) if files else None
                if best:
                    results.append({
                        "provider": "pexels",
                        "type": "video",
                        "url": best.get("link", ""),
                        "width": best.get("width", 0),
                        "height": best.get("height", 0),
                        "license": "Pexels License (free)",
                        "page_url": v.get("url", ""),
                    })
        except Exception as e:
            print(f"WARNING: Pexels video search failed: {e}", file=sys.stderr)
    else:
        url = "https://api.pexels.com/v1/search"
        params = {
            "query": query,
            "per_page": max_results,
            "orientation": "landscape" if target_w > target_h else "portrait",
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for p in data.get("photos", []):
                src = p.get("src", {})
                results.append({
                    "provider": "pexels",
                    "type": "image",
                    "url": src.get("original", src.get("large2x", "")),
                    "width": p.get("width", 0),
                    "height": p.get("height", 0),
                    "license": "Pexels License (free)",
                    "page_url": p.get("url", ""),
                })
        except Exception as e:
            print(f"WARNING: Pexels photo search failed: {e}", file=sys.stderr)

    return results


def search_pixabay(query: str, media_type: str, target_w: int, target_h: int,
                   api_key: str, max_results: int = 5) -> list[dict]:
    """Search Pixabay for images or videos."""
    import requests

    results = []

    if media_type == "video":
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": api_key,
            "q": query,
            "per_page": max_results,
            "min_width": target_w,
            "min_height": target_h,
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for v in data.get("hits", []):
                videos = v.get("videos", {})
                best = videos.get("large", videos.get("medium", videos.get("small", {})))
                if best and best.get("url"):
                    results.append({
                        "provider": "pixabay",
                        "type": "video",
                        "url": best["url"],
                        "width": best.get("width", 0),
                        "height": best.get("height", 0),
                        "license": "Pixabay License (free)",
                        "page_url": v.get("pageURL", ""),
                    })
        except Exception as e:
            print(f"WARNING: Pixabay video search failed: {e}", file=sys.stderr)
    else:
        url = "https://pixabay.com/api/"
        params = {
            "key": api_key,
            "q": query,
            "per_page": max_results,
            "image_type": "photo",
            "min_width": target_w,
            "min_height": target_h,
            "orientation": "horizontal" if target_w > target_h else "vertical",
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for p in data.get("hits", []):
                results.append({
                    "provider": "pixabay",
                    "type": "image",
                    "url": p.get("largeImageURL", ""),
                    "width": p.get("imageWidth", 0),
                    "height": p.get("imageHeight", 0),
                    "license": "Pixabay License (free)",
                    "page_url": p.get("pageURL", ""),
                })
        except Exception as e:
            print(f"WARNING: Pixabay photo search failed: {e}", file=sys.stderr)

    return results


def search_unsplash(query: str, target_w: int, target_h: int,
                    api_key: str, max_results: int = 5) -> list[dict]:
    """Search Unsplash for photos (no video support)."""
    import requests

    results = []
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": query,
        "per_page": max_results,
        "orientation": "landscape" if target_w > target_h else "portrait",
    }
    headers = {"Authorization": f"Client-ID {api_key}"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for p in data.get("results", []):
            urls = p.get("urls", {})
            results.append({
                "provider": "unsplash",
                "type": "image",
                "url": urls.get("raw", urls.get("full", "")),
                "width": p.get("width", 0),
                "height": p.get("height", 0),
                "license": f"Unsplash License ({p.get('user', {}).get('name', 'unknown')})",
                "page_url": p.get("links", {}).get("html", ""),
            })
    except Exception as e:
        print(f"WARNING: Unsplash search failed: {e}", file=sys.stderr)

    return results


def search_all_providers(query: str, media_type: str, target_w: int, target_h: int,
                         sources: list[dict]) -> list[dict]:
    """Search all configured providers, return combined results.

    `sources` is a list of dicts: [{"provider": "pexels", "api_key": "..."}]
    """
    all_results = []
    for src in sources:
        provider = src["provider"]
        api_key = src["api_key"]

        if provider == "pexels":
            all_results.extend(search_pexels(query, media_type, target_w, target_h, api_key))
        elif provider == "pixabay":
            all_results.extend(search_pixabay(query, media_type, target_w, target_h, api_key))
        elif provider == "unsplash":
            if media_type == "video":
                print(f"  INFO: Unsplash does not support video, skipping for video scene", file=sys.stderr)
                continue
            all_results.extend(search_unsplash(query, target_w, target_h, api_key))

    return all_results


def pick_best(results: list[dict], target_w: int, target_h: int) -> dict | None:
    """Pick the result closest to (but >=) the target resolution."""
    if not results:
        return None

    def score(r):
        w, h = r.get("width", 0), r.get("height", 0)
        # Prefer results >= target; penalize those smaller
        covers = (w >= target_w and h >= target_h)
        area = w * h
        # Sort: covers first, then by area (closest to target)
        return (not covers, abs(area - target_w * target_h))

    return min(results, key=score)


def collect_stock_scenes(video_struct: dict) -> list[dict]:
    """Collect all scenes with asset_generation_method: stock."""
    scenes = []
    for story in video_struct.get("stories", []):
        story_id = story.get("id", "")
        for scene in story.get("scene_list", []):
            if scene.get("asset_generation_method") == "stock":
                narration = scene.get("narration") or {}
                scenes.append({
                    "story_id": story_id,
                    "scene_id": scene.get("id", ""),
                    "narration_id": narration.get("id", ""),
                    "visual_content": scene.get("visual_content", ""),
                    "intent": scene.get("intent", ""),
                    "type": scene.get("type", "image"),
                    "origin_asset_path": scene.get("origin_asset_path", ""),
                    "scene_ref": scene,
                })
    return scenes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search and download stock media for video_struct.yaml scenes"
    )
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--force", action="store_true", help="Re-download even if origin_asset_path exists")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config, args.video_struct)

    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)

    sources = get_configured_sources(project_config)
    if not sources:
        print(json.dumps({
            "status": "ok",
            "msg": "No stock media sources configured (stock_media.sources is empty or no valid entries)",
            "data": {"searched": 0, "downloaded": 0, "skipped": 0},
        }, ensure_ascii=False, indent=2))
        return

    target_w, target_h = get_target_dims(project_config)
    video_dir = Path(args.video_struct).parent

    scenes = collect_stock_scenes(video_struct)
    if not scenes:
        print(json.dumps({
            "status": "ok",
            "msg": "No scenes with asset_generation_method: stock",
            "data": {"searched": 0, "downloaded": 0, "skipped": 0},
        }, ensure_ascii=False, indent=2))
        return

    provider_names = [s["provider"] for s in sources]
    print(f"Stock media search: {len(scenes)} scene(s), providers={provider_names}, "
          f"target={target_w}x{target_h}", file=sys.stderr)

    from lib.net import download_file

    downloaded = 0
    skipped = 0
    errors = []
    struct_changed = False

    for s in scenes:
        scene_id = s["scene_id"]
        media_type = s["type"]  # "image" or "video"
        ext = "mp4" if media_type == "video" else "jpg"
        origin_path = video_dir / "stories" / s["story_id"] / s["narration_id"] / "scenes" / f"origin_{scene_id}.{ext}"

        # Skip if already downloaded (idempotent)
        if not args.force and s["origin_asset_path"] and Path(s["origin_asset_path"]).exists():
            skipped += 1
            print(f"  SKIP {scene_id} (already exists)", file=sys.stderr)
            continue

        # Build search query from visual_content + intent
        query = s["visual_content"] or s["intent"] or scene_id
        print(f"  Search {scene_id}: '{query[:60]}...' ({media_type})", file=sys.stderr)

        results = search_all_providers(query, media_type, target_w, target_h, sources)
        best = pick_best(results, target_w, target_h)

        if not best or not best.get("url"):
            errors.append(f"{scene_id}: no results found for '{query[:50]}'")
            print(f"    ERROR: no results", file=sys.stderr)
            continue

        # Download
        origin_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            download_file(best["url"], str(origin_path), timeout=120)
        except Exception as e:
            errors.append(f"{scene_id}: download failed: {e}")
            print(f"    ERROR: download failed: {e}", file=sys.stderr)
            continue

        downloaded += 1
        print(f"    OK: {best['provider']} {best.get('width', '?')}x{best.get('height', '?')} "
              f"-> {origin_path.name}", file=sys.stderr)

        # Update video_struct
        s["scene_ref"]["origin_asset_path"] = str(origin_path)
        if s["scene_ref"].get("asset_path", "") == "":
            # If no upscale needed (origin >= target), use origin as asset directly
            bw, bh = best.get("width", 0), best.get("height", 0)
            if bw >= target_w and bh >= target_h:
                s["scene_ref"]["asset_path"] = str(origin_path)
        struct_changed = True

    if struct_changed:
        save_yaml(video_struct, args.video_struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"Stock media search completed with {len(errors)} error(s)",
            "data": {"downloaded": downloaded, "skipped": skipped, "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"Stock media: {downloaded} downloaded, {skipped} skipped",
            "data": {"downloaded": downloaded, "skipped": skipped, "target": f"{target_w}x{target_h}"},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
