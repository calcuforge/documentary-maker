# Project Layout

## Directory tree

```
documentary-maker/
├── SKILL.md
├── README.md
├── project_prefs.template.yaml     # template; copied per project
├── scripts/                        # CLI suite
├── references/                     # docs (load on demand)
├── themes/                         # theme presets
│   ├── aviation-disaster.yaml
│   ├── history.yaml
│   ├── crime.yaml
│   └── natural-disaster.yaml
├── assets/                         # shared BGM, fonts (user-supplied)
└── projects/                       # created on demand
    └── {project-name}/
        ├── project_prefs.yaml      # copied from template, edited
        ├── voice_reference.wav     # Step 0 — one per project, shared by all videos
        └── videos/
            └── {video-name}/
                ├── topic_definition.md
                ├── topic_research.md
                ├── chapters.yaml
                ├── narration_script.yaml
                ├── narration_script.json     # JSON mirror (auto-generated)
                ├── assets/
                │   ├── manifest.json         # consumed by useAssets
                │   └── *.{png,mp4}           # generated / user-supplied
                ├── narration_audio.wav       # TTS output
                ├── narration_audio.srt        # char-estimated SRT
                ├── timing.json               # consumed by useTiming
                ├── Video.tsx                  # generated per-video
                ├── entry.tsx                  # generated per-video
                ├── video_info.yaml            # final metadata
                ├── output.mp4                 # render output (no BGM)
                ├── video_with_bgm.mp4         # +BGM
                ├── final_video.mp4            # = video_with_bgm.mp4 (or output.mp4)
                └── bgm.mp3                    # copied from prefs.bgm.track (optional)
```

## --public-dir convention

Every remotion command uses `--public-dir projects/{project}/videos/{video}/`. This routes `staticFile("timing.json")`, `staticFile("narration_audio.wav")`, `staticFile("narration_audio.srt")`, `staticFile("assets/manifest.json")`, and per-asset file reads into the per-video directory. The shared template's source code stays untouched.

```bash
TEMPLATE_PATH="<abs>/remotion-video-template"
VDIR="<abs>/documentary-maker/projects/$P/videos/$V"

cd "$TEMPLATE_PATH" && npx remotion render \
  "$VDIR/entry.tsx" MainVideo \
  "$VDIR/output.mp4" \
  --public-dir "$VDIR" --video-bitrate 16M
```

## Naming rules

| Entity | Convention | Example |
| --- | --- | --- |
| Project name | lowercase, hyphen-separated, ≤64 chars | `aviation-disaster-horizontal` |
| Video name | lowercase, hyphen-separated | `swissair-111` |
| Section name | lowercase, underscore | `hero`, `cause_chain` |
| Asset id | lowercase, underscore, kebab-safe | `hero_bg`, `timeline_chart` |
| Composition ID | `MainVideo` / `MainVideo4K` / `MainVideoVertical` | (template-controlled) |

## Project vs. video

A **project** groups videos sharing the same config:
- Same category (aviation-disaster / history / crime / natural-disaster)
- Same orientation (horizontal / vertical)
- Same resolution (1080p / 4k)
- Same creation mode (auto / manual)
- Same language
- Same quality tier

Examples of valid projects:
- `aviation-disaster-horizontal` (1080p, speed tier, zh-CN, auto) — multiple air-crash videos live here
- `aviation-disaster-vertical` (1080p, vertical, zh-CN, auto) — vertical shorts variant
- `history-4k` (4k horizontal, quality tier, en-US, manual) — premium-quality historical docs

Examples of INVALID grouping:
- Mixing horizontal and vertical videos in one project → orientation is a project-level setting
- Mixing categories in one project → theme applies at the project level

Create a new project when any of these config axes differs. Use `cli.py project create --name ... --category ... --orientation ... --resolution ...` to scaffold.

## Shared remotion-video-template

Located at `../remotion-video-template/` relative to documentary-maker root (override in `project_prefs.paths.remotion_template`). The template's `src/components/` is the canonical source for all React components. Per-video `Video.tsx` imports from it via an absolute path embedded at generation time by `scripts/compose_video.py`.

Never copy `remotion-video-template/`. Never symlink it. Use the absolute path import mechanism.

## ComfyUI workflows

`comfyui-scheduler` must be installed (`pip install -e ../comfyui-scheduler`) and at least one ComfyUI node registered:

```bash
comfyui-scheduler node add --id node1 --url http://127.0.0.1:8188
comfyui-scheduler workflow import-all   # imports all default workflows
```

Default workflow IDs are referenced from `project_prefs.workflows.*`:
- `index_tts_2` (TTS)
- `z_image_fp16` (text-to-image)
- `qwen_image_edit_2511_int8_step4` (image-to-image)
- `ltx2.3_t2v_int8` (text-to-video)
- `ltx2.3_i2v_int8` (image-to-video)
- `ltx2.3_flf2v_int8` (first-last-frame to video)
- `wan2.2_svi2pro_vbvr_int8` (multi-scene image-to-video)
- `nvidia_rtx_image_upscale` (image upscale)
- `nvidia_rtx_video_upscale` (video upscale)
