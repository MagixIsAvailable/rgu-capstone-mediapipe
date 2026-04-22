# VisionInput Source and Attribution Record

This file documents external sources and attribution status for the project.
It is intended to support university requirements on source identification,
signposting, and proportion of non-original code.

## 1) Project-Authored Code
The implementation in the `src/` folder is authored for this project by:
- Michal Lazovy

Core authored modules include:
- `src/main.py`
- `src/gesture_mapping.py`
- `src/vigem_output.py`
- `src/visualiser.py`
- `src/setup_camera.py`
- `src/config.py`

## 2) External Libraries and Frameworks
These dependencies are used via their public APIs (imported packages), not by
copying large blocks of their internal source code.

- OpenCV (`cv2`): camera capture and frame/image processing
- MediaPipe (`mediapipe`): hand landmark detection/tracking
- websockets (`websockets`): async telemetry transport
- ViGEm client (`vgamepad`): virtual Xbox controller output
- NumPy (`numpy`): numerical operations for rendering/overlay helpers

See `requirements.txt` for the package list used in this repository.

## 3) Signposted Sections in Source Files
Where needed, explicit "ATTRIBUTION NOTE (SIGNPOSTED SECTION)" headers are
added above specific functions to clearly delimit implementation sections and
state source type/pattern/reference.

Current signposted examples:
- `websocket_handler()` in `src/main.py`
- `broadcast()` in `src/main.py`
- `ema_smooth_pair()` in `src/main.py`
- `_get_gamepad()` in `src/vigem_output.py`

## 4) Tutorials / Q&A Copying Status
No known direct copy-paste code from tutorials, Stack Overflow, or other
unattributed third-party snippets has been intentionally included.

## 5) AI Assistance Statement
Development assistance tools (for example, AI coding assistants) may be used
for drafting, refactoring suggestions, and documentation phrasing. Final code
selection, integration, validation, and responsibility remain with the author.

If any future section is adopted verbatim from an external source, it should be
added to this file with:
- source URL or citation
- license (if applicable)
- exact file/function location
- short purpose note
