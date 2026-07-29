"""
HTML-to-text extraction utility for search results.
"""

from __future__ import annotations

import re


def strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, max_chars: int = 5000) -> str:
    """Truncate text to max_chars, preserving sentence boundaries."""
    if len(text) <= max_chars:
        return text
    # Try to cut at a sentence boundary
    cut = text[:max_chars]
    last_period = max(cut.rfind("。"), cut.rfind(". "), cut.rfind("\n"))
    if last_period > max_chars * 0.5:
        return cut[: last_period + 1]
    return cut + "..."
