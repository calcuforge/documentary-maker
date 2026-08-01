# Workflow Steps — Content Creation (Steps 5–7)

> **When to load:** Step 5 through Step 7 — writing narration scripts, designing
> scene lists, TTS synthesis, and frame calculation. Covers the transformation from
> research into a fully-scored scene structure with audio.

**Prerequisite:** [workflow-setup.md](workflow-setup.md) Steps 1–4 must be complete
(`video_struct.yaml` with a validated chapter list and `search_results/` populated).

---

## Step 5: Write Chapter Narration Scripts

**When:** After the chapter list passes validation.

**What to do:**

1. Write the narration script (讲稿) for each chapter using the format **one
   narration per line** — each line is exactly one scene's narration (≤50
   characters). Step 6 turns each line into a scene automatically, so the number
   of lines = the number of scenes. The script is the chapter's single source of
   narration: **all scene narrations merged together equal this script** (one
   line = one narration).

   ```text
   1956年夏天，达特茅斯学院的一场研讨会，正式确立了人工智能这门学科的名字。
   麦卡锡和明斯基等学者提出，要让机器去模拟人类的学习、推理和解决问题的能力。
   早期的研究者满怀乐观，他们相信用不了几十年，就能造出真正会思考的机器。
   ```

   **Write one chapter at a time, in story order, in multiple passes — do NOT
   write all chapters at once.** Finish one chapter's script before starting the
   next. Focusing on a single chapter produces richer, more detailed narration,
   and writing in order lets each chapter connect to the one before it.

2. **Decide inter-chapter continuity by video style — your call.** Before
   writing, read `project.video_style` and decide how tightly the chapters must
   connect to one another. This is an agent judgment decision, not a fixed table;
   the guide below is a starting point:
   - **Continuous narrative** (e.g. `documentary`, `news_broadcast`): treat all
     chapters as one unbroken story. Each chapter MUST flow from the previous one
     — open by bridging from where the last chapter ended (a temporal or causal
     link), carry a single narrative thread through the whole video, and never
     re-introduce the topic cold. A documentary's chapters should play as
     consecutive acts of the same film, not as standalone clips.
   - **Modular / explanatory** (e.g. `knowledge_sharing`, `tutorial`,
     `data_report`, `product_intro`): chapters may be largely self-contained
     (each covers a distinct concept, step, or section). A light bridge between
     chapters is enough; they can stand on their own.

   Whichever level you choose, apply it consistently across every chapter, and
   show it in how each chapter's first and last narration lines are written.
   Because chapters are written one at a time in story order (sub-step 1), each
   new chapter can — and for continuous styles, must — pick up from the one
   before it.

3. Save each chapter's script to `stories/{story_id}/script.md` (one file per
   chapter, under the video directory). Write **only narration lines** — no
   titles or headers; blank lines are allowed (ignored).

4. **Each script MUST meet `content.min_story_chars`** (project_config.yaml,
   default **500** characters). A chapter script should be a complete, substantive
   narration — not a thin outline.

5. **Writing style — MUST follow [natural-narration.md](natural-narration.md):**
   - No AI filler phrases
   - No rule-of-three abuse
   - Vary sentence length
   - State facts directly
   - Write for the ear, not the eye

6. **Reference:** [demo_projects/project1/video1/stories/story1/script.md](demo_projects/project1/video1/stories/story1/script.md)

7. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_story_scripts.py" \
     --video-struct /abs/path/video_struct.yaml \
     --project-config /abs/path/project_config.yaml
   ```
   If it fails (script missing or below the minimum), fix and re-validate. Do NOT
   proceed until exit 0.

---

## Step 6: Design Scene List from Scripts

**When:** After all chapter scripts pass validation.

**What to do:**

1. **Generate the narration skeleton with a script.** Run `generate_scene_list.py`
   to turn each chapter's `script.md` (one narration per line) into the
   `scene_list` in `video_struct.yaml` — one scene per line, each carrying that
   line as its `narration.content`. The display fields are left empty for you to
   fill next.
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/generate_scene_list.py" --video-struct /abs/path/video_struct.yaml
   ```
   - One scene is created per non-empty line; scene/narration ids are assigned
     globally and stay unique. Stories that already have a `scene_list` are
     skipped (pass `--force` to regenerate).
   - **Do NOT hand-write the `scene_list` / narrations** — let the script generate
     them so they match `script.md` exactly. `verify_video_struct.py` checks that
     merging all scene narrations reproduces `script.md`.

   **Narration length:** each line (scene narration) MUST be **≤ 50 characters —
   a ceiling, not a target**. Aim for a substantive line of roughly **20-45
   characters** and **vary the length**; do NOT reduce them all to 10-character
   fragments. If a line is too long, fix it in `script.md` and re-run the
   generator with `--force`.

2. **Fill the visuals, data and text — one story at a time.** Working one chapter
   at a time, complete that story's scenes before moving to the next (do NOT fill
   every story in one bulk pass). For each scene:
   - Decide the expression method using
     [expression_intent_mapping.md](expression_intent_mapping.md):
     - **AIGC scenes** (`is_aigc_scene: true`, `asset_generation_method: aigc`): need AI-generated imagery/video
     - **Stock scenes** (`is_aigc_scene: true`, `asset_generation_method: stock`): search web stock media — only for generic, non-specific visuals (see the stock mapping files below)
     - **Data/text scenes** (`is_aigc_scene: false`): filled with text/data directly into Remotion components
   - **Apply style-specific constraints** from [special-rules.md](special-rules.md)
     based on `project.video_style` (e.g. a documentary's first scene MUST be a
     video; a product intro opens on the product's appearance). These rules
     override the general mapping where they apply.
   - **Check `stock_media` flags before choosing stock:** read `project_config.yaml`
     → `stock_media.search_image` (default true) and `stock_media.search_video`
     (default false), and only then load the matching reference:
     - `search_image: true` → consult [stock_image_mapping.md](stock_image_mapping.md)
       for which intents suit a stock image (AssetImage / KenBurnsImage).
     - `search_video: true` → consult [stock_video_mapping.md](stock_video_mapping.md)
       for which intents suit stock video (AssetVideo).
     If a flag is false, do NOT load that file and do NOT set
     `asset_generation_method: stock` for that type — use AIGC instead. Example:
     if `search_video: false`, all video-type scenes must use
     `asset_generation_method: aigc` even when the content is generic. Also,
     `stock_media.sources` must be non-empty for stock search to work at all.
   - Fill the display fields from the research and the chapter script: `intent`,
     `is_aigc_scene`, `type`, `remotion_component`, `visual_content`, `data`,
     `text`, `workflows`.
   - Leave EMPTY (auto-filled later): `asset_path`, `origin_asset_path`,
     `narration.total_frame`, `narration.audio_path`.
   - **Do NOT change `narration.content`** — it must stay equal to its `script.md`
     line (`verify_video_struct.py` enforces this).
   - **Data/text fields are data points, not sentences.** For `data`-component
     scenes, the `data` JSON's `label`/`title`/`suffix`/`headers` fields must be
     short labels (a few words, no sentence punctuation); the narrative sentence
     stays whole in `narration.content`. Do not create a `StatCounter`/`DataBar`
     scene just because the narration contains a number — only when the metric
     is the scene's point. See [special-rules.md](special-rules.md) general
     rules 4–5. (`verify_remotion_data` rejects sentence punctuation in labels.)

3. **One scene = one narration:** each scene has exactly one nested `narration`
   (already created from the script line). The scene occupies its whole narration
   duration.

4. **Reference:** [demo_projects/project1/video1/video_struct.yaml](demo_projects/project1/video1/video_struct.yaml)

5. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_video_struct.py" --video-struct /abs/path/video_struct.yaml
   ```
   If it fails, fix and re-validate. Do NOT proceed until exit 0.

---

## Step 7: TTS Synthesis + Frame Calculation

**When:** After video_struct.yaml passes validation.

**What to do:**

1. Run TTS synthesis **(use `--timeout 3600` for safety — TTS may take several minutes per narration)**:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_tts.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml \
     --timeout 3600
   ```
   - `--timeout 3600` (default): per-TTS subprocess timeout (1h)
   This will:
   - Generate `speech.wav` for each scene's narration
   - Measure audio duration via ffprobe
   - Calculate `total_frame = ceil(duration × fps)`
   - Update `video_struct.yaml` `narration.audio_path` (pointing to .wav) and `narration.total_frame`

   **Idempotent:** re-running skips narrations whose audio already exists
   (reported as `skipped`) — safe to resume after an interruption. Pass
   `--force` to regenerate ALL audio. Use `--force` after editing any
   `narration.content`, otherwise the stale audio is kept.

2. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_audio.py" --video-struct /abs/path/video_struct.yaml
   ```
