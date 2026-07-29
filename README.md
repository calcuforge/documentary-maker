# Explainer Video Maker

A Claude Code skill for automated production of narration-driven explainer
videos. Supports documentaries, knowledge sharing, news broadcasts, data
reports, product introductions, and any format suitable for narrated
explanation.

## How It Works

The skill guides an AI coding agent through a 9-step pipeline:

1. **Project initialization** — create project config
2. **Topic definition** — auto-select or user-specified topic
3. **Topic research** — browser search, RSS feeds, custom providers
4. **Video structure design** — stories → narrations → scenes
5. **TTS synthesis** — generate narration audio, calculate frame counts
6. **AIGC task planning** — design prompts, choose workflows
7. **AIGC execution** — generate images/videos via ComfyUI, upscale
8. **Remotion config generation** — build rendering configuration
9. **Video rendering** — render final MP4 via remotion-video-template

Audio drives visuals: narration audio duration determines the total frame
count for all scene units under each narration unit.

## Project Structure

```
explainer-video-maker/
├── README.md
└── skills/explainer-video-maker/
    ├── SKILL.md                    # Main skill definition
    ├── scripts/                    # All automation scripts
    │   ├── lib/                    # Shared Python utilities
    │   │   ├── envelope.py         # JSON output envelope
    │   │   ├── yamlutil.py         # YAML load/save
    │   │   ├── net.py              # Network/locale utilities
    │   │   └── htmltext.py         # HTML-to-text extraction
    │   ├── search_provider/        # Extensible search components
    │   │   ├── search.py           # Browser search (Playwright)
    │   │   └── search_rss.py       # RSS feed search (curl + Playwright)
    │   ├── tool/                   # Pipeline tool scripts
    │   │   ├── check_prereqs.py    # Prerequisite checker
    │   │   ├── search_rss.py       # RSS source discovery
    │   │   ├── run_tts.py          # TTS synthesis + frame calculation
    │   │   ├── run_aigc.py         # AIGC task execution
    │   │   ├── run_upscale.py      # Asset upscaling
    │   │   ├── generate_remotion_sections.py  # Remotion config generator
    │   │   └── render.py           # Video renderer
    │   └── verify/                 # Validation scripts
    │       ├── verify_project_config.py
    │       ├── verify_video_struct.py
    │       ├── verify_audio.py
    │       ├── verify_video_tasks.py
    │       ├── verify_aigc_assets.py
    │       └── verify_remotion_sections.py
    ├── references/                 # Detailed documentation
    │   ├── workflow-steps.md       # Step-by-step agent instructions
    │   ├── natural-narration.md    # Anti-slop narration rules
    │   ├── search-providers.md     # Search provider guide
    │   └── expression_intent_mapping.md  # Scene type selection
    └── templates/                  # Example/template files
        └── demo_projects/          # Reference project structure
```

## Dependencies

- Python >= 3.10, `requests`, `pyyaml`, `playwright`
- `ffmpeg`, `ffprobe` on PATH
- Node.js >= 18, `npx`
- [comfyui-scheduler](https://github.com/calcuforge/comfyui-scheduler.git) CLI (`pip install -e ../comfyui-scheduler`)
- A running ComfyUI server with default workflows imported
- [remotion-video-template](https://github.com/calcuforge/remotion-video-template.git) with `node_modules/` installed

## Setup

```bash
# Install Python dependencies
pip install requests pyyaml playwright
playwright install chromium

# Install comfyui-scheduler
pip install -e ../comfyui-scheduler

# Install remotion-video-template dependencies
cd ../remotion-video-template && npm install
```

## Usage

This is a Claude Code skill. Install it by placing the `skills/` directory
in your Claude Code skills path, then trigger with phrases like:

- "Help me make a documentary about Air France Flight 447"
- "Make a knowledge video about GPU architecture"
- "帮我制作一个动物纪录片"
- "帮我制作一个显卡价格日报"

## License

See [LICENSE](skills/explainer-video-maker/LICENSE).
