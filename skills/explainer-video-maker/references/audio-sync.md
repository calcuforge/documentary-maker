# Audio-Master Clock & Sync

## The rule

**Audio is the master clock.** The narration TTS audio (`narration_audio.wav`) sets the video's total duration. `timing.json.total_duration` MUST match the WAV within ±0.5s. Every section's `duration_frames` derives from this total.

The char-count estimator (`scripts/estimate_timing.py`) is the v1 timing source because ComfyUI's `index_tts_2` workflow returns audio only — no word-level timestamps. Real audio length sets the **total**; char weights distribute time **across sections and SRT cues**.

## Char-count algorithm

```python
def char_weight(ch):
    if ch.isspace(): return 0.0
    if ch in SENT_END or ch in SOFT_END: return 0.0   # 。.!?！？，,;：:、
    if CJK(ch): return 1.0
    if ASCII_LETTER_OR_DIGIT(ch): return 0.5
    return 0.0   # other punctuation, symbols
```

For a section with narration text, `section_weight = sum(char_weight(c) for c in text)`.

Then:
```
section_duration = total_duration * (section_weight / total_weight)
```

Inside a section, narration is split into SRT cues at sentence-final punctuation (`。.!?！？`). Each cue gets:
```
cue_duration = section_duration * (cue_weight / sum(cue_weights))
```

## Why this works (and where it drifts)

✅ **Works well** when narration pacing is roughly uniform — Chinese sentences read at similar speeds, English sentences at similar speeds.

⚠️ **Drifts** when:
- The script mixes very short and very long sentences in one section → cue alignment within section may be off by ±2s.
- The TTS engine pauses heavily at punctuation → punctuation has 0 weight but takes real time. The estimator compensates by absorbing drift into the last cue of each section.
- Numbers, version strings (`v1.2.3`) read slowly per digit → ASCII digit weight 0.5 under-estimates.

If you need tighter alignment, plan sections so char counts roughly match desired durations. Don't hand-tune `duration_hint_seconds` in `chapters.yaml` — it's only a planning hint.

## Drift correction

`estimate_timing.py` automatically:

1. Calls `ffprobe narration_audio.wav` for real `total_duration`.
2. Computes per-section durations from char weights.
3. Sums them; if drift from `total_duration` > 0.001s, absorbs the remainder into the last section's `duration` and `end_time`.
4. Recomputes `start_frame` / `duration_frames` from times × fps.

## TransitionSeries overlap compensation

The Remotion template's `Video.tsx` (and our generated per-video version) uses `@remotion/transitions` `TransitionSeries`. The series renders `sum(sections) - (N-1) * overlap_frames`. To keep the rendered total equal to `timing.total_frames`, every section's `duration_frames` is scaled proportionally:

```
target_total = timing.total_frames + transitionCount * effectiveTransitionFrames
audioScale = target_total / originalTotal
section.duration_frames = round(section.duration_frames * audioScale)
```

Rounding error absorbs into the last section. Verbatim from `remotion-video-template/src/Video.js`.

## Validation checkpoints

| After step | Check |
| --- | --- |
| 6 (TTS) | `timing.json.total_duration` ≈ `ffprobe narration_audio.wav` (±0.5s) |
| 9 (Render) | `ffprobe output.mp4` duration ≈ `narration_audio.wav` (±0.5s) |
| 11 (Verify) | `verify_output.py` exit 0 (or 2) |

## Re-align if drift >0.5s

```bash
python3 "$SKILL_DIR/scripts/estimate_timing.py" --video-dir "$VDIR" --fps 30
```

Re-runs the estimator with the same audio. If drift persists, check that `narration_script.yaml` sections match what was actually concatenated and sent to TTS.

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
