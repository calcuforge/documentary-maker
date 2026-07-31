#!/usr/bin/env python3
"""
Render video using remotion-video-template.

Calls the render-yaml.mjs script in the remotion-video-template project,
passing the remotion_sections.yaml configuration.

Usage:
    python render.py --remotion-sections /abs/path/remotion_sections.yaml \
                     --project-config /abs/path/project_config.yaml \
                     --output /abs/path/result.mp4

Options:
    --remotion-sections  Path to remotion_sections.yaml (required)
    --project-config     Path to project_config.yaml (required)
    --output             Output video file path (required)
    --studio             Launch Remotion Studio instead of rendering
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml


def resolve_template_path(project_config: dict) -> Path:
    """Resolve the remotion-video-template path from project config.

    The default location is the workspace's dep/ directory
    (dep/remotion-video-template). A `~`-prefixed or absolute path is used as-is
    (after ~ expansion); a genuinely relative path resolves against the workspace
    (the directory that contains projects/).
    """
    dep = project_config.get("dependence_paths", {})
    template_rel = dep.get("remotion_template", "dep/remotion-video-template")

    expanded = os.path.expanduser(template_rel)
    if os.path.isabs(expanded):
        return Path(expanded)

    project_root = project_config.get("project", {}).get("project_root_path", "")
    base = Path(project_root).parent.parent if project_root else Path.cwd()
    return (base / expanded).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render video via remotion-video-template")
    parser.add_argument("--remotion-sections", required=True, help="Path to remotion_sections.yaml (absolute)")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--output", required=True, help="Output video file path (absolute)")
    parser.add_argument("--studio", action="store_true", help="Launch Studio instead of rendering")
    parser.add_argument("--timeout", type=int, default=3600, help="Render timeout (seconds, default 1h)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.remotion_sections, args.project_config, args.output)

    project_config = load_yaml(args.project_config)
    template_path = resolve_template_path(project_config)

    if not template_path.exists():
        print(json.dumps({
            "status": "error",
            "msg": f"remotion-video-template not found at: {template_path}",
            "data": {"hint": "Set dependence_paths.remotion_template in project_config.yaml"},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    render_script = template_path / "render-yaml.mjs"
    if not render_script.exists():
        print(json.dumps({
            "status": "error",
            "msg": f"render-yaml.mjs not found in {template_path}",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    sections_path = str(Path(args.remotion_sections).resolve())
    output_path = str(Path(args.output).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Use the video directory as public-dir (contains audio + assets)
    public_dir = str(Path(args.remotion_sections).parent)

    if args.studio:
        # Launch Studio
        cmd = ["node", str(render_script), sections_path, "--studio"]
        print(f"Launching Remotion Studio...", file=sys.stderr)
        print(f"  Config: {sections_path}", file=sys.stderr)
        print(f"  Template: {template_path}", file=sys.stderr)
        try:
            subprocess.run(cmd, cwd=str(template_path))
        except KeyboardInterrupt:
            pass
        return

    # Render — render-yaml.mjs splits the video into frame-range segments, renders
    # them in parallel (each at Remotion's default concurrency) and concatenates
    # them with ffmpeg. segment_frames / segment_workers are optional tuning knobs
    # (render-yaml.mjs applies its own defaults when they are not set).
    render_cfg = project_config.get("render") or {}
    segment_frames = render_cfg.get("segment_frames")
    segment_workers = render_cfg.get("segment_workers")

    cmd = [
        "node", str(render_script),
        sections_path,
        "--public-dir", public_dir,
        "--output", output_path,
    ]
    if segment_frames:
        cmd.extend(["--segment-frames", str(segment_frames)])
    if segment_workers:
        cmd.extend(["--segment-workers", str(segment_workers)])

    print(f"Rendering video...", file=sys.stderr)
    print(f"  Config: {sections_path}", file=sys.stderr)
    print(f"  Public dir: {public_dir}", file=sys.stderr)
    print(f"  Output: {output_path}", file=sys.stderr)
    print(f"  Template: {template_path}", file=sys.stderr)
    print(f"  Segment frames: {segment_frames or '(default)'}", file=sys.stderr)
    print(f"  Segment workers: {segment_workers or '(default)'}", file=sys.stderr)

    # Write render output to a log file instead of capturing via pipes.
    # capture_output=True buffers ALL stdout/stderr in memory — for a long
    # segmented render this can be tens of MB and causes pipe-buffer
    # deadlocks or OOM on Windows. A log file avoids both problems.
    log_path = Path(output_path).parent / "render.log"
    print(f"  Log: {log_path}", file=sys.stderr)

    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            proc = subprocess.run(
                cmd,
                cwd=str(template_path),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
            )
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "status": "error",
            "msg": f"Render timed out after {args.timeout}s",
            "data": {"log": str(log_path)},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "msg": "node not found on PATH — install Node.js >= 18",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except OSError as e:
        print(json.dumps({
            "status": "error",
            "msg": f"Failed to start render process: {e}",
            "data": {"log": str(log_path)},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    if proc.returncode != 0:
        # Read the tail of the log for error diagnostics
        log_tail = ""
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = log_text[-3000:] if log_text else ""
        except OSError:
            pass
        print(json.dumps({
            "status": "error",
            "msg": "Render failed",
            "data": {"log": str(log_path), "log_tail": log_tail},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Verify output exists
    if not Path(output_path).exists():
        log_tail = ""
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = log_text[-1000:] if log_text else ""
        except OSError:
            pass
        print(json.dumps({
            "status": "error",
            "msg": f"Output file not created: {output_path}",
            "data": {"log": str(log_path), "log_tail": log_tail},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Get file size
    size_mb = Path(output_path).stat().st_size / (1024 * 1024)

    print(json.dumps({
        "status": "ok",
        "msg": f"Video rendered successfully: {output_path}",
        "data": {
            "output": output_path,
            "size_mb": round(size_mb, 1),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
