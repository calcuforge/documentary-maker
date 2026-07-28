#!/usr/bin/env python3
"""Research plan generator — reads theme `research_providers` and produces a
step-by-step research plan for the agent to execute in Step 2.

Provider types:

    agent_search   — Free-form web search via the agent's native search tool.
                     `queries` are suggested search strings. The agent should
                     search all of them and synthesize findings.

    web_fetch      — Direct URL fetching (Wikipedia, official sites, databases).
                     `urls` are absolute URLs. The agent fetches each one and
                     extracts structured facts.

    rss            — RSS/Atom feed polling. `feeds` are feed URLs. The agent
                     fetches them (via curl or requests), parses entries, and
                     extracts headlines + summaries + links.

    custom_script  — Agent-developed data retrieval / crawler script. The
                     agent writes a Python script (requests, feedparser, bs4)
                     to fetch structured data, then runs it. `script_hint`
                     describes what the script should do.

Output:
    A structured research plan printed to stdout (JSON envelope). The agent
    reads the plan and executes it step by step. After all providers complete,
    results are merged into topic_research.md.

Commands:
    research plan --project <name> --video <name>
        Emit the research plan for one video, resolving theme providers
        against project prefs.
"""
import argparse
import json
import os
import re
import socket
import sys

import requests
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import workspace  # noqa: E402


PROVIDER_SCHEMA = {
    "agent_search": {"queries": list},
    "web_fetch": {"urls": list},
    "rss": {"feeds": list},
    "custom_script": {},  # free-form; agent interprets script_hint + description
}


def _load_theme(category):
    from themes import show_theme
    return show_theme(category) or {}


def _load_project_prefs(project_name):
    ppath = workspace.prefs_path(project_name)
    if not os.path.isfile(ppath):
        cli_envelope.emit_usage_error(f"Project '{project_name}' not found.", "text")
    with open(ppath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _extract_topic(video_dir, max_len=50):
    """Extract a short topic name for {topic} placeholder substitution.

    1. Parse ``topic_definition.md`` for a ``**事件**`` / ``**Event**`` line.
    2. Fall back to the first narration sentence from ``narration_script.yaml``.
    3. Return *max_len* chars at most.
    """
    # 1. topic_definition.md — extract the event/subject line
    td_path = os.path.join(video_dir, "topic_definition.md")
    if os.path.isfile(td_path):
        with open(td_path, "r", encoding="utf-8") as f:
            text = f.read()
        # Match lines like: **事件** — xxx  or  **Event/subject** — xxx
        m = re.search(
            r"\*\*(?:事件|Event|事件/subject|Event/subject|Topic|主题)\*\*\s*[：:—\-–]\s*(.+)",
            text,
        )
        if m:
            return m.group(1).strip()[:max_len]
        # Fall back to the first heading
        m = re.search(r"^#\s+(.+)", text, re.MULTILINE)
        if m:
            return m.group(1).strip()[:max_len]

    # 2. narration_script.yaml — first scene's first sentence
    ns_path = os.path.join(video_dir, "narration_script.yaml")
    if os.path.isfile(ns_path):
        try:
            with open(ns_path, "r", encoding="utf-8") as f:
                script = yaml.safe_load(f) or {}
            scenes = script.get("scenes", [])
            if scenes:
                narration = (scenes[0].get("narration") or "").strip()
                if narration:
                    # Take up to the first sentence-ending punctuation
                    m = re.match(r"([^。.!！?\n]{1,%d})" % max_len, narration)
                    if m:
                        return m.group(1).strip()
        except Exception:
            pass

    return ""


def _resolve_providers(prefs):
    """Combine theme providers with project-level overrides if present."""
    category = prefs.get("project", {}).get("category", "knowledge-sharing")
    theme = _load_theme(category)
    theme_providers = theme.get("research_providers", [])
    project_overrides = prefs.get("research", {}).get("providers", None)
    if project_overrides is not None:
        return project_overrides
    return theme_providers


# ── region detection & source localization ────────────────────────────────────

# Domain→replacement mapping for CN environment.  Queries containing the key are
# rewritten with the value; URLs matching the key are replaced / flagged.
_CN_QUERY_MAP = {
    "Wikipedia": "百度百科",
    "wikipedia": "百度百科",
    "NTSB": "中国民航局",
    "FAA": "中国民航局",
    "Google Scholar": "百度学术",
    "Google News": "百度资讯",
    "BBC": "央视网",
    "CNN": "新华网",
    "Reuters": "新华社",
    "National Geographic": "中国国家地理",
    "site:en.wikipedia.org": "",
    "site:zh.wikipedia.org": "",
}

_CN_URL_BLOCKED_DOMAINS = {
    # Domain → suggested alternative (empty = no direct alternative)
    "en.wikipedia.org": "baike.baidu.com",
    "zh.wikipedia.org": "baike.baidu.com",
    "google.com": "",
    "bbc.com": "",
    "bbc.co.uk": "",
    "cnn.com": "",
    "reuters.com": "",
    "nytimes.com": "",
    "wsj.com": "",
    "theguardian.com": "",
    "medium.com": "",
    "reddit.com": "",
    "twitter.com": "",
    "x.com": "",
    "facebook.com": "",
    "youtube.com": "bilibili.com",
    "instagram.com": "",
}


def _detect_region(timeout=3):
    """Return ``"cn"`` if the environment appears to be inside China, else ``"global"``.

    Resolution order:
    1. ``RESEARCH_REGION`` env var (``cn`` / ``global``) — explicit override.
    2. Connectivity test: try to reach google.com; if unreachable → ``cn``.
    3. Default: ``global``.
    """
    env_val = os.environ.get("RESEARCH_REGION", "").strip().lower()
    if env_val in ("cn", "china", "domestic"):
        return "cn"
    if env_val in ("global", "international", "us"):
        return "global"

    # Auto-detect: try a quick TCP connect to google.com:443
    try:
        s = socket.create_connection(("google.com", 443), timeout=timeout)
        s.close()
        return "global"
    except (socket.error, OSError):
        return "cn"


def _localize_query(query):
    """Rewrite a search query for the CN environment."""
    for en, cn in _CN_QUERY_MAP.items():
        if en in query:
            if cn:
                query = query.replace(en, cn)
            else:
                # Empty replacement = remove the keyword
                query = query.replace(en, "").replace("  ", " ").strip()
    return query


def _localize_url(url):
    """Return (url, blocked) — the (possibly rewritten) URL and whether it was blocked."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    # Strip www. prefix for matching
    domain_plain = domain[4:] if domain.startswith("www.") else domain
    if domain_plain in _CN_URL_BLOCKED_DOMAINS:
        alt = _CN_URL_BLOCKED_DOMAINS[domain_plain]
        if alt:
            return (url.replace(domain, alt), True)
        return (url, True)
    return (url, False)


def _localize_provider(provider_entry, region):
    """Return a copy of *provider_entry* with queries/URLs localized for *region*."""
    if region != "cn":
        return provider_entry

    import copy
    entry = copy.deepcopy(provider_entry)
    ptype = entry.get("provider", "")

    if ptype == "agent_search":
        queries = entry.get("queries", [])
        entry["queries"] = [_localize_query(q) for q in queries]
        entry["description"] = (entry.get("description", "") +
                                " (CN: queries localized to domestic sources)")

    elif ptype == "web_fetch":
        urls = entry.get("urls", [])
        localized = []
        blocked = []
        for u in urls:
            loc, is_blocked = _localize_url(u)
            if is_blocked:
                blocked.append({"original": u, "localized": loc,
                                "note": "Likely blocked in CN; agent should find a domestic alternative."})
            localized.append(loc)
        entry["urls"] = localized
        if blocked:
            entry["blocked_urls"] = blocked
        entry["description"] = (entry.get("description", "") +
                                " (CN: blocked URLs flagged; use domestic alternatives)")

    return entry


def _provider_plan(video_name, provider_entry, topic_hint=""):
    """Render one provider into an actionable plan step."""
    ptype = provider_entry.get("provider", "")
    desc = provider_entry.get("description", ptype)
    step = {
        "provider": ptype,
        "description": desc,
    }

    if ptype == "agent_search":
        queries = provider_entry.get("queries", [])
        # Substitute {topic} placeholder if present.
        queries = [q.replace("{topic}", topic_hint) for q in queries]
        step["queries"] = queries
        step["action"] = (
            "Use your agent's web search tool to search each query above. "
            "For each query, read the top 3-5 results and extract factual "
            "information: dates, names, statistics, events, direct quotes. "
            "Cross-reference across results. Flag conflicting information."
        )

    elif ptype == "web_fetch":
        urls = provider_entry.get("urls", [])
        step["urls"] = urls
        step["action"] = (
            "Use your agent's web fetch capability to retrieve each URL above. "
            "Extract structured facts from each page. For Wikipedia, capture "
            "the infobox and lead section. For official reports, capture "
            "key findings, dates, and statistics. Skip any URLs that return "
            "404/403 or are behind paywalls."
        )

    elif ptype == "rss":
        feeds = provider_entry.get("feeds", [])
        step["feeds"] = feeds
        step["action"] = (
            "Fetch each RSS feed URL via curl or your agent's fetch tool. "
            "Parse the XML to extract <item> entries: <title>, <link>, "
            f"<description>, <pubDate>. Collect the {provider_entry.get('max_entries', 20)} "
            "most recent entries per feed. Cluster related stories and "
            "identify the top 3-5 trends or breaking developments."
        )

    elif ptype == "custom_script":
        hint = provider_entry.get("script_hint", "")
        step["script_hint"] = hint
        step["script_path"] = f"projects/{{project}}/videos/{video_name}/scripts/"
        step["action"] = (
            "Write a Python script that retrieves structured data for this "
            "topic. Use only stdlib + requests + feedparser + beautifulsoup4. "
            f"Script hint: {hint}. "
            "Save the script to the video's scripts/ directory. Run it and "
            "capture stdout. If the script requires an API key, check project "
            "prefs under `research.custom_script_env`. Delete the script "
            "after collecting its output unless the user asks to keep it."
        )

    else:
        step["action"] = f"Unknown provider type '{ptype}'. Skip."
        step["skip"] = True

    return step


def build_parser():
    parser = argparse.ArgumentParser(description="Research plan generator.")
    cli_envelope.add_format_arg(parser)
    sub = parser.add_subparsers(dest="action", required=True)

    p_plan = sub.add_parser("plan", help="Generate a research plan for one video.")
    p_plan.add_argument("--project", required=True)
    p_plan.add_argument("--video", required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action != "plan":
        cli_envelope.emit_usage_error(f"Unknown action: {args.action}", fmt=args.format)

    prefs = _load_project_prefs(args.project)
    video_dir = workspace.video_dir(args.project, args.video)
    if not os.path.isdir(video_dir):
        cli_envelope.emit_usage_error(f"Video dir not found: {video_dir}", fmt=args.format)

    providers = _resolve_providers(prefs)
    if not providers:
        cli_envelope.emit_warning(
            data={"plan": [], "video_dir": video_dir},
            message=(
                "No research_providers configured for this theme and no "
                "project-level override. Falling back to agent_search only."
            ),
            fmt=args.format,
        )
        return

    region = _detect_region()
    topic_hint = _extract_topic(video_dir)

    steps = []
    total_enabled = 0
    for entry in providers:
        if entry.get("enabled") is False:
            continue
        total_enabled += 1
        localized = _localize_provider(entry, region)
        step = _provider_plan(args.video, localized, topic_hint)
        steps.append(step)

    if total_enabled == 0:
        cli_envelope.emit_warning(
            data={"plan": steps, "video_dir": video_dir},
            message="All configured providers have enabled: false. Nothing to do.",
            fmt=args.format,
        )
        return

    cli_envelope.emit_ok(
        data={
            "video_dir": video_dir,
            "region": region,
            "topic_hint": topic_hint[:100],
            "providers_enabled": total_enabled,
            "plan": steps,
            "output_file": os.path.join(video_dir, "topic_research.md"),
        },
        message=(
            f"Research plan [{region}]: {total_enabled} provider(s) enabled. "
            "Execute each step and write findings to topic_research.md."
        ),
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
