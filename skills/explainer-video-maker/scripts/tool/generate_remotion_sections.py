#!/usr/bin/env python3
"""
Generate remotion_sections.yaml from project_config.yaml and video_struct.yaml.

Creates the rendering configuration that drives remotion-video-template.
The remotion_data field is left empty — the agent fills it based on the
component requirements (see remotion-video-template README.md).

Usage:
    python generate_remotion_sections.py \
        --project-config /abs/path/project_config.yaml \
        --video-struct /abs/path/video_struct.yaml \
        --output /abs/path/remotion_sections.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml


def split_text_to_sentences(text: str) -> list[str]:
    """Split narration text into sentence-level chunks for subtitles."""
    import re
    # Split on Chinese/English sentence boundaries
    parts = re.split(r'(?<=[。！？；\.\!\?;])\s*', text)
    sentences = [s.strip() for s in parts if s.strip()]
    # Merge very short fragments (< 8 chars) with the previous sentence
    merged = []
    for s in sentences:
        if merged and len(s) < 8:
            merged[-1] += s
        else:
            merged.append(s)
    # If only one long sentence, split by comma
    if len(merged) == 1 and len(merged[0]) > 60:
        parts = re.split(r'(?<=[，,、])\s*', merged[0])
        merged = [p.strip() for p in parts if p.strip()]
    return merged if merged else [text]


def build_subtitle_list(video_struct: dict, fps: int) -> list[dict]:
    """Build subtitle list from narration content, split by sentence."""
    subtitles = []
    current_frame = 1

    for story in video_struct.get("stories", []):
        for narration in story.get("narration_list", []):
            total_frame = narration.get("total_frame", 0)
            content = narration.get("content", "")
            if total_frame > 0 and content:
                sentences = split_text_to_sentences(content)
                # Distribute frames proportionally by character count
                total_chars = sum(len(s) for s in sentences)
                frame_cursor = current_frame
                for sent in sentences:
                    sent_frames = max(1, round(total_frame * len(sent) / total_chars))
                    subtitles.append({
                        "text": sent,
                        "start_frame": frame_cursor,
                        "end_frame": frame_cursor + sent_frames - 1,
                    })
                    frame_cursor += sent_frames
            current_frame += total_frame

    return subtitles


def _to_relative(path: str, video_dir: str) -> str:
    """Convert a path to be relative to video_dir (for Remotion public-dir).

    If the path is already relative, return as-is.
    If absolute, try to make it relative to video_dir.
    """
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        return str(p)
    try:
        return str(p.relative_to(video_dir))
    except ValueError:
        # Path is outside video_dir — return as-is (Remotion may still resolve it)
        return str(p)


def build_stories(video_struct: dict, video_dir: str) -> list[dict]:
    """Build the stories/sections structure for remotion_sections.yaml.

    All paths (audio, assets) are relative to video_dir (--public-dir).
    Audio is only attached to the FIRST section of each narration to
    prevent duplicate playback.
    """
    stories_out = []

    for story in video_struct.get("stories", []):
        story_id = story.get("id", "")
        story_name = story.get("name", "")
        section_list = []

        for narration in story.get("narration_list", []):
            narration_id = narration.get("id", "")
            total_frame = narration.get("total_frame", 0)
            audio_path = narration.get("audio_path", "")

            # Convert audio path to relative (for Remotion public-dir)
            audio_rel = _to_relative(audio_path, video_dir)

            is_first_section_in_narration = True

            for scene in narration.get("scene_list", []):
                scene_id = scene.get("id", "")
                percent = scene.get("percent", 100)
                component = scene.get("remotion_component", "")

                # Calculate section frames from percent
                section_frames = max(1, round(total_frame * percent / 100))

                # Audio: only first section per narration carries the audio
                section_audio = audio_rel if is_first_section_in_narration else ""
                is_first_section_in_narration = False

                # Build remotion_data
                asset_path = scene.get("asset_path", "")
                data_content = scene.get("data", "")
                text_content = scene.get("text", "")

                remotion_data = {}
                if component in ("AssetVideo", "AssetImage"):
                    # Asset src relative to public-dir
                    raw_src = asset_path if asset_path else scene.get("origin_asset_path", "")
                    remotion_data = {"src": _to_relative(raw_src, video_dir), "role": "background"}
                elif data_content:
                    try:
                        remotion_data = json.loads(data_content) if isinstance(data_content, str) else data_content
                    except (json.JSONDecodeError, TypeError):
                        remotion_data = {"content": str(data_content)}
                elif text_content:
                    remotion_data = {"text": text_content}

                section = {
                    "total_frame": section_frames,
                    "remotion_component": component,
                    "remotion_data": json.dumps(remotion_data, ensure_ascii=False) if remotion_data else "{}",
                    "audio": section_audio,
                    "scene_id": scene_id,
                }
                section_list.append(section)

        stories_out.append({
            "story_name": story_name,
            "story_id": story_id,
            "section_list": section_list,
        })

    return stories_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate remotion_sections.yaml")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml")
    parser.add_argument("--output", required=True, help="Output remotion_sections.yaml path")
    args = parser.parse_args()

    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)

    video_cfg = project_config.get("video", {})
    theme_cfg = project_config.get("theme", {})
    subtitle_cfg = project_config.get("subtitle", {})

    fps = video_cfg.get("fps", 24)
    resolution = video_cfg.get("resolution", "1080p")
    orientation = video_cfg.get("orientation", "horizontal")

    # Map resolution to remotion format
    resolution_map = {"1080p": "1080P", "4k": "4K"}
    resolution_out = resolution_map.get(resolution.lower(), "1080P")

    video_dir = str(Path(args.video_struct).parent)

    # Build sections
    stories = build_stories(video_struct, video_dir)
    subtitle_list = build_subtitle_list(video_struct, fps)

    # Assemble remotion_sections.yaml
    remotion_sections = {
        "resolution": resolution_out,
        "orientation": orientation,
        "fps": float(fps),
        "theme": {
            "primary_color": theme_cfg.get("primary_color", "#4f6ef7"),
            "background_color": theme_cfg.get("background_color", "#ffffff"),
            "text_color": theme_cfg.get("text_color", "#1a1a1a"),
            "accent_color": theme_cfg.get("accent_color", "#FF6B6B"),
            "transition_type": theme_cfg.get("transition_type", "fade"),
            "transition_duration": float(theme_cfg.get("transition_duration", 12)),
        },
        "subtitle": {
            "font_size": subtitle_cfg.get("font_size", 20),
            "primary_color": subtitle_cfg.get("primary_color", "&H00333333"),
            "outline_color": subtitle_cfg.get("outline_color", "&H00FFFFFF"),
            "outline": subtitle_cfg.get("outline", 2),
            "alignment": subtitle_cfg.get("alignment", 2),
            "marginV": subtitle_cfg.get("marginV", 6),
            "list": subtitle_list,
        },
        "stories": stories,
    }

    # Save
    save_yaml(remotion_sections, args.output)

    # Count sections
    total_sections = sum(len(s.get("section_list", [])) for s in stories)
    print(json.dumps({
        "status": "ok",
        "msg": f"Generated remotion_sections.yaml with {len(stories)} stories, {total_sections} sections",
        "data": {
            "output": str(Path(args.output).resolve()),
            "stories": len(stories),
            "sections": total_sections,
            "subtitles": len(subtitle_list),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
