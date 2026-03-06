import cv2

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
                    with open("camera_config.txt", "w") as f:
                        f.write(str(i))
                    print(f"\n>>> SAVED CAMERA INDEX {i} to 'camera_config.txt' <<<")
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