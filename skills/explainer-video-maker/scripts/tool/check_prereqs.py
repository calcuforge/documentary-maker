#!/usr/bin/env python3
"""
Check all prerequisites for explainer-video-maker pipeline.

Validates:
- Python >= 3.10
- ffmpeg / ffprobe on PATH
- Node.js >= 18 / npx
- comfyui-scheduler CLI installed
- remotion-video-template node_modules present
- requests / pyyaml / playwright Python packages

Usage:
    python check_prereqs.py --project-config /abs/path/project_config.yaml
    python check_prereqs.py  # checks without project-specific paths
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))


def check_python() -> list[str]:
    errors = []
    v = sys.version_info
    if v < (3, 10):
        errors.append(f"Python >= 3.10 required, found {v.major}.{v.minor}.{v.micro}")
    return errors


def check_binary(name: str) -> list[str]:
    errors = []
    if shutil.which(name) is None:
        errors.append(f"'{name}' not found on PATH")
    return errors


def check_node() -> list[str]:
    errors = []
    node_path = shutil.which("node")
    if not node_path:
        errors.append("Node.js not found on PATH")
        return errors
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        version_str = result.stdout.strip().lstrip("v")
        major = int(version_str.split(".")[0])
        if major < 18:
            errors.append(f"Node.js >= 18 required, found v{version_str}")
    except Exception as e:
        errors.append(f"Failed to check Node.js version: {e}")
    return errors


def check_python_packages() -> list[str]:
    errors = []
    packages = ["requests", "yaml", "playwright"]
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            pip_name = "pyyaml" if pkg == "yaml" else pkg
            errors.append(f"Python package '{pip_name}' not installed. Run: pip install {pip_name}")
    return errors


def check_comfyui_scheduler() -> list[str]:
    errors = []
    if shutil.which("comfyui-scheduler") is None:
        errors.append(
            "comfyui-scheduler CLI not found. Install: pip install -e dep/comfyui-scheduler"
        )
    return errors


def check_remotion_template(project_config: dict | None) -> list[str]:
    errors = []
    if not project_config:
        return errors

    dep = project_config.get("dependence_paths", {})
    template_path = dep.get("remotion_template", "")
    if not template_path:
        return errors

    # Default location is the workspace's dep/ directory (e.g.
    # dep/remotion-video-template). A ~-prefixed or absolute path is used as-is
    # (after ~ expansion); a genuinely relative path resolves against the
    # workspace (the directory that contains projects/).
    template_path = os.path.expanduser(template_path)
    project_root = project_config.get("project", {}).get("project_root_path", "")
    if project_root and not os.path.isabs(template_path):
        resolved = Path(project_root).parent.parent / template_path
    else:
        resolved = Path(template_path)

    resolved = resolved.resolve()
    if not resolved.exists():
        errors.append(f"remotion-video-template not found at: {resolved}")
    elif not (resolved / "node_modules").exists():
        errors.append(f"node_modules not found in {resolved}. Run: npm install")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Check prerequisites")
    parser.add_argument("--project-config", default="", help="Path to project_config.yaml (absolute)")
    args = parser.parse_args()

    if args.project_config:
        from lib.net import require_abs
        require_abs(args.project_config)

    all_errors: list[str] = []

    # Core checks
    all_errors.extend(check_python())
    all_errors.extend(check_binary("ffmpeg"))
    all_errors.extend(check_binary("ffprobe"))
    all_errors.extend(check_node())
    all_errors.extend(check_binary("npx"))
    all_errors.extend(check_python_packages())
    all_errors.extend(check_comfyui_scheduler())

    # Project-specific checks
    project_config = None
    if args.project_config:
        from lib.yamlutil import load_yaml
        project_config = load_yaml(args.project_config)
        all_errors.extend(check_remotion_template(project_config))

    if all_errors:
        print(json.dumps({
            "status": "error",
            "msg": f"{len(all_errors)} prerequisite(s) missing",
            "data": {"errors": all_errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "ok",
            "msg": "All prerequisites satisfied",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(0)


if __name__ == "__main__":
    main()
