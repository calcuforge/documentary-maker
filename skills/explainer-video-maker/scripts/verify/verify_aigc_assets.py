#!/usr/bin/env python3
"""
Verify that all externally-acquired assets (AIGC and stock) are present on disk.

Checks scenes where is_aigc_scene=true (both asset_generation_method=aigc and
asset_generation_method=stock):
- origin_asset_path must be set and the file must exist (non-zero)
- Optionally checks asset_path (upscaled) with --check-upscaled

Usage:
    python verify_aigc_assets.py --video-struct /abs/path/video_struct.yaml
    python verify_aigc_assets.py --video-struct /abs/path/video_struct.yaml --check-upscaled

Exit codes: 0 = all assets present, 1 = missing assets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml


def verify(struct: dict, check_upscaled: bool = False) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    stories = struct.get("stories", [])
    total_aigc = 0
    origin_missing = []
    upscaled_missing = []

    for story in stories:
        for section in story.get("section_list", []):
            for scene in section.get("scene_list", []):
                media_list = scene.get("media_list") or []
                if media_list:
                    # MediaSection scenes: verify aigc items only (stock items are
                    # covered by verify_stock_assets.py); the scene itself is not
                    # an asset holder.
                    refs = [item for item in media_list
                            if item.get("asset_generation_method") == "aigc"]
                else:
                    refs = [scene] if scene.get("is_aigc_scene", False) else []

                for ref in refs:
                    total_aigc += 1
                    label = ref.get("id") or scene.get("id", "?")

                    # Check origin_asset_path
                    origin_path = ref.get("origin_asset_path", "")
                    if not origin_path:
                        origin_missing.append(f"{label}: origin_asset_path is empty")
                    elif not Path(origin_path).exists():
                        origin_missing.append(f"{label}: file not found: {origin_path}")
                    elif Path(origin_path).stat().st_size == 0:
                        origin_missing.append(f"{label}: file is empty: {origin_path}")

                    # Check upscaled asset_path
                    if check_upscaled:
                        asset_path = ref.get("asset_path", "")
                        if not asset_path:
                            upscaled_missing.append(f"{label}: asset_path is empty")
                        elif not Path(asset_path).exists():
                            upscaled_missing.append(f"{label}: upscaled file not found: {asset_path}")
                        elif Path(asset_path).stat().st_size == 0:
                            upscaled_missing.append(f"{label}: upscaled file is empty: {asset_path}")

    if origin_missing:
        errors.append(f"Missing origin assets ({len(origin_missing)}/{total_aigc}):")
        errors.extend(f"  - {m}" for m in origin_missing)

    if check_upscaled and upscaled_missing:
        errors.append(f"Missing upscaled assets ({len(upscaled_missing)}/{total_aigc}):")
        errors.extend(f"  - {m}" for m in upscaled_missing)

    if total_aigc == 0:
        warnings.append("No AIGC scenes found in video_struct.yaml")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify AIGC asset files")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--check-upscaled", action="store_true", help="Also verify asset_path (upscaled)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    struct = load_yaml(args.video_struct)
    errors, warnings = verify(struct, check_upscaled=args.check_upscaled)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"AIGC asset verification failed",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"AIGC assets verified with warnings",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "All AIGC assets verified",
            "data": {},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
