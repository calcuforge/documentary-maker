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
    """Resolve the remotion-video-template path from project config."""
    dep = project_config.get("dependence_paths", {})
    template_rel = dep.get("remotion_template", "../remotion-video-template")

    if os.path.isabs(template_rel):
        return Path(template_rel)

    # Resolve relative to the repo root
    # scripts/tool/render.py → SKILL_ROOT=scripts/ → skill root → skills/ → repo root
    repo_root = SKILL_ROOT.parent.parent.parent  # explainer-video-maker/
    resolved = (repo_root / template_rel).resolve()
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Render video via remotion-video-template")
    parser.add_argument("--remotion-sections", required=True, help="Path to remotion_sections.yaml")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml")
    parser.add_argument("--output", required=True, help="Output video file path")
    parser.add_argument("--studio", action="store_true", help="Launch Studio instead of rendering")
    parser.add_argument("--timeout", type=int, default=1800, help="Render timeout (seconds, default 30min)")
    args = parser.parse_args()

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

    # Render
    cmd = [
        "node", str(render_script),
        sections_path,
        "--public-dir", public_dir,
        "--output", output_path,
    ]

    print(f"Rendering video...", file=sys.stderr)
    print(f"  Config: {sections_path}", file=sys.stderr)
    print(f"  Public dir: {public_dir}", file=sys.stderr)
    print(f"  Output: {output_path}", file=sys.stderr)
    print(f"  Template: {template_path}", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(template_path),
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "status": "error",
            "msg": f"Render timed out after {args.timeout}s",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    if result.returncode != 0:
        print(json.dumps({
            "status": "error",
            "msg": "Render failed",
            "data": {"stderr": result.stderr[-2000:] if result.stderr else "", "stdout": result.stdout[-1000:] if result.stdout else ""},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Verify output exists
    if not Path(output_path).exists():
        print(json.dumps({
            "status": "error",
            "msg": f"Output file not created: {output_path}",
            "data": {"stdout": result.stdout[-500:]},
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
