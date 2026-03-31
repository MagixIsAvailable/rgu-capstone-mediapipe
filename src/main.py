"""
Module: main.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Entry point for the VisionInput application. Captures webcam frames via OpenCV, processes hand landmarks using the MediaPipe Legacy Hands API, detects gestures using heuristic geometric analysis, applies EMA smoothing and dead zone logic, and dispatches controller outputs via vigem_output. Optionally runs a WebSocket server for browser-based visualisation and a debug overlay via visualiser.

Dependencies:
mediapipe, cv2, asyncio, websockets, vigem_output, visualiser

Usage:
python src/main.py or python src/main.py --visualise
"""
import cv2
import sys
import time
import csv
import argparse
import logging
from unittest.mock import MagicMock
import numpy as np
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

sys.modules['sounddevice'] = MagicMock()

import mediapipe as mp
import asyncio
import websockets
import json
import math
import contextlib

# ----------------------------------------------------------------
# CONFIG — all tunables in one place
# ----------------------------------------------------------------
CONFIG = {
    "WEBSOCKET_ENABLED": False,
    "SENSITIVITY": 2.0,          # Interaction box size (higher = less movement required)
    "TILT_GAIN": 4.0,             # ~15° tilt = full stick input
    "NEUTRAL_Y_OFFSET": 0.65,    # ⚠ TUNE THIS: read tilt_y at rest from --visualise overlay
    "EMA_ALPHA": 0.3,             # Smoothing factor (0=no update, 1=no smoothing)
    "DEAD_ZONE": 0.15,            # Applied in vigem_output, documented here for reference
    "PINCH_INDEX":  0.05,
    "PINCH_MIDDLE": 0.06,
    "PINCH_RING":   0.07,
    "PINCH_PINKY":  0.08,
    "CALIBRATION_DURATION": 3.0, # Seconds before controller output is enabled
    "log_latency": False,         # Enable with --log-latency flag
    "latency_trials": 200,         # Stop logging after N trials
    "latency_log_dir": "logs/latency",
    "latency_log_file": "latency_log.csv",
    "benchmark_log_dir": "logs/benchmark",
    "benchmark_log_file": "benchmark_runs.csv",
}

WEBSOCKET_ENABLED = CONFIG["WEBSOCKET_ENABLED"]

import vigem_output
import visualiser

mp_hands = mp.solutions.hands
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------
# Camera config
# ----------------------------------------------------------------
try:
    config_path = os.path.join(SCRIPT_DIR, "camera_config.txt")
    with open(config_path, "r") as f:
        content = f.read().strip()
        CAMERA_LABEL = f"camera_index_0"
        if not content:
            CAMERA_INDEX = 0
            logging.warning("camera_config.txt is empty. Using default index 0.")
        elif content.startswith("{"):
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
    if len(connected_clients) >= 5:
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

# ----------------------------------------------------------------
# Drawing utilities
# ----------------------------------------------------------------
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),(0,17)
]

def draw_landmarks_on_image(rgb_image, detection_result):
    hand_landmarks_list = detection_result.multi_hand_landmarks or []
    annotated = np.copy(rgb_image)
    annotated = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
    h, w, _ = annotated.shape
    half = (1.0 / CONFIG["SENSITIVITY"]) / 2
    x1, y1 = int((0.5 - half) * w), int((0.5 - half) * h)
    x2, y2 = int((0.5 + half) * w), int((0.5 + half) * h)
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
    for hlp in hand_landmarks_list:
        lm = hlp.landmark
        for l in lm:
            cv2.circle(annotated, (int(l.x * w), int(l.y * h)), 5, (0, 255, 0), -1)
        for s, e in HAND_CONNECTIONS:
            cv2.line(annotated,
                     (int(lm[s].x * w), int(lm[s].y * h)),
                     (int(lm[e].x * w), int(lm[e].y * h)),
                     (0, 255, 0), 2)
        wrist, mcp = lm[0], lm[9]
        cv2.arrowedLine(annotated,
                        (int(wrist.x * w), int(wrist.y * h)),
                        (int(mcp.x * w),   int(mcp.y * h)),
                        (255, 255, 0), 3, tipLength=0.3)
    return annotated

# ----------------------------------------------------------------
# Gesture detection — always returns list[str]
# ----------------------------------------------------------------
def detect_gesture(landmarks, handedness="Left") -> list[str]:
    """
    Returns a list of gesture label strings.
    Single-gesture results are still returned as a one-element list.
    Neutral state returns ["OPEN_PALM"].
    """
    def dist(a, b):
        return math.dist((a.x, a.y), (b.x, b.y))

    if handedness == "Right":
        thumb = landmarks[4]
        # Layer B: pinch (priority — mutually exclusive)
        if dist(landmarks[8],  thumb) < CONFIG["PINCH_INDEX"]:  return ["index_pinch"]
        if dist(landmarks[12], thumb) < CONFIG["PINCH_MIDDLE"]: return ["middle_pinch"]
        if dist(landmarks[16], thumb) < CONFIG["PINCH_RING"]:   return ["ring_pinch"]
        if dist(landmarks[20], thumb) < CONFIG["PINCH_PINKY"]:  return ["pinky_pinch"]
        # Layer A: individual bends (combinable)
        bends = []
        if landmarks[8].y  > landmarks[6].y:  bends.append("index_bent")
        if landmarks[12].y > landmarks[10].y: bends.append("middle_bent")
        if landmarks[16].y > landmarks[14].y: bends.append("ring_bent")
        if landmarks[20].y > landmarks[18].y: bends.append("pinky_bent")
        return bends if bends else ["OPEN_PALM"]

    # Left hand — modified for D-pad control (as requested)
    # Layer: individual bends (combinable, identical logic to Right hand)
    bends = []
    if landmarks[8].y  > landmarks[6].y:  bends.append("left_index_bent")
    if landmarks[12].y > landmarks[10].y: bends.append("left_middle_bent")
    if landmarks[16].y > landmarks[14].y: bends.append("left_ring_bent")
    if landmarks[20].y > landmarks[18].y: bends.append("left_pinky_bent")
    
    return bends if bends else ["OPEN_PALM"]

# ----------------------------------------------------------------
# Gesture → ViGEm label mapping
# ----------------------------------------------------------------
_LEFT_GESTURE_MAP = {
    "left_index_bent":   "DPAD_UP",
    "left_middle_bent":  "DPAD_DOWN",
    "left_ring_bent":    "DPAD_LEFT",
    "left_pinky_bent":   "DPAD_RIGHT",
    "select":  "PINCH",
    "fist":    "CLOSED_FIST",
    "open":    "OPEN_PALM",
    "point":   "POINTING_UP",
    "victory": "VICTORY",
    "thumb_up":"THUMB_UP",
    "right":   "SWIPE_RIGHT",
    "left":    "SWIPE_LEFT",
    "forward": "SWIPE_UP",
    "back":    "SWIPE_DOWN",
}

def map_to_vigem(gesture_list: list[str], handedness: str) -> list[str]:
    if handedness == "Right":
        gests = set(gesture_list)
        # Combo detection (priority)
        if "index_bent" in gests and "middle_bent" in gests:
            return ["BUTTON_7"]
        if "index_bent" in gests and "ring_bent" in gests:
            return ["BUTTON_8"]
        
        # Single mapping
        mapping = {
            "index_bent":   "BUTTON_1",
            "middle_bent":  "BUTTON_2",
            "ring_bent":    "BUTTON_3",
            "pinky_bent":   "BUTTON_4",
            "index_pinch":  "BUTTON_5",
            "middle_pinch": "BUTTON_6",
            "ring_pinch":   "TRIGGER_LT",
            "pinky_pinch":  "TRIGGER_RT",
            "OPEN_PALM":    "NEUTRAL"
        }
        res = [mapping[g] for g in gesture_list if g in mapping]
        return res if res else ["NEUTRAL"]
        
    return [_LEFT_GESTURE_MAP.get(g, "OPEN_PALM") for g in gesture_list]

# ----------------------------------------------------------------
# Main loop (async)
# ----------------------------------------------------------------
async def main(
    visualise_mode=False,
    log_latency=False,
    benchmark_seconds=0.0,
    benchmark_capture_only=False,
):
    logging.info("Initializing MediaPipe Hands (Legacy Mode)...")
    with mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        max_num_hands=2
    ) as detector:
        cap = cv2.VideoCapture(CAMERA_INDEX)
        # Request 60 FPS (many webcams require MJPG for >30fps at high res)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
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

        # EMA state keyed by hand index — fixes cross-hand bleed
        ema_state = {}

        server_cm = (
            websockets.serve(websocket_handler, "localhost", 8765)
            if WEBSOCKET_ENABLED else contextlib.nullcontext()
        )

        async with server_cm:
            if WEBSOCKET_ENABLED:
                logging.info("WebSocket server running on ws://localhost:8765")
            logging.info("Camera running. Press 'q' to quit.")

            latency_count = 0
            project_root = Path(SCRIPT_DIR).parent
            latency_dir = project_root / CONFIG["latency_log_dir"]
            latency_dir.mkdir(parents=True, exist_ok=True)
            session_created_at = time.strftime("%Y-%m-%d %H:%M:%S")
            session_file_stamp = time.strftime("%Y%m%d_%H%M%S")
            latency_path = latency_dir / f"latency_log_{session_file_stamp}.csv"
            latency_file_handle = None
            latency_writer = None
            if log_latency:
                latency_file_handle = latency_path.open("w", newline="")
                latency_writer = csv.writer(latency_file_handle)
                # Write run metadata once to avoid duplicating static values per event row.
                latency_writer.writerow(["session_created_at", session_created_at])
                latency_writer.writerow(["camera_label", CAMERA_LABEL])
                latency_writer.writerow(["camera_resolution", camera_resolution])
                latency_writer.writerow([])
                latency_writer.writerow([
                    "timestamp",
                    "gesture_label",
                    "hand",
                    "latency_ms",
                ])

            try:
                while cap.isOpened():
                    frame_loop_t0 = time.perf_counter()
                    frame_t_start = None
                    if log_latency and latency_count < CONFIG["latency_trials"]:
                        # Measure end-to-end latency from frame capture through ViGEm output.
                        frame_t_start = time.perf_counter()

                    capture_t0 = time.perf_counter()
                    ret, frame = cap.read()
                    capture_t1 = time.perf_counter()
                    benchmark_stats["capture_s"] += (capture_t1 - capture_t0)
                    if not ret:
                        logging.error("Failed to receive frame.")
                        break
                    if visualise_mode and (cv2.waitKey(1) & 0xFF == ord('q')):
                        break

                    if benchmark_enabled and benchmark_capture_only:
                        benchmark_stats["frames"] += 1
                        benchmark_stats["total_s"] += (time.perf_counter() - frame_loop_t0)
                        if (time.perf_counter() - benchmark_start) >= benchmark_seconds:
                            break
                        await asyncio.sleep(0)
                        continue

                    preprocess_t0 = time.perf_counter()
                    frame = cv2.flip(frame, 1)
                    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    rgb.flags.writeable = False
                    preprocess_t1 = time.perf_counter()
                    benchmark_stats["preprocess_s"] += (preprocess_t1 - preprocess_t0)

                    mediapipe_t0 = time.perf_counter()
                    result = detector.process(rgb)
                    mediapipe_t1 = time.perf_counter()
                    benchmark_stats["mediapipe_s"] += (mediapipe_t1 - mediapipe_t0)
                    rgb.flags.writeable = True

                    now = time.time()
                    dt  = now - prev_frame_time
                    fps = 1.0 / dt if dt > 0 else 0
                    prev_frame_time = now

                    elapsed = now - calibration_start
                    if benchmark_enabled:
                        # Benchmark mode should measure steady-state processing, not startup calibration delay.
                        elapsed = CONFIG["CALIBRATION_DURATION"]
                    is_calibrating = elapsed < CONFIG["CALIBRATION_DURATION"]

                    calculated_values = {
                        'fps': fps,
                        'calibration_status': "calibrating" if is_calibrating else "calibrated",
                        'calibration_time_remain': max(0, CONFIG["CALIBRATION_DURATION"] - elapsed),
                        'gestures': [], 'handedness': [],
                        'pinch_dists': [], 'pinch_speeds': [], 'wrist_coords': []
                    }

                    output_t0 = time.perf_counter()
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
                            lm         = hlp.landmark
                            handedness = result.multi_handedness[i].classification[0].label

                            gesture_list = detect_gesture(lm, handedness)
                            vigem_label  = map_to_vigem(gesture_list, handedness)

                            # Joystick X: hand tilt (wrist → middle MCP)
                            wrist  = lm[0]
                            mcp    = lm[9]
                            h_size = math.sqrt((mcp.x - wrist.x)**2 + (mcp.y - wrist.y)**2)
                            tilt_x = (mcp.x - wrist.x) / (h_size + 1e-6)
                            norm_x = tilt_x * CONFIG["TILT_GAIN"]

                            # Joystick Y: inter-hand angle (left hand) or tilt fallback
                            if handedness == "Left" and right_lms:
                                l_w, r_w = left_lms[0], right_lms[0]
                                dx = r_w.x - l_w.x
                                dy = r_w.y - l_w.y
                                
                                if abs(dx) < 0.05 and abs(dy) < 0.05:
                                    norm_y = 0.0
                                else:
                                    angle = math.atan2(dy, dx)
                                    # Sensitivity: Normalize against ~36 degrees (pi/5)
                                    norm_y = -(angle / (math.pi / 5))
                            else:
                                tilt_y = (wrist.y - mcp.y) / (h_size + 1e-6)
                                norm_y = -(tilt_y - CONFIG["NEUTRAL_Y_OFFSET"]) * CONFIG["TILT_GAIN"]

                            # Per-hand EMA (fixes shared-state bug)
                            prev = ema_state.get(i, (0.0, 0.0))
                            a    = CONFIG["EMA_ALPHA"]
                            norm_x = a * norm_x + (1 - a) * prev[0]
                            norm_y = a * norm_y + (1 - a) * prev[1]
                            ema_state[i] = (norm_x, norm_y)

                            norm_x = max(-1.0, min(1.0, norm_x))
                            norm_y = max(-1.0, min(1.0, norm_y))

                            vigem_output.apply_gesture(vigem_label, handedness, norm_x, norm_y)

                            is_non_neutral = any(g != "OPEN_PALM" for g in gesture_list)
                            should_log_latency = (
                                frame_t_start is not None
                                and is_non_neutral
                                and latency_count < CONFIG["latency_trials"]
                            )
                            if should_log_latency and latency_writer is not None:
                                t_end = time.perf_counter()
                                latency_ms = (t_end - frame_t_start) * 1000
                                gest_str = ",".join(gesture_list)
                                latency_writer.writerow([
                                    time.strftime("%H:%M:%S"),
                                    gest_str,
                                    handedness.lower(),
                                    f"{latency_ms:.2f}",
                                ])

                                latency_count += 1
                                if latency_count == CONFIG["latency_trials"]:
                                    saved_path = latency_path.resolve()
                                    print(
                                        f"\nLatency logging complete - {CONFIG['latency_trials']} trials saved to {saved_path}"
                                    )

                            gest_str = ",".join(gesture_list)
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
                        vigem_output.release_all()
                        prev_pinch_dists = []
                        ema_state.clear()
                    output_t1 = time.perf_counter()
                    benchmark_stats["output_s"] += (output_t1 - output_t0)

                    if visualise_mode:
                        vis_lm = [hlp.landmark for hlp in (result.multi_hand_landmarks or [])]
                        annotated = visualiser.draw_overlay(frame, vis_lm, calculated_values)
                        cv2.imshow("MediaPipe Gesture Controller", annotated)

                    benchmark_stats["frames"] += 1
                    benchmark_stats["total_s"] += (time.perf_counter() - frame_loop_t0)
                    if benchmark_enabled and (time.perf_counter() - benchmark_start) >= benchmark_seconds:
                        break

                    await asyncio.sleep(0)
            finally:
                cap.release()
                if visualise_mode:
                    cv2.destroyAllWindows()
                if latency_file_handle is not None:
                    latency_file_handle.close()

                if benchmark_enabled:
                    runtime_s = max(1e-9, time.perf_counter() - benchmark_start)
                    frames = benchmark_stats["frames"]
                    fps = frames / runtime_s
                    per_frame_ms = lambda s: (s / frames * 1000.0) if frames else 0.0
                    capture_ms = per_frame_ms(benchmark_stats["capture_s"])
                    preprocess_ms = per_frame_ms(benchmark_stats["preprocess_s"])
                    mediapipe_ms = per_frame_ms(benchmark_stats["mediapipe_s"])
                    output_ms = per_frame_ms(benchmark_stats["output_s"])
                    loop_total_ms = per_frame_ms(benchmark_stats["total_s"])

                    benchmark_dir = project_root / CONFIG["benchmark_log_dir"]
                    benchmark_dir.mkdir(parents=True, exist_ok=True)
                    benchmark_path = benchmark_dir / CONFIG["benchmark_log_file"]
                    benchmark_file_exists = benchmark_path.exists() and benchmark_path.stat().st_size > 0

                    with benchmark_path.open("a", newline="") as f:
                        writer = csv.writer(f)
                        if not benchmark_file_exists:
                            writer.writerow([
                                "timestamp",
                                "camera_label",
                                "camera_resolution",
                                "mode",
                                "duration_s",
                                "frames",
                                "fps",
                                "capture_ms_per_frame",
                                "preprocess_ms_per_frame",
                                "mediapipe_ms_per_frame",
                                "output_ms_per_frame",
                                "loop_total_ms_per_frame",
                            ])

                        writer.writerow([
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                            CAMERA_LABEL,
                            camera_resolution,
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
    parser = argparse.ArgumentParser(description="MediaPipe Gesture Controller")
    parser.add_argument("--visualise", action="store_true",
                        help="Enable rich visualisation overlay")
    parser.add_argument("--log-latency", action="store_true",
                        help="Log gesture latency to logs/latency/latency_log.csv")
    parser.add_argument("--benchmark-seconds", type=float, default=0.0,
                        help="Run benchmark for N seconds and print timing summary")
    parser.add_argument("--benchmark-capture-only", action="store_true",
                        help="Benchmark capture only (skip MediaPipe and output processing)")
    args = parser.parse_args()
    try:
        asyncio.run(main(
            visualise_mode=args.visualise,
            log_latency=(CONFIG["log_latency"] or args.log_latency),
            benchmark_seconds=args.benchmark_seconds,
            benchmark_capture_only=args.benchmark_capture_only,
        ))
    except KeyboardInterrupt:
        logging.info("Program stopped by user.")