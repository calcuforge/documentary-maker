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
import sys

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


def _resolve_providers(prefs):
    """Combine theme providers with project-level overrides if present."""
    category = prefs.get("project", {}).get("category", "knowledge-sharing")
    theme = _load_theme(category)
    theme_providers = theme.get("research_providers", [])
    project_overrides = prefs.get("research", {}).get("providers", None)
    if project_overrides is not None:
        # Project explicitly overrides providers — use those.
        return project_overrides
    return theme_providers


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

    # Try to read topic_definition.md for a topic hint to substitute into queries.
    topic_hint = ""
    td_path = os.path.join(video_dir, "topic_definition.md")
    if os.path.isfile(td_path):
        with open(td_path, "r", encoding="utf-8") as f:
            topic_hint = f.read().strip()[:200]

    steps = []
    total_enabled = 0
    for entry in providers:
        if entry.get("enabled") is False:
            continue
        total_enabled += 1
        step = _provider_plan(args.video, entry, topic_hint)
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
            "topic_hint": topic_hint[:100],
            "providers_enabled": total_enabled,
            "plan": steps,
            "output_file": os.path.join(video_dir, "topic_research.md"),
        },
        message=(
            f"Research plan: {total_enabled} provider(s) enabled. "
            "Execute each step and write findings to topic_research.md."
        ),
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
