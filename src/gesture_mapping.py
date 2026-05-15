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
import sys
from importlib import import_module
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
        # When frozen by PyInstaller, resources are extracted to sys._MEIPASS.
        # Try fallback locations so bundled apps can find the JSON file.
        if not map_path.exists():
            # check PyInstaller temp extraction dir
            _meipass = getattr(sys, '_MEIPASS', None)
            if _meipass:
                alt = Path(_meipass) / 'config' / 'gesture_map.json'
                if alt.exists():
                    map_path = alt

        if not map_path.exists():
            # check current working dir config
            alt2 = Path.cwd() / 'config' / 'gesture_map.json'
            if alt2.exists():
                map_path = alt2

        # Also try scanning any _MEI* temp extraction folder locations for config
        if not map_path.exists():
            try:
                import tempfile
                tmp = Path(tempfile.gettempdir())
                for p in tmp.iterdir():
                    if p.name.startswith('_MEI') and p.is_dir():
                        candidate = p / 'config' / 'gesture_map.json'
                        if candidate.exists():
                            map_path = candidate
                            break
            except Exception:
                pass

        # If we located a file, parse it. Otherwise try embedded fallback.
        if map_path.exists():
            with map_path.open("r", encoding="utf-8") as f:
                _GESTURE_MAP = json.load(f)
        else:
            # 1) Try importing embedded module as a normal package module.
            mod = None
            try:
                mod = import_module('src._embedded_gesture_map')
            except Exception:
                try:
                    mod = import_module('_embedded_gesture_map')
                except Exception:
                    mod = None

            if mod and hasattr(mod, '_EMBEDDED_GESTURE_MAP'):
                _GESTURE_MAP = mod._EMBEDDED_GESTURE_MAP
            else:
                # 2) Try reading the extracted data file from sys._MEIPASS/src/_embedded_gesture_map.py
                try:
                    _meipass = getattr(sys, '_MEIPASS', None)
                    if _meipass:
                        emb = Path(_meipass) / 'src' / '_embedded_gesture_map.py'
                        if emb.exists():
                            scope = {}
                            code = emb.read_text(encoding='utf-8')
                            exec(code, scope)
                            if '_EMBEDDED_GESTURE_MAP' in scope:
                                _GESTURE_MAP = scope['_EMBEDDED_GESTURE_MAP']
                except Exception:
                    _GESTURE_MAP = None

            if _GESTURE_MAP is None:
                        # Nothing worked — fall back to a built-in default mapping so the
                        # frozen app continues to run. This mirrors the content added to
                        # src/_embedded_gesture_map.py at build-time.
                        _GESTURE_MAP = {
                            "right_hand": {
                                "gestures": {
                                    "index_bent": "BUTTON_A",
                                    "middle_bent": "BUTTON_B",
                                    "ring_bent": "BUTTON_X",
                                    "pinky_bent": "BUTTON_Y",
                                    "index_pinch": "SHOULDER_LEFT",
                                    "middle_pinch": "SHOULDER_RIGHT",
                                    "ring_pinch": "TRIGGER_LT",
                                    "pinky_pinch": "TRIGGER_RT",
                                    "OPEN_PALM": "NEUTRAL"
                                },
                                "combos": {},
                                "combo_priority": []
                            },
                            "left_hand": {
                                "gestures": {
                                    "index_bent": "DPAD_UP",
                                    "middle_bent": "DPAD_DOWN",
                                    "ring_bent": "DPAD_LEFT",
                                    "pinky_bent": "DPAD_RIGHT"
                                },
                                "combos": {
                                    "index_bent+middle_bent": "BUTTON_BACK",
                                    "ring_bent+pinky_bent": "BUTTON_START"
                                },
                                "combo_priority": [
                                    "index_bent+middle_bent",
                                    "ring_bent+pinky_bent"
                                ]
                            }
                        }
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
