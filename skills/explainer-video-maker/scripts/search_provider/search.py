#!/usr/bin/env python3
"""
Browser-based search provider using Playwright (Chromium).

Visits multiple information sources (search engines + encyclopedias), extracts
useful text content, and outputs results as Markdown.

Usage:
    python search.py --query "法航447空难" --output /abs/path/result.md
    python search.py --query "GPU pricing 2025" --sources google,wikipedia --output /abs/path/result.md

Options:
    --query     Search query (required)
    --output    Output markdown file path (absolute path, required)
    --sources   Comma-separated source list (default: auto-detect by locale)
                Available: baidu, bing, sogou, google, baike, wikipedia
    --max-pages Max results to extract per search engine (default: 5)
    --timeout   Page load timeout in ms (default: 30000)
    --visit-top Number of top results to visit for full content (default: 5)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

# Add skill root to path for lib imports
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.htmltext import strip_html, truncate
from lib.net import is_china_network

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright is not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════
#  Search Engines
# ═══════════════════════════════════════════════════════════════════


def search_baidu(page, query: str, max_results: int, timeout: int) -> list[dict]:
    """Search Baidu — primary search engine for China network."""
    results = []
    url = f"https://www.baidu.com/s?wd={quote(query)}&rn={max_results * 2}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Baidu organic results: div.result or div[tpl]
        items = page.query_selector_all("div.result, div[tpl]")
        for item in items[:max_results * 2]:
            title_el = item.query_selector("h3 a")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            href = title_el.get_attribute("href") or ""

            # Snippet: multiple possible selectors
            snippet = ""
            for sel in [".c-abstract", ".content-right_8Zs40", ".c-span-last p",
                        "[class*='content']", ".c-row .c-span-last"]:
                snippet_el = item.query_selector(sel)
                if snippet_el:
                    snippet = snippet_el.inner_text().strip()
                    if len(snippet) > 20:
                        break

            if title and len(title) > 3:
                results.append({
                    "source": "baidu",
                    "title": title,
                    "url": href,
                    "content": snippet[:500],
                })
    except Exception as e:
        print(f"WARNING: Baidu search failed: {e}", file=sys.stderr)
    return results[:max_results]


def search_bing(page, query: str, max_results: int, timeout: int) -> list[dict]:
    """Search Bing — works in both China and international networks."""
    results = []
    # Use cn.bing.com for better Chinese results
    base = "https://cn.bing.com" if is_china_network() else "https://www.bing.com"
    url = f"{base}/search?q={quote(query)}&count={max_results * 2}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        items = page.query_selector_all("li.b_algo")
        for item in items[:max_results * 2]:
            title_el = item.query_selector("h2 a")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            href = title_el.get_attribute("href") or ""

            snippet = ""
            for sel in [".b_caption p", ".b_lineclamp2", ".b_lineclamp3",
                        ".b_lineclamp4", ".b_algoSlug"]:
                snippet_el = item.query_selector(sel)
                if snippet_el:
                    snippet = snippet_el.inner_text().strip()
                    if len(snippet) > 20:
                        break

            if title and len(title) > 3:
                results.append({
                    "source": "bing",
                    "title": title,
                    "url": href,
                    "content": snippet[:500],
                })
    except Exception as e:
        print(f"WARNING: Bing search failed: {e}", file=sys.stderr)
    return results[:max_results]


def search_sogou(page, query: str, max_results: int, timeout: int) -> list[dict]:
    """Search Sogou — supplementary Chinese search engine."""
    results = []
    url = f"https://www.sogou.com/web?query={quote(query)}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        items = page.query_selector_all("div.vrwrap, div.rb")
        for item in items[:max_results * 2]:
            title_el = item.query_selector("h3 a")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            href = title_el.get_attribute("href") or ""

            snippet = ""
            for sel in [".str_info", ".space-txt", "[class*='str-text']", "p.str_info"]:
                snippet_el = item.query_selector(sel)
                if snippet_el:
                    snippet = snippet_el.inner_text().strip()
                    if len(snippet) > 20:
                        break

            if title and len(title) > 3:
                results.append({
                    "source": "sogou",
                    "title": title,
                    "url": href,
                    "content": snippet[:500],
                })
    except Exception as e:
        print(f"WARNING: Sogou search failed: {e}", file=sys.stderr)
    return results[:max_results]


def search_google(page, query: str, max_results: int, timeout: int) -> list[dict]:
    """Search Google — for international networks."""
    results = []
    url = f"https://www.google.com/search?q={quote(query)}&num={max_results * 2}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        items = page.query_selector_all("div.g, div[data-hveid]")
        for item in items[:max_results * 2]:
            title_el = item.query_selector("h3")
            link_el = item.query_selector("a[href^='http']")
            if not title_el:
                continue
            title = title_el.inner_text().strip()
            href = link_el.get_attribute("href") if link_el else ""

            snippet = ""
            for sel in ["[data-sncf]", ".VwiC3b", "[style*='-webkit-line-clamp']",
                        ".IsZvec", ".lEBKkf"]:
                snippet_el = item.query_selector(sel)
                if snippet_el:
                    snippet = snippet_el.inner_text().strip()
                    if len(snippet) > 20:
                        break

            if title and href and len(title) > 3:
                results.append({
                    "source": "google",
                    "title": title,
                    "url": href,
                    "content": snippet[:500],
                })
    except Exception as e:
        print(f"WARNING: Google search failed: {e}", file=sys.stderr)
    return results[:max_results]


# ═══════════════════════════════════════════════════════════════════
#  Encyclopedias
# ═══════════════════════════════════════════════════════════════════


def search_baike(page, query: str, timeout: int) -> list[dict]:
    """Search Baidu Baike — try multiple strategies to find the article.

    Strategy 1: Use Baidu search restricted to baike.baidu.com
    Strategy 2: Use Baike's own search page
    Strategy 3: Direct URL access
    Then extract full article content from the found page.
    """
    results = []

    # Strategy 1: Baidu site-restricted search
    baike_url = _find_baike_via_baidu(page, query, timeout)

    # Strategy 2: Baike search page
    if not baike_url:
        baike_url = _find_baike_via_search(page, query, timeout)

    # Strategy 3: Direct URL
    if not baike_url:
        baike_url = f"https://baike.baidu.com/item/{quote(query)}"

    # Extract article content
    content = _extract_baike_content(page, baike_url, timeout)
    if content:
        results.append({
            "source": "baike",
            "title": f"百度百科: {query}",
            "url": baike_url,
            "content": content,
        })
    return results


def _find_baike_via_baidu(page, query: str, timeout: int) -> str | None:
    """Use Baidu search with site:baike.baidu.com to find the right Baike page."""
    try:
        url = f"https://www.baidu.com/s?wd={quote('site:baike.baidu.com ' + query)}"
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Find first result that links to baike.baidu.com
        links = page.query_selector_all("h3 a")
        for link in links[:5]:
            href = link.get_attribute("href") or ""
            title = link.inner_text().strip()
            # Baidu redirects through baidu.com/link?url=... — need to follow
            if href and ("baike" in title.lower() or "百科" in title):
                return href  # Baidu redirect URL, will be resolved on visit
        # Also check snippets for baike markers
        items = page.query_selector_all("div.result, div[tpl]")
        for item in items[:5]:
            source_el = item.query_selector("[class*='source'], .c-showurl, span.c-color-gray")
            if source_el and "baike" in (source_el.inner_text() or ""):
                title_el = item.query_selector("h3 a")
                if title_el:
                    return title_el.get_attribute("href") or ""
    except Exception as e:
        print(f"WARNING: Baidu site-search for Baike failed: {e}", file=sys.stderr)
    return None


def _find_baike_via_search(page, query: str, timeout: int) -> str | None:
    """Use Baike's own search page."""
    try:
        url = f"https://baike.baidu.com/search?word={quote(query)}"
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Find the first result link
        links = page.query_selector_all(".search-list a, .result-list a, dd a")
        for link in links[:3]:
            href = link.get_attribute("href") or ""
            if "/item/" in href:
                if href.startswith("/"):
                    return f"https://baike.baidu.com{href}"
                return href
    except Exception as e:
        print(f"WARNING: Baike search page failed: {e}", file=sys.stderr)
    return None


def _extract_baike_content(page, url: str, timeout: int) -> str:
    """Extract structured content from a Baidu Baike article page."""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        parts = []

        # Summary / description
        for sel in [".J-summary", "#J-summary", ".summary", ".lemma-summary",
                     ".main-content .para", "div.lemmaWgt-lemmaSummary-summary"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 30:
                    parts.append(text)
                    break

        # Main content paragraphs
        paragraphs = page.query_selector_all(
            ".main-content .para, .content .para, "
            "div[class*='mainContent'] .para, "
            ".J-lemma-content .para, "
            "#J-main-column .para"
        )
        for p in paragraphs[:15]:
            text = p.inner_text().strip()
            if len(text) > 20 and text not in parts:
                parts.append(text)

        # Section headers for structure
        headers = page.query_selector_all(
            ".main-content h2, .content h2, "
            "div[class*='mainContent'] h2, "
            ".J-lemma-content h2"
        )
        header_texts = [h.inner_text().strip() for h in headers[:10] if h.inner_text().strip()]

        content = "\n\n".join(parts)
        if header_texts:
            content = f"[Sections: {' | '.join(header_texts)}]\n\n{content}"

        return truncate(content, 6000) if content else ""
    except Exception as e:
        print(f"WARNING: Baike content extraction failed for {url}: {e}", file=sys.stderr)
    return ""


def search_wikipedia(page, query: str, timeout: int) -> list[dict]:
    """Search Wikipedia — for international networks. Tries EN then ZH."""
    results = []

    for lang, domain in [("en", "en.wikipedia.org"), ("zh", "zh.wikipedia.org")]:
        url = f"https://{domain}/wiki/{quote(query.replace(' ', '_'))}"
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            paragraphs = page.query_selector_all("#mw-content-text .mw-parser-output > p")
            content_parts = []
            for p in paragraphs[:8]:
                text = p.inner_text().strip()
                if text and not text.startswith("[") and len(text) > 30:
                    content_parts.append(text)
            content = "\n\n".join(content_parts)
            if content and len(content) > 100:
                results.append({
                    "source": f"wikipedia-{lang}",
                    "title": f"Wikipedia ({lang.upper()}): {query}",
                    "url": url,
                    "content": truncate(content, 5000),
                })
                break  # Found in one language, stop
        except Exception as e:
            print(f"WARNING: Wikipedia ({lang}) failed: {e}", file=sys.stderr)
            continue

    return results


# ═══════════════════════════════════════════════════════════════════
#  Page Content Extraction
# ═══════════════════════════════════════════════════════════════════


def visit_page(page, url: str, timeout: int) -> str:
    """Visit a URL and extract main text content."""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Try common content selectors (ordered by specificity)
        selectors = [
            "article",
            "main",
            ".article-content",
            ".post-content",
            ".entry-content",
            ".content-detail",
            "#article_content",
            ".article_content",
            "[class*='article-body']",
            "[class*='content-body']",
            ".content",
            "#content",
        ]
        for selector in selectors:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return truncate(text, 5000)

        # Fallback: body text
        body = page.query_selector("body")
        if body:
            text = body.inner_text().strip()
            if len(text) > 200:
                return truncate(text, 4000)
    except Exception as e:
        print(f"WARNING: Failed to visit {url}: {e}", file=sys.stderr)
    return ""


# ═══════════════════════════════════════════════════════════════════
#  Output Formatting
# ═══════════════════════════════════════════════════════════════════


def format_results_markdown(query: str, results: list[dict], page_contents: dict[str, str]) -> str:
    """Format search results as a Markdown document."""
    lines = [
        f"# Search Results: {query}",
        "",
        f"*Generated by search_provider/search.py*",
        f"*Sources: {', '.join(sorted(set(r['source'] for r in results)))}*",
        f"*Results: {len(results)}*",
        "",
    ]

    for i, r in enumerate(results, 1):
        lines.append(f"## Result {i}: {r['title']}")
        lines.append(f"- Source: {r['source']}")
        lines.append(f"- URL: {r['url']}")
        lines.append("")
        if r["content"]:
            lines.append(r["content"])
        # Append full page content if available
        url = r.get("url", "")
        if url in page_contents and page_contents[url]:
            lines.append("")
            lines.append("### Full Page Content")
            lines.append("")
            lines.append(page_contents[url])
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="Browser-based web search provider")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--output", required=True, help="Output markdown file path (absolute)")
    parser.add_argument("--sources", default="",
                        help="Comma-separated sources: baidu,bing,sogou,google,baike,wikipedia")
    parser.add_argument("--max-pages", type=int, default=5, help="Max results per search engine")
    parser.add_argument("--timeout", type=int, default=30000, help="Page load timeout (ms)")
    parser.add_argument("--visit-top", type=int, default=5,
                        help="Number of top results to visit for full content")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.output)

    # Determine sources based on network locale
    if args.sources:
        sources = [s.strip().lower() for s in args.sources.split(",")]
    else:
        if is_china_network():
            sources = ["baidu", "baike", "bing"]
        else:
            sources = ["google", "wikipedia", "bing"]

    all_results: list[dict] = []
    page_contents: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="zh-CN" if is_china_network() else "en-US",
        )
        page = context.new_page()

        for source in sources:
            if source == "baidu":
                all_results.extend(search_baidu(page, args.query, args.max_pages, args.timeout))
            elif source == "bing":
                all_results.extend(search_bing(page, args.query, args.max_pages, args.timeout))
            elif source == "sogou":
                all_results.extend(search_sogou(page, args.query, args.max_pages, args.timeout))
            elif source == "google":
                all_results.extend(search_google(page, args.query, args.max_pages, args.timeout))
            elif source == "baike":
                all_results.extend(search_baike(page, args.query, args.timeout))
            elif source == "wikipedia":
                all_results.extend(search_wikipedia(page, args.query, args.timeout))
            else:
                print(f"WARNING: Unknown source '{source}', skipping.", file=sys.stderr)

        # Deduplicate by title similarity (keep first occurrence)
        seen_titles: set[str] = set()
        unique_results: list[dict] = []
        for r in all_results:
            key = r["title"].strip().lower()[:40]
            if key not in seen_titles:
                seen_titles.add(key)
                unique_results.append(r)
        all_results = unique_results

        # Visit top results for full page content
        visited = 0
        for r in all_results:
            if visited >= args.visit_top:
                break
            url = r.get("url", "")
            if not url or not url.startswith("http"):
                continue
            if url in page_contents:
                continue
            # Skip baike URLs (already extracted in search_baike)
            if "baike.baidu.com" in url and r["source"] == "baike":
                continue
            content = visit_page(page, url, args.timeout)
            if content:
                page_contents[url] = content
                visited += 1

        browser.close()

    if not all_results:
        print(f"ERROR: No results found for query: {args.query}", file=sys.stderr)
        sys.exit(1)

    # Write output
    md = format_results_markdown(args.query, all_results, page_contents)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")

    # Summary
    source_counts = {}
    for r in all_results:
        source_counts[r["source"]] = source_counts.get(r["source"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in source_counts.items())
    print(f"OK: {len(all_results)} results ({summary}), {visited} pages visited → {output_path}")


if __name__ == "__main__":
    main()
