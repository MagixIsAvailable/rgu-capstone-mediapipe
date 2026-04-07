"""Loads gesture mapping from JSON and exposes mapping helpers."""

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


def map_left_hand_gesture(gesture_label: str) -> str | None:
    """Map left hand gesture to controller action."""
    # Load full mapping and isolate left-hand section.
    gmap = load_gesture_map()
    left = gmap.get("left_hand", {})
    # Return mapped action or None when gesture has no mapping.
    gestures = left.get("gestures", {})
    return gestures.get(gesture_label)
