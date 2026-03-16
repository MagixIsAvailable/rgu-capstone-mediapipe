# VisionInput - 360° Room Gesture Controller

**VisionInput** is a plug-and-play gesture controller designed for immersive projection environments. It leverages MediaPipe hand tracking to emulate an Xbox 360 controller, allowing you to control PC games and applications using natural hand movements.

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

2. **Run the Controller**
   Launch the main backend script:
   ```powershell
   python src/main.py --visualise
   ```
   *The `--visualise` flag opens a debug window showing the camera feed and skeleton overlay.*

## Controls & Gestures

The system uses a split-hand control scheme optimized for navigation and interaction.

### Left Hand (Navigation / Joystick)
Controls the **Left Analog Stick** (WASD movement).

- **Horizontal (X-Axis)**: Tilt your wrist Left/Right.
- **Vertical (Y-Axis)**: Uses **Inter-Hand Angle**.
  - **Move Forward**: Raise your Right Hand relative to your Left Hand.
  - **Move Backward**: Lower your Right Hand relative to your Left Hand.
  - *Fallback*: If only the Left Hand is visible, wrist tilt (Up/Down) is used.

### Right Hand (Action Buttons)
Action mapping uses a **2-Layer Gesture System**:

| Gesture | Controller Input | Function |
| :--- | :--- | :--- |
| **Index Pinch** | **LB** | Left Bumper |
| **Middle Pinch** | **RB** | Right Bumper |
| **Ring Pinch** | **LT** | Left Trigger |
| **Pinky Pinch** | **RT** | Right Trigger |
| **Index Finger Bent** | **A** | Button 1 (Select) |
| **Middle Finger Bent** | **B** | Button 2 (Back/Cancel) |
| **Ring Finger Bent** | **X** | Button 3 (Interact) |
| **Pinky Finger Bent** | **Y** | Button 4 (Menu) |
| **Index + Middle Bent** | **Back** | Button 7 (View) |
| **Index + Ring Bent** | **Start** | Button 8 (Menu) |
| **Open Palm** | **Neutral** | No Input |

## Feature Overview

- **Hand Tracking**: Uses MediaPipe to detect hand landmarks in real-time.
- **2-Layer Gesture System**: Distinguishes between "Bends" (face buttons) and "Pinches" (shoulders/triggers) for versatile input.
- **Inter-Hand Physics**: Calculates relative angles between hands for smooth, ergonomic joystick control (solving the "gorilla arm" fatigue issue).
- **Proximity Guard**: Prevents cursor jitter when hands are too close together.
- **Input Emulation**: Mapped to a virtual Xbox 360 controller via ViGEmBus.
- **WebSocket Server**: Broadcasts gesture events to the web frontend (optional).

## Project Structure

```text
rgu-capstone-mediapipe/
├── config/              # Configuration files (gesture mappings)
├── src/                 # Core source code (main pipeline)
│   ├── main.py          # Entry point & gesture logic
│   ├── vigem_output.py  # Virtual controller driver
│   ├── setup_camera.py  # Camera selection utility
│   └── visualiser.py    # Debug overlay drawing
├── web/                 # 360° web viewer application (A-Frame)
├── archive/             # Historical files & prototypes
├── README.md            # Project documentation
└── requirements.txt     # Python dependencies
```

## Troubleshooting

- **No Controller Detected**: Ensure you have installed the ViGEmBus driver. You should hear the Windows USB connection sound when the script starts.
- **Window Closes Immediately**: If `camera_config.txt` is invalid, the script will pause and ask you to run `python src/setup_camera.py`.
- **"Right Hand Up" not registering**: Ensure your hands are at least 10cm apart. The system ignores inputs when hands are touching to prevent jitter.

## License

This project is licensed under the MIT License.
