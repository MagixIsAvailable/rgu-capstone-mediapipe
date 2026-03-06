## Week 1 — 6 March 2026
- Set up GitHub repo
- Installed MediaPipe + OpenCV
- Confirmed GO 3S works as USB webcam
- Hand landmark detection working on both cameras
- Sent proposal to supervisor for review

1. Architecture Adjustment
Initial Plan: Run everything in the browser (MediaPipe JS + A-Frame).
Pivot: Switched to a Hybrid Architecture (Python Backend + Browser Frontend).
Reason: Leveraging your working Python environment avoids complex browser-based WASM setup and gives us better performance/control.
How it works: Python script captures video & detects gestures -> Sends text commands via WebSocket -> Browser (A-Frame) receives commands & moves camera.
2. Issues Encountered & Fixes
🔴 Issue 1: ModuleNotFoundError: No module named 'websockets'

Cause: The script was being run by the global Python installation instead of the project's virtual environment (.venv).
Fix: Explicitly ran the script using the .venv executable: & python.exe src\gesture_test.py.
🔴 Issue 2: Audio Driver Crash (PortAudio / sounddevice)

Cause: Importing mediapipe attempts to initialize audio drivers even if we only use vision features. On some Windows systems or remote setups, this crashes.
Fix: Added a mock for sounddevice before importing MediaPipe to bypass this check:
🔴 Issue 3: AttributeError: module 'mediapipe' has no attribute 'solutions'

Cause: The installed version of MediaPipe was likely newer or incomplete, lacking the older solutions API (e.g., mp.solutions.hands).
Fix: Migrated the code to the modern MediaPipe Tasks API:
Used mediapipe.tasks.python.vision.HandLandmarker.
Downloaded the required model file: hand_landmarker.task.
Rewrote the detection loop to use detect_for_video with timestamps.
🔴 Issue 4: Missing Visualization Tools

Cause: The new Tasks API does not include the mp_draw utility from the legacy API.
Fix: Wrote a custom draw_landmarks_on_image function using OpenCV and NumPy to manually draw landmarks and connections on the frames.
3. Current Status
Python (gesture_test.py): Successfully tracks hands, detects pinch/directions, and broadcasts to ws://localhost:8765.
Web (index.html): A-Frame scene connects to the WebSocket and smoothly updates the camera position based on gestures.