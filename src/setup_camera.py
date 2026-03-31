"""
Module: setup_camera.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Interactive camera selection utility for VisionInput. Iterates through available camera indices, displays a live preview for each, and saves the selected camera index plus an optional user label to camera_config.txt for use by main.py. Run once on first installation or when the camera setup changes.

Dependencies:
cv2

Usage:
python src/setup_camera.py
"""
import cv2
import os
import json

# Get the absolute path of the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    print("Scanning cameras... Press 'y' to select, 'n' for next, 'q' to quit.")
    
    # Check indices 0 to 9
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # Read a frame to ensure it's working
            ret, frame = cap.read()
            if not ret:
                cap.release()
                continue

            print(f"Checking Camera Index {i}...")
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                cv2.putText(frame, f"Camera Index {i}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, "Press 'y' to select, 'n' for next", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                cv2.imshow('Camera Selector', frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('y'):
                    camera_label = input(
                        "Enter a camera label (e.g., Logitech C920), or press Enter to use default: "
                    ).strip()
                    if not camera_label:
                        camera_label = f"camera_index_{i}"

                    config_path = os.path.join(SCRIPT_DIR, "camera_config.txt")
                    payload = {
                        "camera_index": i,
                        "camera_label": camera_label,
                    }
                    with open(config_path, "w") as f:
                        json.dump(payload, f)
                    print(
                        f"\n>>> SAVED CAMERA INDEX {i} ({camera_label}) to '{config_path}' <<<"
                    )
                    cap.release()
                    cv2.destroyAllWindows()
                    return
                elif key == ord('n'):
                    break
                elif key == ord('q'):
                    cap.release()
                    cv2.destroyAllWindows()
                    return
            cap.release()
    
    cv2.destroyAllWindows()
    print("No more cameras found.")

if __name__ == "__main__":
    main()