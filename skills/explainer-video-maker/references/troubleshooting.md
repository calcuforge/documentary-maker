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

Fix: edit `project_prefs.paths.remotion_template` to point at the right location — relative paths resolve against the **explainer-video-maker repo root** (default `../remotion-video-template`), absolute paths are used as-is. Or pass `--template-path` to `check_prereqs.py`.

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

### Render fails with "Cannot find module 'remotion'" or wrong template path

The generated per-scene `entry.tsx`/`scene.tsx` import from `<TEMPLATE_PATH>/src/components/index.js` using an absolute path baked in at generation time. If the template path is wrong, the bundler fails.

Fix: check `project_prefs.paths.remotion_template` resolves to the actual template directory, then re-run `compose` to regenerate all scene files.

### Render fails with "Can't resolve '@remotion/transitions'"

Generated compositions live outside the template's node_modules tree, so bare package imports can't resolve. The generated `scene.tsx` imports `TransitionSeries`/`linearTiming` from the template barrel (which re-exports them) — if you see this error, your `scene.tsx` is stale (generated before the barrel re-export existed). Re-run `compose`.

### Render fails: entry "does not contain registerRoot"

Stale generated `entry.tsx`. Re-run `compose` — current generation emits `registerRoot(RemotionRoot)`.

### Legacy flat schema error

```
error: narration_script.yaml uses the legacy flat section-list schema.
```

The pipeline requires the nested chapters → scenes → shots schema. Restructure the YAML (see workflow-script.md Step 3/4) — old flat section lists are not auto-migrated. Rough mapping: each old section becomes one scene with one shot; `visual:` fields move onto the shot (`component`, `asset_id`, `props`); `data:`/`text:` move onto the shot; group scenes under chapters.

### Scene timing vs scene WAV drift

```
scene 'hero': timing drift 1.20s > 0.5s
```

The scene's `timing.json` is written straight from ffprobing the scene WAV, so drift means one of them is stale. Re-run the scene's TTS:

```bash
python3 "$SKILL_DIR/scripts/cli.py" tts run --project $P --video $V --scene hero
python3 "$SKILL_DIR/scripts/cli.py" tts merge --project $P --video $V
```

### `tts merge` / `merge` concat failures

- **"Scene(s) missing narration.wav/timing.json"** — run `tts run --scene <name>` for each missing scene first.
- **Scene WAV concat produces garbled audio or fails** — a scene WAV was produced outside the toolchain without 48 kHz mono normalization. Re-run that scene's `tts run` (it always normalizes).
- **`merge` (video) fails with `scene_encoding_mismatch`** — scenes were rendered with different composition ids / flags. Re-render all scenes with the same `COMP_ID` and bitrate, then `merge` again.

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

Find the offending scene first:

```bash
python3 "$SKILL_DIR/scripts/cli.py" audit beats --video-dir "$VDIR"
```

Likely cause: that scene was rendered from a stale `timing.json` (narration was regenerated but the scene wasn't re-rendered). Re-run `compose`, re-render the flagged scene, and re-run `merge`.

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
