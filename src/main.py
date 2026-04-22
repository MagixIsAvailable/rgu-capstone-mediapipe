"""
Module: main.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Core runtime orchestration for the VisionInput pipeline. Captures camera frames, performs MediaPipe hand landmark inference, classifies gestures using deterministic geometric heuristics, maps gestures to controller actions via JSON configuration, applies temporal smoothing and dead-zone handling, then forwards outputs to a virtual Xbox 360 controller through the ViGEm layer. This module also manages WebSocket telemetry, visual debug overlays, latency logging, and benchmark instrumentation.

Architecture (matches Chapter 3 dissertation structure):
├── Vision Layer (Section 3.2)
│   └── Camera init, MediaPipe Hands, frame preprocessing
├── Gesture Detection (Section 3.3)
│   └── detect_gesture() - heuristic geometric classifier
├── Mapping Layer (Section 3.4)
│   └── map_to_vigem() - bimanual asymmetric mapping (Guiard, 1987)
└── Output Layer (Section 3.5)
    └── vigem_output.py - ViGEm virtual Xbox controller

Key Files:
- main.py: This file - core runtime loop
- config.py: All configuration values (EMA_ALPHA, DEAD_ZONE, etc.)
- vigem_output.py: ViGEm output layer
- setup_camera.py: Camera selection utility
- gesture_map.json: Gesture-to-controller mapping (runtime source of truth)
- visualiser.py: Debug overlay (--visualise flag)


Usage:
Run directly as the application entry point.
Examples:

python main.py
python main.py --visualise
python main.py --log-latency
python main.py --benchmark-seconds 30 --run-tag native
"""

import cv2
import sys
import time
import csv
import argparse
import logging
from unittest.mock import MagicMock
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

sys.modules['sounddevice'] = MagicMock()

# =============================================================================
# SECTION 1: CONFIGURATION
# Corresponds to: Chapter 3, Section 3.1 System Architecture
# All tunables consolidated here via config.py for easy adjustment
# =============================================================================

import mediapipe as mp
import asyncio
import websockets
import json
import math
import contextlib
from collections import deque
from config import (
    WEBSOCKET_ENABLED,
    WEBSOCKET_HOST,
    WEBSOCKET_PORT,
    MAX_WEBSOCKET_CLIENTS,
    SENSITIVITY,
    TILT_GAIN,
    NEUTRAL_Y_OFFSET,
    EMA_ALPHA,
    DEAD_ZONE,
    PREPROCESS_CONTRAST_ENABLED,
    PREPROCESS_ALPHA,
    PREPROCESS_BETA,
    PINCH_INDEX,
    PINCH_MIDDLE,
    PINCH_RING,
    PINCH_PINKY,
    CALIBRATION_DURATION,
    LOG_LATENCY_DEFAULT,
    LATENCY_TRIALS,
    LATENCY_LOG_DIR,
    LATENCY_LOG_FILE,
    BENCHMARK_LOG_DIR,
    BENCHMARK_LOG_FILE,
    DETECTION_CONFIDENCE,
    TRACKING_CONFIDENCE,
    CAMERA_REQUEST_FPS,
    CAMERA_REQUEST_WIDTH,
    CAMERA_REQUEST_HEIGHT,
    INTER_HAND_NEUTRAL_EPSILON,
    ANGLE_NORMALIZATION,
)
from gesture_mapping import map_hand_actions

import vigem_output
import visualiser

# MediaPipe legacy Hands solution handle used for detector construction.
mp_hands = mp.solutions.hands
# Directory of this file; used to resolve camera config and project-relative logs.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# SECTION 2: VISION LAYER — Camera & MediaPipe Initialization
# Corresponds to: Chapter 3, Section 3.2 Vision Layer
# - Camera initialization with negotiation (adaptive-by-negotiation)
# - MediaPipe Hands setup (model_complexity=0 for low latency)
# - Optional frame preprocessing (O(x,y) = α·I(x,y) + β)
# =============================================================================

# ----------------------------------------------------------------
# Camera config
# ----------------------------------------------------------------
try:
    # Read persisted camera selection written by setup_camera.py.
    config_path = os.path.join(SCRIPT_DIR, "camera_config.txt")
    with open(config_path, "r") as f:
        content = f.read().strip()
        CAMERA_LABEL = f"camera_index_0"
        if not content:
            CAMERA_INDEX = 0
            logging.warning("camera_config.txt is empty. Using default index 0.")
        elif content.startswith("{"):
            # Preferred format: JSON with index + friendly label.
            payload = json.loads(content)
            CAMERA_INDEX = int(payload.get("camera_index", 0))
            CAMERA_LABEL = payload.get("camera_label", f"camera_index_{CAMERA_INDEX}")
        else:
            # Backward compatibility: legacy config stored only the numeric index.
            CAMERA_INDEX = int(content)
            CAMERA_LABEL = f"camera_index_{CAMERA_INDEX}"
    logging.info(
        f"Loading Camera Index {CAMERA_INDEX} ({CAMERA_LABEL}) from {config_path}..."
    )
except FileNotFoundError:
    logging.warning("camera_config.txt not found. Using default index 0.")
    CAMERA_INDEX = 0
    CAMERA_LABEL = "camera_index_0"
except ValueError:
    logging.error("Invalid camera index in camera_config.txt. Using default 0.")
    CAMERA_INDEX = 0
    CAMERA_LABEL = "camera_index_0"
except json.JSONDecodeError:
    logging.error("Invalid JSON in camera_config.txt. Using default index 0.")
    CAMERA_INDEX = 0
    CAMERA_LABEL = "camera_index_0"

# ----------------------------------------------------------------
# WebSocket
# ----------------------------------------------------------------
connected_clients = set()

# ============================================================================
# ATTRIBUTION NOTE (SIGNPOSTED SECTION)
# Source type: Original implementation by project author
# Pattern used: Standard async WebSocket connection-lifecycle management
# External API reference: websockets.serve / websocket.wait_closed
# Delimitation: This note applies to websocket_handler() below only
# ============================================================================
async def websocket_handler(websocket):
    """Handle incoming WebSocket client connection with connection cap enforcement.
    
    This handler manages a single client connection lifecycle. It maintains a
    global connected_clients set to track all active connections and enforce
    a maximum client limit to prevent resource exhaustion.
    
    Design rationale:
    - One coroutine per client allows concurrent client servicing (async I/O)
    - Connection cap prevents unbounded memory growth (important for long-running
      server processes that may accumulate connection attempts over hours/days)
    - websocket.wait_closed() is blocking but async-safe; coroutine yields control
      while waiting for client to disconnect
    
    Args:
        websocket: websockets connection object (context-managed by caller)
    
    Returns:
        None
    
    Side effects:
        - Modifies global `connected_clients` set (add/remove websocket objects)
        - Logs client connection and disconnection events
        - May close websocket connection if client count exceeds MAX_WEBSOCKET_CLIENTS
    
    Raises:
        Exceptions during websocket operations  are handled by caller (websockets.serve)
        and do not crash the server.
    
    References:
        - config.py: MAX_WEBSOCKET_CLIENTS constant
        - websockets.serve() documentation: https://websockets.readthedocs.io/
    """
    # Enforce a connection cap so telemetry system cannot grow unbounded
    # (e.g., if clients repeatedly connect/disconnect without cleanup)
    if len(connected_clients) >= MAX_WEBSOCKET_CLIENTS:
        logging.warning(f"Rejected connection from {websocket.remote_address}: too many clients")
        await websocket.close()
        return

    logging.info(f"New client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        # Block until this client disconnects (remote close or error)
        # websocket.wait_closed() yields control while waiting (doesn't block event loop)
        await websocket.wait_closed()
    finally:
        # Cleanup: remove from active set (runs even if connection errors out)
        connected_clients.discard(websocket)
        logging.info(f"Client disconnected: {websocket.remote_address}")

    # ============================================================================
    # ATTRIBUTION NOTE (SIGNPOSTED SECTION)
    # Source type: Original implementation by project author
    # Pattern used: Standard pub-sub broadcast with dead-client cleanup
    # External API reference: websockets send/ConnectionClosed semantics
    # Delimitation: This note applies to broadcast() below only
    # ============================================================================
async def broadcast(message_dict):
    """Broadcast a JSON message to all connected WebSocket clients.
    
    Non-blocking pub-sub pattern: ignores clients that disconnect during send
    (they're silently removed from the client set). Fast-exit when no clients
    are listening or WebSocket disabled.
    
    Design rationale:
    - Fast-exit when no receivers (common case during headless operation)
    - Fire-and-forget semantics; if a client drops, just remove and continue
    - JSON serialization centralizes here (single encode per frame vs per-client)
    - Error handling collects dead connections and batch-removes them
    
    Args:
        message_dict: dict, arbitrary data to broadcast
            Typically: {"x": norm_x, "y": norm_y, "gesture": gesture_str, "hand": handedness}
            Will be JSON-encoded and sent to all clients
    
    Returns:
        None
    
    Side effects:
        - Serializes message_dict to JSON string
        - Sends to all connected WebSocket clients (async, non-blocking)
        - Modifies global `connected_clients` set (removes disconnected clients)
        - Logs nothing on success (keep frame-by-frame logging quiet)
    
    Performance note:
        - O(N) complexity where N = number of connected clients
        - Typical case N=0 (telemetry disabled or no clients) → instant return
        - JSON encoding is ~0.1ms for small dicts
    """
    # Fast-exit when WebSocket output is disabled or nobody is listening
    if not WEBSOCKET_ENABLED or not connected_clients:
        return
    
    message_str = json.dumps(message_dict)  # Single encode per frame
    dead = set()  # Collect disconnected clients for batch removal
    
    for client in connected_clients:
        try:
            await client.send(message_str)  # Async send (non-blocking)
        except websockets.exceptions.ConnectionClosed:
            # Client disconnected — mark for removal
            dead.add(client)
    
    # Batch remove all disconnected clients
    connected_clients.difference_update(dead)

# =============================================================================
# SECTION 3: GESTURE DETECTION
# Corresponds to: Chapter 3, Section 3.3 Gesture Detection
# - Heuristic geometric classifier (not ML-based)
# - Pinch detection: Euclidean distance < threshold
# - Bend detection: tip.y > pip.y (finger flexion proxy)
# - Priority order: pinch > combo > individual bend
# =============================================================================

def detect_gesture(landmarks, handedness="Left") -> list[str]:
    """Detect gesture from hand landmarks using heuristic geometric rules.
    
    This function implements a deterministic (non-ML) classifier based on simple
    geometric heuristics: pinch detection via Euclidean distance, finger bends via
    Y-coordinate comparison. Chosen for interpretability and predictable failure modes.
    
    Detection priority (resolves ambiguity when multiple conditions met):
        1. Pinch gestures (finger-to-thumb contact) — highest priority, mutually exclusive
        2. Individual finger bends — combinable, lower priority
        3. Default OPEN_PALM when no bends detected
    
    Algorithm overview:
        RIGHT HAND (dominant — discrete actions):
            1. Check pinches (thumb tip ↔ each finger tip in order: index, middle, ring, pinky)
               If any pinch detected, return immediately (priority blocking)
            2. Check individual finger bends (tip below PIP joint on each finger)
               Collect all bends into a list (combinable, e.g., both index+middle bent)
            3. Return bends list or default ['OPEN_PALM']
        
        LEFT HAND (non-dominant — continuous + D-pad):
            1. Skip pinch detection (left hand only does bends)
            2. Check individual finger bends with 'left_' prefix (for gesture_map.json)
            3. Return bends list or default ['OPEN_PALM']
    
    Gesture labels:
        Pinches (RIGHT only): 'index_pinch', 'middle_pinch', 'ring_pinch', 'pinky_pinch'
        Bends (RIGHT): 'index_bent', 'middle_bent', 'ring_bent', 'pinky_bent'
        Bends (LEFT): 'left_index_bent', 'left_middle_bent', 'left_ring_bent', 'left_pinky_bent'
        Default: 'OPEN_PALM'
    
    Args:
        landmarks: MediaPipe NormalizedLandmarkList object (21 landmarks per hand)
            Indices:
                0: wrist (hand center, used as reference)
                1-4: thumb (MCP, PIP, DIP, tip)
                5-8: index (MCP, PIP, DIP, tip)
                9-12: middle (MCP, PIP, DIP, tip)
                13-16: ring (MCP, PIP, DIP, tip)
                17-20: pinky (MCP, PIP, DIP, tip)
            Reference: https://mediapipe-studio.webapps.google.com/home
        
        handedness: str, either "Left" or "Right"
            Determines which gesture types to detect (pinches only for right hand)
    
    Returns:
        list[str]: Detected gesture labels
            - Pinch detected: ['index_pinch'] (early return)
            - Bends detected: ['index_bent', 'middle_bent'] (may have multiple)
            - No bends: ['OPEN_PALM'] (always non-empty)
    
    Side effects:
        Logging: none (pure computational function)
    
    Thresholds (from config.py):
        Pinch distance thresholds increase per finger due to anatomical reach:
        - PINCH_INDEX = 0.05 (closest thumb reach, most sensitive)
        - PINCH_MIDDLE = 0.06
        - PINCH_RING = 0.07
        - PINCH_PINKY = 0.08 (furthest thumb reach, least sensitive)
        These are normalized Euclidean distances in [0, 1] image coordinates.
        Tuned empirically through calibration phase (Chapter 4, Section 4.3).
    
    Bend detection (Y-axis):
        - Finger tip Y > PIP joint Y → finger is flexed (bent)
        - Y-axis increases downward in image coords (top=0, bottom=1)
        - Simple but effective proxy for flexion (handles rolled fingers, etc.)
    
    Known limitations:
        - Thumb pinch detection assumes thumb-to-tip alignment (fails if thumb is abducted)
        - Bent detection ignores MCP joint angle (only uses DIP crease), may misfire on
          over-extended fingers with large hand shape variation
        - No temporal filtering; single noisy frame can cause false gesture
          (EMA smoothing applied post-detection in main.py, NOT here)
        - RIGHT hand pinch priority may mask simultaneous bends
          (e.g., if index pinches and middle bends, only 'index_pinch' returned)
    
    References:
        - Chapter 3, Section 3.3: Gesture Detection
        - Chapter 4, Section 4.3: Threshold calibration methodology
    """
    def dist(a, b):
        """Compute 2D Euclidean distance in normalized image coordinates."""
        return math.dist((a.x, a.y), (b.x, b.y))

    if handedness == "Right":
        thumb = landmarks[4]  # Thumb tip (landmark 4)
        
        # ===== PHASE 1: Pinch detection (priority — mutually exclusive) =====
        # Pinch detection via Euclidean distance between thumb tip and each finger tip.
        # Thresholds increase per finger due to anatomical reach differences
        # (see config.PINCH_*, tuned during calibration phase).
        
        if dist(landmarks[8],  thumb) < PINCH_INDEX:  return ["index_pinch"]   # 0.05
        if dist(landmarks[12], thumb) < PINCH_MIDDLE: return ["middle_pinch"]  # 0.06
        if dist(landmarks[16], thumb) < PINCH_RING:   return ["ring_pinch"]    # 0.07
        if dist(landmarks[20], thumb) < PINCH_PINKY:  return ["pinky_pinch"]   # 0.08
        
        # ===== PHASE 2: Individual finger bends (combinable, lower priority) =====
        # Finger bend detection: finger tip below PIP joint → finger is flexed.
        # Uses Y-axis comparison (Y increases downward in image coords).
        # Indices: [finger_tip, DIP, PIP, MCP] for each finger
        bends = []
        if landmarks[8].y  > landmarks[6].y:  bends.append("index_bent")   # index tip > index PIP
        if landmarks[12].y > landmarks[10].y: bends.append("middle_bent")  # middle tip > middle PIP
        if landmarks[16].y > landmarks[14].y: bends.append("ring_bent")    # ring tip > ring PIP
        if landmarks[20].y > landmarks[18].y: bends.append("pinky_bent")   # pinky tip > pinky PIP
        
        # ===== PHASE 3: Default to OPEN_PALM if no bends detected =====
        return bends if bends else ["OPEN_PALM"]

    # ===== LEFT HAND: D-pad control (no pinches, only bends for directional navigation) =====
    # Left hand skips pinch detection entirely; used for continuous joystick + D-pad
    # (bimanual asymmetry per Guiard, 1987).
    
    bends = []
    if landmarks[8].y  > landmarks[6].y:  bends.append("left_index_bent")   # Add 'left_' prefix
    if landmarks[12].y > landmarks[10].y: bends.append("left_middle_bent")  # for gesture_map.json lookup
    if landmarks[16].y > landmarks[14].y: bends.append("left_ring_bent")
    if landmarks[20].y > landmarks[18].y: bends.append("left_pinky_bent")
    
    return bends if bends else ["OPEN_PALM"]

# =============================================================================
# SECTION 4: GESTURE MAPPING
# Corresponds to: Chapter 3, Section 3.4 Mapping Layer
# - Bimanual asymmetry (Guiard, 1987)
# - Left hand: continuous navigation (joystick) + D-pad from bends
# - Right hand: discrete actions (buttons from pinches and combos)
# =============================================================================

def map_to_vigem(gesture_list: list[str], handedness: str) -> list[str]:
    """Map detected gestures to Xbox controller actions following bimanual asymmetry.
    
    Bimanual control architecture based on Guiard's Kinematic Chain Model (1987):
    - Non-dominant hand (LEFT): continuous spatial context (joystick + D-pad)
    - Dominant hand (RIGHT): discrete actions (button presses)
    
    This function acts as a thin wrapper around gesture_mapping.map_hand_actions(),
    which reads the actual mappings from gesture_map.json (data-driven, not hardcoded).
    
    Design rationale:
    - Separates gesture DETECTION (heuristic geometric) from MAPPING (data-driven config)
    - Allows runtime remapping of gestures without code changes (config/gesture_map.json)
    - Left-hand labels include 'left_' prefix (from detect_gesture), which must be
      stripped before JSON lookup (gesture_map.json uses unprefixed labels for left hand)
    
    Args:
        gesture_list: list[str], gesture labels from detect_gesture()
            Examples (RIGHT hand): ['index_bent', 'middle_bent'], ['OPEN_PALM']
            Examples (LEFT hand): ['left_index_bent'], ['OPEN_PALM']
        
        handedness: str, "Left" or "Right"
            Determines which set of mappings is applied
    
    Returns:
        list[str]: Controller action labels (vgamepad terminology)
            Examples: ['BUTTON_A'], ['BUTTON_7', 'BUTTON_8'], ['NEUTRAL']
            Passed directly to vigem_output.apply_gesture()
    
    Side effects:
        - Reads gesture_map.json from disk (once, cached by gesture_mapping module)
        - No logging or I/O beyond JSON read
    
    References:
        - Chapter 3, Section 3.4: Mapping Layer
        - Guiard, Y. (1987). Asymmetric division of labor in human skilled bimanual action.
          Journal of Motor Behavior, 19(4), 486-517.
        - gesture_mapping.py: map_hand_actions() implementation
        - gesture_map.json: Runtime mapping configuration
    
    Known issues/limitations:
        - If gesture_map.json is malformed, map_hand_actions() may raise exception
          (should be caught and logged in gesture_mapping module)
        - String matching is case-sensitive (detect_gesture must match gesture_map.json keys exactly)
    """
    if handedness == "Right":
        # Right-hand mappings are fully data-driven via gesture_map.json.
        # Call gesture_mapping.map_hand_actions() with gesture labels as-is.
        return map_hand_actions("Right", gesture_list)

    # Left-hand detector returns labels with 'left_' prefix (e.g., 'left_index_bent').
    # Strip prefix to normalize before JSON lookup — gesture_map.json stores
    # left hand actions under unprefixed keys for clarity.
    normalized = [g.replace("left_", "") for g in gesture_list]
    return map_hand_actions("Left", normalized)


# ============================================================================
# ATTRIBUTION NOTE (SIGNPOSTED SECTION)
# Source type: Original implementation by project author
# Pattern used: Standard Exponential Moving Average (EMA) filter
# Formula: smoothed = alpha * new + (1 - alpha) * previous
# Delimitation: This note applies to ema_smooth_pair() below only
# ============================================================================
def ema_smooth_pair(
    raw_x: float,
    raw_y: float,
    prev_x: float,
    prev_y: float,
    alpha: float,
) -> tuple[float, float]:
    """Apply EMA smoothing to 2D joystick values (x, y)."""
    smooth_x = alpha * raw_x + (1 - alpha) * prev_x
    smooth_y = alpha * raw_y + (1 - alpha) * prev_y
    return smooth_x, smooth_y

# =============================================================================
# SECTION 5: FRAME-SYNCHRONOUS MAIN LOOP & OUTPUT
# Pipeline Structure: Camera → MediaPipe → detect_gesture() → map_to_vigem() → EMA → vigem_output
# - EMA smoothing: smoothed = α × new + (1-α) × previous
# - Dead zone: |value| < DEAD_ZONE → 0 (prevents unintended drift)
# =============================================================================

async def main(
    visualise_mode=False,
    log_latency=False,
    benchmark_seconds=0.0,
    benchmark_capture_only=False,
    run_tag="",
):
    """Main frame-synchronous processing loop for gesture detection and controller output.
    
    Pipeline architecture (runs frame-by-frame, async for WebSocket concurrency):
        1. VISION LAYER: Capture frame from camera, preprocess (flip, contrast)
        2. DETECTION: MediaPipe Hands inference → 21 landmark positions per hand
        3. GESTURE LAYER: detect_gesture() → heuristic labels (pinch, bent, open)
        4. MAPPING: map_to_vigem() → Xbox controller actions (data-driven from gesture_map.json)
        5. FILTERING: EMA smoothing (per-hand) → damp frame jitter while preserving latency
        6. OUTPUT: vigem_output.apply_gesture() → virtual Xbox bus
        7. TELEMETRY: WebSocket broadcast + latency logging + visualisation overlay
    
    Performance targets (from Chapter 4 evaluation):
        - Frame rate: 30-60 fps (adaptive to hardware/camera capability)
        - Gesture latency: <100ms (capture to controller output)
        - EMA smoothing: α=0.3 (tuned for responsiveness vs noise rejection)
    
    Modes and instrumentation:
    
    --visualise (visualise_mode=True):
        Renders rich debug overlay on camera frames showing landmark positions,
        detected gestures, pinch state, wrist vectors, FPS counter, calibration status.
        Used for development/troubleshooting. Adds ~5-15ms per frame overhead.
    
    --log-latency (log_latency=True):
        Records end-to-end latency from frame capture to controller output for first
        LATENCY_TRIALS non-neutral gestures. Logged to logs/latency/latency_log_*.csv
        with per-frame breakdown: capture, preprocess, MediaPipe, output timings.
        Used for performance validation and optimization (Chapter 4 Section 4.2).
    
    --benchmark-seconds N (benchmark_seconds > 0):
        Measures pipeline throughput over N seconds. Two modes:
        - Full pipeline: runs full gesture→controller cycle, logs timing breakdown
        - Capture-only: skips MediaPipe/output, measures raw frame I/O capability
        Output: logs/benchmark/benchmark_runs.csv with per-frame averages and FPS.
    
    --run-tag "string" (run_tag):
        Optional label for this run (e.g., "native", "camo", "low-light") used in logs
        to track experiment conditions. Stored in latency and benchmark CSVs.
    
    State management:
    - Calibration: First CALIBRATION_DURATION seconds (typically 3s) are skipped to build
      stable MediaPipe tracking state. Visualizer shows countdown. ViGEm output suppressed.
    - EMA state: Per-hand smoothing state keyed by hand index (prevents cross-hand bleed).
    - Pinch history: Tracks previous frame pinch distance to compute pinch speed.
    - Read error tracking: Counts cap.read() failures (helpful for diagnostics).
    
    Benchmarking accumulates timing per stage:
        capture_s, preprocess_s, mediapipe_s, output_s, total_s → averages per frame
    
    Args:
        visualise_mode: bool, enable rich debug overlay
        log_latency: bool, record gesture latency to CSV
        benchmark_seconds: float, run benchmark for N seconds (0.0 = disabled)
        benchmark_capture_only: bool, measure frame capture only (skip processing)
        run_tag: str, optional run label for log metadata
    
    Returns:
        None
    
    Side effects:
        - Opens camera device (cv2.VideoCapture)
        - Initializes MediaPipe Hands detector (loads model file, one-time latency ~500ms)
        - Creates/populates CSV files in logs/latency/ and logs/benchmark/
        - Sends telemetry to WebSocket clients if WEBSOCKET_ENABLED
        - Displays OpenCV window if visualise_mode=True
        - Maps hand gestures to Xbox controller via ViGEm (requires driver installation)
        - Catches KeyboardInterrupt (Ctrl+C) for graceful shutdown
    
    Async notes:
        - Main frame loop is async to allow concurrent WebSocket broadcasts
        - asyncio.sleep(0) yields control after each frame (allows event loop to process
          other async tasks, such as WebSocket client handling)
        - Benchmark mode respects async context (doesn't block other tasks)
    
    References:
        - Chapter 3: System architecture and pipeline design
        - Chapter 4: Performance evaluation and calibration
        - config.py: All tunable parameters (EMA_ALPHA, DEAD_ZONE, CALIBRATION_DURATION, etc.)
    
    Known limitations/TODOs:
        - DEAD_ZONE logic defined in config.py but also applied in vigem_output.py
          (should be consolidated to single location to avoid confusion)
        - No multi-threaded camera capture (all I/O on main thread)
        - No fallback if MediaPipe model file (hand_landmarker.task) is missing
        - Benchmark mode computes aggregates only at finish time (no streaming stats)
    """
    # =============================================================================
    # SECTION 1: CONFIGURATION LOADING
    # Corresponds to: Chapter 3, Section 3.1 System Architecture
    # All tunables consolidated here via config.py for easy adjustment
    # =============================================================================

    # =============================================================================
    # SECTION 2: VISION LAYER — Camera & MediaPipe Initialization
    # Corresponds to: Chapter 3, Section 3.2 Vision Layer
    # - Camera initialization with negotiation (adaptive-by-negotiation)
    # - MediaPipe Hands setup (model_complexity=0 for low latency)
    # - Optional frame preprocessing (O(x,y) = α·I(x,y) + β)
    # =============================================================================

    # Build MediaPipe detector once and keep it alive for the run.
    # Using Legacy Hands API (mp_hands.Hands()) for compatibility.
    # model_complexity=0 selected for speed (real-time capable) over accuracy trade-off.
    logging.info("Initializing MediaPipe Hands (Legacy Mode)...")
    with mp_hands.Hands(
        model_complexity=0,  # 0=fast, 1=accurate; 0 chosen for real-time responsiveness
        min_detection_confidence=DETECTION_CONFIDENCE,  # Landmark confidence threshold
        min_tracking_confidence=TRACKING_CONFIDENCE,    # Temporal tracking threshold
        max_num_hands=2  # Bimanual input: both hands supported
    ) as detector:
        # Open selected camera and request preferred capture mode.
        cap = cv2.VideoCapture(CAMERA_INDEX)
        # Request 60 FPS (many webcams require MJPG for >30fps at high res)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FPS, CAMERA_REQUEST_FPS)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_REQUEST_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_REQUEST_HEIGHT)
        if not cap.isOpened():
            logging.error("Run 'python src/setup_camera.py' to fix this.")
            input("Press Enter to exit...")
            logging.error(f"Could not open camera index {CAMERA_INDEX}.")
            return

        print(f"FPS negotiated: {cap.get(cv2.CAP_PROP_FPS)}")
        print(f"Resolution: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        camera_resolution = f"{frame_width}x{frame_height}"
        requested_fps = CAMERA_REQUEST_FPS
        requested_resolution = f"{CAMERA_REQUEST_WIDTH}x{CAMERA_REQUEST_HEIGHT}"
        negotiated_fps = cap.get(cv2.CAP_PROP_FPS)
        backend_id = int(cap.get(cv2.CAP_PROP_BACKEND))
        backend_name = "unknown"
        if hasattr(cv2, "videoio_registry"):
            with contextlib.suppress(Exception):
                backend_name = cv2.videoio_registry.getBackendName(backend_id)
        raw_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        decoded_fourcc = "".join(chr((raw_fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00")
        negotiated_fourcc = decoded_fourcc if decoded_fourcc.isprintable() and decoded_fourcc else "UNKNOWN"

        # Benchmark accumulators hold stage timings across frames.
        benchmark_enabled = benchmark_seconds > 0
        benchmark_start = time.perf_counter()
        benchmark_stats = {
            "frames": 0,
            "capture_s": 0.0,
            "preprocess_s": 0.0,
            "mediapipe_s": 0.0,
            "output_s": 0.0,
            "total_s": 0.0,
        }
        if benchmark_enabled:
            logging.info(
                "Benchmark mode enabled: %.1fs (%s)",
                benchmark_seconds,
                "capture only" if benchmark_capture_only else "full pipeline",
            )

        calibration_start = time.time()
        prev_frame_time   = time.time()
        prev_pinch_dists  = []
        frame_index = 0
        read_failed_count = 0
        frame_time_window = deque()

        # EMA state keyed by hand index — fixes cross-hand bleed
        ema_state = {}

        # WebSocket server is only started when telemetry is enabled.
        server_cm = (
            websockets.serve(websocket_handler, WEBSOCKET_HOST, WEBSOCKET_PORT)
            if WEBSOCKET_ENABLED else contextlib.nullcontext()
        )

        async with server_cm:
            if WEBSOCKET_ENABLED:
                logging.info(f"WebSocket server running on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
            logging.info("Camera running. Press 'q' to quit.")

            latency_count = 0
            project_root = Path(SCRIPT_DIR).parent
            # Create per-session latency CSV in logs/latency.
            latency_dir = project_root / LATENCY_LOG_DIR
            latency_dir.mkdir(parents=True, exist_ok=True)
            session_created_at = time.strftime("%Y-%m-%d %H:%M:%S")
            session_file_stamp = time.strftime("%Y%m%d_%H%M%S")
            latency_path = latency_dir / f"latency_log_{session_file_stamp}.csv"
            latency_file_handle = None
            latency_writer = None
            if log_latency:
                # Write static session metadata first, then per-event rows.
                latency_file_handle = latency_path.open("w", newline="")
                latency_writer = csv.writer(latency_file_handle)
                # Write run metadata once to avoid duplicating static values per event row.
                latency_writer.writerow(["session_created_at", session_created_at])
                latency_writer.writerow(["camera_label", CAMERA_LABEL])
                latency_writer.writerow(["camera_resolution", camera_resolution])
                latency_writer.writerow(["run_tag", run_tag])
                latency_writer.writerow(["visualise_mode", str(visualise_mode).lower()])
                latency_writer.writerow(["websocket_enabled", str(WEBSOCKET_ENABLED).lower()])
                latency_writer.writerow(["backend", f"{backend_name} ({backend_id})"])
                latency_writer.writerow(["requested_resolution", requested_resolution])
                latency_writer.writerow(["requested_fps", requested_fps])
                latency_writer.writerow(["negotiated_fps", f"{negotiated_fps:.2f}"])
                latency_writer.writerow(["negotiated_fourcc", negotiated_fourcc or "unknown"])
                latency_writer.writerow([])
                latency_writer.writerow([
                    "timestamp",
                    "frame_index",
                    "gesture_label",
                    "hand",
                    "hand_confidence",
                    "hand_count",
                    "is_non_neutral",
                    "latency_ms",
                    "norm_x",
                    "norm_y",
                    "fps_rolling_1s",
                    "capture_ms",
                    "preprocess_ms",
                    "mediapipe_ms",
                    "output_ms",
                    "loop_ms",
                    "read_failed_count",
                ])

            try:
                while cap.isOpened():
                    # =============================================================================
                    # FRAME SYNCHRONOUS MAIN LOOP
                    # Pipeline: Camera → MediaPipe → detect_gesture() → map_to_vigem() → EMA → ViGEm
                    # =============================================================================
                    
                    # Total frame loop timing starts here.
                    frame_loop_t0 = time.perf_counter()
                    frame_index += 1
                    frame_t_start = None
                    if log_latency and latency_count < LATENCY_TRIALS:
                        # Measure end-to-end latency from frame capture through ViGEm output.
                        frame_t_start = time.perf_counter()

                    # =============================================================================
                    # STAGE 1: CAPTURE & PREPROCESS
                    # =============================================================================
                    
                    capture_t0 = time.perf_counter()
                    ret, frame = cap.read()  # Read one frame from camera
                    capture_t1 = time.perf_counter()
                    benchmark_stats["capture_s"] += (capture_t1 - capture_t0)
                    if not ret:
                        read_failed_count += 1
                        logging.error("Failed to receive frame.")
                        break  # Camera disconnected or read error
                    if visualise_mode and (cv2.waitKey(1) & 0xFF == ord('q')):
                        break  # User pressed 'q' to quit

                    # Skip processing during calibration (just capture and drain frames)
                    if benchmark_enabled and benchmark_capture_only:
                        # Capture-only mode intentionally skips processing/output.
                        benchmark_stats["frames"] += 1
                        benchmark_stats["total_s"] += (time.perf_counter() - frame_loop_t0)
                        if (time.perf_counter() - benchmark_start) >= benchmark_seconds:
                            break  # Benchmark duration exceeded
                        await asyncio.sleep(0)  # Yield to event loop
                        continue

                    # Frame preprocessing: flip for natural interaction + optional contrast boost
                    preprocess_t0 = time.perf_counter()
                    frame = cv2.flip(frame, 1)  # Horizontal flip (mirror for user comfort)
                    if PREPROCESS_CONTRAST_ENABLED:
                        # Optional contrast/brightness adjustment: O(x,y) = α·I(x,y) + β
                        # Can help with poor lighting or washed-out video
                        frame = cv2.convertScaleAbs(
                            frame,
                            alpha=PREPROCESS_ALPHA,      # Contrast multiplier
                            beta=PREPROCESS_BETA,        # Brightness offset
                        )
                    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert to RGB for MediaPipe
                    rgb.flags.writeable = False  # Hint to MediaPipe for optimization
                    preprocess_t1 = time.perf_counter()
                    benchmark_stats["preprocess_s"] += (preprocess_t1 - preprocess_t0)

                    # =============================================================================
                    # STAGE 2: MEDIA PIPE INFERENCE (Gesture Detection Layer)
                    # =============================================================================
                    mediapipe_t0 = time.perf_counter()
                    # Hand landmark inference (21 landmarks per hand, confidence scores)
                    result = detector.process(rgb)
                    mediapipe_t1 = time.perf_counter()
                    benchmark_stats["mediapipe_s"] += (mediapipe_t1 - mediapipe_t0)
                    rgb.flags.writeable = True
                    capture_ms_frame = (capture_t1 - capture_t0) * 1000.0
                    preprocess_ms_frame = (preprocess_t1 - preprocess_t0) * 1000.0
                    mediapipe_ms_frame = (mediapipe_t1 - mediapipe_t0) * 1000.0

                    # =============================================================================
                    # FRAME TIMING & FPS CALCULATION
                    # =============================================================================
                    now = time.time()
                    
                    # Instantaneous FPS (1 / frame_dt) + rolling 1-second FPS for monitoring
                    dt  = now - prev_frame_time
                    fps = 1.0 / dt if dt > 0 else 0  # Instantaneous
                    prev_frame_time = now
                    
                    # Rolling 1-second window: track timestamps of past second
                    frame_time_window.append(now)
                    while frame_time_window and (now - frame_time_window[0]) > 1.0:
                        frame_time_window.popleft()  # Remove old timestamps
                    
                    # Compute rolling FPS from window (more stable than instantaneous)
                    if len(frame_time_window) >= 2:
                        rolling_window_s = frame_time_window[-1] - frame_time_window[0]
                        fps_rolling_1s = ((len(frame_time_window) - 1) / rolling_window_s) if rolling_window_s > 0 else fps
                    else:
                        fps_rolling_1s = fps

                    # Check if still in calibration phase
                    elapsed = now - calibration_start
                    if benchmark_enabled:
                        # Benchmark mode should measure steady-state processing, not startup calibration delay.
                        elapsed = CALIBRATION_DURATION  # Skip directly to end of calibration
                    is_calibrating = elapsed < CALIBRATION_DURATION

                    calculated_values = {
                        'fps': fps,
                        'calibration_status': "calibrating" if is_calibrating else "calibrated",
                        'calibration_time_remain': max(0, CALIBRATION_DURATION - elapsed),
                        'gestures': [], 'handedness': [],
                        'pinch_dists': [], 'pinch_speeds': [], 'wrist_coords': []
                    }

                    output_t0 = time.perf_counter()
                    pending_latency_rows = []
                    if result.multi_hand_landmarks and not is_calibrating:
                        # =============================================================================
                        # STAGE 3: GESTURE DETECTION & MAPPING
                        # Applies detect_gesture() → map_to_vigem() → EMA smoothing → ViGEm output
                        # =============================================================================
                        
                        # Align pinch history length to detected hand count
                        n_hands = len(result.multi_hand_landmarks)
                        while len(prev_pinch_dists) < n_hands:
                            prev_pinch_dists.append(0.0)
                        prev_pinch_dists = prev_pinch_dists[:n_hands]

                        # Pre-pass: identify left/right wrist positions for inter-hand joystick Y
                        # (left hand's joystick Y is derived from angle between wrists)
                        left_lms = right_lms = None
                        for idx, h_obj in enumerate(result.multi_handedness):
                            lbl = h_obj.classification[0].label  # "Left" or "Right"
                            lm  = result.multi_hand_landmarks[idx].landmark
                            if lbl == "Left":  left_lms  = lm
                            elif lbl == "Right": right_lms = lm

                        # Process each detected hand independently
                        for i, hlp in enumerate(result.multi_hand_landmarks):
                            lm = hlp.landmark  # 21 normalized landmarks
                            hand_info = result.multi_handedness[i].classification[0]
                            handedness = hand_info.label  # "Left" or "Right"
                            hand_confidence = hand_info.score  # 0-1, confidence in classification

                            # =================================================================
                            # GESTURE DETECTION (heuristic geometric classifier)
                            # =================================================================
                            gesture_list = detect_gesture(lm, handedness)
                            
                            # =================================================================
                            # GESTURE MAPPING (data-driven via gesture_map.json)
                            # =================================================================
                            # Convert abstract gesture labels to controller actions
                            vigem_label  = map_to_vigem(gesture_list, handedness)

                            # =================================================================
                            # JOYSTICK COMPUTATION (wrist-based continuous input)
                            # =================================================================
                            # Joystick X: hand tilt (wrist → middle MCP angle)
                            # Used to steer/pan in applications
                            wrist  = lm[0]      # Wrist (landmark 0)
                            mcp    = lm[9]      # Middle MCP (landmark 9)
                            h_size = math.sqrt((mcp.x - wrist.x)**2 + (mcp.y - wrist.y)**2)
                            tilt_x = (mcp.x - wrist.x) / (h_size + 1e-6)  # Normalized tilt
                            norm_x = tilt_x * TILT_GAIN  # Amplify for controller response

                            # Joystick Y: inter-hand angle (left hand) or wrist tilt fallback
                            # For left hand: Y = angle between left and right wrist positions
                            #   (creates a 2-hand spatial control mechanism)
                            # For right hand: Y = wrist forward-back tilt (fallback)
                            if handedness == "Left" and right_lms:
                                # Both hands visible: use inter-hand distance for Y
                                l_w, r_w = left_lms[0], right_lms[0]
                                dx = r_w.x - l_w.x  # Horizontal separation
                                dy = r_w.y - l_w.y  # Vertical separation
                                
                                # Neutral zone: if hands are very close, center joystick Y
                                if abs(dx) < INTER_HAND_NEUTRAL_EPSILON and abs(dy) < INTER_HAND_NEUTRAL_EPSILON:
                                    norm_y = 0.0
                                else:
                                    # Compute angle from left to right wrist, normalize to [-1, 1]
                                    angle = math.atan2(dy, dx)  # -π to +π
                                    norm_y = -(angle / ANGLE_NORMALIZATION)  # Negate for intuitive control
                            else:
                                # Right hand or left hand alone: use wrist tilt fallback
                                tilt_y = (wrist.y - mcp.y) / (h_size + 1e-6)  # Forward-back tilt
                                norm_y = -(tilt_y - NEUTRAL_Y_OFFSET) * TILT_GAIN

                            # =================================================================
                            # EMA SMOOTHING (temporal filtering)
                            # Reference: Chapter 4 "Temporal Filtering & Latency Analysis"
                            # =================================================================
                            # Exponential Moving Average: smoothed = α·raw + (1-α)·previous
                            # - α=0.3: balances smoothness vs latency (tuned empirically)
                            # - Per-hand state (keyed by index) prevents cross-hand bleed
                            # - Reduces frame jitter while preserving responsiveness
                            
                            prev = ema_state.get(i, (0.0, 0.0))  # Get previous state for this hand
                            a = EMA_ALPHA  # Smoothing factor (typically 0.3)
                            norm_x, norm_y = ema_smooth_pair(
                                norm_x,
                                norm_y,
                                prev[0],
                                prev[1],
                                a,
                            )
                            ema_state[i] = (norm_x, norm_y)  # Cache for next frame

                            # Clamp to Xbox controller range [-1.0, 1.0]
                            norm_x = max(-1.0, min(1.0, norm_x))
                            norm_y = max(-1.0, min(1.0, norm_y))

                            # TODO: DEAD_ZONE defined in config.py but also applied in vigem_output.py
                            # (apply_gesture). Consolidate to single location to avoid confusion
                            # and potential duplicated logic post-evaluation.
                            
                            # =================================================================
                            # CONTROLLER OUTPUT (send mapped action + analog values)
                            # =================================================================
                            # Send to virtual Xbox bus via ViGEm
                            vigem_output.apply_gesture(vigem_label, handedness, norm_x, norm_y)

                            # =================================================================
                            # LATENCY LOGGING (selective, only for non-neutral gestures)
                            # =================================================================
                            # Gesture latency: time from frame capture to ViGEm output
                            # Logged only when: latency logging enabled AND gesture non-neutral
                            is_non_neutral = any(g != "OPEN_PALM" for g in gesture_list)
                            should_log_latency = (
                                frame_t_start is not None
                                and is_non_neutral
                                and latency_count < LATENCY_TRIALS
                            )
                            if should_log_latency and latency_writer is not None:
                                # Buffer rows and append output/loop timings later in same frame.
                                t_end = time.perf_counter()
                                latency_ms = (t_end - frame_t_start) * 1000
                                gest_str = ",".join(gesture_list)  # CSV-friendly comma-separated list
                                pending_latency_rows.append([
                                    time.strftime("%H:%M:%S"),
                                    frame_index,
                                    gest_str,
                                    handedness.lower(),
                                    f"{hand_confidence:.3f}",
                                    len(result.multi_hand_landmarks),
                                    str(is_non_neutral).lower(),
                                    f"{latency_ms:.2f}",
                                    f"{norm_x:.3f}",
                                    f"{norm_y:.3f}",
                                    f"{fps_rolling_1s:.2f}",
                                    f"{capture_ms_frame:.2f}",
                                    f"{preprocess_ms_frame:.2f}",
                                    f"{mediapipe_ms_frame:.2f}",
                                ])

                                latency_count += 1
                                if latency_count == LATENCY_TRIALS:
                                    saved_path = latency_path.resolve()
                                    print(
                                        f"\nLatency logging complete - {LATENCY_TRIALS} trials saved to {saved_path}"
                                    )

                            # =================================================================
                            # WebSocket TELEMETRY (optional real-time visualization)
                            # =================================================================
                            gest_str = ",".join(gesture_list)
                            # Broadcast to connected clients for web-based monitoring/visualization
                            await broadcast({"x": norm_x, "y": norm_y,
                                             "gesture": gest_str, "hand": handedness})

                            # =================================================================
                            # DEBUG/VISUALISATION DATA (populated for --visualise overlay)
                            # =================================================================
                            disp_label = ",".join(vigem_label)  # Display format
                            calculated_values['gestures'].append(disp_label)
                            calculated_values['handedness'].append(handedness)
                            calculated_values['wrist_coords'].append((norm_x, norm_y))

                            # Compute pinch metrics for visualisation
                            thumb, idx_tip = lm[4], lm[8]
                            p_dist = math.sqrt((idx_tip.x - thumb.x)**2 + (idx_tip.y - thumb.y)**2)
                            calculated_values['pinch_dists'].append(p_dist)
                            calculated_values['pinch_speeds'].append(abs(p_dist - prev_pinch_dists[i]))
                            prev_pinch_dists[i] = p_dist

                    else:
                        # No valid hand data (calibrating or no hands detected):
                        # Release controller and reset frame-local history state.
                        vigem_output.release_all()
                        prev_pinch_dists = []
                        ema_state.clear()  # Clear per-hand smoothing state
                    
                    output_t1 = time.perf_counter()
                    benchmark_stats["output_s"] += (output_t1 - output_t0)
                    output_ms_frame = (output_t1 - output_t0) * 1000.0
                    loop_ms_frame = (time.perf_counter() - frame_loop_t0) * 1000.0
                    
                    # Finalize latency rows with stage timings
                    if pending_latency_rows and latency_writer is not None:
                        for base_row in pending_latency_rows:
                            latency_writer.writerow(base_row + [
                                f"{output_ms_frame:.2f}",
                                f"{loop_ms_frame:.2f}",
                                read_failed_count,
                            ])

                    if visualise_mode:
                        # Draw rich diagnostics overlay window when --visualise is enabled.
                        # Layers: landmarks, skeleton, pinch indicators, wrist vectors, calibration status
                        vis_lm = [hlp.landmark for hlp in (result.multi_hand_landmarks or [])]
                        annotated = visualiser.draw_overlay(frame, vis_lm, calculated_values)
                        cv2.imshow("MediaPipe Gesture Controller", annotated)

                    # Benchmark accumulation: add this frame's timing to totals
                    benchmark_stats["frames"] += 1
                    benchmark_stats["total_s"] += (time.perf_counter() - frame_loop_t0)
                    
                    # Check if benchmark duration exceeded
                    if benchmark_enabled and (time.perf_counter() - benchmark_start) >= benchmark_seconds:
                        break

                    # Yield control to event loop for other async tasks (WebSocket clients)
                    await asyncio.sleep(0)
            finally:
                # Always release resources, even on errors/keyboard interrupt.
                cap.release()
                if visualise_mode:
                    cv2.destroyAllWindows()
                if latency_file_handle is not None:
                    latency_file_handle.close()

                # =============================================================================
                # SECTION 4: BENCHMARK AGGREGATION & RESULTS
                # Compute per-frame averages from accumulated timing data
                # =============================================================================
                if benchmark_enabled:
                    # Compute aggregate per-frame stats from accumulated timings
                    runtime_s = max(1e-9, time.perf_counter() - benchmark_start)  # Total elapsed time
                    frames = benchmark_stats["frames"]  # Total frames processed
                    fps = frames / runtime_s  # Overall throughput
                    
                    # Compute per-frame average for each stage (ms per frame)
                    per_frame_ms = lambda s: (s / frames * 1000.0) if frames else 0.0
                    capture_ms = per_frame_ms(benchmark_stats["capture_s"])
                    preprocess_ms = per_frame_ms(benchmark_stats["preprocess_s"])
                    mediapipe_ms = per_frame_ms(benchmark_stats["mediapipe_s"])
                    output_ms = per_frame_ms(benchmark_stats["output_s"])
                    loop_total_ms = per_frame_ms(benchmark_stats["total_s"])

                    # Write results to logs/benchmark/benchmark_runs.csv
                    benchmark_dir = project_root / BENCHMARK_LOG_DIR
                    benchmark_dir.mkdir(parents=True, exist_ok=True)
                    benchmark_path = benchmark_dir / BENCHMARK_LOG_FILE
                    
                    # Define CSV column headers for benchmark results
                    benchmark_header = [
                        "timestamp",
                        "run_tag",
                        "camera_label",
                        "camera_resolution",
                        "backend",
                        "negotiated_fourcc",
                        "mode",
                        "duration_s",
                        "frames",
                        "fps",
                        "capture_ms_per_frame",
                        "preprocess_ms_per_frame",
                        "mediapipe_ms_per_frame",
                        "output_ms_per_frame",
                        "loop_total_ms_per_frame",
                    ]
                    
                    # Check header compatibility if CSV already exists
                    # (prevents mixing different versions of benchmark schema)
                    if benchmark_path.exists() and benchmark_path.stat().st_size > 0:
                        with benchmark_path.open("r", newline="") as f:
                            existing_header = f.readline().strip()
                        expected_header = ",".join(benchmark_header)
                        if existing_header != expected_header:
                            # Schema mismatch: use versioned filename
                            benchmark_path = benchmark_dir / "benchmark_runs_v2.csv"

                    # Append results row (and header if file is empty/new)
                    benchmark_file_exists = benchmark_path.exists() and benchmark_path.stat().st_size > 0

                    with benchmark_path.open("a", newline="") as f:
                        writer = csv.writer(f)
                        if not benchmark_file_exists:
                            writer.writerow(benchmark_header)  # Write header if new file

                        writer.writerow([
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                            run_tag,
                            CAMERA_LABEL,
                            camera_resolution,
                            f"{backend_name} ({backend_id})",
                            negotiated_fourcc or "unknown",
                            "capture-only" if benchmark_capture_only else "full-pipeline",
                            f"{runtime_s:.2f}",
                            frames,
                            f"{fps:.2f}",
                            f"{capture_ms:.2f}",
                            f"{preprocess_ms:.2f}",
                            f"{mediapipe_ms:.2f}",
                            f"{output_ms:.2f}",
                            f"{loop_total_ms:.2f}",
                        ])

                    # Print summary to console
                    print("\n=== Benchmark Summary ===")
                    print(f"Mode: {'capture-only' if benchmark_capture_only else 'full-pipeline'}")
                    print(f"Duration: {runtime_s:.2f}s")
                    print(f"Frames: {frames}")
                    print(f"FPS: {fps:.2f}")
                    print(f"Capture avg: {capture_ms:.2f} ms/frame")
                    if not benchmark_capture_only:
                        print(f"Preprocess avg: {preprocess_ms:.2f} ms/frame")
                        print(f"MediaPipe avg: {mediapipe_ms:.2f} ms/frame")
                        print(f"Output avg: {output_ms:.2f} ms/frame")
                    print(f"Loop total avg: {loop_total_ms:.2f} ms/frame")
                    print(f"Benchmark row saved to: {benchmark_path.resolve()}")

if __name__ == "__main__":
    # Command-line interface for runtime modes and instrumentation flags.
    # Allows developers to run different configurations without code changes.
    
    parser = argparse.ArgumentParser(description="VisionInput — Gesture-Based Xbox Controller")
    
    # Debug visualization flag
    parser.add_argument(
        "--visualise",
        action="store_true",
        help="Enable rich debug overlay: shows landmarks, gestures, pinch state, FPS. "
             "Useful for development/troubleshooting. Adds ~5-15ms/frame overhead. "
             "(Chapter 5: Diagnostic system design)"
    )
    
    # Latency logging flag
    parser.add_argument(
        "--log-latency",
        action="store_true",
        help="Record gesture-to-output latency to logs/latency/latency_log_*.csv. "
             "Captures first LATENCY_TRIALS non-neutral gestures with per-stage timings "
             "(capture, preprocess, MediaPipe, output, total loop). "
             "Used for performance validation. (Chapter 4 Section 4.2)"
    )
    
    # Performance benchmarking mode
    parser.add_argument(
        "--benchmark-seconds",
        type=float,
        default=0.0,
        help="Run benchmark for N seconds, measure throughput and per-frame timings. "
             "Output: logs/benchmark/benchmark_runs.csv with averaged stage times and FPS. "
             "Useful for hardware comparison and optimization. Default: 0.0 (disabled)"
    )
    
    # Capture-only benchmark mode (useful for isolating camera I/O performance)
    parser.add_argument(
        "--benchmark-capture-only",
        action="store_true",
        help="During benchmark, measure frame capture only (skip MediaPipe and output). "
             "Isolates camera/encoder bottleneck from processing pipeline. "
             "Requires --benchmark-seconds. Useful for camera negotiation testing."
    )
    
    # Custom run label for experiment tracking
    parser.add_argument(
        "--run-tag",
        type=str,
        default="",
        help="Optional label for this run, stored in latency/benchmark logs. "
             "Examples: 'native', 'camo', 'low-light', 'usb2', 'resolution_1080p'. "
             "Used to track experiment conditions and group results for analysis."
    )
    
    args = parser.parse_args()
    
    try:
        # Run the main async event loop
        asyncio.run(main(
            visualise_mode=args.visualise,
            log_latency=(LOG_LATENCY_DEFAULT or args.log_latency),
            benchmark_seconds=args.benchmark_seconds,
            benchmark_capture_only=args.benchmark_capture_only,
            run_tag=args.run_tag,
        ))
    except KeyboardInterrupt:
        # User pressed Ctrl+C — graceful shutdown (resources cleaned up in finally blocks)
        logging.info("Program stopped by user.")