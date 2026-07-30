#!/usr/bin/env python3
"""
Initialize a new project directory and project_config.yaml from the template
scripts/project_config_tpl.yaml.

All default field values live in the template file — nothing is hardcoded here.
The script loads the template, creates a project directory, fills
project.project_root_path, and writes project_config.yaml. The agent then edits
the created file DIRECTLY to supply request-dependent fields (project.name,
language, video_style, target_audience, ...).

The project directory is created under --projects-dir, named after project.name
in the template. If that name already exists, a numeric suffix is appended
(my-project, my-project2, my-project3, ...).

Usage:
    python init_project.py --projects-dir /abs/path/projects

Output (JSON envelope): data.project_dir and data.project_config give the
created project directory and project_config.yaml locations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml, save_yaml
from verify.verify_project_config import validate

TEMPLATE_PATH = SKILL_ROOT / "project_config_tpl.yaml"


def resolve_project_dir(projects_dir: Path, name: str) -> tuple[Path, str]:
    """Return (project_dir, final_name), appending a numeric suffix if needed."""
    candidate = projects_dir / name
    if not candidate.exists():
        return candidate, name
    n = 2
    while True:
        suffixed = f"{name}{n}"
        candidate = projects_dir / suffixed
        if not candidate.exists():
            return candidate, suffixed
        n += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a new project from project_config_tpl.yaml")
    parser.add_argument("--projects-dir", required=True, help="Workspace projects/ directory (absolute)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.projects_dir)

    if not TEMPLATE_PATH.exists():
        print(json.dumps({
            "status": "error",
            "msg": f"Template not found: {TEMPLATE_PATH}",
            "data": {},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    config = load_yaml(TEMPLATE_PATH)
    project = config.setdefault("project", {})

    base_name = project.get("name") or "project"
    projects_dir = Path(args.projects_dir)
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_dir, final_name = resolve_project_dir(projects_dir, base_name)
    project_dir.mkdir(parents=True, exist_ok=False)

    # Fill the created project's identity and root path
    project["name"] = final_name
    project["project_root_path"] = str(project_dir)

    # Guarantee the generated config passes validation before writing
    errors = validate(config)
    if errors:
        print(json.dumps({
            "status": "error",
            "msg": "Generated project_config.yaml failed validation",
            "data": {"errors": errors},
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    config_path = project_dir / "project_config.yaml"
    save_yaml(config, config_path)

    # Fields left empty in the template for the agent to fill
    supplement = [
        f"project.{field}"
        for field in ("language", "video_style", "target_audience")
        if not project.get(field)
    ]

    print(json.dumps({
        "status": "ok",
        "msg": f"Initialized project '{final_name}'",
        "data": {
            "project_dir": str(project_dir.resolve()),
            "project_config": str(config_path.resolve()),
            "project_name": final_name,
            "creation_mode": project.get("creation_mode", ""),
            "agent_supplement": supplement,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
