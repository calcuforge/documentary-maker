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

## Step 3: Design Chapters

**Output:** `chapters.yaml`

Schema:

```yaml
- name: hero                  # lowercase, underscore, matches timing.json section.name
  label: 引子                  # short, for chapter bar
  duration_hint_seconds: 15   # rough; char-estimate overrides during TTS
  component: FullBleedLayout   # suggestion; narration_script may override
- name: timeline
  label: 时间线
  duration_hint_seconds: 45
  component: Timeline
```

Chapter design principles:

1. **Follow the theme's narrative_arc** — each theme preset ships an `narrative_arc:` list (hook → background → ... → conclusion). Use it as a skeleton, deviating when the topic demands.
2. **Section count** — `project_prefs.content.section_count` (default 7). Aviation disasters and crime stories usually need 7-9; short historical vignettes can fit in 5.
3. **Each section = one visual idea** — if you'd need two components to render a section, split into two sections.
4. **Hero + summary always** — first section is the hook, last is the takeaway.

### Component selection hints

Use the theme's `component_suggestions` map to pick a default component per section `name`:

| Section type | Component |
| --- | --- |
| Opening title / hook | `FullBleedLayout` |
| Chronological milestones | `Timeline` |
| Causal / process | `FlowChart` / `DiagramReveal` |
| Comparison | `ComparisonCard` |
| Data / impact | `DataBar` / `MetricsRow` / `StatHighlight` |
| Quote | `QuoteBlock` |
| Media (photo / footage) | `MediaSection` / `AssetImage` / `AssetVideo` |
| Architecture / system | `DiagramReveal` |
| Steps / response | `StepProgress` |

---

## Step 4: Write Narration Script + Per-Section Visual Design

**Output:** `narration_script.yaml`

Schema:

```yaml
- name: hero
  label: 引子
  narration: |
    1998年9月2日，瑞士航空111号班机从纽约肯尼迪机场起飞，
    目的地是日内瓦。这架MD-11客机上载有229人。
    谁也没有想到，这架飞机即将在大西洋上空，
    写下航空安全史上重要的一页。
  visual:
    component: FullBleedLayout
    asset_id: hero_bg            # optional — must exist in assets/manifest.json
    props:
      title: 瑞士航空111号班机
      subtitle: "1998.09.02 · 大西洋"

- name: timeline
  label: 时间线
  narration: |
    起飞后约58分钟，机组成员注意到驾驶舱上方出现异常气味...
  visual:
    component: Timeline
    props:
      title: 关键时间线
      items:
        - { label: 00:00, description: 从肯尼迪机场起飞 }
        - { label: 00:58, description: 异常气味出现 }
        - { label: 01:14, description: 机组请求返航 }
        - { label: 01:31, description: 飞机失联 }

- name: cause_chain
  label: 事故链条
  narration: |
    调查发现，事故源于驾驶舱 ceiling 上方的电弧...
  visual:
    component: FlowChart
    props:
      title: 事故链条
      steps:
        - { label: 电弧, description: 安装错误的电线产生电弧 }
        - { label: 起火, description: 旁边易燃材料被点燃 }
        - { label: 蔓延, description: 火势蔓延至驾驶舱顶 }
        - { label: 失控, description: 仪表和操纵系统损坏 }

- name: summary
  label: 反思
  narration: |
    瑞士航空111号班机的悲剧，直接推动了全球航空 wiring
    安全规范的修订...
  visual:
    component: StatHighlight
    props:
      value: "229"
      unit: 人
      label: 全部遇难
      description: 此次事故的遇难者人数
```

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

### Visual design rules

- **Asset binding** — `visual.asset_id` must reference an id in `assets/manifest.json`. Plan the asset in Step 5 before committing the section name to the script.
- **Component override** — `visual.component` overrides `chapters.yaml`'s `component` field. Use this when the narration suggests a different layout than the chapter designer picked.
- **Props** — pass through to the Remotion component as `props`. Type-safe against the component's expected shape (`Timeline` expects `items[]` with `label` + `description`, etc.).
- **Text-only sections** are fine. Omit `visual.asset_id`; pick a non-media component.

---

## Per-section audio length estimation

Char-count estimator (in `scripts/estimate_timing.py`) distributes total audio time by character weight:
- CJK char = 1.0
- ASCII letter/digit = 0.5
- Punctuation, whitespace = 0.0

So a section with 100 CJK chars and a section with 200 ASCII chars get roughly the same time slice. Plan sections so char counts roughly match the desired duration split — if a section needs to be 30% of total runtime, its narration char weight should be ~30% of the script's total weight.

The estimator compensates for transition overlap (each section's `duration_frames` is scaled proportionally so total = `timing.total_frames`). Don't try to hand-tune section durations in `chapters.yaml` — `duration_hint_seconds` is just a planning hint.

---

## Manual-mode gates

After each step, in Manual Mode:

1. Show the user the file just produced (`topic_definition.md`, `topic_research.md`, `chapters.yaml`, `narration_script.yaml`).
2. Ask: "Looks good? Reply with edits, or 'continue' to proceed."
3. If edits: revise, re-show. Do NOT proceed until explicit "continue" / "ok" / "looks good".
4. Apply edits in-place; do not rewrite the whole file unless asked.

In Auto Mode, skip the gate; just report the file path and move to the next step.
