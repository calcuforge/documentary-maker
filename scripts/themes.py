#!/usr/bin/env python3
"""Theme registry.

Themes are YAML partials in documentary-maker/themes/*.yaml. Each theme
overrides `theme:` and `content:` blocks plus a `component_suggestions:` map
and a `narrative_arc:` list hint for chapter design.

Commands:
    themes list
    themes show   --name <theme>
    themes resolve --name <theme> --prefs <project_prefs.yaml>
                    Deep-merge the theme onto the project prefs and emit
                    the effective prefs document.
"""
import argparse
import copy
import glob
import os
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
THEMES_DIR = os.path.join(SKILL_DIR, "themes")

sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402


def _deep_merge(base, overlay):
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def list_themes():
    files = sorted(glob.glob(os.path.join(THEMES_DIR, "*.yaml")))
    out = []
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            out.append({
                "name": name,
                "primary_color": data.get("theme", {}).get("primary_color"),
                "accent_color": data.get("theme", {}).get("accent_color"),
                "tone": data.get("content", {}).get("tone"),
                "arc": data.get("narrative_arc", []),
            })
        except Exception as exc:
            out.append({"name": name, "error": str(exc)})
    return out


def show_theme(name):
    path = os.path.join(THEMES_DIR, f"{name}.yaml")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_theme(name, prefs_path):
    theme = show_theme(name)
    if theme is None:
        return None
    with open(prefs_path, "r", encoding="utf-8") as f:
        prefs = yaml.safe_load(f) or {}
    merged = _deep_merge(prefs, theme)
    return merged


def build_parser():
    parser = argparse.ArgumentParser(description="Theme registry.")
    cli_envelope.add_format_arg(parser)
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("list", help="List available themes.")

    p_show = sub.add_parser("show", help="Show one theme preset.")
    p_show.add_argument("--name", required=True)

    p_resolve = sub.add_parser("resolve", help="Deep-merge a theme onto project prefs.")
    p_resolve.add_argument("--name", required=True)
    p_resolve.add_argument("--prefs", required=True, help="Path to project_prefs.yaml")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action == "list":
        out = list_themes()
        cli_envelope.emit_ok(data={"themes": out}, fmt=args.format)
    elif args.action == "show":
        out = show_theme(args.name)
        if out is None:
            cli_envelope.emit_usage_error(f"Theme '{args.name}' not found.", fmt=args.format)
        cli_envelope.emit_ok(data=out, fmt=args.format)
    elif args.action == "resolve":
        out = resolve_theme(args.name, args.prefs)
        if out is None:
            cli_envelope.emit_usage_error(f"Theme '{args.name}' not found.", fmt=args.format)
        cli_envelope.emit_ok(data=out, fmt=args.format)


if __name__ == "__main__":
    main()
