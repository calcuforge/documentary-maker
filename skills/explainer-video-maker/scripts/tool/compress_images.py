#!/usr/bin/env python3
"""
Compress all image assets in video_struct.yaml to JPEG quality 95.

Walks every scene's asset_path and origin_asset_path, converts non-JPEG image
files (.png / .webp / .bmp / .tiff / .tif) to JPEG via ffmpeg, updates the
YAML references, and deletes the original files.

Video files (.mp4 / .mov / .avi / .webm / .mkv) are left untouched — they were
already compressed with h264 crf 18 during upscale (Step 10.2).

Run BEFORE generate_remotion_sections.py (Step 12) so the Remotion config picks
up the compressed .jpg paths.

Usage:
    python compress_images.py --video-struct /abs/path/video_struct.yaml
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml

# File categories by extension
SKIP_EXTS = {".jpg", ".jpeg"}       # already JPEG — nothing to do
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".wmv"}

# ffmpeg -q:v scale: 1 (best) … 31 (worst).  2 ≈ JPEG quality 95.
DEFAULT_QUALITY = 2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compress all image assets to JPEG via ffmpeg"
    )
    parser.add_argument("--video-struct", required=True,
                        help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY,
                        help=f"ffmpeg -q:v value (1-31, lower=better. Default {DEFAULT_QUALITY})")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    video_struct = load_yaml(args.video_struct)

    converted = 0
    skipped = 0
    deleted = 0
    errors = []

    for story in video_struct.get("stories", []):
        for scene in story.get("scene_list", []):
            for field in ("asset_path", "origin_asset_path"):
                path_str = scene.get(field, "")
                if not path_str:
                    continue

                path = Path(path_str)
                if not path.exists():
                    continue

                ext = path.suffix.lower()
                if ext in SKIP_EXTS:
                    continue
                if ext in VIDEO_EXTS:
                    continue
                if ext not in {".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}:
                    continue

                jpg_path = path.with_suffix(".jpg")

                # Idempotent: skip if the JPEG already exists and is non-empty
                if jpg_path.exists() and jpg_path.stat().st_size > 0:
                    skipped += 1
                    continue

                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(path),
                     "-q:v", str(args.quality), str(jpg_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout or "").strip()
                    errors.append({
                        "scene_id": scene.get("id", "?"),
                        "field": field,
                        "source": str(path),
                        "error": detail[:300],
                    })
                    continue

                # Update the YAML reference to point at the JPEG
                scene[field] = str(jpg_path)

                # Remove the original (now replaced by the JPEG).
                # Guard with exists() — another scene may have shared the same
                # source file and already deleted it.
                if path.resolve() != jpg_path.resolve() and path.exists():
                    path.unlink()
                    deleted += 1

                converted += 1

    if converted or deleted:
        save_yaml(video_struct, args.video_struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"Image compression completed with {len(errors)} error(s) "
                   f"({converted} converted, {skipped} skipped, {deleted} originals deleted)",
            "data": {"converted": converted, "skipped": skipped, "deleted": deleted,
                     "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"Image compression complete: {converted} converted, "
                   f"{skipped} skipped, {deleted} originals deleted",
            "data": {"converted": converted, "skipped": skipped, "deleted": deleted},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
