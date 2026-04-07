"""Loads gesture mapping from JSON and exposes mapping helpers."""

import json
from pathlib import Path

_GESTURE_MAP = None


def load_gesture_map(path: str | None = None) -> dict:
    """Load gesture mapping from JSON file."""
    global _GESTURE_MAP
    if _GESTURE_MAP is None:
        map_path = Path(path) if path else (Path(__file__).resolve().parent.parent / "config" / "gesture_map.json")
        if not map_path.exists():
            raise FileNotFoundError(f"Gesture map not found: {map_path}")
        with map_path.open("r", encoding="utf-8") as f:
            _GESTURE_MAP = json.load(f)
    return _GESTURE_MAP


def map_right_hand_gesture(gesture_label: str) -> str:
    """Map right hand gesture/combo key to controller action."""
    gmap = load_gesture_map()
    right = gmap.get("right_hand", {})

    combos = right.get("combos", {})
    if gesture_label in combos:
        return combos[gesture_label]

    gestures = right.get("gestures", {})
    return gestures.get(gesture_label, "NEUTRAL")


def map_left_hand_gesture(gesture_label: str) -> str | None:
    """Map left hand gesture to controller action."""
    gmap = load_gesture_map()
    left = gmap.get("left_hand", {})
    gestures = left.get("gestures", {})
    return gestures.get(gesture_label)
