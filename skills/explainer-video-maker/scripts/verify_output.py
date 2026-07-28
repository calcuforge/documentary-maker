#!/usr/bin/env python3
"""End-of-pipeline acceptance gate.

Checks:
    - every scene has scenes/{scene}/scene.mp4 rendered.
    - per-scene timing.json matches the scene narration.wav within 0.5s.
    - root timing.json exists and total_duration matches narration_audio.wav within 0.5s.
    - final_video.mp4 (or video_with_bgm.mp4 / output.mp4) exists and plays.
    - video resolution matches project config (1920x1080 / 3840x2160 / 1080x1920).
    - audio-video duration drift < 0.5s.
    - assets/manifest.json validates (resolved entries have files on disk).
    - video_info.yaml written by Step 11.

Exit codes:
    0 — green
    1 — failure (blocking)
    2 — warnings (still acceptable)
"""
import argparse
import json
import os
import subprocess
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DOC_ROOT = os.path.normpath(os.path.join(SKILL_DIR, "..", ".."))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import script_schema  # noqa: E402


def ffprobe_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def ffprobe_streams(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "stream=width,height,codec_type", "-of", "json", path],
            capture_output=True, text=True, timeout=15,
        )
        return json.loads(r.stdout or "{}")
    except Exception:
        return None


def build_parser():
    parser = argparse.ArgumentParser(description="End-of-pipeline acceptance gate.")
    cli_envelope.add_format_arg(parser)
    parser.add_argument("--project", required=True)
    parser.add_argument("--video", required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    vdir = os.path.join(DOC_ROOT, "projects", args.project, "videos", args.video)
    if not os.path.isdir(vdir):
        cli_envelope.emit_usage_error(f"Video dir not found: {vdir}", fmt=args.format)

    prefs_path = os.path.join(DOC_ROOT, "projects", args.project, "project_prefs.yaml")
    with open(prefs_path, "r", encoding="utf-8") as f:
        prefs = yaml.safe_load(f) or {}
    orientation = prefs.get("project", {}).get("orientation", "horizontal")
    resolution = prefs.get("video", {}).get("resolution", "1080p")

    expected_dims = {
        ("horizontal", "1080p"): (1920, 1080),
        ("horizontal", "4k"): (3840, 2160),
        ("vertical", "1080p"): (1080, 1920),
        ("vertical", "4k"): (2160, 3840),
    }.get((orientation, resolution))

    problems = []
    warnings = []

    # scene artifacts: every scene rendered + per-scene clock drift
    script_path = os.path.join(vdir, "narration_script.yaml")
    if not os.path.isfile(script_path):
        problems.append("narration_script.yaml missing")
    else:
        try:
            script = script_schema.load_script(script_path)
            for sc in script["scenes"]:
                name = sc["name"]
                scene_dir = os.path.join(vdir, "scenes", name)
                scene_mp4 = os.path.join(scene_dir, "scene.mp4")
                scene_wav = os.path.join(scene_dir, "narration.wav")
                scene_tj = os.path.join(scene_dir, "timing.json")
                if not os.path.isfile(scene_mp4):
                    problems.append(f"scene '{name}': scene.mp4 not rendered")
                if not os.path.isfile(scene_wav) or not os.path.isfile(scene_tj):
                    problems.append(f"scene '{name}': narration.wav/timing.json missing")
                    continue
                with open(scene_tj, "r", encoding="utf-8") as f:
                    st = json.load(f)
                wav_dur = ffprobe_duration(scene_wav)
                if wav_dur is None:
                    problems.append(f"scene '{name}': ffprobe could not read narration.wav")
                elif abs(st.get("total_duration", 0) - wav_dur) > 0.5:
                    problems.append(
                        f"scene '{name}': timing drift "
                        f"{abs(st.get('total_duration', 0) - wav_dur):.2f}s > 0.5s")
        except script_schema.SchemaError as exc:
            problems.append(f"narration_script.yaml: {exc}")

    # timing.json + audio drift
    timing_path = os.path.join(vdir, "timing.json")
    audio_path = os.path.join(vdir, "narration_audio.wav")
    if not os.path.isfile(timing_path):
        problems.append("timing.json missing")
    if not os.path.isfile(audio_path):
        problems.append("narration_audio.wav missing")
    if os.path.isfile(timing_path) and os.path.isfile(audio_path):
        with open(timing_path, "r", encoding="utf-8") as f:
            timing = json.load(f)
        wav_dur = ffprobe_duration(audio_path)
        if wav_dur is None:
            problems.append("ffprobe could not read narration_audio.wav")
        else:
            drift = abs(timing.get("total_duration", 0) - wav_dur)
            if drift > 0.5:
                problems.append(f"timing drift {drift:.2f}s > 0.5s")

    # final video
    final_path = os.path.join(vdir, "final_video.mp4")
    bgm_path = os.path.join(vdir, "video_with_bgm.mp4")
    raw_path = os.path.join(vdir, "output.mp4")
    chosen_final = final_path if os.path.isfile(final_path) else (
        bgm_path if os.path.isfile(bgm_path) else raw_path
    )
    if not os.path.isfile(chosen_final):
        problems.append("final video missing (no final_video.mp4 / video_with_bgm.mp4 / output.mp4)")
    else:
        streams = ffprobe_streams(chosen_final) or {}
        vstream = next(
            (s for s in streams.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        if vstream is None:
            problems.append("final video has no video stream")
        elif expected_dims:
            w, h = int(vstream.get("width", 0)), int(vstream.get("height", 0))
            if (w, h) != expected_dims:
                problems.append(
                    f"resolution mismatch: got {w}x{h}, expected {expected_dims[0]}x{expected_dims[1]}"
                )
        vid_dur = ffprobe_duration(chosen_final)
        if vid_dur is not None and os.path.isfile(audio_path):
            wav_dur = ffprobe_duration(audio_path)
            if wav_dur is not None and abs(vid_dur - wav_dur) > 0.5:
                problems.append(f"video/audio drift {abs(vid_dur-wav_dur):.2f}s > 0.5s")

    # manifest validate
    manifest_path = os.path.join(vdir, "assets", "manifest.json")
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for a in manifest.get("assets", []):
            if a.get("status") == "resolved" and a.get("path"):
                full = os.path.join(vdir, "assets", a["path"])
                if not os.path.isfile(full):
                    problems.append(f"manifest entry {a['id']}: resolved path missing on disk")

    # video_info.yaml
    info_path = os.path.join(vdir, "video_info.yaml")
    if not os.path.isfile(info_path):
        warnings.append("video_info.yaml missing — Step 11 metadata not written")

    if problems:
        cli_envelope.emit_error(
            "verify_failed",
            f"{len(problems)} blocking problem(s).",
            details={"problems": problems, "warnings": warnings},
            fmt=args.format, exit_code=1,
        )
    if warnings:
        cli_envelope.emit_warning(
            data={"warnings": warnings},
            message=f"{len(warnings)} warning(s) (acceptable).",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data={"final_video": chosen_final, "warnings": warnings},
        message="All checks passed.",
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
