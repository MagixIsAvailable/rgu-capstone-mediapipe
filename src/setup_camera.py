"""
Module: setup_camera.py
Project: VisionInput — Gesture-Based Controller for Immersive Projection Environments
Author: Michal Lazovy | RGU CM4134 Honours Capstone 2026
Supervisor: Dr John N.A. Brown | Partner: James Hutton Institute, Aberdeen

Purpose:
Interactive camera selection utility for VisionInput. Iterates through available camera indices, displays a live preview for each, and saves the selected camera index to camera_config.txt for use by main.py. Run once on first installation or when the camera setup changes.

Dependencies:
cv2

Usage:
python src/setup_camera.py
"""
import cv2
import os

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
                    config_path = os.path.join(SCRIPT_DIR, "camera_config.txt")
                    with open(config_path, "w") as f:
                        f.write(str(i))
                    print(f"\n>>> SAVED CAMERA INDEX {i} to '{config_path}' <<<")
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