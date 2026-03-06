import cv2
import sys
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
cap = None
for i in range(3):  # Try indices 0, 1, 2
    print(f"Testing Camera Index {i}...")
    temp_cap = cv2.VideoCapture(i)
    if temp_cap.isOpened():
        ret, test_frame = temp_cap.read()
        if ret:
            print(f"Success: Camera Index {i} is working. Resolution: {test_frame.shape}")
            cap = temp_cap
            break
        temp_cap.release()

if cap is None:
    print("Error: Could not open any video source.")
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
        for hand_landmarks in result.multi_hand_landmarks:
            mp_draw.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

    cv2.imshow("MediaPipe GO 3S Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()