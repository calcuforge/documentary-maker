# Stock Video Mapping (asset_generation_method: stock, type: video)

> **When to load:** Step 6 (design scene list) — **ONLY when
> `project_config.yaml` → `stock_media.search_video` is `true`** (and
> `stock_media.sources` is non-empty). `search_video` is `false` by default.
> If it is `false`, do NOT use stock video; map these intents to AIGC
> (`text-to-video` / `image-to-video`) instead, per
> `expression_intent_mapping.md`.

Stock video (searched from Pexels / Pixabay) suits scenes that benefit from
**real motion and a real-world footage look** — generic B-roll, establishing
shots, and atmospheric events where no specific subject must be depicted
accurately. Stock clips are free and realistic, but quality and duration vary,
so reserve them for scenes where authentic motion matters more than precise
content.

| Use stock video when… | Use AIGC instead when… |
|----------------------|------------------------|
| Generic B-roll / establishing motion (traffic, crowds, sky, water) | A specific historical event must be reconstructed |
| Real-world footage look (documentary feel) | The subject must match the narration precisely |
| Atmosphere with genuine motion (a mood the still image can't carry) | Consistent character/object appearance across scenes |
| A news-style generic event (no identifiable subject required) | A specific person, brand, or product in motion |
| No brand-specific or copyrighted content needed | Stylized or fictional motion |

**Component choice:** always `AssetVideo` (background role for full-bleed B-roll).

**Duration:** the search prefers the **shortest** clip that is still at least
the scene's narration length (`total_frame / fps`); the download is then
trimmed to exactly that length. If no clip is long enough, the longest
available is used. Keep stock scenes to narration-driven lengths.

**Resolution:** the search targets the project's final resolution
(`video.resolution`). If no exact match exists it downloads the largest
available and the upscale step (Step 10) enlarges it to target.

---

## Mapping by intent category

### Narrative / Atmosphere

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Establish a scene | 1950s New York street, traffic | AssetVideo | Real establishing motion is immersive and free in stock libraries. |
| Create emotional atmosphere | A city under tension, storm clouds | AssetVideo | Genuine motion/lighting carries atmosphere a still cannot. |
| Express abstract concepts | Data center, flowing network | AssetVideo | Generic tech/abstract motion is abundant in stock. |

### News

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Recreate a news event (generic) | Rocket launch, city skyline | AssetVideo | Stock news/B-roll footage is realistic and free; ideal for generic events. |
| Introduce background | Historical context, cityscape | AssetVideo | Moving backgrounds add a broadcast feel. |
