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

Each section is driven by **three layers**: narration (master clock), data materials (charts/stats), and text materials (quotes/bullets/callouts). The `visual:` block picks a primary component; the `data:` and `text:` blocks add supporting visuals that render alongside it.

Schema:

```yaml
- name: hero
  label: 引子
  narration: |
    1998年9月2日，瑞士航空111号班机从纽约肯尼迪机场起飞，
    目的地是日内瓦。这架MD-11客机上载有229人。
  visual:
    component: FullBleedLayout
    asset_id: hero_bg
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

- name: impact
  label: 事故数据
  narration: |
    Swissair 111不是孤立事件。1990年代全球航空事故率居高不下，
    每一次事故都在推动安全标准更新。
  visual:
    component: FullBleedLayout
  # Data materials: structured statistics rendered as chart components.
  data:
    - type: stat                   # single big number
      value: "229"
      unit: 人
      label: 全部遇难
      description: "1998年9月2日，大西洋上空"
    - type: bar_chart              # bar chart
      title: 全球航空致命事故率（每百万架次）
      items:
        - { label: "1970s", value: 4.8 }
        - { label: "1980s", value: 2.2 }
        - { label: "1990s", value: 1.3 }
        - { label: "2000s", value: 0.7 }
        - { label: "2010s", value: 0.3 }
    - type: metrics                # KPI row
      title: 1998年航空安全数据
      metrics:
        - { value: "16", label: 致命事故, icon: "alert-triangle" }
        - { value: "1244", label: 遇难人数, icon: "users" }
        - { value: "83%", label: 人为因素占比, icon: "user" }
        - { value: "6%", label: 机械故障, icon: "settings" }
  # Text materials: quotes, key facts, bullet lists rendered as text components.
  text:
    - type: quote                  # pull quote
      quote: "这起事故直接推动了全球航空布线安全规范的修订。"
      attribution: "加拿大运输安全委员会 (TSB), 1999年最终报告"
    - type: key_points             # icon bullet list
      title: 事故三大诱因
      items:
        - { icon: "zap", title: Kapton电线电弧, description: "安装错误的电线在高空低气压下产生电弧" }
        - { icon: "flame", title: MPET易燃材料, description: "隔热层被电弧点燃，火势迅速蔓延" }
        - { icon: "alert-triangle", title: 关键系统损坏, description: "火势导致驾驶舱仪表和操纵系统失效" }

- name: analysis
  label: 专家观点
  narration: |
    航空安全专家指出，SR111事故暴露了机上易燃材料认证
    体系的漏洞...
  text:
    - type: quote
      quote: "当时的适航标准根本没想到要测试电线在低气压下的电弧风险。"
      attribution: "航空工程师, 调查报告听证会"
    - type: callout                # single highlighted fact
      icon: "info"
      text: "FAA在事故后3年内强制要求所有商用飞机更换Kapton绝缘材料。"
```

### Visual design: the three layers

Each section gets three composable visual layers. The narration audio plays over all of them. The `visual:` component is the **primary layout** — it owns the background, the title, and the overall structure. `data:` and `text:` items are **secondary** — they render inside or alongside the primary component.

| Layer | Drives | Sources | Rendered by |
| --- | --- | --- | --- |
| `visual:` (primary) | Composition + AIGC asset | `asset_id` (Step 5 manifest), `props` | SectionComponent switch |
| `data:` (secondary) | Pre-processed statistics, charts | Agent research (Step 2), official reports | `StatHighlight`, `DataBar`, `MetricsRow` |
| `text:` (secondary) | Pre-processed quotes, facts, arguments | Agent research (Step 2), interviews, documents | `QuoteBlock`, `FeatureGrid`, `IconCard` |

Data and text items should be **prepared during Step 4** using facts gathered in Step 2 research. The agent writes the `data:` and `text:` blocks alongside the narration — they are NOT auto-generated. Each data/text item gets a `type` field that maps to a specific Remotion component (see [design-guide.md](design-guide.md#data-type--component-mapping)).

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
