# Special Rules — Style-Specific Scene Constraints

> **When to load:** During Step 6 (design scene list), after choosing the
> expression method from `expression_intent_mapping.md`. These are hard
> constraints that override the general mapping for specific `video_style`
> values. Read `project.video_style` from project_config.yaml and apply the
> matching section below, plus the general rules that apply to every style.

These rules capture craft conventions that the generic intent→component mapping
does not express — for example, that a documentary should open on moving
footage, not a static card. When a rule conflicts with a cheaper default
(e.g. "use a text card"), the rule wins.

---

## General rules (all styles)

1. **First scene must be a strong visual.** The opening scene of the whole
   video (first scene of the first story) must be a full-bleed visual — an
   AIGC/stock video, an AIGC/stock image, or a `KenBurnsImage`. Never open on a
   pure text/data component (QuoteBlock, FeatureGrid, DataTable, etc.).
2. **Vary consecutive components.** Do not put two identical data/text
   components back-to-back (e.g. two DataTables or two StatCounters in a row).
   Break them up with a visual scene or a different component type.
3. **Vary the first scene of each chapter.** Each story's opening scene should
   use a different component/visual approach than the previous story's opener,
   so chapters feel distinct.
4. **On-screen data fields hold data points, never sentences.** In data/text
   components (`StatCounter`, `DataBar`, `DataTable`, `IconCard`, `FeatureGrid`,
   `Timeline`, `FlowChart`), the structured fields (`value`, `suffix`, `label`,
   `title`, `headers`, `rows`, etc.) must contain **concise metrics and short
   labels** — a few words at most, no sentence punctuation (，。；！？、). The
   full narrative sentence — the complete thought the viewer hears — belongs
   ONLY in `narration.content`. Never fracture one sentence across a big number
   and a label field; that renders as a number floating above a broken
   half-sentence (the #1 cause of "incoherent data" displays).
   - ✓ StatCounter → `value: 30`, `suffix: "天"`, `label: "搜救时长"`; and
     `narration.content: "最初的几轮搜索一无所获，黑匣子的信号在三十天后才出现。"`
   - ✗ StatCounter → `value: 30`, `suffix: "天"`, `label: "最初的几轮搜索一无所获，黑匣子的信号也在"` (narration leaked into the label).
   `verify_remotion_data` (validate-remotion-data.mjs) rejects sentence
   punctuation in these fields, so a leak fails the gate.
5. **A number inside a sentence ≠ a StatCounter scene.** Do not pick
   `StatCounter`/`DataBar` just because the narration contains a number. Use
   them only when the **metric itself is the point of the scene** (the
   narration is essentially "X reached N" / "N people …"). If the number is
   incidental to a story sentence (e.g. "the signal returned after 30 days"),
   make it a visual scene (`KenBurnsImage`/`AssetVideo`/`AssetImage`) and keep
   the whole sentence as narration.

---

## Content type balance (scene mix)

Every scene falls into one of two buckets:

- **Visual scenes** — AIGC or stock image/video (`AssetImage`, `AssetVideo`,
  `KenBurnsImage`; `is_aigc_scene: true`). They show, set mood, and carry
  cinematic weight.
- **Data/text scenes** — structured components (`QuoteBlock`, `FeatureGrid`,
  `IconCard`, `ComparisonCard`, `StatCounter`, `DataBar`, `Timeline`,
  `FlowChart`, `CodeBlock`, `DataTable`, `DiagramReveal`, `AnimationDemo`;
  `is_aigc_scene: false`). They explain, quantify, and organize information.

The right mix depends on `project.video_style`. Use the table as a planning
target for the whole video (not a hard per-chapter quota), then apply the
matching style section's rule:

| Style | Visual scenes | Data/text scenes | Character |
|-------|--------------:|-----------------:|-----------|
| documentary | **75–85%** | 15–25% | Show, don't tell — footage-led, data as seasoning |
| knowledge_sharing | 30–40% | **60–70%** | Explain — diagrams/cards lead, visuals illustrate |
| news_broadcast | 40–50% | 50–60% | Report — footage and facts in balance |
| product_intro | 50–60% | 40–50% | Showcase — product shots + feature breakdown |
| data_report | 15–25% | **75–85%** | Quantify — data-dominant, visuals frame the numbers |
| tutorial | 25–35% | 65–75% | Instruct — steps/code lead, visuals demo |

A lopsided video (e.g. a documentary that is 80% text cards, or a data report
that is 80% B-roll) feels off-genre. Aim for the target band.

---

## documentary (纪录片)

1. **First scene is a video.** The opening scene MUST be a `video` type scene
   rendered with `AssetVideo` (an establishing/atmosphere shot), not a static
   image and not a text card. Prefer a slow, wide establishing shot.
2. **Favor cinematic visuals.** Establishing shots, era/atmosphere scenes, and
   the closing scene should be video or `KenBurnsImage`; avoid stacking static
   `AssetImage` scenes.
3. **Close on a wide shot + quote.** The final scene should be a cinematic
   visual (video or KenBurnsImage) or a `QuoteBlock` summarizing the theme.
4. **Content balance: 75–85% visual, 15–25% data/text.** Footage (video +
   KenBurnsImage) is the body of a documentary; use data/text components only as
   occasional accents (a milestone Timeline, a key StatCounter, a closing
   QuoteBlock). Avoid consecutive data/text scenes.

## knowledge_sharing (知识分享)

1. **Open by stating what the viewer will learn.** The first scene should set
   up the concept (a visual or an IconCard/QuoteBlock framing the topic), not
   jump straight into dense data.
2. **Prefer explanatory components.** Concept scenes should favor
   `DiagramReveal`, `FlowChart`, `FeatureGrid`, and `AnimationDemo` over plain
   text.
3. **Content balance: 30–40% visual, 60–70% data/text.** Explanatory components
   carry the teaching; drop in an image/animation to introduce or reinforce each
   major concept so it doesn't become a wall of cards.

## news_broadcast (新闻播报)

1. **Open with a headline feel.** The first scene should establish the event —
   a `video`/image of the subject, or a bold `QuoteBlock`/title framing the
   story.
2. **Lead with facts and numbers.** Use `StatCounter`, `DataBar`, `Timeline`,
   and `DataTable` to present the news concretely; keep claims tied to data.
3. **Content balance: 40–50% visual, 50–60% data/text.** Alternate footage with
   the facts it supports — a clip establishing the event, then the numbers, then
   context — so the report feels grounded and concrete.

## product_intro (产品介绍)

1. **First scene showcases the product.** The opening scene MUST show the
   product's appearance — an `AssetImage` or `KenBurnsImage` (pan to reveal
   details) of the product, not a text card.
2. **Selling points via structured components.** Use `FeatureGrid` /
   `IconCard` for features and `ComparisonCard` for positioning against
   alternatives.
3. **Content balance: 50–60% visual, 40–50% data/text.** Pair product shots with
   the feature/spec breakdowns they illustrate; lead and close on the product
   itself.

## data_report (数据报告)

1. **Open with the key metric or trend.** The first scene should present the
   headline number/trend (`StatCounter` or `DataBar`) or a visual that frames
   the dataset — not unrelated atmosphere.
2. **Every number needs a component.** Present figures with `StatCounter`,
   `DataBar`, or `DataTable` rather than embedding raw numbers in narration-only
   scenes.
3. **Content balance: 15–25% visual, 75–85% data/text.** Data components are the
   core; use an occasional image only to frame the subject or give the eye a
   rest between dense figures.

## tutorial (教程)

1. **Open with the goal or end result.** The first scene should show what the
   viewer will build/achieve (a visual or a framing card).
2. **Steps are sequential.** Present procedures with `FlowChart` and show code
   with `CodeBlock`; keep step order explicit.
3. **Content balance: 25–35% visual, 65–75% data/text.** Steps and code lead;
   use a visual to show the end result or a concept demo at key points, not as
   filler between steps.
