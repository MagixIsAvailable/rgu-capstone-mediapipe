# VisionInput - 360° Room Gesture Controller

**VisionInput** is a plug-and-play gesture controller designed for immersive projection environments. It replaces standard PC game controller input using real-time MediaPipe hand tracking and broadcasts interaction data via WebSockets for 360° visualization.

## System Requirements

- **OS**: Windows 10 or Windows 11 (Required for ViGEmBus)
- **Python**: 3.10 or 3.11 (Restricted by MediaPipe Legacy API)
- **Driver**: [ViGEmBus Driver](https://github.com/nefarius/ViGEmBus/releases) (Must be installed manually)

## Installation

1. **Install ViGEmBus Driver**
   - Download the latest installer from the link above and run it.

2. **Clone the Repository**
   ```powershell
   git clone https://github.com/MagixIsAvailable/rgu-capstone-mediapipe.git
   cd rgu-capstone-mediapipe
   ```

3. **Install Dependencies**
   It is recommended to use a virtual environment.
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

## Configuration

1. **Camera Setup**
   Run the interactive camera selector to identify your webcam index:
   ```powershell
   python src/setup_camera.py
   ```
   Follow the on-screen prompts (Press 'y' to select, 'n' to skip) to save your configuration.

2. **Gesture Mapping**
   Customize controller bindings by editing `config/gesture_map.json`.

## Usage

1. **Start the Controller Logic**
   Launch the main backend script:
   ```powershell
   python src/main.py
   ```
   *Optional: Add `--visualise` to see the debug camera overlay.*
   ```powershell
   python src/main.py --visualise
   ```

2. **Launch the 360° Viewer**
   Open `web/index.html` in your web browser. This interface connects to the backend via WebSocket (port 8765) to receive gesture events in real-time.

## Feature Overview

- **Hand Tracking**: Uses MediaPipe to detect hand landmarks.
- **Gesture Recognition**: Supports Pinch, Swipe (Left/Right/Up/Down), Point, Fist, and Open Palm.
- **Input Emulation**: Mapped to a virtual Xbox 360 controller via ViGEmBus.
- **WebSocket Server**: Broadcasts gesture events to the web frontend.

## Project Structure

```text
rgu-capstone-mediapipe/
├── config/              # Configuration files (gesture mappings)
├── src/                 # Core source code (main pipeline)
├── web/                 # 360° web viewer application
├── archive/             # Historical files & prototypes (non-production)
├── README.md            # You are here
└── requirements.txt     # Python dependencies
```

## Troubleshooting

- **No Controller Detected**: Ensure you have installed the ViGEmBus driver and that you hear the Windows USB connection sound when the script starts.
- **WebSocket Error**: Ensure the browser and the Python script are running on the same machine (localhost). Port 8765 must be free.
- **Camera Index Error**: If the camera fails to open, run `src/setup_camera.py` again to re-select a valid camera.

## License

This project is licensed under the MIT License.