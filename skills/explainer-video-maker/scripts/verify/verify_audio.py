#!/usr/bin/env python3
"""
Verify that all scene narration audio files have been generated and that
video_struct.yaml narrations have been updated with total_frame and audio_path.

Usage:
    python verify_audio.py --video-struct /abs/path/video_struct.yaml

Exit codes: 0 = all good, 1 = errors found.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml


def verify(struct: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors = []
    warnings = []

    stories = struct.get("stories", [])
    if not stories:
        errors.append("[stories] list is empty or missing")
        return errors, warnings

    total_narrations = 0
    audio_missing = []
    frame_missing = []
    path_missing = []

    for story in stories:
        for section in story.get("section_list", []):
            narration = section.get("narration") or {}
            total_narrations += 1
            narration_id = narration.get("id", "?")

            # Check audio_path
            audio_path = narration.get("audio_path", "")
            if not audio_path:
                path_missing.append(narration_id)
            elif not Path(audio_path).exists():
                audio_missing.append({"id": narration_id, "path": audio_path})

            # Check total_frame
            total_frame = narration.get("total_frame")
            if total_frame is None or total_frame == 0:
                frame_missing.append(narration_id)
            elif not isinstance(total_frame, int) or total_frame <= 0:
                frame_missing.append(narration_id)

    if path_missing:
        errors.append(f"audio_path is empty for narration(s): {path_missing}")
    if audio_missing:
        for item in audio_missing:
            errors.append(f"Audio file not found: {item['path']} (narration: {item['id']})")
    if frame_missing:
        errors.append(f"total_frame is missing/zero for narration(s): {frame_missing}")

    if not errors and total_narrations == 0:
        warnings.append("No narration units found")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify audio generation status")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.video_struct)

    struct = load_yaml(args.video_struct)
    errors, warnings = verify(struct)

    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"Audio verification failed with {len(errors)} error(s)",
            "data": {"errors": errors, "warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    elif warnings:
        print(json.dumps({
            "status": "warning",
            "msg": f"Audio verified with {len(warnings)} warning(s)",
            "data": {"warnings": warnings},
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "All narration audio files verified",
            "data": {},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
