#!/usr/bin/env python3
"""
RSS search provider — fetches RSS feed, selects article links, visits them
via Playwright (Chromium), and extracts useful content.

Usage:
    python search_rss.py --feed-url "https://rsshub.app/36kr/newsflashes" --output /abs/path/result.md
    python search_rss.py --feed-url "https://feeds.arstechnica.com/arstechnica/index" --max-articles 5 --output /abs/path/result.md

Options:
    --feed-url      RSS/Atom feed URL (required)
    --output        Output markdown file path (absolute, required)
    --max-articles  Max articles to fetch and visit (default: 5)
    --keywords      Comma-separated keywords to filter articles (optional)
    --timeout       Page load timeout in ms (default: 30000)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.htmltext import strip_html, truncate

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright is not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


def fetch_feed(feed_url: str, timeout: int = 30) -> str:
    """Fetch RSS feed XML using curl."""
    try:
        result = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", str(timeout), feed_url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode != 0:
            print(f"ERROR: curl failed (exit {result.returncode}): {result.stderr}", file=sys.stderr)
            sys.exit(1)
        return result.stdout
    except FileNotFoundError:
        print("ERROR: curl not found on PATH", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"ERROR: curl timed out fetching {feed_url}", file=sys.stderr)
        sys.exit(1)


def parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS/Atom feed XML into a list of article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"ERROR: Failed to parse feed XML: {e}", file=sys.stderr)
        sys.exit(1)

    # RSS 2.0
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        desc = item.findtext("description", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        if title and link:
            articles.append({
                "title": title,
                "link": link,
                "description": strip_html(desc)[:500],
                "date": pub_date,
            })

    # Atom
    if not articles:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext("atom:summary", "", ns).strip()
            updated = entry.findtext("atom:updated", "", ns).strip()
            if title and link:
                articles.append({
                    "title": title,
                    "link": link,
                    "description": strip_html(summary)[:500],
                    "date": updated,
                })

    return articles


def filter_by_keywords(articles: list[dict], keywords: list[str]) -> list[dict]:
    """Filter articles that contain any of the keywords (case-insensitive)."""
    if not keywords:
        return articles
    kw_lower = [k.lower() for k in keywords]
    filtered = []
    for a in articles:
        text = f"{a['title']} {a['description']}".lower()
        if any(k in text for k in kw_lower):
            filtered.append(a)
    return filtered


def visit_article(page, url: str, timeout: int) -> str:
    """Visit an article URL and extract main text content."""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        for selector in ["article", "main", ".post-content", ".article-body",
                         ".entry-content", ".content", "#article_content"]:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text()
                if len(text) > 100:
                    return truncate(text, 4000)
        body = page.query_selector("body")
        if body:
            return truncate(body.inner_text(), 3000)
    except Exception as e:
        print(f"WARNING: Failed to visit {url}: {e}", file=sys.stderr)
    return ""


def format_markdown(feed_url: str, articles: list[dict], contents: dict[str, str]) -> str:
    """Format articles as Markdown."""
    lines = [
        f"# RSS Search Results",
        "",
        f"*Feed: {feed_url}*",
        f"*Articles: {len(articles)}*",
        "",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"## {i}. {a['title']}")
        lines.append(f"- URL: {a['link']}")
        if a["date"]:
            lines.append(f"- Date: {a['date']}")
        lines.append("")
        if a["description"]:
            lines.append(f"> {a['description']}")
            lines.append("")
        content = contents.get(a["link"], "")
        if content:
            lines.append("### Full Content")
            lines.append("")
            lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="RSS search provider")
    parser.add_argument("--feed-url", required=True, help="RSS/Atom feed URL")
    parser.add_argument("--output", required=True, help="Output markdown file path (absolute)")
    parser.add_argument("--max-articles", type=int, default=5, help="Max articles to visit")
    parser.add_argument("--keywords", default="", help="Comma-separated filter keywords")
    parser.add_argument("--timeout", type=int, default=30000, help="Page load timeout (ms)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.output)

    xml_text = fetch_feed(args.feed_url)
    articles = parse_feed(xml_text)

    if not articles:
        print(f"ERROR: No articles found in feed: {args.feed_url}", file=sys.stderr)
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
    if keywords:
        articles = filter_by_keywords(articles, keywords)

    articles = articles[: args.max_articles]

    contents: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        for a in articles:
            link = a["link"]
            if link.startswith("http"):
                content = visit_article(page, link, args.timeout)
                if content:
                    contents[link] = content
        browser.close()

    md = format_markdown(args.feed_url, articles, contents)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")

    print(f"OK: {len(articles)} articles saved to {output_path}")


if __name__ == "__main__":
    main()
