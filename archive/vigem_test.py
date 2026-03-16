import time
import vigem_output

def main():
    print("=== ViGEm Controller Smoke Test ===")
    print("Open 'joy.cpl' (Game Controllers) in Windows to verify inputs.")
    
    gestures = [
        "SWIPE_RIGHT", "SWIPE_LEFT", "SWIPE_UP", "SWIPE_DOWN",
        "PINCH", "FIST", "POINT", "OPEN", "UNKNOWN_TEST"
    ]

    for gesture in gestures:
        print(f"\nTesting gesture: {gesture}")
        vigem_output.apply_gesture(gesture)
        time.sleep(1)

    print("\nTest sequence finished. Releasing all inputs...")
    vigem_output.release_all()
    print("Done.")

if __name__ == "__main__":
    main()