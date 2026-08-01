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
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml


def build_subtitle_list(video_struct: dict) -> list[dict]:
    """Build subtitle list with one entry per scene (1:1 with scene_list).

    Each scene carries exactly one narration; the subtitle text is the full
    narration content and the frame span covers the whole scene. Iteration
    order matches build_stories, so subtitle.list aligns one-to-one with the
    flattened scene_list across all stories/sections.
    """
    subtitles = []
    current_frame = 1

    for story in video_struct.get("stories", []):
        for scene in story.get("scene_list", []):
            narration = scene.get("narration") or {}
            total_frame = narration.get("total_frame", 0)
            content = narration.get("content", "")
            # Scene owns its whole narration duration (min 1 frame, matches build_stories)
            scene_frames = max(1, total_frame)
            subtitles.append({
                "text": content,
                "start_frame": current_frame,
                "end_frame": current_frame + scene_frames - 1,
            })
            current_frame += scene_frames

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


def build_bgm_block(project_config: dict, video_dir: str) -> dict | None:
    """Build the top-level `bgm` block for remotion_sections.yaml.

    Copies the project-level BGM file into the video directory (the Remotion
    --public-dir) so it can be referenced via staticFile("bgm.mp3"). Returns
    None when BGM is disabled or the file does not exist.
    """
    bgm = project_config.get("bgm", {})
    if not bgm.get("enabled", True):
        return None

    audio = bgm.get("audio", "")
    if not audio:
        return None
    src = Path(audio)
    # A relative bgm.audio resolves against the project root (run_bgm.py writes
    # an absolute path, but a hand-edited config may use a project-relative one).
    if not src.is_absolute():
        project_root = project_config.get("project", {}).get("project_root_path", "")
        if project_root:
            src = Path(project_root) / src
    if not src.exists():
        return None

    dest = Path(video_dir) / "bgm.mp3"
    if src.resolve() != dest.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    return {
        "audio": "bgm.mp3",
        "volume": float(bgm.get("volume", 0.1)),
        "loop": bool(bgm.get("loop", True)),
    }


def build_stories(video_struct: dict, video_dir: str) -> list[dict]:
    """Build the stories/sections structure for remotion_sections.yaml.

    Each scene carries exactly one narration, so every section_list entry
    corresponds to a single scene and its narration:
      section_list[]:
        - audio: path/to/speech.wav    # the scene's narration audio
          scene_list[]:                 # a single visual scene
            - remotion_component, remotion_data, total_frame, scene_id

    A scene occupies its whole narration duration (total_frame = narration.total_frame).
    All paths are relative to video_dir (--public-dir).
    """
    stories_out = []

    for story in video_struct.get("stories", []):
        story_id = story.get("id", "")
        story_name = story.get("name", "")
        section_list = []

        for scene in story.get("scene_list", []):
            narration = scene.get("narration") or {}
            total_frame = narration.get("total_frame", 0)
            audio_path = narration.get("audio_path", "")
            audio_rel = _to_relative(audio_path, video_dir)

            scene_id = scene.get("id", "")
            component = scene.get("remotion_component", "")

            # The scene owns its entire narration duration
            scene_frames = max(1, total_frame)

            # Build remotion_data
            asset_path = scene.get("asset_path", "")
            data_content = scene.get("data", "")
            text_content = scene.get("text", "")

            remotion_data = {}
            if component in ("AssetVideo", "AssetImage", "KenBurnsImage"):
                raw_src = asset_path if asset_path else scene.get("origin_asset_path", "")
                remotion_data = {"src": _to_relative(raw_src, video_dir), "role": "background", "totalFrame": scene_frames}
            elif data_content:
                try:
                    remotion_data = json.loads(data_content) if isinstance(data_content, str) else data_content
                except (json.JSONDecodeError, TypeError):
                    remotion_data = {"content": str(data_content)}
            elif text_content:
                remotion_data = {"text": text_content}

            scene_list_out = [{
                "remotion_component": component,
                "remotion_data": json.dumps(remotion_data, ensure_ascii=False) if remotion_data else "{}",
                "total_frame": scene_frames,
                "scene_id": scene_id,
            }]

            section_list.append({
                "audio": audio_rel,
                "scene_list": scene_list_out,
            })

        stories_out.append({
            "story_name": story_name,
            "story_id": story_id,
            "section_list": section_list,
        })

    return stories_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate remotion_sections.yaml")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--output", required=True, help="Output remotion_sections.yaml path (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config, args.video_struct, args.output)

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
    subtitle_list = build_subtitle_list(video_struct)

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
            "font_size": subtitle_cfg.get("font_size", 26),
            "primary_color": subtitle_cfg.get("primary_color", "&H00333333"),
            "outline_color": subtitle_cfg.get("outline_color", "&H00FFFFFF"),
            "outline": subtitle_cfg.get("outline", 2),
            "alignment": subtitle_cfg.get("alignment", 2),
            "marginV": subtitle_cfg.get("marginV", 6),
            "list": subtitle_list,
        },
        "stories": stories,
    }

    # Optional background music (copied into the video dir by build_bgm_block)
    bgm_block = build_bgm_block(project_config, video_dir)
    if bgm_block:
        remotion_sections["bgm"] = bgm_block

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
