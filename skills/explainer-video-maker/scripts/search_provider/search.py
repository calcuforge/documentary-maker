#!/usr/bin/env python3
"""
Browser-based search provider using Playwright (Chromium).

Visits multiple information sources (search engine + encyclopedia), extracts
useful text content, and outputs results as Markdown.

Usage:
    python search.py --query "Air France 447" --output /abs/path/result.md
    python search.py --query "GPU pricing 2025" --sources bing,baike --output /abs/path/result.md

Options:
    --query     Search query (required)
    --output    Output markdown file path (absolute path, required)
    --sources   Comma-separated source list (default: auto-detect by locale)
                Available: bing, google, baike, wikipedia
    --max-pages Max pages to visit per source (default: 3)
    --timeout   Page load timeout in ms (default: 30000)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def search_bing(page, query: str, max_pages: int, timeout: int) -> list[dict]:
    """Search Bing and extract result snippets + visit top results."""
    results = []
    url = f"https://www.bing.com/search?q={query}&count={max_pages * 5}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        # Extract search result snippets
        items = page.query_selector_all("li.b_algo")
        for item in items[: max_pages * 3]:
            title_el = item.query_selector("h2 a")
            snippet_el = item.query_selector(".b_caption p")
            title = title_el.inner_text() if title_el else ""
            href = title_el.get_attribute("href") if title_el else ""
            snippet = snippet_el.inner_text() if snippet_el else ""
            if title:
                results.append({"source": "bing", "title": title, "url": href, "content": snippet})
    except Exception as e:
        print(f"WARNING: Bing search failed: {e}", file=sys.stderr)
    return results


def search_google(page, query: str, max_pages: int, timeout: int) -> list[dict]:
    """Search Google and extract result snippets."""
    results = []
    url = f"https://www.google.com/search?q={query}&num={max_pages * 5}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        items = page.query_selector_all("div.g")
        for item in items[: max_pages * 3]:
            title_el = item.query_selector("h3")
            link_el = item.query_selector("a")
            snippet_el = item.query_selector("[data-sncf]")
            title = title_el.inner_text() if title_el else ""
            href = link_el.get_attribute("href") if link_el else ""
            snippet = snippet_el.inner_text() if snippet_el else ""
            if title:
                results.append({"source": "google", "title": title, "url": href, "content": snippet})
    except Exception as e:
        print(f"WARNING: Google search failed: {e}", file=sys.stderr)
    return results


def search_baike(page, query: str, timeout: int) -> list[dict]:
    """Search Baidu Baike and extract article summary."""
    results = []
    url = f"https://baike.baidu.com/item/{query}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        summary_el = page.query_selector(".main-content .para")
        if not summary_el:
            summary_el = page.query_selector("#J-summary")
        content = summary_el.inner_text() if summary_el else ""
        if content:
            results.append({
                "source": "baike",
                "title": f"Baidu Baike: {query}",
                "url": url,
                "content": truncate(content, 3000),
            })
    except Exception as e:
        print(f"WARNING: Baike search failed: {e}", file=sys.stderr)
    return results


def search_wikipedia(page, query: str, timeout: int) -> list[dict]:
    """Search Wikipedia and extract article summary."""
    results = []
    url = f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}"
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        # Get first few paragraphs
        paragraphs = page.query_selector_all("#mw-content-text .mw-parser-output > p")
        content_parts = []
        for p in paragraphs[:5]:
            text = p.inner_text().strip()
            if text and not text.startswith("[") and len(text) > 30:
                content_parts.append(text)
        content = "\n\n".join(content_parts)
        if content:
            results.append({
                "source": "wikipedia",
                "title": f"Wikipedia: {query}",
                "url": url,
                "content": truncate(content, 3000),
            })
    except Exception as e:
        print(f"WARNING: Wikipedia search failed: {e}", file=sys.stderr)
    return results


def visit_page(page, url: str, timeout: int) -> str:
    """Visit a URL and extract main text content."""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        # Try common content selectors
        for selector in ["article", "main", ".content", ".article-content", "#content"]:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text()
                if len(text) > 200:
                    return truncate(text, 4000)
        # Fallback: body text
        body = page.query_selector("body")
        if body:
            return truncate(body.inner_text(), 4000)
    except Exception as e:
        print(f"WARNING: Failed to visit {url}: {e}", file=sys.stderr)
    return ""


def format_results_markdown(query: str, results: list[dict], page_contents: dict[str, str]) -> str:
    """Format search results as a Markdown document."""
    lines = [
        f"# Search Results: {query}",
        "",
        f"*Generated by search_provider/search.py*",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Browser-based web search provider")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--output", required=True, help="Output markdown file path (absolute)")
    parser.add_argument("--sources", default="", help="Comma-separated sources: bing,google,baike,wikipedia")
    parser.add_argument("--max-pages", type=int, default=3, help="Max results per source")
    parser.add_argument("--timeout", type=int, default=30000, help="Page load timeout (ms)")
    parser.add_argument("--visit-top", type=int, default=3, help="Number of top results to visit for full content")
    args = parser.parse_args()

    # Determine sources
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",")]
    else:
        if is_china_network():
            sources = ["bing", "baike"]
        else:
            sources = ["google", "wikipedia"]

    all_results: list[dict] = []
    page_contents: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for source in sources:
            if source == "bing":
                all_results.extend(search_bing(page, args.query, args.max_pages, args.timeout))
            elif source == "google":
                all_results.extend(search_google(page, args.query, args.max_pages, args.timeout))
            elif source == "baike":
                all_results.extend(search_baike(page, args.query, args.timeout))
            elif source == "wikipedia":
                all_results.extend(search_wikipedia(page, args.query, args.timeout))
            else:
                print(f"WARNING: Unknown source '{source}', skipping.", file=sys.stderr)

        # Visit top results for full content
        visited = 0
        for r in all_results:
            if visited >= args.visit_top:
                break
            url = r.get("url", "")
            if url and url.startswith("http") and url not in page_contents:
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

    print(f"OK: {len(all_results)} results saved to {output_path}")


if __name__ == "__main__":
    main()
