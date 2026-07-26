#!/usr/bin/env python3
"""Generate TTS audio from narration_script.yaml.

Two backends:
    comfyui_indextts  — calls `comfyui-scheduler run -w index_tts_2 -i ...`
                        Downloads the resulting audio file → narration_audio.wav.
    http_server       — POSTs JSON to an OpenAI-compatible /v1/audio/speech
                        endpoint; saves the binary response → narration_audio.wav.

After audio is on disk, runs `estimate_timing.py` to build SRT + timing.json.
"""
import argparse
import json
import os
import subprocess
import sys

import requests
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DOC_ROOT = os.path.normpath(os.path.join(SKILL_DIR, "..", ".."))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import comfyui as comfyui_runner  # noqa: E402
import estimate_timing  # noqa: E402


def load_project_prefs(project_name):
    ppath = os.path.join(DOC_ROOT, "projects", project_name, "project_prefs.yaml")
    if not os.path.isfile(ppath):
        cli_envelope.emit_usage_error(
            f"Project '{project_name}' not found (no prefs at {ppath}).",
            fmt="text",
        )
    with open(ppath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_narration_script(video_dir):
    path = os.path.join(video_dir, "narration_script.yaml")
    if not os.path.isfile(path):
        cli_envelope.emit_usage_error(
            f"narration_script.yaml not found at {path}", fmt="text")
    with open(path, "r", encoding="utf-8") as f:
        sections = yaml.safe_load(f) or []
    return sections


def concat_narration(sections):
    """Build a single TTS input string with [SECTION:name] markers preserved
    only as natural pauses (the markers are NOT sent to TTS)."""
    parts = []
    for s in sections:
        text = (s.get("narration") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def synth_comfyui(sections, prefs, video_dir, fmt):
    workflow_id = prefs.get("workflows", {}).get("tts", "index_tts_2")
    voice_file = prefs.get("tts", {}).get("voice_file")
    if not voice_file:
        cli_envelope.emit_usage_error(
            "tts.voice_file is required when backend=comfyui_indextts. "
            "Set it in project_prefs.yaml.",
            fmt=fmt,
        )
    if not os.path.isfile(voice_file):
        cli_envelope.emit_usage_error(
            f"voice_file not found: {voice_file}", fmt=fmt)
    content = concat_narration(sections)
    if not content.strip():
        cli_envelope.emit_usage_error(
            "Narration is empty. Add narration text to narration_script.yaml.",
            fmt=fmt)
    inputs = {"content": content, "voice_file": voice_file}
    # Run the workflow and download outputs into assets/ (audio file is the
    # primary output; we'll move it to narration_audio.wav below).
    dest = os.path.join(video_dir, "assets")
    os.makedirs(dest, exist_ok=True)
    # Use the inner function directly so we control the result object.
    result = _run_workflow_and_capture(workflow_id, inputs, dest, fmt)
    audio_path = None
    for f in result.get("files", []):
        if f.get("kind") == "audio":
            audio_path = f.get("local_path")
            break
    if audio_path is None:
        # Fall back: pick any output file.
        for f in result.get("files", []):
            audio_path = f.get("local_path")
            if audio_path:
                break
    if audio_path is None:
        cli_envelope.emit_error(
            "workflow_failed",
            "index_tts workflow produced no audio file.",
            details=result, fmt=fmt, exit_code=1,
        )
    final_path = os.path.join(video_dir, "narration_audio.wav")
    # Rename/move. If the file is already a wav, just rename; else let ffmpeg convert.
    if audio_path.lower().endswith(".wav"):
        os.replace(audio_path, final_path)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, final_path],
            check=True, capture_output=True,
        )
        os.remove(audio_path)
    return final_path


def _run_workflow_and_capture(workflow_id, inputs, dest_dir, fmt):
    """Reimplements comfyui_runner.run_workflow but returns dict instead of exiting."""
    import shutil
    if not shutil.which("comfyui-scheduler"):
        cli_envelope.emit_error(
            "prereqs_failed",
            "comfyui-scheduler is not on PATH.",
            fmt=fmt, exit_code=1,
        )
    argv = ["comfyui-scheduler", "run", "-w", workflow_id, "-i", json.dumps(inputs)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        cli_envelope.emit_error(
            "workflow_failed",
            f"comfyui-scheduler exited {result.returncode}: {result.stderr.strip()}",
            details={"stdout": result.stdout, "stderr": result.stderr},
            fmt=fmt, exit_code=1,
        )
    envelope = json.loads(result.stdout)
    data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
    files_out = []
    for f in data.get("files", []):
        url = f.get("url")
        kind = f.get("kind", "audio")
        if not url:
            continue
        try:
            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()
        except Exception as exc:
            cli_envelope.emit_error(
                "download_failed",
                f"Failed to download {url}: {exc}", fmt=fmt, exit_code=1,
            )
        from urllib.parse import urlsplit
        filename = os.path.basename(urlsplit(url).path) or f"output_{kind}.bin"
        local = os.path.join(dest_dir, filename)
        with open(local, "wb") as fh:
            for chunk in resp.iter_content(8192):
                fh.write(chunk)
        files_out.append({"kind": kind, "url": url, "filename": filename, "local_path": local})
    return {"workflow_id": workflow_id, "task_id": data.get("task_id"),
            "prompt_id": data.get("prompt_id"),
            "output_type": data.get("output_type"),
            "files": files_out}


def synth_http(sections, prefs, video_dir, fmt):
    cfg = prefs.get("tts", {}).get("http", {})
    url = cfg.get("url")
    if not url:
        cli_envelope.emit_usage_error(
            "tts.http.url is required when backend=http_server.", fmt=fmt)
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    content = concat_narration(sections)
    if not content.strip():
        cli_envelope.emit_usage_error(
            "Narration is empty. Add narration text to narration_script.yaml.",
            fmt=fmt)
    payload = {
        "model": cfg.get("model", "tts-1"),
        "input": content,
        "voice": cfg.get("voice", "alloy"),
        "response_format": cfg.get("response_format", "wav"),
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=900)
        resp.raise_for_status()
    except Exception as exc:
        cli_envelope.emit_error(
            "http_tts_failed",
            f"HTTP TTS request failed: {exc}",
            details={"status_code": getattr(resp, "status_code", None),
                     "body": getattr(resp, "text", None) if 'resp' in dir() else None},
            fmt=fmt, exit_code=1,
        )
    final_path = os.path.join(video_dir, "narration_audio.wav")
    with open(final_path, "wb") as f:
        f.write(resp.content)
    return final_path


def build_parser():
    parser = argparse.ArgumentParser(description="Generate TTS audio from narration_script.yaml.")
    cli_envelope.add_format_arg(parser)
    parser.add_argument("--project", required=True)
    parser.add_argument("--video", required=True,
                        help="Video name (subdirectory of project's videos/).")
    parser.add_argument("--backend", default=None,
                        choices=["comfyui_indextts", "http_server"],
                        help="Override prefs.tts.backend.")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    prefs = load_project_prefs(args.project)
    video_dir = os.path.join(DOC_ROOT, "projects", args.project, "videos", args.video)
    if not os.path.isdir(video_dir):
        cli_envelope.emit_usage_error(
            f"Video dir not found: {video_dir}", fmt=args.format)
    sections = load_narration_script(video_dir)
    backend = args.backend or prefs.get("tts", {}).get("backend", "comfyui_indextts")
    if backend == "comfyui_indextts":
        audio_path = synth_comfyui(sections, prefs, video_dir, args.format)
    elif backend == "http_server":
        audio_path = synth_http(sections, prefs, video_dir, args.format)
    else:
        cli_envelope.emit_usage_error(f"Unknown TTS backend: {backend}", fmt=args.format)

    # Build SRT + timing.json via char-count estimator.
    fps = prefs.get("video", {}).get("fps", 30)
    # Re-invoke estimate_timing in-process to reuse its drift correction.
    sys.argv = [
        "estimate_timing.py",
        "--video-dir", video_dir,
        "--fps", str(fps),
        "--format", args.format,
    ]
    estimate_timing.main()


if __name__ == "__main__":
    main()
