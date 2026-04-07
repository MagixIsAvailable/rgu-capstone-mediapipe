"""VisionInput — Gesture-to-Controller System
==========================================
BSc (Hons) Computing & Creative Design Capstone Project
Robert Gordon University | CM4134 Honours Project

This module implements a vision-based gesture controller that translates
hand movements into Xbox controller inputs via MediaPipe and ViGEm.

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

Author: Michal Lazovy
Supervisor: Dr John N.A. Brown
Last Updated: April 2026
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
    logging.error("Error: 'camera_config.txt' not found.")
    logging.error("Please run 'python src/setup_camera.py' first to select your camera.")
    input("Press Enter to exit...")
    sys.exit()
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

async def websocket_handler(websocket):
    # Enforce a connection cap so telemetry cannot grow unbounded.
    if len(connected_clients) >= MAX_WEBSOCKET_CLIENTS:
        logging.warning(f"Rejected connection from {websocket.remote_address}: too many clients")
        await websocket.close()
        return

    logging.info(f"New client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        logging.info(f"Client disconnected: {websocket.remote_address}")

async def broadcast(message_dict):
    # Fast-exit when websocket output is disabled or nobody is listening.
    if not WEBSOCKET_ENABLED or not connected_clients:
        return
    message_str = json.dumps(message_dict)
    dead = set()
    for client in connected_clients:
        try:
            await client.send(message_str)
        except websockets.exceptions.ConnectionClosed:
            dead.add(client)
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
    
    This function implements a deterministic classifier rather than ML-based
    recognition. Selected for interpretability and predictable failure modes.
    
    Detection priority (to resolve ambiguity):
        1. Pinch gestures (finger-to-thumb contact)
        2. Multi-finger combos (e.g., index+middle for BUTTON_7)
        3. Individual finger bends
    
    Args:
        landmarks: MediaPipe NormalizedLandmarkList (21 landmarks)
            Index mapping: 0=wrist, 1-4=thumb, 5-8=index, 9-12=middle,
            13-16=ring, 17-20=pinky. Within each finger: MCP→PIP→DIP→tip.
        handedness: str, either "Left" or "Right"
    
    Returns:
        list[str]: List of detected gesture labels (e.g., ['index_bent', 'middle_bent'])
                   Empty bends list defaults to ['OPEN_PALM'].
    
    References:
        - Chapter 3, Section 3.3 Gesture Detection
        - Pinch thresholds: index=0.05, middle=0.06, ring=0.07, pinky=0.08
            (Thresholds increase per finger due to anatomical reach differences)
    """
    def dist(a, b):
        # 2D euclidean distance in normalized image coordinates.
        return math.dist((a.x, a.y), (b.x, b.y))

    if handedness == "Right":
        thumb = landmarks[4]  # Thumb tip (landmark 4)
        # Layer B: pinch detection (priority — mutually exclusive)
        # Pinch detection: Euclidean distance between thumb tip and finger tip.
        # Thresholds increase per finger due to anatomical reach differences.
        if dist(landmarks[8],  thumb) < PINCH_INDEX:  return ["index_pinch"]   # 0.05
        if dist(landmarks[12], thumb) < PINCH_MIDDLE: return ["middle_pinch"]  # 0.06
        if dist(landmarks[16], thumb) < PINCH_RING:   return ["ring_pinch"]    # 0.07
        if dist(landmarks[20], thumb) < PINCH_PINKY:  return ["pinky_pinch"]   # 0.08
        
        # Layer A: individual finger bends (combinable)
        # Finger bend detection: tip below PIP joint = finger flexed.
        # Uses Y-axis comparison (Y increases downward in image coords).
        bends = []
        if landmarks[8].y  > landmarks[6].y:  bends.append("index_bent")   # tip > PIP
        if landmarks[12].y > landmarks[10].y: bends.append("middle_bent")  # tip > PIP
        if landmarks[16].y > landmarks[14].y: bends.append("ring_bent")    # tip > PIP
        if landmarks[20].y > landmarks[18].y: bends.append("pinky_bent")   # tip > PIP
        return bends if bends else ["OPEN_PALM"]

    # Left hand — D-pad control (no pinches, only bends for directional navigation)
    # Layer: individual bends (combinable, same logic as right hand)
    bends = []
    if landmarks[8].y  > landmarks[6].y:  bends.append("left_index_bent")
    if landmarks[12].y > landmarks[10].y: bends.append("left_middle_bent")
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
    """Map detected gestures to controller actions following bimanual asymmetry.
    
    Design based on Guiard's Kinematic Chain Model (1987):
    - Non-dominant hand (left): continuous spatial context (joystick)
    - Dominant hand (right): discrete actions (buttons)
    
    Args:
        gesture_list: list[str], gesture labels from detect_gesture()
            E.g., ['index_bent', 'middle_bent'] from right hand
        handedness: str, "Left" or "Right"
    
    Returns:
        list[str]: Controller actions to apply via vigem_output.apply_gesture()
                   E.g., ['BUTTON_7'] or ['NEUTRAL']
    
    References:
        - Chapter 3, Section 3.4 Mapping Layer
        - Guiard, Y. (1987). Asymmetric division of labor in human skilled bimanual action."""
    if handedness == "Right":
        # Right-hand mappings are fully data-driven via gesture_map.json.
        return map_hand_actions("Right", gesture_list)

    # Left-hand detector labels are emitted as left_*; normalize before JSON lookup.
    normalized = [g.replace("left_", "") for g in gesture_list]
    return map_hand_actions("Left", normalized)

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
    # Build MediaPipe detector once and keep it alive for the run.
    logging.info("Initializing MediaPipe Hands (Legacy Mode)...")
    with mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=DETECTION_CONFIDENCE,
        min_tracking_confidence=TRACKING_CONFIDENCE,
        max_num_hands=2
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
                    # Total frame loop timing starts here.
                    frame_loop_t0 = time.perf_counter()
                    frame_index += 1
                    frame_t_start = None
                    if log_latency and latency_count < LATENCY_TRIALS:
                        # Measure end-to-end latency from frame capture through ViGEm output.
                        frame_t_start = time.perf_counter()

                    capture_t0 = time.perf_counter()
                    ret, frame = cap.read()
                    capture_t1 = time.perf_counter()
                    benchmark_stats["capture_s"] += (capture_t1 - capture_t0)
                    if not ret:
                        read_failed_count += 1
                        logging.error("Failed to receive frame.")
                        break
                    if visualise_mode and (cv2.waitKey(1) & 0xFF == ord('q')):
                        break

                    if benchmark_enabled and benchmark_capture_only:
                        # Capture-only mode intentionally skips processing/output.
                        benchmark_stats["frames"] += 1
                        benchmark_stats["total_s"] += (time.perf_counter() - frame_loop_t0)
                        if (time.perf_counter() - benchmark_start) >= benchmark_seconds:
                            break
                        await asyncio.sleep(0)
                        continue

                    preprocess_t0 = time.perf_counter()
                    # Mirror camera for natural interaction and optionally apply contrast/brightness.
                    frame = cv2.flip(frame, 1)
                    if PREPROCESS_CONTRAST_ENABLED:
                        frame = cv2.convertScaleAbs(
                            frame,
                            alpha=PREPROCESS_ALPHA,
                            beta=PREPROCESS_BETA,
                        )
                    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    rgb.flags.writeable = False
                    preprocess_t1 = time.perf_counter()
                    benchmark_stats["preprocess_s"] += (preprocess_t1 - preprocess_t0)

                    mediapipe_t0 = time.perf_counter()
                    # Hand landmark inference.
                    result = detector.process(rgb)
                    mediapipe_t1 = time.perf_counter()
                    benchmark_stats["mediapipe_s"] += (mediapipe_t1 - mediapipe_t0)
                    rgb.flags.writeable = True
                    capture_ms_frame = (capture_t1 - capture_t0) * 1000.0
                    preprocess_ms_frame = (preprocess_t1 - preprocess_t0) * 1000.0
                    mediapipe_ms_frame = (mediapipe_t1 - mediapipe_t0) * 1000.0

                    now = time.time()
                    # Instantaneous FPS + rolling 1-second FPS for smoother monitoring/logging.
                    dt  = now - prev_frame_time
                    fps = 1.0 / dt if dt > 0 else 0
                    prev_frame_time = now
                    frame_time_window.append(now)
                    while frame_time_window and (now - frame_time_window[0]) > 1.0:
                        frame_time_window.popleft()
                    if len(frame_time_window) >= 2:
                        rolling_window_s = frame_time_window[-1] - frame_time_window[0]
                        fps_rolling_1s = ((len(frame_time_window) - 1) / rolling_window_s) if rolling_window_s > 0 else fps
                    else:
                        fps_rolling_1s = fps

                    elapsed = now - calibration_start
                    if benchmark_enabled:
                        # Benchmark mode should measure steady-state processing, not startup calibration delay.
                        elapsed = CALIBRATION_DURATION
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
                        # Align pinch history length to detected hand count
                        n_hands = len(result.multi_hand_landmarks)
                        while len(prev_pinch_dists) < n_hands:
                            prev_pinch_dists.append(0.0)
                        prev_pinch_dists = prev_pinch_dists[:n_hands]

                        # Pre-pass: identify left/right wrist positions for inter-hand Y
                        left_lms = right_lms = None
                        for idx, h_obj in enumerate(result.multi_handedness):
                            lbl = h_obj.classification[0].label
                            lm  = result.multi_hand_landmarks[idx].landmark
                            if lbl == "Left":  left_lms  = lm
                            elif lbl == "Right": right_lms = lm

                        for i, hlp in enumerate(result.multi_hand_landmarks):
                            lm = hlp.landmark
                            hand_info = result.multi_handedness[i].classification[0]
                            handedness = hand_info.label
                            hand_confidence = hand_info.score

                            gesture_list = detect_gesture(lm, handedness)
                            # Convert abstract gesture labels to controller actions.
                            vigem_label  = map_to_vigem(gesture_list, handedness)

                            # Joystick X: hand tilt (wrist → middle MCP)
                            wrist  = lm[0]
                            mcp    = lm[9]
                            h_size = math.sqrt((mcp.x - wrist.x)**2 + (mcp.y - wrist.y)**2)
                            tilt_x = (mcp.x - wrist.x) / (h_size + 1e-6)
                            norm_x = tilt_x * TILT_GAIN

                            # Joystick Y: inter-hand angle (left hand) or tilt fallback
                            if handedness == "Left" and right_lms:
                                l_w, r_w = left_lms[0], right_lms[0]
                                dx = r_w.x - l_w.x
                                dy = r_w.y - l_w.y
                                
                                if abs(dx) < INTER_HAND_NEUTRAL_EPSILON and abs(dy) < INTER_HAND_NEUTRAL_EPSILON:
                                    norm_y = 0.0
                                else:
                                    angle = math.atan2(dy, dx)
                                    norm_y = -(angle / ANGLE_NORMALIZATION)
                            else:
                                tilt_y = (wrist.y - mcp.y) / (h_size + 1e-6)
                                norm_y = -(tilt_y - NEUTRAL_Y_OFFSET) * TILT_GAIN

                            # EMA smoothing: damps frame-to-frame jitter while preserving responsiveness.
                            # Per-hand state (keyed by index) prevents cross-hand bleed from shared state.
                            # Formula: smoothed = α × raw + (1-α) × previous
                            # α=0.3 balances smoothness vs latency (see Chapter 4 evaluation)
                            prev = ema_state.get(i, (0.0, 0.0))
                            a    = EMA_ALPHA
                            norm_x = a * norm_x + (1 - a) * prev[0]
                            norm_y = a * norm_y + (1 - a) * prev[1]
                            ema_state[i] = (norm_x, norm_y)

                            # Clamp to [-1.0, 1.0] controller range
                            norm_x = max(-1.0, min(1.0, norm_x))
                            norm_y = max(-1.0, min(1.0, norm_y))

                            # TODO: DEAD_ZONE defined in config.py but actual dead zone logic applied in
                            # vigem_output.py:apply_gesture(). Consolidate to single location post-evaluation
                            # to avoid confusion and potential duplicated logic.
                            
                            # Send mapped action(s) and analog values to virtual controller.
                            vigem_output.apply_gesture(vigem_label, handedness, norm_x, norm_y)

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
                                gest_str = ",".join(gesture_list)
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

                            gest_str = ",".join(gesture_list)
                            # Optional real-time telemetry for browser/client visualizations.
                            await broadcast({"x": norm_x, "y": norm_y,
                                             "gesture": gest_str, "hand": handedness})

                            disp_label = ",".join(vigem_label)
                            calculated_values['gestures'].append(disp_label)
                            calculated_values['handedness'].append(handedness)
                            calculated_values['wrist_coords'].append((norm_x, norm_y))

                            thumb, idx_tip = lm[4], lm[8]
                            p_dist = math.sqrt((idx_tip.x - thumb.x)**2 + (idx_tip.y - thumb.y)**2)
                            calculated_values['pinch_dists'].append(p_dist)
                            calculated_values['pinch_speeds'].append(abs(p_dist - prev_pinch_dists[i]))
                            prev_pinch_dists[i] = p_dist

                    else:
                        # No valid hand data: release controller and reset frame-local history state.
                        vigem_output.release_all()
                        prev_pinch_dists = []
                        ema_state.clear()
                    output_t1 = time.perf_counter()
                    benchmark_stats["output_s"] += (output_t1 - output_t0)
                    output_ms_frame = (output_t1 - output_t0) * 1000.0
                    loop_ms_frame = (time.perf_counter() - frame_loop_t0) * 1000.0
                    if pending_latency_rows and latency_writer is not None:
                        for base_row in pending_latency_rows:
                            latency_writer.writerow(base_row + [
                                f"{output_ms_frame:.2f}",
                                f"{loop_ms_frame:.2f}",
                                read_failed_count,
                            ])

                    if visualise_mode:
                        # Draw rich diagnostics overlay window when --visualise is enabled.
                        vis_lm = [hlp.landmark for hlp in (result.multi_hand_landmarks or [])]
                        annotated = visualiser.draw_overlay(frame, vis_lm, calculated_values)
                        cv2.imshow("MediaPipe Gesture Controller", annotated)

                    benchmark_stats["frames"] += 1
                    benchmark_stats["total_s"] += (time.perf_counter() - frame_loop_t0)
                    if benchmark_enabled and (time.perf_counter() - benchmark_start) >= benchmark_seconds:
                        break

                    await asyncio.sleep(0)
            finally:
                # Always release resources, even on errors/keyboard interrupt.
                cap.release()
                if visualise_mode:
                    cv2.destroyAllWindows()
                if latency_file_handle is not None:
                    latency_file_handle.close()

                if benchmark_enabled:
                    # Compute aggregate per-frame stats and append benchmark CSV row.
                    runtime_s = max(1e-9, time.perf_counter() - benchmark_start)
                    frames = benchmark_stats["frames"]
                    fps = frames / runtime_s
                    per_frame_ms = lambda s: (s / frames * 1000.0) if frames else 0.0
                    capture_ms = per_frame_ms(benchmark_stats["capture_s"])
                    preprocess_ms = per_frame_ms(benchmark_stats["preprocess_s"])
                    mediapipe_ms = per_frame_ms(benchmark_stats["mediapipe_s"])
                    output_ms = per_frame_ms(benchmark_stats["output_s"])
                    loop_total_ms = per_frame_ms(benchmark_stats["total_s"])

                    benchmark_dir = project_root / BENCHMARK_LOG_DIR
                    benchmark_dir.mkdir(parents=True, exist_ok=True)
                    benchmark_path = benchmark_dir / BENCHMARK_LOG_FILE
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
                    if benchmark_path.exists() and benchmark_path.stat().st_size > 0:
                        with benchmark_path.open("r", newline="") as f:
                            existing_header = f.readline().strip()
                        expected_header = ",".join(benchmark_header)
                        if existing_header != expected_header:
                            benchmark_path = benchmark_dir / "benchmark_runs_v2.csv"

                    benchmark_file_exists = benchmark_path.exists() and benchmark_path.stat().st_size > 0

                    with benchmark_path.open("a", newline="") as f:
                        writer = csv.writer(f)
                        if not benchmark_file_exists:
                            writer.writerow(benchmark_header)

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
    # CLI interface for runtime modes.
    parser = argparse.ArgumentParser(description="MediaPipe Gesture Controller")
    parser.add_argument("--visualise", action="store_true",
                        help="Enable rich visualisation overlay")
    parser.add_argument("--log-latency", action="store_true",
                        help="Log gesture latency to logs/latency/latency_log.csv")
    parser.add_argument("--benchmark-seconds", type=float, default=0.0,
                        help="Run benchmark for N seconds and print timing summary")
    parser.add_argument("--benchmark-capture-only", action="store_true",
                        help="Benchmark capture only (skip MediaPipe and output processing)")
    parser.add_argument("--run-tag", type=str, default="",
                        help="Optional run label for logs (e.g. native, camo, low-light)")
    args = parser.parse_args()
    try:
        asyncio.run(main(
            visualise_mode=args.visualise,
            log_latency=(LOG_LATENCY_DEFAULT or args.log_latency),
            benchmark_seconds=args.benchmark_seconds,
            benchmark_capture_only=args.benchmark_capture_only,
            run_tag=args.run_tag,
        ))
    except KeyboardInterrupt:
        logging.info("Program stopped by user.")