import cv2
import sys
import mediapipe as mp

# Initialise MediaPipe Hands
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Load camera configuration
try:
    with open("camera_config.txt", "r") as f:
        CAMERA_INDEX = int(f.read().strip())
    print(f"Loading Camera Index {CAMERA_INDEX} from camera_config.txt...")
except FileNotFoundError:
    print("Error: 'camera_config.txt' not found.")
    print("Please run 'python src/find_camera.py' first to select your camera.")
    sys.exit()

cap = cv2.VideoCapture(CAMERA_INDEX)

if not cap.isOpened():
    print(f"Error: Could not open camera index {CAMERA_INDEX}.")
    sys.exit()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Failed to receive frame.")
        break

    # Flip and convert
    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Process
    result = hands.process(rgb)

    # Draw landmarks if hand detected
    if result.multi_hand_landmarks:
        for hand_landmarks, hand_info in zip(result.multi_hand_landmarks, result.multi_handedness):
            mp_draw.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            # Get handedness label (Left/Right)
            label = hand_info.classification[0].label
            
            # Display label near the wrist (landmark 0)
            h, w, _ = frame.shape
            cx, cy = int(hand_landmarks.landmark[0].x * w), int(hand_landmarks.landmark[0].y * h)
            cv2.putText(frame, label, (cx, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

    cv2.imshow("MediaPipe GO 3S Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()