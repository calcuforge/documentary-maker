# documentary-maker

A Claude Code skill that produces narration-driven documentary videos — history, aviation disaster, true crime, natural disaster — from a topic. Pipeline: research → script → AIGC visuals → TTS → Remotion → FFmpeg.

## What it is

- **Platform-agnostic.** No CTA, no thumbnails, no platform-bound publish_info. The final video is a plain MP4 plus a `video_info.yaml` metadata file for downstream cover-image / shorts / publishing tasks.
- **AIGC-heavy.** Images and b-roll come from ComfyUI workflows orchestrated by `comfyui-scheduler`. Text-only sections are fine too.
- **Project-based.** A project groups videos sharing the same config (category + orientation + resolution + language + quality tier + creation mode). One project = many videos.
- **Reuses `remotion-video-template`.** Per-video `Video.tsx`/`entry.tsx` import components from the shared template — no copy.
- **YAML config.** Project prefs in `project_prefs.yaml` with inline comments. No JSON configs.
- **Two TTS backends.** ComfyUI `index_tts` (default; clones a reference voice) OR any OpenAI-compatible `/v1/audio/speech` HTTP server.

## Quick start

```bash
# 1. Check prerequisites
python3 scripts/check_prereqs.py

# 2. Install comfyui-scheduler if not already
cd ../comfyui-scheduler && pip install -e . && cd -

# 3. Register a ComfyUI node + import workflows
comfyui-scheduler node add --id node1 --url http://127.0.0.1:8188
comfyui-scheduler workflow import-all

# 4. Create a project
python3 scripts/cli.py project create \
  --name aviation-disaster-horizontal \
  --category aviation-disaster \
  --orientation horizontal \
  --resolution 1080p \
  --quality speed \
  --language zh-CN \
  --mode auto

# 5. Edit project_prefs.yaml to set tts.voice_file
python3 scripts/cli.py project set \
  --name aviation-disaster-horizontal \
  --key tts.voice_file --value /abs/path/to/reference_voice.mp3

# 6. Create a video scaffold
python3 scripts/cli.py project video \
  --name aviation-disaster-horizontal --video swissair-111

# 7. Write topic_definition.md, topic_research.md, chapters.yaml,
#    narration_script.yaml into the video dir (Step 1-4 of the workflow).
#    See references/workflow-script.md for the schema.

# 8. Plan + generate assets (Step 5)
VDIR="projects/aviation-disaster-horizontal/videos/swissair-111"
python3 scripts/cli.py assets init --video-dir "$VDIR"
python3 scripts/cli.py assets add --video-dir "$VDIR" \
  --id hero_bg --section hero --type image --role background \
  --source t2i --status planned \
  --prompt "..." --workflow z_image_fp16 --upscale-target 1080p
python3 scripts/cli.py comfyui run -w z_image_fp16 \
  --inputs '{"prompt":"...","width":1280,"height":720}' \
  --dest-dir "$VDIR/assets"
python3 scripts/cli.py assets update --video-dir "$VDIR" --id hero_bg \
  --status resolved --path hero_bg.png

# 9. TTS + SRT + timing.json (Step 6)
python3 scripts/cli.py tts run \
  --project aviation-disaster-horizontal --video swissair-111

# 10. Upscale (Step 7) — skip if quality tier + 1080p target
# 11. Generate composition (Step 8)
python3 scripts/cli.py compose \
  --project aviation-disaster-horizontal --video swissair-111

# 12. Render (Step 9)
TEMPLATE="../remotion-video-template"
cd "$TEMPLATE" && npx remotion render \
  "$PWD/../documentary-maker/$VDIR/entry.tsx" MainVideo \
  "$PWD/../documentary-maker/$VDIR/output.mp4" \
  --public-dir "$PWD/../documentary-maker/$VDIR" --video-bitrate 16M

# 13. Mix BGM (Step 10) + Verify (Step 11)
# See references/workflow-production.md and references/workflow-finish.md
```

## Directory structure

See [references/project-layout.md](references/project-layout.md) for the full tree. Key points:

- `documentary-maker/projects/{project-name}/project_prefs.yaml` — project-level config
- `documentary-maker/projects/{project-name}/videos/{video-name}/` — per-video files
- `documentary-maker/themes/*.yaml` — theme presets
- `documentary-maker/scripts/*.py` — CLI suite
- `documentary-maker/references/*.md` — load-on-demand docs
- `../remotion-video-template/` — shared Remotion template (referenced, not copied)
- `../comfyui-scheduler/` — ComfyUI workflow runner (installed via pip)

## Dependencies

- Python ≥ 3.10, `requests`, `pyyaml`
- `ffmpeg`, `ffprobe` on PATH
- Node.js ≥ 18, `npx`
- `comfyui-scheduler` CLI (pip install -e ../comfyui-scheduler)
- A running ComfyUI server with the default workflows imported
- `remotion-video-template/` with `node_modules/` installed (`npm install`)

## Documentation

Load on demand — do NOT read all at once:

| File | When |
| --- | --- |
| [references/workflow-script.md](references/workflow-script.md) | Steps 1-4 |
| [references/workflow-assets.md](references/workflow-assets.md) | Step 5 — AIGC pipelines |
| [references/workflow-production.md](references/workflow-production.md) | Steps 6-10 — TTS, render, BGM |
| [references/workflow-finish.md](references/workflow-finish.md) | Step 11 — verify + metadata |
| [references/themes.md](references/themes.md) | Theme catalog |
| [references/project-layout.md](references/project-layout.md) | Directory structure |
| [references/audio-sync.md](references/audio-sync.md) | Char-count timing |
| [references/design-guide.md](references/design-guide.md) | Component selection |
| [references/troubleshooting.md](references/troubleshooting.md) | Errors |

## Status

v1.0 — initial implementation. Known limitations:

- No browser preview (Remotion Studio). Render directly to file.
- No stock-asset search (assetSeeker). Manual file import only.
- SRT/timing.json estimated by char count, not word-level timestamps.
- Subtitles rendered natively in Remotion (no FFmpeg burn).
- Vertical videos limited to 1080p.

## License

MIT. See [LICENSE](LICENSE).
