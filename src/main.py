import cv2
import sys
import time
import argparse
from unittest.mock import MagicMock
import numpy as np
import os

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
        CAMERA_INDEX = int(content) if content else 0
        if not content:
            print("camera_config.txt is empty. Using default index 0.")
    print(f"Loading Camera Index {CAMERA_INDEX} from {config_path}...")
except FileNotFoundError:
    print("Error: 'camera_config.txt' not found.")
    print("Please run 'python src/setup_camera.py' first to select your camera.")
    input("Press Enter to exit...")
    sys.exit()
except ValueError:
    print("Error: Invalid camera index in camera_config.txt. Using default 0.")
    CAMERA_INDEX = 3

# ----------------------------------------------------------------
# WebSocket
# ----------------------------------------------------------------
connected_clients = set()

async def websocket_handler(websocket):
    print(f"New client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        print(f"Client disconnected: {websocket.remote_address}")

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
        return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2)

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

    # Left hand — classic navigation logic
    index_tip, index_pip = landmarks[8],  landmarks[6]
    thumb_tip             = landmarks[4]
    middle_tip, middle_pip = landmarks[12], landmarks[10]
    ring_tip,   ring_pip   = landmarks[16], landmarks[14]
    pinky_tip,  pinky_pip  = landmarks[20], landmarks[18]
    wrist                  = landmarks[0]

    if dist(index_tip, thumb_tip) < 0.05: return ["select"]
    if wrist.x < 0.2: return ["right"]
    if wrist.x > 0.8: return ["left"]
    if wrist.y < 0.2: return ["forward"]
    if wrist.y > 0.8: return ["back"]

    fingers_open = sum([
        index_tip.y  < index_pip.y,
        middle_tip.y < middle_pip.y,
        ring_tip.y   < ring_pip.y,
        pinky_tip.y  < pinky_pip.y,
    ])
    thumb_is_up = thumb_tip.y < index_pip.y - 0.05

    if fingers_open == 0:
        return ["thumb_up"] if thumb_is_up else ["fist"]
    if fingers_open == 1 and index_tip.y < index_pip.y:  return ["point"]
    if fingers_open == 2 and index_tip.y < index_pip.y \
                         and middle_tip.y < middle_pip.y: return ["victory"]
    if fingers_open == 4: return ["open"]
    return ["OPEN_PALM"]

# ----------------------------------------------------------------
# Gesture → ViGEm label mapping
# ----------------------------------------------------------------
_LEFT_GESTURE_MAP = {
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
async def main(visualise_mode=False):
    print("Initializing MediaPipe Hands (Legacy Mode)...")
    with mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        max_num_hands=2
    ) as detector:
        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            print("Run 'python src/setup_camera.py' to fix this.")
            input("Press Enter to exit...")
            print(f"Error: Could not open camera index {CAMERA_INDEX}.")
            return

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
                print("WebSocket server running on ws://localhost:8765")
            print("Camera running. Press 'q' to quit.")

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("Failed to receive frame.")
                    break
                if visualise_mode and (cv2.waitKey(1) & 0xFF == ord('q')):
                    break

                frame = cv2.flip(frame, 1)
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = detector.process(rgb)
                rgb.flags.writeable = True

                now = time.time()
                dt  = now - prev_frame_time
                fps = 1.0 / dt if dt > 0 else 0
                prev_frame_time = now

                elapsed       = now - calibration_start
                is_calibrating = elapsed < CONFIG["CALIBRATION_DURATION"]

                calculated_values = {
                    'fps': fps,
                    'calibration_status': "calibrating" if is_calibrating else "calibrated",
                    'calibration_time_remain': max(0, CONFIG["CALIBRATION_DURATION"] - elapsed),
                    'gestures': [], 'handedness': [],
                    'pinch_dists': [], 'pinch_speeds': [], 'wrist_coords': []
                }

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

                if visualise_mode:
                    vis_lm = [hlp.landmark for hlp in (result.multi_hand_landmarks or [])]
                    annotated = visualiser.draw_overlay(frame, vis_lm, calculated_values)
                    cv2.imshow("MediaPipe Gesture Controller", annotated)

                await asyncio.sleep(0.001)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MediaPipe Gesture Controller")
    parser.add_argument("--visualise", action="store_true",
                        help="Enable rich visualisation overlay")
    args = parser.parse_args()
    try:
        asyncio.run(main(visualise_mode=args.visualise))
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")