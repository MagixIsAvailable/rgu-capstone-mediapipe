# VisionInput — MediaPipe gesture-based Xbox controller wrapper

**VisionInput** is a plug-and-play gesture controller that replaces standard PC game controller input in an immersive 360° room environment using real-time hand gesture detection.

## Prerequisites
- **OS**: Windows 10 or Windows 11
- **Python**: Version 3.10 or higher
- **Driver**: ViGEmBus driver installed (Required for virtual controller emulation)

## Installation

1. **Install ViGEmBus Driver**
   - Download and install the latest release from:  
     [https://github.com/nefarius/ViGEmBus/releases](https://github.com/nefarius/ViGEmBus/releases)

2. **Clone the Repository**
   ```bash
   git clone https://github.com/MagixIsAvailable/rgu-capstone-mediapipe.git
   cd rgu-capstone-mediapipe
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Connect your webcam.
2. Run the wrapper script:
   ```bash
   python gesture_wrapper.py
   ```
3. The script will:
   - Download the necessary MediaPipe model (`hand_landmarker.task`) automatically on first run.
   - Start a camera feed window visualizing detected gestures.
   - Create a virtual Xbox 360 controller labeled "VisionInput".

## Configuration
- **Camera Selection**: To change the camera index (default is 0), create or edit `src/camera_config.txt` inside the `src/` folder with the index number (e.g., `1`).
- **Gesture Mapping**: Edit `gesture_map.json` in the root directory to customize controller bindings.

## Project Structure
- `gesture_wrapper.py`: Main entry point.
- `src/`: Core logic and helper scripts.
- `gesture_map.json`: Gesture-to-controller mapping configuration.
- `requirements.txt`: Python package dependencies.
