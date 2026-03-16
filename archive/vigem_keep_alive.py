import time
import sys

# Try to import the output module
try:
    import vigem_output
except ImportError:
    print("Could not import vigem_output. Make sure you are in the project root.")
    sys.exit(1)

def main():
    print("=================================================")
    print("   ViGEm KEEP ALIVE TEST")
    print("=================================================")
    print("1. Go to: https://hardwaretester.com/gamepad")
    print("2. You should see 'Xbox 360 Controller' detected.")
    print("3. This script will press 'A' every second.")
    print("4. Press CTRL+C in this terminal to stop.")
    print("=================================================\n")

    # Initialize the controller
    gamepad = vigem_output._get_gamepad()
    
    if gamepad is None:
        print("\n[ERROR] Controller could not be initialized.")
        print("Please make sure you installed the ViGEmBus Driver.")
        print("Download: https://github.com/nefarius/ViGEmBus/releases")
        return

    try:
        while True:
            # Press 'A' (SELECT/PINCH)
            print(">> Pressing 'A' button...")
            vigem_output.apply_gesture("SELECT")
            time.sleep(0.5)
            
            # Release
            vigem_output.release_all()
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\nStopping test...")
        vigem_output.release_all()
        print("Controller disconnected.")

if __name__ == "__main__":
    main()
