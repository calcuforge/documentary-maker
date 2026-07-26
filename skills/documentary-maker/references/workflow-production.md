# Workflow — Production Phase (Steps 6-10)

> **Load when:** entering Step 6, or when the user asks about TTS, upscale, composition, render, or BGM.

## Step 6: Generate TTS

**Outputs:** `narration_audio.wav`, `narration_audio.srt`, `timing.json`

Two backends via `scripts/generate_tts.py`:

### (a) ComfyUI index_tts (default)

```bash
python3 "$SKILL_DIR/scripts/cli.py" tts run --project $P --video $V
```

Calls `comfyui-scheduler run -w index_tts_2 -i '{"content":"<full narration>","voice_file":"<abs path>"}'`. Downloads the resulting audio file, renames to `narration_audio.wav`.

**Prereq:** `project_prefs.tts.voice_file` must point to an existing reference audio file. IndexTTS uses it to clone the speaker's timbre.

### (b) OpenAI-compatible HTTP TTS

```bash
python3 "$SKILL_DIR/scripts/cli.py" tts run --project $P --video $V --backend http_server
```

POSTs JSON `{model, input, voice, response_format}` to `tts.http.url`. Saves binary response → `narration_audio.wav`.

Config:
```yaml
tts:
  backend: http_server
  http:
    url: http://127.0.0.1:8000/v1/audio/speech
    api_key: sk-...         # null = no auth
    model: tts-1
    voice: alloy
    response_format: wav
```

### SRT + timing.json — char-count estimator

After audio lands on disk, `estimate_timing.py` runs automatically:

1. `ffprobe` the WAV for real `total_duration`.
2. For each section in `narration_script.yaml`, compute a char weight:
   - CJK = 1.0, ASCII letter/digit = 0.5, punctuation/whitespace = 0.0
3. Allocate `section.duration = total_duration * (section_weight / total_weight)`.
4. Inside each section, split narration into SRT cues at sentence-final punctuation (`。.!?！？`); allocate cue time by char weight.
5. Compute `start_frame` / `duration_frames` from time × fps.
6. Round-trip drift correction: ensure `sum(section.duration) == total_duration` (absorb remainder into last section).

**Audio-master clock rule**: `timing.json.total_duration` MUST match `ffprobe narration_audio.wav` within ±0.5s. Verify immediately:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 "$VDIR/narration_audio.wav"
python3 -c "import json; print(json.load(open('$VDIR/timing.json'))['total_duration'])"
```

If drift ≥ 0.5s, re-run `estimate_timing.py` — it auto-corrects. If still drifting, check that narration_script.yaml sections match what was actually sent to TTS.

### Manual mode gate

Show the user the audio file, the SRT preview (first 3 cues), and the timing summary (total duration + per-section breakdown). Ask "Sounds right? Want to regenerate?" before proceeding.

---

## Step 7: Upscale to Target Resolution

For each resolved image and video asset, decide whether to upscale:

| Tier | Target | Images | Videos |
| --- | --- | --- | --- |
| speed | 1080p | 1280×720 → 1920×1080 | 854×480 → 1920×1080 |
| speed | 4k | 1280×720 → 3840×2160 | 854×480 → 3840×2160 |
| quality | 1080p | skip (already 1920×1080) | 1280×720 → 1920×1080 |
| quality | 4k | 1920×1080 → 3840×2160 | 1280×720 → 3840×2160 |

Vertical videos are 1080p only in v1.

### Batch ordering (same rule as Step 5)

Follow the same batch strategy from [workflow-assets.md#5b-prime-batch-execution-strategy](workflow-assets.md#5b-prime-batch-execution-strategy). Upscale jobs split into two sequential batches:

| Batch | Workflow | Input |
| --- | --- | --- |
| 7 | `nvidia_rtx_video_upscale` | All resolved video assets that need upscaling |
| 8 | `nvidia_rtx_image_upscale` | All resolved image assets that need upscaling |

**Video upscale always runs before image upscale** — video upscale is heavier and ties up the GPU longer. Finishing images last means the agent can start Step 8 (composition generation) while CPU-bound image upscale finishes.

### Image upscale (nvidia_rtx_image_upscale)

Magnification = target_long_side / source_long_side. For 1280×720 → 1920×1080, magnification = 1920/1280 = 1.5.

Within a batch, all image upscale calls are independent (different input files, same workflow). The agent MUST issue them in parallel:

```bash
# Batch 8 — two images in parallel (single message, multiple Bash calls)
python3 "$SKILL_DIR/scripts/cli.py" comfyui run \
  -w nvidia_rtx_image_upscale \
  -i '{"image_file":".../assets/hero_bg.png","magnification":1.5}' \
  --dest-dir "$VDIR/assets"

python3 "$SKILL_DIR/scripts/cli.py" comfyui run \
  -w nvidia_rtx_image_upscale \
  -i '{"image_file":".../assets/timeline_bg.png","magnification":1.5}' \
  --dest-dir "$VDIR/assets"
```

After all upscale jobs in one batch finish, update the manifest entries:

```bash
python3 "$SKILL_DIR/scripts/cli.py" assets update \
  --video-dir "$VDIR" --id hero_bg --upscaled
python3 "$SKILL_DIR/scripts/cli.py" assets update \
  --video-dir "$VDIR" --id timeline_bg --upscaled
```

### Video upscale (nvidia_rtx_video_upscale)

Same pattern; video workflows accept `file` input. Batch 7 runs before batch 8.

### Skip-upscale optimization

For quality tier + 1080p target on images: skip batch 8 entirely for images. Mark the manifest entry `upscaled: true` without running the workflow.

---

## Step 8: Generate Per-Video Composition

**Outputs:** `Video.tsx`, `entry.tsx`, `narration_script.json` (JSON mirror)

```bash
python3 "$SKILL_DIR/scripts/cli.py" compose --project $P --video $V
```

This script:
1. Reads `project_prefs.yaml`, deep-merges the theme preset.
2. Reads `narration_script.yaml`, writes a JSON mirror (`narration_script.json`) for runtime `staticFile` consumption.
3. Generates `Video.tsx` — a SectionComponent switch driven by `section.visual.component`, importing components from `<TEMPLATE_PATH>/src/components/index.js`. Mirrors the audio-master clock math from the template's `Video.js`.
4. Generates `entry.tsx` — a Composition registration. Composition ID, dimensions, fps, default props all derived from project prefs.

The shared template's `useTiming` reads `timing.json` and `useAssets` reads `assets/manifest.json` via `staticFile` (per-video via `--public-dir`).

### Why not edit the shared template directly?

The template's `src/Video.js` ships with hardcoded literals ("Your Video Title", "In This Episode", "Thanks for Watching"). Editing it per video would either fork the template or violate the "shared template" rule. Per-video `Video.tsx` lives in the video dir, imports the template's component library, and supplies the section-specific content. The shared template stays untouched.

### Default props applied

From project prefs (theme block) → Composition `defaultProps`:
- `primaryColor`, `backgroundColor`, `textColor`, `accentColor`
- `transitionType`, `transitionDuration`
- `scaleFactor` (1 for 1080p, 2 for 4k)
- `orientation` ("horizontal" / "vertical")
- `enableAudio: true` (audio is the master clock — never disable unless testing)
- `enableSubtitles: false` (toggle true to render SRT natively)
- `bgmVolume: 0` (BGM mixed via FFmpeg in Step 10)

### Manual mode gate

Show the user the generated `Video.tsx` + `entry.tsx`. The user can edit the file directly (rare) or request a regeneration after editing `narration_script.yaml`. Don't render until "continue".

---

## Step 9: Render

**Output:** `output.mp4` (1920×1080 / 3840×2160 / 1080×1920, 30 fps)

Run from the template directory so node_modules resolves:

```bash
TEMPLATE_PATH="<abs path to remotion-video-template>"
VDIR="<abs path to video dir>"
COMP_ID=MainVideo  # or MainVideo4K / MainVideoVertical per project prefs

cd "$TEMPLATE_PATH" && npx remotion render \
  "$VDIR/entry.tsx" \
  "$COMP_ID" \
  "$VDIR/output.mp4" \
  --public-dir "$VDIR" \
  --video-bitrate 16M
```

The `--public-dir` flag points at the per-video dir so `staticFile("timing.json")`, `staticFile("narration_audio.wav")`, `staticFile("assets/manifest.json")`, etc. all resolve into the video dir.

### Verify audio-sync after render

```bash
VID=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VDIR/output.mp4")
WAV=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VDIR/narration_audio.wav")
python3 -c "v,w=float('$VID'),float('$WAV'); print(f'video={v:.2f}s audio={w:.2f}s diff={abs(v-w):.2f}s'); exit(1 if abs(v-w)>0.5 else 0)"
```

### Verify resolution

```bash
ffprobe -v quiet -show_entries stream=width,height -of csv=p=0 "$VDIR/output.mp4"
# Expected: 1920,1080 (horizontal 1080p) / 3840,2160 (4k) / 1080,1920 (vertical)
```

If drift >0.5s or resolution wrong, fix `timing.json` or composition dimensions, re-render.

---

## Step 10: Mix BGM

**Output:** `video_with_bgm.mp4`

BGM config from `project_prefs.bgm`:
- `volume` (0 to 1.0, default 0.12)
- `track` (absolute path to mp3, or null for no BGM)
- `loop` (true = `-stream_loop -1`)

### Single-write rule

The Remotion `<Audio src="bgm.mp3">` block in `Video.tsx` AND the FFmpeg `amix` below are two paths that can layer BGM. Pick ONE. Default is FFmpeg-only — `defaultProps.bgmVolume = 0` so the Remotion BGM block is disabled. Step 10 layers BGM via FFmpeg.

If you want beat-synced BGM baked in Remotion: set `bgmVolume > 0` in project prefs or video_info overrides, drop `bgm.mp3` in the video dir, **skip Step 10**.

### Mix

```bash
BGM_VOL=$(python3 -c "import yaml; print(yaml.safe_load(open('$PREFS'))['bgm']['volume'])")
BGM_TRACK=$(python3 -c "import yaml; print(yaml.safe_load(open('$PREFS'))['bgm']['track'])")

if [ -z "$BGM_TRACK" ] || [ ! -f "$BGM_TRACK" ]; then
  # No BGM — just rename output.mp4
  cp "$VDIR/output.mp4" "$VDIR/video_with_bgm.mp4"
  exit 0
fi

cp "$BGM_TRACK" "$VDIR/bgm.mp3"

ffmpeg -y \
  -i "$VDIR/output.mp4" \
  -stream_loop -1 -i "$VDIR/bgm.mp3" \
  -filter_complex "[0:a]volume=1.5[a1];[1:a]volume=${BGM_VOL}[a2];[a1][a2]amix=inputs=2:duration=first:normalize=0[aout]" \
  -map 0:v -map "[aout]" \
  -c:v copy -c:a aac -b:a 192k \
  "$VDIR/video_with_bgm.mp4"
```

**Why these values:**
- `volume=1.5` (narration): lifts TTS audio from ~-26 dB to ~-22 dB without clipping.
- `volume=$BGM_VOL` (BGM, default 0.12 = ~-18 dB): ~18 dB headroom under narration.
- `normalize=0`: prevents `amix` from halving the narration volume.

### Verify loudness

```bash
ffmpeg -i "$VDIR/video_with_bgm.mp4" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
# Target: mean -20 to -22 dB, max -1 to -3 dB
```

If too quiet, add `loudnorm=I=-16:TP=-1.5:LRA=11` for EBU R128 normalization (slower).

---

## Outro

No CTA step. The final section in `narration_script.yaml` is plain closing narration. Skip vpm's Steps 12-15 (subtitles, publish info, shorts, cleanup) — `final_video.mp4` is just `video_with_bgm.mp4` copied.

```bash
cp "$VDIR/video_with_bgm.mp4" "$VDIR/final_video.mp4"
```

Then proceed to Step 11 (`workflow-finish.md`).
