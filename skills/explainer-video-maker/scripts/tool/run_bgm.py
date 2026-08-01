#!/usr/bin/env python3
"""
Generate background music (BGM) for a project via comfyui-scheduler's
text-to-music workflow (stable_audio_3_medium).

BGM is a project-level resource shared by all videos in the project. This script
generates it once and writes the resulting file path back into project_config.yaml
(bgm.audio). The remotion config step then copies it into each video dir and mixes
it in-render via Remotion <Audio>.

Skipped (idempotent) when:
  - bgm.enabled is false
  - bgm.audio already points to an existing file (pass --force to regenerate)

Usage:
    python run_bgm.py --project-config /abs/path/project_config.yaml

Options:
    --project-config  Path to project_config.yaml (absolute, required)
    --force           Regenerate even if bgm.audio already exists
    --timeout         Per-generation subprocess timeout in seconds (default 1h)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml


def get_audio_duration(audio_path: str) -> float | None:
    """Return audio duration in seconds via ffprobe, or None on any failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return float(json.loads(result.stdout)["format"]["duration"])
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, OSError):
        return None


def synth_text_to_music(prompt: str, output_path: str, length: int, seed: int | None, timeout: int) -> str:
    """Generate music using comfyui-scheduler stable_audio_3_medium workflow.

    Returns the output audio file path.
    """
    payload = {"prompt": prompt, "duration": float(length)}
    if seed is not None:
        payload["seed"] = seed

    inputs = json.dumps(payload, ensure_ascii=False)
    cmd = ["comfyui-scheduler", "run", "-w", "stable_audio_3_medium", "-i", inputs]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"BGM generation timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError("comfyui-scheduler not found on PATH")

    if result.returncode != 0:
        raise RuntimeError(f"comfyui-scheduler failed: {result.stderr or result.stdout[:300]}")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON from comfyui-scheduler: {result.stdout[:200]}")

    if output.get("status") != "ok":
        raise RuntimeError(f"BGM generation error: {output.get('msg', 'unknown')}")

    files = output.get("data", {}).get("files", [])
    if not files:
        raise RuntimeError("No output files from BGM generation")

    file_url = files[0].get("url", "")
    if not file_url:
        raise RuntimeError("No URL in BGM generation output")

    from lib.net import download_file
    download_file(file_url, output_path)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate background music for a project")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if bgm.audio exists")
    parser.add_argument("--timeout", type=int, default=3600, help="Per-generation subprocess timeout in seconds (default 1h)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config)

    project_config = load_yaml(args.project_config)
    bgm = project_config.get("bgm", {})

    if not bgm.get("enabled", True):
        print(json.dumps({
            "status": "ok",
            "msg": "BGM disabled (bgm.enabled: false) — skipping generation",
            "data": {},
        }, ensure_ascii=False, indent=2))
        return

    project_root = project_config.get("project", {}).get("project_root_path", "")
    if not project_root:
        print(json.dumps({
            "status": "error",
            "msg": "Cannot generate BGM: project.project_root_path is not set",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Default output path (project-level, shared across all videos)
    output_path = str(Path(project_root) / "bgm.mp3")

    existing = bgm.get("audio", "")
    if existing and Path(existing).exists() and not args.force:
        duration = get_audio_duration(existing)
        print(json.dumps({
            "status": "ok",
            "msg": f"BGM already exists — skipping: {existing}",
            "data": {"audio": existing, "duration": duration},
        }, ensure_ascii=False, indent=2))
        return

    prompt = bgm.get("prompt", "")
    if not prompt:
        print(json.dumps({
            "status": "error",
            "msg": "Cannot generate BGM: bgm.prompt is empty — describe the desired music "
                   "(style, instruments, mood) in project_config.yaml",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    length = bgm.get("length", 120) or 120
    aigc_seed = project_config.get("aigc", {}).get("seed", 0)
    seed = int(aigc_seed) if aigc_seed else None

    try:
        synth_text_to_music(prompt, output_path, int(length), seed, timeout=args.timeout)
    except RuntimeError as e:
        print(json.dumps({
            "status": "error",
            "msg": f"BGM generation failed: {e}",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    duration = get_audio_duration(output_path)

    # Write the generated path back into project_config.yaml
    bgm["audio"] = output_path
    save_yaml(project_config, args.project_config)

    print(json.dumps({
        "status": "ok",
        "msg": f"BGM generated: {output_path}",
        "data": {"audio": output_path, "duration": duration},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
