import cv2
import sys
import time
from unittest.mock import MagicMock
import numpy as np
import os
import urllib.request

# FORCE MOCK SOUNDDEVICE: Avoid PortAudio initialization error
sys.modules['sounddevice'] = MagicMock()

import mediapipe as mp
# Use the new Tasks API
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

import asyncio
import websockets
import json
import math

# Import the controller logic
import vigem_output

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
    if not connected_clients:
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
    hand_landmarks_list = detection_result.hand_landmarks
    annotated_image = np.copy(rgb_image)
    annotated_image = cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR)

    # Loop through the detected hands to visualize.
    for hand_landmarks in hand_landmarks_list:
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
async def main():
    # Ensure model exists
    model_path = os.path.join(SCRIPT_DIR, 'hand_landmarker.task')
    if not os.path.exists(model_path):
        print(f"Model '{model_path}' not found. Downloading...")
        url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
        urllib.request.urlretrieve(url, model_path)
        print("Download complete.")

    # Initialize Hand Landmarker
    base_options = python.BaseOptions(model_asset_path=model_path)
    options = vision.HandLandmarkerOptions(base_options=base_options,
                                           running_mode=vision.RunningMode.VIDEO,
                                           num_hands=2)
    
    detector = vision.HandLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"Error: Could not open camera index {CAMERA_INDEX}.")
        return

    # Start WebSocket Server
    print("Starting WebSocket server on ws://localhost:8765...")
    async with websockets.serve(websocket_handler, "localhost", 8765):
        print("Camera running. Press 'q' to quit.")
        
        start_time = time.time() * 1000

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("Failed to receive frame.")
                break

            # Check logic for 'q' key
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            # 1. Flip and Convert
            frame = cv2.flip(frame, 1) # Mirror
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # 2. Hand Tracking
            timestamp_ms = int(time.time() * 1000 - start_time)
            result = detector.detect_for_video(mp_image, timestamp_ms)

            # 3. Draw and Check Gestures
            annotated_image = draw_landmarks_on_image(rgb, result)
            
            if result.hand_landmarks:
                for i, hand_landmarks in enumerate(result.hand_landmarks):
                    # Get Handedness (Left or Right)
                    # MediaPipe returns a list of classifications, we take the first one
                    handedness = result.handedness[i][0].category_name
                    
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

                    # Send to Virtual Controller with Handedness
                    vigem_output.apply_gesture(vigem_label, handedness)

                    if gesture:
                        # Visual Feedback
                        cv2.putText(annotated_image, f"{handedness}: {gesture.upper()}", (50, 50 + i*40), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        # Send to Web Client
                        await broadcast({"gesture": gesture})
            else:
                # Release controller if no gesture is detected
                vigem_output.release_all()

            # Show the frame
            cv2.imshow("MediaPipe Gesture Controller", annotated_image)

            # Yield control to asyncio event loop (for websocket tasks)
            await asyncio.sleep(0.001)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
