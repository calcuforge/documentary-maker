# Troubleshooting

## Common errors

### `comfyui-scheduler` not on PATH

```
error: comfyui-scheduler is not on PATH. pip install -e ../comfyui-scheduler
```

Fix:
```bash
cd ../comfyui-scheduler && pip install -e .
```

Verify:
```bash
comfyui-scheduler --help
```

### No ComfyUI nodes registered

```
warn: comfyui: NO nodes registered (run `comfyui-scheduler node add ...`)
```

Fix:
```bash
comfyui-scheduler node add --id node1 --url http://127.0.0.1:8188
comfyui-scheduler status
```

### `remotion-video-template` not found

```
fail: remotion-video-template: NOT FOUND at ...
```

Fix: edit `project_prefs.paths.remotion_template` to point at the right location (relative to explainer-video-maker root), or pass `--template-path` to `check_prereqs.py`.

### `node_modules` missing in template

```
remotion-video-template: .../remotion-video-template (WITHOUT node_modules (run npm install))
```

Fix:
```bash
cd ../remotion-video-template && npm install
```

This is a one-time ~2.2 GB download.

### TTS voice_file missing

```
error: tts.voice_file is required when backend=comfyui_indextts.
```

Fix: edit `project_prefs.yaml` → `tts.voice_file: "<absolute path to reference audio>"`. The audio can be any short clip (~5-30s) of the desired speaker's voice. IndexTTS clones timbre from it.

### TTS HTTP server returns non-2xx

```
error: HTTP TTS request failed: 401 Unauthorized
```

Fix: set `tts.http.api_key` in project prefs, or unset if the server doesn't require auth.

### Workflow `index_tts_2` not found

```
error: comfyui-scheduler exited 1: Workflow not found
```

Fix: import workflows into comfyui-scheduler's database:
```bash
cd ../comfyui-scheduler && comfyui-scheduler workflow import-all
```

### Render fails with "Cannot find module 'remotion'"

The generated `entry.tsx` imports from `<TEMPLATE_PATH>/src/components/index.js` using an absolute path. If the template path is wrong, the bundler can't find `remotion`/`react`.

Fix: check `project_prefs.paths.remotion_template` resolves to the actual template directory. Re-run `compose_video.py` after fixing the path — the absolute path is baked into `entry.tsx` at generation time.

### timing.json drift > 0.5s

```
warn: timing.json drift >0.5s (total=360.000, timing=359.200).
```

Usually caused by the char-count estimator rounding. Re-run:
```bash
python3 "$SKILL_DIR/scripts/estimate_timing.py" --video-dir "$VDIR" --fps 30
```

If drift persists, the narration_script.yaml sections may not match what was sent to TTS. Verify `concat_narration()` logic in `generate_tts.py` — it joins sections with `\n\n` and no markers.

### Render output resolution wrong

```
fail: resolution mismatch: got 1920x1080, expected 3840x2160
```

Either:
- Composition ID was wrong — `compose_video.py` picked `MainVideo` instead of `MainVideo4K`. Check `project_prefs.video.resolution` is `4k`.
- Rendered the wrong composition ID. Pass the right one to `npx remotion render`:
  ```bash
  npx remotion render .../entry.tsx MainVideo4K ...
  ```

### Video/audio drift > 0.5s after render

```
fail: video/audio drift 1.20s > 0.5s
```

Likely cause: `entry.tsx` `calculateVideoMetadata` didn't pick up the latest `timing.json`. Re-run `compose_video.py` and re-render.

### Asset "resolved but no path on disk"

```
warn: Asset 'hero_bg' resolved but no path on disk
```

The manifest entry was flipped to `resolved` before the file landed in `assets/`. Re-generate via `comfyui.py run` and verify the download succeeded, then update the manifest path:

```bash
python3 "$SKILL_DIR/scripts/cli.py" assets update \
  --video-dir "$VDIR" --id hero_bg --path hero_bg.png
```

## CLI discovery

If you're not sure which script to run:

```bash
python3 "$SKILL_DIR/scripts/cli.py" --help                  # list resources
python3 "$SKILL_DIR/scripts/cli.py" schema                 # list all methods
python3 "$SKILL_DIR/scripts/cli.py" schema tts.run          # spec for one method
```

Envelope error codes:

| Exit | Meaning |
| --- | --- |
| 0 | OK (or warnings accepted) |
| 1 | Workflow failure (server-side, file missing, etc.) |
| 2 | Usage error (missing required option, invalid args) |
| 3 | Confirmation required (destructive migration / overwrite) |

## BGM troubleshooting

### BGM track not found

```bash
ls -la "$VDIR/bgm.mp3"
```

If `project_prefs.bgm.track` is null or doesn't exist, Step 10's mix command just copies `output.mp4` → `video_with_bgm.mp4` (no BGM).

### BGM too quiet / loud

Adjust `bgm.volume` in project prefs. Default 0.12 (~-18 dB). For podcast-level clarity, 0.08-0.10; for ambient mood, 0.15-0.20. Above 0.25 competes with narration.

### Loudness check

```bash
ffmpeg -i "$VDIR/video_with_bgm.mp4" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
# Target: mean -20 to -22 dB, max -1 to -3 dB
```

If still off, apply EBU R128:
```bash
ffmpeg -y -i "$VDIR/video_with_bgm.mp4" \
  -af loudnorm=I=-16:TP=-1.5:LRA=11 \
  -c:v copy -c:a aac -b:a 192k \
  "$VDIR/video_with_bgm_norm.mp4"
mv "$VDIR/video_with_bgm_norm.mp4" "$VDIR/video_with_bgm.mp4"
```

## Preference commands

Project prefs are read from `projects/<name>/project_prefs.yaml`. To view/set:

```bash
python3 "$SKILL_DIR/scripts/cli.py" project show --name $P
python3 "$SKILL_DIR/scripts/cli.py" project set --name $P --key bgm.volume --value 0.08
python3 "$SKILL_DIR/scripts/cli.py" project set --name $P --key tts.voice_file --value "/abs/path/to/voice.mp3"
python3 "$SKILL_DIR/scripts/cli.py" project set --name $P --key ai.quality_tier --value quality
```

To see resolved prefs (theme merged):
```bash
python3 "$SKILL_DIR/scripts/cli.py" themes resolve --name <category> --prefs "$PREFS_PATH"
```
