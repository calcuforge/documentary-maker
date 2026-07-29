#!/usr/bin/env python3
"""
TTS synthesis + frame count calculation.

Reads video_struct.yaml, generates speech audio for each narration unit using
the configured TTS backend (comfyui_indextts or http_server), then uses ffprobe
to measure audio duration and calculates total_frame for each narration unit.

Updates video_struct.yaml with audio_path and total_frame fields.

Usage:
    python run_tts.py --project-config /abs/path/project_config.yaml --video-struct /abs/path/video_struct.yaml

The project_config.yaml tts.backend field selects the backend:
    - comfyui_indextts: uses comfyui-scheduler run -w index_tts_2
    - http_server: POST multipart to tts.http.url
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse ffprobe output for {audio_path}: {e}")


def duration_to_frames(duration_sec: float, fps: int) -> int:
    """Convert duration in seconds to frame count."""
    return math.ceil(duration_sec * fps)


def synth_comfyui_indextts(
    content: str,
    voice_file: str,
    output_path: str,
    speed: float = 1.0,
) -> str:
    """Generate speech using comfyui-scheduler index_tts_2 workflow.

    Returns the output audio file path.
    """
    inputs = json.dumps({
        "content": content,
        "voice_file": voice_file,
    }, ensure_ascii=False)

    cmd = ["comfyui-scheduler", "run", "-w", "index_tts_2", "-i", inputs]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"TTS timed out for: {content[:50]}...")
    except FileNotFoundError:
        raise RuntimeError("comfyui-scheduler not found on PATH")

    if result.returncode != 0:
        raise RuntimeError(f"comfyui-scheduler failed: {result.stderr or result.stdout}")

    # Parse output JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON from comfyui-scheduler: {result.stdout[:200]}")

    if output.get("status") != "ok":
        raise RuntimeError(f"TTS error: {output.get('msg', 'unknown')}")

    files = output.get("data", {}).get("files", [])
    if not files:
        raise RuntimeError("No output files from TTS")

    # Download the output file
    file_url = files[0].get("url", "")
    if not file_url:
        raise RuntimeError("No URL in TTS output file")

    # Download via requests
    import requests
    resp = requests.get(file_url, timeout=60)
    resp.raise_for_status()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    return output_path


def synth_http_server(
    content: str,
    voice_file: str,
    output_path: str,
    url: str,
    speed: float = 1.0,
    headers: dict | None = None,
) -> str:
    """Generate speech using HTTP multipart TTS server.

    Protocol: POST multipart/form-data
        Fields: input (text), speed (float str), voice_file (file upload)
        Response: raw audio bytes
    """
    import requests

    # Expand environment variables in URL
    resolved_url = os.path.expandvars(url)

    with open(voice_file, "rb") as vf:
        files = {"voice_file": (os.path.basename(voice_file), vf, "audio/wav")}
        data = {
            "input": content,
            "speed": str(speed),
        }
        req_headers = headers or {}
        resp = requests.post(resolved_url, data=data, files=files, headers=req_headers, timeout=120)

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP TTS server error ({resp.status_code}): {resp.text[:200]}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    return output_path


def collect_narration_units(video_struct: dict) -> list[dict]:
    """Collect all narration units with their context from video_struct."""
    units = []
    for story in video_struct.get("stories", []):
        story_id = story.get("id", "")
        for narration in story.get("narration_list", []):
            units.append({
                "story_id": story_id,
                "narration_id": narration.get("id", ""),
                "content": narration.get("content", ""),
                "audio_path": narration.get("audio_path", ""),
                "narration_ref": narration,  # reference for in-place update
            })
    return units


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TTS synthesis and calculate frames")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml")
    parser.add_argument("--workers", type=int, default=3, help="Concurrent TTS workers")
    parser.add_argument("--force", action="store_true", help="Re-generate even if audio exists")
    args = parser.parse_args()

    # Load configs
    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)

    tts_config = project_config.get("tts", {})
    backend = tts_config.get("backend", "comfyui_indextts")
    speed = tts_config.get("speed", 1.0)
    fps = project_config.get("video", {}).get("fps", 24)

    # Resolve voice file
    voice_file = tts_config.get("voice_file", "")
    if not voice_file:
        # Auto-resolve: projects/{name}/voice_file.wav
        project_root = project_config.get("project", {}).get("project_root_path", "")
        if project_root:
            candidate = Path(project_root) / "voice_file.wav"
            if candidate.exists():
                voice_file = str(candidate)
    if not voice_file or not Path(voice_file).exists():
        print(json.dumps({
            "status": "error",
            "msg": f"Voice reference file not found: '{voice_file}'. Set tts.voice_file in project_config.yaml",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # HTTP server config
    http_config = tts_config.get("http", {})
    http_url = http_config.get("url", "")
    http_headers = {}
    # Support env var headers
    if "Host-User-ID" in os.environ:
        http_headers["Host-User-ID"] = os.environ["Host-User-ID"]
    if "Host-User-Token" in os.environ:
        http_headers["Host-User-Token"] = os.environ["Host-User-Token"]

    # Collect narration units
    units = collect_narration_units(video_struct)
    if not units:
        print(json.dumps({"status": "error", "msg": "No narration units found in video_struct.yaml", "data": {}}, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Determine output directory: same as video_struct, stories/{story_id}/{narration_id}/
    video_dir = Path(args.video_struct).parent

    # Filter units that need generation
    to_generate = []
    for u in units:
        audio_path = u["audio_path"]
        if not args.force and audio_path and Path(audio_path).exists():
            continue  # Skip existing
        # Output path: video_dir/stories/{story_id}/{narration_id}/speech.wav
        out_dir = video_dir / "stories" / u["story_id"] / u["narration_id"]
        out_path = str(out_dir / "speech.wav")
        u["output_path"] = out_path
        to_generate.append(u)

    # Generate audio
    errors = []
    generated = 0

    def generate_one(unit: dict) -> dict:
        """Generate TTS for a single narration unit."""
        try:
            if backend == "comfyui_indextts":
                synth_comfyui_indextts(
                    content=unit["content"],
                    voice_file=voice_file,
                    output_path=unit["output_path"],
                    speed=speed,
                )
            elif backend == "http_server":
                synth_http_server(
                    content=unit["content"],
                    voice_file=voice_file,
                    output_path=unit["output_path"],
                    url=http_url,
                    speed=http_config.get("speed", speed),
                    headers=http_headers,
                )
            else:
                raise RuntimeError(f"Unknown TTS backend: {backend}")
            return {"unit": unit, "error": None}
        except Exception as e:
            return {"unit": unit, "error": str(e)}

    if to_generate:
        print(f"Generating TTS for {len(to_generate)} narration unit(s) using backend: {backend}", file=sys.stderr)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(generate_one, u): u for u in to_generate}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result["error"]:
                    errors.append({"narration_id": result["unit"]["narration_id"], "error": result["error"]})
                else:
                    generated += 1

    # Calculate frames and update video_struct
    updated_count = 0
    for u in units:
        audio_path = u.get("output_path", u["audio_path"])
        if audio_path and Path(audio_path).exists():
            try:
                duration = get_audio_duration(audio_path)
                total_frame = duration_to_frames(duration, fps)
                # Update in-place
                u["narration_ref"]["audio_path"] = audio_path
                u["narration_ref"]["total_frame"] = total_frame
                updated_count += 1
            except Exception as e:
                errors.append({"narration_id": u["narration_id"], "error": f"ffprobe: {e}"})

    # Save updated video_struct
    save_yaml(video_struct, args.video_struct)

    # Report
    if errors:
        print(json.dumps({
            "status": "error",
            "msg": f"TTS completed with {len(errors)} error(s)",
            "data": {"generated": generated, "updated": updated_count, "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"TTS complete: {generated} generated, {updated_count} updated with frame counts",
            "data": {"generated": generated, "updated": updated_count, "fps": fps},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
