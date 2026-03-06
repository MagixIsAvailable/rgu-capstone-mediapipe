import cv2
import sys
import mediapipe as mp
import asyncio
import websockets
import json
import math

print(f"DEBUG: MediaPipe loaded from: {mp.__file__}")

# Initialise MediaPipe Hands
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Load camera configuration
try:
    with open("camera_config.txt", "r") as f:
        camera_idx_str = f.read().strip()
        if not camera_idx_str:
             print("camera_config.txt is empty. Using default index 0.")
             CAMERA_INDEX = 0    
        else:
             CAMERA_INDEX = int(camera_idx_str)
    print(f"Loading Camera Index {CAMERA_INDEX} from camera_config.txt...")
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
# Gesture Detection Logic
# ----------------------------------------------------------------
def detect_gesture(landmarks):
    # Tip of Index Finger
    index_tip = landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
    # Tip of Thumb
    thumb_tip = landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
    # Wrist
    wrist = landmarks.landmark[mp_hands.HandLandmark.WRIST]

    # Calculate distance for Pinch gesture
    pinch_dist = math.sqrt(
        (index_tip.x - thumb_tip.x)**2 + 
        (index_tip.y - thumb_tip.y)**2
    )

    # Simple logic mapping screen areas to commands
    # Normalized coordinates: (0,0) top-left, (1,1) bottom-right

    gesture = None

    if pinch_dist < 0.05:
        gesture = "select"
    elif wrist.x < 0.2:
        gesture = "right"   # In mirrored view (webcam), left side of screen is user's right
    elif wrist.x > 0.8:
        gesture = "left"    # In mirrored view (webcam), right side of screen is user's left
    elif wrist.y < 0.2:
        gesture = "forward" # Top of screen
    elif wrist.y > 0.8:
        gesture = "back"    # Bottom of screen
    
    return gesture

# ----------------------------------------------------------------
# Main Loop (Async)
# ----------------------------------------------------------------
async def main():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"Error: Could not open camera index {CAMERA_INDEX}.")
        return

    # Start WebSocket Server
    print("Starting WebSocket server on ws://localhost:8765...")
    async with websockets.serve(websocket_handler, "localhost", 8765):
        print("Camera running. Press 'q' to quit.")
        
        while cap.isOpened():
            # Check if user pressed 'q'
            # Note: cv2.waitKey(1) creates a small blocking delay, which is fine here
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            ret, frame = cap.read()
            if not ret:
                print("Failed to receive frame.")
                break

            # 1. Image Processing
            # Flip horizontally for selfie-view display
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # 2. Hand Tracking
            result = hands.process(rgb)

            # 3. Gesture Logic + Drawing
            active_gesture = None
            
            if result.multi_hand_landmarks:
                for hand_landmarks in result.multi_hand_landmarks:
                    mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                    
                    # Compute gestures based on landmarks
                    active_gesture = detect_gesture(hand_landmarks)
                    
                    # Visual Feedback on Video
                    if active_gesture:
                        cv2.putText(frame, active_gesture.upper(), (50, 50), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # 4. Send to WebSocket Clients
            if active_gesture:
                await broadcast({"gesture": active_gesture})

            # Show the frame
            cv2.imshow("MediaPipe Gesture Controller", frame)

            # Yield control to asyncio event loop (for websocket tasks)
            await asyncio.sleep(0.001)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram stopped by user.")
