"""Shared scene-frame allocation and narration chunking utilities.

One narration maps to 1-N scenes; each scene carries an integer `percentage`
(sum = 100 per narration). This module is the single source of truth for:
  - splitting a narration's total_frame across its scenes (largest-remainder),
  - splitting narration content into short subtitle chunks (sentence-first).
Used by search_stock_media.py (Step 8) and generate_remotion_sections.py (Step 12)
so both derive identical per-scene frame counts.
"""

from __future__ import annotations

import re


def largest_remainder(total: int, weights: list[int]) -> list[int]:
    """Split `total` integer units across items proportionally to `weights`.

    Uses the largest-remainder (Hamilton) method so `sum(result) == total`
    exactly. Degenerate weights (all zero / empty) split evenly.
    """
    n = len(weights)
    result = [0] * n
    if n == 0 or total <= 0:
        return result
    wsum = sum(weights)
    if wsum <= 0:
        base = [total // n] * n
        for i in range(total % n):
            base[i] += 1
        return base
    raw = [total * w / wsum for w in weights]
    base = [int(x) for x in raw]  # floor split
    rem = [x - b for x, b in zip(raw, base)]
    deficit = total - sum(base)  # 0 <= deficit < n
    for i in sorted(range(n), key=lambda i: (-rem[i], i))[:deficit]:
        base[i] += 1
    return base


def scene_frame_allocation(total_frame: int, percentages: list[int]) -> list[int]:
    """Per-scene frame counts from a narration's total_frame + scene percentages.

    Guarantees `sum(result) == total_frame` (largest remainder). Before TTS runs
    (total_frame == 0) falls back to `max(1, p)` so the config stays structurally
    valid. When total_frame >= scene count, enforces a minimum of 1 frame per
    scene (borrowing from the largest allocation, keeping the sum exact).
    """
    if total_frame <= 0:
        return [max(1, p) for p in percentages]
    frames = largest_remainder(total_frame, percentages)
    if total_frame >= len(frames):
        zero = [i for i in range(len(frames)) if frames[i] < 1]
        while zero:
            i = zero.pop()
            j = max(range(len(frames)), key=lambda k: frames[k])
            frames[j] -= 1
            frames[i] = 1
            if frames[j] < 1:
                zero.append(j)
    return frames


_SENTENCE_RE = re.compile(r"(?<=[。！？；．.?!;…])")


def split_sentences(content: str) -> list[str]:
    """Split narration content into sentences, keeping the punctuation attached."""
    parts = _SENTENCE_RE.split(content or "")
    return [p.strip() for p in parts if p and p.strip()]


_SECONDARY_RE = re.compile(r"[，、,;: ]")


def _cut_sentence(sentence: str, min_chars: int, max_chars: int) -> list[str]:
    """Split an over-long single sentence into <= max_chars pieces.

    Prefers a secondary boundary (，、,;: space) within the first max_chars;
    otherwise hard-cuts at max_chars.
    """
    pieces = []
    head = sentence
    while len(head) > max_chars:
        window = head[:max_chars]
        cuts = [m.start() for m in _SECONDARY_RE.finditer(window)]
        # Keep delimiter on the head piece: cut AFTER the delimiter
        cut = next((c + 1 for c in reversed(cuts) if c + 1 >= min_chars), None)
        if cut is None:
            cut = max_chars
        pieces.append(head[:cut].strip())
        head = head[cut:].strip()
    if head:
        pieces.append(head)
    return pieces


def split_narration_chunks(content: str, min_chars: int = 18, max_chars: int = 30) -> list[str]:
    """Split narration content into subtitle chunks (each ~min..max chars).

    Sentence-first: greedy-merge sentences into chunks up to max_chars. A single
    sentence longer than max_chars is sub-split at a secondary boundary or a
    hard char cut. Returns [] for blank input.
    """
    if not (content or "").strip():
        return []
    sentences = split_sentences(content)
    if not sentences:
        return [content.strip()]
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if len(s) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            for piece in _cut_sentence(s, min_chars, max_chars):
                if piece:
                    chunks.append(piece)
            continue
        if buf and len(buf) + len(s) > max_chars:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}{s}" if buf else s
    if buf:
        chunks.append(buf)
    return chunks
