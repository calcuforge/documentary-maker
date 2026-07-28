#!/usr/bin/env python3
"""Merge per-scene renders into output.mp4 (ordered, lossless).

Scenes are rendered independently (scenes/{scene}/scene.mp4). This script
concatenates them in narration_script.yaml order using
`ffmpeg -f concat -c copy` — no re-encode, so it is fast and lossless.

Lossless concat requires every scene render to share identical encoding
parameters (same composition id, fps, bitrate settings produce this
naturally). The script ffprobes each scene file and verifies:
    video: codec_name, width, height, pix_fmt, r_frame_rate
    audio: codec_name, sample_rate, channels
before concatenating. On mismatch it fails with a diff rather than
silently re-encoding.

Usage:
    python3 scripts/cli.py merge --project P --video V
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DOC_ROOT = os.path.normpath(os.path.join(SKILL_DIR, "..", ".."))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import script_schema  # noqa: E402

VIDEO_KEYS = ["codec_name", "width", "height", "pix_fmt", "r_frame_rate"]
AUDIO_KEYS = ["codec_name", "sample_rate", "channels"]


def ffprobe_params(path):
    """Return (video_params, audio_params) dicts for a media file."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,"
             "sample_rate,channels",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(r.stdout or "{}")
    except Exception as exc:
        return None, None, str(exc)
    vstream = next((s for s in data.get("streams", [])
                    if s.get("codec_type") == "video"), None)
    astream = next((s for s in data.get("streams", [])
                    if s.get("codec_type") == "audio"), None)
    vparams = {k: vstream.get(k) for k in VIDEO_KEYS} if vstream else None
    aparams = {k: astream.get(k) for k in AUDIO_KEYS} if astream else None
    return vparams, aparams, None


def build_parser():
    parser = argparse.ArgumentParser(
        description="Concatenate rendered scenes into output.mp4 (lossless).")
    cli_envelope.add_format_arg(parser)
    parser.add_argument("--project", required=True)
    parser.add_argument("--video", required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    video_dir = os.path.join(DOC_ROOT, "projects", args.project, "videos", args.video)
    if not os.path.isdir(video_dir):
        cli_envelope.emit_usage_error(f"Video dir not found: {video_dir}", fmt=args.format)

    try:
        script = script_schema.load_script(os.path.join(video_dir, "narration_script.yaml"))
    except script_schema.SchemaError as exc:
        cli_envelope.emit_usage_error(str(exc), fmt=args.format)

    # 1. Collect scene renders in script order.
    scene_files = []
    missing = []
    for sc in script["scenes"]:
        path = os.path.join(video_dir, "scenes", sc["name"], "scene.mp4")
        if not os.path.isfile(path):
            missing.append(sc["name"])
        scene_files.append((sc["name"], path))
    if missing:
        cli_envelope.emit_usage_error(
            f"Scene render(s) missing: {missing}. Render each scene first "
            "(npx remotion render .../scenes/<scene>/entry.tsx ...).",
            fmt=args.format)

    # 2. Verify encoding parameter consistency.
    params = {}
    probe_errors = []
    for name, path in scene_files:
        vparams, aparams, err = ffprobe_params(path)
        if err or vparams is None:
            probe_errors.append(f"{name}: ffprobe failed ({err or 'no video stream'})")
            continue
        params[name] = (vparams, aparams)
    if probe_errors:
        cli_envelope.emit_error(
            "ffprobe_failed", "Could not probe scene render(s).",
            details={"errors": probe_errors}, fmt=args.format, exit_code=1,
        )

    first_name = scene_files[0][0]
    ref_v, ref_a = params[first_name]
    mismatches = []
    for name, _ in scene_files[1:]:
        v, a = params[name]
        for k in VIDEO_KEYS:
            if v.get(k) != ref_v.get(k):
                mismatches.append(
                    f"{name}: video {k}={v.get(k)} differs from "
                    f"{first_name} {k}={ref_v.get(k)}")
        if ref_a is not None or a is not None:
            for k in AUDIO_KEYS:
                if (a or {}).get(k) != (ref_a or {}).get(k):
                    mismatches.append(
                        f"{name}: audio {k}={(a or {}).get(k)} differs from "
                        f"{first_name} {k}={(ref_a or {}).get(k)}")
    if mismatches:
        cli_envelope.emit_error(
            "scene_encoding_mismatch",
            "Scene renders have inconsistent encoding parameters; lossless "
            "concat (-c copy) is not possible. Re-render all scenes with the "
            "same composition id and render flags.",
            details={"mismatches": mismatches}, fmt=args.format, exit_code=1,
        )

    # 3. Write concat list (absolute paths, forward slashes for ffmpeg).
    concat_list = os.path.join(video_dir, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for _, path in scene_files:
            f.write(f"file '{os.path.abspath(path).replace(os.sep, '/')}'\n")

    # 4. Concatenate losslessly.
    output = os.path.join(video_dir, "output.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy", output],
            check=True, capture_output=True, timeout=1800,
        )
    except subprocess.CalledProcessError as exc:
        cli_envelope.emit_error(
            "ffmpeg_failed",
            f"Scene concat failed: {(exc.stderr or b'').decode('utf-8', 'replace')[-800:]}",
            fmt=args.format, exit_code=1,
        )

    cli_envelope.emit_ok(
        data={
            "output": output,
            "scenes": [name for name, _ in scene_files],
            "encoding": {"video": ref_v, "audio": ref_a},
        },
        message=f"Merged {len(scene_files)} scene(s) → {output} (-c copy, lossless).",
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
