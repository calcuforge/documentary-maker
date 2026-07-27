# Workflow — Asset Phase (Step 5)

> **Load when:** entering Step 5, or whenever the user supplies images/videos, asks for AIGC visuals, or wants richer media than text+typography.

## 5a. Plan

For each section in `narration_script.yaml`, decide the production path for its `visual.asset_id` (if any). Register the plan in `assets/manifest.json` via `cli.py assets add --status planned` BEFORE generating.

Asset types and roles:

| Role | Use | Remotion component |
| --- | --- | --- |
| `background` | Full-bleed backdrop behind a title / narration | `<AssetImage role="background">` (with ken-burns) |
| `inline` | Framed media inside the layout | `<AssetImage role="inline">` (delegates to `MediaSection`) |
| `broll` | Atmosphere clip | `<AssetVideo>` |
| `overlay` | Transparent animation layer | (future — `OverlayLayer`) |
| `bgm` / `sfx` | Music / sound effects | FFmpeg mix (Step 10) |

Asset sources:

| Source | Description | Cost |
| --- | --- | --- |
| `user` | User-supplied local file | free |
| `t2i` | ComfyUI `z_image_fp16` text-to-image | GPU time |
| `i2i` | ComfyUI `qwen_image_edit_2511_int8_step4` image-to-image | GPU time |
| `t2v` | ComfyUI `ltx2.3_t2v_int8` text-to-video | GPU time |
| `i2v` | ComfyUI `ltx2.3_i2v_int8` image-to-video | GPU time |
| `flf2v` | ComfyUI `ltx2.3_flf2v_int8` first+last frame | GPU time |
| `multi_scene_i2v` | ComfyUI `wan2.2_svi2pro_vbvr_int8` multi-scene prompt | GPU time |
| `stock` | (future) assetSeeker stock photo / video | free/paid |
| `text` | No asset — pure Remotion text/typography | free |

## 5b. Generation Pipeline — Speed vs Quality

Two tiers from `project_prefs.ai.quality_tier`:

| Tier | Initial image size | Initial video size | Upscale step |
| --- | --- | --- | --- |
| `speed` | 1280×720 | 854×480 | ALWAYS upscale to target |
| `quality` | 1920×1080 | 1280×720 | Upscale video always; image only if target=4k |

Target resolution from `project_prefs.video.resolution`:
- 1080p horizontal → 1920×1080
- 4k horizontal → 3840×2160
- 1080p vertical → 1080×1920

### Workflow → input mapping

Image workflows (`z_image_fp16`, `qwen_image_edit_2511_int8_step4`):
```bash
comfyui-scheduler run -w z_image_fp16 -i '{
  "prompt": "<detailed prompt>",
  "negative_prompt": "<from prefs.ai.negative_prompt>",
  "width": 1280,
  "height": 720,
  "seed": 12345
}'
```

Image-to-video (`ltx2.3_i2v_int8`):
```bash
comfyui-scheduler run -w ltx2.3_i2v_int8 -i '{
  "prompt": "<motion description>",
  "image_file": "<abs path to source image>",
  "width": 854,
  "height": 480,
  "fps": 24,
  "length": 5,
  "seed": 12345
}'
```

First+last frame (`ltx2.3_flf2v_int8`):
```bash
comfyui-scheduler run -w ltx2.3_flf2v_int8 -i '{
  "prompt": "<motion description>",
  "first_frame_image": "<path>",
  "last_frame_image": "<path>",
  "width": 854,
  "height": 480,
  "fps": 24,
  "length": 3
}'
```

Multi-scene image-to-video (`wan2.2_svi2pro_vbvr_int8`) — multi-prompt with `|N\n` separators:
```bash
comfyui-scheduler run -w wan2.2_svi2pro_vbvr_int8 -i '{
  "prompt": "scene one description|5\nscene two description|5",
  "image_file": "<path>",
  "width": 640,
  "height": 384,
  "fps": 16
}'
```

### Generate + register in one go

**Registration comes first.** Register all planned assets with `assets add --status planned` BEFORE generating. Then generate in batched groups — never mix workflow types in one batch.

```bash
SKILL_DIR=...
PROJECT=aviation-disaster-horizontal
VIDEO=swissair-111
VDIR="$SKILL_DIR/../projects/$PROJECT/videos/$VIDEO"

# 1. Initialize manifest (once per video)
python3 "$SKILL_DIR/scripts/cli.py" assets init --video-dir "$VDIR"

# 2. Register ALL planned assets first
python3 "$SKILL_DIR/scripts/cli.py" assets add \
  --video-dir "$VDIR" \
  --id hero_bg --section hero --type image --role background \
  --source t2i --status planned \
  --prompt "Photorealistic MD-11 cockpit interior, dim blue emergency lighting,
           instrument panels, wide angle, no text, no watermark" \
  --workflow z_image_fp16 --upscale-target 1080p

python3 "$SKILL_DIR/scripts/cli.py" assets add \
  --video-dir "$VDIR" \
  --id timeline_bg --section timeline --type image --role background \
  --source t2i --status planned \
  --prompt "Aerial view of Atlantic Ocean at dusk with search lights, dramatic sky" \
  --workflow z_image_fp16 --upscale-target 1080p

python3 "$SKILL_DIR/scripts/cli.py" assets add \
  --video-dir "$VDIR" \
  --id wreck_broll --section impact --type video --role broll \
  --source t2v --status planned \
  --prompt "Slow pan over aircraft wreckage on ocean floor, dark blue water" \
  --workflow ltx2.3_t2v_int8 --upscale-target 1080p

# 3. Generate assets in batched groups (see 5b. batch strategy below)
```

### User-supplied files

```bash
python3 "$SKILL_DIR/scripts/cli.py" assets add \
  --video-dir "$VDIR" \
  --id timeline_chart --section timeline --type image --role inline \
  --source user --status resolved \
  --file /path/to/user/diagram.png \
  --license "user-owned" --credit "user"
```

The file is copied into `assets/timeline_chart.png` and the manifest path set automatically.

## 5b-prime. Batch Execution Strategy

When multiple assets are planned across sections, batch out calls by workflow type to avoid overloading the ComfyUI server with mixed pipeline workloads. **Same workflow → parallel calls in one batch. Different workflows → sequential batches.**

### Batch execution order (fixed)

Batch 0 (voice design) runs once per project, before any video's asset generation. Batches 1-8 run per video.

| Batch | Workflow(s) | Example command |
| --- | --- | --- |
| 0 | `voice_design` (`ominivoice_voice_design` or `qwen3_tts_voice_design`) | `comfyui-scheduler run -w ominivoice_voice_design -i '{...}'` |
| 1 | All `t2i` (`z_image_fp16`) | `comfyui-scheduler run -w z_image_fp16 -i '{...}'` |
| 2 | All `i2i` (`qwen_image_edit_2511_int8_step4`) | `comfyui-scheduler run -w qwen_image_edit_2511_int8_step4 -i '{...}'` |
| 3 | All `t2v` (`ltx2.3_t2v_int8`) | `comfyui-scheduler run -w ltx2.3_t2v_int8 -i '{...}'` |
| 4 | All `i2v` (`ltx2.3_i2v_int8`) | `comfyui-scheduler run -w ltx2.3_i2v_int8 -i '{...}'` |
| 5 | All `flf2v` (`ltx2.3_flf2v_int8`) | `comfyui-scheduler run -w ltx2.3_flf2v_int8 -i '{...}'` |
| 6 | All `multi_scene_i2v` (`wan2.2_svi2pro_vbvr_int8`) | `comfyui-scheduler run -w wan2.2_svi2pro_vbvr_int8 -i '{...}'` |
| 7 | All `nvidia_rtx_video_upscale` | (Step 7 — see workflow-production.md) |
| 8 | All `nvidia_rtx_image_upscale` | (Step 7 — see workflow-production.md) |

**Skip batches with no assets.** Only the batches that have at least one planned asset run.

### Parallel execution within a batch

Every call inside a batch is **independent** — they differ only in prompt/seed/input_file, not workflow ID. The agent MUST issue them as parallel Bash commands (multiple tool calls in one message). Example for batch 1 — two t2i jobs:

```bash
# All three commands in one message — they are independent, same workflow.

# Job A:
python3 "$SKILL_DIR/scripts/cli.py" comfyui run \
  -w z_image_fp16 \
  -i '{"prompt":"MD-11 cockpit interior, blue emergency lighting, wide angle","width":1280,"height":720}' \
  --dest-dir "$VDIR/assets"

# Job B:
python3 "$SKILL_DIR/scripts/cli.py" comfyui run \
  -w z_image_fp16 \
  -i '{"prompt":"Aerial view of Atlantic Ocean at dusk, search lights","width":1280,"height":720}' \
  --dest-dir "$VDIR/assets"
```

### After each batch

After a batch completes, for each job, find the downloaded file in `$VDIR/assets/` and update the manifest from `planned` → `resolved`:

```bash
python3 "$SKILL_DIR/scripts/cli.py" assets update \
  --video-dir "$VDIR" --id hero_bg --status resolved --path hero_bg.png
python3 "$SKILL_DIR/scripts/cli.py" assets update \
  --video-dir "$VDIR" --id timeline_bg --status resolved --path timeline_bg.png
```

Then proceed to the next batch. **Never start the next batch before all jobs in the current batch finish and their manifest entries are resolved** — downstream batches (e.g. i2v) may depend on files produced by upstream batches (e.g. t2i).

### Dependency chain

```
voice_design ──→ TTS    (TTS needs voice_reference.wav as speaker reference)
t2i ──────────→ i2v     (i2v needs t2i output as first frame)
t2i ──────────→ flf2v   (needs first + last frame images)
t2i ──────────→ upscale (upscale needs generated image)

t2v: no upstream dependency (text-only input)
```

When a downstream batch needs an upstream output, wait for the upstream batch to fully complete before starting the downstream batch.

### ComfyUI server capacity

The `comfyui-scheduler` CLI auto-selects the least-busy node. Parallel calls within a batch leverage multi-GPU setups. If you only have one GPU / one node, parallel calls queue on the server side — they will still complete, just sequentially.

### Manual mode gate (batch)

In Manual Mode, show the user a summary of all planned batches before generating anything:

```
Planned AIGC: 2 t2i, 1 t2v, 2 upscale.
  Batch 1 (t2i × 2):  hero_bg, timeline_bg
  Batch 3 (t2v × 1):  wreck_broll
  Batch 7 (video_upscale × 1): wreck_broll → 1080p
  Batch 8 (image_upscale × 2): hero_bg, timeline_bg → 1080p

Proceed? Reply 'continue' or adjust prompts first.
```

After each batch, report number of succeeded/failed jobs before starting the next batch. Generates only after explicit "continue".

```bash
python3 "$SKILL_DIR/scripts/cli.py" assets validate --video-dir "$VDIR"
```

Checks: duplicate ids, resolved-but-missing-path, file-on-disk presence. Warnings are non-blocking.

## Hard rules

- **Manifest is the single source of truth.** Never reference an asset by raw path in `Video.tsx`; always go through `<AssetImage id="...">` / `<AssetVideo id="...">` so the manifest's `status` gating works.
- **Always register before generating.** `status: planned` lets the composition generator reason about an asset's intent before it exists. Flip to `resolved` only after the file is on disk.
- **Negative prompt** comes from `prefs.ai.negative_prompt` — don't repeat it per call.
- **Seed** — `prefs.ai.seed` (null = random). Pin for reproducibility when iterating.

## Manual mode gate (Step 5)

In Manual Mode, before generating any AI asset:
1. Show the user the planned cost (workflow id + GPU time, ~rough estimate).
2. Show the full prompt + negative prompt.
3. Ask: "Generate? Reply 'continue' or edit prompt first."
4. Generate only after explicit OK.

User-supplied and `text` sources bypass this gate — they're free.
