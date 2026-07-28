#!/usr/bin/env python3
"""Audit audio-master-clock alignment (scene level + video level).

With per-scene TTS, each scene's timing.json.total_duration comes directly
from ffprobing that scene's narration.wav, so drift should be ~0. This audit
catches the cases where artifacts get out of sync:

    - scene timing.json vs scene narration.wav drift > threshold
      (timing.json stale — re-run `tts run --scene <name>`);
    - rendered scene.mp4 vs scene narration.wav drift > threshold
      (render used stale timing — re-run compose + render);
    - video-level timing.json vs merged narration_audio.wav drift > threshold
      (merge stale — re-run `tts merge`).

Exit 0 = clean; warning envelope = drifts found (review before publishing);
error envelope = required artifacts missing.

Usage:
    python3 scripts/cli.py audit beats --video-dir <dir> [--threshold 0.5]
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import script_schema  # noqa: E402

DRIFT_THRESHOLD_S = 0.5


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


def build_parser():
    parser = argparse.ArgumentParser(description="Audit scene timing drift.")
    cli_envelope.add_format_arg(parser)
    # Optional positional so both `audit beats --video-dir X` (via cli.py)
    # and direct `audit_beat_sync.py --video-dir X` work.
    parser.add_argument("action", nargs="?", choices=["beats"], default="beats")
    parser.add_argument("--video-dir", required=True)
    parser.add_argument("--threshold", type=float, default=DRIFT_THRESHOLD_S,
                        help="Drift threshold in seconds (default 0.5).")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    vdir = args.video_dir
    script_path = os.path.join(vdir, "narration_script.yaml")
    if not os.path.isfile(script_path):
        cli_envelope.emit_usage_error(
            f"narration_script.yaml not found: {script_path}", fmt=args.format)
    try:
        script = script_schema.load_script(script_path)
    except script_schema.SchemaError as exc:
        cli_envelope.emit_usage_error(str(exc), fmt=args.format)

    flagged = []
    missing = []

    # Scene-level checks.
    for sc in script["scenes"]:
        name = sc["name"]
        scene_dir = os.path.join(vdir, "scenes", name)
        timing_path = os.path.join(scene_dir, "timing.json")
        wav_path = os.path.join(scene_dir, "narration.wav")
        mp4_path = os.path.join(scene_dir, "scene.mp4")

        if not os.path.isfile(timing_path) or not os.path.isfile(wav_path):
            missing.append(f"scene '{name}': timing.json/narration.wav missing (run tts)")
            continue
        with open(timing_path, "r", encoding="utf-8") as f:
            timing = json.load(f)
        wav_dur = ffprobe_duration(wav_path)
        if wav_dur is None:
            missing.append(f"scene '{name}': ffprobe could not read narration.wav")
            continue
        drift = abs(timing.get("total_duration", 0) - wav_dur)
        if drift > args.threshold:
            flagged.append({
                "scope": f"scene:{name}",
                "check": "timing.json vs narration.wav",
                "timing_s": round(timing.get("total_duration", 0), 2),
                "audio_s": round(wav_dur, 2),
                "drift_s": round(drift, 2),
            })
        if os.path.isfile(mp4_path):
            mp4_dur = ffprobe_duration(mp4_path)
            if mp4_dur is not None:
                drift = abs(mp4_dur - wav_dur)
                if drift > args.threshold:
                    flagged.append({
                        "scope": f"scene:{name}",
                        "check": "scene.mp4 vs narration.wav",
                        "video_s": round(mp4_dur, 2),
                        "audio_s": round(wav_dur, 2),
                        "drift_s": round(drift, 2),
                    })

    # Video-level check (only when the merged artifacts exist).
    root_timing = os.path.join(vdir, "timing.json")
    root_wav = os.path.join(vdir, "narration_audio.wav")
    if os.path.isfile(root_timing) and os.path.isfile(root_wav):
        with open(root_timing, "r", encoding="utf-8") as f:
            timing = json.load(f)
        wav_dur = ffprobe_duration(root_wav)
        if wav_dur is not None:
            drift = abs(timing.get("total_duration", 0) - wav_dur)
            if drift > args.threshold:
                flagged.append({
                    "scope": "video",
                    "check": "timing.json vs narration_audio.wav",
                    "timing_s": round(timing.get("total_duration", 0), 2),
                    "audio_s": round(wav_dur, 2),
                    "drift_s": round(drift, 2),
                })

    if missing:
        cli_envelope.emit_warning(
            data={"missing": missing, "flagged": flagged},
            message=f"{len(missing)} scene artifact(s) not ready yet.",
            fmt=args.format,
        )
    if flagged:
        cli_envelope.emit_warning(
            data={"flagged": flagged, "threshold_s": args.threshold},
            message=f"{len(flagged)} drift(s) > {args.threshold}s.",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data={"flagged": [], "threshold_s": args.threshold},
        message="No drift exceeded threshold.",
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
