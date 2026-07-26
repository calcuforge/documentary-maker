#!/usr/bin/env python3
"""Project CRUD for documentary-maker.

A "project" is a directory under documentary-maker/projects/{name}/ that
contains a `project_prefs.yaml` and a `videos/` subfolder for per-video work.

Commands:
    project create --name <name> [--category <cat>] [--orientation h|v]
                   [--resolution 1080p|4k] [--quality speed|quality]
                   [--language zh-CN|en-US] [--mode auto|manual]
    project list
    project show   --name <name>
    project set    --name <name> --key <dotted.path> --value <yaml-safe>
    project video  --name <name> --video <video-name>
                   Create a per-video subfolder scaffold.

Project name rules: lowercase, hyphen-separated, ≤64 chars.
"""
import argparse
import os
import re
import shutil
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
# documentary-maker root is two levels up from skill dir (skills/documentary-maker/)
DOC_ROOT = os.path.normpath(os.path.join(SKILL_DIR, "..", ".."))
PROJECTS_DIR = os.path.join(DOC_ROOT, "projects")
TEMPLATE_PATH = os.path.join(SKILL_DIR, "project_prefs.template.yaml")

sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _project_dir(name):
    return os.path.join(PROJECTS_DIR, name)


def _prefs_path(name):
    return os.path.join(_project_dir(name), "project_prefs.yaml")


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _dump_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _set_nested(d, dotted, value):
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def build_parser():
    parser = argparse.ArgumentParser(description="Project management.")
    cli_envelope.add_format_arg(parser)
    sub = parser.add_subparsers(dest="action", required=True)

    p_create = sub.add_parser("create", help="Create a new project.")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--category", default=None,
                          choices=["aviation-disaster", "history", "crime", "natural-disaster"])
    p_create.add_argument("--orientation", default=None, choices=["horizontal", "vertical"])
    p_create.add_argument("--resolution", default=None, choices=["1080p", "4k"])
    p_create.add_argument("--quality", default=None, choices=["speed", "quality"])
    p_create.add_argument("--language", default=None, choices=["zh-CN", "en-US"])
    p_create.add_argument("--mode", default=None, choices=["auto", "manual"])

    p_list = sub.add_parser("list", help="List all projects.")

    p_show = sub.add_parser("show", help="Show project prefs.")
    p_show.add_argument("--name", required=True)

    p_set = sub.add_parser("set", help="Set a dotted-path preference (e.g. theme.primary_color).")
    p_set.add_argument("--name", required=True)
    p_set.add_argument("--key", required=True)
    p_set.add_argument("--value", required=True)

    p_video = sub.add_parser("video", help="Create a per-video subfolder scaffold.")
    p_video.add_argument("--name", required=True)
    p_video.add_argument("--video", required=True)

    return parser


def cmd_create(args):
    if not NAME_RE.match(args.name):
        cli_envelope.emit_usage_error(
            "Invalid project name. Use lowercase, hyphen-separated, ≤64 chars.",
            fmt=args.format,
        )
    pdir = _project_dir(args.name)
    if os.path.exists(pdir):
        cli_envelope.emit_usage_error(
            f"Project '{args.name}' already exists at {pdir}",
            fmt=args.format,
        )
    os.makedirs(pdir, exist_ok=False)
    os.makedirs(os.path.join(pdir, "videos"), exist_ok=True)
    shutil.copy(TEMPLATE_PATH, _prefs_path(args.name))
    prefs = _load_yaml(_prefs_path(args.name))
    prefs["project"]["name"] = args.name
    if args.category:
        prefs["project"]["category"] = args.category
    if args.orientation:
        prefs["project"]["orientation"] = args.orientation
    if args.mode:
        prefs["project"]["creation_mode"] = args.mode
    if args.language:
        prefs["project"]["language"] = args.language
    if args.resolution:
        prefs["video"]["resolution"] = args.resolution
    if args.quality:
        prefs["ai"]["quality_tier"] = args.quality
    _dump_yaml(_prefs_path(args.name), prefs)
    cli_envelope.emit_ok(
        data={"project_dir": pdir, "prefs_path": _prefs_path(args.name)},
        message=f"Project '{args.name}' created.",
        fmt=args.format,
    )


def cmd_list(args):
    if not os.path.isdir(PROJECTS_DIR):
        cli_envelope.emit_ok(data={"projects": []}, fmt=args.format)
    projects = []
    for name in sorted(os.listdir(PROJECTS_DIR)):
        pdir = _project_dir(name)
        if os.path.isdir(pdir) and os.path.isfile(_prefs_path(name)):
            prefs = _load_yaml(_prefs_path(name))
            videos_dir = os.path.join(pdir, "videos")
            video_count = 0
            if os.path.isdir(videos_dir):
                video_count = sum(
                    1 for v in os.listdir(videos_dir)
                    if os.path.isdir(os.path.join(videos_dir, v))
                )
            projects.append({
                "name": name,
                "category": prefs.get("project", {}).get("category"),
                "orientation": prefs.get("project", {}).get("orientation"),
                "resolution": prefs.get("video", {}).get("resolution"),
                "video_count": video_count,
            })
    cli_envelope.emit_ok(data={"projects": projects}, fmt=args.format)


def cmd_show(args):
    ppath = _prefs_path(args.name)
    if not os.path.isfile(ppath):
        cli_envelope.emit_usage_error(f"Project '{args.name}' not found.", fmt=args.format)
    cli_envelope.emit_ok(data=_load_yaml(ppath), fmt=args.format)


def cmd_set(args):
    ppath = _prefs_path(args.name)
    if not os.path.isfile(ppath):
        cli_envelope.emit_usage_error(f"Project '{args.name}' not found.", fmt=args.format)
    prefs = _load_yaml(ppath)
    value = args.value
    # Try parsing ints/floats; otherwise leave as string.
    try:
        if "." in value:
            value = float(value)
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            value = int(value)
    except (ValueError, AttributeError):
        pass
    if value in ("null", "None"):
        value = None
    if value in ("true", "True"):
        value = True
    if value in ("false", "False"):
        value = False
    _set_nested(prefs, args.key, value)
    _dump_yaml(ppath, prefs)
    cli_envelope.emit_ok(
        data={args.key: value},
        message=f"Set {args.key} = {value!r} in {args.name}.",
        fmt=args.format,
    )


def cmd_video(args):
    vdir = os.path.join(_project_dir(args.name), "videos", args.video)
    if os.path.exists(vdir):
        cli_envelope.emit_usage_error(
            f"Video '{args.video}' already exists at {vdir}",
            fmt=args.format,
        )
    os.makedirs(vdir, exist_ok=False)
    os.makedirs(os.path.join(vdir, "assets"), exist_ok=True)
    cli_envelope.emit_ok(
        data={"video_dir": vdir},
        message=f"Video '{args.video}' scaffold created under '{args.name}'.",
        fmt=args.format,
    )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    {
        "create": cmd_create,
        "list": cmd_list,
        "show": cmd_show,
        "set": cmd_set,
        "video": cmd_video,
    }[args.action](args)


if __name__ == "__main__":
    main()
