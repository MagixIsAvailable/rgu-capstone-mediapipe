"""
Module: setup_camera.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Interactive camera selection utility. Iterates through available camera indices (0-9),
displays a live preview for each, and saves the selected camera index plus user label
to camera_config.txt for use by main.py. Run once on first installation or when camera
hardware changes.

This utility allows non-technical end-users to configure which physical camera to use
without editing code or configuration files. Critical for deployment on diverse hardware.

Key outputs:
- camera_config.txt: JSON file containing camera_index (int) and camera_label (str)
  Used by main.py to load camera settings at startup.

Dependencies:
cv2 (OpenCV)

Usage:
python src/setup_camera.py
Then select a camera using interactive prompts (y/n/q keys).

Known limitations:
- Only checks indices 0-9 (max 10 cameras); extended iteration removed for UX reasons
- No validation that selected camera can sustain full frame rate required by main.py
- Camera label is optional but recommended for documentation (e.g., "Logitech C920")
"""
import cv2
import os
import json

# Get the absolute path of the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    """Interactive camera selection and configuration wizard.
    
    Algorithm:
        1. Iterate through camera indices 0-9
        2. For each valid camera (cv2.VideoCapture succeeds + first frame reads):
           - Display camera preview window with index label
           - Wait for user input:
             * 'y' = select this camera, save config, exit
             * 'n' = try next camera index
             * 'q' = quit without saving, exit
        3. Save selected index and label to camera_config.txt in JSON format
    
    Camera validation:
        cv2.VideoCapture(i) succeeds but may not actually deliver frames (some drivers
        report success before checking for camera presence, especially USB devices).
        The code validates by attempting cv2.read() to ensure real frame data.
    
    User label input:
        After selection, user is prompted for an optional friendly label.
        If empty, defaults to "camera_index_{N}" where N is the camera index.
        Stored in camera_config.txt for reference (e.g., in logs, UI displays).
    
    Output format:
        JSON payload: {"camera_index": <int>, "camera_label": "<str>"}
        File: camera_config.txt (relative to this script's directory)
    
    Returns:
        None (but writes camera_config.txt on success)
    
    Side effects:
        - Opens cv2 window titled "Camera Selector"
        - Writes JSON to camera_config.txt (overwrites on repeated runs)
        - Prints status to stdout (user guidance + success/exit messages)
    
    References:
        - main.py: Reads camera_config.txt at startup
        - Chapter 3, Section 3.2: Camera negotiation process
    """
    print("Scanning cameras... Press 'y' to select, 'n' for next, 'q' to quit.")
    
    # Check camera indices 0-9 (covers most common multi-camera setups)
    # Iteration limit chosen to balance compatibility with UX (user shouldn't wait >30s)
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # Try reading one frame to confirm camera is actually responsive
            # (Some USB devices report isOpened=True but never deliver frames)
            ret, frame = cap.read()
            if not ret:
                # Camera object exists but isn't delivering frames — skip it
                cap.release()
                continue

            print(f"Checking Camera Index {i}...")
            
            # Continuous preview loop for this camera index
            while True:
                ret, frame = cap.read()
                if not ret:
                    # Frame read failed (e.g., camera disconnected mid-stream)
                    break
                
                # Add visual labels to frame for user guidance
                cv2.putText(frame, f"Camera Index {i}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, "Press 'y' to select, 'n' for next", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                cv2.imshow('Camera Selector', frame)
                
                # Wait 1ms for key press, extract keycode with & 0xFF
                # (0xFF mask required on Windows to filter out system key modifiers)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('y'):
                    # User selected this camera — prompt for optional label
                    camera_label = input(
                        "Enter a camera label (e.g., Logitech C920), or press Enter to use default: "
                    ).strip()
                    if not camera_label:
                        # Default label uses index if user provides empty string
                        camera_label = f"camera_index_{i}"

                    # Write JSON config file
                    config_path = os.path.join(SCRIPT_DIR, "camera_config.txt")
                    payload = {
                        "camera_index": i,
                        "camera_label": camera_label,
                    }
                    with open(config_path, "w") as f:
                        json.dump(payload, f)  # Write Python dict as JSON
                    print(
                        f"\n>>> SAVED CAMERA INDEX {i} ({camera_label}) to '{config_path}' <<<"
                    )
                    cap.release()
                    cv2.destroyAllWindows()
                    return  # Success — exit
                elif key == ord('n'):
                    # User rejected this camera — try next index
                    break
                elif key == ord('q'):
                    # User quit — exit immediately without saving
                    cap.release()
                    cv2.destroyAllWindows()
                    return  # Exit
            cap.release()
    
    # No more cameras found after checking 0-9
    cv2.destroyAllWindows()
    print("No more cameras found.")

if __name__ == "__main__":
    main()