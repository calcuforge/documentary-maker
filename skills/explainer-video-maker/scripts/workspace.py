#!/usr/bin/env python3
"""Workspace resolution — where the `projects/` directory lives.

Project data (prefs, narration scripts, scene audio, renders) belongs in the
user's WORKSPACE — the directory the agent works from — never inside the
skill installation. All skill commands therefore resolve projects against
the current working directory.

Resolution order for the projects root:
    1. EXPLAINER_PROJECTS_DIR env var — an explicit projects directory.
    2. EXPLAINER_WORKSPACE env var — a workspace root; projects go in
       <root>/projects.
    3. <CWD>/projects — the normal case: the agent runs every skill command
       from the workspace root (a SKILL.md hard rule), and the Claude Code
       shell keeps a stable CWD across commands within a session.
"""
import os


def projects_dir():
    """Absolute path to the workspace's projects/ directory (may not exist yet)."""
    explicit = os.environ.get("EXPLAINER_PROJECTS_DIR")
    if explicit:
        return os.path.normpath(os.path.abspath(explicit))
    ws = os.environ.get("EXPLAINER_WORKSPACE")
    if ws:
        return os.path.normpath(os.path.join(os.path.abspath(ws), "projects"))
    return os.path.normpath(os.path.join(os.getcwd(), "projects"))


def project_dir(name):
    return os.path.join(projects_dir(), name)


def prefs_path(project):
    return os.path.join(project_dir(project), "project_prefs.yaml")


def video_dir(project, video):
    return os.path.join(project_dir(project), "videos", video)
