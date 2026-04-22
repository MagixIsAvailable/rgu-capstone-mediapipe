"""
Module: gesture_mapping.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Configuration and mapping layer for the VisionInput pipeline. Loads gesture-to-action mappings from JSON and resolves controller actions for left and right hands. Supports single-gesture mappings and multi-gesture combo rules with optional priority ordering, then returns neutral fallbacks when no valid mapping exists. This module centralises gesture/action translation only — no camera capture, model inference, or controller output logic is contained here.

Dependencies:
json
pathlib

Usage:
Imported by main.py and output modules to convert detected gesture labels into controller action labels.
Not run directly.
"""

import json
from pathlib import Path

# In-memory cache so JSON is read once per process.
_GESTURE_MAP = None


def load_gesture_map(path: str | None = None) -> dict:
    """Load gesture mapping from JSON file."""
    global _GESTURE_MAP
    # Lazy-load mapping on first use, then reuse cached copy.
    if _GESTURE_MAP is None:
        # Default to repo-level config/gesture_map.json unless an override path is given.
        map_path = Path(path) if path else (Path(__file__).resolve().parent.parent / "config" / "gesture_map.json")
        if not map_path.exists():
            raise FileNotFoundError(f"Gesture map not found: {map_path}")
        # Parse JSON mapping into dictionary.
        with map_path.open("r", encoding="utf-8") as f:
            _GESTURE_MAP = json.load(f)
    return _GESTURE_MAP


def map_right_hand_gesture(gesture_label: str) -> str:
    """Map right hand gesture/combo key to controller action."""
    # Load full mapping and isolate right-hand section.
    gmap = load_gesture_map()
    right = gmap.get("right_hand", {})

    # Combo rules have priority over single-gesture rules.
    combos = right.get("combos", {})
    if gesture_label in combos:
        return combos[gesture_label]

    # Fall back to single-gesture mapping, then neutral if unknown.
    gestures = right.get("gestures", {})
    return gestures.get(gesture_label, "NEUTRAL")


def map_right_hand_combo(gesture_labels: list[str]) -> str | None:
    """Resolve a right-hand combo action from gesture labels using JSON config.

    Combo matching is ordered by `combo_priority` when present. If not defined,
    the matcher falls back to longest-combo-first ordering.
    """
    gmap = load_gesture_map()
    right = gmap.get("right_hand", {})
    combos = right.get("combos", {})
    if not combos:
        return None

    labels = set(gesture_labels)
    combo_priority = right.get("combo_priority")
    if not combo_priority:
        combo_priority = sorted(combos.keys(), key=lambda k: len(k.split("+")), reverse=True)

    for combo_key in combo_priority:
        action = combos.get(combo_key)
        if not action:
            continue
        required = {token.strip() for token in combo_key.split("+") if token.strip()}
        if required and required.issubset(labels):
            return action

    return None


def map_hand_actions(handedness: str, gesture_labels: list[str]) -> list[str]:
    """Resolve controller actions for a hand from JSON mapping config.

    Rules:
    - Combo mappings are evaluated first using optional combo_priority.
    - If no combo matches, individual gesture mappings are used.
    - Unknown gestures are ignored.
    - Empty results fall back to ["NEUTRAL"].
    """
    gmap = load_gesture_map()

    side_key = "right_hand" if handedness == "Right" else "left_hand"
    hand_map = gmap.get(side_key, {})

    combos = hand_map.get("combos", {})
    combo_priority = hand_map.get("combo_priority")

    labels = set(gesture_labels)
    if combos:
        if not combo_priority:
            combo_priority = sorted(combos.keys(), key=lambda k: len(k.split("+")), reverse=True)

        for combo_key in combo_priority:
            action = combos.get(combo_key)
            if not action:
                continue
            required = {token.strip() for token in combo_key.split("+") if token.strip()}
            if required and required.issubset(labels):
                return [action]

    gestures = hand_map.get("gestures", {})
    mapped = [gestures[g] for g in gesture_labels if g in gestures]
    return mapped if mapped else ["NEUTRAL"]


def map_left_hand_gesture(gesture_label: str) -> str | None:
    """Map left hand gesture to controller action."""
    # Load full mapping and isolate left-hand section.
    gmap = load_gesture_map()
    left = gmap.get("left_hand", {})
    # Return mapped action or None when gesture has no mapping.
    gestures = left.get("gestures", {})
    return gestures.get(gesture_label)
