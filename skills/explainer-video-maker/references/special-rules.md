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

## knowledge_sharing (知识分享)

1. **Open by stating what the viewer will learn.** The first scene should set
   up the concept (a visual or an IconCard/QuoteBlock framing the topic), not
   jump straight into dense data.
2. **Prefer explanatory components.** Concept scenes should favor
   `DiagramReveal`, `FlowChart`, `FeatureGrid`, and `AnimationDemo` over plain
   text.

## news_broadcast (新闻播报)

1. **Open with a headline feel.** The first scene should establish the event —
   a `video`/image of the subject, or a bold `QuoteBlock`/title framing the
   story.
2. **Lead with facts and numbers.** Use `StatCounter`, `DataBar`, `Timeline`,
   and `DataTable` to present the news concretely; keep claims tied to data.

## product_intro (产品介绍)

1. **First scene showcases the product.** The opening scene MUST show the
   product's appearance — an `AssetImage` or `KenBurnsImage` (pan to reveal
   details) of the product, not a text card.
2. **Selling points via structured components.** Use `FeatureGrid` /
   `IconCard` for features and `ComparisonCard` for positioning against
   alternatives.

## data_report (数据报告)

1. **Open with the key metric or trend.** The first scene should present the
   headline number/trend (`StatCounter` or `DataBar`) or a visual that frames
   the dataset — not unrelated atmosphere.
2. **Every number needs a component.** Present figures with `StatCounter`,
   `DataBar`, or `DataTable` rather than embedding raw numbers in narration-only
   scenes.

## tutorial (教程)

1. **Open with the goal or end result.** The first scene should show what the
   viewer will build/achieve (a visual or a framing card).
2. **Steps are sequential.** Present procedures with `FlowChart` and show code
   with `CodeBlock`; keep step order explicit.
