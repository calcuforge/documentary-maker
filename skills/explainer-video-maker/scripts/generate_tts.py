#!/usr/bin/env python3
"""Per-scene TTS generation + merge.

Narration is synthesized **per scene** (each scene is one TTS job), so a
scene's narration can be regenerated without touching the rest of the video.
Every scene WAV is normalized to 48 kHz mono pcm_s16le so the merged track
can be built with `ffmpeg -f concat -c copy` (lossless, no re-encode).

Commands:
    tts synth --prefs PATH --text TEXT --voice-file PATH [--speed FLOAT]
              [--output PATH]
        Synthesize a single text string to audio using the backend configured
        in project_prefs.yaml (tts.backend). Routes to comfyui_indextts or
        http_server automatically. Output is normalized to 48 kHz mono WAV.

    tts run --project P --video V [--scene NAME] [--backend B]
        Synthesize one scene (--scene) or ALL scenes (no --scene).
        Per scene output:
            scenes/{scene}/narration.wav   (48 kHz mono)
            scenes/{scene}/narration.srt   (scene-relative cues)
            scenes/{scene}/timing.json     (shots distribution)
        Without --scene, automatically runs the merge afterwards.

    tts merge --project P --video V
        Concatenate scene WAVs → narration_audio.wav (video root),
        merge scene SRTs with offsets → narration_audio.srt,
        aggregate scene timings → timing.json (video-level summary).

Backends:
    comfyui_indextts — `comfyui-scheduler run -w index_tts_2 -i ...`
    http_server      — multipart/form-data POST to tts.http.url
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import requests
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import estimate_timing  # noqa: E402
import script_schema  # noqa: E402
import workspace  # noqa: E402

AUDIO_FORMAT_ARGS = ["-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le"]

SRT_TIME_RE = re.compile(
    r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)")


# ── loading helpers ─────────────────────────────────────────────────────────

def load_project_prefs(project_name, fmt):
    ppath = workspace.prefs_path(project_name)
    if not os.path.isfile(ppath):
        cli_envelope.emit_usage_error(
            f"Project '{project_name}' not found (no prefs at {ppath}).", fmt=fmt)
    with open(ppath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_voice_file(prefs, project_name, fmt):
    vf = prefs.get("tts", {}).get("voice_file")
    if not vf:
        default_vf = os.path.normpath(
            os.path.join(workspace.project_dir(project_name), "voice_reference.wav"))
        if os.path.isfile(default_vf):
            vf = default_vf
            prefs.setdefault("tts", {})["voice_file"] = vf
    if not vf or not os.path.isfile(vf):
        cli_envelope.emit_usage_error(
            f"tts.voice_file not found or does not exist: {vf}. "
            "Run voice design (Step 0) first, or set tts.voice_file manually.",
            fmt=fmt)
    return vf


def normalize_wav(src, dest, fmt):
    """Convert/resample any audio file to 48 kHz mono pcm_s16le WAV.

    Required so `ffmpeg -f concat -c copy` can stitch scene WAVs losslessly.
    """
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src] + AUDIO_FORMAT_ARGS + [dest],
            check=True, capture_output=True, timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        cli_envelope.emit_error(
            "ffmpeg_failed",
            f"Failed to normalize {src} → {dest}: "
            f"{(exc.stderr or b'').decode('utf-8', 'replace')[-500:]}",
            fmt=fmt, exit_code=1,
        )
    if os.path.abspath(src) != os.path.abspath(dest) and os.path.isfile(src):
        os.remove(src)


def synth_text(text, prefs, voice_file, output_path, fmt):
    """Synthesize *text* to audio using the backend from *prefs*.

    Reads ``tts.backend`` from *prefs* (default ``comfyui_indextts``), calls
    the corresponding backend, and writes a 48 kHz mono pcm_s16le WAV to
    *output_path*.  *voice_file* is the reference audio for voice cloning.

    Returns *output_path* on success.
    """
    backend = prefs.get("tts", {}).get("backend", "comfyui_indextts")
    tmp_dir = tempfile.mkdtemp(prefix="tts_synth_")
    try:
        if backend == "comfyui_indextts":
            raw = synth_comfyui(text, prefs, voice_file, tmp_dir, fmt)
        elif backend == "http_server":
            body = synth_http(text, prefs, voice_file, fmt)
            raw = os.path.join(tmp_dir, "response.bin")
            with open(raw, "wb") as f:
                f.write(body)
        else:
            cli_envelope.emit_usage_error(f"Unknown TTS backend: {backend}", fmt=fmt)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        normalize_wav(raw, output_path, fmt)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return output_path


# ── synthesis backends (single scene) ───────────────────────────────────────

def _run_workflow_and_capture(workflow_id, inputs, dest_dir, fmt):
    """Run a comfyui-scheduler workflow and download its output files."""
    import shutil
    if not shutil.which("comfyui-scheduler"):
        cli_envelope.emit_error(
            "prereqs_failed", "comfyui-scheduler is not on PATH.",
            fmt=fmt, exit_code=1,
        )
    argv = ["comfyui-scheduler", "run", "-w", workflow_id, "-i", json.dumps(inputs)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        cli_envelope.emit_error(
            "workflow_failed",
            f"comfyui-scheduler exited {result.returncode}: {result.stderr.strip()}",
            details={"stdout": result.stdout, "stderr": result.stderr},
            fmt=fmt, exit_code=1,
        )
    envelope = json.loads(result.stdout)
    data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
    files_out = []
    for f in data.get("files", []):
        url = f.get("url")
        kind = f.get("kind", "audio")
        if not url:
            continue
        try:
            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()
        except Exception as exc:
            cli_envelope.emit_error(
                "download_failed", f"Failed to download {url}: {exc}",
                fmt=fmt, exit_code=1,
            )
        from urllib.parse import urlsplit
        filename = os.path.basename(urlsplit(url).path) or f"output_{kind}.bin"
        local = os.path.join(dest_dir, filename)
        with open(local, "wb") as fh:
            for chunk in resp.iter_content(8192):
                fh.write(chunk)
        files_out.append({"kind": kind, "url": url, "filename": filename, "local_path": local})
    return {"workflow_id": workflow_id, "task_id": data.get("task_id"),
            "prompt_id": data.get("prompt_id"),
            "output_type": data.get("output_type"),
            "files": files_out}


def synth_comfyui(text, prefs, voice_file, tmp_dir, fmt):
    workflow_id = prefs.get("workflows", {}).get("tts", "index_tts_2")
    inputs = {"content": text, "voice_file": voice_file}
    result = _run_workflow_and_capture(workflow_id, inputs, tmp_dir, fmt)
    audio_path = None
    for f in result.get("files", []):
        if f.get("kind") == "audio":
            audio_path = f.get("local_path")
            break
    if audio_path is None:
        for f in result.get("files", []):
            audio_path = f.get("local_path")
            if audio_path:
                break
    if audio_path is None:
        cli_envelope.emit_error(
            "workflow_failed", "index_tts workflow produced no audio file.",
            details=result, fmt=fmt, exit_code=1,
        )
    return audio_path


def synth_http(text, prefs, voice_file, fmt):
    cfg = prefs.get("tts", {}).get("http", {})
    url_raw = cfg.get("url", "")
    if not url_raw:
        cli_envelope.emit_usage_error(
            "tts.http.url is required when backend=http_server.", fmt=fmt)
    url = os.path.expandvars(url_raw)
    if "${BACKEND_PROXY_ENDPOINT}" in url or not url.startswith("http"):
        cli_envelope.emit_usage_error(
            f"tts.http.url could not be resolved: {url_raw}. "
            "Set the BACKEND_PROXY_ENDPOINT env var.",
            fmt=fmt)
    speed = cfg.get("speed", 1.0)
    data = {"input": text, "speed": str(speed)}
    with open(voice_file, "rb") as vfh:
        files = {"voice_file": (os.path.basename(voice_file), vfh, "audio/wav")}
        try:
            resp = requests.post(url, data=data, files=files, timeout=900)
            resp.raise_for_status()
        except Exception as exc:
            cli_envelope.emit_error(
                "http_tts_failed", f"HTTP TTS request failed: {exc}",
                details={"status_code": getattr(resp, "status_code", None)},
                fmt=fmt, exit_code=1,
            )
    return resp.content


# ── per-scene pipeline ──────────────────────────────────────────────────────

def synth_scene(scene, prefs, voice_file, video_dir, backend, fmt):
    """One scene → scenes/{name}/narration.wav (+ srt + timing via estimate)."""
    name = scene["name"]
    text = (scene.get("narration") or "").strip()
    if not text:
        cli_envelope.emit_usage_error(
            f"Scene '{name}' has no narration text. Every scene needs narration "
            "(it drives the scene's audio-master clock).",
            fmt=fmt)
    scene_dir = os.path.join(video_dir, "scenes", name)
    tmp_dir = os.path.join(scene_dir, "_tts_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    final_path = os.path.join(scene_dir, "narration.wav")

    if backend == "comfyui_indextts":
        raw = synth_comfyui(text, prefs, voice_file, tmp_dir, fmt)
        normalize_wav(raw, final_path, fmt)
    elif backend == "http_server":
        body = synth_http(text, prefs, voice_file, fmt)
        raw = os.path.join(tmp_dir, "response.bin")
        with open(raw, "wb") as f:
            f.write(body)
        normalize_wav(raw, final_path, fmt)
    else:
        cli_envelope.emit_usage_error(f"Unknown TTS backend: {backend}", fmt=fmt)

    # Remove the tmp dir if empty (downloads already moved into final_path).
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    fps = prefs.get("video", {}).get("fps", 30)
    estimate_timing.main([
        "--video-dir", video_dir,
        "--scene", name,
        "--fps", str(fps),
        "--format", fmt,
    ])
    return final_path


# ── merge ───────────────────────────────────────────────────────────────────

def parse_srt(path):
    """Parse an SRT file into [(start_s, end_s, text), ...]."""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        time_idx = None
        match = None
        for i, ln in enumerate(lines):
            match = SRT_TIME_RE.search(ln)
            if match:
                time_idx = i
                break
        if match is None:
            continue
        g = [int(x) for x in match.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        text = "\n".join(lines[time_idx + 1:])
        blocks.append((start, end, text))
    return blocks


def merge_scenes(script, prefs, video_dir, fmt):
    """Concatenate scene WAVs/SRTs/timings into the video-level artifacts."""
    fps = prefs.get("video", {}).get("fps", 30)
    scenes = script["scenes"]

    # 1. Verify every scene has audio + timing.
    missing = []
    scene_timings = []
    for sc in scenes:
        wav = os.path.join(video_dir, "scenes", sc["name"], "narration.wav")
        tj = os.path.join(video_dir, "scenes", sc["name"], "timing.json")
        if not os.path.isfile(wav) or not os.path.isfile(tj):
            missing.append(sc["name"])
            continue
        with open(tj, "r", encoding="utf-8") as f:
            scene_timings.append((sc, json.load(f)))
    if missing:
        cli_envelope.emit_usage_error(
            f"Scene(s) missing narration.wav/timing.json: {missing}. "
            "Run `tts run` (all scenes) or `tts run --scene <name>` for each first.",
            fmt=fmt)

    # 2. Concatenate WAVs losslessly (-c copy; all scenes are 48k mono).
    concat_list = os.path.join(video_dir, "concat_audio.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for sc, _ in scene_timings:
            wav = os.path.join(video_dir, "scenes", sc["name"], "narration.wav")
            f.write(f"file '{os.path.abspath(wav).replace(os.sep, '/')}'\n")
    merged_wav = os.path.join(video_dir, "narration_audio.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy", merged_wav],
            check=True, capture_output=True, timeout=600,
        )
    except subprocess.CalledProcessError as exc:
        cli_envelope.emit_error(
            "ffmpeg_failed",
            "Scene WAV concat failed. Scene WAVs must share sample rate / "
            "channels / codec (tts run normalizes them to 48 kHz mono): "
            f"{(exc.stderr or b'').decode('utf-8', 'replace')[-500:]}",
            fmt=fmt, exit_code=1,
        )

    # 3. Merge SRTs with per-scene offsets; renumber sequentially.
    srt_lines = []
    idx = 1
    offset = 0.0
    for sc, st in scene_timings:
        scene_dur = st.get("total_duration", 0.0)
        cues = parse_srt(os.path.join(video_dir, "scenes", sc["name"], "narration.srt"))
        for start, end, text in cues:
            srt_lines.append(str(idx))
            srt_lines.append(
                f"{estimate_timing._fmt_srt_time(offset + start)} --> "
                f"{estimate_timing._fmt_srt_time(offset + end)}")
            srt_lines.append(text)
            srt_lines.append("")
            idx += 1
        offset += scene_dur
    merged_srt = os.path.join(video_dir, "narration_audio.srt")
    with open(merged_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    # 4. Aggregate video-level timing.json.
    total_duration = sum(st.get("total_duration", 0.0) for _, st in scene_timings)
    total_frames = sum(st.get("total_frames", 0) for _, st in scene_timings)
    chapter_acc = {}
    scene_blocks = []
    cumulative = 0.0
    for sc, st in scene_timings:
        dur = st.get("total_duration", 0.0)
        start = round(cumulative, 3)
        end = round(cumulative + dur, 3)
        scene_blocks.append({
            "name": sc["name"],
            "label": sc.get("label") or sc["name"],
            "chapter": sc.get("chapter"),
            "start_time": start,
            "end_time": end,
            "duration": round(dur, 3),
            "start_frame": round(start * fps),
            "duration_frames": st.get("total_frames", 0),
        })
        ch_name = sc.get("chapter")
        ch_label = ch_name
        for ch in script["chapters"]:
            if ch.get("name") == ch_name:
                ch_label = ch.get("label") or ch_name
                break
        if ch_name not in chapter_acc:
            chapter_acc[ch_name] = {
                "name": ch_name, "label": ch_label,
                "start_time": start, "end_time": end,
                "duration": round(dur, 3), "scenes": [sc["name"]],
            }
        else:
            chapter_acc[ch_name]["end_time"] = end
            chapter_acc[ch_name]["duration"] = round(
                chapter_acc[ch_name]["duration"] + dur, 3)
            chapter_acc[ch_name]["scenes"].append(sc["name"])
        cumulative += dur

    timing = {
        "total_duration": round(total_duration, 3),
        "fps": fps,
        "total_frames": total_frames,
        "chapters": list(chapter_acc.values()),
        "scenes": scene_blocks,
    }
    with open(os.path.join(video_dir, "timing.json"), "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)

    return timing, merged_wav, merged_srt


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(description="Per-scene TTS generation + merge.")
    cli_envelope.add_format_arg(parser)
    sub = parser.add_subparsers(dest="action", required=True)

    p_run = sub.add_parser("run", help="Synthesize TTS for one scene or all scenes.")
    p_run.add_argument("--project", required=True)
    p_run.add_argument("--video", required=True)
    p_run.add_argument("--scene", default=None,
                       help="Synthesize only this scene. Omit for all scenes "
                            "(which auto-runs merge afterwards).")
    p_run.add_argument("--backend", default=None,
                       choices=["comfyui_indextts", "http_server"],
                       help="Override prefs.tts.backend.")

    p_synth = sub.add_parser("synth", help="Synthesize a single text string to audio.")
    p_synth.add_argument("--prefs", required=True,
                         help="Path to project_prefs.yaml (reads tts.backend and tts.http.*).")
    p_synth.add_argument("--text", required=True,
                         help="Text to synthesize.")
    p_synth.add_argument("--voice-file", required=True,
                         help="Reference voice WAV for cloning.")
    p_synth.add_argument("--speed", type=float, default=None,
                         help="Speech speed multiplier (overrides tts.http.speed).")
    p_synth.add_argument("--output", default=None,
                         help="Output WAV path. Defaults to <cwd>/tts_output.wav.")

    p_merge = sub.add_parser("merge",
                             help="Concatenate scene WAVs/SRTs/timings into video-level artifacts.")
    p_merge.add_argument("--project", required=True)
    p_merge.add_argument("--video", required=True)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    fmt = args.format
    prefs = load_project_prefs(args.project, fmt)
    video_dir = workspace.video_dir(args.project, args.video)
    if not os.path.isdir(video_dir):
        cli_envelope.emit_usage_error(f"Video dir not found: {video_dir}", fmt=fmt)

    try:
        script = script_schema.load_script(os.path.join(video_dir, "narration_script.yaml"))
    except script_schema.SchemaError as exc:
        cli_envelope.emit_usage_error(str(exc), fmt=fmt)

    if args.action == "synth":
        # Load prefs from the given path (not project-based).
        prefs_path = args.prefs
        if not os.path.isfile(prefs_path):
            cli_envelope.emit_usage_error(f"Prefs file not found: {prefs_path}", fmt=fmt)
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = yaml.safe_load(f) or {}
        voice_file = args.voice_file
        if not os.path.isfile(voice_file):
            cli_envelope.emit_usage_error(f"Voice file not found: {voice_file}", fmt=fmt)
        # Apply --speed override if given
        if args.speed is not None:
            prefs.setdefault("tts", {}).setdefault("http", {})["speed"] = args.speed
        output_path = args.output or os.path.join(os.getcwd(), "tts_output.wav")
        result = synth_text(args.text, prefs, voice_file, output_path, fmt)
        cli_envelope.emit_ok(
            data={"output": result, "backend": prefs.get("tts", {}).get("backend", "comfyui_indextts")},
            message=f"TTS synth complete → {result}",
            fmt=fmt,
        )

    elif args.action == "run":
        voice_file = resolve_voice_file(prefs, args.project, fmt)
        backend = args.backend or prefs.get("tts", {}).get("backend", "comfyui_indextts")
        if args.scene:
            scene = script_schema.find_scene(script, args.scene)
            if scene is None:
                cli_envelope.emit_usage_error(
                    f"Scene '{args.scene}' not found. "
                    f"Known scenes: {[s['name'] for s in script['scenes']]}",
                    fmt=fmt)
            scenes = [scene]
        else:
            scenes = script["scenes"]

        outputs = []
        for sc in scenes:
            path = synth_scene(sc, prefs, voice_file, video_dir, backend, fmt)
            outputs.append({"scene": sc["name"], "wav": path})

        if args.scene:
            cli_envelope.emit_ok(
                data={"scenes": outputs},
                message=f"Scene '{args.scene}' TTS + timing complete. "
                        "Run `tts merge` once all scenes are done.",
                fmt=fmt,
            )
        else:
            timing, merged_wav, merged_srt = merge_scenes(script, prefs, video_dir, fmt)
            cli_envelope.emit_ok(
                data={"scenes": outputs, "timing": timing,
                      "narration_audio": merged_wav, "narration_srt": merged_srt},
                message=(f"TTS complete for {len(outputs)} scene(s); merged track "
                         f"{timing['total_duration']:.2f}s."),
                fmt=fmt,
            )
    elif args.action == "merge":
        timing, merged_wav, merged_srt = merge_scenes(script, prefs, video_dir, fmt)
        cli_envelope.emit_ok(
            data={"timing": timing,
                  "narration_audio": merged_wav, "narration_srt": merged_srt},
            message=(f"Merged {len(timing['scenes'])} scene(s) → "
                     f"{merged_wav} ({timing['total_duration']:.2f}s)."),
            fmt=fmt,
        )


if __name__ == "__main__":
    main()
