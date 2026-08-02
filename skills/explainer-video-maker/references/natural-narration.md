# Natural Narration — Anti-Slop Rules for Spoken Scripts

> **When to load:** During Step 5 (write chapter narration scripts), when writing
> each chapter's `script.md`. Also applies to every `narration.content` field in
> video_struct.yaml (one narration per section).

A narration script is **heard**, not read. AI-generated prose has predictable
tells that make it sound like a machine reading a press release. This guide
removes those tells.

> **Length:** there is **no hard character cap** on a narration (`narration.content`).
> Write a complete, substantive thought and **vary the length** across narrations
> (mix fuller lines with the occasional short punch). Do NOT chop every narration
> into a tiny fragment — a line should carry real information. If one narration
> needs multiple visuals, split it into several scenes (with `percentage` shares)
> in Step 6 — for visual reasons, not for length.

---

## The 5 Core Rules (write for the ear)

1. **Cut the throat-clearing.** Delete opener filler and emphasis crutches. State the thing.
2. **Break formulaic structure.** No forced rule-of-three, no negative parallelism
   ("not X, it's Y" / "不是……而是……"), no rhetorical teaser setups.
3. **Vary rhythm.** Mix sentence lengths — short punch, then a longer one.
   Same-length sentences in a row sound robotic. Two items beat three.
4. **Trust the listener.** State facts directly. Skip softening, over-qualifying,
   hand-holding, and explaining your own metaphor.
5. **Cut the quotable.** If a line sounds like a pull-quote or slogan, rewrite it plain.

---

## Kill List — Words & Phrases

### zh-CN — AI vocabulary to avoid (rewrite or delete)

赋能、打造、深入探讨、值得一提的是、值得注意的是、不难发现、众所周知、总的来说、
综上所述、此外、然而（作连接拐杖时）、与此同时、在……的加持下、在……的浪潮下、
不断演变的格局、焦点、里程碑、标志着、见证了、是……的体现/证明/缩影、
至关重要、举足轻重、革命性、颠覆、震撼、令人叹为观止、必看、天花板、
无缝、丝滑（比喻义）、生态、闭环、抓手、拉满、遥遥领先、
从而彰显了……、进一步凸显了……、为……注入了新的活力。

### en-US — AI vocabulary to avoid

moreover, furthermore, it's worth noting, it's important to note, in today's
landscape, ever-evolving, delve into, leverage, seamless, robust, cutting-edge,
game-changer, revolutionize, unlock, empower, testament to, stands as, plays a
crucial/pivotal role, at the heart of, in the realm of, when it comes to.

### Filler → plain

| Filler | Replace with |
|--------|-------------|
| "为了实现这一目标" | "为了这一点" / drop it |
| "在这个时间点上" | "现在" |
| "值得注意的是，数据显示" | "数据显示" |
| "in order to achieve this" | "to do this" |
| "at this point in time" | "now" |
| "接下来我们来看看" | (drop, just say the thing) |

---

## Structural Tells to Break

| Tell | Sounds like | Fix |
|------|-------------|-----|
| **Rule of three** | "更快、更强、更智能" every beat | Use two items, or four, or one specific one |
| **Negative parallelism** | "这不仅是X，更是Y" / "不是……而是……" | State Y directly |
| **Rhetorical teaser** | "但事情没那么简单" / "接下来才是重点" | Just say the next thing |
| **Vague attribution** | "业内普遍认为" / "有专家指出" | Name the source + date, or drop |
| **-ing tail** | "……，从而彰显了其重要性" | End at the fact |
| **Fake range** | "从入门到精通，从原理到实战" | Say what it actually covers |
| **Generic uplift ending** | "未来可期" / "值得期待" / "让我们拭目以待" | End on a concrete fact |
| **Synonym cycling** | 主角→主人公→中心人物 in one breath | Repeat the plain word |
| **Over-qualifying** | "可能大概或许在某种程度上" | Pick one hedge or none |

---

## Calibrated Soul

Clean-but-soulless narration is still a tell. A little humanity helps:

- **Light first person is honest.** "我实测下来" / "I tested this and" grounds a claim.
  Use sparingly.
- **Acknowledge complexity.** "这点很好用，但也有代价" beats a flat superlative.
- **Be concrete.** "同一个任务，42美元降到6美元" beats "省了非常多钱".
- **No manufactured drama.** Temporal and logical transitions only
  ("先看……，再看……，问题在于……"). No suspense, no outrage.

---

## Number Formatting for TTS

Write numbers the way you'd naturally type them — `2025年`, `18个月`, `90%`.
Modern TTS reads digit+unit combinations correctly.

**Keep as digits** (TTS reads naturally):

| Type | Example |
|------|---------|
| Year | `2025年`, `1998年` |
| Duration with unit | `18个月`, `3年`, `45天` |
| Percentage | `15%`, `90%` |
| Tech units | `128GB`, `16核`, `4K` |
| Integer with Chinese unit | `2900万`, `5亿` |

**Must spell out** (TTS reads ambiguously):

| Type | Wrong | Correct |
|------|-------|---------|
| ISO date | `2025-01-15` | 2025年1月15日 |
| Multi-dot version | `v1.2.3` | v一点二点三 |
| Phone/ID string | `400-123-4567` | 四零零 一二三 四五六七 |
| Long bare integer | `3999999` | 三百九十九万九千九百九十九 |

---

## Pre-Delivery Checklist

Before finalizing narration content, verify:

- [ ] No items from the kill list remain
- [ ] No forced rule-of-three
- [ ] No rhetorical teasers or clickbait hooks
- [ ] Sentence lengths vary (not all the same)
- [ ] Attributions are named or removed
- [ ] Numbers formatted for TTS
- [ ] Ending is a concrete fact, not "未来可期"
- [ ] No narration is a tiny fragment — each carries a full thought and lengths vary across narrations
