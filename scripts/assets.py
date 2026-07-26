#!/usr/bin/env python3
"""Asset manifest management.

Mirrors video-podcast-maker's manifest schema so the shared
remotion-video-template's `useAssets` / `AssetImage` / `AssetVideo` work
unchanged.

Commands:
    assets init   --video-dir <dir>
    assets add    --video-dir <dir>
                  --id <id> --section <section> --type image|video|audio|text
                  --role background|inline|broll|overlay|bgm|sfx
                  --source user|t2i|i2i|t2v|i2v|flf2v|multi_scene_i2v|stock|text
                  [--file <path>]            # for user-supplied assets: copy into assets/
                  [--path <rel>]             # if file already inside assets/
                  [--license <s>] [--credit <s>]
                  [--prompt <s>] [--workflow <id>] [--status planned|resolved|pending_confirmation]
                  [--upscale-target 1080p|4k]
    assets list   --video-dir <dir>
    assets update --video-dir <dir> --id <id>  [--status <s>] [--path <rel>]
                  [--upscaled <bool>]
    assets validate --video-dir <dir>
"""
import argparse
import json
import os
import shutil
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402

MANIFEST_REL = "assets/manifest.json"


def _manifest_path(video_dir):
    return os.path.join(video_dir, MANIFEST_REL)


def _load_manifest(video_dir):
    path = _manifest_path(video_dir)
    if not os.path.isfile(path):
        return {"schema_version": 1, "assets": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "assets" not in data:
        data["assets"] = []
    if "schema_version" not in data:
        data["schema_version"] = 1
    return data


def _save_manifest(video_dir, manifest):
    path = _manifest_path(video_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def build_parser():
    parser = argparse.ArgumentParser(description="Asset manifest management.")
    cli_envelope.add_format_arg(parser)
    sub = parser.add_subparsers(dest="action", required=True)

    p_init = sub.add_parser("init", help="Create an empty manifest.")
    p_init.add_argument("--video-dir", required=True)

    p_add = sub.add_parser("add", help="Register a new asset.")
    p_add.add_argument("--video-dir", required=True)
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--section", required=True)
    p_add.add_argument("--type", required=True,
                       choices=["image", "video", "audio", "text"])
    p_add.add_argument("--role", required=True,
                       choices=["background", "inline", "broll", "overlay", "bgm", "sfx"])
    p_add.add_argument("--source", required=True,
                       choices=["user", "t2i", "i2i", "t2v", "i2v", "flf2v",
                                "multi_scene_i2v", "stock", "text"])
    p_add.add_argument("--file", default=None,
                       help="Local file to copy into assets/ (for user-supplied assets).")
    p_add.add_argument("--path", default=None,
                       help="Relative path inside assets/ (if file already there).")
    p_add.add_argument("--license", default=None)
    p_add.add_argument("--credit", default=None)
    p_add.add_argument("--prompt", default=None)
    p_add.add_argument("--workflow", default=None)
    p_add.add_argument("--status", default="planned",
                       choices=["planned", "pending_confirmation", "resolved"])
    p_add.add_argument("--upscale-target", default=None, choices=["1080p", "4k"])
    p_add.add_argument("--upscaled", default=False, action="store_true")

    p_list = sub.add_parser("list", help="List assets.")
    p_list.add_argument("--video-dir", required=True)

    p_update = sub.add_parser("update", help="Update an existing asset entry.")
    p_update.add_argument("--video-dir", required=True)
    p_update.add_argument("--id", required=True)
    p_update.add_argument("--status", default=None,
                          choices=["planned", "pending_confirmation", "resolved"])
    p_update.add_argument("--path", default=None)
    p_update.add_argument("--upscaled", default=None, action="store_true")
    p_update.add_argument("--no-upscaled", dest="upscaled", action="store_false")

    p_validate = sub.add_parser("validate", help="Validate manifest integrity.")
    p_validate.add_argument("--video-dir", required=True)

    return parser


def cmd_init(args):
    _save_manifest(args.video_dir, {"schema_version": 1, "assets": []})
    cli_envelope.emit_ok(
        data={"manifest": _manifest_path(args.video_dir)},
        message=f"Initialized manifest at {_manifest_path(args.video_dir)}",
        fmt=args.format,
    )


def cmd_add(args):
    manifest = _load_manifest(args.video_dir)
    assets_dir = os.path.join(args.video_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    rel_path = args.path
    if args.file and not rel_path:
        ext = os.path.splitext(args.file)[1] or ""
        rel_path = f"{args.id}{ext}"
        dest = os.path.join(assets_dir, rel_path)
        shutil.copy(args.file, dest)
    if any(a["id"] == args.id for a in manifest["assets"]):
        cli_envelope.emit_usage_error(
            f"Asset id '{args.id}' already exists in manifest.",
            fmt=args.format)
    entry = {
        "id": args.id,
        "section": args.section,
        "type": args.type,
        "role": args.role,
        "source": args.source,
        "status": args.status,
        "path": rel_path,
        "license": args.license,
        "credit": args.credit,
        "prompt": args.prompt,
        "workflow": args.workflow,
        "upscale_target": args.upscale_target,
        "upscaled": bool(args.upscaled),
    }
    manifest["assets"].append(entry)
    _save_manifest(args.video_dir, manifest)
    cli_envelope.emit_ok(
        data={"entry": entry, "manifest": _manifest_path(args.video_dir)},
        message=f"Added asset '{args.id}' ({args.source}/{args.type}).",
        fmt=args.format,
    )


def cmd_list(args):
    manifest = _load_manifest(args.video_dir)
    cli_envelope.emit_ok(data=manifest, fmt=args.format)


def cmd_update(args):
    manifest = _load_manifest(args.video_dir)
    found = None
    for a in manifest["assets"]:
        if a["id"] == args.id:
            found = a
            break
    if found is None:
        cli_envelope.emit_usage_error(
            f"Asset id '{args.id}' not found.", fmt=args.format)
    if args.status:
        found["status"] = args.status
    if args.path:
        found["path"] = args.path
    if args.upscaled is not None:
        found["upscaled"] = bool(args.upscaled)
    _save_manifest(args.video_dir, manifest)
    cli_envelope.emit_ok(
        data={"entry": found},
        message=f"Updated asset '{args.id}'.",
        fmt=args.format,
    )


def cmd_validate(args):
    manifest = _load_manifest(args.video_dir)
    problems = []
    asset_ids = set()
    for a in manifest["assets"]:
        if a["id"] in asset_ids:
            problems.append(f"duplicate id: {a['id']}")
        asset_ids.add(a["id"])
        if a.get("status") == "resolved" and not a.get("path"):
            problems.append(f"{a['id']}: resolved but no path")
        if a.get("status") == "resolved" and a.get("path"):
            full = os.path.join(args.video_dir, "assets", a["path"])
            if not os.path.isfile(full):
                problems.append(f"{a['id']}: resolved path missing on disk: {a['path']}")
    if problems:
        cli_envelope.emit_warning(
            data={"problems": problems, "manifest": manifest},
            message=f"{len(problems)} validation problem(s).",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data={"assets": len(manifest['assets']), "manifest": manifest},
        message="Manifest OK.",
        fmt=args.format,
    )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    {
        "init": cmd_init,
        "add": cmd_add,
        "list": cmd_list,
        "update": cmd_update,
        "validate": cmd_validate,
    }[args.action](args)


if __name__ == "__main__":
    main()
