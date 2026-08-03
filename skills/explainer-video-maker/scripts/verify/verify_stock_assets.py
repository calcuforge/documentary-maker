#!/usr/bin/env python3
"""
Verify that all stock-media scenes have downloaded assets.

Checks scenes where asset_generation_method == "stock":
- origin_asset_path must be non-empty and the file must exist (non-zero)
- Optionally checks asset_path (upscaled) with --check-upscaled

Usage:
    python verify_stock_assets.py --video-struct /abs/path/video_struct.yaml
    python verify_stock_assets.py --video-struct /abs/path/video_struct.yaml --check-upscaled

Exit codes: 0 = all present, 1 = missing, 2 = warnings only.
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
    total_stock = 0
    origin_missing = []
    upscaled_missing = []

    for story in stories:
        for section in story.get("section_list", []):
            for scene in section.get("scene_list", []):
                media_list = scene.get("media_list") or []
                if media_list:
                    refs = [item for item in media_list
                            if item.get("asset_generation_method") == "stock"]
                else:
                    refs = [scene] if scene.get("asset_generation_method") == "stock" else []

                for ref in refs:
                    total_stock += 1
                    label = ref.get("id") or scene.get("id", "?")

                    origin_path = ref.get("origin_asset_path", "")
                    if not origin_path:
                        origin_missing.append(f"{label}: origin_asset_path is empty")
                    elif not Path(origin_path).exists():
                        origin_missing.append(f"{label}: file not found: {origin_path}")
                    elif Path(origin_path).stat().st_size == 0:
                        origin_missing.append(f"{label}: file is empty: {origin_path}")

                    if check_upscaled:
                        asset_path = ref.get("asset_path", "")
                        if not asset_path:
                            upscaled_missing.append(f"{label}: asset_path is empty")
                        elif not Path(asset_path).exists():
                            upscaled_missing.append(f"{label}: upscaled file not found: {asset_path}")
                        elif Path(asset_path).stat().st_size == 0:
                            upscaled_missing.append(f"{label}: upscaled file is empty: {asset_path}")

    if origin_missing:
        errors.append(f"Missing stock assets ({len(origin_missing)}/{total_stock}):")
        errors.extend(f"  - {m}" for m in origin_missing)

    if check_upscaled and upscaled_missing:
        errors.append(f"Missing upscaled stock assets ({len(upscaled_missing)}/{total_stock}):")
        errors.extend(f"  - {m}" for m in upscaled_missing)

    if total_stock == 0:
        warnings.append("No stock-media scenes found in video_struct.yaml")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify stock-media asset files")
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
            "msg": "Stock asset verification failed",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": "Stock assets verified with warnings",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "All stock assets verified",
            "data": {},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
