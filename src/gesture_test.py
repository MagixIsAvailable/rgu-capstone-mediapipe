import cv2
import mediapipe as mp

# Initialise MediaPipe Hands
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Change index to whichever number your GO 3S was on
cap = cv2.VideoCapture(1)
if not cap.isOpened():
    print("Camera 1 not found. Trying Camera 0...")
    cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Could not open video source.")

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
        for hand_landmarks in result.multi_hand_landmarks:
            mp_draw.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
        print("Hand detected")

    cv2.imshow("MediaPipe GO 3S Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()