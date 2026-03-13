import cv2
import sys
import time
import argparse
from unittest.mock import MagicMock
import numpy as np
import os
import urllib.request

# FORCE MOCK SOUNDDEVICE: Avoid PortAudio initialization error
sys.modules['sounddevice'] = MagicMock()

import mediapipe as mp
import asyncio
import websockets
import json
import math
import contextlib

WEBSOCKET_ENABLED = False

# Import the controller logic
import vigem_output
import visualiser

# MediaPipe Solutions (Legacy)
mp_hands = mp.solutions.hands

# Get the absolute path of the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load camera configuration
try:
    config_path = os.path.join(SCRIPT_DIR, "camera_config.txt")
    with open(config_path, "r") as f:
        camera_idx_str = f.read().strip()
        if not camera_idx_str:
             print("camera_config.txt is empty. Using default index 0.")
             CAMERA_INDEX = 0    
        else:
             CAMERA_INDEX = int(camera_idx_str)
    print(f"Loading Camera Index {CAMERA_INDEX} from {config_path}...")
except FileNotFoundError:
    print("Error: 'camera_config.txt' not found.")
    print("Please run 'python src/find_camera.py' first to select your camera.")
    sys.exit()
except ValueError:
    print("Error: Invalid camera index. Using default 0.")
    CAMERA_INDEX = 0

# ----------------------------------------------------------------
# WebSocket Server Global State
# ----------------------------------------------------------------
connected_clients = set()

async def websocket_handler(websocket):
    print(f"New client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        print(f"Client disconnected: {websocket.remote_address}")

async def broadcast(message_dict):
    if not WEBSOCKET_ENABLED or not connected_clients:
        return
    message_str = json.dumps(message_dict)
    # Broadcast to all connected clients
    to_remove = set()
    for client in connected_clients:
        try:
            await client.send(message_str)
        except websockets.exceptions.ConnectionClosed:
            to_remove.add(client)
    
    connected_clients.difference_update(to_remove)

# ----------------------------------------------------------------
# Drawing Utilities
# ----------------------------------------------------------------
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17)
]

def draw_landmarks_on_image(rgb_image, detection_result):
    hand_landmarks_list = detection_result.multi_hand_landmarks if detection_result.multi_hand_landmarks else []
    annotated_image = np.copy(rgb_image)
    annotated_image = cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR)

    # Loop through the detected hands to visualize.
    for hand_landmarks_proto in hand_landmarks_list:
        hand_landmarks = hand_landmarks_proto.landmark
        # Draw the landmarks.
        for landmark in hand_landmarks:
             x = int(landmark.x * annotated_image.shape[1])
             y = int(landmark.y * annotated_image.shape[0])
             cv2.circle(annotated_image, (x, y), 5, (0, 255, 0), -1)
        
        # Draw the connections
        for connection in HAND_CONNECTIONS:
            start_idx = connection[0]
            end_idx = connection[1]
            start_point = hand_landmarks[start_idx]
            end_point = hand_landmarks[end_idx]
            
            start_x = int(start_point.x * annotated_image.shape[1])
            start_y = int(start_point.y * annotated_image.shape[0])
            end_x = int(end_point.x * annotated_image.shape[1])
            end_y = int(end_point.y * annotated_image.shape[0])
            
            cv2.line(annotated_image, (start_x, start_y), (end_x, end_y), (0, 255, 0), 2)
            
    return annotated_image

# ----------------------------------------------------------------
# Gesture Detection Logic
# ----------------------------------------------------------------
def detect_gesture(landmarks):
    # Tip of Index Finger
    index_tip = landmarks[8]
    index_pip = landmarks[6]
    # Tip of Thumb
    thumb_tip = landmarks[4]
    # Wrist
    wrist = landmarks[0]
    
    # Other fingers for pose detection
    middle_tip = landmarks[12]
    middle_pip = landmarks[10]
    ring_tip = landmarks[16]
    ring_pip = landmarks[14]
    pinky_tip = landmarks[20]
    pinky_pip = landmarks[18]

    # Calculate distance for Pinch gesture
    pinch_dist = math.sqrt(
        (index_tip.x - thumb_tip.x)**2 + 
        (index_tip.y - thumb_tip.y)**2
    )

    # 1. PINCH (High Priority)
    if pinch_dist < 0.05:
        return "select"

    # 2. SCREEN EDGES (Navigation / Swipes)
    # Check these before poses so you can move while holding a pose, 
    # or prioritize movement at edges.
    if wrist.x < 0.2: return "right"
    if wrist.x > 0.8: return "left"
    if wrist.y < 0.2: return "forward"
    if wrist.y > 0.8: return "back"

    # 3. POSE DETECTION
    # Check if fingers are open (Tip Y < PIP Y means finger is pointing UP)
    index_open = index_tip.y < index_pip.y
    middle_open = middle_tip.y < middle_pip.y
    ring_open = ring_tip.y < ring_pip.y
    pinky_open = pinky_tip.y < pinky_pip.y
    
    fingers_open = sum([index_open, middle_open, ring_open, pinky_open])

    # Thumb Up: Thumb tip is significantly above Index PIP (and other fingers closed)
    thumb_is_up = thumb_tip.y < index_pip.y - 0.05

    if fingers_open == 0:
        if thumb_is_up: return "thumb_up"
        return "fist"
    
    if fingers_open == 1 and index_open: return "point"
    if fingers_open == 2 and index_open and middle_open: return "victory"
    if fingers_open == 4: return "open"

    return None

# ----------------------------------------------------------------
# Main Loop (Async)
# ----------------------------------------------------------------
async def main(visualise_mode=False):
    print("Initializing MediaPipe Hands (Legacy Mode)...")
    
    # Initialize Legacy Hand Landmarker with Lite Model (model_complexity=0)
    # min_detection_confidence and min_tracking_confidence set to defaults or user pref
    with mp_hands.Hands(
        model_complexity=0, # 0=Lite, 1=Full
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        max_num_hands=2
    ) as detector:

        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            print(f"Error: Could not open camera index {CAMERA_INDEX}.")
            return

        # Initialize State Variables
        calibration_start_time = time.time()
        prev_frame_time = time.time()
        previous_pinch_dists = [] # List to store previous pinch dist per hand

        # Start WebSocket Server
        if WEBSOCKET_ENABLED:
            print("Starting WebSocket server on ws://localhost:8765...")
            server_cm = websockets.serve(websocket_handler, "localhost", 8765)
        else:
            print("WebSocket server disabled.")
            server_cm = contextlib.nullcontext()

        async with server_cm:
            print("Camera running. Press 'q' to quit.")
            
            # Start time not needed for Legacy process() which is synchronous/static image
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("Failed to receive frame.")
                    break

                # Check logic for 'q' key
                if visualise_mode and (cv2.waitKey(1) & 0xFF == ord('q')):
                    break

                # 1. Flip and Convert
                frame = cv2.flip(frame, 1) # Mirror
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 2. Hand Tracking (Legacy)
                # To improve performance, optionally mark the image as not writeable to pass by reference.
                rgb.flags.writeable = False
                result = detector.process(rgb)
                rgb.flags.writeable = True

                # FPS Calculation
                curr_frame_time_sec = time.time()
                dt = curr_frame_time_sec - prev_frame_time
                fps = 1.0 / dt if dt > 0 else 0
                prev_frame_time = curr_frame_time_sec
                
                # Calibration Status (first 3 seconds)
                calibration_elapsed = curr_frame_time_sec - calibration_start_time
                is_calibrating = calibration_elapsed < 3.0
                
                calculated_values = {
                    'fps': fps,
                    'calibration_status': "calibrating" if is_calibrating else "calibrated",
                    'calibration_time_remain': max(0, 3.0 - calibration_elapsed),
                    'gestures': [],
                    'handedness': [],
                    'pinch_dists': [],
                    'pinch_speeds': [],
                    'wrist_coords': []
                }
                
                if result.multi_hand_landmarks:
                    # Ensure previous_pinch_dists is large enough
                    while len(previous_pinch_dists) < len(result.multi_hand_landmarks):
                        previous_pinch_dists.append(0.0)
                    
                    # Truncate if fewer hands
                    previous_pinch_dists = previous_pinch_dists[:len(result.multi_hand_landmarks)]

                    for i, hand_landmarks_proto in enumerate(result.multi_hand_landmarks):
                        # Convert protobuf landmarks to list for easier access if necessary, 
                        # but your existing code uses property access .x .y which works on protobuf too.
                        # However, structure is a bit different.
                        # The 'hand_landmarks' in Tasks API was a list of NormalizedLandmark objects.
                        # Here 'hand_landmarks_proto' is a NormalizedLandmarkList.
                        # We can iterate it directly.
                        hand_landmarks = hand_landmarks_proto.landmark

                        # Get Handedness (Left or Right)
                        # Legacy returns 'multi_handedness'.
                        # Note: Legacy API output for 'Left' means it appears on left side? 
                        # Actually 'Left' label usually corresponds to 'Left Hand'.
                        # MediaPipe Hands classification is:
                        # Label: "Left" means left hand.
                        # But input image is mirrored?
                        # Let's rely on the label MediaPipe gives.
                        handedness_obj = result.multi_handedness[i]
                        handedness = handedness_obj.classification[0].label
                        
                        # Detect Gesture (returns 'right', 'left', 'select', etc.)
                        gesture = detect_gesture(hand_landmarks)
                        
                        # Map to ViGEm command labels
                        vigem_label = "OPEN_PALM" # Default neutral state
                        if gesture == "select": vigem_label = "PINCH"
                        elif gesture == "fist": vigem_label = "CLOSED_FIST"
                        elif gesture == "open": vigem_label = "OPEN_PALM"
                        elif gesture == "point": vigem_label = "POINTING_UP"
                        elif gesture == "victory": vigem_label = "VICTORY"
                        elif gesture == "thumb_up": vigem_label = "THUMB_UP"
                        elif gesture == "right": vigem_label = "SWIPE_RIGHT"
                        elif gesture == "left": vigem_label = "SWIPE_LEFT"
                        elif gesture == "forward": vigem_label = "SWIPE_UP"
                        elif gesture == "back": vigem_label = "SWIPE_DOWN"

                        # Get Wrist for X/Y Control
                        wrist = hand_landmarks[0]
                        # Normalize to -1.0 to 1.0
                        # x: 0 (left) -> -1.0, 1 (right) -> 1.0
                        norm_x = (wrist.x - 0.5) * 2
                        # y: 0 (top) -> 1.0, 1 (bottom) -> -1.0 (Inverted for Joystick Up/Forward)
                        norm_y = -(wrist.y - 0.5) * 2

                        # Send to Virtual Controller with Handedness & Coords
                        vigem_output.apply_gesture(vigem_label, handedness, norm_x, norm_y)

                        if gesture:
                            # Send to Web Client
                            await broadcast({
                                "x": norm_x,
                                "y": norm_y,
                                "gesture": gesture,
                                "hand": handedness
                            })
                        
                        # Store values for Visualizer
                        calculated_values['gestures'].append(vigem_label)
                        calculated_values['handedness'].append(handedness)
                        calculated_values['wrist_coords'].append((norm_x, norm_y))
                        
                        # Calculate Pinch Distance & Speed
                        thumb_tip = hand_landmarks[4]
                        index_tip = hand_landmarks[8]
                        pinch_dist = math.sqrt((index_tip.x - thumb_tip.x)**2 + (index_tip.y - thumb_tip.y)**2)
                        
                        prev_p = previous_pinch_dists[i]
                        pinch_speed = abs(pinch_dist - prev_p)
                        previous_pinch_dists[i] = pinch_dist
                        
                        calculated_values['pinch_dists'].append(pinch_dist)
                        calculated_values['pinch_speeds'].append(pinch_speed)

                else:
                    # Release controller if no gesture is detected
                    vigem_output.release_all()
                    previous_pinch_dists = []

                # 3. Draw Overlays
                if visualise_mode:
                    # The visualiser expects a list of hand landmarks lists
                    # Adapting result.multi_hand_landmarks to expected format if needed
                    # Tasks API format: list of lists of landmarks
                    # Legacy: list of NormalizedLandmarkList
                    # We need to extract .landmark list from each
                    vis_landmarks = []
                    if result.multi_hand_landmarks:
                        for hl in result.multi_hand_landmarks:
                            vis_landmarks.append(hl.landmark)
                    
                    # Use new comprehensive visualizer
                    annotated_image = visualiser.draw_overlay(frame, vis_landmarks, calculated_values)
                    # Show the frame
                    cv2.imshow("MediaPipe Gesture Controller", annotated_image)

                # Yield control to asyncio event loop (for websocket tasks)
                await asyncio.sleep(0.001)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MediaPipe Gesture Controller")
    parser.add_argument("--visualise", action="store_true", help="Enable rich visualisation overlay")
    args = parser.parse_args()
    
    try:
        asyncio.run(main(visualise_mode=args.visualise))
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
