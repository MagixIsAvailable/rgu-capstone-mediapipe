# VisionInput - 360° Room Gesture Controller

**VisionInput** is a plug-and-play gesture controller designed for immersive projection environments. It leverages MediaPipe hand tracking to emulate an Xbox 360 controller, allowing you to control PC games and applications using natural hand movements.

## System Requirements

- **OS**: Windows 10 or Windows 11 (Required for ViGEmBus)
- **Python**: 3.10 or 3.11 (Restricted by MediaPipe Legacy API)
- **Driver**: [ViGEmBus Driver](https://github.com/nefarius/ViGEmBus/releases) (Must be installed manually)

## Hardware

### Developed & Tested On
- **CPU**: AMD Ryzen 9 5950X
- **GPU**: NVIDIA RTX 3090
- **RAM**: 64GB DDR4
- **Camera**: Tested with Insta360 GO 3S (webcam mode) and older Creative webcams.
- **Controller Reference**: Mappings verified against a Razer Wolverine V2 using `joy.cpl`.

### Recommendations
While developed on high-end hardware, the system is designed to scale.
- **Webcam**: Any functional USB webcam (720p+ recommended for best tracking).
- **CPU**: Modern multi-core processor (MediaPipe relies heavily on CPU).
- **Lighting**: Adequate lighting is crucial for stable hand tracking.

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

## Usage Guide

1. **Start the Controller**: Run the `main.py` script. You should see "VX360Gamepad initialized successfully" in the terminal.
2. **Check Calibration**: Stand in front of the camera. The system will calibrate for 3 seconds (don't move during this time).
3. **Open Your Game**: Leave the Python window running and launch any game that supports Xbox controllers (e.g., Rocket League, Fall Guys, or generic racing games).
4. **Play**: Your hand movements now control the game directly!
   - *Tip: Keep the debug window open on a second monitor to check your hand tracking status.*

## Customization

You can fine-tune the controller sensitivity by editing the `CONFIG` dictionary at the top of `src/main.py`:

- `SENSITIVITY`: Increase this to make the virtual joystick more responsive (requires less hand movement).
- `TILT_GAIN`: Adjusts how much wrist tilt is needed for full joystick deflection.
- `NEUTRAL_Y_OFFSET`: Calibrate the "resting" vertical position of your hands if you find the character drifting forward/backward automatically.

## Controls & Gestures

The system uses a split-hand control scheme optimized for navigation and interaction.

### Left Hand (Navigation & D-Pad)
Controls the **Left Analog Stick** and **D-Pad** simultaneously.

#### Analog Stick (Movement)
- **Horizontal (X-Axis)**: Tilt your wrist **Left/Right**.
- **Vertical (Y-Axis)**: Uses **Inter-Hand Angle**.
  - **Move Forward**: Raise your Right Hand relative to your Left Hand.
  - **Move Backward**: Lower your Right Hand relative to your Left Hand.
  - *Fallback*: If only the Left Hand is visible, wrist tilt (Up/Down) is used.

#### D-Pad (Directional Buttons)
Finger bends trigger D-Pad inputs, independent of wrist movement.
- **Index Finger Bent**: D-Pad Up
- **Middle Finger Bent**: D-Pad Down
- **Ring Finger Bent**: D-Pad Left
- **Pinky Finger Bent**: D-Pad Right

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

### Web Interface (Experimental)
The project includes a 360° A-Frame web viewer (`web/index.html`). To use it:
1. Set `WEBSOCKET_ENABLED = True` in `src/main.py`.
2. Open `web/index.html` in your browser.
3. The Python script will broadcast hand gestures to the web scene via WebSocket.

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
