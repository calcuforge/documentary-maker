# Project Layout

## Workspace vs. skill directories

Project data lives in the **workspace** (the directory the agent works from), never inside the skill installation. The projects root resolves as: `EXPLAINER_PROJECTS_DIR` env → `EXPLAINER_WORKSPACE` env (+ `/projects`) → `<CWD>/projects`. All skill commands run from the workspace root.

```
<workspace>/                        # the agent's working directory
├── projects/                       # created on demand — ALL project data
│   └── {project-name}/
│       └── ...
└── (user's other files)

explainer-video-maker/              # skill installation (code only, no project data)
├── skills/explainer-video-maker/
│   ├── SKILL.md
│   ├── project_prefs.template.yaml # template; copied per project
│   ├── scripts/                    # CLI suite
│   ├── references/                 # docs (load on demand)
│   ├── themes/                     # theme presets (aviation-disaster, history, ...)
│   └── assets/                     # shared BGM, fonts (user-supplied)
```

## Per-project tree

```
<workspace>/projects/
└── {project-name}/
        ├── project_prefs.yaml      # copied from template, edited
        ├── voice_reference.wav     # Step 0 — one per project, shared by all videos
        └── videos/
            └── {video-name}/
                ├── topic_definition.md
                ├── topic_research.md
                ├── narration_script.yaml     # chapters → scenes → shots (single source)
                ├── assets/
                │   ├── manifest.json         # shared by all scenes; consumed by useAssets
                │   └── *.{png,mp4,webm}      # generated / user-supplied
                ├── scenes/
                │   └── {scene-name}/         # one dir per scene
                │       ├── narration.wav     # scene TTS (48 kHz mono)
                │       ├── narration.srt     # scene subtitles (relative time)
                │       ├── timing.json       # scene timing (shots list)
                │       ├── composition.json  # shot designs (auto-generated)
                │       ├── scene.tsx         # generated per-scene composition
                │       ├── entry.tsx         # generated per-scene Remotion entry
                │       └── scene.mp4         # scene render (narration + subtitles)
                ├── timing.json               # video-level summary (chapters + scenes)
                ├── narration_audio.wav       # merged scene track
                ├── narration_audio.srt       # merged subtitles (offset)
                ├── concat_audio.txt          # ffmpeg concat list (auto-generated)
                ├── concat.txt                # ffmpeg scene concat list (auto-generated)
                ├── video_info.yaml           # final metadata
                ├── output.mp4                # merged scenes (no BGM)
                ├── video_with_bgm.mp4        # +BGM
                ├── final_video.mp4           # = video_with_bgm.mp4 (or output.mp4)
                └── bgm.mp3                   # copied from prefs.bgm.track (optional)
```

## --public-dir convention

Every remotion command uses `--public-dir projects/{project}/videos/{video}/` — the **video root**, shared by all scenes. Scene files resolve via a `scenes/{scene}/` prefix; the asset manifest stays shared:

- `staticFile("scenes/{scene}/timing.json")` / `narration.wav` / `narration.srt` / `composition.json`
- `staticFile("assets/manifest.json")` + per-asset file reads

The shared template's source code stays untouched.

```bash
TEMPLATE_PATH="<abs>/remotion-video-template"
VDIR="<abs>/explainer-video-maker/projects/$P/videos/$V"

cd "$TEMPLATE_PATH" && npx remotion render \
  "$VDIR/scenes/hero/entry.tsx" MainVideo \
  "$VDIR/scenes/hero/scene.mp4" \
  --public-dir "$VDIR" --video-bitrate 16M
```

## Naming rules

| Entity | Convention | Example |
| --- | --- | --- |
| Project name | lowercase, hyphen-separated, ≤64 chars | `aviation-disaster-horizontal` |
| Video name | lowercase, hyphen-separated | `swissair-111` |
| Chapter name | lowercase, underscore | `opening`, `main` |
| Scene name | lowercase, underscore, unique per video | `hero`, `cause_chain` |
| Shot name | lowercase, underscore, unique per scene | `hero_01`, `timeline_02` |
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

Located at `../remotion-video-template/` relative to the explainer-video-maker repo root (override in `project_prefs.paths.remotion_template` — relative paths resolve against the repo root, absolute paths are used as-is). The template's `src/components/` is the canonical source for all React components. Per-scene `scene.tsx`/`entry.tsx` import from it via an absolute path embedded at generation time by `scripts/compose_video.py`. The template barrel also re-exports `TransitionSeries`/`linearTiming` from `@remotion/transitions` so generated compositions outside the template's node_modules tree can import them.

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
