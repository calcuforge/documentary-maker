#!/usr/bin/env python3
"""
Generate remotion_sections.yaml from project_config.yaml and video_struct.yaml.

Creates the rendering configuration that drives remotion-video-template.
The remotion_data field is left empty — the agent fills it based on the
component requirements (see remotion-video-template README.md).

Each section_list entry corresponds to ONE narration (its audio + volume) and
that narration's 1-N scenes. Every scene's total_frame is the percentage share
of the narration's total_frame (largest-remainder, so Σ scene frames ==
narration total_frame). subtitle.list is aligned to the narration's scenes: the
narration text is split into short chunks (sentence-first, char fallback) and
distributed across the scenes; each entry carries a flat `scene_index` that
YamlVideo.js uses for transition compensation.

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

from lib.scene_frames import largest_remainder, scene_frame_allocation, split_narration_chunks
from lib.yamlutil import load_yaml, save_yaml


def build_subtitle_list(video_struct: dict) -> list[dict]:
    """Build subtitle entries aligned with each narration's 1-N scenes.

    Per narration (section): the content is split into short chunks
    (sentence-first, char fallback); chunks are distributed across the scenes by
    frame share. Every entry carries `scene_index` — the scene's flat index
    (story → section → scene order, matching YamlVideo.flattenStories) used for
    transition compensation. A scene that receives no chunks gets no subtitle.
    """
    subtitles = []
    current_frame = 1
    flat_scene_index = 0

    for story in video_struct.get("stories", []):
        for section in story.get("section_list", []):
            narration = section.get("narration") or {}
            content = narration.get("content", "")
            total_frame = narration.get("total_frame", 0)
            scenes = section.get("scene_list", [])
            percents = [s.get("percentage", 100) for s in scenes]
            frames = scene_frame_allocation(int(total_frame or 0), percents)
            chunks = split_narration_chunks(content)

            if not chunks:
                current_frame += sum(frames)
                flat_scene_index += len(frames)
                continue

            # Chunk count per scene, proportional to frame share.
            counts = largest_remainder(len(chunks), frames)
            ci = 0
            for f, k in zip(frames, counts):
                scene_chunks = chunks[ci:ci + k]
                ci += k
                if scene_chunks:
                    spans = largest_remainder(f, [len(c) for c in scene_chunks])
                    for span, ch in zip(spans, scene_chunks):
                        span = max(1, span)
                        subtitles.append({
                            "text": ch,
                            "start_frame": current_frame,
                            "end_frame": current_frame + span - 1,
                            "scene_index": flat_scene_index,
                        })
                        current_frame += span
                else:
                    current_frame += f
                flat_scene_index += 1

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


def build_stories(video_struct: dict, video_dir: str, narration_volume: float = 1.0) -> list[dict]:
    """Build the stories/sections structure for remotion_sections.yaml.

    Each section_list entry corresponds to ONE narration (audio + volume) and
    its 1-N scenes. Each scene's total_frame is the percentage share of the
    narration's total_frame (largest-remainder, Σ scene frames == narration
    total_frame). All paths are relative to video_dir (--public-dir).
    """
    stories_out = []

    for story in video_struct.get("stories", []):
        story_id = story.get("id", "")
        story_name = story.get("name", "")
        section_list = []

        for section in story.get("section_list", []):
            narration = section.get("narration") or {}
            total_frame = narration.get("total_frame", 0)
            audio_path = narration.get("audio_path", "")
            audio_rel = _to_relative(audio_path, video_dir)

            scenes = section.get("scene_list", [])
            percents = [s.get("percentage", 100) for s in scenes]
            frames = scene_frame_allocation(int(total_frame or 0), percents)

            scene_list_out = []
            for scene, f in zip(scenes, frames):
                scene_id = scene.get("id", "")
                component = scene.get("remotion_component", "")

                # Build remotion_data
                asset_path = scene.get("asset_path", "")
                data_content = scene.get("data", "")
                text_content = scene.get("text", "")

                remotion_data = {}
                if component == "MediaSection":
                    items = []
                    for item in scene.get("media_list", []):
                        raw_src = item.get("asset_path") or item.get("origin_asset_path", "")
                        if not raw_src:
                            continue
                        items.append({
                            "src": _to_relative(raw_src, video_dir),
                            "alt": item.get("visual_content", ""),
                            "caption": item.get("caption", "") or None,
                        })
                    remotion_data = {"items": items}
                    if text_content:
                        remotion_data["text"] = text_content
                    if data_content:
                        try:
                            remotion_data["data"] = json.loads(data_content) if isinstance(data_content, str) else data_content
                        except (json.JSONDecodeError, TypeError):
                            remotion_data["data"] = []
                elif component in ("AssetVideo", "AssetImage", "KenBurnsImage"):
                    raw_src = asset_path if asset_path else scene.get("origin_asset_path", "")
                    remotion_data = {"src": _to_relative(raw_src, video_dir), "role": "background", "totalFrame": f}
                elif data_content:
                    try:
                        remotion_data = json.loads(data_content) if isinstance(data_content, str) else data_content
                    except (json.JSONDecodeError, TypeError):
                        remotion_data = {"content": str(data_content)}
                elif text_content:
                    remotion_data = {"text": text_content}

                scene_list_out.append({
                    "remotion_component": component,
                    "remotion_data": json.dumps(remotion_data, ensure_ascii=False) if remotion_data else "{}",
                    "total_frame": f,
                    "scene_id": scene_id,
                })

            section_list.append({
                "audio": audio_rel,
                "volume": narration_volume,
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
    tts_cfg = project_config.get("tts", {})
    render_cfg = project_config.get("render", {})

    fps = video_cfg.get("fps", 24)
    resolution = video_cfg.get("resolution", "1080p")
    orientation = video_cfg.get("orientation", "horizontal")

    # Map resolution to remotion format
    resolution_map = {"1080p": "1080P", "4k": "4K"}
    resolution_out = resolution_map.get(resolution.lower(), "1080P")

    video_dir = str(Path(args.video_struct).parent)

    # Build sections
    narration_volume = float(tts_cfg.get("volume", 1.0))
    stories = build_stories(video_struct, video_dir, narration_volume)
    subtitle_list = build_subtitle_list(video_struct)

    # Assemble remotion_sections.yaml
    remotion_sections = {
        "resolution": resolution_out,
        "orientation": orientation,
        "fps": float(fps),
        "codec": render_cfg.get("codec", "h264"),
        "crf": int(render_cfg.get("crf", 23)),
        "timeout_ms": int(render_cfg.get("timeout_ms", 60000)),
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
    total_scenes = sum(
        len(sec.get("scene_list", []))
        for s in stories for sec in s.get("section_list", [])
    )
    print(json.dumps({
        "status": "ok",
        "msg": f"Generated remotion_sections.yaml with {len(stories)} stories, "
               f"{total_sections} sections, {total_scenes} scenes",
        "data": {
            "output": str(Path(args.output).resolve()),
            "stories": len(stories),
            "sections": total_sections,
            "scenes": total_scenes,
            "subtitles": len(subtitle_list),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
