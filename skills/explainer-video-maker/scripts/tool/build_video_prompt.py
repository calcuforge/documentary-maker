#!/usr/bin/env python3
"""
Convert a structured video-prompt YAML (Prompt设计阶段产物) into a flat prompt
string for the ComfyUI pipeline payload in video_tasks.yaml.

Reads a scene's prompt file (video_prompt_{scene_id}.yaml, co-located with its
assets in stories/{story_id}/{narration_id}/scenes/) and outputs the flattened
prompt.

Usage:
    python build_video_prompt.py --prompt-yaml /abs/path/to/video_prompt_{scene_id}.yaml [--type text_to_video]

The --type flag overrides the video_prompt.type field in the YAML, which is
useful when a scene has BOTH text_to_video and image_to_video tasks (the agent
calls this script once per task type with the same prompt file).

Output (JSON envelope): data.prompt contains the flat prompt string, and
data.negative_prompt (if present) contains the negative-prompt list.

The structured prompt format follows this schema (see Step 9a):
    video_prompt:
      type: text_to_video | image_to_video | text_to_image
      common:
        subject:    {main, description}
        scene:      {location, environment}
        time:       {period, lighting}
        style:      {visual, color, quality}
        action:     {description}
        camera:     {shot, movement, angle}
      text_to_video:
        prompt: "<one-sentence prompt>"
        negative_prompt: ["term1", "term2", ...]
      image_to_video:
        motion:
          type: camera_and_object_motion
          camera:  {movement}
          object:  {movement}
      text_to_image:
        prompt: "<one-sentence prompt>"
        negative_prompt: ["term1", "term2", ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml


def flatten_struct(data) -> str:
    """Recursively flatten a nested dict/list into a comma-joined string."""
    parts = []
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, dict):
                parts.append(flatten_struct(value))
            elif isinstance(value, list):
                parts.append(", ".join(str(v) for v in value))
            elif value:
                parts.append(str(value))
    return ", ".join(filter(None, parts))


def build_prompt(config: dict, type_override: str | None = None) -> dict:
    """Build a flat prompt string from a structured video-prompt config."""
    video = config.get("video_prompt", {})
    video_type = type_override or video.get("type", "")
    parts = []

    # Common section
    common = video.get("common", {})
    if common:
        parts.append(flatten_struct(common))

    if video_type == "text_to_video":
        t2v = video.get("text_to_video", {})
        prompt_text = t2v.get("prompt", "")
        if prompt_text:
            parts.append(prompt_text)
        negative = t2v.get("negative_prompt", [])

    elif video_type == "text_to_image":
        t2i = video.get("text_to_image", {})
        prompt_text = t2i.get("prompt", "")
        if prompt_text:
            parts.append(prompt_text)
        negative = t2i.get("negative_prompt", [])

    elif video_type == "image_to_video":
        i2v = video.get("image_to_video", {})
        motion = i2v.get("motion", {})
        if motion:
            parts.append(flatten_struct(motion))
        negative = []

    else:
        negative = []

    # Join into a single-line prompt
    prompt = ". ".join(parts)
    prompt = prompt.replace("\n", " ").replace("\r", " ")
    prompt = " ".join(prompt.split())  # collapse whitespace

    result: dict[str, str | list[str]] = {"prompt": prompt}
    if negative:
        result["negative_prompt"] = negative
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a structured video-prompt YAML to a flat prompt string"
    )
    parser.add_argument("--prompt-yaml", required=True, help="Path to the scene's prompt.yaml (absolute)")
    parser.add_argument("--type", dest="prompt_type", default=None,
                        choices=["text_to_video", "image_to_video", "text_to_image"],
                        help="Override video_prompt.type (useful for scenes with both t2v and i2v tasks)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.prompt_yaml)

    config = load_yaml(args.prompt_yaml)
    try:
        result = build_prompt(config, type_override=args.prompt_type)
    except (KeyError, TypeError) as e:
        print(json.dumps({
            "status": "error",
            "msg": f"Malformed prompt YAML: {e}",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    effective_type = args.prompt_type or config.get("video_prompt", {}).get("type", "?")
    print(json.dumps({
        "status": "ok",
        "msg": f"Built prompt for type={effective_type}",
        "data": result,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
