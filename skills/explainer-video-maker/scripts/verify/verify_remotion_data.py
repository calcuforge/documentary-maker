#!/usr/bin/env python3
"""
Validate remotion_data fields per component by calling remotion-video-template's
validate-remotion-data.mjs script.

Resolves the remotion-video-template path from project_config.yaml →
dependence_paths.remotion_template, then invokes:
    node <template>/validate-remotion-data.mjs <remotion_sections.yaml>

Usage:
    python verify_remotion_data.py \
        --remotion-sections /abs/path/remotion_sections.yaml \
        --project-config /abs/path/project_config.yaml

Exit codes: 0 = valid, 1 = errors found.
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
    parser = argparse.ArgumentParser(
        description="Validate remotion_data via remotion-video-template's validator"
    )
    parser.add_argument("--remotion-sections", required=True,
                        help="Path to remotion_sections.yaml (absolute)")
    parser.add_argument("--project-config", required=True,
                        help="Path to project_config.yaml (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.remotion_sections, args.project_config)

    if not Path(args.remotion_sections).exists():
        print(json.dumps({
            "status": "error",
            "msg": f"File not found: {args.remotion_sections}",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    project_config = load_yaml(args.project_config)
    template_path = resolve_template_path(project_config)

    validate_script = template_path / "validate-remotion-data.mjs"
    if not validate_script.exists():
        print(json.dumps({
            "status": "error",
            "msg": f"validate-remotion-data.mjs not found in {template_path}",
            "data": {"hint": "Update remotion-video-template to a version that includes this script"},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    sections_path = str(Path(args.remotion_sections).resolve())

    try:
        result = subprocess.run(
            ["node", str(validate_script), sections_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "status": "error",
            "msg": "Validation timed out after 60s",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "msg": "node not found on PATH",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Pass through the validator's JSON output
    output = result.stdout.strip()
    if output:
        print(output)
    elif result.stderr:
        print(json.dumps({
            "status": "error",
            "msg": "Validator produced no JSON output",
            "data": {"stderr": result.stderr[-1000:]},
        }, ensure_ascii=False, indent=2))

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
