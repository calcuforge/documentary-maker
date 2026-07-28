# Workflow — Script Phase (Steps 1-4)

> **Load when:** workflow start, or when the user asks about topic definition, research, chapter design, or narration script writing.

## Execution Modes

Detect at workflow start:

- "Make a video about..." / no special instructions → **Auto Mode** (default). Pipeline runs end-to-end.
- "I want to control each step" / "interactive" / "let me review" → **Manual Mode**. Each AI product (script, narration, assets, TTS, composition) waits for explicit confirmation before next step.

In Auto Mode, the only mandatory stop is Step 11 (`verify_output.py` exit 0/2). In Manual Mode, pause after every step that produces an AI artifact.

---

## Step 1: Define Topic Direction

**Output:** `topic_definition.md` in the video dir.

Auto: infer from the user's request. Match trigger keywords → category → theme. Sensible defaults (audience: general, tone: serious, duration: 3-7 min).

Manual: confirm each item:
1. **Event/subject** — what specific event or topic? (e.g. "Swissair Flight 111, 1998")
2. **Category** — aviation-disaster / history / crime / natural-disaster
3. **Angle** — causal analysis / narrative retelling / impact-focused / historical context
4. **Audience** — general / technical / region-specific
5. **Duration** — short (3-5 min) / medium (5-8 min) / long (8-15 min)
6. **Language** — zh-CN / en-US (defaults from project prefs)

Write a short brief (200-300 words) explaining the angle, scope, and why this topic matters.

---

## Step 2: Research Topic

**Output:** `topic_research.md`

Research is driven by **providers** configured in the theme preset (`research_providers`). Generate a research plan, then execute each provider in order.

### 2a. Generate the research plan

```bash
python3 "$SKILL_DIR/scripts/cli.py" research plan --project $P --video $V
```

This emits a JSON plan with one step per enabled provider. Each step has an `action` description telling the agent exactly what to do. Provider types:

| Provider | What the agent does |
| --- | --- |
| `agent_search` | Web search using the agent's native search tool. Runs each `queries` entry, reads top 3-5 results, extracts facts. |
| `web_fetch` | Directly fetches each URL in `urls`. Extracts structured facts from Wikipedia infoboxes, official reports, databases. |
| `rss` | Fetches each RSS feed URL, parses `<item>` entries, compiles headlines + summaries + links. |
| `custom_script` | Agent writes a Python script (requests + feedparser + bs4) to retrieve structured data. The `script_hint` describes what it should do. Save in `videos/{v}/scripts/`, run, capture output. |

### 2b. Execute the plan

Run each provider step **in order**. Same-type providers within one step can be parallelized (e.g. multiple `web_fetch` URLs in parallel).

After all providers complete, merge findings into `topic_research.md`:
- Factual summary (dates, names, statistics, events, quotes) — cross-reference at least 3 sources.
- For news-type videos: top headlines + lead paragraph per story.
- For documentary-type videos: timeline of events, cause/effect chains, key figures.
- Source URLs at the bottom — `video_info.yaml` (Step 11) reads them.

### 2c. Provider configuration

Themes configure providers in `research_providers:`. Examples:

**Documentary (aviation-disaster):** `agent_search` + `web_fetch` enabled. Pre-written search queries target accident reports, Wikipedia, NTSB.
**News (tech-news):** `rss` + `agent_search` + `custom_script` enabled. RSS feeds pull headlines; agent_search fills background; custom_script aggregates and filters.
**Knowledge-sharing:** `agent_search` + `web_fetch` enabled. Broad search queries + Wikipedia for foundational facts.

Project-level overrides in `project_prefs.yaml` under `research.providers:` win over theme defaults.

---

## Step 3: Design Video Structure (chapter → scene skeleton)

**Output:** `narration_script.yaml` — skeleton only (chapters + scene names/labels). Narration and shots are filled in Step 4, in the same file. There is no separate `chapters.yaml`.

Structure model:

- **Chapter** — organizational grouping (metadata, downstream chapter lists). Never a render unit.
- **Scene** — one narration block + one or more shots. The unit of TTS, subtitles, timing, and rendering.
- **Shot** — one visual unit: source material + auxiliary layers.

Skeleton schema:

```yaml
chapters:
  - name: opening             # lowercase, underscore
    label: 开篇                # short display label
    scenes:
      - name: hero            # lowercase, underscore, unique across the whole video
        label: 引子
      - name: timeline
        label: 时间线
  - name: main
    label: 主体
    scenes:
      - name: cause_chain
        label: 事故链条
```

Structure design principles:

1. **Follow the theme's narrative_arc** — each theme preset ships a `narrative_arc:` list (hook → background → ... → conclusion). Use it as the chapter skeleton, deviating when the topic demands.
2. **Scene count** — `project_prefs.content.section_count` (default 7) is the target *scene* count. Aviation disasters and crime stories usually need 7-9 scenes; short historical vignettes can fit in 5.
3. **Each scene = one narration beat** — one idea per scene. If you'd need two unrelated visuals back to back, that's two scenes (or one scene with multiple shots covering the same beat from different angles).
4. **Multi-shot scenes** — use multiple shots in a scene when one narration beat benefits from a visual cut (e.g. a background image shot → a diagram shot while the same narration continues). A scene with no explicit `shots:` list renders as a single implicit shot.
5. **Hero + summary always** — first scene is the hook, last is the takeaway.

---

## Step 4: Fill Narration + Per-Scene Shot Design

**Output:** `narration_script.yaml` (complete: chapters → scenes → shots)

Fill each skeleton scene with `narration:` (the scene's TTS text — the scene's audio-master clock) and `shots:` (the visual units played in order while the narration runs). Each shot is driven by **source material + auxiliary layers**: an optional `asset_id` (AIGC / stock / user media), a `component` (render template), `props`, and the auxiliary layers `data:` (charts/stats), `text:` (quotes/bullets/callouts), `overlays:` (transparent webm animations).

Schema:

```yaml
chapters:
  - name: opening
    label: 开篇
    scenes:
      - name: hero
        label: 引子
        narration: |
          1998年9月2日，瑞士航空111号班机从纽约肯尼迪机场起飞，
          目的地是日内瓦。这架MD-11客机上载有229人。
        shots:
          - name: hero_01                  # lowercase, underscore; unique within the scene
            component: FullBleedLayout     # render template (component list below)
            asset_id: hero_bg              # source material (optional; omit for gradient/pure-component)
            duration_hint_seconds: 8       # optional; scenes split audio time by hints (even without)
            props:
              title: 瑞士航空111号班机
              subtitle: "1998.09.02 · 大西洋"
            overlays:                      # auxiliary layer: transparent animation (optional)
              - asset_id: smoke_overlay
                style: { opacity: 0.6 }

      - name: timeline
        label: 时间线
        narration: |
          起飞后约58分钟，机组成员注意到驾驶舱上方出现异常气味。
          随后烟雾进入驾驶舱，机组宣布进入紧急状态并请求返航。
        shots:
          - name: timeline_01              # material shot
            component: AssetImage
            asset_id: timeline_bg
            duration_hint_seconds: 6
            props: { layout: full, caption: 搜救现场 }
          - name: timeline_02              # pure-component shot (no material)
            component: Timeline
            duration_hint_seconds: 9
            props:
              items:
                - { label: 00:00, description: 从肯尼迪机场起飞 }
                - { label: 00:58, description: 异常气味出现 }
                - { label: 01:14, description: 机组请求返航 }
                - { label: 01:31, description: 飞机失联 }

  - name: main
    label: 主体
    scenes:
      - name: impact
        label: 事故数据
        narration: |
          Swissair 111不是孤立事件。1990年代全球航空事故率居高不下，
          每一次事故都在推动安全标准更新。
        shots:
          - name: impact_01
            component: FullBleedLayout
            # Data materials: structured statistics rendered as chart components.
            data:
              - type: stat                 # single big number
                value: "229"
                unit: 人
                label: 全部遇难
                description: "1998年9月2日，大西洋上空"
              - type: bar_chart            # bar chart
                title: 全球航空致命事故率（每百万架次）
                items:
                  - { label: "1970s", value: 4.8 }
                  - { label: "1980s", value: 2.2 }
                  - { label: "1990s", value: 1.3 }
                  - { label: "2000s", value: 0.7 }
                  - { label: "2010s", value: 0.3 }
            # Text materials: quotes, key facts, bullet lists.
            text:
              - type: quote                # pull quote
                quote: "这起事故直接推动了全球航空布线安全规范的修订。"
                attribution: "加拿大运输安全委员会 (TSB), 1999年最终报告"
              - type: key_points           # icon bullet list
                title: 事故三大诱因
                items:
                  - { icon: "zap", title: Kapton电线电弧, description: "安装错误的电线在高空低气压下产生电弧" }
                  - { icon: "flame", title: MPET易燃材料, description: "隔热层被电弧点燃，火势迅速蔓延" }
                  - { icon: "alert-triangle", title: 关键系统损坏, description: "火势导致驾驶舱仪表和操纵系统失效" }
```

### Shot design: material + auxiliary layers

A shot composes one source material with up to three auxiliary layer types. The scene's narration audio plays over all shots of that scene.

| Field | Role | Sources | Rendered by |
| --- | --- | --- | --- |
| `component` + `asset_id` + `props` | **Source material / primary layout** — owns background, title, structure | AIGC (Step 5), stock search, user files, or pure component (no asset) | ShotComponent switch (FullBleedLayout / AssetImage / AssetVideo / Timeline / FlowChart / ...) |
| `data:` | Auxiliary layer — pre-processed statistics, charts | Agent research (Step 2), official reports | `StatHighlight`, `DataBar`, `MetricsRow`, `StepProgress`, `FlowChart`, `Timeline`, `ComparisonCard` |
| `text:` | Auxiliary layer — quotes, facts, arguments | Agent research (Step 2), interviews, documents | `QuoteBlock`, `IconCard`, `FeatureGrid`, `DiagramReveal` |
| `overlays:` | Auxiliary layer — transparent animation over the material | user/stock webm (VP9 alpha, 30 fps, duration ≥ shot window) | `OverlayLayer` |

Data and text items should be **prepared during Step 4** using facts gathered in Step 2 research. The agent writes the `data:` and `text:` blocks alongside the narration — they are NOT auto-generated. Each data/text item gets a `type` field that maps to a specific Remotion component (see [design-guide.md](design-guide.md)).

### Shot component selection

Use the theme's `component_suggestions` map (keyed by semantic scene names) as the starting point, then pick per shot:

| Shot content | Component | Material needed? |
| --- | --- | --- |
| Opening title / hook | `FullBleedLayout` | background asset (or gradient) |
| Photo / footage frame | `AssetImage` / `AssetVideo` | yes (inline / broll) |
| Full-bleed backdrop | `FullBleedLayout` with `asset_id` | yes (background role, Ken Burns) |
| Chronological milestones | `Timeline` | no |
| Causal / process | `FlowChart` | no |
| Architecture / system | `DiagramReveal` | no |
| Comparison | `ComparisonCard` | no |
| Data / impact | `DataBar` / `MetricsRow` (as component or `data:` item) | no |
| Quote | `QuoteBlock` | no |
| Steps / response | `StepProgress` | no |

A scene mixing material and data usually wants two shots: one material shot (background image / b-roll), then one pure-component shot (chart) — rather than stacking everything on one frame.

### Visual composition guidance (`visual_composition`)

Each theme preset includes a `visual_composition:` block — a **non-binding suggestion** that tells the agent how to allocate the four visual source types across sections. It does NOT enforce ratios; it guides judgment when the agent designs each section's `visual:`, `data:`, and `text:` blocks.

| Source | `visual_composition` key | When to use |
| --- | --- | --- |
| AI合成 (images/video) | `aigc` | No real photos available; need conceptual scenes; ComfyUI t2i/i2v |
| 素材搜索 (stock/web) | `stock` | Real photos exist online; agent web search for images; user-supplied files |
| 数据图表组件 | `data_charts` | Statistics, trends, KPIs — rendered by `data[]` items (DataBar, StatHighlight, MetricsRow, Timeline) |
| 文本资料组件 | `text_components` | Quotes, arguments, bullet points — rendered by `text[]` items (QuoteBlock, IconCard, FeatureGrid) |

Levels: `high` (primary visual source for this category), `medium` (supporting), `low` (occasional), `none` (skip).

**Example — aviation-disaster:** `aigc: high, stock: low, data_charts: medium, text_components: low`
→ Most sections use AI-generated imagery. A few sections add data charts (casualty stats, accident rates). Occasional text quotes from investigation reports. Very little stock media hunting.

**Example — tech-news:** `aigc: low, stock: medium, data_charts: medium, text_components: high`
→ Most sections use text components (specs, features, comparisons). Some stock photos of products. Moderate use of data charts. AI-generated images only for futuristic concepts.

The agent reads `visual_composition` from the resolved theme, then designs each section's layers accordingly. Full per-theme values in [design-guide.md](design-guide.md#visual-composition-per-theme).

### Data item types

| `type` | What it shows | Remotion component | Props |
| --- | --- | --- | --- |
| `stat` | One big number with label | `StatHighlight` | `value`, `unit`, `label`, `description` |
| `bar_chart` | Horizontal bar chart | `DataBar` | `title`, `items: [{label, value}]` |
| `metrics` | 4-up KPI dashboard | `MetricsRow` | `title`, `metrics: [{value, label, icon}]` |
| `steps` | Numbered process steps | `StepProgress` | `title`, `steps: [{label, description}]` |
| `flow` | Causal chain / process | `FlowChart` | `title`, `steps: [{label, description, icon}]` |
| `timeline` | Chronological events | `Timeline` | `title`, `items: [{label, description}]` |
| `comparison` | A vs B side-by-side | `ComparisonCard` | `title`, `left: {title, items}`, `right: {title, items}` |

### Text item types

| `type` | What it shows | Remotion component | Props |
| --- | --- | --- | --- |
| `quote` | Pull quote with attribution | `QuoteBlock` | `quote`, `attribution` |
| `key_points` | Icon-bulleted feature list | `FeatureGrid` or `IconCard` | `title`, `items: [{icon, title, description}]` |
| `callout` | Single highlighted fact/callout | `IconCard` (single) | `icon`, `title` (or `text`) |
| `diagram` | Node-edge diagram | `DiagramReveal` | `title`, `nodes: [{id, label}]`, `edges: [{from, to}]` |

### Narration rules (anti-slop)

Same spirit as video-podcast-maker's `natural-narration.md`:

1. **Cut opener filler** — "接下来我们来看看", "总的来说", "首先让我们了解一下" → delete.
2. **No rule-of-three** — if you find yourself writing "第一... 第二... 第三..." mid-script, restructure.
3. **No negative parallelism** — "不是X，而是Y" reads as AI press release. State the fact directly.
4. **No rhetorical teasers** — "让我们看看发生了什么" → just describe what happened.
5. **Vary sentence length** — mix short factual beats with longer explanatory sentences. End sections on a concrete fact, not "未来可期".

### Number formatting

- Years (`1998年`, `2025年`), durations (`18个月`, `45天`), percentages (`90%`), version+unit (`4K`, `128GB`) → keep as digits; TTS reads them naturally.
- Dash-separated dates (`1998-09-02`) → convert to `1998年9月2日` to avoid TTS ambiguity.
- Phone numbers, ID strings → spell out or group with spaces (`4 0 0 - 1 2 3 - 4 5 6 7`).

### Shot design rules

- **Asset binding** — `asset_id` (and every `overlays[].asset_id`) must reference an id in `assets/manifest.json`. `assets validate` cross-checks references both ways. Plan the asset in Step 5 before rendering.
- **Props** — pass through to the Remotion component as `props`. Type-safe against the component's expected shape (`Timeline` expects `items[]` with `label` + `description`, etc.).
- **Pure-component shots** are fine — omit `asset_id` and pick a non-media component (`Timeline`, `FlowChart`, `QuoteBlock`, ...).
- **duration_hint_seconds** — relative, not absolute. The scene's real audio length is distributed across shots proportionally to hints (unhinted shots get the mean hint; no hints anywhere → even split). Use hints to give a chart shot more dwell time than a b-roll flash.
- **Scene narration ends on a full sentence** — each scene is one TTS call; ending mid-sentence creates an unnatural seam at the scene join.

---

## Timing model (scene level)

With per-scene TTS there is **no cross-scene estimation**: each scene's total duration comes directly from ffprobing that scene's `narration.wav`. Two distributions happen inside a scene (`scripts/estimate_timing.py`):

1. **Shot durations** — the scene's real duration is distributed across its shots by `duration_hint_seconds` (proportional; unhinted shots get the mean of positive hints; no hints → even split). Remainder absorbed into the last shot.
2. **Subtitle cues** — the scene narration is split at sentence-final punctuation (`。.!?！？`), and cue durations allocated by char weight:
   - CJK char = 1.0
   - ASCII letter/digit = 0.5
   - Punctuation, whitespace = 0.0

So within a scene, a cue with 30 CJK chars gets ~2× the time of a 30-ASCII-char cue. Cue times are relative to the scene start; `tts merge` offsets them into the video-global `narration_audio.srt`.

The composition compensates for shot transition overlap (each shot's `duration_frames` is scaled proportionally so the rendered total = the scene's `timing.total_frames`). `duration_hint_seconds` shapes the *relative* split only — the scene audio always sets the absolute total.

---

## Manual-mode gates

After each step, in Manual Mode:

1. Show the user the file just produced (`topic_definition.md`, `topic_research.md`, `narration_script.yaml` — skeleton at Step 3, full version at Step 4).
2. Ask: "Looks good? Reply with edits, or 'continue' to proceed."
3. If edits: revise, re-show. Do NOT proceed until explicit "continue" / "ok" / "looks good".
4. Apply edits in-place; do not rewrite the whole file unless asked.

In Auto Mode, skip the gate; just report the file path and move to the next step.
