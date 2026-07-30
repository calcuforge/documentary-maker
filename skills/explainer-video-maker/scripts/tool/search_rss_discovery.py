#!/usr/bin/env python3
"""
Search for RSS feed sources matching a topic.

Uses Playwright (Chromium) to search RSSHub and other RSS discovery services,
returns a list of candidate RSS feed URLs.

Usage:
    python search_rss.py --query "GPU pricing news" --output /abs/path/rss_sources.json
    python search_rss.py --query "AI technology" --max-results 10

Output JSON structure:
    [{"url": "...", "title": "...", "description": "..."}]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.net import is_china_network

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright is not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


# Well-known RSSHub routes that can be searched
RSSHUB_SEARCH_URL = "https://rsshub.app"
RSSHUB_DISCOVERY = "https://docs.rsshub.app"


def search_rsshub(page, query: str, timeout: int) -> list[dict]:
    """Search RSSHub documentation for relevant routes."""
    results = []
    # Try the RSSHub search
    try:
        search_url = f"https://docs.rsshub.app/search?q={query}"
        page.goto(search_url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        items = page.query_selector_all(".search-results a, .result a, article a")
        for item in items[:10]:
            title = item.inner_text().strip()
            href = item.get_attribute("href") or ""
            if title and href and "/routes/" in href:
                # Convert docs route to RSSHub feed URL
                route_path = href.split("/routes/")[-1].replace("/", "")
                results.append({
                    "url": f"{RSSHUB_SEARCH_URL}/{route_path}",
                    "title": title,
                    "description": f"RSSHub route: {route_path}",
                })
    except Exception as e:
        print(f"WARNING: RSSHub search failed: {e}", file=sys.stderr)
    return results


def search_feedly(page, query: str, timeout: int) -> list[dict]:
    """Search Feedly for RSS feeds matching the query."""
    results = []
    try:
        url = f"https://feedly.com/i/search/feeds?q={query}"
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        items = page.query_selector_all(".search-result, .feed-result, [data-testid='search-result']")
        for item in items[:10]:
            title_el = item.query_selector("h3, .title, .feed-title")
            link_el = item.query_selector("a")
            title = title_el.inner_text().strip() if title_el else ""
            href = link_el.get_attribute("href") if link_el else ""
            desc_el = item.query_selector("p, .description")
            desc = desc_el.inner_text().strip() if desc_el else ""
            if title:
                results.append({
                    "url": href,
                    "title": title,
                    "description": desc,
                })
    except Exception as e:
        print(f"WARNING: Feedly search failed: {e}", file=sys.stderr)
    return results


def suggest_common_feeds(query: str) -> list[dict]:
    """Suggest common RSS feeds based on topic keywords (offline fallback)."""
    suggestions = []
    q = query.lower()

    tech_feeds = [
        {"url": "https://rsshub.app/36kr/newsflashes", "title": "36Kr Newsflashes", "description": "Tech news (Chinese)"},
        {"url": "https://rsshub.app/sspai/matrix", "title": "SSPai Matrix", "description": "Tech articles (Chinese)"},
        {"url": "https://feeds.arstechnica.com/arstechnica/index", "title": "Ars Technica", "description": "Tech news"},
        {"url": "https://www.theverge.com/rss/index.xml", "title": "The Verge", "description": "Tech & culture"},
        {"url": "https://hnrss.org/frontpage", "title": "Hacker News", "description": "Tech community"},
    ]
    news_feeds = [
        {"url": "https://rsshub.app/thepaper/featured", "title": "The Paper", "description": "News (Chinese)"},
        {"url": "https://feeds.bbci.co.uk/news/rss.xml", "title": "BBC News", "description": "World news"},
        {"url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "title": "NYT", "description": "World news"},
    ]
    finance_feeds = [
        {"url": "https://rsshub.app/wallstreetcn/news/global", "title": "Wall Street CN", "description": "Finance (Chinese)"},
        {"url": "https://feeds.bloomberg.com/markets/news.rss", "title": "Bloomberg", "description": "Markets"},
    ]

    if any(k in q for k in ["tech", "ai", "programming", "software", "gpu", "hardware", "科技", "编程", "显卡"]):
        suggestions.extend(tech_feeds)
    if any(k in q for k in ["news", "daily", "report", "新闻", "日报", "资讯"]):
        suggestions.extend(news_feeds)
    if any(k in q for k in ["price", "market", "finance", "stock", "价格", "市场", "金融"]):
        suggestions.extend(finance_feeds)

    # Default: return tech + news if nothing specific
    if not suggestions:
        suggestions = tech_feeds + news_feeds

    return suggestions


def main() -> None:
    parser = argparse.ArgumentParser(description="Search for RSS feed sources")
    parser.add_argument("--query", required=True, help="Search query for RSS feeds")
    parser.add_argument("--output", default="", help="Output JSON file path (absolute, optional — prints to stdout if omitted)")
    parser.add_argument("--max-results", type=int, default=10, help="Max results to return")
    parser.add_argument("--timeout", type=int, default=30000, help="Page load timeout (ms)")
    parser.add_argument("--offline", action="store_true",
                        help="Skip browser search, only use built-in feed suggestions (no Playwright needed)")
    args = parser.parse_args()

    if args.output:
        from lib.net import require_abs
        require_abs(args.output)

    all_results: list[dict] = []

    if not args.offline:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            # Search RSSHub
            all_results.extend(search_rsshub(page, args.query, args.timeout))

            # Search Feedly (non-China)
            if not is_china_network():
                all_results.extend(search_feedly(page, args.query, args.timeout))

            browser.close()

    # Add offline suggestions as fallback (or primary in --offline mode)
    if len(all_results) < 3 or args.offline:
        all_results.extend(suggest_common_feeds(args.query))

    # Deduplicate by URL
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    all_results = unique[: args.max_results]

    output_json = json.dumps(all_results, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"OK: {len(all_results)} RSS sources saved to {output_path}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
