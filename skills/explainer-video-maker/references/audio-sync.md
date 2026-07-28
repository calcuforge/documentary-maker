# Audio-Master Clock & Sync

## The rule

**Audio is the master clock, per scene.** TTS is generated per scene, so each scene's real narration WAV (`scenes/{s}/narration.wav`) sets that scene's duration exactly — `scenes/{s}/timing.json.total_duration` equals the ffprobed WAV length (no estimation at scene level). The video's total duration is the sum of scene durations; the root `timing.json` aggregates them.

Inside a scene, two distributions happen (`scripts/estimate_timing.py`):

1. **Shot durations** — distributed across the scene's real duration by `duration_hint_seconds` (proportional; unhinted shots get the mean of positive hints; no hints anywhere → even split).
2. **Subtitle cues** — narration split at sentence-final punctuation, cue durations by char weight (the char-count estimator below).

## Scene TTS normalization (concat-critical)

Every scene WAV is normalized to **48 kHz mono pcm_s16le** by `tts run` before anything else. This is what lets `tts merge` build the video-level track with `ffmpeg -f concat -c copy` — lossless, no re-encode. If you ever produce a scene WAV outside the toolchain, normalize it the same way:

```bash
ffmpeg -y -i raw.wav -ar 48000 -ac 1 -c:a pcm_s16le scenes/{s}/narration.wav
```

Never hand-splice scene WAVs or SRTs — always through `cli.py tts merge`, which also offsets SRT cues and aggregates timing.

## Char-count algorithm (subtitle cues)

ComfyUI's `index_tts_2` workflow returns audio only — no word-level timestamps — so cue times inside a scene are estimated by character weight:

```python
def char_weight(ch):
    if ch.isspace(): return 0.0
    if ch in SENT_END or ch in SOFT_END: return 0.0   # 。.!?！？，,;：:、
    if CJK(ch): return 1.0
    if ASCII_LETTER_OR_DIGIT(ch): return 0.5
    return 0.0   # other punctuation, symbols
```

Cues split at sentence-final punctuation (`。.!?！？`); each cue gets:

```
cue_duration = scene_duration * (cue_weight / sum(cue_weights))
```

Cue times are **relative to the scene start** (from 0). `tts merge` offsets each scene's cues by the cumulative duration of preceding scenes when building `narration_audio.srt`.

### Where cue alignment drifts

✅ Works well when narration pacing is roughly uniform within a scene.

⚠️ Drifts when:
- A scene mixes very short and very long sentences → individual cues may be off by ±1-2s (subtitle timing only; scene total is exact).
- The TTS engine pauses heavily at punctuation → punctuation has 0 weight but takes real time; remainder absorbs into the last cue.
- Numbers / version strings (`v1.2.3`) read slowly per digit → ASCII digit weight 0.5 under-estimates.

Scene joins: end every scene's narration on a full sentence — each scene is an independent TTS call, so a mid-sentence cut produces an audible prosody seam at the merge boundary.

## TransitionSeries overlap compensation (per scene)

Each scene's generated `scene.tsx` runs its shots in a `TransitionSeries` (transitions between shots). The series renders `sum(shots) - (N-1) * overlap_frames`. To keep the rendered total equal to the scene's `timing.total_frames`, every shot's `duration_frames` is scaled proportionally:

```
target_total = scene_timing.total_frames + transitionCount * effectiveTransitionFrames
audioScale = target_total / originalTotal
shot.duration_frames = round(shot.duration_frames * audioScale)
```

Rounding error absorbs into the last shot. Same math as `remotion-video-template/src/Video.js`, scoped to one scene.

## Validation checkpoints

| After step | Check |
| --- | --- |
| 6 (per-scene TTS) | `scenes/{s}/timing.json.total_duration` == `ffprobe scenes/{s}/narration.wav` (exact by construction) |
| 6 (merge) | root `timing.json.total_duration` ≈ `ffprobe narration_audio.wav` (±0.5s); `audit beats` clean |
| 9 (scene render) | each `scenes/{s}/scene.mp4` ≈ its `narration.wav` (±0.5s) — `audit beats` checks this |
| 9 (scene merge) | `ffprobe output.mp4` ≈ `narration_audio.wav` (±0.5s) |
| 11 (verify) | `verify_output.py` exit 0 (or 2) |

```bash
python3 "$SKILL_DIR/scripts/cli.py" audit beats --video-dir "$VDIR"
```

## Re-align if something drifts

| Symptom | Fix |
| --- | --- |
| Scene timing vs scene WAV drift | `cli.py tts run --scene {s}` (regenerate scene timing from the WAV) |
| Root timing vs merged WAV drift | `cli.py tts merge` (re-aggregate) |
| scene.mp4 vs scene WAV drift | `cli.py compose` + re-render that scene + `cli.py merge` |
| SRT cues feel off inside a scene | restructure that scene's narration (shorter sentences) and re-run its TTS |

Scene-level regeneration is cheap — only the affected scene re-synthesizes and re-renders; the rest of the video is untouched until the final `merge`.

## Char weight table reference

For the curious — the full weight table is in `scripts/estimate_timing.py`:

| Char class | Weight | Examples |
| --- | --- | --- |
| CJK ideographs | 1.0 | 中文汉字, カタカナ |
| ASCII letter | 0.5 | A-Z, a-z |
| ASCII digit | 0.5 | 0-9 |
| Sentence-final punct | 0.0 | `。 . ! ? ！ ？` |
| Soft punct | 0.0 | `， , ; ： ： 、` |
| Whitespace | 0.0 | space, newline, tab |
| Other | 0.0 | emoji, symbols, fullwidth punct |
