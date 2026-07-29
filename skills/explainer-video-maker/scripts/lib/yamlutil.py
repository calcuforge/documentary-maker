"""
YAML load/save utilities with consistent encoding and error handling.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> Any:
    """Load a YAML file, exiting with a readable error on failure."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {p}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"ERROR: YAML parse error in {p}: {exc}", file=sys.stderr)
        sys.exit(1)


def save_yaml(data: Any, path: str | Path) -> None:
    """Save data to a YAML file with UTF-8 encoding."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_yaml_str(content: str) -> Any:
    """Parse a YAML string."""
    return yaml.safe_load(content)
