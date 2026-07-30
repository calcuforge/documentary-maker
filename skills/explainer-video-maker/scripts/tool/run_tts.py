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
    timeout: int = 3600,
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"TTS timed out after {timeout}s for: {content[:50]}...")
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

    # Download the output file (supports http:// and file:// URLs)
    file_url = files[0].get("url", "")
    if not file_url:
        raise RuntimeError("No URL in TTS output file")

    from lib.net import download_file
    download_file(file_url, output_path, timeout=60)

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


def _run_voice_design(voice_instruct: str, output_path: str, timeout: int = 3600) -> str:
    """Generate a reference voice via ominivoice_voice_design workflow.

    Returns the output audio file path.
    """
    content = "这是一个语音参考样本，用于确定解说视频的旁白音色。" if "男" in voice_instruct or "女" in voice_instruct else \
              "This is a voice reference sample for narration."

    inputs = json.dumps({
        "voice_instruct": voice_instruct,
        "content": content,
    }, ensure_ascii=False)

    cmd = ["comfyui-scheduler", "run", "-w", "ominivoice_voice_design", "-i", inputs]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Voice design timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError("comfyui-scheduler not found on PATH")

    if result.returncode != 0:
        raise RuntimeError(f"Voice design failed: {result.stderr or result.stdout[:300]}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON from voice design: {result.stdout[:200]}")

    if output.get("status") != "ok":
        raise RuntimeError(f"Voice design error: {output.get('msg', 'unknown')}")

    files = output.get("data", {}).get("files", [])
    if not files:
        raise RuntimeError("No output files from voice design")

    file_url = files[0].get("url", "")
    if not file_url:
        raise RuntimeError("No URL in voice design output")

    from lib.net import download_file
    download_file(file_url, output_path)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TTS synthesis and calculate frames")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--video-struct", required=True, help="Path to video_struct.yaml (absolute)")
    parser.add_argument("--workers", type=int, default=3, help="Concurrent TTS workers")
    parser.add_argument("--timeout", type=int, default=3600, help="Per-TTS subprocess timeout in seconds (default 1h)")
    parser.add_argument("--force", action="store_true", help="Re-generate even if audio exists")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config, args.video_struct)

    # Load configs
    project_config = load_yaml(args.project_config)
    video_struct = load_yaml(args.video_struct)

    tts_timeout = args.timeout
    tts_config = project_config.get("tts", {})
    backend = tts_config.get("backend", "comfyui_indextts")
    speed = tts_config.get("speed", 1.0)
    fps = project_config.get("video", {}).get("fps", 24)

    # Resolve voice file — auto-generate via voice design if missing
    project_root = project_config.get("project", {}).get("project_root_path", "")
    voice_file = tts_config.get("voice_file", "")
    if not voice_file and project_root:
        candidate = Path(project_root) / "voice_file.wav"
        if candidate.exists():
            voice_file = str(candidate)

    if not voice_file or not Path(voice_file).exists():
        # Run voice design to generate a reference voice
        voice_instruct = tts_config.get("voice_instruct", "")
        if not voice_instruct:
            lang = project_config.get("project", {}).get("language", "zh-CN")
            voice_instruct = "男，中年，中音调" if lang == "zh-CN" else "male, middle-aged, moderate pitch"

        voice_output = str(Path(project_root) / "voice_file.wav") if project_root else ""
        if not voice_output:
            print(json.dumps({
                "status": "error",
                "msg": "Cannot auto-generate voice: project.project_root_path is not set",
                "data": {},
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

        print(f"Voice file not found. Running voice design (instruct: {voice_instruct})...", file=sys.stderr)
        voice_file = _run_voice_design(voice_instruct, voice_output, timeout=tts_timeout)

        # Update project_config.yaml with the generated voice file
        tts_config["voice_file"] = voice_file
        save_yaml(project_config, args.project_config)
        print(f"Voice file generated and saved to project_config: {voice_file}", file=sys.stderr)

    # HTTP server config
    http_config = tts_config.get("http", {})
    http_url = http_config.get("url", "")
    # Headers: project_config tts.http.headers → env vars fallback
    http_headers = dict(http_config.get("headers", {}))
    if not http_headers.get("Host-User-ID") and "Host-User-ID" in os.environ:
        http_headers["Host-User-ID"] = os.environ["Host-User-ID"]
    if not http_headers.get("Host-User-Token") and "Host-User-Token" in os.environ:
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
    skipped = 0
    for u in units:
        # Output path: video_dir/stories/{story_id}/{narration_id}/speech.wav
        out_dir = video_dir / "stories" / u["story_id"] / u["narration_id"]
        out_path = str(out_dir / "speech.wav")

        # Check both the YAML audio_path and the computed output path
        audio_path = u["audio_path"]
        already_exists = (
            (audio_path and Path(audio_path).exists())
            or Path(out_path).exists()
        )
        if not args.force and already_exists:
            u["output_path"] = out_path if Path(out_path).exists() else audio_path
            skipped += 1
            continue

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
                    timeout=tts_timeout,
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
        print(f"Generating TTS for {len(to_generate)} narration unit(s) using backend: {backend}"
              f" ({skipped} skipped, already exist)", file=sys.stderr)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(generate_one, u): u for u in to_generate}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result["error"]:
                    errors.append({"narration_id": result["unit"]["narration_id"], "error": result["error"]})
                else:
                    generated += 1

    # Compress WAV → MP3 (128kbps) for reduced memory usage during Remotion render
    def _compress_audio(wav_path: str) -> str:
        mp3_path = str(Path(wav_path).with_suffix(".mp3"))
        if Path(mp3_path).exists() and not args.force:
            return mp3_path
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-b:a", "128k", "-map_metadata", "-1", mp3_path],
                capture_output=True, text=True, timeout=60,
                check=True,
            )
            return mp3_path
        except subprocess.SubprocessError as e:
            print(f"    WARNING: audio compression failed for {wav_path}: {e}", file=sys.stderr)
            return wav_path  # fall back to uncompressed

    compressed_count = 0
    for u in units:
        wav_path = u.get("output_path", u["audio_path"])
        if wav_path and Path(wav_path).exists() and wav_path.endswith(".wav"):
            mp3_path = _compress_audio(wav_path)
            if mp3_path != wav_path:
                u["output_path"] = mp3_path
                u["narration_ref"]["audio_path"] = mp3_path
                compressed_count += 1
    if compressed_count:
        print(f"  Compressed {compressed_count} audio file(s) to MP3 (128kbps)", file=sys.stderr)

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
            "data": {"generated": generated, "skipped": skipped, "updated": updated_count, "errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": f"TTS complete: {generated} generated, {skipped} skipped, {updated_count} updated with frame counts",
            "data": {"generated": generated, "skipped": skipped, "updated": updated_count, "fps": fps},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
