#!/usr/bin/env python3
"""Shared loader for narration_script.yaml (chapters → scenes → shots).

The narration script is the single source of structural truth:

    chapters:
      - name: opening
        label: 开篇
        scenes:
          - name: hero
            label: 引子
            narration: |
              ...
            shots:
              - name: hero_01
                component: FullBleedLayout
                asset_id: hero_bg
                duration_hint_seconds: 6
                props: {...}
                data: [...]
                text: [...]
                overlays: [{asset_id: smoke_overlay, style: {...}}]

A scene is the unit of narration, TTS, subtitles, and rendering. A shot is
the unit of visual composition (source material + auxiliary layers). Chapters
are organizational groupings only — they are never rendered as a unit.

The legacy flat schema (a top-level list of sections) is rejected with a
clear error: projects must be restructured to the nested schema.
"""
import os

import yaml


class SchemaError(ValueError):
    """Raised when narration_script.yaml is missing or malformed."""


def load_script(path):
    """Load and normalize narration_script.yaml.

    Returns:
        {
          "chapters": [ {name, label, scenes: [...]} ],
          "scenes":   [ {name, label, chapter, narration, shots} ]  # flattened
        }

    Raises SchemaError on structural problems.
    """
    if not os.path.isfile(path):
        raise SchemaError(f"narration_script.yaml not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if isinstance(data, list):
        raise SchemaError(
            "narration_script.yaml uses the legacy flat section-list schema. "
            "Restructure it to the nested chapters → scenes → shots schema "
            "(see references/workflow-script.md)."
        )
    if not isinstance(data, dict):
        raise SchemaError("narration_script.yaml must be a mapping with a top-level 'chapters:' key.")

    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise SchemaError("narration_script.yaml must contain a non-empty 'chapters:' list.")

    scene_names = set()
    scenes = []
    for ch in chapters:
        if not isinstance(ch, dict) or not ch.get("name"):
            raise SchemaError("Every chapter needs a 'name' field.")
        ch_scenes = ch.get("scenes")
        if not isinstance(ch_scenes, list) or not ch_scenes:
            raise SchemaError(f"Chapter '{ch['name']}' must contain a non-empty 'scenes:' list.")
        for sc in ch_scenes:
            if not isinstance(sc, dict) or not sc.get("name"):
                raise SchemaError(f"Every scene in chapter '{ch['name']}' needs a 'name' field.")
            if sc["name"] in scene_names:
                raise SchemaError(f"Duplicate scene name: '{sc['name']}' (scene names must be unique across the video).")
            scene_names.add(sc["name"])
            shots = sc.get("shots") or []
            shot_names = set()
            for shot in shots:
                if not isinstance(shot, dict) or not shot.get("name"):
                    raise SchemaError(f"Every shot in scene '{sc['name']}' needs a 'name' field.")
                if shot["name"] in shot_names:
                    raise SchemaError(f"Duplicate shot name '{shot['name']}' in scene '{sc['name']}'.")
                shot_names.add(shot["name"])
            scenes.append({
                "name": sc["name"],
                "label": sc.get("label") or sc["name"],
                "chapter": ch["name"],
                "narration": sc.get("narration") or "",
                "shots": shots,
            })

    return {"chapters": chapters, "scenes": scenes}


def find_scene(script, name):
    """Return the flattened scene dict with the given name, or None."""
    for sc in script["scenes"]:
        if sc["name"] == name:
            return sc
    return None


def effective_shots(scene):
    """Return the scene's shots; a scene with no explicit shots gets one
    implicit shot named after the scene (single-shot scene)."""
    shots = scene.get("shots") or []
    if shots:
        return shots
    return [{"name": scene["name"], "component": "FullBleedLayout"}]


def referenced_asset_ids(script):
    """All asset ids referenced by any shot (main asset + overlays)."""
    ids = set()
    for sc in script["scenes"]:
        for shot in effective_shots(sc):
            if shot.get("asset_id"):
                ids.add(shot["asset_id"])
            for ov in shot.get("overlays") or []:
                if isinstance(ov, dict) and ov.get("asset_id"):
                    ids.add(ov["asset_id"])
    return ids
